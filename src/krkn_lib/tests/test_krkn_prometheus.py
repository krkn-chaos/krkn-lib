import datetime
import logging
import os
from unittest.mock import patch, MagicMock

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
from krkn_lib.tests import BaseTest


class TestKrknPrometheus(BaseTest):
    url = "http://localhost:9090"

    def test_process_prom_query(self):
        prom_cli = KrknPrometheus(self.url)
        query = "node_boot_time_seconds"
        start_time = datetime.datetime.now() - datetime.timedelta(hours=1)

        end_time = datetime.datetime.now()
        res = prom_cli.process_prom_query_in_range(query, start_time, end_time)

        self.assertTrue(len(res) > 0)
        self.assertTrue("metric" in res[0].keys())
        self.assertTrue("values" in res[0].keys())
        for value in res[0]["values"]:
            self.assertEqual(len(value), 2)

    def process_query(self):
        prom_cli = KrknPrometheus(self.url)
        query = "node_boot_time_seconds"

        res = prom_cli.process_query(query)

        self.assertTrue(len(res) > 0)
        self.assertTrue("metric" in res[0].keys())
        self.assertTrue("values" in res[0].keys())
        for value in res[0]["values"]:
            self.assertEqual(len(value), 2)

    def test_flaky_tests(self):
        logging.warn("test_process_alert")
        logging.warn("FLAKY TESTS NEED TO BE REFACTORED AND REENABLED")

    ######## FLAKY TEST NEEDS TO BE REFACTORED # NOQA
    # def test_process_alert(self):
    #     prom_cli = KrknPrometheus(self.url)
    #     res = prom_cli.process_prom_query_in_range(
    #         "node_boot_time_seconds", end_time=datetime.datetime.now()
    #     )
    #     logging.disable(logging.NOTSET)
    #     controls = []
    #     for result in res:
    #         for value in result["values"]:
    #             controls.append(
    #                 f"container: {res[0]['metric']['container']}, "
    #                 f"endpoint: {res[0]['metric']['endpoint']}, "
    #                 f"value: {value[1]}"
    #             )
    #
    #     alert_info = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, value: {{$value}}",
    #         "severity": "info",
    #     }
    #
    #     alert_debug = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, "
    #         "value: {{$value}}",
    #         "severity": "debug",
    #     }
    #
    #     alert_warning = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, "
    #         "value: {{$value}}",
    #         "severity": "warning",
    #     }
    #
    #     alert_error = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, "
    #         "value: {{$value}}",
    #         "severity": "error",
    #     }
    #
    #     alert_critical = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, "
    #         "value: {{$value}}",
    #         "severity": "critical",
    #     }
    #
    #     alert_not_exists = {
    #         "expr": "node_boot_time_seconds",
    #         "description": "container: {{$labels.container}}, "
    #         "endpoint: {{$labels.endpoint}}, "
    #         "value: {{$value}}",
    #         "severity": "not_exists",
    #     }
    #     # tests that the logger contains at least a record
    #     # on the selected log level and that the returned string from
    #     # the log is contained on the log printed
    #
    #     with self.assertLogs(level="INFO") as lc:
    #         string_value = prom_cli.process_alert(
    #             alert_info,
    #             datetime.datetime.now() - datetime.timedelta(days=1),
    #             datetime.datetime.now(),
    #         )
    #         self.assertTrue(len(lc.records) > 0)
    #         logger_output = str(lc.output[0])
    #         self.assertTrue(string_value[1] in logger_output)
    #         with self.assertLogs(level="DEBUG") as lc:
    #             string_value = prom_cli.process_alert(
    #                 alert_debug,
    #                 datetime.datetime.now() - datetime.timedelta(days=1),
    #                 datetime.datetime.now(),
    #             )
    #             self.assertTrue(len(lc.records) > 0)
    #             logger_output = str(lc.output[0])
    #             self.assertTrue(string_value[1] in logger_output)
    #
    #             with self.assertLogs(level="WARNING") as lc:
    #                 string_value = prom_cli.process_alert(
    #                     alert_warning,
    #                     datetime.datetime.now() - datetime.timedelta(days=1),
    #                     datetime.datetime.now(),
    #                 )
    #                 self.assertTrue(len(lc.records) > 0)
    #                 logger_output = str(lc.output[0])
    #                 self.assertTrue(string_value[1] in logger_output)
    #
    #             with self.assertLogs(level="ERROR") as lc:
    #                 string_value = prom_cli.process_alert(
    #                     alert_error,
    #                     datetime.datetime.now() - datetime.timedelta(days=1),
    #                     datetime.datetime.now(),
    #                 )
    #                 self.assertTrue(len(lc.records) > 0)
    #                 logger_output = str(lc.output[0])
    #
    #                 self.assertTrue(string_value[1] in logger_output)
    #
    #             with self.assertLogs(level="CRITICAL") as lc:
    #                 string_value = prom_cli.process_alert(
    #                     alert_critical,
    #                     datetime.datetime.now() - datetime.timedelta(days=1),
    #                     datetime.datetime.now(),
    #                 )
    #                 self.assertTrue(len(lc.records) > 0)
    #                 logger_output = str(lc.output[0])
    #                 self.assertTrue(string_value[1] in logger_output)
    #
    #             with self.assertLogs(level="ERROR") as lc:
    #                 string_value = prom_cli.process_alert(
    #                     alert_not_exists,
    #                     datetime.datetime.now() - datetime.timedelta(days=1),
    #                     datetime.datetime.now(),
    #                 )
    #                 self.assertTrue(len(lc.records) == 1)
    #                 self.assertEqual(lc.records[0].levelname, "ERROR")
    #                 self.assertEqual(
    #                     lc.records[0].msg, "invalid severity level: not_exists" # NOQA
    #                 )
    #                 logger_output = str(lc.output[0])
    #                 self.assertTrue(string_value[1] in logger_output)

    def test_parse_metric(self):
        prom_cli = KrknPrometheus(self.url)
        metric = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "values": [[1699357840, "0.1"]],
        }
        metric_no_value = {
            "metric": {
                "pod": "test_pod",
                "instance": "test_instance",
                "no_value": "no_value",
            },
            "values": [],
        }

        control = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['values'][0][1]}"
        )

        control_underscore = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher "
            f"than 30ms. {metric['metric']['no_value']}"
        )

        control_no_value = (
            f"10 minutes avg. 99th etcd "
            f"commit {metric['metric']['instance']} "
            f"latency on {metric['metric']['pod']} higher than "
            f"30ms. {{{{$value}}}}"
        )

        description = (
            "10 minutes avg. 99th etcd commit {{$labels.instance}} latency"
            " on {{$labels.pod}} higher than 30ms. {{$value}}"
        )
        description_underscore = (
            "10 minutes avg. 99th etcd commit {{$labels.instance}} "
            "latency on {{$labels.pod}} higher than 30ms. {{$labels.no_value}}"
        )

        # tests a standard label and vale replacement
        result = prom_cli.parse_metric(description, metric)

        # tests a replacement for a metric with an
        # empty array of values ( {{$value}} won't be replaced)
        result_no_value = prom_cli.parse_metric(description, metric_no_value)
        # tests a replacement for a label containing underscore
        # ( only alnum letters, _ and - are allowed in labels)
        result_underscore = prom_cli.parse_metric(
            description_underscore, metric
        )

        self.assertEqual(control, result)
        self.assertEqual(control_no_value, result_no_value)
        self.assertEqual(control_underscore, result_underscore)

    @patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect')
    def test_socks5_proxy_without_auth(self, mock_prom_connect):
        """Test SOCKS5 proxy configuration without authentication"""
        mock_prom_connect.return_value = MagicMock()

        # Set http_proxy environment variable with socks5 URL
        test_proxy = "socks5://127.0.0.1:1080"
        with patch.dict(os.environ, {'http_proxy': test_proxy}, clear=False):
            prom_cli = KrknPrometheus(self.url)

            # Verify PrometheusConnect was called with correct proxy configuration
            mock_prom_connect.assert_called_once()
            call_args = mock_prom_connect.call_args

            # Check that proxy was passed correctly
            self.assertIn('proxy', call_args[1])
            proxy_config = call_args[1]['proxy']

            # Should use socks5h:// scheme for remote DNS resolution
            expected_proxy = "socks5h://127.0.0.1:1080"
            self.assertEqual(proxy_config['http'], expected_proxy)
            self.assertEqual(proxy_config['https'], expected_proxy)

            # Verify other parameters
            self.assertEqual(call_args[1]['url'], self.url)
            self.assertTrue(call_args[1]['disable_ssl'])

    @patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect')
    def test_socks5_proxy_with_auth(self, mock_prom_connect):
        """Test SOCKS5 proxy configuration with authentication"""
        mock_prom_connect.return_value = MagicMock()

        # Set http_proxy environment variable with credentials
        test_proxy = "socks5://testuser:testpass@127.0.0.1:1080"
        with patch.dict(os.environ, {'http_proxy': test_proxy}, clear=False):
            prom_cli = KrknPrometheus(self.url)

            # Verify PrometheusConnect was called with correct proxy configuration
            mock_prom_connect.assert_called_once()
            call_args = mock_prom_connect.call_args

            # Check that proxy was passed correctly
            self.assertIn('proxy', call_args[1])
            proxy_config = call_args[1]['proxy']

            # Should include credentials in socks5h:// URL
            expected_proxy = "socks5h://testuser:testpass@127.0.0.1:1080"
            self.assertEqual(proxy_config['http'], expected_proxy)
            self.assertEqual(proxy_config['https'], expected_proxy)

    @patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect')
    def test_no_proxy_configuration(self, mock_prom_connect):
        """Test initialization without proxy configuration"""
        mock_prom_connect.return_value = MagicMock()

        # Clear proxy environment variables
        env_vars = {
            'http_proxy': None,
            'HTTP_PROXY': None,
            'https_proxy': None,
            'HTTPS_PROXY': None
        }

        with patch.dict(os.environ, env_vars, clear=False):
            # Remove the keys if they exist
            for key in ['http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY']:
                os.environ.pop(key, None)

            prom_cli = KrknPrometheus(self.url)

            # Verify PrometheusConnect was called
            mock_prom_connect.assert_called_once()
            call_args = mock_prom_connect.call_args

            # Check that proxy configuration is None for both protocols
            self.assertIn('proxy', call_args[1])
            proxy_config = call_args[1]['proxy']
            self.assertIsNone(proxy_config['http'])
            self.assertIsNone(proxy_config['https'])

    @patch('krkn_lib.prometheus.krkn_prometheus.PrometheusConnect')
    def test_socks5_proxy_with_bearer_token(self, mock_prom_connect):
        """Test SOCKS5 proxy configuration with bearer token authentication"""
        mock_prom_connect.return_value = MagicMock()

        # Set http_proxy environment variable
        test_proxy = "socks5://proxyuser:proxypass@127.0.0.1:1080"
        bearer_token = "test-bearer-token-12345"

        with patch.dict(os.environ, {'http_proxy': test_proxy}, clear=False):
            prom_cli = KrknPrometheus(self.url, bearer_token)

            # Verify PrometheusConnect was called
            mock_prom_connect.assert_called_once()
            call_args = mock_prom_connect.call_args

            # Check proxy configuration
            self.assertIn('proxy', call_args[1])
            proxy_config = call_args[1]['proxy']
            expected_proxy = "socks5h://proxyuser:proxypass@127.0.0.1:1080"
            self.assertEqual(proxy_config['http'], expected_proxy)
            self.assertEqual(proxy_config['https'], expected_proxy)

            # Verify bearer token is included in headers
            self.assertIn('headers', call_args[1])
            headers = call_args[1]['headers']
            self.assertIn('Authorization', headers)
            self.assertEqual(headers['Authorization'], f'Bearer {bearer_token}')
