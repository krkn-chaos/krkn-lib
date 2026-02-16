import datetime
import os
import time
import uuid
from unittest import mock

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
            raw_data=[
                {"name": name, "timestamp": time_now, "value": 3.14}
            ],
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

    def test_search_alert_not_existing(self):
        self.assertEqual(
            len(
                self.lib_elastic.search_alert("notexisting", "notexisting")
            ),
            0
        )

    def test_search_metric_not_existing(self):
        self.assertEqual(
            len(
                self.lib_elastic.search_metric(
                    "notexisting", "notexisting"
                )
            ),
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


class TestKrknElasticOpenSearch(BaseTest):
    """Test suite for OpenSearch backend support using mocks"""

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_initialization(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test that OpenSearch backend initializes correctly"""
        # Mock auto-detection to return opensearch
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
            username="test_user",
            password="test_pass",
        )

        self.assertIsNotNone(client.es)
        self.assertEqual(client.backend_type, "opensearch")
        mock_opensearch_class.assert_called_once()

    def test_elasticsearch_initialization(self):
        """Test that Elasticsearch backend initializes correctly (default)"""
        self.assertIsNotNone(self.lib_elastic.es)
        self.assertEqual(self.lib_elastic.backend_type, "elasticsearch")

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", False)
    def test_opensearch_not_installed(self, mock_requests_get):
        """Test auto-detecting OpenSearch when not installed raises
        exception"""
        # Mock auto-detection to return opensearch
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            _ = KrknElastic(
                SafeLogger(),
                os.getenv("ELASTIC_URL"),
                int(os.getenv("ELASTIC_PORT")),
            )
        self.assertIn(
            "opensearch-py is not installed", str(context.exception)
        )

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_push_alert(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test push alert with OpenSearch backend"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        run_uuid = str(uuid.uuid4())
        index = "test-opensearch-alert"
        alert = ElasticAlert(
            alert="opensearch_alert_1",
            severity="WARNING",
            created_at=datetime.datetime.now(),
            run_uuid=run_uuid,
        )

        # Mock the index method to succeed
        mock_client.index.return_value = {"result": "created"}

        result = client.push_alert(alert, index)
        self.assertNotEqual(result, -1)

        # Verify index was called with correct parameters
        mock_client.index.assert_called_once()
        call_args = mock_client.index.call_args
        self.assertEqual(call_args[1]["index"], index)
        self.assertIn("body", call_args[1])

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_push_metric(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test push metric with OpenSearch backend"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        run_uuid = str(uuid.uuid4())
        index = "test-opensearch-metric"
        timestamp = datetime.datetime.now()
        metric = ElasticMetric(
            run_uuid=run_uuid,
            metricName="opensearch_metric_1",
            timestamp=timestamp,
            value=2.71,
        )

        # Mock the index method to succeed
        mock_client.index.return_value = {"result": "created"}

        result = client.push_metric(metric, index)
        self.assertNotEqual(result, -1)

        # Verify index was called with correct parameters
        mock_client.index.assert_called_once()
        call_args = mock_client.index.call_args
        self.assertEqual(call_args[1]["index"], index)
        self.assertIn("body", call_args[1])

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_push_telemetry(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test push telemetry with OpenSearch backend"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        run_uuid = str(uuid.uuid4())
        index = "test-opensearch-telemetry"
        example_data = self.get_ChaosRunTelemetry_json(run_uuid)
        telemetry = ChaosRunTelemetry(json_dict=example_data)

        # Mock the ElasticChaosRunTelemetry and index method
        with mock.patch(
            "krkn_lib.elastic.krkn_elastic.ElasticChaosRunTelemetry"
        ) as mock_elastic_chaos:
            mock_elastic_instance = mock.MagicMock()
            mock_elastic_instance.to_dict.return_value = {"test": "data"}
            mock_elastic_chaos.return_value = mock_elastic_instance

            mock_client.index.return_value = {"result": "created"}

            res = client.push_telemetry(telemetry, index)
            self.assertNotEqual(res, -1)

            # Verify to_dict was called and index was called
            mock_elastic_instance.to_dict.assert_called_once()
            mock_client.index.assert_called_once()
            call_args = mock_client.index.call_args
            self.assertEqual(call_args[1]["index"], index)
            self.assertEqual(call_args[1]["body"], {"test": "data"})

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_upload_metrics(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test upload metrics to OpenSearch"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        run_uuid = str(uuid.uuid4())
        name = f"opensearch-metric-{self.get_random_string(5)}"
        index = "test-opensearch-upload-metric"
        time_now = datetime.datetime.now()

        # Mock the push_metric method
        with mock.patch.object(client, "push_metric", return_value=1) as mock_push:
            result = client.upload_metrics_to_elasticsearch(
                run_uuid=run_uuid,
                raw_data=[
                {"name": name, "timestamp": time_now, "value": 3.14}
            ],
                index=index,
            )
            self.assertGreaterEqual(result, 0)
            mock_push.assert_called()

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearchNotFoundError", Exception)
    def test_opensearch_search_not_existing(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test searching for non-existing data in OpenSearch"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        # Mock search to raise NotFoundError
        from elasticsearch import NotFoundError
        mock_client.search.side_effect = NotFoundError("test", "not found", {})

        self.assertEqual(
            len(client.search_alert("notexisting", "notexisting")), 0
        )
        self.assertEqual(
            len(client.search_metric("notexisting", "notexisting")), 0
        )
        self.assertEqual(
            len(client.search_telemetry("notexisting", "notexisting")), 0
        )

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_upload_data(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test upload_data_to_elasticsearch with OpenSearch backend"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_client.index.return_value = {"result": "created"}
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        timestamp = datetime.datetime.now()
        run_uuid = str(uuid.uuid4())
        index = "opensearch_chaos_test"
        time_result = client.upload_data_to_elasticsearch(
            {"timestamp": timestamp, "run_uuid": run_uuid}, index
        )
        self.assertGreater(time_result, 0)
        mock_client.index.assert_called_once()

    def test_is_not_found_error_elasticsearch(self):
        """Test _is_not_found_error helper with Elasticsearch NotFoundError"""
        from elasticsearch import NotFoundError

        error = NotFoundError("test", "not found", {})
        result = self.lib_elastic._is_not_found_error(error)
        self.assertTrue(result)

    def test_is_not_found_error_opensearch(self):
        """Test _is_not_found_error helper with OpenSearch NotFoundError"""
        try:
            from opensearchpy import NotFoundError as OpenSearchNotFoundError

            error = OpenSearchNotFoundError("test", "not found", {})
            result = self.lib_elastic._is_not_found_error(error)
            self.assertTrue(result)
        except ImportError:
            self.skipTest("opensearch-py not installed")

    def test_is_not_found_error_other_exception(self):
        """Test _is_not_found_error helper with other exceptions"""
        error = ValueError("some other error")
        result = self.lib_elastic._is_not_found_error(error)
        self.assertFalse(result)

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_search_with_results(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test searching returns results with OpenSearch"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://test-opensearch.example.com",
            9200,
        )

        run_uuid = str(uuid.uuid4())
        index = "test-index"

        # Mock search to return results
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "run_uuid": run_uuid,
                            "metricName": "test_metric",
                            "timestamp": (
                                "2024-01-01T00:00:00.000000"
                            ),
                            "value": 1.0
                        }
                    }
                ]
            }
        }

        metrics = client.search_metric(run_uuid, index)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].run_uuid, run_uuid)

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_url_parsing(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test that OpenSearch URL is correctly parsed"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        # Test with https URL
        client = KrknElastic(
            SafeLogger(),
            "https://opensearch.example.com",
            9200,
        )

        # Verify client was created successfully
        self.assertIsNotNone(client.es)
        self.assertEqual(client.backend_type, "opensearch")

        # Verify OpenSearch was called with correct parameters
        call_args = mock_opensearch_class.call_args
        self.assertIn("hosts", call_args[1])
        self.assertEqual(
            call_args[1]["hosts"][0]["host"], "opensearch.example.com"
        )
        self.assertEqual(call_args[1]["hosts"][0]["port"], 9200)
        self.assertTrue(call_args[1]["use_ssl"])

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_opensearch_http_url(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test that OpenSearch handles http URLs correctly"""
        # Mock auto-detection
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": {"distribution": "opensearch"}
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        # Test with http URL
        client = KrknElastic(
            SafeLogger(),
            "http://opensearch.example.com",
            9200,
        )

        # Verify client was created successfully
        self.assertIsNotNone(client.es)
        self.assertEqual(client.backend_type, "opensearch")

        # Verify use_ssl is False for http
        call_args = mock_opensearch_class.call_args
        self.assertFalse(call_args[1]["use_ssl"])

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_auto_detect_opensearch(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test auto-detection of OpenSearch backend"""
        # Mock the info endpoint response for OpenSearch
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "opensearch-node",
            "cluster_name": "opensearch-cluster",
            "version": {
                "distribution": "opensearch",
                "number": "2.5.0",
                "build_type": "tar"
            },
            "tagline": (
                "The OpenSearch Project: https://opensearch.org/"
            )
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        # Create client (auto-detection is now default)
        client = KrknElastic(
            SafeLogger(),
            "https://opensearch.example.com",
            9200,
        )

        # Verify it detected OpenSearch
        self.assertEqual(client.backend_type, "opensearch")
        mock_requests_get.assert_called_once()

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_auto_detect_elasticsearch(
        self, mock_elasticsearch_class, mock_requests_get
    ):
        """Test auto-detection of Elasticsearch backend"""
        # Mock the info endpoint response for Elasticsearch
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "elasticsearch-node",
            "cluster_name": "elasticsearch-cluster",
            "version": {
                "number": "7.17.13",
                "build_flavor": "default",
                "build_type": "docker"
            },
            "tagline": "You Know, for Search"
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_elasticsearch_class.return_value = mock_client

        # Create client (auto-detection is now default)
        client = KrknElastic(
            SafeLogger(),
            "https://elasticsearch.example.com",
            9200,
        )

        # Verify it detected Elasticsearch
        self.assertEqual(client.backend_type, "elasticsearch")
        mock_requests_get.assert_called_once()

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_auto_detect_opensearch_by_tagline(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test auto-detection of OpenSearch by tagline"""
        # Mock response with OpenSearch tagline
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "node",
            "cluster_name": "cluster",
            "version": {
                "number": "2.0.0"
            },
            "tagline": "The OpenSearch Project"
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://search.example.com",
            9200,
        )

        self.assertEqual(client.backend_type, "opensearch")

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.Elasticsearch")
    def test_auto_detect_fallback_to_elasticsearch(
        self, mock_elasticsearch_class, mock_requests_get
    ):
        """Test auto-detection falls back to Elasticsearch on error"""
        # Mock a failed request
        mock_requests_get.side_effect = Exception("Connection failed")

        mock_client = mock.MagicMock()
        mock_elasticsearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://search.example.com",
            9200,
        )

        # Should fall back to Elasticsearch
        self.assertEqual(client.backend_type, "elasticsearch")

    @mock.patch("krkn_lib.elastic.krkn_elastic.requests.get")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OpenSearch")
    @mock.patch("krkn_lib.elastic.krkn_elastic.OPENSEARCH_AVAILABLE", True)
    def test_auto_detect_opensearch_by_cluster_name(
        self, mock_opensearch_class, mock_requests_get
    ):
        """Test auto-detection of OpenSearch by cluster name"""
        # Mock response with opensearch in cluster name
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "node",
            "cluster_name": "my-opensearch-cluster",
            "version": {
                "number": "2.0.0"
            },
            "tagline": "You Know, for Search"
        }
        mock_requests_get.return_value = mock_response

        mock_client = mock.MagicMock()
        mock_opensearch_class.return_value = mock_client

        client = KrknElastic(
            SafeLogger(),
            "https://search.example.com",
            9200,
        )

        self.assertEqual(client.backend_type, "opensearch")
