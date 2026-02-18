from __future__ import annotations

import logging
import math
import time

import requests
import urllib3
from elasticsearch import Elasticsearch, NotFoundError

try:
    from opensearchpy import NotFoundError as OpenSearchNotFoundError
    from opensearchpy import (
        OpenSearch,
    )

    OPENSEARCH_AVAILABLE = True
except ImportError:
    # Try alternative import path
    try:
        from opensearch_py import NotFoundError as OpenSearchNotFoundError
        from opensearch_py import (
            OpenSearch,
        )

        OPENSEARCH_AVAILABLE = True
    except ImportError:
        OPENSEARCH_AVAILABLE = False
        OpenSearch = None
        OpenSearchNotFoundError = None

from krkn_lib.models.elastic.models import (
    ElasticAlert,
    ElasticChaosRunTelemetry,
    ElasticMetric,
)
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.utils.safe_logger import SafeLogger


class KrknElastic:
    es = None
    backend_type = None  # 'elasticsearch' or 'opensearch'

    def __init__(
        self,
        safe_logger: SafeLogger,
        elastic_url: str,
        elastic_port: int = 443,
        verify_certs: bool = False,
        username: str = None,
        password: str = None,
    ):
        es_logger = logging.getLogger("elasticsearch")
        es_logger.setLevel(logging.WARNING)
        opensearch_logger = logging.getLogger("opensearch")
        opensearch_logger.setLevel(logging.WARNING)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        urllib3.disable_warnings(DeprecationWarning)
        es_transport_logger = logging.getLogger("elastic_transport.transport")
        es_transport_logger.setLevel(logging.CRITICAL)
        self.safe_logger = safe_logger

        try:
            if not elastic_url:
                raise Exception("elastic search url is not valid")
            if not elastic_port:
                raise Exception("elastic port is not valid")

            credentials = (
                (username, password) if username and password else None
            )

            # Auto-detect backend type
            self.backend_type = self._detect_backend(
                elastic_url, elastic_port, credentials, verify_certs
            )
            self.safe_logger.info(
                f"Auto-detected backend: {self.backend_type}"
            )

            # Create the appropriate client based on backend type
            if self.backend_type == "opensearch":
                if not OPENSEARCH_AVAILABLE:
                    raise Exception(
                        "OpenSearch backend requested but "
                        "opensearch-py is not installed. "
                        "Install it with: pip install opensearch-py"
                    )
                # Parse host from URL
                host = elastic_url.replace("https://", "")
                host = host.replace("http://", "")
                self.es = OpenSearch(
                    hosts=[{"host": host, "port": elastic_port}],
                    http_auth=credentials,
                    use_ssl=elastic_url.startswith("https"),
                    verify_certs=verify_certs,
                    ssl_show_warn=False,
                )
            elif self.backend_type == "elasticsearch":
                self.es = Elasticsearch(
                    f"{elastic_url}:{elastic_port}",
                    http_auth=credentials,
                    verify_certs=verify_certs,
                    ssl_show_warn=False,
                )
        except Exception as e:
            self.safe_logger.error(
                "Failed to initialize %s: %s" % (self.backend_type, e)
            )
            raise e

    def _detect_backend(
        self,
        elastic_url: str,
        elastic_port: int,
        credentials: tuple = None,
        verify_certs: bool = False,
    ) -> str:
        """
        Auto-detect whether the backend is Elasticsearch or OpenSearch
        by querying the cluster info endpoint.

        :param elastic_url: The URL of the search backend
        :param elastic_port: The port of the search backend
        :param credentials: Optional tuple of (username, password)
        :param verify_certs: Whether to verify SSL certificates
        :return: "elasticsearch" or "opensearch"
        """
        # Build the info endpoint URL
        base_url = f"{elastic_url}:{elastic_port}"
        info_url = f"{base_url}/"

        try:
            # Make a request to the info endpoint
            auth = credentials if credentials else None
            response = requests.get(
                info_url,
                auth=auth,
                verify=verify_certs,
                timeout=10,
            )

            if response.status_code == 200:
                info = response.json()

                # Check for OpenSearch-specific fields
                if "version" in info:
                    version_info = info["version"]

                    # OpenSearch includes "distribution" field
                    if "distribution" in version_info:
                        distribution = version_info["distribution"].lower()
                        if "opensearch" in distribution:
                            return "opensearch"

                    # Check build_type or other OpenSearch indicators
                    if "build_type" in version_info:
                        build_type = version_info.get("build_type", "").lower()
                        if "opensearch" in build_type:
                            return "opensearch"

                    # Check tagline (OpenSearch has different tagline)
                    tagline = info.get("tagline", "").lower()
                    if "opensearch" in tagline:
                        return "opensearch"

                    # Check cluster name for opensearch indicators
                    cluster_name = info.get("cluster_name", "").lower()
                    if "opensearch" in cluster_name:
                        return "opensearch"

                # Default to ES if no OpenSearch indicators found
                self.safe_logger.info(
                    "No OpenSearch indicators found, using Elasticsearch"
                )
                return "elasticsearch"

        except Exception as e:
            self.safe_logger.warning(
                f"Failed to auto-detect backend type: {e}. "
                f"Defaulting to Elasticsearch"
            )
            return "elasticsearch"

    def _is_not_found_error(self, exception: Exception) -> bool:
        """
        Helper method to check if an exception is a NotFoundError
        for either Elasticsearch or OpenSearch
        """
        if isinstance(exception, NotFoundError):
            return True
        if (
            OPENSEARCH_AVAILABLE
            and OpenSearchNotFoundError
            and isinstance(exception, OpenSearchNotFoundError)
        ):
            return True
        return False

    def upload_data_to_elasticsearch(self, item: dict, index: str = "") -> int:
        """uploads captured data in item dictionary to Elasticsearch


        :param item: the data to post to elastic search
        :param index: the elastic search index pattern to post to

        :return: the time taken to post the result,
                will be 0 if index and es are blank
        """

        if self.es and index != "":
            # Attach to elastic search and attempt index creation
            start = time.time()
            self.safe_logger.info(
                f"Uploading item {item} to index {index} in Elasticsearch"
            )
            try:
                response = self.es.index(index=index, body=item)
                self.safe_logger.info(f"Response back was {response}")
                if response["result"] != "created":
                    self.safe_logger.error(
                        f"Error trying to create new item in {index}"
                    )
                    return -1
            except Exception as e:
                self.safe_logger.error(f"Error trying to create new item: {e}")
                return -1
            end = time.time()
            elapsed_time = end - start

            # return elapsed time for upload if no issues
            return math.ceil(elapsed_time)
        return 0

    def upload_metrics_to_elasticsearch(
        self,
        run_uuid: str,
        raw_data: list[dict[str, str | int | float]],
        index: str,
    ) -> int:
        """
        Saves raw data returned from the Krkn prometheus
        client to elastic search as a ElasticMetric object
        raw data will be a mixed types dictionary in the format
        {"name":"str", "values":[(10, '3.14'), (11,'3.15').....]

        :param run_uuid: the krkn run id
        :param raw_data: the mixed type dictionary (will be validated
            checking the attributes types )
        :param index: the elasticsearch index where
            the object will be stored
        :return: the time needed to save if succeeded -1 if failed
        """
        if not index:
            raise Exception("index cannot be None or empty")
        if not run_uuid:
            raise Exception("run uuid cannot be None or empty")
        time_start = time.time()
        try:
            for metric in raw_data:
                result = self.push_metric(
                    ElasticMetric(run_uuid=run_uuid, **metric),
                    index,
                )
                if result == -1:
                    self.safe_logger.error(
                        f"failed to save metric "
                        f"to elasticsearch : {metric}"
                    )

            return int(time.time() - time_start)
        except Exception as e:
            self.safe_logger.error(f"Upload metric exception: {e}")
            return -1

    def push_alert(self, alert: ElasticAlert, index: str) -> int:
        """
        Pushes an ElasticAlert object to elastic

        :param alert: the populated ElasticAlert object
        :param index: the index where the ElasticAlert Object
            is pushed
        :return: the time needed to save if succeeded -1 if failed
        """
        if not index:
            raise Exception("index cannot be None or empty")
        try:
            time_start = time.time()
            # Use to_dict() and low-level index() for compatibility
            # with both Elasticsearch and OpenSearch
            self.es.index(index=index, body=alert.to_dict())
            return int(time.time() - time_start)
        except Exception as e:
            self.safe_logger.error(f"Push alert exception: {e}")
            return -1

    def push_metric(self, metric: ElasticMetric, index: str) -> int:
        """
        Pushes an ElasticMetric object to elastic

        :param metric: the populated ElasticMetric object
        :param index: the index where the ElasticMetric Object
            is pushed
        :return: the time needed to save if succeeded -1 if failed
        """
        if not index:
            raise Exception("index cannot be None or empty")
        try:
            time_start = time.time()
            # Use to_dict() and low-level index() for compatibility
            # with both Elasticsearch and OpenSearch
            self.es.index(index=index, body=metric.to_dict())
            return int(time.time() - time_start)
        except Exception as e:
            print("error" + str(e))
            self.safe_logger.error(f"Exception pushing metric: {e}")
            return -1

    def push_telemetry(self, telemetry: ChaosRunTelemetry, index: str):
        if not index:
            raise Exception("index cannot be None or empty")
        try:
            elastic_chaos = ElasticChaosRunTelemetry(telemetry)
            time_start = time.time()
            # Use to_dict() and low-level index() for compatibility
            # with both Elasticsearch and OpenSearch
            self.es.index(index=index, body=elastic_chaos.to_dict())
            return int(time.time() - time_start)
        except Exception as e:
            self.safe_logger.info(f"Elastic push telemetry error: {e}")
            return -1

    def search_telemetry(self, run_uuid: str, index: str):
        """
        Searches ElasticChaosRunTelemetry by run_uuid
        :param run_uuid: the Krkn run id to search
        :param index: the index where the ElasticChaosRunTelemetry
            should have been saved
        :return: the list of objects retrieved (Empty if nothing
            has been found)
        """
        try:
            # Use raw search query instead of DSL
            # (works with both ES and OpenSearch)
            query = {"query": {"match": {"run_uuid": run_uuid}}}
            result = self.es.search(index=index, body=query)
            documents = [
                ElasticChaosRunTelemetry(**hit["_source"])
                for hit in result["hits"]["hits"]
            ]
        except Exception as e:
            if self._is_not_found_error(e):
                self.safe_logger.error("Search telemetry not found")
                return []
            raise
        return documents

    def search_alert(self, run_uuid: str, index: str) -> list[ElasticAlert]:
        """
        Searches ElasticAlerts by run_uuid
        :param run_uuid: the Krkn run id to search
        :param index: the index where the ElasticAlert
            should have been saved
        :return: the list of objects retrieved (Empty if nothing
            has been found)
        """
        try:
            # Use raw search query instead of DSL
            # (works with both ES and OpenSearch)
            query = {"query": {"match": {"run_uuid": run_uuid}}}
            result = self.es.search(index=index, body=query)
            documents = [
                ElasticAlert(**hit["_source"])
                for hit in result["hits"]["hits"]
            ]
        except Exception as e:
            if self._is_not_found_error(e):
                self.safe_logger.error("Search alert not found")
                return []
            raise
        return documents

    def search_metric(self, run_uuid: str, index: str) -> list[ElasticMetric]:
        """
        Searches ElasticMetric by run_uuid
        :param run_uuid: the Krkn run id to search
        :param index: the index where the ElasticAlert
            should have been saved
        :return: the list of objects retrieved (Empty if nothing
            has been found)
        """
        try:
            # Use raw search query instead of DSL
            # (works with both ES and OpenSearch)
            query = {"query": {"match": {"run_uuid": run_uuid}}}
            result = self.es.search(index=index, body=query)
            documents = [
                ElasticMetric(**hit["_source"])
                for hit in result["hits"]["hits"]
            ]
        except Exception as e:
            if self._is_not_found_error(e):
                self.safe_logger.error("Search metric not found")
                return []
            raise
        return documents
