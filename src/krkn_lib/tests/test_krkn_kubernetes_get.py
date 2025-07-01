import logging
import random
import re
import time
import os
import unittest

from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.tests import BaseTest
from kubernetes import config
from krkn_lib.k8s import ApiRequestException, KrknKubernetes
from kubernetes.client import ApiException


class KrknKubernetesTestsGet(BaseTest):
    def test_get_version(self):
        try:
            response = self.lib_k8s.get_version()
            self.assertGreater(float(response), 0)
        except Exception as e:
            self.fail(f"exception on getting kubectl version execution: {e}")

    def test_get_kubeconfig_path(self):
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
        if "~" in kubeconfig_path:
            kubeconfig_path = os.path.expanduser(kubeconfig_path)

        krknkubernetes_path = KrknKubernetes(kubeconfig_path=kubeconfig_path)

        self.assertEqual(
            krknkubernetes_path.get_kubeconfig_path(), kubeconfig_path
        )

    def test_get_namespace_status(self):
        # happy path
        result = self.lib_k8s.get_namespace_status("default")
        self.assertEqual("Active", result)
        # error
        with self.assertRaises(ApiRequestException):
            self.lib_k8s.get_namespace_status("not-exists")

    def test_get_all_pods(self):
        namespace = "test-ap" + self.get_random_string(10)
        random_label = self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fake_kraken(random_label=random_label, namespace=namespace)
        # test without filter
        results = self.lib_k8s.get_all_pods()
        etcd_found = False
        for result in results:
            if re.match(r"^etcd", result[0]):
                etcd_found = True
        self.assertTrue(etcd_found)
        # test with label_selector filter
        results = self.lib_k8s.get_all_pods("random=%s" % random_label)
        self.assertTrue(len(results) == 1)
        self.assertEqual(results[0][1], namespace)
        self.assertEqual(results[0][0], "kraken-deployment")
        self.wait_pod("kraken-deployment", namespace)
        results = self.lib_k8s.get_all_pods(
            "random=%s" % random_label, field_selector="status.phase=Running"
        )
        print("resuls" + str(results))
        self.assertTrue(len(results) == 1)
        self.assertEqual(results[0][1], namespace)
        self.assertEqual(results[0][0], "kraken-deployment")

        results = self.lib_k8s.get_all_pods(
            field_selector="status.phase=Running"
        )
        self.assertTrue(len(results) >= 1)

        self.pod_delete_queue.put(["kraken-deployment", namespace])

    def test_get_pod_log(self):
        namespace = "test-pl-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=name)
        self.wait_pod(name, namespace)
        try:
            logs = self.lib_k8s.get_pod_log(name, namespace)
            response = logs.data.decode("utf-8")
            self.assertTrue("Linux" in response)
        except Exception as e:
            logging.error(
                "failed to get logs due to an exception: %s" % str(e)
            )
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put([name, namespace])

    def test_get_containers_in_pod(self):
        namespace = "test-cip-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=name)
        self.wait_pod(name, namespace)
        try:
            containers = self.lib_k8s.get_containers_in_pod(name, namespace)
            self.assertTrue(len(containers) == 1)
            self.assertTrue(containers[0] == name)
        except Exception:
            logging.error(
                "failed to get containers in pod {0} namespace {1}".format(
                    name, namespace
                )
            )
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put([name, namespace])

    def test_get_job_status(self):
        namespace = "test-js-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_job(name, namespace)
        max_retries = 30
        sleep = 2
        counter = 0
        status = None
        while True:
            if counter > max_retries:
                logging.error("Job not active after 60 seconds, failing")
                self.assertTrue(False)
            try:
                status = self.lib_k8s.get_job_status(name, namespace)
                if status is not None:
                    break
                time.sleep(sleep)
                counter = counter + 1

            except ApiException:
                continue
        self.assertTrue(status.metadata.name == name)
        self.lib_k8s.delete_namespace(namespace)

    def test_get_pod_info(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            name = "test-name-" + self.get_random_string(10)
            self.deploy_namespace(namespace, [])
            self.deploy_fedtools(namespace=namespace, name=name)
            self.wait_pod(name, namespace)
            info = self.lib_k8s.get_pod_info(name, namespace)
            self.assertEqual(info.namespace, namespace)
            self.assertEqual(info.name, name)
            self.assertIsNotNone(info.podIP)
            self.assertIsNotNone(info.nodeName)
            self.assertIsNotNone(info.containers)

            info = self.lib_k8s.get_pod_info("test1", namespace)
            self.assertIsNone(info)
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put([name, namespace])

    def test_get_pvc_info(self):
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
            info = self.lib_k8s.get_pvc_info(pvc_name, namespace)
            self.assertIsNotNone(info)
            self.assertEqual(info.name, pvc_name)
            self.assertEqual(info.namespace, namespace)
            self.assertEqual(info.volumeName, pv_name)

            info = self.lib_k8s.get_pvc_info("do_not_exist", "do_not_exist")
            self.assertIsNone(info)

        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)
        self.lib_k8s.delete_namespace(namespace)

    def test_get_node_resource_version(self):
        try:
            nodes = self.lib_k8s.list_nodes()
            random_node_index = random.randint(0, len(nodes) - 1)
            node_resource_version = self.lib_k8s.get_node_resource_version(
                nodes[random_node_index]
            )
            self.assertIsNotNone(node_resource_version)
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)

    def test_get_all_kubernetes_object_count(self):
        objs = self.lib_k8s.get_all_kubernetes_object_count(
            ["Namespace", "Ingress", "ConfigMap", "Unknown"]
        )
        self.assertTrue("Namespace" in objs.keys())
        self.assertTrue("Ingress" in objs.keys())
        self.assertTrue("ConfigMap" in objs.keys())
        self.assertFalse("Unknown" in objs.keys())

    def test_get_kubernetes_core_objects_count(self):
        objs = self.lib_k8s.get_kubernetes_core_objects_count(
            "v1",
            [
                "Namespace",
                "Ingress",
                "ConfigMap",
            ],
        )
        self.assertTrue("Namespace" in objs.keys())
        self.assertTrue("ConfigMap" in objs.keys())
        self.assertFalse("Ingress" in objs.keys())

    def test_get_kubernetes_custom_objects_count(self):
        objs = self.lib_k8s.get_kubernetes_custom_objects_count(
            ["Namespace", "Ingress", "ConfigMap", "Unknown"]
        )
        self.assertFalse("Namespace" in objs.keys())
        self.assertFalse("ConfigMap" in objs.keys())
        self.assertTrue("Ingress" in objs.keys())

    def test_get_nodes_infos(self):
        telemetry = ChaosRunTelemetry()
        nodes, _ = self.lib_k8s.get_nodes_infos()
        for node in nodes:
            self.assertTrue(node.count > 0)
            self.assertTrue(node.nodes_type)
            self.assertTrue(node.architecture)
            self.assertTrue(node.instance_type)
            self.assertTrue(node.os_version)
            self.assertTrue(node.kernel_version)
            self.assertTrue(node.kubelet_version)
            telemetry.node_summary_infos.append(node)
        try:
            _ = telemetry.to_json()
        except Exception:
            self.fail("failed to deserialize NodeInfo")

    def test_get_node_cpu_count(self):
        nodes = self.lib_k8s.list_nodes()
        node_cpus = self.lib_k8s.get_node_cpu_count(nodes[0])
        self.assertGreater(node_cpus, 0)

        node_cpus = self.lib_k8s.get_node_cpu_count("does_not_exist")
        self.assertEqual(node_cpus, 0)

    def test_get_node_resources_infos(self):
        nodes = self.lib_k8s.list_nodes()
        infos = self.lib_k8s.get_node_resources_info(nodes[0])
        self.assertGreater(infos.disk_space, 0)
        self.assertGreater(infos.memory, 0)
        self.assertGreater(infos.cpu, 0)

    def test_get_node_ip(self):
        nodes = self.lib_k8s.list_nodes()
        ip_address = self.lib_k8s.get_node_ip(nodes[0])
        self.assertIsNotNone(ip_address)
        with self.assertRaises(Exception):
            ip_address = self.lib_k8s.get_node_ip("not_existing")

    def test_get_pod_container_id(self):
        namespace = "test-cid-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=name)
        self.wait_pod(name, namespace)
        container_ids = self.lib_k8s.get_container_ids(
            pod_name=name, namespace=namespace
        )
        self.assertTrue(len(container_ids) > 0)
        container_ids = self.lib_k8s.get_container_ids(
            pod_name="do_not_exists", namespace="do_not_exists"
        )
        self.assertTrue(len(container_ids) == 0)

    def test_get_pod_pids(self):
        namespace = "test-cid-" + self.get_random_string(10)
        base_pod_name = "test-name-" + self.get_random_string(10)
        target_pod_name = "test-name-" + self.get_random_string(10)

        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=base_pod_name)
        self.deploy_fedtools(namespace=namespace, name=target_pod_name)

        self.wait_pod(base_pod_name, namespace)
        self.wait_pod(target_pod_name, namespace)

        container_id = self.lib_k8s.get_container_ids(
            pod_name=target_pod_name, namespace=namespace
        )
        pids = self.lib_k8s.get_pod_pids(
            base_pod_name,
            namespace,
            base_pod_name,
            target_pod_name,
            namespace,
            container_id[0],
        )

        self.assertIsNotNone(pids)
        self.assertTrue(isinstance(pids, list))
        self.assertTrue(len(pids) > 0)

        pids = self.lib_k8s.get_pod_pids(
            base_pod_name,
            namespace,
            base_pod_name,
            target_pod_name,
            namespace,
            "does_not_exist",
        )
        self.assertIsNone(pids)

        with self.assertRaises(Exception):
            _ = self.lib_k8s.get_pod_pids(
                "does_not_exist",
                namespace,
                base_pod_name,
                target_pod_name,
                namespace,
                container_id[0],
            )

        with self.assertRaises(Exception):
            _ = self.lib_k8s.get_pod_pids(
                base_pod_name,
                namespace,
                base_pod_name,
                "does_not_exist",
                namespace,
                container_id[0],
            )

        with self.assertRaises(Exception):
            _ = self.lib_k8s.get_pod_pids(
                base_pod_name,
                namespace,
                "does_not_exist",
                target_pod_name,
                namespace,
                container_id[0],
            )


if __name__ == "__main__":
    unittest.main()
