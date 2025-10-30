# Integration tests for KrknPrometheus with SOCKS5 proxy
#
# This test file contains both unit tests (using mocks) and integration tests
# (requiring real services).
#
# Unit tests (always run):
# - test_init_without_socks_proxy
# - test_init_with_socks5_proxy
# - test_init_with_socks5_proxy_with_credentials
# - test_init_with_regular_http_proxy
#
# Integration tests (require running services):
# - test_query_prometheus_with_socks5_proxy_real_connection
#   Requires: Prometheus at localhost:9090 and SOCKS5 proxy at localhost:1080
#
# - test_query_prometheus_with_socks5_proxy_with_auth
#   Requires: Prometheus, authenticated SOCKS5 proxy, and env vars:
#   SOCKS_PROXY_USER and SOCKS_PROXY_PASS
#
# To set up a local SOCKS5 proxy for testing:
# 1. Using SSH tunnel: ssh -D 1080 -N username@remote-host
# 2. Using dante-server or other SOCKS proxy software
#
# Run unit tests only:
#   python -m unittest src.krkn_lib.tests.test_krkn_prometheus_socks_proxy \
#     -k "test_init"
#
# Run all tests (including integration):
#   python -m unittest src.krkn_lib.tests.test_krkn_prometheus_socks_proxy

import datetime
import logging
import os
import socket
import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus


class TestKrknPrometheusSocksProxy(unittest.TestCase):
    """Test cases for SOCKS proxy functionality in KrknPrometheus"""

    url = "http://localhost:9090"

    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.original_http_proxy = os.environ.get("http_proxy")
        cls.original_https_proxy = os.environ.get("https_proxy")
        cls.original_HTTP_PROXY = os.environ.get("HTTP_PROXY")
        cls.original_HTTPS_PROXY = os.environ.get("HTTPS_PROXY")

    @classmethod
    def tearDownClass(cls):
        """Restore original environment"""
        # Restore original proxy settings
        if cls.original_http_proxy:
            os.environ["http_proxy"] = cls.original_http_proxy
        elif "http_proxy" in os.environ:
            del os.environ["http_proxy"]

        if cls.original_https_proxy:
            os.environ["https_proxy"] = cls.original_https_proxy
        elif "https_proxy" in os.environ:
            del os.environ["https_proxy"]

        if cls.original_HTTP_PROXY:
            os.environ["HTTP_PROXY"] = cls.original_HTTP_PROXY
        elif "HTTP_PROXY" in os.environ:
            del os.environ["HTTP_PROXY"]

        if cls.original_HTTPS_PROXY:
            os.environ["HTTPS_PROXY"] = cls.original_HTTPS_PROXY
        elif "HTTPS_PROXY" in os.environ:
            del os.environ["HTTPS_PROXY"]

    def setUp(self):
        """Clear proxy environment before each test"""
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
            if key in os.environ:
                del os.environ[key]

    @patch("krkn_lib.prometheus.krkn_prometheus.PrometheusConnect")
    def test_init_without_socks_proxy(self, mock_prom_connect):
        """Test initialization without SOCKS proxy"""
        mock_prom_connect.return_value = MagicMock()

        # Initialize without proxy
        prom_cli = KrknPrometheus(self.url)

        # Verify PrometheusConnect was called
        mock_prom_connect.assert_called_once()
        call_args = mock_prom_connect.call_args

        # Proxy should be None
        self.assertIn("proxy", call_args[1])
        proxy_config = call_args[1]["proxy"]
        self.assertIsNone(proxy_config["http"])
        self.assertIsNone(proxy_config["https"])


    def test_query_prometheus_with_socks5_proxy_real_connection(self):
        """
        Integration test: Query Prometheus through SOCKS5 proxy

        This test requires:
        1. A running Prometheus server at http://localhost:9090
        2. A running SOCKS5 proxy at localhost:1080

        The test will be skipped if either service is unavailable.
        """
        # Check if Prometheus is available
        prom_available = self._check_service_available("localhost", 9090)
        if not prom_available:
            self.skipTest("Prometheus server not available at localhost:9090")

        # Check if SOCKS proxy is available
        socks_available = self._check_service_available("localhost", 1080)
        if not socks_available:
            self.skipTest("SOCKS5 proxy not available at localhost:1080")

        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://127.0.0.1:1080"

            # Initialize Prometheus client with SOCKS proxy
            prom_cli = KrknPrometheus(self.url)

            # Attempt a simple query
            query = "up"
            result = prom_cli.process_query(query)

            # Verify we got a response
            self.assertIsNotNone(result)
            self.assertIsInstance(result, list)

            # If Prometheus has any targets, we should get results
            logging.info(
                f"Successfully queried Prometheus through SOCKS5 proxy. "
                f"Results: {len(result)} metrics"
            )

            # Try a time-range query
            start_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
            end_time = datetime.datetime.now()

            range_result = prom_cli.process_prom_query_in_range(
                query, start_time, end_time, granularity=60
            )

            self.assertIsNotNone(range_result)
            self.assertIsInstance(range_result, list)

            logging.info(
                f"Successfully queried Prometheus time range through "
                f"SOCKS5 proxy. Results: {len(range_result)} metrics"
            )

        except Exception as e:
            self.fail(
                f"Failed to query Prometheus through SOCKS5 proxy: {str(e)}"
            )

    def test_query_prometheus_with_socks5_proxy_with_auth(self):
        """
        Integration test: Query Prometheus through authenticated SOCKS5 proxy

        This test requires:
        1. A running Prometheus server at http://localhost:9090
        2. A running SOCKS5 proxy at localhost:1080 with authentication

        The test will be skipped if either service is unavailable.
        """
        # Check if Prometheus is available
        prom_available = self._check_service_available("localhost", 9090)
        if not prom_available:
            self.skipTest("Prometheus server not available at localhost:9090")

        # Check if SOCKS proxy is available
        socks_available = self._check_service_available("localhost", 1080)
        if not socks_available:
            self.skipTest("SOCKS5 proxy not available at localhost:1080")

        # Check if auth is configured via environment
        socks_user = os.environ.get("SOCKS_PROXY_USER")
        socks_pass = os.environ.get("SOCKS_PROXY_PASS")

        if not socks_user or not socks_pass:
            self.skipTest(
                "SOCKS5 proxy authentication credentials not configured. "
                "Set SOCKS_PROXY_USER and SOCKS_PROXY_PASS environment "
                "variables to run this test."
            )

        try:
            # Set SOCKS5 proxy with authentication
            os.environ["http_proxy"] = (
                f"socks5://{socks_user}:{socks_pass}@127.0.0.1:1080"
            )

            # Initialize Prometheus client with authenticated SOCKS proxy
            prom_cli = KrknPrometheus(self.url)

            # Attempt a simple query
            query = "up"
            result = prom_cli.process_query(query)

            # Verify we got a response
            self.assertIsNotNone(result)
            self.assertIsInstance(result, list)

            logging.info(
                f"Successfully queried Prometheus through authenticated "
                f"SOCKS5 proxy. Results: {len(result)} metrics"
            )

        except Exception as e:
            self.fail(
                f"Failed to query Prometheus through authenticated "
                f"SOCKS5 proxy: {str(e)}"
            )

    @staticmethod
    def _check_service_available(host, port, timeout=2):
        """
        Check if a service is available at the given host and port

        :param host: hostname or IP address
        :param port: port number
        :param timeout: connection timeout in seconds
        :return: True if service is available, False otherwise
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
            return result == 0
        except socket.error:
            return False
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
