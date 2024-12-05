import datetime
import logging
import random
import time
import unittest

import yaml

from krkn_lib.tests import BaseTest
from tzlocal import get_localzone
from kubernetes.client import ApiException


class KrknKubernetesTestsMisc(BaseTest):
    def test_read_pod(self):
        namespace = "test-rp" + self.get_random_string(10)
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
        finally:
            self.pod_delete_queue.put([name, namespace])

    def test_net_policy(self):
        namespace = "test-np" + self.get_random_string(10)
        name = "test"
        self.deploy_namespace(namespace, [])
        self.create_networkpolicy(name, namespace)
        np = self.lib_k8s.get_namespaced_net_policy(namespace=namespace)
        self.assertTrue(len(np) == 1)
        self.lib_k8s.delete_net_policy(name, namespace)
        np = self.lib_k8s.get_namespaced_net_policy(namespace=namespace)
        self.assertTrue(len(np) == 0)
        self.lib_k8s.delete_namespace(namespace)

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
        self.pod_delete_queue.put(["kraken-deployment", namespace])

    def test_collect_and_parse_cluster_events(self):
        start_now = datetime.datetime.now()
        namespace_with_evt = "test-" + self.get_random_string(10)
        pod_name = "test-" + self.get_random_string(10)
        self.deploy_namespace(namespace_with_evt, [])
        self.deploy_delayed_readiness_pod(pod_name, namespace_with_evt, 0)
        try:
            self.wait_pod(pod_name, namespace=namespace_with_evt)
        except Exception:
            logging.error("failed to create pod")
            self.assertTrue(False)
        finally:
            self.pod_delete_queue.put([pod_name, namespace_with_evt])
        
        time.sleep(10)
        local_timezone = f"{get_localzone()}"
        end__time = datetime.datetime.now()
        events = self.lib_k8s.collect_and_parse_cluster_events(
            int(start_now.timestamp()),
            int(end__time.timestamp()),
            local_timezone,
            namespace=namespace_with_evt,
        )
        self.assertGreater(len(events), 0)

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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)


if __name__ == "__main__":
    unittest.main()
