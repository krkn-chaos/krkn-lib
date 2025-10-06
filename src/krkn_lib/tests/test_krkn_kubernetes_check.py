import logging
import time
import unittest

from krkn_lib.tests import BaseTest
from krkn_lib.k8s import ApiRequestException
from kubernetes.client import ApiException


class KrknKubernetesTestsCheck(BaseTest):
    def test_check_namespaces(self):
        i = 0
        namespaces = []
        labels = [
            "check-namespace-" + self.get_random_string(10),
            "check-namespace-" + self.get_random_string(10),
        ]
        common_label = "check-namespace-" + self.get_random_string(10)
        while i < 5:
            name = "test-ns-" + self.get_random_string(10)
            self.deploy_namespace(
                name,
                [
                    {"name": "common", "label": common_label},
                    {"name": "test", "label": labels[i % 2]},
                ],
            )
            namespaces.append(name)
            i = i + 1

        result_1 = self.lib_k8s.check_namespaces(namespaces)

        result_2 = self.lib_k8s.check_namespaces(
            namespaces, "common=%s" % common_label
        )

        total_nofilter = set(result_1) - set(namespaces)
        total_filter = set(result_2) - set(namespaces)

        # checks that the list of namespaces equals
        # the list returned without any label filter
        self.assertTrue(len(total_nofilter) == 0)
        # checks that the list of namespaces equals
        # the list returned with the common label as a filter
        self.assertTrue(len(total_filter) == 0)

        # checks that the function raises an error if
        # some of the namespaces passed does not satisfy
        # the label passed as parameter
        with self.assertRaises(ApiRequestException):
            self.lib_k8s.check_namespaces(namespaces, "test=%s" % labels[0])
        # checks that the function raises an error if
        # some of the namespaces passed does not satisfy
        # the label passed as parameter
        with self.assertRaises(ApiRequestException):
            self.lib_k8s.check_namespaces(namespaces, "test=%s" % labels[1])

        for namespace in namespaces:
            self.lib_k8s.delete_namespace(namespace)

    def test_monitor_nodes(self):
        try:
            node_status = self.lib_k8s.monitor_nodes()
            self.assertIsNotNone(node_status)
            self.assertTrue(len(node_status) >= 1)
            self.assertTrue(node_status[0])
            self.assertTrue(len(node_status[1]) == 0)
        except ApiException:
            logging.error("failed to retrieve node status, failing.")
            self.assertTrue(False)

    def test_monitor_namespace(self):
        good_namespace = "test-ns-" + self.get_random_string(10)
        good_name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(good_namespace, [])
        self.deploy_fedtools(namespace=good_namespace, name=good_name)
        self.wait_pod(good_name, namespace=good_namespace)
        status = self.lib_k8s.monitor_namespace(namespace=good_namespace)
        self.assertTrue(status[0])
        self.assertTrue(len(status[1]) == 0)

        bad_namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(bad_namespace, [])
        self.deploy_fake_kraken(
            namespace=bad_namespace,
            random_label=None,
            node_name="do_not_exist",
        )
        status = self.lib_k8s.monitor_namespace(namespace=bad_namespace)
        # sleeping for a while just in case
        time.sleep(5)
        self.assertFalse(status[0])
        self.assertTrue(len(status[1]) == 1)
        self.assertTrue(status[1][0] == "kraken-deployment")
        self.pod_delete_queue.put(["kraken-deployment", bad_namespace])
        self.pod_delete_queue.put([good_name, good_namespace])

    def test_monitor_component(self):
        good_namespace = "test-ns-" + self.get_random_string(10)
        good_name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(good_namespace, [])
        self.deploy_fedtools(namespace=good_namespace, name=good_name)
        self.wait_pod(good_name, namespace=good_namespace)
        status = self.lib_k8s.monitor_component(
            iteration=0, component_namespace=good_namespace
        )
        self.assertTrue(status[0])
        self.assertTrue(len(status[1]) == 0)

        bad_namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(bad_namespace, [])
        self.deploy_fake_kraken(
            namespace=bad_namespace,
            random_label=None,
            node_name="do_not_exist",
        )
        status = self.lib_k8s.monitor_component(
            iteration=1, component_namespace=bad_namespace
        )
        # sleeping for a while just in case
        time.sleep(5)
        self.assertFalse(status[0])
        self.assertTrue(len(status[1]) == 1)
        self.assertTrue(status[1][0] == "kraken-deployment")
        self.pod_delete_queue.put(["kraken-deployment", bad_namespace])
        self.pod_delete_queue.put([good_name, good_namespace])

    def test_check_if_namespace_exists(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            self.deploy_namespace(namespace, [])
            self.assertTrue(self.lib_k8s.check_if_namespace_exists(namespace))
            self.assertFalse(
                self.lib_k8s.check_if_namespace_exists(
                    self.get_random_string(10)
                )
            )
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)
        self.lib_k8s.delete_namespace(namespace)

    def test_check_if_pod_exists(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            name = "test-name-" + self.get_random_string(10)
            self.deploy_namespace(namespace, [])
            self.deploy_fedtools(namespace=namespace, name=name)
            self.wait_pod(name, namespace, timeout=240)
            self.assertTrue(self.lib_k8s.check_if_pod_exists(name, namespace))
            self.assertFalse(
                self.lib_k8s.check_if_pod_exists(
                    "do_not_exist", "do_not_exist"
                )
            )
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put([name, namespace])

    def test_check_if_pvc_exists(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            storage_class = "sc-" + self.get_random_string(10)
            pv_name = "pv-" + self.get_random_string(10)
            pvc_name = "pvc-" + self.get_random_string(10)
            self.deploy_namespace(namespace, [])
            self.deploy_persistent_volume(pv_name, storage_class, namespace)
            self.deploy_persistent_volume_claim(
                pvc_name, storage_class, namespace
            )
            self.assertTrue(
                self.lib_k8s.check_if_pvc_exists(pvc_name, namespace)
            )
            self.assertFalse(
                self.lib_k8s.check_if_pvc_exists(
                    "do_not_exist", "do_not_exist"
                )
            )
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)
        self.lib_k8s.delete_namespace(namespace)

    def test_is_pod_running(self):
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        count = 0
        while self.lib_k8s.is_pod_running("fedtools", namespace):
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        result = self.lib_k8s.is_pod_running("do_not_exist", "do_not_exist")
        self.assertFalse(result)
        self.pod_delete_queue.put(["fedtools", namespace])

    def test_is_kubernetes(self):
        self.assertTrue(self.lib_k8s.is_kubernetes())

    def test_is_terminating(self):
        namespace = "test-ns-" + self.get_random_string(10)
        terminated = "terminated-" + self.get_random_string(10)
        not_terminated = "not-terminated-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(terminated, namespace, 0)
        self.background_delete_pod(terminated, namespace)

        time.sleep(1)
        self.assertTrue(self.lib_k8s.is_pod_terminating(terminated, namespace))
        self.deploy_delayed_readiness_pod(not_terminated, namespace, 10)
        self.assertFalse(
            self.lib_k8s.is_pod_terminating(not_terminated, namespace)
        )
        self.pod_delete_queue.put([not_terminated, namespace])

    def test_service_exists(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_service(name, namespace)
        self.assertTrue(self.lib_k8s.service_exists(name, namespace))
        self.assertFalse(
            self.lib_k8s.service_exists("doesnotexist", "doesnotexist")
        )
        self.lib_k8s.delete_namespace(namespace)


if __name__ == "__main__":
    unittest.main()
