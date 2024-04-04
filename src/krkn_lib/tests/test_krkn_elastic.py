import datetime
import os

from krkn_lib.telemetry.elastic import KrknElastic
from krkn_lib.tests import BaseTest
from krkn_lib.utils.safe_logger import SafeLogger


class TestKrknElastic(BaseTest):
    url = os.getenv("ES_SERVER")
    safe_logger: SafeLogger = SafeLogger()

    def test_upload_correct(self):
        elastic = KrknElastic(self.safe_logger, self.url)
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, "chaos_test"
        )

        self.assertGreater(time, 0)

    def test_upload_no_index(self):
        elastic = KrknElastic(self.safe_logger, self.url)
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, ""
        )

        self.assertEqual(time, 0)

    def test_upload_bad_es_url(self):
        elastic = KrknElastic(self.safe_logger, "https://localhost")
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, "chaos_test"
        )

        self.assertEqual(time, -1)

    def test_upload_blank_es_url(self):
        es_url = ""
        elastic = KrknElastic(self.safe_logger, es_url)
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, "chaos_test"
        )

        self.assertEqual(time, 0)
