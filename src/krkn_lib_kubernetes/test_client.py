import sys
import tempfile
import time
import unittest
import requests
import yaml
import logging
import string
import random
import re
from typing import List, Dict
from kubernetes import config
from kubernetes.client import ApiException
from requests import ConnectTimeout
from krkn_lib_kubernetes import ApiRequestException
from jinja2 import Environment, FileSystemLoader
from .client import KrknLibKubernetes


class BaseTest(unittest.TestCase):
    lib_k8s: KrknLibKubernetes

    @classmethod
    def setUpClass(cls):
        cls.lib_k8s = KrknLibKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)
        host = cls.lib_k8s.api_client.configuration.host
        logging.disable(logging.CRITICAL)
        try:
            requests.get(host, timeout=2, verify=False)
        except ConnectTimeout:
            logging.error(
                "Unable to connect to Kubernetes API %s.\n"
                "To run the tests please setup a running kubernetes cluster.\n"
                "To have a local working kubernetes cluster "
                "visit https://minikube.sigs.k8s.io/docs/\n",
                host,
            )
            sys.exit(1)

    @classmethod
    def tearDownClass(cls) -> None:
        pass

    def wait_pod(
        self, name: str, namespace: str = "default", timeout: int = 60
    ):
        runtime = 0
        while True:
            if runtime >= timeout:
                raise Exception(
                    "timeout on waiting {0} pod on namespace {1}".format(
                        name, namespace
                    )
                )
            result = self.lib_k8s.read_pod(name, namespace)
            if result.status.phase == "Running":
                logging.info("pod %s is now running" % name)
                return
            time.sleep(2)
            runtime = runtime + 2

    def deploy_namespace(self, name: str, labels: List[Dict[str, str]]):
        template = self.template_to_namespace(name, labels)
        self.apply_template(template)

    def deploy_fedtools(
        self,
        namespace: str = "default",
        random_label: str = None,
        name: str = "fedtools",
    ):
        template = self.template_to_pod(name, namespace, random_label)
        self.apply_template(template)

    def deploy_fake_kraken(
        self,
        namespace: str = "default",
        random_label: str = None,
        node_name: str = None,
    ):
        template = self.template_to_pod(
            "kraken-deployment", namespace, random_label, node_name
        )
        self.apply_template(template)

    def deploy_job(self, name: str, namespace: str = "default"):
        template = self.template_to_job(name, namespace)
        self.apply_template(template)

    def deploy_persistent_volume(
        self, name: str, storage_class: str, namespace: str
    ):
        template = self.template_to_pv(name, storage_class, namespace)
        self.apply_template(template)

    def deploy_persistent_volume_claim(
        self, name: str, storage_class: str, namespace: str
    ):
        template = self.template_to_pvc(name, storage_class, namespace)
        self.apply_template(template)

    def delete_fake_kraken(self, namespace: str = "default"):
        self.lib_k8s.delete_pod("kraken-deployment", namespace)

    def template_to_job(self, name: str, namespace: str = "default") -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("job.j2")
        content = template.render(name=name, namespace=namespace)
        return content

    def template_to_namespace(
        self, name: str, labels: List[Dict[str, str]]
    ) -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("namespace_template.j2")
        content = template.render(name=name, labels=labels)
        return content

    def template_to_pod(
        self,
        name: str,
        namespace: str = "default",
        random_label: str = None,
        node_name: str = None,
    ) -> any:
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("fedtools-deployment.j2")
        if node_name is not None:
            content = template.render(
                name=name,
                namespace=namespace,
                random_label=random_label,
                has_node_selector=True,
                node_name=node_name,
            )
        else:
            content = template.render(
                name=name,
                has_node_selector=False,
                namespace=namespace,
                random_label=random_label,
            )
        return content

    def template_to_pv(self, name: str, storage_class: str, namespace: str):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("pv.j2")
        content = template.render(
            name=name, namespace=namespace, storage_class=storage_class
        )
        return content

    def template_to_pvc(self, name: str, storage_class: str, namespace: str):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("pvc.j2")
        content = template.render(
            name=name, namespace=namespace, storage_class=storage_class
        )
        return content

    def apply_template(self, template: str):
        with tempfile.NamedTemporaryFile(mode="w") as file:
            file.write(template)
            file.flush()
            self.lib_k8s.apply_yaml(file.name, "")

    def get_random_string(self, length: int) -> str:
        letters = string.ascii_lowercase
        return "".join(random.choice(letters) for i in range(length))

    def is_openshift(self) -> bool:
        try:
            result = self.lib_k8s.get_clusterversion_string()
            if result == "":
                return False
            return True
        except Exception:
            return False


class KrknLibKubernetesTests(BaseTest):
    def test_exec_command(self):
        namespace = "test-ns-" + self.get_random_string(5)
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
        name = "test-ns-" + self.get_random_string(5)
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
        labels.append("check-namespace-" + self.get_random_string(5))
        labels.append("check-namespace-" + self.get_random_string(5))
        common_label = "check-namespace-" + self.get_random_string(5)
        while i < 5:
            name = "test-ns-" + self.get_random_string(5)
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
        namespace = "test-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_fake_kraken(namespace=namespace)
        pods = self.lib_k8s.list_pods(namespace=namespace)
        self.assertTrue(len(pods) == 1)
        self.assertIn("kraken-deployment", pods)
        self.lib_k8s.delete_namespace(namespace)
        self.delete_fake_kraken(namespace=namespace)

    def test_get_all_pods(self):
        namespace = "test-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_fedtools(namespace=namespace)
        self.wait_pod("fedtools", namespace=namespace)
        self.lib_k8s.delete_pod("fedtools", namespace=namespace)
        with self.assertRaises(ApiException):
            self.lib_k8s.read_pod("fedtools", namespace=namespace)

    def test_create_pod(self):
        namespace = "test-ns-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
        name = "test-name-" + self.get_random_string(5)
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
        good_namespace = "test-ns-" + self.get_random_string(5)
        good_name = "test-name-" + self.get_random_string(5)
        self.deploy_namespace(good_namespace, [])
        self.deploy_fedtools(namespace=good_namespace, name=good_name)
        self.wait_pod(good_name, namespace=good_namespace)
        status = self.lib_k8s.monitor_namespace(namespace=good_namespace)
        self.assertTrue(status[0])
        self.assertTrue(len(status[1]) == 0)

        bad_namespace = "test-ns-" + self.get_random_string(5)
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
        good_namespace = "test-ns-" + self.get_random_string(5)
        good_name = "test-name-" + self.get_random_string(5)
        self.deploy_namespace(good_namespace, [])
        self.deploy_fedtools(namespace=good_namespace, name=good_name)
        self.wait_pod(good_name, namespace=good_namespace)
        status = self.lib_k8s.monitor_component(
            iteration=0, component_namespace=good_namespace
        )
        self.assertTrue(status[0])
        self.assertTrue(len(status[1]) == 0)

        bad_namespace = "test-ns-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
            name = "test-name-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
            name = "test-name-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
            storage_class = "sc-" + self.get_random_string(5)
            pv_name = "pv-" + self.get_random_string(5)
            pvc_name = "pvc-" + self.get_random_string(5)
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
            namespace = "test-ns-" + self.get_random_string(5)
            storage_class = "sc-" + self.get_random_string(5)
            pv_name = "pv-" + self.get_random_string(5)
            pvc_name = "pvc-" + self.get_random_string(5)
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
        namespace = "test-ns-" + self.get_random_string(5)
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


if __name__ == "__main__":
    unittest.main()
