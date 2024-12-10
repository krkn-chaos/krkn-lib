import datetime
import time
import uuid

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import ElasticAlert, ElasticMetric
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class TestKrknElastic(BaseTest):

    def test_push_search_alert(self):
        run_uuid = str(uuid.uuid4())
        index = "test-push-alert"
        alert_1 = ElasticAlert(
            alert="alert_1",
            severity="WARNING",
            created_at=datetime.datetime.now(),
            run_uuid=run_uuid,
        )
        alert_2 = ElasticAlert(
            alert="alert_2",
            severity="ERROR",
            created_at=datetime.datetime.now(),
            run_uuid=run_uuid,
        )
        result = self.lib_elastic.push_alert(alert_1, index)
        self.assertNotEqual(result, -1)
        result = self.lib_elastic.push_alert(alert_2, index)
        self.assertNotEqual(result, -1)
        time.sleep(1)
        alerts = self.lib_elastic.search_alert(run_uuid, index)
        self.assertEqual(len(alerts), 2)

        alert = next(alert for alert in alerts if alert.alert == "alert_1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "WARNING")

        alert = next(alert for alert in alerts if alert.alert == "alert_2")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "ERROR")

    def test_push_search_metric(self):
        run_uuid = str(uuid.uuid4())
        index = "test-push-metric"
        metric_1 = ElasticMetric(
            run_uuid=run_uuid,
            name="metric_1",
            timestamp=100,
            value=1.0,
            created_at=datetime.datetime.now(),
        )
        result = self.lib_elastic.push_metric(metric_1, index)
        self.assertNotEqual(result, -1)
        time.sleep(1)
        metrics = self.lib_elastic.search_metric(run_uuid, index)
        self.assertEqual(len(metrics), 1)
        metric = next(
            metric for metric in metrics if metric.name == "metric_1"
        )
        self.assertIsNotNone(metric)
        self.assertEqual(metric.value, 1.0)
        self.assertEqual(metric.timestamp, 100)
        self.assertEqual(metric.run_uuid, run_uuid)
        self.assertEqual(metric.name, "metric_1")

    def test_push_search_telemetry(self):
        run_uuid = str(uuid.uuid4())
        index = "test-push-telemetry"
        example_data = self.get_ChaosRunTelemetry_json(run_uuid)
        telemetry = ChaosRunTelemetry(json_dict=example_data)
        res = self.lib_elastic.push_telemetry(telemetry, index)
        self.assertNotEqual(res, -1)
        time.sleep(3)
        result = self.lib_elastic.search_telemetry(
            run_uuid=run_uuid, index=index
        )

        self.assertEqual(len(result), 1)

    def test_upload_metric_to_elasticsearch(self):
        bad_metric_uuid = str(uuid.uuid4())
        good_metric_uuid = str(uuid.uuid4())
        name = f"metric-{self.get_random_string(5)}"
        index = "test-upload-metric"
        # testing bad metric
        self.lib_elastic.upload_metrics_to_elasticsearch(
            run_uuid=bad_metric_uuid,
            raw_data={
                "name": 1,
                "timestamp": "bad",
                "value": "bad",
            },
            index=index,
        )

        self.assertEqual(
            len(self.lib_elastic.search_metric(bad_metric_uuid, index)), 0
        )

        self.lib_elastic.upload_metrics_to_elasticsearch(
            run_uuid=good_metric_uuid,
            raw_data=[{"name": name, "timestamp": 10, "value": 3.14}],
            index=index,
        )
        time.sleep(1)
        metric = self.lib_elastic.search_metric(good_metric_uuid, index)
        self.assertEqual(len(metric), 1)
        self.assertEqual(metric[0].name, name)
        self.assertEqual(metric[0].timestamp, 10)
        self.assertEqual(metric[0].value, 3.14)

    def test_search_alert_not_existing(self):
        self.assertEqual(
            len(self.lib_elastic.search_alert("notexisting", "notexisting")), 0
        )

    def test_search_metric_not_existing(self):
        self.assertEqual(
            len(self.lib_elastic.search_metric("notexisting", "notexisting")),
            0,
        )

    def test_search_telemetry_not_existing(self):
        self.assertEqual(
            len(
                self.lib_elastic.search_telemetry("notexisting", "notexisting")
            ),
            0,
        )

    def test_upload_correct(self):
        timestamp = datetime.datetime.now()
        run_uuid = str(uuid.uuid4())
        index = "chaos_test"
        time = self.lib_elastic.upload_data_to_elasticsearch(
            {"timestamp": timestamp, "run_uuid": run_uuid}, index
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
        with self.assertRaises(Exception):
            _ = KrknElastic(
                SafeLogger(),
                es_url,
            )
