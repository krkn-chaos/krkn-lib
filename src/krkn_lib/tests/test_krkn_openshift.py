"""
Comprehensive tests for KrknOpenshift class.

This test suite includes both unit tests (mocked) and integration tests
(requiring actual testdata or clusters).

Unit tests use mocks to test all methods without requiring
actual OpenShift clusters or external services.

Integration tests use BaseTest and require actual testdata files
or cluster connections.

Assisted By: Claude Code
"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

from krkn_lib.ocp.krkn_openshift import KrknOpenshift
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


# ==============================================================================
# UNIT TESTS (Mocked - No external dependencies)
# ==============================================================================


class TestKrknOpenshiftInit(unittest.TestCase):
    """Test KrknOpenshift initialization."""

    @patch("krkn_lib.k8s.krkn_kubernetes.config")
    def test_init_with_kubeconfig(self, mock_config):
        """Test initialization with kubeconfig path."""
        mock_config.load_kube_config = Mock()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_kubeconfig = f.name

        try:
            ocp = KrknOpenshift(kubeconfig_path=temp_kubeconfig)

            self.assertIsNotNone(ocp)
            # Should inherit from KrknKubernetes
            self.assertTrue(hasattr(ocp, "api_client"))
        finally:
            if os.path.exists(temp_kubeconfig):
                os.unlink(temp_kubeconfig)

    def test_init_with_kubeconfig_string(self):
        """Test initialization with kubeconfig"""
        kubeconfig = os.environ.get(
            "KUBECONFIG", str(Path.home() / ".kube" / "config")
        )
        path = Path(kubeconfig)
        kubeconfig_content = path.read_text(encoding="utf-8")

        ocp = KrknOpenshift(kubeconfig_string=kubeconfig_content)
        nodes = ocp.list_nodes()
        self.assertTrue(len(nodes) > 0)

    @patch("krkn_lib.k8s.krkn_kubernetes.config")
    def test_init_without_kubeconfig(self, mock_config):
        """Test initialization without kubeconfig path."""
        mock_config.load_kube_config = Mock()

        ocp = KrknOpenshift()

        self.assertIsNotNone(ocp)


class TestGetClusterversionString(unittest.TestCase):
    """Test get_clusterversion_string method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "_get_clusterversion_string")
    def test_get_clusterversion_string_success(
        self, mock_get_clusterversion_string
    ):
        """Test successful retrieval of clusterversion string."""
        mock_get_clusterversion_string.return_value = "4.13.0"

        result = self.ocp.get_clusterversion_string()

        self.assertEqual(result, "4.13.0")
        mock_get_clusterversion_string.assert_called_once()

    @patch.object(KrknOpenshift, "_get_clusterversion_string")
    def test_get_clusterversion_string_empty(
        self, mock_get_clusterversion_string
    ):
        """Test when clusterversion string is empty."""
        mock_get_clusterversion_string.return_value = ""

        result = self.ocp.get_clusterversion_string()

        self.assertEqual(result, "")


class TestIsOpenshift(unittest.TestCase):
    """Test is_openshift method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "_get_clusterversion_string")
    def test_is_openshift_true(self, mock_get_clusterversion_string):
        """Test is_openshift returns True for OpenShift cluster."""
        mock_get_clusterversion_string.return_value = "4.13.0"

        result = self.ocp.is_openshift()

        self.assertTrue(result)

    @patch.object(KrknOpenshift, "_get_clusterversion_string")
    def test_is_openshift_false_empty(self, mock_get_clusterversion_string):
        """Test is_openshift returns False when version is empty."""
        mock_get_clusterversion_string.return_value = ""

        result = self.ocp.is_openshift()

        self.assertFalse(result)

    @patch.object(KrknOpenshift, "_get_clusterversion_string")
    def test_is_openshift_false_none(self, mock_get_clusterversion_string):
        """Test is_openshift returns False when version is None."""
        mock_get_clusterversion_string.return_value = None

        result = self.ocp.is_openshift()

        self.assertFalse(result)


class TestGetClusterType(unittest.TestCase):
    """Test get_cluster_type method with PropertyMock."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_type_rosa(self, mock_api_client_prop):
        """Test getting ROSA cluster type from resource tags."""
        mock_api_client = Mock()

        mock_response = (
            str(
                {
                    "status": {
                        "platform": "AWS",
                        "platformStatus": {
                            "aws": {
                                "region": "us-west-2",
                                "resourceTags": [
                                    {"key": "prowci", "value": "ci-rosa-123"},
                                    {
                                        "key": "red-hat-clustertype",
                                        "value": "rosa",
                                    },
                                ],
                            }
                        },
                    }
                }
            ),
        )

        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cluster_type()

        self.assertEqual(result, "rosa")

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_type_self_managed(self, mock_api_client_prop):
        """Test getting self-managed cluster type (no resource tags)."""
        mock_api_client = Mock()

        mock_response = (
            str(
                {
                    "status": {
                        "platform": "AWS",
                        "platformStatus": {"aws": {"region": "us-west-2"}},
                    }
                }
            ),
        )

        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cluster_type()

        self.assertEqual(result, "self-managed")

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_type_exception(self, mock_api_client_prop):
        """Test exception handling returns self-managed."""
        mock_api_client = Mock()
        mock_api_client.call_api.side_effect = Exception("API error")
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cluster_type()

        self.assertEqual(result, "self-managed")

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_type_no_api_client(self, mock_api_client_prop):
        """Test when api_client is None."""
        mock_api_client_prop.return_value = None

        result = self.ocp.get_cluster_type()

        self.assertIsNone(result)


class TestGetCloudInfrastructure(unittest.TestCase):
    """Test get_cloud_infrastructure method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cloud_infrastructure_aws(self, mock_api_client_prop):
        """Test getting AWS infrastructure."""
        mock_api_client = Mock()

        mock_response = (
            str(
                {
                    "status": {
                        "platform": "AWS",
                        "platformStatus": {"aws": {"region": "us-west-2"}},
                    }
                }
            ),
        )

        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cloud_infrastructure()

        self.assertEqual(result, "AWS")

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cloud_infrastructure_exception(self, mock_api_client_prop):
        """Test exception handling returns Unknown."""
        mock_api_client = Mock()
        mock_api_client.call_api.side_effect = Exception("API error")
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cloud_infrastructure()

        self.assertEqual(result, "Unknown")

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cloud_infrastructure_no_api_client(
        self, mock_api_client_prop
    ):
        """Test when api_client is None."""
        mock_api_client_prop.return_value = None

        result = self.ocp.get_cloud_infrastructure()

        self.assertIsNone(result)


class TestGetClusterNetworkPlugins(unittest.TestCase):
    """Test get_cluster_network_plugins method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_network_plugins_ovn(self, mock_api_client_prop):
        """Test getting OVNKubernetes network plugin."""
        mock_api_client = Mock()

        mock_response = (
            str(
                {
                    "items": [
                        {
                            "metadata": {"name": "cluster"},
                            "status": {"networkType": "OVNKubernetes"},
                        }
                    ]
                }
            ),
        )

        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cluster_network_plugins()

        self.assertEqual(result, ["OVNKubernetes"])

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_network_plugins_exception(self, mock_api_client_prop):
        """Test exception handling returns Unknown."""
        mock_api_client = Mock()
        mock_api_client.call_api.side_effect = Exception("API error")
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_cluster_network_plugins()

        self.assertEqual(result, ["Unknown"])

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    def test_get_cluster_network_plugins_no_api_client(
        self, mock_api_client_prop
    ):
        """Test when api_client is None."""
        mock_api_client_prop.return_value = None

        result = self.ocp.get_cluster_network_plugins()

        self.assertEqual(result, [])


class TestGetPrometheusApiConnectionData(unittest.TestCase):
    """Test get_prometheus_api_connection_data method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    @patch.object(KrknOpenshift, "create_token_for_sa")
    def test_get_prometheus_api_connection_data_success(
        self, mock_create_token, mock_api_client_prop
    ):
        """Test successful retrieval of Prometheus connection data."""
        mock_create_token.return_value = "test-token-12345"

        mock_api_client = Mock()
        host = "prometheus-k8s-openshift-monitoring.apps.cluster.com"
        mock_response = (
            str(
                {
                    "items": [
                        {
                            "metadata": {"name": "prometheus-k8s"},
                            "spec": {"host": host},
                        }
                    ]
                }
            ),
        )

        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_prometheus_api_connection_data()

        self.assertIsNotNone(result)
        self.assertEqual(result.token, "test-token-12345")
        self.assertEqual(
            result.endpoint,
            "https://prometheus-k8s-openshift-monitoring.apps.cluster.com",
        )

    @patch.object(KrknOpenshift, "create_token_for_sa")
    def test_get_prometheus_api_connection_data_no_token(
        self, mock_create_token
    ):
        """Test when token creation fails."""
        mock_create_token.return_value = None

        result = self.ocp.get_prometheus_api_connection_data()

        self.assertIsNone(result)

    @patch.object(KrknOpenshift, "api_client", new_callable=PropertyMock)
    @patch.object(KrknOpenshift, "create_token_for_sa")
    def test_get_prometheus_api_connection_data_route_not_found(
        self, mock_create_token, mock_api_client_prop
    ):
        """Test when prometheus route is not found."""
        mock_create_token.return_value = "test-token-12345"

        mock_api_client = Mock()
        mock_response = (str({"items": []}),)
        mock_api_client.call_api.return_value = mock_response
        mock_api_client.select_header_accept.return_value = "application/json"
        mock_api_client_prop.return_value = mock_api_client

        result = self.ocp.get_prometheus_api_connection_data()

        self.assertIsNone(result)


class TestCollectFilterArchiveOcpLogs(unittest.TestCase):
    """Test collect_filter_archive_ocp_logs method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()
            self.safe_logger = Mock(spec=SafeLogger)

    @patch("shutil.which")
    def test_collect_filter_archive_ocp_logs_oc_not_found(self, mock_which):
        """Test when oc command is not found."""
        mock_which.return_value = None

        result = self.ocp.collect_filter_archive_ocp_logs(
            "/tmp/src",
            "/tmp/dst",
            "/tmp/kubeconfig",
            1234567890,
            1234567900,
            [r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+"],
            3,
            self.safe_logger,
        )

        self.assertIsNone(result)
        self.safe_logger.error.assert_called()

    @patch("os.path.exists")
    @patch("shutil.which")
    def test_collect_filter_archive_ocp_logs_invalid_kubeconfig(
        self, mock_which, mock_exists
    ):
        """Test with invalid kubeconfig path."""
        mock_which.return_value = "/usr/bin/oc"

        def exists_side_effect(path):
            if "kubeconfig" in path:
                return False
            return True

        mock_exists.side_effect = exists_side_effect

        with self.assertRaises(Exception) as context:
            self.ocp.collect_filter_archive_ocp_logs(
                "/tmp/src",
                "/tmp/dst",
                "/tmp/kubeconfig",
                1234567890,
                1234567900,
                [r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+"],
                3,
                self.safe_logger,
            )

        self.assertIn("kubeconfig path", str(context.exception))

    @patch("os.path.expanduser")
    @patch("os.path.exists")
    @patch("shutil.which")
    def test_collect_filter_archive_ocp_logs_expands_tilde(
        self, mock_which, mock_exists, mock_expanduser
    ):
        """Test tilde expansion in paths."""
        mock_which.return_value = "/usr/bin/oc"
        mock_exists.return_value = False

        def expanduser_side_effect(path):
            return path.replace("~", "/home/user")

        mock_expanduser.side_effect = expanduser_side_effect

        with self.assertRaises(Exception):
            self.ocp.collect_filter_archive_ocp_logs(
                "~/src",
                "~/dst",
                "~/kubeconfig",
                1234567890,
                1234567900,
                [r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+"],
                3,
                self.safe_logger,
            )

        # Should have expanded paths
        self.assertTrue(mock_expanduser.called)


class TestFilterMustGatherOcpLogFolder(unittest.TestCase):
    """Test filter_must_gather_ocp_log_folder method."""

    def setUp(self):
        with patch("krkn_lib.k8s.krkn_kubernetes.config"):
            self.ocp = KrknOpenshift()

    def test_filter_must_gather_ocp_log_folder_dst_not_exists(self):
        """Test when destination directory doesn't exist."""
        with self.assertRaises(Exception) as context:
            self.ocp.filter_must_gather_ocp_log_folder(
                "src/testdata/must-gather",
                "/nonexistent/dir",
                1234567890,
                1234567900,
                "*.log",
                3,
                [r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+"],
            )

        self.assertIn(
            "Log destination dir do not exist", str(context.exception)
        )


# ==============================================================================
# INTEGRATION TESTS (Require actual testdata or kind cluster connections)
# ==============================================================================


class KrknOpenshiftIntegrationTest(BaseTest):
    """Integration tests requiring actual cluster connections."""

    def test_get_cluster_version_string(self):
        """Test cluster version string retrieval on real cluster."""
        result = self.lib_ocp.get_clusterversion_string()
        self.assertIsNotNone(result)

    def test_get_cluster_network_plugins(self):
        """Test network plugin detection on real cluster."""
        resp = self.lib_ocp.get_cluster_network_plugins()
        self.assertTrue(len(resp) > 0)
        self.assertEqual(resp[0], "Unknown")

    def test_get_cluster_type(self):
        """Test cluster type detection on real cluster."""
        resp = self.lib_ocp.get_cluster_type()
        self.assertTrue(resp)
        self.assertEqual(resp, "self-managed")

    def test_get_cloud_infrastructure(self):
        """Test cloud infrastructure detection on real cluster."""
        resp = self.lib_ocp.get_cloud_infrastructure()
        self.assertTrue(resp)
        self.assertEqual(resp, "Unknown")

    def test_is_openshift(self):
        """Test OpenShift detection on real cluster."""
        self.assertFalse(self.lib_ocp.is_openshift())

    def test_filter_must_gather_ocp_log_folder(self):
        """Test log filtering with actual testdata files."""
        # 1694473200 = 12 Sep 2023 01:00 AM GMT+2
        # 1694476200 = 12 Sep 2023 01:50 AM GMT+2
        filter_patterns = [
            # Sep 9 11:20:36.123425532
            r"(\w{3}\s\d{1,2}\s\d{2}:\d{2}:\d{2}\.\d+).+",
            # kinit 2023/09/15 11:20:36 log
            r"kinit (\d+/\d+/\d+\s\d{2}:\d{2}:\d{2})\s+",
            # 2023-09-15T11:20:36.123425532Z log
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+",
        ]
        dst_dir = f"/tmp/filtered_logs.{datetime.now().timestamp()}"
        os.mkdir(dst_dir)

        try:
            self.lib_ocp.filter_must_gather_ocp_log_folder(
                "src/testdata/must-gather",
                dst_dir,
                1694473200,
                1694476200,
                "*.log",
                3,
                filter_patterns,
            )

            test_file_1 = os.path.join(
                dst_dir,
                "namespaces.openshift-monitoring.pods."
                "openshift-state-metrics-"
                "78df59b4d5-mjvhd.openshift-state-metrics."
                "openshift-state-metrics.logs.current.log",
            )

            test_file_2 = os.path.join(
                dst_dir,
                "namespaces.openshift-monitoring.pods.prometheus-"
                "k8s-0.prometheus.prometheus.logs.current.log",
            )

            self.assertTrue(os.path.exists(test_file_1))
            self.assertTrue(os.path.exists(test_file_2))

            test_file_1_lines = 0
            test_file_2_lines = 0

            with open(test_file_1) as file:
                for _ in file:
                    test_file_1_lines += 1

            with open(test_file_2) as file:
                for _ in file:
                    test_file_2_lines += 1

            self.assertEqual(test_file_1_lines, 7)
            self.assertEqual(test_file_2_lines, 4)
        finally:
            # Cleanup temporary directory
            if os.path.exists(dst_dir):
                import shutil

                shutil.rmtree(dst_dir)

    def _test_collect_filter_archive_ocp_logs(self):
        """
        Test full log collection, filtering, and archiving.

        Note: This test is incomplete and inactive because
        we don't have an OCP integration env yet.
        """
        base_dir = os.path.join(
            "/tmp", f"log-filter-test.{datetime.now().timestamp()}"
        )
        work_dir = os.path.join(base_dir, "must-gather")
        dst_dir = os.path.join(base_dir, "filtered_logs")
        os.mkdir(base_dir)
        os.mkdir(work_dir)
        os.mkdir(dst_dir)
        start = 1695218445
        end = 1695219345
        filter_patterns = [
            # Sep 9 11:20:36.123425532
            r"(\w{3}\s\d{1,2}\s\d{2}:\d{2}:\d{2}\.\d+).+",
            # kinit 2023/09/15 11:20:36 log
            r"kinit (\d+/\d+/\d+\s\d{2}:\d{2}:\d{2})\s+",
            # 2023-09-15T11:20:36.123425532Z log
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+",
        ]
        self.lib_ocp.collect_filter_archive_ocp_logs(
            work_dir,
            dst_dir,
            "/path/to/kubeconfig",  # Update with actual path
            start,
            end,
            filter_patterns,
            5,
            SafeLogger(),
        )


if __name__ == "__main__":
    unittest.main()
