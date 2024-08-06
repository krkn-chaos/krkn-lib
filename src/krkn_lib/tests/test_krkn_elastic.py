import datetime
import os
import time
import uuid

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.tests import BaseTest
from krkn_lib.models.elastic.models import ElasticMetric, ElasticAlert
from krkn_lib.tests.test_krkn_elastic_models import TestKrknElasticModels
from krkn_lib.utils.safe_logger import SafeLogger


class TestKrknElastic(BaseTest):
    url = os.getenv("ES_SERVER")
    safe_logger: SafeLogger = SafeLogger()

    def upload_correct(self, run_uuid, index):
        elastic = KrknElastic(self.safe_logger, self.url)
        example_data = self.get_ChaosRunTelemetry_json(run_uuid)
        print("example data" + str(example_data))
        time = elastic.upload_data_to_elasticsearch(example_data, index)

        self.assertGreater(time, 0)

    def _testupload_no_index(self):
        elastic = KrknElastic(self.safe_logger, self.url)
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, ""
        )

        self.assertEqual(time, 0)

    def _testupload_bad_es_url(self):
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

    def _testsearch_telemetry(self):
        elastic = KrknElastic(self.safe_logger, self.url)

        index = "chaos_test"

        run_uuid = str(uuid.uuid4())
        self.upload_correct(run_uuid, index)
        time.sleep(5)
        doc = elastic.search_telemetry(run_uuid, index)

        TestKrknElasticModels.check_test_ElasticChaosRunTelemetry(
            self, doc[0], run_uuid
        )


    def _testsearch_metric(self):
        elastic = KrknElastic(self.safe_logger, self.url)

        index = "chaos_test"

        run_uuid = str(uuid.uuid4())
        time.sleep(5)
    
        example_data = self.get_ChaosRunMetric_json(run_uuid)
        # building from object (to save in elastic)
        elastic.upload_metrics_to_elasticsearch(run_uuid, example_data, index)
        time.sleep(5)
        doc = elastic.search_metric(run_uuid, index)

        self.assertEqual(
            doc.value, 13234.23
        )