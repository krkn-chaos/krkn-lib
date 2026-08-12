import logging
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch

from kubernetes import client
from kubernetes.client import ApiException

from krkn_lib.k8s import ApiRequestException
from krkn_lib.k8s.krkn_kubernetes import KrknKubernetes
from krkn_lib.tests import BaseTest


class KrknKubernetesTestsDelete(BaseTest):
    def test_delete_namespace(self):
        name = "test-d-ns-" + self.get_random_string(6)
        self.deploy_namespace(name, [{"name": "name", "label": name}])
        result = self.lib_k8s.get_namespace_status(name)
        self.assertTrue(result == "Active")
        self.lib_k8s.delete_namespace(name)
        try:
            while True:
                logging.info("Waiting %s namespace to be deleted", name)
                self.lib_k8s.get_namespace_status(name)
        except ApiRequestException:
            logging.info("Namespace %s terminated", name)

    def test_delete_pod(self):
        namespace = "test-dp-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        self.wait_pod("fedtools", namespace=namespace)
        self.lib_k8s.delete_pod("fedtools", namespace=namespace)
        with self.assertRaises(ApiException):
            self.lib_k8s.read_pod("fedtools", namespace=namespace)
        self.pod_delete_queue.put(["fedtools", namespace])

    def test_delete_deployment(self):
        namespace = "test-dd" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_deployment(name, namespace)
        deps = self.lib_k8s.get_deployment_ns(namespace=namespace)
        self.assertTrue(len(deps) == 1)
        self.lib_k8s.delete_deployment(name, namespace)
        deps = self.lib_k8s.get_deployment_ns(namespace=namespace)
        self.assertTrue(len(deps) == 0)
        self.pod_delete_queue.put([name, namespace])

    def test_delete_statefulsets(self):
        namespace = "test-ss" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_statefulset(name, namespace)
        ss = self.lib_k8s.get_all_statefulset(namespace=namespace)
        self.assertTrue(len(ss) == 1)
        self.lib_k8s.delete_statefulset(name, namespace)
        ss = self.lib_k8s.get_all_statefulset(namespace=namespace)
        self.assertTrue(len(ss) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_daemonset(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_daemonset(name, namespace)
        daemonset = self.lib_k8s.get_daemonset(namespace=namespace)
        self.assertTrue(len(daemonset) == 1)
        self.lib_k8s.delete_daemonset(name, namespace)

        daemonset = self.lib_k8s.get_daemonset(namespace=namespace)
        self.assertTrue(len(daemonset) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_services(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_service(name, namespace)
        services = self.lib_k8s.get_all_services(namespace=namespace)
        self.assertTrue(len(services) == 1)
        self.lib_k8s.delete_services(name, namespace)
        services = self.lib_k8s.get_all_services(namespace=namespace)
        self.assertTrue(len(services) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_replicaset(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_replicaset(name, namespace)
        replicaset = self.lib_k8s.get_all_replicasets(namespace=namespace)
        self.assertTrue(len(replicaset) == 1)
        self.lib_k8s.delete_replicaset(name, namespace)
        replicaset = self.lib_k8s.get_all_replicasets(namespace=namespace)
        self.assertTrue(len(replicaset) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_job(self):
        namespace = "test-ns-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_job(name, namespace)
        self.lib_k8s.delete_job(name, namespace)
        max_retries = 30
        sleep = 2
        counter = 0
        while True:
            if counter > max_retries:
                logging.error("Job not canceled after 60 seconds, failing")
                self.assertTrue(False)
            try:
                self.lib_k8s.get_job_status(name, namespace)
                time.sleep(sleep)
                counter = counter + 1

            except ApiException:
                # if an exception is raised the job is not found so has been
                # deleted correctly
                logging.debug(
                    "job deleted after %d seconds" % (counter * sleep)
                )
                break
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_deployment_already_deleted(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_deployment.side_effect = ApiException(status=404)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            self.lib_k8s.delete_deployment("name", "namespace")

    def test_delete_deployment_api_error_raises(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_deployment.side_effect = ApiException(status=500)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            with self.assertRaises(ApiException):
                self.lib_k8s.delete_deployment("name", "namespace")

    def test_delete_daemonset_already_deleted(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_daemon_set.side_effect = ApiException(status=404)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            self.lib_k8s.delete_daemonset("name", "namespace")

    def test_delete_daemonset_api_error_raises(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_daemon_set.side_effect = ApiException(status=500)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            with self.assertRaises(ApiException):
                self.lib_k8s.delete_daemonset("name", "namespace")

    def test_delete_statefulset_already_deleted(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_stateful_set.side_effect = ApiException(status=404)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            self.lib_k8s.delete_statefulset("name", "namespace")

    def test_delete_statefulset_api_error_raises(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_stateful_set.side_effect = ApiException(status=500)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            with self.assertRaises(ApiException):
                self.lib_k8s.delete_statefulset("name", "namespace")

    def test_delete_replicaset_already_deleted(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_replica_set.side_effect = ApiException(status=404)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            self.lib_k8s.delete_replicaset("name", "namespace")

    def test_delete_replicaset_api_error_raises(self):
        mock_apps = MagicMock()
        mock_apps.delete_namespaced_replica_set.side_effect = ApiException(status=500)
        with patch.object(
            KrknKubernetes,
            "apps_api",
            new_callable=PropertyMock,
            return_value=mock_apps,
        ):
            with self.assertRaises(ApiException):
                self.lib_k8s.delete_replicaset("name", "namespace")

    def test_delete_services_already_deleted(self):
        mock_cli = MagicMock()
        mock_cli.delete_namespaced_service.side_effect = ApiException(status=404)
        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            self.lib_k8s.delete_services("name", "namespace")

    def test_delete_services_api_error_raises(self):
        mock_cli = MagicMock()
        mock_cli.delete_namespaced_service.side_effect = ApiException(status=500)
        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            with self.assertRaises(ApiException):
                self.lib_k8s.delete_services("name", "namespace")


    def test_delete_pod_force_passes_grace_period_zero(self):
        """Verify force delete passes V1DeleteOptions with grace_period_seconds=0"""
        mock_cli = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.creation_timestamp = datetime(
            2026, 1, 1, tzinfo=timezone.utc
        )
        mock_cli.read_namespaced_pod.side_effect = [
            mock_pod,
            ApiException(status=404),
        ]
        mock_cli.delete_namespaced_pod.return_value = None

        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            self.lib_k8s.delete_pod("test-pod", "test-ns", grace_period_seconds=0)

        mock_cli.delete_namespaced_pod.assert_called_once()
        call_kwargs = mock_cli.delete_namespaced_pod.call_args[1]
        self.assertEqual(call_kwargs["name"], "test-pod")
        self.assertEqual(call_kwargs["namespace"], "test-ns")
        self.assertIsInstance(call_kwargs["body"], client.V1DeleteOptions)
        self.assertEqual(call_kwargs["body"].grace_period_seconds, 0)

    def test_delete_pod_graceful_no_delete_options(self):
        """Verify graceful delete (default) does not pass V1DeleteOptions body"""
        mock_cli = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.creation_timestamp = datetime(
            2026, 1, 1, tzinfo=timezone.utc
        )
        mock_cli.read_namespaced_pod.side_effect = [
            mock_pod,
            ApiException(status=404),
        ]
        mock_cli.delete_namespaced_pod.return_value = None

        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            self.lib_k8s.delete_pod("test-pod", "test-ns")

        mock_cli.delete_namespaced_pod.assert_called_once_with(
            name="test-pod", namespace="test-ns"
        )

    def test_delete_pod_custom_grace_period(self):
        """Verify a custom grace_period_seconds value is passed correctly"""
        mock_cli = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.creation_timestamp = datetime(
            2026, 1, 1, tzinfo=timezone.utc
        )
        mock_cli.read_namespaced_pod.side_effect = [
            mock_pod,
            ApiException(status=404),
        ]
        mock_cli.delete_namespaced_pod.return_value = None

        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            self.lib_k8s.delete_pod("test-pod", "test-ns", grace_period_seconds=15)

        call_kwargs = mock_cli.delete_namespaced_pod.call_args[1]
        self.assertIsInstance(call_kwargs["body"], client.V1DeleteOptions)
        self.assertEqual(call_kwargs["body"].grace_period_seconds, 15)

    def test_delete_pod_force_already_deleted(self):
        """Verify force delete handles 404 (already deleted) gracefully"""
        mock_cli = MagicMock()
        mock_cli.read_namespaced_pod.side_effect = ApiException(status=404)

        with patch.object(
            KrknKubernetes,
            "cli",
            new_callable=PropertyMock,
            return_value=mock_cli,
        ):
            self.lib_k8s.delete_pod("test-pod", "test-ns", grace_period_seconds=0)

        mock_cli.delete_namespaced_pod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
