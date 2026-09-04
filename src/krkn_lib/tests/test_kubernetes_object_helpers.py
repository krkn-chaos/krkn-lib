"""
Tests for KubernetesObjectHelpers
"""

import unittest
from unittest.mock import MagicMock
from kubernetes.client.rest import ApiException
from krkn_lib.k8s.kubernetes_object_helpers import KubernetesObjectHelpers


class TestKubernetesObjectHelpers(unittest.TestCase):
    """Tests for KubernetesObjectHelpers class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_krkn = MagicMock()
        self.helpers = KubernetesObjectHelpers(self.mock_krkn)

    def test_get_object_by_name_pod(self):
        """Test getting a Pod using get_object_by_name"""
        mock_pod = {"metadata": {"name": "test-pod", "namespace": "default"}}
        self.mock_krkn.cli.read_namespaced_pod.return_value = mock_pod
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pod

        result = self.helpers.get_object_by_name("Pod", "test-pod", "default")

        self.assertEqual(result, mock_pod)
        self.mock_krkn.cli.read_namespaced_pod.assert_called_once_with("test-pod", "default")

    def test_get_object_by_name_deployment(self):
        """Test getting a Deployment using get_object_by_name"""
        mock_deployment = {"metadata": {"name": "test-deploy"}}
        self.mock_krkn.apps_api.read_namespaced_deployment.return_value = mock_deployment
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_deployment

        result = self.helpers.get_object_by_name("Deployment", "test-deploy", "default")

        self.assertEqual(result, mock_deployment)
        self.mock_krkn.apps_api.read_namespaced_deployment.assert_called_once_with("test-deploy", "default")

    def test_get_object_by_name_statefulset(self):
        """Test getting a StatefulSet using get_object_by_name"""
        mock_sts = {"metadata": {"name": "test-sts"}}
        self.mock_krkn.apps_api.read_namespaced_stateful_set.return_value = mock_sts
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_sts

        result = self.helpers.get_object_by_name("StatefulSet", "test-sts", "default")

        self.assertEqual(result, mock_sts)
        self.mock_krkn.apps_api.read_namespaced_stateful_set.assert_called_once_with("test-sts", "default")

    def test_get_object_by_name_daemonset(self):
        """Test getting a DaemonSet using get_object_by_name"""
        mock_ds = {"metadata": {"name": "test-ds"}}
        self.mock_krkn.apps_api.read_namespaced_daemon_set.return_value = mock_ds
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_ds

        result = self.helpers.get_object_by_name("DaemonSet", "test-ds", "default")

        self.assertEqual(result, mock_ds)
        self.mock_krkn.apps_api.read_namespaced_daemon_set.assert_called_once_with("test-ds", "default")

    def test_get_object_by_name_replicaset(self):
        """Test getting a ReplicaSet using get_object_by_name"""
        mock_rs = {"metadata": {"name": "test-rs"}}
        self.mock_krkn.apps_api.read_namespaced_replica_set.return_value = mock_rs
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_rs

        result = self.helpers.get_object_by_name("ReplicaSet", "test-rs", "default")

        self.assertEqual(result, mock_rs)
        self.mock_krkn.apps_api.read_namespaced_replica_set.assert_called_once_with("test-rs", "default")

    def test_get_object_by_name_service(self):
        """Test getting a Service using get_object_by_name"""
        mock_svc = {"metadata": {"name": "test-svc"}}
        self.mock_krkn.cli.read_namespaced_service.return_value = mock_svc
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_svc

        result = self.helpers.get_object_by_name("Service", "test-svc", "default")

        self.assertEqual(result, mock_svc)
        self.mock_krkn.cli.read_namespaced_service.assert_called_once_with("test-svc", "default")

    def test_get_object_by_name_persistentvolumeclaim(self):
        """Test getting a PersistentVolumeClaim using get_object_by_name"""
        mock_pvc = {"metadata": {"name": "test-pvc"}}
        self.mock_krkn.cli.read_namespaced_persistent_volume_claim.return_value = mock_pvc
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pvc

        result = self.helpers.get_object_by_name("PersistentVolumeClaim", "test-pvc", "default")

        self.assertEqual(result, mock_pvc)
        self.mock_krkn.cli.read_namespaced_persistent_volume_claim.assert_called_once_with("test-pvc", "default")

    def test_get_object_by_name_job(self):
        """Test getting a Job using get_object_by_name"""
        mock_job = {"metadata": {"name": "test-job"}}
        self.mock_krkn.batch_cli.read_namespaced_job.return_value = mock_job
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_job

        result = self.helpers.get_object_by_name("Job", "test-job", "default")

        self.assertEqual(result, mock_job)
        self.mock_krkn.batch_cli.read_namespaced_job.assert_called_once_with("test-job", "default")

    def test_get_object_by_name_cronjob(self):
        """Test getting a CronJob using get_object_by_name"""
        mock_cj = {"metadata": {"name": "test-cj"}}
        self.mock_krkn.batch_cli.read_namespaced_cron_job.return_value = mock_cj
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_cj

        result = self.helpers.get_object_by_name("CronJob", "test-cj", "default")

        self.assertEqual(result, mock_cj)
        self.mock_krkn.batch_cli.read_namespaced_cron_job.assert_called_once_with("test-cj", "default")

    def test_get_object_by_name_node(self):
        """Test getting a Node using get_object_by_name"""
        mock_node = {"metadata": {"name": "worker-1"}}
        self.mock_krkn.cli.read_node.return_value = mock_node
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_node

        result = self.helpers.get_object_by_name("Node", "worker-1")

        self.assertEqual(result, mock_node)
        self.mock_krkn.cli.read_node.assert_called_once_with("worker-1")

    def test_get_object_by_name_persistentvolume(self):
        """Test getting a PersistentVolume using get_object_by_name"""
        mock_pv = {"metadata": {"name": "test-pv"}}
        self.mock_krkn.cli.read_persistent_volume.return_value = mock_pv
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pv

        result = self.helpers.get_object_by_name("PersistentVolume", "test-pv")

        self.assertEqual(result, mock_pv)
        self.mock_krkn.cli.read_persistent_volume.assert_called_once_with("test-pv")

    def test_get_object_by_name_case_insensitive(self):
        """Test that resource kind is case-insensitive"""
        mock_pod = {"metadata": {"name": "test-pod"}}
        self.mock_krkn.cli.read_namespaced_pod.return_value = mock_pod
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_pod

        result = self.helpers.get_object_by_name("pod", "test-pod", "default")

        self.assertEqual(result, mock_pod)

    def test_get_object_by_name_missing_namespace_raises(self):
        """Test that missing namespace for namespaced resource raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.helpers.get_object_by_name("Pod", "test-pod")

        self.assertIn("Namespace is required", str(context.exception))

    def test_get_object_by_name_unsupported_kind(self):
        """Test that unsupported resource kind returns None"""
        result = self.helpers.get_object_by_name("UnsupportedKind", "test", "default")
        self.assertIsNone(result)

    def test_get_object_by_name_api_exception(self):
        """Test that ApiException is re-raised"""
        self.mock_krkn.cli.read_namespaced_pod.side_effect = ApiException(404, "Not Found")

        with self.assertRaises(ApiException):
            self.helpers.get_object_by_name("Pod", "test-pod", "default")

    def test_get_object_by_name_cluster_scoped_ignores_namespace(self):
        """Test that cluster-scoped resources don't use namespace"""
        mock_node = {"metadata": {"name": "worker-1"}}
        self.mock_krkn.cli.read_node.return_value = mock_node
        self.mock_krkn.api_client.sanitize_for_serialization.return_value = mock_node

        result = self.helpers.get_object_by_name("Node", "worker-1", namespace="ignored")

        self.assertEqual(result, mock_node)
        self.mock_krkn.cli.read_node.assert_called_once_with("worker-1")


if __name__ == "__main__":
    unittest.main()
