import time

import math
import urllib3
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch_dsl import Search

from krkn_lib.models.elastic.models import ElasticAlert
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

    def push_alert(self, alert: ElasticAlert, index: str) -> int:
        """
        Pushes an ElasticAlert object to elastic

        :param alert: the populated ElasticAlert object
        :param index: the index where the Elastic AlertObject
            is pushed
        :return: 0 if succeeded -1 if failed
        """
        try:
            alert.save(using=self.es, index=index)
            return 0
        except Exception:
            return -1

    def search_alert(self, run_id: str, index: str) -> list[ElasticAlert]:
        """
        Searches ElasticAlerts by run_id
        :param run_id: the Krkn run id to search
        :param index: the index where the KrknAlerts
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
