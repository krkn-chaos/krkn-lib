import time

import urllib3
from elasticsearch import Elasticsearch

from krkn_lib.utils.safe_logger import SafeLogger


class KrknElastic:
    es = None

    def __init__(self, safe_logger: SafeLogger, elastic_url: str):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        urllib3.disable_warnings(DeprecationWarning)
        self.safe_logger = safe_logger
        try:
            # create Elasticsearch object
            if elastic_url:
                self.es = Elasticsearch(f"{elastic_url}:443")
        except Exception as e:
            self.safe_logger.error("Failed to initalize elasticsearch: %s" % e)
            raise e

    def upload_data_to_elasticsearch(self, item: dict, index: str = ""):
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
            return elapsed_time
        return 0
