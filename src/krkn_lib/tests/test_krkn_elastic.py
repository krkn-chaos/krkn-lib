import datetime
import time
import unittest
import uuid
from unittest.mock import Mock, MagicMock, patch

from elasticsearch import NotFoundError

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import ElasticAlert, ElasticMetric
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class TestKrknElasticWithMock(unittest.TestCase):
    """Tests for KrknElastic using mocks (no Elasticsearch required)"""

    def setUp(self):
        """Set up mock Elasticsearch client"""
        self.mock_es = MagicMock()
        self.safe_logger = SafeLogger()

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_init_success(self, mock_elasticsearch):
        """Test successful initialization"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(
            self.safe_logger, "http://localhost", 9200, username="user", password="pass"
        )
        self.assertIsNotNone(elastic.es)
        mock_elasticsearch.assert_called_once()

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_init_no_credentials(self, mock_elasticsearch):
        """Test initialization without credentials"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)
        self.assertIsNotNone(elastic.es)

    def test_init_no_url(self):
        """Test initialization with empty URL raises exception"""
        with self.assertRaises(Exception) as context:
            KrknElastic(self.safe_logger, "", 9200)
        self.assertIn("elastic search url is not valid", str(context.exception))

    def test_init_no_port(self):
        """Test initialization with no port raises exception"""
        with self.assertRaises(Exception) as context:
            KrknElastic(self.safe_logger, "http://localhost", None)
        self.assertIn("elastic port is not valid", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_success(self, mock_elasticsearch):
        """Test successful data upload"""
        mock_elasticsearch.return_value = self.mock_es
        self.mock_es.index.return_value = {"result": "created"}

        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)
        result = elastic.upload_data_to_elasticsearch(
            {"test": "data"}, "test-index"
        )

        self.assertGreaterEqual(result, 0)
        self.mock_es.index.assert_called_once()

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_empty_index(self, mock_elasticsearch):
        """Test upload with empty index returns 0"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        result = elastic.upload_data_to_elasticsearch({"test": "data"}, "")
        self.assertEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_failed(self, mock_elasticsearch):
        """Test failed data upload"""
        mock_elasticsearch.return_value = self.mock_es
        self.mock_es.index.return_value = {"result": "failed"}

        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)
        result = elastic.upload_data_to_elasticsearch(
            {"test": "data"}, "test-index"
        )

        self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_exception(self, mock_elasticsearch):
        """Test data upload with exception"""
        mock_elasticsearch.return_value = self.mock_es
        self.mock_es.index.side_effect = Exception("Connection error")

        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)
        result = elastic.upload_data_to_elasticsearch(
            {"test": "data"}, "test-index"
        )

        self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_metric_success(self, mock_elasticsearch):
        """Test successful metric push"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        metric = ElasticMetric(
            run_uuid="test-uuid",
            name="test-metric",
            timestamp=datetime.datetime.now(),
            value=1.0,
        )

        result = elastic.push_metric(metric, "test-index")
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_metric_no_index(self, mock_elasticsearch):
        """Test push metric with no index raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        metric = ElasticMetric(
            run_uuid="test-uuid",
            name="test-metric",
            timestamp=datetime.datetime.now(),
            value=1.0,
        )

        with self.assertRaises(Exception) as context:
            elastic.push_metric(metric, "")
        self.assertIn("index cannot be None or empty", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_metric_exception(self, mock_elasticsearch):
        """Test push metric with exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        metric = ElasticMetric(
            run_uuid="test-uuid",
            name="test-metric",
            timestamp=datetime.datetime.now(),
            value=1.0,
        )

        # Mock save to raise exception
        metric.save = Mock(side_effect=Exception("Save failed"))

        result = elastic.push_metric(metric, "test-index")
        self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_alert_success(self, mock_elasticsearch):
        """Test successful alert push"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        alert = ElasticAlert(
            run_uuid="test-uuid",
            alert="test-alert",
            severity="WARNING",
            created_at=datetime.datetime.now(),
        )

        result = elastic.push_alert(alert, "test-index")
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_alert_no_index(self, mock_elasticsearch):
        """Test push alert with no index raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        alert = ElasticAlert(
            run_uuid="test-uuid",
            alert="test-alert",
            severity="WARNING",
            created_at=datetime.datetime.now(),
        )

        with self.assertRaises(Exception) as context:
            elastic.push_alert(alert, "")
        self.assertIn("index cannot be None or empty", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_alert_exception(self, mock_elasticsearch):
        """Test push alert with exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        alert = ElasticAlert(
            run_uuid="test-uuid",
            alert="test-alert",
            severity="WARNING",
            created_at=datetime.datetime.now(),
        )

        # Mock save to raise exception
        alert.save = Mock(side_effect=Exception("Save failed"))

        result = elastic.push_alert(alert, "test-index")
        self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_telemetry_success(self, mock_elasticsearch):
        """Test successful telemetry push"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Create minimal telemetry with all required fields
        telemetry_data = {
            "run_uuid": "test-uuid",
            "scenarios": [],
            "timestamp": "2023-05-22T14:55:02Z",
            "job_status": True,
            "node_summary_infos": [],
            "node_taints": [],
            "kubernetes_objects_count": {},
            "network_plugins": [],
        }
        telemetry = ChaosRunTelemetry(json_dict=telemetry_data)

        result = elastic.push_telemetry(telemetry, "test-index")
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_telemetry_no_index(self, mock_elasticsearch):
        """Test push telemetry with no index raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        telemetry_data = {
            "run_uuid": "test-uuid",
            "scenarios": [],
            "timestamp": "2023-05-22T14:55:02Z",
            "job_status": True,
            "node_summary_infos": [],
            "node_taints": [],
            "kubernetes_objects_count": {},
            "network_plugins": [],
        }
        telemetry = ChaosRunTelemetry(json_dict=telemetry_data)

        with self.assertRaises(Exception) as context:
            elastic.push_telemetry(telemetry, "")
        self.assertIn("index cannot be None or empty", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_to_elasticsearch_success(self, mock_elasticsearch):
        """Test successful metrics upload"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        raw_data = [
            {
                "name": "test-metric",
                "timestamp": datetime.datetime.now(),
                "value": 3.14,
            }
        ]

        result = elastic.upload_metrics_to_elasticsearch(
            "test-uuid", raw_data, "test-index"
        )
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_no_index(self, mock_elasticsearch):
        """Test upload metrics with no index raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        with self.assertRaises(Exception) as context:
            elastic.upload_metrics_to_elasticsearch("test-uuid", [], "")
        self.assertIn("index cannot be None or empty", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_no_uuid(self, mock_elasticsearch):
        """Test upload metrics with no UUID raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        with self.assertRaises(Exception) as context:
            elastic.upload_metrics_to_elasticsearch("", [], "test-index")
        self.assertIn("run uuid cannot be None or empty", str(context.exception))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_alert_success(self, mock_search_class, mock_elasticsearch):
        """Test successful alert search"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Mock search results
        mock_hit = Mock()
        mock_hit.to_dict.return_value = {
            "run_uuid": "test-uuid",
            "alert": "test-alert",
            "severity": "WARNING",
            "created_at": datetime.datetime.now(),
        }

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([mock_hit]))

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.return_value = mock_result
        mock_search_class.return_value = mock_search

        results = elastic.search_alert("test-uuid", "test-index")
        self.assertEqual(len(results), 1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_alert_not_found(self, mock_search_class, mock_elasticsearch):
        """Test alert search when index not found"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.side_effect = NotFoundError("Index not found")
        mock_search_class.return_value = mock_search

        results = elastic.search_alert("test-uuid", "test-index")
        self.assertEqual(len(results), 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_metric_success(self, mock_search_class, mock_elasticsearch):
        """Test successful metric search"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Mock search results
        mock_hit = Mock()
        mock_hit.to_dict.return_value = {
            "run_uuid": "test-uuid",
            "name": "test-metric",
            "timestamp": datetime.datetime.now(),
            "value": 1.0,
        }

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([mock_hit]))

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.return_value = mock_result
        mock_search_class.return_value = mock_search

        results = elastic.search_metric("test-uuid", "test-index")
        self.assertEqual(len(results), 1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_metric_not_found(self, mock_search_class, mock_elasticsearch):
        """Test metric search when index not found"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.side_effect = NotFoundError("Index not found")
        mock_search_class.return_value = mock_search

        results = elastic.search_metric("test-uuid", "test-index")
        self.assertEqual(len(results), 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_telemetry_success(self, mock_search_class, mock_elasticsearch):
        """Test successful telemetry search"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Mock search results
        mock_hit = Mock()
        mock_hit.to_dict.return_value = {
            "run_uuid": "test-uuid",
            "scenarios": [],
            "timestamp": "2023-05-22T14:55:02Z",
            "job_status": True,
            "node_summary_infos": [],
            "node_taints": [],
            "kubernetes_objects_count": {},
            "network_plugins": [],
        }

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([mock_hit]))

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.return_value = mock_result
        mock_search_class.return_value = mock_search

        results = elastic.search_telemetry("test-uuid", "test-index")
        self.assertEqual(len(results), 1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    @patch("krkn_lib.elastic.krkn_elastic.Search")
    def test_search_telemetry_not_found(
        self, mock_search_class, mock_elasticsearch
    ):
        """Test telemetry search when index not found"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        mock_search = Mock()
        mock_search.filter.return_value = mock_search
        mock_search.execute.side_effect = NotFoundError("Index not found")
        mock_search_class.return_value = mock_search

        results = elastic.search_telemetry("test-uuid", "test-index")
        self.assertEqual(len(results), 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_exception(self, mock_elasticsearch):
        """Test upload metrics with exception during push"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Mock push_metric to return error
        with patch.object(elastic, 'push_metric', return_value=-1):
            raw_data = [
                {
                    "name": "test-metric",
                    "timestamp": datetime.datetime.now(),
                    "value": 3.14,
                }
            ]
            result = elastic.upload_metrics_to_elasticsearch(
                "test-uuid", raw_data, "test-index"
            )
            # Should still complete but log errors
            self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_invalid_data(self, mock_elasticsearch):
        """Test upload metrics with invalid metric data that raises exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        # Mock ElasticMetric to raise exception
        raw_data = [
            {
                "name": "test-metric",
                "timestamp": datetime.datetime.now(),
                "value": 3.14,
            }
        ]

        with patch('krkn_lib.elastic.krkn_elastic.ElasticMetric', side_effect=Exception("Invalid data")):
            result = elastic.upload_metrics_to_elasticsearch(
                "test-uuid", raw_data, "test-index"
            )
            # Should return -1 on exception
            self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_telemetry_exception(self, mock_elasticsearch):
        """Test push telemetry with exception"""
        mock_elasticsearch.return_value = self.mock_es
        elastic = KrknElastic(self.safe_logger, "http://localhost", 9200)

        telemetry_data = {
            "run_uuid": "test-uuid",
            "scenarios": [],
            "timestamp": "2023-05-22T14:55:02Z",
            "job_status": True,
            "node_summary_infos": [],
            "node_taints": [],
            "kubernetes_objects_count": {},
            "network_plugins": [],
        }
        telemetry = ChaosRunTelemetry(json_dict=telemetry_data)

        # Mock to raise exception during save
        with patch('krkn_lib.models.elastic.models.ElasticChaosRunTelemetry.save', side_effect=Exception("Save failed")):
            result = elastic.push_telemetry(telemetry, "test-index")
            self.assertEqual(result, -1)


class TestKrknElasticIntegration(BaseTest):
    """Integration tests that require actual Elasticsearch (original tests)"""

    def setUp(self):
        """Skip tests if Elasticsearch is not configured"""
        if self.lib_elastic is None:
            self.skipTest("Elasticsearch not configured")

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
        timestamp = datetime.datetime.now()
        metric_1 = ElasticMetric(
            run_uuid=run_uuid,
            metricName="metric_1",
            timestamp=timestamp,
            value=1.0,
        )
        result = self.lib_elastic.push_metric(metric_1, index)
        self.assertNotEqual(result, -1)
        time.sleep(1)
        metrics = self.lib_elastic.search_metric(run_uuid, index)
        self.assertEqual(len(metrics), 1)
        metric = metrics[0]

        self.assertIsNotNone(metric)
        self.assertEqual(
            metric.timestamp, timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
        )
        self.assertEqual(metric.run_uuid, run_uuid)
        self.assertEqual(metric["value"], 1.0)

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

        time_now = datetime.datetime.now()
        self.lib_elastic.upload_metrics_to_elasticsearch(
            run_uuid=good_metric_uuid,
            raw_data=[{"name": name, "timestamp": time_now, "value": 3.14}],
            index=index,
        )
        time.sleep(1)
        metric = self.lib_elastic.search_metric(good_metric_uuid, index)
        self.assertEqual(len(metric), 1)
        self.assertEqual(metric[0].name, name)
        self.assertEqual(
            metric[0].timestamp, time_now.strftime("%Y-%m-%dT%H:%M:%S.%f")
        )
        self.assertEqual(metric[0].value, 3.14)
