import datetime
import logging
from unittest.mock import Mock, patch

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn_lib.tests import BaseTest


class TestKrknPrometheus(BaseTest):
    """
    Integration tests for KrknPrometheus class.
    Uses mocking to avoid dependency on actual Prometheus server.
    """
    url = "http://localhost:9090"

    def setUp(self):
        logging.disable(logging.NOTSET)
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(levelname)s: %(message)s',
            force=True
        )

    def test_constructor_success(self):
        """Test successful initialization of KrknPrometheus."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_instance = Mock()
            mock_prom.return_value = mock_instance
            
            prom_cli = KrknPrometheus(self.url)
            
            mock_prom.assert_called_once()
            self.assertEqual(prom_cli.prom_cli, mock_instance)

    def test_constructor_with_bearer_token(self):
        """Test initialization with bearer token."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            bearer_token = "test_token_12345"
            mock_instance = Mock()
            mock_prom.return_value = mock_instance
            
            KrknPrometheus(self.url, bearer_token)
            
            # Verify the headers were set correctly
            call_args = mock_prom.call_args
            self.assertIn('headers', call_args.kwargs)
            self.assertEqual(
                call_args.kwargs['headers']['Authorization'],
                f"Bearer {bearer_token}"
            )

    def test_constructor_exception_handling(self):
        """Test that constructor exits on initialization failure."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.side_effect = Exception("Connection failed")
            
            with self.assertRaises(SystemExit) as cm:
                KrknPrometheus(self.url)
            
            self.assertEqual(cm.exception.code, 1)

    def test_process_prom_query_in_range_success(self):
        """Test successful range query execution."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            # Mock response data
            expected_result = [
                {
                    "metric": {"instance": "node1", "pod": "test_pod"},
                    "values": [[1699357840, "0.1"], [1699357850, "0.2"]]
                }
            ]
            mock_client.custom_query_range.return_value = expected_result
            
            prom_cli = KrknPrometheus(self.url)
            query = "node_boot_time_seconds"
            start_time = datetime.datetime.now() - datetime.timedelta(hours=1)
            end_time = datetime.datetime.now()
            
            res = prom_cli.process_prom_query_in_range(query, start_time, end_time)
            
            self.assertEqual(res, expected_result)
            self.assertTrue(len(res) > 0)
            self.assertIn("metric", res[0].keys())
            self.assertIn("values", res[0].keys())
            for value in res[0]["values"]:
                self.assertEqual(len(value), 2)

    def test_process_prom_query_in_range_default_times(self):
        """Test range query with default start/end times."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            mock_client.custom_query_range.return_value = []
            
            prom_cli = KrknPrometheus(self.url)
            query = "test_query"
            
            # Call without providing start_time and end_time
            prom_cli.process_prom_query_in_range(query)
            
            # Verify the method was called
            mock_client.custom_query_range.assert_called_once()

    def test_process_prom_query_in_range_custom_granularity(self):
        """Test range query with custom granularity."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            mock_client.custom_query_range.return_value = []
            
            prom_cli = KrknPrometheus(self.url)
            query = "test_query"
            start_time = datetime.datetime.now() - datetime.timedelta(hours=1)
            end_time = datetime.datetime.now()
            granularity = 30
            
            prom_cli.process_prom_query_in_range(query, start_time, end_time, granularity)
            
            call_args = mock_client.custom_query_range.call_args
            self.assertEqual(call_args.kwargs['step'], "30s")

    def test_process_prom_query_in_range_exception(self):
        """Test exception handling in range query."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            mock_client.custom_query_range.side_effect = Exception("Query failed")
            
            prom_cli = KrknPrometheus(self.url)
            query = "node_boot_time_seconds"
            
            with self.assertRaises(Exception) as cm:
                prom_cli.process_prom_query_in_range(query)
            
            self.assertIn("Query failed", str(cm.exception))

    def test_process_query_success(self):
        """Test successful instant query execution."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            expected_result = [
                {
                    "metric": {"instance": "node1"},
                    "value": [1699357840, "0.5"]
                }
            ]
            mock_client.custom_query.return_value = expected_result
            
            prom_cli = KrknPrometheus(self.url)
            query = "up"
            
            res = prom_cli.process_query(query)
            
            self.assertEqual(res, expected_result)
            self.assertTrue(len(res) > 0)
            self.assertIn("metric", res[0].keys())
            mock_client.custom_query.assert_called_once_with(query=query)

    def test_process_query_exception(self):
        """Test exception handling in instant query."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            mock_client.custom_query.side_effect = Exception("Connection error")
            
            prom_cli = KrknPrometheus(self.url)
            query = "test_query"
            
            with self.assertRaises(Exception) as cm:
                prom_cli.process_query(query)
            
            self.assertIn("Connection error", str(cm.exception))

    def test_process_alert_info_severity(self):
        """Test process_alert with info severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            mock_result = [
                {
                    "metric": {"container": "test-container", "endpoint": "test-endpoint"},
                    "values": [[1699357840, "0.1"]]
                }
            ]
            mock_client.custom_query_range.return_value = mock_result
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "test_query",
                "description": "container: {{$labels.container}}, endpoint: {{$labels.endpoint}}, value: {{$value}}",
                "severity": "info"
            }
            start_time = datetime.datetime.now() - datetime.timedelta(days=1)
            end_time = datetime.datetime.now()
            
            timestamp, log_output = prom_cli.process_alert(alert, start_time, end_time)
            
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("test-container", log_output)
            self.assertIn("test-endpoint", log_output)
            self.assertIn("0.1", log_output)

    def test_process_alert_debug_severity(self):
        """Test process_alert with debug severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            mock_result = [
                {
                    "metric": {"pod": "test-pod"},
                    "values": [[1699357840, "1.5"]]
                }
            ]
            mock_client.custom_query_range.return_value = mock_result
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "test_query",
                "description": "pod: {{$labels.pod}}, value: {{$value}}",
                "severity": "debug"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("test-pod", log_output)
            self.assertIn("1.5", log_output)

    def test_process_alert_warning_severity(self):
        """Test process_alert with warning severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            mock_result = [
                {
                    "metric": {"instance": "node1"},
                    "values": [[1699357840, "90"]]
                }
            ]
            mock_client.custom_query_range.return_value = mock_result
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "cpu_usage",
                "description": "High CPU on {{$labels.instance}}: {{$value}}%",
                "severity": "warning"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("node1", log_output)
            self.assertIn("90", log_output)

    def test_process_alert_error_severity(self):
        """Test process_alert with error severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            mock_result = [
                {
                    "metric": {"service": "api"},
                    "values": [[1699357840, "500"]]
                }
            ]
            mock_client.custom_query_range.return_value = mock_result
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "http_errors",
                "description": "Error on {{$labels.service}}: code {{$value}}",
                "severity": "error"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("api", log_output)
            self.assertIn("500", log_output)

    def test_process_alert_critical_severity(self):
        """Test process_alert with critical severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            mock_result = [
                {
                    "metric": {"cluster": "prod"},
                    "values": [[1699357840, "0"]]
                }
            ]
            mock_client.custom_query_range.return_value = mock_result
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "cluster_down",
                "description": "Cluster {{$labels.cluster}} is down!",
                "severity": "critical"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("prod", log_output)
            self.assertIn("down", log_output)

    def test_process_alert_invalid_severity(self):
        """Test process_alert with invalid severity level."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "test_query",
                "description": "Test description",
                "severity": "not_exists"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            # Should return timestamp and log_output with error message
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("invalid severity level", log_output)

    def test_process_alert_missing_expr(self):
        """Test process_alert with missing expr field."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "description": "Test description",
                "severity": "info"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            # Should return timestamp and log_output with error message
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("expr", log_output)
            self.assertIn("missing", log_output)

    def test_process_alert_missing_description(self):
        """Test process_alert with missing description field."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "test_query",
                "severity": "info"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            # Should return timestamp and log_output with error message
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("description", log_output)
            self.assertIn("missing", log_output)

    def test_process_alert_missing_severity(self):
        """Test process_alert with missing severity field."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "test_query",
                "description": "Test description"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            # Should return timestamp and log_output with error message
            self.assertIsNotNone(timestamp)
            self.assertIsNotNone(log_output)
            self.assertIn("severity", log_output)
            self.assertIn("missing", log_output)

    def test_process_alert_no_records(self):
        """Test process_alert when query returns no records."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_client = Mock()
            mock_prom.return_value = mock_client
            
            # Return empty list
            mock_client.custom_query_range.return_value = []
            
            prom_cli = KrknPrometheus(self.url)
            
            alert = {
                "expr": "non_existent_metric",
                "description": "Test",
                "severity": "info"
            }
            
            timestamp, log_output = prom_cli.process_alert(
                alert,
                datetime.datetime.now() - datetime.timedelta(hours=1),
                datetime.datetime.now()
            )
            
            self.assertIsNone(timestamp)
            self.assertIsNone(log_output)

    def test_parse_metric_standard_replacement(self):
        """Test parse_metric with standard label and value replacement."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric = {
                "metric": {
                    "pod": "test_pod",
                    "instance": "test_instance",
                },
                "values": [[1699357840, "0.1"]],
            }

            description = (
                "10 minutes avg. 99th etcd commit {{$labels.instance}} latency"
                " on {{$labels.pod}} higher than 30ms. {{$value}}"
            )
            
            expected = (
                "10 minutes avg. 99th etcd "
                "commit test_instance "
                "latency on test_pod higher "
                "than 30ms. 0.1"
            )

            result = prom_cli.parse_metric(description, metric)
            self.assertEqual(expected, result)

    def test_parse_metric_no_value(self):
        """Test parse_metric with empty values array."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric_no_value = {
                "metric": {
                    "pod": "test_pod",
                    "instance": "test_instance",
                },
                "values": [],
            }

            description = (
                "10 minutes avg. 99th etcd commit {{$labels.instance}} latency"
                " on {{$labels.pod}} higher than 30ms. {{$value}}"
            )
            
            expected = (
                "10 minutes avg. 99th etcd "
                "commit test_instance "
                "latency on test_pod higher than "
                "30ms. {{$value}}"
            )

            result = prom_cli.parse_metric(description, metric_no_value)
            self.assertEqual(expected, result)

    def test_parse_metric_underscore_label(self):
        """Test parse_metric with labels containing underscores."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric = {
                "metric": {
                    "pod": "test_pod",
                    "instance": "test_instance",
                    "no_value": "underscore_test",
                },
                "values": [[1699357840, "0.1"]],
            }

            description_underscore = (
                "10 minutes avg. 99th etcd commit {{$labels.instance}} "
                "latency on {{$labels.pod}} higher than 30ms. {{$labels.no_value}}"
            )
            
            expected = (
                "10 minutes avg. 99th etcd "
                "commit test_instance "
                "latency on test_pod higher "
                "than 30ms. underscore_test"
            )

            result = prom_cli.parse_metric(description_underscore, metric)
            self.assertEqual(expected, result)

    def test_parse_metric_multiple_values(self):
        """Test parse_metric with multiple values in the series."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric = {
                "metric": {"pod": "test_pod"},
                "values": [[1699357840, "0.1"], [1699357850, "0.2"], [1699357860, "0.3"]],
            }

            description = "Pod {{$labels.pod}} has value: {{$value}}"
            
            # Should use the first value
            expected = "Pod test_pod has value: 0.1"

            result = prom_cli.parse_metric(description, metric)
            self.assertEqual(expected, result)

    def test_parse_metric_missing_label(self):
        """Test parse_metric when a label doesn't exist in the metric."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric = {
                "metric": {"pod": "test_pod"},
                "values": [[1699357840, "0.1"]],
            }

            description = "Pod {{$labels.pod}} on node {{$labels.node}}"
            
            # Missing label should not be replaced
            expected = "Pod test_pod on node {{$labels.node}}"

            result = prom_cli.parse_metric(description, metric)
            self.assertEqual(expected, result)

    def test_parse_metric_no_placeholders(self):
        """Test parse_metric with description containing no placeholders."""
        with patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect') as mock_prom:
            mock_prom.return_value = Mock()
            prom_cli = KrknPrometheus(self.url)
            
            metric = {
                "metric": {"pod": "test_pod"},
                "values": [[1699357840, "0.1"]],
            }

            description = "This is a plain description with no placeholders"
            
            result = prom_cli.parse_metric(description, metric)
            self.assertEqual(description, result)
