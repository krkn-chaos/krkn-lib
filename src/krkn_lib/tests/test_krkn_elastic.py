import os
import uuid
from unittest.mock import MagicMock, patch

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic.models import (
    ElasticAlert,
    ElasticMetric,
)
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.utils.safe_logger import SafeLogger
from krkn_lib.tests.base_test import BaseTest

class TestKrknElastic(BaseTest):
    def setUp(self):
        self.safe_logger = MagicMock(spec=SafeLogger)
        self.elastic_url = os.getenv("ELASTIC_URL", "http://localhost")
        self.elastic_port = int(os.getenv("ELASTIC_PORT", 9200))

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_init(self, mock_es):
        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        mock_es.assert_called_with(
            f"{self.elastic_url}:{self.elastic_port}",
            http_auth=None,
            verify_certs=False,
            ssl_show_warn=False,
        )
        self.assertIsNotNone(krkn_elastic.es)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_init_with_auth(self, mock_es):
        username = "user"
        password = "password"
        krkn_elastic = KrknElastic(
            self.safe_logger,
            self.elastic_url,
            self.elastic_port,
            username=username,
            password=password,
        )
        mock_es.assert_called_with(
            f"{self.elastic_url}:{self.elastic_port}",
            http_auth=(username, password),
            verify_certs=False,
            ssl_show_warn=False,
        )

    def test_init_invalid_params(self):
        with self.assertRaises(Exception):
            KrknElastic(self.safe_logger, "")

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_to_elasticsearch(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        mock_es_instance.index.return_value = {"result": "created"}

        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        item = {"key": "value"}
        index = "test-index"

        result = krkn_elastic.upload_data_to_elasticsearch(item, index)
        mock_es_instance.index.assert_called_with(index=index, body=item)
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_data_to_elasticsearch_fail(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        mock_es_instance.index.return_value = {"result": "error"}

        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        item = {"key": "value"}
        index = "test-index"

        result = krkn_elastic.upload_data_to_elasticsearch(item, index)
        self.assertEqual(result, -1)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_upload_metrics_to_elasticsearch(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        # Mock the save method on ElasticMetric instance
        with patch("krkn_lib.models.elastic.models.ElasticMetric.save") as mock_save:
            krkn_elastic = KrknElastic(
                self.safe_logger, self.elastic_url, self.elastic_port
            )
            run_uuid = "test-uuid"
            raw_data = [{"name": "metric1", "value": 10}]
            index = "test-index"

            result = krkn_elastic.upload_metrics_to_elasticsearch(
                run_uuid, raw_data, index
            )
            
            self.assertEqual(mock_save.call_count, 1)
            self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_alert(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        alert = MagicMock(spec=ElasticAlert)
        index = "test-index"

        result = krkn_elastic.push_alert(alert, index)
        alert.save.assert_called_with(using=mock_es_instance, index=index)
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_metric(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        metric = MagicMock(spec=ElasticMetric)
        index = "test-index"

        result = krkn_elastic.push_metric(metric, index)
        metric.save.assert_called_with(using=mock_es_instance, index=index)
        self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_push_telemetry(self, mock_es):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        telemetry = MagicMock(spec=ChaosRunTelemetry)
        # Mock attributes needed for ElasticChaosRunTelemetry constructor
        telemetry.scenarios = []
        telemetry.node_summary_infos = []
        telemetry.node_taints = []
        telemetry.kubernetes_objects_count = {}
        telemetry.network_plugins = []
        telemetry.health_checks = []
        telemetry.virt_checks = []
        telemetry.post_virt_checks = []
        
        index = "test-index"

        with patch("krkn_lib.elastic.krkn_elastic.ElasticChaosRunTelemetry") as mock_elastic_telemetry_cls:
            mock_elastic_telemetry = MagicMock()
            mock_elastic_telemetry_cls.return_value = mock_elastic_telemetry
            
            result = krkn_elastic.push_telemetry(telemetry, index)
            
            mock_elastic_telemetry.save.assert_called_with(using=mock_es_instance, index=index)
            self.assertGreaterEqual(result, 0)

    @patch("krkn_lib.elastic.krkn_elastic.Search")
    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_search_telemetry(self, mock_es, mock_search):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        mock_search_instance = MagicMock()
        mock_search.return_value = mock_search_instance
        mock_search_instance.filter.return_value = mock_search_instance
        
        mock_hit = MagicMock()
        mock_hit.to_dict.return_value = {}
        mock_search_instance.execute.return_value = [mock_hit]

        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        run_uuid = "test-uuid"
        index = "test-index"

        with patch("krkn_lib.elastic.krkn_elastic.ElasticChaosRunTelemetry") as mock_cls:
            results = krkn_elastic.search_telemetry(run_uuid, index)
            
            mock_search.assert_called_with(using=mock_es_instance, index=index)
            mock_search_instance.filter.assert_called_with("match", run_uuid=run_uuid)
            self.assertEqual(len(results), 1)

    @patch("krkn_lib.elastic.krkn_elastic.Search")
    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_search_alert(self, mock_es, mock_search):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        mock_search_instance = MagicMock()
        mock_search.return_value = mock_search_instance
        mock_search_instance.filter.return_value = mock_search_instance
        
        mock_hit = MagicMock()
        mock_hit.to_dict.return_value = {}
        mock_search_instance.execute.return_value = [mock_hit]

        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        run_uuid = "test-uuid"
        index = "test-index"

        with patch("krkn_lib.elastic.krkn_elastic.ElasticAlert") as mock_cls:
            results = krkn_elastic.search_alert(run_uuid, index)
            
            mock_search.assert_called_with(using=mock_es_instance, index=index)
            self.assertEqual(len(results), 1)

    @patch("krkn_lib.elastic.krkn_elastic.Search")
    @patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_search_metric(self, mock_es, mock_search):
        mock_es_instance = MagicMock()
        mock_es.return_value = mock_es_instance
        
        mock_search_instance = MagicMock()
        mock_search.return_value = mock_search_instance
        mock_search_instance.filter.return_value = mock_search_instance
        
        mock_hit = MagicMock()
        mock_hit.to_dict.return_value = {}
        mock_search_instance.execute.return_value = [mock_hit]

        krkn_elastic = KrknElastic(
            self.safe_logger, self.elastic_url, self.elastic_port
        )
        run_uuid = "test-uuid"
        index = "test-index"

        with patch("krkn_lib.elastic.krkn_elastic.ElasticMetric") as mock_cls:
            results = krkn_elastic.search_metric(run_uuid, index)
            
            mock_search.assert_called_with(using=mock_es_instance, index=index)
            self.assertEqual(len(results), 1)


class TestKrknElasticIntegration(BaseTest):
    def setUp(self):
        if not self.lib_elastic.es.ping():
            self.skipTest("Elasticsearch is not reachable")

    def test_integration_upload_data(self):
        item = {"key": "integration-test-value"}
        index = "krkn-integration-test"

        result = self.lib_elastic.upload_data_to_elasticsearch(item, index)
        self.assertGreaterEqual(result, 0)

    def test_integration_metrics_lifecycle(self):
        """
        Tests uploading metrics and then searching for them to verify persistence.
        """
        run_uuid = str(uuid.uuid4())
        index = "krkn-integration-metrics"
        raw_data = [{"name": "test_metric", "value": 99.9}]

        # 1. Upload Metric
        result = self.lib_elastic.upload_metrics_to_elasticsearch(
            run_uuid, raw_data, index
        )
        self.assertGreaterEqual(result, 0)

        # 2. Refresh index to make document immediately searchable
        self.lib_elastic.es.indices.refresh(index=index)

        # 3. Search and Verify
        metrics = self.lib_elastic.search_metric(run_uuid, index)
        self.assertTrue(len(metrics) > 0, "Should find at least one metric")
        self.assertEqual(metrics[0].run_uuid, run_uuid)

    def test_integration_alert_lifecycle(self):
        """
        Tests pushing an alert and searching for it.
        """
        run_uuid = str(uuid.uuid4())
        index = "krkn-integration-alerts"
        alert = ElasticAlert(
            run_uuid=run_uuid, severity="critical", alert="Integration Test Alert"
        )

        # 1. Push Alert
        result = self.lib_elastic.push_alert(alert, index)
        self.assertGreaterEqual(result, 0)

        # 2. Refresh index
        self.lib_elastic.es.indices.refresh(index=index)

        # 3. Search and Verify
        alerts = self.lib_elastic.search_alert(run_uuid, index)
        self.assertTrue(len(alerts) > 0, "Should find at least one alert")
        self.assertEqual(alerts[0].run_uuid, run_uuid)
        self.assertEqual(alerts[0].alert, "Integration Test Alert")
