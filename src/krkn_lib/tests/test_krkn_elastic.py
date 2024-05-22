import datetime
import time

import uuid

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import (
    ElasticAlert,
    ElasticMetric,
    ElasticMetricValue,
)
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class TestKrknElastic(BaseTest):

    def test_push_search_alert(self):
        run_id = str(uuid.uuid4())
        index = "test-push-alert"
        alert_1 = ElasticAlert(
            alert="alert_1",
            severity="WARNING",
            created_at=datetime.datetime.now(),
            run_id=run_id,
        )
        alert_2 = ElasticAlert(
            alert="alert_2",
            severity="ERROR",
            created_at=datetime.datetime.now(),
            run_id=run_id,
        )
        self.lib_elastic.push_alert(alert_1, index)
        self.lib_elastic.push_alert(alert_2, index)
        time.sleep(1)
        alerts = self.lib_elastic.search_alert(run_id, index)
        self.assertEqual(len(alerts), 2)

        alert = next(alert for alert in alerts if alert.alert == "alert_1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "WARNING")

        alert = next(alert for alert in alerts if alert.alert == "alert_2")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "ERROR")

    def test_push_search_metric(self):
        run_id = str(uuid.uuid4())
        index = "test-push-metric"
        metric_1 = ElasticMetric(
            run_id=run_id,
            name="metric_1",
            values=[
                ElasticMetricValue(100, 1.0),
                ElasticMetricValue(101, 2.0),
                ElasticMetricValue(102, 3.0),
            ],
            created_at=datetime.datetime.now(),
        )
        metric_2 = ElasticMetric(
            run_id=run_id,
            name="metric_2",
            values=[
                ElasticMetricValue(103, 4.0),
                ElasticMetricValue(104, 5.0),
                ElasticMetricValue(105, 6.0),
            ],
            created_at=datetime.datetime.now(),
        )
        self.lib_elastic.push_metric(metric_1, index)
        self.lib_elastic.push_metric(metric_2, index)
        time.sleep(1)
        metrics = self.lib_elastic.search_metric(run_id, index)
        self.assertEqual(len(metrics), 2)
        metric = next(
            metric for metric in metrics if metric.name == "metric_1"
        )
        self.assertIsNotNone(metric)
        self.assertEqual(len(metric.values), 3)
        self.assertEqual(
            set([(v.timestamp, v.value) for v in metric.values]),
            {
                (100, 1.0),
                (101, 2.0),
                (102, 3.0),
            },
        )

        metric = next(
            metric for metric in metrics if metric.name == "metric_2"
        )
        self.assertIsNotNone(metric)

        self.assertEqual(len(metric.values), 3)
        self.assertEqual(
            set([(v.timestamp, v.value) for v in metric.values]),
            {
                (103, 4.0),
                (104, 5.0),
                (105, 6.0),
            },
        )

    def test_upload_metric_to_elasticsearch(self):
        bad_metric_uuid = str(uuid.uuid4())
        good_metric_uuid = str(uuid.uuid4())
        name = f"metric-{self.get_random_string(5)}"
        index = "test-upload-metric"
        # testing bad metric
        self.lib_elastic.upload_metric_to_elasticsearch(
            run_id=bad_metric_uuid,
            raw_data={"name": 1, "values": [("bad", "bad")]},
            index=index,
        )

        self.assertEqual(
            len(self.lib_elastic.search_metric(bad_metric_uuid, index)), 0
        )

        self.lib_elastic.upload_metric_to_elasticsearch(
            run_id=good_metric_uuid,
            raw_data=[{"name": name, "values": [(10, 3.14)]}],
            index=index,
        )
        time.sleep(1)
        metric = self.lib_elastic.search_metric(good_metric_uuid, index)
        self.assertEqual(len(metric), 1)
        self.assertEqual(metric[0].name, name)
        self.assertEqual(metric[0].values[0].timestamp, 10)
        self.assertEqual(metric[0].values[0].value, 3.14)

    def test_search_alert_not_existing(self):
        self.assertEqual(
            len(self.lib_elastic.search_alert("notexisting", "notexisting")), 0
        )

    def test_search_metric_not_existing(self):
        self.assertEqual(
            len(self.lib_elastic.search_metric("notexisting", "notexisting")),
            0,
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
