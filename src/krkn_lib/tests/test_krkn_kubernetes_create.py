"""
Functional tests for KrknKubernetes create and deployment operations.

These tests require an active Kubernetes cluster (kind, minikube, etc.)
and will perform actual operations against the cluster.

Run with: python -m unittest src.krkn_lib.tests.test_krkn_kubernetes_create

Assisted By: Claude Code
"""

import logging
import tempfile
import unittest
import time
import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes.client import ApiException

from krkn_lib.tests import BaseTest


class KrknKubernetesTestsCreate(BaseTest):
    """Test create operations on Kubernetes cluster."""
    def test_create_pod(self):
        """Test creating a pod and waiting for it to be running."""
        namespace = "test-cp-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        template_str = self.template_to_pod("fedtools", namespace=namespace)
        body = yaml.safe_load(template_str)
        self.lib_k8s.create_pod(body, namespace)
        try:
            self.wait_pod("fedtools", namespace=namespace)
        except Exception:
            logging.error("failed to create pod")
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put(["fedtools", namespace])

    def test_create_job(self):
        """Test creating a Kubernetes job."""
        namespace = "test-ns-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        template = self.template_to_job(name, namespace)
        body = yaml.safe_load(template)
        self.lib_k8s.create_job(body, namespace)
        try:
            self.lib_k8s.get_job_status(name, namespace)
        except ApiException:
            logging.error(
                "job {0} in namespace {1} not found, failing.".format(
                    name, namespace
                )
            )
            self.assertTrue(False)
        self.lib_k8s.delete_namespace(namespace)

    def test_apply_yaml(self):
        """Test applying YAML configuration from file."""
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            environment = Environment(loader=FileSystemLoader("src/testdata/"))
            template = environment.get_template("namespace_template.j2")
            content = template.render(name=namespace, labels=[])
            with tempfile.NamedTemporaryFile(mode="w") as file:
                file.write(content)
                file.flush()
                self.lib_k8s.apply_yaml(file.name, "")
            status = self.lib_k8s.get_namespace_status(namespace)
            self.assertEqual(status, "Active")
        except Exception as e:
            logging.error("exception in test {0}".format(str(e)))
            self.assertTrue(False)
        finally:
            self.lib_k8s.delete_namespace(namespace)

    def test_create_configmap(self):
        """Test creating a ConfigMap."""
        namespace = "test-cm-" + self.get_random_string(10)
        cm_name = "test-configmap-" + self.get_random_string(10)

        self.deploy_namespace(namespace, [])

        try:
            # Create ConfigMap directly using Kubernetes API
            configmap_body = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": cm_name},
                "data": {"test_key": "test_value"},
            }

            self.lib_k8s.cli.create_namespaced_config_map(
                namespace=namespace, body=configmap_body
            )

            time.sleep(2)

            # Verify ConfigMap exists
            cm = self.lib_k8s.cli.read_namespaced_config_map(cm_name, namespace)
            self.assertIsNotNone(cm)
            self.assertEqual(cm.metadata.name, cm_name)
        except Exception as e:
            logging.error(f"Failed to create ConfigMap: {e}")
            self.assertTrue(False)
        finally:
            self.lib_k8s.delete_namespace(namespace)

    def test_create_token_for_namespace(self):
        """Test creating service account token."""
        token = self.lib_k8s.create_token_for_sa("default", "default")
        self.assertIsNotNone(token)

        not_token = self.lib_k8s.create_token_for_sa(
            "do_not_exists", "do_not_exists"
        )
        self.assertIsNone(not_token)

    def test_pod_ready_status(self):
        """Test checking pod Ready status."""
        namespace = "test-ready-" + self.get_random_string(10)
        pod_name = "ready-test-pod"

        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace, name=pod_name)

        try:
            # Wait for pod to be running using BaseTest helper
            self.wait_pod(pod_name, namespace, timeout=120)

            # Verify pod exists and is running
            pod = self.lib_k8s.read_pod(pod_name, namespace)
            self.assertIsNotNone(pod)

            # Check pod status is Running
            self.assertEqual(pod.status.phase, "Running")

            # Check pod has conditions
            self.assertIsNotNone(pod.status.conditions)
            self.assertGreater(len(pod.status.conditions), 0)

            # Verify at least one condition exists
            condition_types = [c.type for c in pod.status.conditions]
            self.assertIn("Ready", condition_types)
        finally:
            self.pod_delete_queue.put([pod_name, namespace])


if __name__ == "__main__":
    unittest.main()
