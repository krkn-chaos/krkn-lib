import unittest
from unittest.mock import Mock, patch

from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils.safe_logger import SafeLogger


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


if __name__ == "__main__":
    unittest.main()
