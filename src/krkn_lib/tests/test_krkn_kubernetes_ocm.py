import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from kubernetes.client import ApiException

from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes


class TestKrknKubernetesOCM(unittest.TestCase):
    def setUp(self):
        """Set up mock objects for each test"""
        self.mock_custom_client = MagicMock()

        # Import and create instance with all mocks in place
        with (
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.CoreV1Api"),
            patch("kubernetes.client.CustomObjectsApi"),
            patch("kubernetes.client.AppsV1Api"),
            patch("kubernetes.client.BatchV1Api"),
            patch("kubernetes.client.ApiClient"),
            patch("kubernetes.client.VersionApi"),
            patch("kubernetes.client.NetworkingV1Api"),
        ):
            # Create KrknKubernetes instance with mocked dependencies
            self.lib_k8s = KrknKubernetes(kubeconfig_path="dummy")

        # Patch the custom_object_client property to return our mock
        self.custom_client_patcher = patch.object(
            type(self.lib_k8s),
            "custom_object_client",
            new_callable=PropertyMock,
            return_value=self.mock_custom_client,
        )
        self.custom_client_patcher.start()

    def tearDown(self):
        """Clean up patches after each test"""
        self.custom_client_patcher.stop()

    def test_list_killable_managedclusters_api_exception(self):
        self.mock_custom_client.list_cluster_custom_object.side_effect = ApiException(status=500)
        with self.assertRaises(ApiException):
            self.lib_k8s.list_killable_managedclusters()

    def test_list_killable_managedclusters_empty(self):
        self.mock_custom_client.list_cluster_custom_object.return_value = {"items": []}
        result = self.lib_k8s.list_killable_managedclusters()
        self.assertEqual(result, [])

    def test_list_killable_managedclusters_available(self):
        self.mock_custom_client.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "cluster-1"},
                    "status": {
                        "conditions": [
                            {"reason": "ManagedClusterAvailable", "status": "True"}
                        ]
                    }
                }
            ]
        }
        result = self.lib_k8s.list_killable_managedclusters()
        self.assertEqual(result, ["cluster-1"])

    def test_list_killable_managedclusters_unavailable(self):
        self.mock_custom_client.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "cluster-1"},
                    "status": {
                        "conditions": [
                            {"reason": "ManagedClusterAvailable", "status": "False"}
                        ]
                    }
                }
            ]
        }
        result = self.lib_k8s.list_killable_managedclusters()
        self.assertEqual(result, [])

    def test_list_killable_managedclusters_no_available_condition(self):
        self.mock_custom_client.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "cluster-1"},
                    "status": {
                        "conditions": [
                            {"reason": "SomeOtherCondition", "status": "True"}
                        ]
                    }
                }
            ]
        }
        result = self.lib_k8s.list_killable_managedclusters()
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
