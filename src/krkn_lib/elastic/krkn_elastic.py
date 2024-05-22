from __future__ import annotations

import datetime
import time

import math
import urllib3
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch_dsl import Search

from krkn_lib.models.elastic.models import (
    ElasticAlert,
    ElasticMetric,
    ElasticMetricValue,
)
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
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        urllib3.disable_warnings(DeprecationWarning)
        self.safe_logger = safe_logger
        try:
            # create Elasticsearch object
            if elastic_url:
                credentials = (
                    (username, password) if username and password else None
                )
                self.es = Elasticsearch(
                    f"{elastic_url}:{elastic_port}",
                    http_auth=credentials,
                    verify_certs=verify_certs,
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

    def upload_metric_to_elasticsearch(
        self,
        run_id: str,
        raw_data: list[dict[str, list[(int, float)] | str]],
        index: str,
    ) -> int:
        """
        Saves raw data returned from the Krkn prometheus
        client to elastic search as a ElasticMetric object
        raw data will be a mixed types dictionary in the format
        {"name":"str", "values":[(10, 3.14), (11,3.15).....]

        :param run_id: the krkn run id
        :param raw_data: the mixed type dictionary (will be validated
            checking the attributes types )
        :param index: the elasticsearch index where
            the object will be stored
        :return: the time needed to save if succeeded -1 if failed
        """
        time_start = time.time()
        try:
            for metric in raw_data:
                if (
                    "name" in metric
                    and "values" in metric
                    and isinstance(metric["name"], str)
                    and isinstance(metric["values"], list)
                ):
                    values = [
                        ElasticMetricValue(timestamp=v[0], value=v[1])
                        for v in metric["values"]
                        if isinstance(v[0], int) and isinstance(v[1], float)
                    ]
                    metric = ElasticMetric(
                        run_id=run_id,
                        name=metric["name"],
                        values=values,
                        created_at=datetime.datetime.now(),
                    )
                    self.push_metric(metric, index)
            return int(time.time() - time_start)
        except Exception:
            return -1

    def push_alert(self, alert: ElasticAlert, index: str) -> int:
        """
        Pushes an ElasticAlert object to elastic

        :param alert: the populated ElasticAlert object
        :param index: the index where the ElasticAlert Object
            is pushed
        :return: the time needed to save if succeeded -1 if failed
        """
        try:
            time_start = time.time()
            alert.save(using=self.es, index=index)
            return int(time.time() - time_start)
        except Exception:
            return -1

    def push_metric(self, metric: ElasticMetric, index: str) -> int:
        """
        Pushes an ElasticMetric object to elastic

        :param metric: the populated ElasticMetric object
        :param index: the index where the ElasticMetric Object
            is pushed
        :return: the time needed to save if succeeded -1 if failed
        """
        try:
            time_start = time.time()
            metric.save(using=self.es, index=index)
            return int(time.time() - time_start)
        except Exception:
            return -1

    def search_alert(self, run_id: str, index: str) -> list[ElasticAlert]:
        """
        Searches ElasticAlerts by run_id
        :param run_id: the Krkn run id to search
        :param index: the index where the ElasticAlert
            should have been saved
        :return: the list of objects retrieved (Empty if nothing
            has been found)
        """
        try:
            search = Search(using=self.es, index=index).filter(
                "match", run_id=run_id
            )
            result = search.execute()
            documents = [ElasticAlert(**hit.to_dict()) for hit in result]
        except NotFoundError:
            return []
        return documents

    def search_metric(self, run_id: str, index: str) -> list[ElasticMetric]:
        """
        Searches ElasticMetric by run_id
        :param run_id: the Krkn run id to search
        :param index: the index where the ElasticAlert
            should have been saved
        :return: the list of objects retrieved (Empty if nothing
            has been found)
        """
        try:
            search = Search(using=self.es, index=index).filter(
                "match", run_id=run_id
            )
            result = search.execute()
            documents = [ElasticMetric(**hit.to_dict()) for hit in result]
        except NotFoundError:
            return []
        return documents
