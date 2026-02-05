import logging
import time
import unittest

from kubernetes.client import ApiException

from krkn_lib.k8s import ApiRequestException
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


if __name__ == "__main__":
    unittest.main()
