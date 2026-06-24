import unittest
from unittest.mock import Mock, patch

from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils.safe_logger import SafeLogger
from krkn_lib.models.telemetry import ChaosRunTelemetry


def _make_telemetry():
    mock_logger = Mock(spec=SafeLogger)
    mock_ocpcli = Mock(spec=KrknOpenshift)
    return KrknTelemetryOpenshift(
        safe_logger=mock_logger,
        lib_openshift=mock_ocpcli,
    ), mock_ocpcli


def _cluster_response(items, continue_token=None):
    resp = {"items": items, "metadata": {}}
    if continue_token:
        resp["metadata"]["continue"] = continue_token
    return resp


class TestGetVmNumber(unittest.TestCase):

    def test_returns_correct_count(self):
        """Returns count from a single-page cluster-wide response."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([{}, {}, {}])
        )
        self.assertEqual(telemetry.get_vm_number(), 3)
        client.list_cluster_custom_object.assert_called_once_with(
            group="kubevirt.io",
            version="v1",
            plural="virtualmachineinstances",
            limit=500,
        )

    def test_paginates_across_pages(self):
        """Follows continue token and sums items across pages."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = [
            _cluster_response([{}, {}], continue_token="tok1"),
            _cluster_response([{}]),
        ]
        self.assertEqual(telemetry.get_vm_number(), 3)
        self.assertEqual(
            client.list_cluster_custom_object.call_count, 2
        )

    def test_empty_vmi_list_returns_zero(self):
        """Empty cluster returns 0."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([])
        )
        self.assertEqual(telemetry.get_vm_number(), 0)

    @patch("krkn_lib.telemetry.ocp.krkn_telemetry_openshift.logging")
    def test_exception_returns_zero_and_logs(self, mock_logging):
        """Exception returns 0 and logs the error message."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = (
            Exception("connection refused")
        )
        self.assertEqual(telemetry.get_vm_number(), 0)
        mock_logging.info.assert_called_once()
        self.assertIn(
            "connection refused", mock_logging.info.call_args[0][0]
        )


class TestGetBuildCount(unittest.TestCase):

    def test_returns_correct_count(self):
        """Returns count from a single-page cluster-wide response."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([{}, {}])
        )
        self.assertEqual(telemetry.get_build_count(), 2)
        client.list_cluster_custom_object.assert_called_once_with(
            group="build.openshift.io",
            version="v1",
            plural="builds",
            limit=500,
        )

    def test_paginates_across_pages(self):
        """Follows continue token and sums items across pages."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = [
            _cluster_response([{}, {}], continue_token="tok1"),
            _cluster_response([{}, {}], continue_token="tok2"),
            _cluster_response([{}]),
        ]
        self.assertEqual(telemetry.get_build_count(), 5)
        self.assertEqual(client.list_cluster_custom_object.call_count, 3)

    def test_empty_build_list_returns_zero(self):
        """Empty cluster returns 0."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([])
        )
        self.assertEqual(telemetry.get_build_count(), 0)

    @patch("krkn_lib.telemetry.ocp.krkn_telemetry_openshift.logging")
    def test_exception_returns_zero_and_logs(self, mock_logging):
        """Exception returns 0 and logs the error message."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = (
            Exception("builds api not found")
        )
        self.assertEqual(telemetry.get_build_count(), 0)
        mock_logging.info.assert_called_once()
        self.assertIn(
            "builds api not found", mock_logging.info.call_args[0][0]
        )


class TestGetRouteCount(unittest.TestCase):

    def test_returns_correct_count(self):
        """Returns count from a single-page cluster-wide response."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([{}, {}, {}, {}])
        )
        self.assertEqual(telemetry.get_route_count(), 4)
        client.list_cluster_custom_object.assert_called_once_with(
            group="route.openshift.io",
            version="v1",
            plural="routes",
            limit=500,
        )

    def test_paginates_across_pages(self):
        """Follows continue token and sums items across pages."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = [
            _cluster_response([{}, {}], continue_token="tok1"),
            _cluster_response([{}]),
        ]
        self.assertEqual(telemetry.get_route_count(), 3)
        self.assertEqual(client.list_cluster_custom_object.call_count, 2)

    def test_empty_route_list_returns_zero(self):
        """Empty cluster returns 0."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.return_value = (
            _cluster_response([])
        )
        self.assertEqual(telemetry.get_route_count(), 0)

    @patch("krkn_lib.telemetry.ocp.krkn_telemetry_openshift.logging")
    def test_exception_returns_zero_and_logs(self, mock_logging):
        """Exception returns 0 and logs the error message."""
        telemetry, mock_ocpcli = _make_telemetry()
        client = mock_ocpcli.custom_object_client
        client.list_cluster_custom_object.side_effect = (
            Exception("routes api not found")
        )
        self.assertEqual(telemetry.get_route_count(), 0)
        mock_logging.info.assert_called_once()
        self.assertIn(
            "routes api not found", mock_logging.info.call_args[0][0]
        )


class TestPutOcpLogs(unittest.TestCase):

    def _make_config(self, **overrides):
        base = {
            "logs_backup": True,
            "api_url": "https://telemetry.example.com",
            "username": "user",
            "password": "pass",
            "backup_threads": 2,
            "max_retries": 3,
            "archive_path": "/tmp",
            "logs_filter_patterns": [r".*"],
            "oc_cli_path": None,
            "telemetry_group": "test",
        }
        base.update(overrides)
        return base

    def test_skips_when_api_url_is_none(self):
        """Returns early and logs info when api_url is None."""
        telemetry, _ = _make_telemetry()
        telemetry.put_ocp_logs("req-id", self._make_config(api_url=None), 0, 1)
        telemetry.safe_logger.info.assert_called_once()
        self.assertIn(
            "api_url", telemetry.safe_logger.info.call_args[0][0]
        )

    def test_skips_when_api_url_is_empty_string(self):
        """Returns early and logs info when api_url is an empty string."""
        telemetry, _ = _make_telemetry()
        telemetry.put_ocp_logs("req-id", self._make_config(api_url=""), 0, 1)
        telemetry.safe_logger.info.assert_called_once()
        self.assertIn(
            "api_url", telemetry.safe_logger.info.call_args[0][0]
        )

    def test_raises_when_api_url_has_invalid_scheme(self):
        """Raises Exception when api_url does not start with http/https."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id",
                self._make_config(api_url="ftp://telemetry.example.com"),
                0,
                1,
            )
        self.assertIn("api_url is invalid", str(ctx.exception))

    def test_raises_when_api_url_has_no_scheme(self):
        """Raises Exception when api_url is a bare hostname with no scheme."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id",
                self._make_config(api_url="telemetry.example.com"),
                0,
                1,
            )
        self.assertIn("api_url is invalid", str(ctx.exception))

    def test_raises_when_logs_backup_missing(self):
        """Raises Exception when logs_backup is absent from config."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(logs_backup=None), 0, 1
            )
        self.assertIn("logs_backup flag is missing", str(ctx.exception))

    def test_raises_when_backup_threads_missing(self):
        """Raises Exception when backup_threads is absent, not also a type error."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(backup_threads=None), 0, 1
            )
        msg = str(ctx.exception)
        self.assertIn("backup_threads is missing", msg)
        self.assertNotIn("must be a number", msg)

    def test_raises_when_backup_threads_is_string(self):
        """Raises Exception when backup_threads is a string, not an int."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(backup_threads="4"), 0, 1
            )
        msg = str(ctx.exception)
        self.assertIn("must be a number not a string", msg)
        self.assertNotIn("is missing", msg)

    def test_raises_when_username_missing(self):
        """Raises Exception when username is absent from config."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(username=None), 0, 1
            )
        self.assertIn("username is missing", str(ctx.exception))

    def test_raises_when_password_missing(self):
        """Raises Exception when password is absent from config."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(password=None), 0, 1
            )
        self.assertIn("password is missing", str(ctx.exception))

    def test_raises_when_max_retries_missing(self):
        """Raises Exception when max_retries is absent from config."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(max_retries=None), 0, 1
            )
        self.assertIn("max_retries is missing", str(ctx.exception))

    def test_raises_when_archive_path_missing(self):
        """Raises Exception when archive_path is absent from config."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(archive_path=None), 0, 1
            )
        self.assertIn("archive_path is missing", str(ctx.exception))

    def test_raises_when_logs_filter_patterns_missing(self):
        """Raises Exception when logs_filter_patterns is absent, not also a type error."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id", self._make_config(logs_filter_patterns=None), 0, 1
            )
        msg = str(ctx.exception)
        self.assertIn("logs_filter_patterns is missing", msg)
        self.assertNotIn("must be a list", msg)

    def test_raises_when_logs_filter_patterns_not_a_list(self):
        """Raises Exception when logs_filter_patterns is a string, not a list."""
        telemetry, _ = _make_telemetry()
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs(
                "req-id",
                self._make_config(logs_filter_patterns=".*"),
                0,
                1,
            )
        msg = str(ctx.exception)
        self.assertIn("must be a list of regex pattern", msg)
        self.assertNotIn("is missing", msg)

    def test_raises_with_all_missing_fields_joined(self):
        """Single exception message contains all missing field names joined."""
        telemetry, _ = _make_telemetry()
        config = {
            "api_url": "https://telemetry.example.com",
            "logs_backup": None,
            "backup_threads": None,
            "username": None,
            "password": None,
            "max_retries": None,
            "archive_path": None,
            "logs_filter_patterns": None,
        }
        with self.assertRaises(Exception) as ctx:
            telemetry.put_ocp_logs("req-id", config, 0, 1)
        msg = str(ctx.exception)
        for fragment in [
            "logs_backup flag is missing",
            "backup_threads is missing",
            "username is missing",
            "password is missing",
            "max_retries is missing",
            "archive_path is missing",
            "logs_filter_patterns is missing",
        ]:
            self.assertIn(fragment, msg)

    def test_skips_when_logs_backup_is_false(self):
        """Returns early and logs info when logs_backup is False."""
        telemetry, _ = _make_telemetry()
        telemetry.put_ocp_logs(
            "req-id", self._make_config(logs_backup=False), 0, 1
        )
        telemetry.safe_logger.info.assert_called_once()
        self.assertIn(
            "logs_backup is False", telemetry.safe_logger.info.call_args[0][0]
        )



class TestGetLibOcp(unittest.TestCase):
    def test_returns_ocpcli(self):
        """Returns the internal __ocpcli assigned during initialization."""
        telemetry, mock_ocpcli = _make_telemetry()
        self.assertIs(telemetry.get_lib_ocp(), mock_ocpcli)


class TestGetOcpPrometheusData(unittest.TestCase):
    @patch.object(KrknTelemetryOpenshift, "get_prometheus_pod_data")
    def test_delegates_to_kubernetes_prometheus_with_ocp_defaults(self, mock_get_pod_data):
        """Invokes get_prometheus_pod_data with specific OpenShift strings."""
        telemetry, _ = _make_telemetry()
        mock_get_pod_data.return_value = [(1, "test_file.tar.gz")]
        telemetry_config = {"api_url": "test"}
        request_id = "req-123"
        result = telemetry.get_ocp_prometheus_data(
            telemetry_config,
            request_id
        )
        mock_get_pod_data.assert_called_once_with(
            telemetry_config,
            request_id,
            "prometheus-k8s-0",
            "prometheus",
            "openshift-monitoring",
        )
        self.assertEqual(result, [(1, "test_file.tar.gz")])


class TestCollectClusterMetadata(unittest.TestCase):

    @patch.object(KrknTelemetryOpenshift, "get_route_count")
    @patch.object(KrknTelemetryOpenshift, "get_build_count")
    @patch.object(KrknTelemetryOpenshift, "get_vm_number")
    def test_collects_metadata_successfully(
        self,
        mock_get_vm,
        mock_get_build,
        mock_get_route,
    ):
        """Populates chaos_telemetry with metadata successfully."""
        telemetry, mock_ocpcli = _make_telemetry()
        mock_ocpcli.get_cloud_infrastructure.return_value = "AWS"
        mock_ocpcli.get_cluster_type.return_value = "Managed"
        mock_ocpcli.get_clusterversion_string.return_value = "4.15.2"
        mock_ocpcli.get_cluster_network_plugins.return_value = ["OVN"]
        mock_get_vm.return_value = 10
        mock_get_build.return_value = 20
        mock_get_route.return_value = 30
        chaos_telemetry = ChaosRunTelemetry()
        with patch(
            "krkn_lib.telemetry.k8s.KrknTelemetryKubernetes.collect_cluster_metadata"
        ) as mock_super_collect:
            telemetry.collect_cluster_metadata(chaos_telemetry)
            mock_super_collect.assert_called_once_with(chaos_telemetry)
        self.assertEqual(chaos_telemetry.cloud_infrastructure, "AWS")
        self.assertEqual(chaos_telemetry.cloud_type, "Managed")
        # Assert both the raw version string and the derived major_version slice
        # to make clear we are validating current [:4] behavior, not invented semantics.
        self.assertEqual(chaos_telemetry.cluster_version, "4.15.2")
        self.assertEqual(chaos_telemetry.major_version, "4.15")
        self.assertEqual(chaos_telemetry.network_plugins, ["OVN"])
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count["VirtualMachineInstance"],
            10,
        )
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count["Build"],
            20,
        )
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count["Route"],
            30,
        )

    @patch.object(KrknTelemetryOpenshift, "get_route_count")
    @patch.object(KrknTelemetryOpenshift, "get_build_count")
    @patch.object(KrknTelemetryOpenshift, "get_vm_number")
    def test_handles_exceptions_gracefully(
        self,
        mock_get_vm,
        mock_get_build,
        mock_get_route,
    ):
        """Exceptions in timed methods do not crash and leave fields as None."""
        telemetry, mock_ocpcli = _make_telemetry()
        mock_ocpcli.get_cloud_infrastructure.return_value = "AWS"
        mock_ocpcli.get_cluster_type.side_effect = Exception("API error")
        mock_ocpcli.get_clusterversion_string.return_value = "4.15.2"
        mock_ocpcli.get_cluster_network_plugins.return_value = ["OVN"]
        mock_get_vm.return_value = 10
        mock_get_build.return_value = 20
        mock_get_route.return_value = 30
        chaos_telemetry = ChaosRunTelemetry()
        with patch(
            "krkn_lib.telemetry.k8s.KrknTelemetryKubernetes.collect_cluster_metadata"
        ):
            telemetry.collect_cluster_metadata(chaos_telemetry)
        self.assertEqual(chaos_telemetry.cloud_infrastructure, "AWS")
        # cloud_type is None because the failed timed() call causes get_result
        # to return None, overwriting the 'self-managed' default.
        self.assertIsNone(chaos_telemetry.cloud_type)
        self.assertEqual(chaos_telemetry.cluster_version, "4.15.2")
        # The timed() wrapper emits a warning before re-raising;
        # verify the warning is observable on the exception path.
        telemetry.safe_logger.warning.assert_called()

    @patch.object(KrknTelemetryOpenshift, "get_route_count")
    @patch.object(KrknTelemetryOpenshift, "get_build_count")
    @patch.object(KrknTelemetryOpenshift, "get_vm_number")
    def test_does_not_add_vmi_count_when_zero(
        self,
        mock_get_vm,
        mock_get_build,
        mock_get_route,
    ):
        """VirtualMachineInstance key is absent when vm_number returns 0."""
        telemetry, mock_ocpcli = _make_telemetry()
        mock_ocpcli.get_cloud_infrastructure.return_value = "AWS"
        mock_ocpcli.get_cluster_type.return_value = "Managed"
        mock_ocpcli.get_clusterversion_string.return_value = "4.15.2"
        mock_ocpcli.get_cluster_network_plugins.return_value = ["OVN"]
        mock_get_vm.return_value = 0
        mock_get_build.return_value = 5
        mock_get_route.return_value = 3
        chaos_telemetry = ChaosRunTelemetry()
        with patch(
            "krkn_lib.telemetry.k8s.KrknTelemetryKubernetes.collect_cluster_metadata"
        ):
            telemetry.collect_cluster_metadata(chaos_telemetry)
        self.assertNotIn(
            "VirtualMachineInstance",
            chaos_telemetry.kubernetes_objects_count,
        )
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count["Build"],
            5,
        )
        self.assertEqual(
            chaos_telemetry.kubernetes_objects_count["Route"],
            3,
        )


if __name__ == "__main__":
    unittest.main()
