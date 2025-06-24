from __future__ import annotations

import logging
import math
import time

import urllib3
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch_dsl import Search

from krkn_lib.models.elastic.models import (
    ElasticAlert,
    ElasticChaosRunTelemetry,
    ElasticMetric,
)
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.utils.safe_logger import SafeLogger


class KrknElastic:
    es = None

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
            # create Elasticsearch object

            credentials = (
                (username, password) if username and password else None
            )
            self.es = Elasticsearch(
                f"{elastic_url}:{elastic_port}",
                http_auth=credentials,
                verify_certs=verify_certs,
                ssl_show_warn=False,
            )
        except Exception as e:
            self.safe_logger.error("Failed to initalize elasticsearch: %s" % e)
            raise e

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
            alert.save(using=self.es, index=index)
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
            metric.save(using=self.es, index=index)
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
            elastic_chaos.save(using=self.es, index=index)
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
            search = Search(using=self.es, index=index).filter(
                "match", run_uuid=run_uuid
            )
            result = search.execute()
            documents = [
                ElasticChaosRunTelemetry(**hit.to_dict()) for hit in result
            ]
        except NotFoundError:
            self.safe_logger.error("Search telemetry not found")
            return []
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
            search = Search(using=self.es, index=index).filter(
                "match", run_uuid=run_uuid
            )
            result = search.execute()
            documents = [ElasticAlert(**hit.to_dict()) for hit in result]
        except NotFoundError:
            self.safe_logger.error("Search alert not found")
            return []
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
            search = Search(using=self.es, index=index).filter(
                "match", run_uuid=run_uuid
            )
            result = search.execute()
            documents = [ElasticMetric(**hit.to_dict()) for hit in result]
        except NotFoundError:
            self.safe_logger.error("Search metric not found")
            return []
        return documents
