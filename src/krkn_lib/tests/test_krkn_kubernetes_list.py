import logging
import unittest

from krkn_lib.tests import BaseTest


class KrknKubernetesTestsList(BaseTest):
    def test_list_all_namespaces(self):
        # test list all namespaces
        result = self.lib_k8s.list_all_namespaces()
        result_count = 0
        for r in result:
            for _ in r.items:
                result_count += 1
        print("result type" + str(result_count))
        self.assertTrue(result_count > 1)
        # test filter by label
        result = self.lib_k8s.list_all_namespaces(
            "kubernetes.io/metadata.name=default"
        )

        self.assertTrue(len(result) == 1)
        namespace_names = []
        for r in result:
            for item in r.items:
                namespace_names.append(item.metadata.name)
        self.assertIn("default", namespace_names)

        # test unexisting filter
        result = self.lib_k8s.list_namespaces(
            "k8s.io/metadata.name=donotexist"
        )
        self.assertTrue(len(result) == 0)

    def test_list_namespaces(self):
        # test all namespaces
        result = self.lib_k8s.list_namespaces()
        self.assertTrue(len(result) > 1)
        # test filter by label
        result = self.lib_k8s.list_namespaces(
            "kubernetes.io/metadata.name=default"
        )
        self.assertTrue(len(result) == 1)
        self.assertIn("default", result)

        # test unexisting filter
        result = self.lib_k8s.list_namespaces(
            "k8s.io/metadata.name=donotexist"
        )
        self.assertTrue(len(result) == 0)

    def test_list_nodes(self):
        nodes = self.lib_k8s.list_nodes()
        self.assertTrue(len(nodes) >= 1)
        nodes = self.lib_k8s.list_nodes("donot=exists")
        self.assertTrue(len(nodes) == 0)

    def test_list_killable_nodes(self):
        nodes = self.lib_k8s.list_nodes()
        self.assertTrue(len(nodes) > 0)
        self.deploy_fake_kraken(node_name=nodes[0])
        killable_nodes = self.lib_k8s.list_killable_nodes()
        self.assertNotIn(nodes[0], killable_nodes)
        self.pod_delete_queue.put(["krkn-deployment", "default"])

    def test_list_pods(self):
        namespace = "test-lp" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fake_kraken(namespace=namespace)

        # Test basic pod listing
        pods = self.lib_k8s.list_pods(namespace=namespace)
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)

        self.wait_pod(pods[0], namespace)

        pods = self.lib_k8s.list_pods(
            namespace=namespace, field_selector="status.phase=Running"
        )
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)

        pods = self.lib_k8s.list_pods(
            namespace=namespace, field_selector="status.phase=Terminating"
        )
        self.assertTrue(len(pods) == 0)

        # Test with exclude_label - should not exclude
        # any pods (no matching labels)
        pods = self.lib_k8s.list_pods(
            namespace=namespace, exclude_label="skip=true"
        )
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)

        # Add a pod with the exclude label leveraging random_label will set
        # random=skip
        self.deploy_fake_kraken(
            namespace=namespace, name="kraken-exclude", random_label="skip"
        )

        # Test listing all pods without exclusion
        pods = self.lib_k8s.list_pods(namespace=namespace)
        self.assertTrue(len(pods) == 2)
        self.assertIn("kraken-deployment", pods)
        self.assertIn("kraken-exclude", pods)

        # Test with exclude_label - should exclude the labeled pod
        pods = self.lib_k8s.list_pods(
            namespace=namespace, exclude_label="random=skip"
        )
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)
        self.assertNotIn("kraken-exclude", pods)

        # Clean up
        self.pod_delete_queue.put(["kraken-deployment", namespace])
        self.pod_delete_queue.put(["kraken-exclude", namespace])

    def test_list_ready_nodes(self):
        try:
            ready_nodes = self.lib_k8s.list_ready_nodes()
            nodes = self.lib_k8s.list_nodes()
            result = set(ready_nodes) - set(nodes)
            self.assertEqual(len(result), 0)
            result = self.lib_k8s.list_ready_nodes(
                label_selector="do_not_exist"
            )
            self.assertEqual(len(result), 0)
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)

    def test_list_namespaces_by_regex(self):
        namespace_1 = (
            self.get_random_string(3) + "-test-ns-" + self.get_random_string(3)
        )
        namespace_2 = (
            self.get_random_string(3) + "-test-ns-" + self.get_random_string(3)
        )
        self.deploy_namespace(namespace_1, labels=[])
        self.deploy_namespace(namespace_2, labels=[])

        filtered_ns_ok = self.lib_k8s.list_namespaces_by_regex(
            r"^[a-z0-9]{3}\-test\-ns\-[a-z0-9]{3}$"
        )

        filtered_ns_fail = self.lib_k8s.list_namespaces_by_regex(
            r"^[a-z0-9]{4}\-test\-ns\-[a-z0-9]{4}$"
        )

        try:
            filtered_no_regex = self.lib_k8s.list_namespaces_by_regex(
                "1234_I'm no regex_567!"
            )
            self.assertEqual(len(filtered_no_regex), 0)
        except Exception:
            self.fail("method raised exception with" "invalid regex")

        self.lib_k8s.delete_namespace(namespace_1)
        self.lib_k8s.delete_namespace(namespace_2)
        self.assertEqual(len(filtered_ns_ok), 2)
        self.assertEqual(len(filtered_ns_fail), 0)

    def test_list_schedulable_nodes(self):
        schedulable_nodes = self.lib_k8s.list_schedulable_nodes()
        self.assertGreater(len(schedulable_nodes), 0)
        schedulable_nodes_empty_selector = self.lib_k8s.list_schedulable_nodes(
            label_selector=""
        )
        self.assertEqual(
            len(schedulable_nodes), len(schedulable_nodes_empty_selector)
        )

    def test_list_pod_network_interfaces(self):
        namespace = "test-cid-" + self.get_random_string(10)
        base_pod_name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=base_pod_name)
        self.wait_pod(base_pod_name, namespace)

        nics = self.lib_k8s.list_pod_network_interfaces(
            base_pod_name, namespace
        )
        self.assertGreater(len(nics), 0)
        self.assertTrue("eth0" in nics)


if __name__ == "__main__":
    unittest.main()
