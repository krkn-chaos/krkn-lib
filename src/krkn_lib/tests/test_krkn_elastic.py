import datetime
import time

import uuid

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import ElasticAlert
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class TestKrknElastic(BaseTest):

    def test_push_alert(self):
        run_id = str(uuid.uuid4())
        index = "test-push-alert"
        alert_1 = ElasticAlert(
            alert="example alert 1",
            severity="WARNING",
            created_at=datetime.datetime.now(),
            run_id=run_id,
        )
        alert_2 = ElasticAlert(
            alert="example alert 1",
            severity="WARNING",
            created_at=datetime.datetime.now(),
            run_id=run_id,
        )
        self.lib_elastic.push_alert(alert_1, index)
        self.lib_elastic.push_alert(alert_2, index)
        time.sleep(1)
        alerts = self.lib_elastic.search_alert(run_id, index)
        self.assertEqual(len(alerts), 2)

    def test_search_not_existing(self):
        self.assertEqual(
            len(self.lib_elastic.search_alert("notexisting", "notexisting")), 0
        )

    def test_upload_correct(self):
        timestamp = datetime.datetime.now()
        run_id = str(uuid.uuid4())
        index = "chaos_test"
        time = self.lib_elastic.upload_data_to_elasticsearch(
            {"timestamp": timestamp, "run_id": run_id}, index
        )
        self.assertGreater(time, 0)

    def test_upload_no_index(self):
        time = self.lib_elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, ""
        )

        self.assertEqual(time, 0)

    def test_upload_bad_es_url(self):
        elastic = KrknElastic(
            SafeLogger(),
            "http://localhost",
        )
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, "chaos_test"
        )

        self.assertEqual(time, -1)

    def _testupload_blank_es_url(self):
        es_url = ""
        elastic = KrknElastic(
            SafeLogger(),
            es_url,
        )
        time = elastic.upload_data_to_elasticsearch(
            {"timestamp": datetime.datetime.now()}, "chaos_test"
        )

        self.assertEqual(time, 0)
