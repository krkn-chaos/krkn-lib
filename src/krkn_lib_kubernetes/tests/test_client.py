import os.path
import tempfile
import time
import unittest

import uuid

import yaml
import logging
import random
import re
from kubernetes.client import ApiException
from krkn_lib_kubernetes import ApiRequestException
from jinja2 import Environment, FileSystemLoader

from krkn_lib_kubernetes.tests.base_test import BaseTest


class KrknLibKubernetesTests(BaseTest):
    def test_exec_command(self):
        namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        self.wait_pod("fedtools", namespace=namespace)

        try:
            cmd = ["-br", "addr", "show"]
            result = self.lib_k8s.exec_cmd_in_pod(
                cmd,
                "fedtools",
                namespace,
                base_command="ip",
            )
            self.assertRegex(result, r"\d+\.\d+\.\d+\.\d+")

            # run command in bash
            cmd = ["ls -al /"]
            result = self.lib_k8s.exec_cmd_in_pod(cmd, "fedtools", namespace)
            self.assertRegex(result, r"etc")
            self.assertRegex(result, r"root")
            self.assertRegex(result, r"bin")
        except Exception as exc:
            assert False, f"command execution raised an exception {exc}"

    def test_get_cluster_version(self):
        # TODO
        result = self.lib_k8s.get_clusterversion_string()
        self.assertIsNotNone(result)

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
            "kubernetes.io/metadata.name=donotexist"
        )
        self.assertTrue(len(result) == 0)

    def test_get_namespace_status(self):
        # happy path
        result = self.lib_k8s.get_namespace_status("default")
        self.assertEqual("Active", result)
        # error
        with self.assertRaises(ApiRequestException):
            self.lib_k8s.get_namespace_status("not-exists")

    def test_delete_namespace(self):
        name = "test-ns-" + self.get_random_string(10)
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

    def test_check_namespaces(self):
        i = 0
        namespaces = []
        labels = []
        labels.append("check-namespace-" + self.get_random_string(10))
        labels.append("check-namespace-" + self.get_random_string(10))
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
        self.delete_fake_kraken()

    def test_list_pods(self):
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fake_kraken(namespace=namespace)
        pods = self.lib_k8s.list_pods(namespace=namespace)
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)
        self.lib_k8s.delete_namespace(namespace)
        self.delete_fake_kraken(namespace=namespace)

    def test_get_all_pods(self):
        namespace = "test-" + self.get_random_string(10)
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
        self.assertEqual(results[0][0], "kraken-deployment")
        self.assertEqual(results[0][1], namespace)
        self.lib_k8s.delete_namespace(namespace)
        self.delete_fake_kraken(namespace=namespace)

    def test_delete_pod(self):
        namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        self.wait_pod("fedtools", namespace=namespace)
        self.lib_k8s.delete_pod("fedtools", namespace=namespace)
        with self.assertRaises(ApiException):
            self.lib_k8s.read_pod("fedtools", namespace=namespace)

    def test_create_pod(self):
        namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        template_str = self.template_to_pod("fedtools", namespace=namespace)
        body = yaml.safe_load(template_str)
        self.lib_k8s.create_pod(body, namespace)
        try:
            self.wait_pod("fedtools", namespace=namespace)
        except Exception:
            logging.error("failed to create pod")
            self.assertTrue(False)

    def test_read_pod(self):
        namespace = "test-ns-" + self.get_random_string(10)
        name = "test-name-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace, name=name)
        try:
            pod = self.lib_k8s.read_pod(name, namespace)
            self.assertEqual(pod.metadata.name, name)
            self.assertEqual(pod.metadata.namespace, namespace)
        except Exception:
            logging.error(
                "failed to read pod {0} in namespace {1}".format(
                    name, namespace
                )
            )
            self.assertTrue(False)

    def test_get_pod_log(self):
        namespace = "test-ns-" + self.get_random_string(10)
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

    def test_get_containers_in_pod(self):
        namespace = "test-ns-" + self.get_random_string(10)
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

    def test_create_job(self):
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

    def test_get_job_status(self):
        namespace = "test-ns-" + self.get_random_string(10)
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

    def test_monitor_nodes(self):
        try:
            nodeStatus = self.lib_k8s.monitor_nodes()
            self.assertIsNotNone(nodeStatus)
            self.assertTrue(len(nodeStatus) >= 1)
            self.assertTrue(nodeStatus[0])
            self.assertTrue(len(nodeStatus[1]) == 0)
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
            bad_namespace, random_label=None, node_name="do_not_exist"
        )
        status = self.lib_k8s.monitor_namespace(namespace=bad_namespace)
        # sleeping for a while just in case
        time.sleep(5)
        self.assertFalse(status[0])
        self.assertTrue(len(status[1]) == 1)
        self.assertTrue(status[1][0] == "kraken-deployment")
        self.delete_fake_kraken(namespace=bad_namespace)

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
            bad_namespace, random_label=None, node_name="do_not_exist"
        )
        status = self.lib_k8s.monitor_component(
            iteration=1, component_namespace=bad_namespace
        )
        # sleeping for a while just in case
        time.sleep(5)
        self.assertFalse(status[0])
        self.assertTrue(len(status[1]) == 1)
        self.assertTrue(status[1][0] == "kraken-deployment")
        self.delete_fake_kraken(namespace=bad_namespace)

    def test_apply_yaml(self):
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
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)

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

    def test_check_if_pod_exists(self):
        try:
            namespace = "test-ns-" + self.get_random_string(10)
            name = "test-name-" + self.get_random_string(10)
            self.deploy_namespace(namespace, [])
            self.deploy_fedtools(namespace=namespace, name=name)
            self.wait_pod(name, namespace, timeout=120)
            self.assertTrue(self.lib_k8s.check_if_pod_exists(name, namespace))
            self.assertFalse(
                self.lib_k8s.check_if_pod_exists(
                    "do_not_exist", "do_not_exist"
                )
            )
        except Exception as e:
            logging.error("test raised exception {0}".format(str(e)))
            self.assertTrue(False)

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

    def test_find_kraken_node(self):
        namespace = "test-ns-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        nodes = self.lib_k8s.list_nodes()
        random_node_index = random.randint(0, len(nodes) - 1)
        self.deploy_fake_kraken(
            namespace=namespace, node_name=nodes[random_node_index]
        )
        result = self.lib_k8s.find_kraken_node()
        self.assertEqual(nodes[random_node_index], result)
        self.delete_fake_kraken(namespace)

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
        nodes = self.lib_k8s.get_nodes_infos()
        for node in nodes:
            self.assertTrue(node.node_type)
            self.assertTrue(node.architecture)
            self.assertTrue(node.instance_type)
            self.assertTrue(node.os_version)
            self.assertTrue(node.kernel_version)
            self.assertTrue(node.kubelet_version)

    def test_get_cluster_infrastructure(self):
        resp = self.lib_k8s.get_cluster_infrastructure()
        self.assertTrue(resp)
        self.assertEqual(resp, "Unknown")

    def test_get_cluster_network_plugins(self):
        resp = self.lib_k8s.get_cluster_network_plugins()
        self.assertTrue(len(resp) > 0)
        self.assertEqual(resp[0], "Unknown")

    def test_download_folder_from_pod_as_archive(self):
        test_workdir = os.getenv("TEST_WORKDIR")
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        count = 0
        MAX_RETRIES = 5
        while not self.lib_k8s.is_pod_running("fedtools", namespace):
            if count > MAX_RETRIES:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue

        archive = self.lib_k8s.archive_and_get_path_from_pod(
            "fedtools",
            "fedtools",
            namespace,
            "/tmp",
            "/etc",
            str(uuid.uuid1()),
            archive_part_size=10000,
            download_path=test_workdir,
        )
        for file in archive:
            self.assertTrue(os.path.isfile(file[1]))
            self.assertTrue(os.stat(file[1]).st_size > 0)

    # NEEDFIX
    def test_exists_path_in_pod(self):
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        count = 0
        MAX_RETRIES = 5
        while not self.lib_k8s.is_pod_running("fedtools", namespace):
            if count > MAX_RETRIES:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue

        self.assertTrue(
            self.lib_k8s.path_exists_in_pod(
                "fedtools", "fedtools", namespace, "/home"
            )
        )

        self.assertFalse(
            self.lib_k8s.path_exists_in_pod(
                "fedtools", "fedtools", namespace, "/does_not_exist"
            )
        )

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


if __name__ == "__main__":
    unittest.main()
