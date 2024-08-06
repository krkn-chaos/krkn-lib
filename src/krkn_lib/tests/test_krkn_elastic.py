import datetime
import os

from krkn_lib.telemetry.elastic import KrknElastic
from krkn_lib.tests import BaseTest
from krkn_lib.utils.safe_logger import SafeLogger


class TestKrknElastic(BaseTest):
    url = os.getenv("ES_SERVER")
    safe_logger: SafeLogger = SafeLogger()

    def testupload_correct(self):
        elastic = KrknElastic(self.safe_logger, self.url)
        time = elastic.upload_data_to_elasticsearch(
            {
                "timestamp": datetime.datetime.now(),
                "run_uuid": "03264e35-126e-4027-b49e-96bd878a53ac",
            },
            "chaos_test",
        )

        print("example data" + str())

        self.assertGreater(time, 0)

    def testupload_no_index(self):
        elastic = KrknElastic(self.safe_logger, self.url)
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, ""
        )

        self.assertEqual(time, 0)

    def testupload_bad_es_url(self):
        elastic = KrknElastic(self.safe_logger, "https://localhost")
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, ""
        )
        self.assertEqual(time, 0)

    def testupload_blank_es_url(self):
        try:
            es_url = ""
            KrknElastic(self.safe_logger, es_url)
        except Exception as e:
            self.assertEqual(str(e), "elastic search url is not valid")
