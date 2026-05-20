"""Unit tests for deploy_io_throttle_pod and create_pod conflict handling."""

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from kubernetes.client import ApiException

from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes


class TestDeployIoThrottlePod(unittest.TestCase):
    def setUp(self):
        self.lib_k8s = KrknKubernetes.__new__(KrknKubernetes)

    @patch(
        "krkn_lib.k8s.krkn_kubernetes.uuid.uuid4",
        return_value=MagicMock(hex="a1b2c3d4e5f678901234567890abcdef"),
    )
    def test_deploy_uses_uuid_suffix(self, _mock_uuid):
        self.lib_k8s.create_pod = MagicMock()
        pod_name = self.lib_k8s.deploy_io_throttle_pod(
            "worker-1", "quay.io/example/tools:latest", "default", 1
        )
        self.assertEqual(pod_name, "io-throttle-a1b2c3d4e5")
        create_body = self.lib_k8s.create_pod.call_args[0][0]
        self.assertEqual(
            create_body["metadata"]["name"], "io-throttle-a1b2c3d4e5"
        )
        self.lib_k8s.create_pod.assert_called_once()


class TestCreatePodConflictHandling(unittest.TestCase):
    def setUp(self):
        self.lib_k8s = KrknKubernetes.__new__(KrknKubernetes)
        self.mock_cli = MagicMock()
        self.cli_patcher = patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=self.mock_cli,
        )
        self.cli_patcher.start()
        self.addCleanup(self.cli_patcher.stop)
        self.lib_k8s.delete_pod = MagicMock()

    def test_create_pod_does_not_delete_on_already_exists(self):
        conflict = ApiException(status=409, reason="AlreadyExists")
        self.mock_cli.create_namespaced_pod.side_effect = conflict
        body = {"metadata": {"name": "io-throttle-existing"}}

        with self.assertRaises(ApiException):
            self.lib_k8s.create_pod(body, "default", 1)

        self.lib_k8s.delete_pod.assert_not_called()

    @patch("krkn_lib.k8s.krkn_kubernetes.time.sleep")
    def test_create_pod_deletes_only_when_pod_was_created(self, _mock_sleep):
        created = MagicMock()
        self.mock_cli.create_namespaced_pod.return_value = created
        self.mock_cli.read_namespaced_pod.side_effect = Exception("read failed")

        with self.assertRaises(Exception):
            self.lib_k8s.create_pod(
                {"metadata": {"name": "io-throttle-new"}}, "default", 1
            )

        self.lib_k8s.delete_pod.assert_called_once_with(
            "io-throttle-new", "default"
        )
