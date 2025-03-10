import time
import unittest

from krkn_lib.tests import BaseTest


class KrknKubernetesTestsCreate(BaseTest):
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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

    def test_pods_by_namespace_pattern_and_label_same_name_respawn(
        self,
    ):
        # not working
        # test pod with same name recovered
        namespace = "test-ns-2-" + self.get_random_string(10)
        delayed_1 = "delayed-2-1-" + self.get_random_string(10)
        delayed_2 = "delayed-2-2-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        monitor_timeout = 45
        pod_delay = 0
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
        time.sleep(3)
        self.deploy_delayed_readiness_pod(
            delayed_1, namespace, pod_delay, label
        )

        result = pods_thread.join()
        self.assertIsNone(result.error)
        self.assertEqual(len(result.recovered), 1)
        self.assertEqual(result.recovered[0].pod_name, delayed_1)
        self.assertEqual(result.recovered[0].namespace, namespace)
        self.assertTrue(result.recovered[0].pod_readiness_time > 0)
        self.assertTrue(result.recovered[0].pod_rescheduling_time > 0)
        self.assertTrue(result.recovered[0].total_recovery_time >= pod_delay)
        self.assertEqual(len(result.unrecovered), 0)
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

    def test_pods_by_label_never_respawn(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        monitor_timeout = 10
        time.sleep(5)
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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

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
        self.lib_k8s.delete_namespace(namespace)

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
        pod_delay = 1
        pods_and_namespaces = self.lib_k8s.select_pods_by_label(
            f"test={label}"
        )
        pods_thread = self.lib_k8s.monitor_pods_by_label(
            f"test={label}", pods_and_namespaces, monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        time.sleep(3)
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
        self.lib_k8s.delete_namespace(namespace)


if __name__ == "__main__":
    unittest.main()
