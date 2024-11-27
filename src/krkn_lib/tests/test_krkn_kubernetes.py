import datetime
import logging
import os
import random
import re
import tempfile
import time
import unittest
import uuid

import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes import config
from kubernetes.client import ApiException
from tzlocal import get_localzone

from krkn_lib.k8s import ApiRequestException, KrknKubernetes
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.tests import BaseTest


class KrknKubernetesTests(BaseTest):
    def test_exec_command(self):
        namespace = "test-ns-" + self.get_random_string(10)
        alpine_name = "alpine-" + self.get_random_string(10)
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

        # deploys an alpine container that DOES NOT
        # contain bash, so executing a command without
        # a base command will make the method fallback
        # on sh and NOT fail
        self.depoy_alpine(alpine_name, namespace)

        while not self.lib_k8s.is_pod_running(alpine_name, namespace):
            if count > MAX_RETRIES:
                self.assertFalse(True, "container failed to become ready")
            count += 1
            time.sleep(3)
            continue

        try:
            self.lib_k8s.exec_cmd_in_pod(["ls", "-al"], alpine_name, namespace)
        except Exception:
            self.fail()

    def test_pod_shell(self):
        namespace = "test-ns-" + self.get_random_string(10)
        alpine_name = "alpine-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])

        # test against alpine that runs sh
        self.depoy_alpine(alpine_name, namespace)
        count = 0
        while not self.lib_k8s.is_pod_running(alpine_name, namespace):
            time.sleep(3)
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        shell = self.lib_k8s.get_pod_shell(alpine_name, namespace, "alpine")
        self.assertEqual(shell, "sh")

        # test against fedtools that runs bash
        self.deploy_fedtools(namespace=namespace)
        count = 0
        while not self.lib_k8s.is_pod_running("fedtools", namespace):
            time.sleep(3)
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        shell = self.lib_k8s.get_pod_shell("fedtools", namespace)
        self.assertEqual(shell, "bash")

    def test_exec_command_on_node(self):
        try:
            response = self.lib_k8s.exec_command_on_node(
                "kind-control-plane",
                ["timedatectl", "status"],
                f"test-pod-{time.time()}",
            )
            self.assertTrue(
                "NTP service: active" or "Network time on: yes" in response
            )
        except Exception as e:
            self.fail(f"exception on node command execution: {e}")

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
        with open(kubeconfig_path, mode="r") as kubeconfig:
            kubeconfig_str = kubeconfig.read()

        krknkubernetes_path = KrknKubernetes(kubeconfig_path=kubeconfig_path)
        krknkubernetes_string = KrknKubernetes(
            kubeconfig_string=kubeconfig_str
        )

        self.assertEqual(
            krknkubernetes_path.get_kubeconfig_path(), kubeconfig_path
        )

        test_path = krknkubernetes_string.get_kubeconfig_path()
        self.assertTrue(os.path.exists(test_path))
        with open(test_path, "r") as test:
            test_kubeconfig = test.read()
            self.assertEqual(test_kubeconfig, kubeconfig_str)

    def test_list_all_namespaces(self):
        # test list all namespaces
        result = self.lib_k8s.list_all_namespaces()
        result_count = 0
        for r in result:
            for item in r.items:
                result_count += 1
        print("result type" + str((result_count)))
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

    def test_net_policy(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.create_networkpolicy(name, namespace)
        np = self.lib_k8s.get_namespaced_net_policy(namespace=namespace)
        self.assertTrue(len(np) == 1)
        self.lib_k8s.delete_net_policy(name, namespace)
        np = self.lib_k8s.get_namespaced_net_policy(namespace=namespace)
        self.assertTrue(len(np) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_deployment(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.deploy_deployment(name, namespace)
        deps = self.lib_k8s.get_deployment_ns(namespace=namespace)
        self.assertTrue(len(deps) == 1)
        self.lib_k8s.delete_deployment(name, namespace)
        deps = self.lib_k8s.get_deployment_ns(namespace=namespace)
        self.assertTrue(len(deps) == 0)
        self.lib_k8s.delete_namespace(namespace)

    def test_delete_statefulsets(self):
        namespace = "test-" + self.get_random_string(10)
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

    def test_download_folder_from_pod_as_archive(self):
        workdir_basepath = os.getenv("TEST_WORKDIR")
        workdir = self.get_random_string(10)
        test_workdir = os.path.join(workdir_basepath, workdir)
        os.mkdir(test_workdir)
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
        self.lib_k8s.exec_cmd_in_pod(
            ["mkdir /test"], "fedtools", namespace, "fedtools"
        )
        # create test file
        self.lib_k8s.exec_cmd_in_pod(
            ["dd if=/dev/urandom of=/test/test.bin bs=1024 count=500"],
            "fedtools",
            namespace,
            "fedtools",
        )
        archive = self.lib_k8s.archive_and_get_path_from_pod(
            "fedtools",
            "fedtools",
            namespace,
            "/tmp",
            "/test",
            str(uuid.uuid1()),
            archive_part_size=10000,
            download_path=test_workdir,
        )
        for file in archive:
            self.assertTrue(os.path.isfile(file[1]))
            self.assertTrue(os.stat(file[1]).st_size > 0)

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

    def test_collect_and_parse_cluster_events(self):
        namespace_with_evt = "test-" + self.get_random_string(10)
        pod_name = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace_with_evt, [])
        self.deploy_delayed_readiness_pod(pod_name, namespace_with_evt, 0)
        self.background_delete_pod(pod_name, namespace_with_evt)
        time.sleep(10)
        local_timezone = f"{get_localzone()}"
        now = datetime.datetime.now()
        one_hour_ago = now - datetime.timedelta(hours=1)
        events = self.lib_k8s.collect_and_parse_cluster_events(
            int(one_hour_ago.timestamp()),
            int(now.timestamp()),
            local_timezone,
            namespace=namespace_with_evt,
        )
        self.assertGreater(len(events), 0)

    def test_is_kubernetes(self):
        self.assertTrue(self.lib_k8s.is_kubernetes())

    def test_create_token_for_namespace(self):
        token = self.lib_k8s.create_token_for_sa("default", "default")
        self.assertIsNotNone(token)

        not_token = self.lib_k8s.create_token_for_sa(
            "do_not_exists", "do_not_exists"
        )
        self.assertIsNone(not_token)

    def test_is_terminating(self):
        namespace = "test-ns-" + self.get_random_string(10)
        terminated = "terminated-" + self.get_random_string(10)
        not_terminated = "not-terminated-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(terminated, namespace, 0)
        self.background_delete_pod(terminated, namespace)
        time.sleep(3)
        self.assertTrue(self.lib_k8s.is_pod_terminating(terminated, namespace))
        self.deploy_delayed_readiness_pod(not_terminated, namespace, 10)
        self.assertFalse(
            self.lib_k8s.is_pod_terminating(not_terminated, namespace)
        )

    def test_monitor_pods_by_label_no_pods_affected(self):
        # test no pods affected
        namespace = "test-ns-0-" + self.get_random_string(10)
        delayed_1 = "delayed-0-" + self.get_random_string(10)
        delayed_2 = "delayed-0-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        while not self.lib_k8s.is_pod_running(delayed_1, namespace) or (
            not self.lib_k8s.is_pod_running(delayed_2, namespace)
        ):
            time.sleep(1)
            continue

        monitor_timeout = 2
        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        start_time = time.time()
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        result = pods_thread.join()
        end_time = time.time() - start_time
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # added half second of delay that might be introduced to API
        # calls
        self.assertTrue(monitor_timeout < end_time < monitor_timeout + 0.5)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.recovered), 0)
        self.assertEqual(len(result.unrecovered), 0)

    def test_pods_by_name_and_namespace_pattern_different_names_respawn(
        self,
    ):
        # test pod with different name recovered
        namespace = "test-ns-1-" + self.get_random_string(10)
        delayed_1 = "delayed-1-" + self.get_random_string(10)
        delayed_2 = "delayed-1-" + self.get_random_string(10)
        delayed_respawn = "delayed-1-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        pod_delay = 1
        monitor_timeout = 10
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        pods_and_namespaces = (
            self.lib_k8s.select_pods_by_name_pattern_and_namespace_pattern(
                "^delayed-1-.*", "^test-ns-1-.*"
            )
        )

        pods_thread = (
            self.lib_k8s.monitor_pods_by_name_pattern_and_namespace_pattern(
                "^delayed-1-.*",
                "^test-ns-1-.*",
                pods_and_namespaces,
                monitor_timeout,
            )
        )

        self.background_delete_pod(delayed_1, namespace)
        self.deploy_delayed_readiness_pod(
            delayed_respawn, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.assertIsNone(result.error)
        self.background_delete_pod(delayed_respawn, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.assertEqual(len(result.recovered), 1)
        self.assertEqual(result.recovered[0].pod_name, delayed_respawn)
        self.assertEqual(result.recovered[0].namespace, namespace)
        self.assertTrue(result.recovered[0].pod_readiness_time > 0)
        self.assertTrue(result.recovered[0].pod_rescheduling_time > 0)
        self.assertTrue(result.recovered[0].total_recovery_time >= pod_delay)
        self.assertEqual(len(result.unrecovered), 0)

    def test_pods_by_namespace_pattern_and_label_same_name_respawn(
        self,
    ):
        # not working
        # test pod with same name recovered
        namespace = "test-ns-2-" + self.get_random_string(10)
        delayed_1 = "delayed-2-" + self.get_random_string(10)
        delayed_2 = "delayed-2-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        monitor_timeout = 45
        pod_delay = 1
        pods_and_namespaces = (
            self.lib_k8s.select_pods_by_namespace_pattern_and_label(
                "^test-ns-2-.*", f"test={label}"
            )
        )
        pods_thread = self.lib_k8s.monitor_pods_by_namespace_pattern_and_label(
            "^test-ns-2-.*",
            f"test={label}",
            pods_and_namespaces,
            monitor_timeout,
        )

        self.lib_k8s.delete_pod(delayed_1, namespace)
        self.deploy_delayed_readiness_pod(
            delayed_1, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.recovered), 1)
        self.assertEqual(result.recovered[0].pod_name, delayed_1)
        self.assertEqual(result.recovered[0].namespace, namespace)
        self.assertTrue(result.recovered[0].pod_readiness_time > 0)
        self.assertTrue(result.recovered[0].pod_rescheduling_time > 0)
        self.assertTrue(result.recovered[0].total_recovery_time >= pod_delay)
        self.assertEqual(len(result.unrecovered), 0)

    def test_pods_by_label_respawn_timeout(self):
        # test pod will not recover before the timeout
        namespace = "test-ns-3-" + self.get_random_string(10)
        delayed_1 = "delayed-3-" + self.get_random_string(10)
        delayed_2 = "delayed-3-" + self.get_random_string(10)
        delayed_respawn = "delayed-respawn-3-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)

        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        monitor_timeout = 20
        pod_delay = 30
        # pod with same name recovered

        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}",
            pods_and_namespaces,
            monitor_timeout,
        )

        self.background_delete_pod(delayed_1, namespace)
        self.deploy_delayed_readiness_pod(
            delayed_respawn, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.assertIsNone(result.error)
        self.assertEqual(len(result.unrecovered), 1)
        self.assertEqual(result.unrecovered[0].pod_name, delayed_respawn)
        self.assertEqual(result.unrecovered[0].namespace, namespace)
        self.assertEqual(len(result.recovered), 0)
        self.background_delete_pod(delayed_respawn, namespace)
        self.background_delete_pod(delayed_2, namespace)

    def test_pods_by_label_never_respawn(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        monitor_timeout = 7

        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)

        result = pods_thread.join()
        self.assertIsNotNone(result.error)
        self.background_delete_pod(delayed_2, namespace)

    def test_pods_by_label_multiple_respawn(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        delayed_3 = "delayed-4-" + self.get_random_string(10)
        delayed_respawn_1 = "delayed-4-respawn-" + self.get_random_string(10)
        delayed_respawn_2 = "delayed-4-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_3, namespace, 0, label)
        monitor_timeout = 20
        pod_delay = 2
        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)

        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.background_delete_pod(delayed_3, namespace)
        self.background_delete_pod(delayed_respawn_1, namespace)
        self.background_delete_pod(delayed_respawn_2, namespace)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.unrecovered), 0)
        self.assertEqual(len(result.recovered), 2)
        self.assertTrue(
            delayed_respawn_1 in [p.pod_name for p in result.recovered]
        )
        self.assertTrue(
            delayed_respawn_2 in [p.pod_name for p in result.recovered]
        )

    def test_pods_by_label_multiple_respawn_one_too_late(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        delayed_3 = "delayed-4-" + self.get_random_string(10)
        delayed_respawn_1 = "delayed-4-respawn-" + self.get_random_string(10)
        delayed_respawn_2 = "delayed-4-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_3, namespace, 0, label)
        monitor_timeout = 20
        pod_delay = 2
        pod_too_much_delay = 25
        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)

        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_too_much_delay, label
        )

        result = pods_thread.join()
        self.background_delete_pod(delayed_3, namespace)
        self.background_delete_pod(delayed_respawn_1, namespace)
        self.background_delete_pod(delayed_respawn_2, namespace)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.unrecovered), 1)
        self.assertEqual(len(result.recovered), 1)
        self.assertTrue(
            delayed_respawn_1 in [p.pod_name for p in result.recovered]
        )
        self.assertTrue(
            delayed_respawn_2 in [p.pod_name for p in result.unrecovered]
        )

    def test_pods_by_label_multiple_respawn_one_fails(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        delayed_3 = "delayed-4-" + self.get_random_string(10)
        delayed_respawn_1 = "delayed-4-respawn-" + self.get_random_string(10)
        delayed_respawn_2 = "delayed-4-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_3, namespace, 0, label)
        monitor_timeout = 5
        pod_delay = 2
        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)

        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.background_delete_pod(delayed_3, namespace)
        self.background_delete_pod(delayed_respawn_1, namespace)
        self.background_delete_pod(delayed_respawn_2, namespace)
        self.assertIsNotNone(result.error)
        self.assertEqual(len(result.unrecovered), 0)
        self.assertEqual(len(result.recovered), 0)

    def test_replace_service_selector(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_service(name, namespace)
        self.lib_k8s.replace_service_selector(
            ["app=selector", "test=replace"], name, namespace
        )

        service = self.lib_k8s.cli.read_namespaced_service(name, namespace)
        sanitized_service = self.lib_k8s.api_client.sanitize_for_serialization(
            service
        )
        self.assertEqual(len(sanitized_service["spec"]["selector"].keys()), 2)
        self.assertTrue("app" in sanitized_service["spec"]["selector"])
        self.assertEqual(
            sanitized_service["spec"]["selector"]["app"], "selector"
        )
        self.assertTrue("test" in sanitized_service["spec"]["selector"])
        self.assertEqual(
            sanitized_service["spec"]["selector"]["test"], "replace"
        )

        # test None result with non-existent service

        none_result = self.lib_k8s.replace_service_selector(
            ["app=selector"], "doesnotexist", "doesnotexist"
        )
        self.assertIsNone(none_result)

        # test None result with empty selector list
        none_result = self.lib_k8s.replace_service_selector(
            [], name, namespace
        )
        self.assertIsNone(none_result)

        # test selector validation (bad_selector will be ignored)
        self.lib_k8s.replace_service_selector(
            ["bad_selector", "good=selector"], name, namespace
        )
        service = self.lib_k8s.cli.read_namespaced_service(name, namespace)
        sanitized_service = self.lib_k8s.api_client.sanitize_for_serialization(
            service
        )
        self.assertEqual(len(sanitized_service["spec"]["selector"].keys()), 1)
        self.assertTrue("good" in sanitized_service["spec"]["selector"])
        self.assertEqual(
            sanitized_service["spec"]["selector"]["good"], "selector"
        )

    def test_deploy_undeploy_service_hijacking(self):
        # test deploy
        namespace = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        with open("src/testdata/service_hijacking_test_plan.yaml") as stream:
            plan = yaml.safe_load(stream)

        service_infos = self.lib_k8s.deploy_service_hijacking(
            namespace,
            plan,
            "quay.io/redhat-chaos/krkn-service-hijacking:v0.1.0",
        )

        self.assertIsNotNone(service_infos)
        self.assertIsNotNone(service_infos.config_map_name)
        self.assertIsNotNone(service_infos.selector)
        self.assertIsNotNone(service_infos.pod_name)
        self.assertIsNotNone(service_infos.namespace)

        pod_infos = self.lib_k8s.get_pod_info(
            service_infos.pod_name, service_infos.namespace
        )
        config_map_infos = self.lib_k8s.cli.read_namespaced_config_map(
            service_infos.config_map_name, service_infos.namespace
        )
        self.assertIsNotNone(pod_infos)
        self.assertIsNotNone(config_map_infos)

        # test undeploy
        self.lib_k8s.undeploy_service_hijacking(service_infos)

        pod_infos = self.lib_k8s.get_pod_info(
            service_infos.pod_name, service_infos.namespace
        )

        self.assertIsNone(pod_infos)
        with self.assertRaises(ApiException):
            self.lib_k8s.cli.read_namespaced_config_map(
                service_infos.config_map_name, service_infos.namespace
            )

    def test_service_exists(self):
        namespace = "test-" + self.get_random_string(10)
        name = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_service(name, namespace)
        self.assertTrue(self.lib_k8s.service_exists(name, namespace))
        self.assertFalse(
            self.lib_k8s.service_exists("doesnotexist", "doesnotexist")
        )

    def test_deploy_syn_flood(self):
        namespace = "test-" + self.get_random_string(10)
        syn_flood_pod_name = "krkn-syn-flood-" + self.get_random_string(10)
        nginx_pod_name = "nginx-test-pod-" + self.get_random_string(10)
        service_name = "nginx-test-service" + self.get_random_string(10)
        self.deploy_namespace(namespace, labels=[])
        self.deploy_nginx(
            namespace=namespace,
            pod_name=nginx_pod_name,
            service_name=service_name,
        )
        count = 0
        while not self.lib_k8s.is_pod_running(nginx_pod_name, namespace):
            time.sleep(3)
            if count > 20:
                self.assertTrue(
                    False, "container is not running after 20 retries"
                )
            count += 1
            continue
        test_duration = 10
        self.lib_k8s.deploy_syn_flood(
            pod_name=syn_flood_pod_name,
            namespace=namespace,
            image="quay.io/krkn-chaos/krkn-syn-flood",
            target=service_name,
            target_port=80,
            packet_size=120,
            window_size=64,
            duration=test_duration,
            node_selectors={},
        )

        start = time.time()
        end = 0
        while self.lib_k8s.is_pod_running(syn_flood_pod_name, namespace):
            end = time.time()
            continue
        # using assertAlmostEqual with delta because the is_pod_running check
        # introduces some latency due to the api calls that makes difficult
        # to record the test duration with sufficient accuracy
        self.assertAlmostEqual(
            first=end - start,
            second=test_duration,
            places=None,
            delta=2,
        )

    def test_select_services_by_label(self):
        namespace = "test-" + self.get_random_string(10)
        service_name_1 = "krkn-syn-flood-" + self.get_random_string(10)
        service_name_2 = "krkn-syn-flood-" + self.get_random_string(10)
        self.deploy_namespace(namespace, labels=[])
        self.deploy_service(service_name_1, namespace)
        self.deploy_service(service_name_2, namespace)
        service = self.lib_k8s.select_service_by_label(
            namespace, "test=service"
        )
        self.assertEqual(len(service), 2)

        self.assertTrue(service_name_1 in service)
        self.assertTrue(service_name_2 in service)

        service = self.lib_k8s.select_service_by_label(namespace, "not=found")
        self.assertEqual(len(service), 0)

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


if __name__ == "__main__":
    unittest.main()
