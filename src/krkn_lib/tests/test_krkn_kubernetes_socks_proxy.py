# Created-by: Claude Sonnet 4

import os
import unittest
from unittest.mock import MagicMock, patch

from kubernetes import config
from urllib3.contrib.socks import SOCKSProxyManager

from krkn_lib.k8s import KrknKubernetes


class KrknKubernetesTestsSocksProxy(unittest.TestCase):
    """Test cases for SOCKS proxy initialization in KrknKubernetes"""

    def test_init_without_socks_proxy(self):
        """Test initialization without SOCKS proxy
        (normal HTTP/HTTPS proxy or no proxy)"""
        # Ensure no socks proxy is set
        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Clear any existing proxy
            if "http_proxy" in os.environ:
                del os.environ["http_proxy"]

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify that socks_proxy_manager is not set
            self.assertIsNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

            # Verify that api_client can be created
            api_client = lib_k8s.api_client
            self.assertIsNotNone(api_client)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_init_with_socks5_proxy(
        self, mock_load_kube_config, mock_socks_manager
    ):
        """Test initialization with SOCKS5 proxy"""
        # Setup mock
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify that SOCKSProxyManager was called with socks5h URL
            # (the 'h' suffix forces remote DNS resolution)
            mock_socks_manager.assert_called_once()
            call_args = mock_socks_manager.call_args
            self.assertIn("socks5h://localhost:1080", call_args[0][0])

            # Verify that socks_proxy_manager was set
            self.assertIsNotNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

            # Verify that client config proxy is None (SOCKS uses pool manager)
            self.assertIsNone(lib_k8s.client_config.proxy)
            self.assertIsNone(lib_k8s.client_config.proxy_headers)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_init_with_socks5_proxy_with_credentials(
        self, mock_load_kube_config, mock_socks_manager
    ):
        """Test initialization with SOCKS5 proxy with username and password"""
        # Setup mock
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy with credentials
            os.environ["http_proxy"] = "socks5://user:pass@localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify that SOCKSProxyManager was called
            mock_socks_manager.assert_called_once()
            call_args = mock_socks_manager.call_args

            # Verify that credentials are included in the SOCKS URL
            self.assertIn("user", call_args[0][0])
            self.assertIn("pass", call_args[0][0])
            self.assertIn("socks5h://", call_args[0][0])

            # Verify that socks_proxy_manager was set
            self.assertIsNotNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_init_with_socks4_proxy(
        self, mock_load_kube_config, mock_socks_manager
    ):
        """Test initialization with SOCKS4 proxy"""
        # Setup mock
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS4 proxy
            os.environ["http_proxy"] = "socks4://localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify that SOCKSProxyManager was called
            mock_socks_manager.assert_called_once()
            call_args = mock_socks_manager.call_args

            # SOCKS4 should also be detected and used
            self.assertIn("socks", call_args[0][0].lower())

            # Verify that socks_proxy_manager was set
            self.assertIsNotNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_api_client_uses_socks_proxy_manager(
        self, mock_load_kube_config, mock_socks_manager
    ):
        """Test that api_client properly uses SOCKS proxy manager"""
        # Setup mock
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Access api_client to trigger its creation
            api_client = lib_k8s.api_client

            # Verify that api_client was created
            self.assertIsNotNone(api_client)

            # Verify that the pool_manager was replaced
            # with SOCKS proxy manager
            self.assertEqual(
                api_client.rest_client.pool_manager, mock_socks_instance
            )

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_init_with_regular_http_proxy(self, mock_load_kube_config):
        """Test initialization with regular HTTP proxy (not SOCKS)"""
        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set regular HTTP proxy with credentials
            # Note: The current implementation requires
            # credentials in the proxy URL
            os.environ["http_proxy"] = (
                "http://user:pass@proxy.example.com:8080"
            )

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify that SOCKS proxy manager is NOT set
            self.assertIsNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

            # Verify that regular proxy is set in client config
            self.assertEqual(
                lib_k8s.client_config.proxy,
                "http://user:pass@proxy.example.com:8080",
            )

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.ssl.create_default_context")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_socks_proxy_ssl_context_configuration(
        self, mock_load_kube_config, mock_ssl_context, mock_socks_manager
    ):
        """Test that SSL context is properly configured for SOCKS proxy"""
        # Setup mocks
        mock_ssl_instance = MagicMock()
        mock_ssl_context.return_value = mock_ssl_instance
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://localhost:1080"

            # Initialize KrknKubernetes
            KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Verify SSL context was created
            mock_ssl_context.assert_called_once()

            # Verify SOCKSProxyManager was called with SSL context
            mock_socks_manager.assert_called_once()
            call_kwargs = mock_socks_manager.call_args[1]
            self.assertEqual(call_kwargs["ssl_context"], mock_ssl_instance)

            # Verify num_pools and maxsize are set
            self.assertEqual(call_kwargs["num_pools"], 10)
            self.assertEqual(call_kwargs["maxsize"], 10)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_api_client_caching_with_socks_proxy(
        self, mock_load_kube_config, mock_socks_manager
    ):
        """Test that api_client is cached and reused with SOCKS proxy"""
        # Setup mock
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Access api_client multiple times
            api_client_1 = lib_k8s.api_client
            api_client_2 = lib_k8s.api_client

            # Verify they are the same instance (cached)
            self.assertIs(api_client_1, api_client_2)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]

    @patch("krkn_lib.k8s.krkn_kubernetes.client.CustomObjectsApi")
    @patch("krkn_lib.k8s.krkn_kubernetes.SOCKSProxyManager")
    @patch("krkn_lib.k8s.krkn_kubernetes.config.load_kube_config")
    def test_custom_object_client_with_socks_proxy(
        self,
        mock_load_kube_config,
        mock_socks_manager,
        mock_custom_objects_api,
    ):
        """Test that custom_object_client works properly with SOCKS proxy"""
        # Setup mocks
        mock_socks_instance = MagicMock(spec=SOCKSProxyManager)
        mock_socks_manager.return_value = mock_socks_instance

        # Mock the custom object client response for cluster version
        mock_cluster_version_response = {
            "items": [
                {
                    "status": {
                        "conditions": [
                            {
                                "type": "Available",
                                "message": "Cluster version is 4.14.0",
                            }
                        ]
                    }
                }
            ]
        }

        # Setup the mock custom objects API
        mock_custom_obj = MagicMock()
        mock_custom_obj.list_cluster_custom_object.return_value = (
            mock_cluster_version_response
        )
        mock_custom_objects_api.return_value = mock_custom_obj

        original_http_proxy = os.environ.get("http_proxy")
        try:
            # Set SOCKS5 proxy
            os.environ["http_proxy"] = "socks5://localhost:1080"

            # Initialize KrknKubernetes
            lib_k8s = KrknKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

            # Call the method that uses custom_object_client
            result = lib_k8s.custom_object_client.list_cluster_custom_object(
                "config.openshift.io",
                "v1",
                "clusterversions",
            )

            mock_custom_obj = mock_custom_obj.list_cluster_custom_object
            # Verify the call was made
            mock_custom_obj.assert_called_once_with(
                "config.openshift.io",
                "v1",
                "clusterversions",
            )

            # Verify the result
            self.assertIsNotNone(result)
            self.assertIn("items", result)
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(
                result["items"][0]["status"]["conditions"][0]["message"],
                "Cluster version is 4.14.0",
            )

            # Verify that the SOCKS proxy manager was set up
            self.assertIsNotNone(lib_k8s._KrknKubernetes__socks_proxy_manager)

            # Verify the api_client is using the SOCKS proxy manager
            api_client = lib_k8s.api_client
            self.assertEqual(
                api_client.rest_client.pool_manager, mock_socks_instance
            )

            # Verify that CustomObjectsApi was instantiated with the api_client
            mock_custom_objects_api.assert_called_with(api_client)

        finally:
            # Restore original proxy setting
            if original_http_proxy:
                os.environ["http_proxy"] = original_http_proxy
            elif "http_proxy" in os.environ:
                del os.environ["http_proxy"]


if __name__ == "__main__":
    unittest.main()
