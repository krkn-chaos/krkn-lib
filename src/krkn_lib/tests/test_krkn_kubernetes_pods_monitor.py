import time

from krkn_lib.k8s.pod_monitor import (
    select_and_monitor_by_label,
    select_and_monitor_by_name_pattern_and_namespace_pattern,
    select_and_monitor_by_namespace_pattern_and_label,
)
from krkn_lib.tests import BaseTest


class TestKrknKubernetesPodsMonitor(BaseTest):
    def test_monitor_pods_by_label_no_pods_affected(self):
        # test no pods affected
        namespace = "test-ns-0-" + self.get_random_string(10)
        delayed_1 = "delayed-0-" + self.get_random_string(10)
        delayed_2 = "delayed-0-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        while not self.lib_k8s.is_pod_running(
            delayed_1, namespace
        ) and not self.lib_k8s.is_pod_running(delayed_2, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 2

        start_time = time.time()

        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )
        snapshot = future.result()
        end_time = time.time()
        pods_status = snapshot.get_pods_status()
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)

        # added half second of delay that might be introduced to API
        # calls
        self.assertAlmostEqual(end_time - start_time, monitor_timeout, 1)

        self.assertEqual(len(pods_status.recovered), 0)
        self.assertEqual(len(pods_status.unrecovered), 0)
        self.background_delete_ns(namespace)

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
        while not self.lib_k8s.is_pod_running(
            delayed_1, namespace
        ) and not self.lib_k8s.is_pod_running(delayed_2, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        future = select_and_monitor_by_name_pattern_and_namespace_pattern(
            pod_name_pattern="^delayed-1-.*",
            namespace_pattern="^test-ns-1-.*",
            max_timeout=monitor_timeout,
        )

        self.background_delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario
        # can't happen (eg. replicaset or deployment)
        time.sleep(0.01)
        self.deploy_delayed_readiness_pod(
            delayed_respawn, namespace, pod_delay, label
        )

        while not self.lib_k8s.is_pod_running(
            delayed_1, namespace
        ) and not self.lib_k8s.is_pod_running(delayed_respawn, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        snapshot = future.result()
        pods_status = snapshot.get_pods_status()

        self.assertEqual(len(pods_status.recovered), 1)
        self.assertEqual(pods_status.recovered[0].pod_name, delayed_respawn)
        self.assertEqual(pods_status.recovered[0].namespace, namespace)
        self.assertTrue(pods_status.recovered[0].pod_readiness_time > 0)
        self.assertTrue(pods_status.recovered[0].pod_rescheduling_time >= 0)
        self.assertTrue(
            pods_status.recovered[0].total_recovery_time >= pod_delay
        )
        self.assertEqual(len(pods_status.unrecovered), 0)
        self.background_delete_ns(namespace)

    def test_pods_by_namespace_pattern_and_label_same_name_respawn(
        self,
    ):
        # flaky
        # test pod with same name recovered
        namespace = "test-ns-2-" + self.get_random_string(10)
        delayed_1 = "delayed-2-1-" + self.get_random_string(10)
        delayed_2 = "delayed-2-2-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        self.wait_pod(delayed_1, namespace)
        self.wait_pod(delayed_2, namespace)
        monitor_timeout = 45
        pod_delay = 0

        future = select_and_monitor_by_namespace_pattern_and_label(
            namespace_pattern="^test-ns-2-.*",
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
        )

        self.lib_k8s.delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(0.01)
        self.deploy_delayed_readiness_pod(
            delayed_1, namespace, pod_delay, label
        )

        while not self.lib_k8s.is_pod_running(delayed_1, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        snapshot = future.result()
        pods_status = snapshot.get_pods_status()
        self.background_delete_ns(namespace)
        self.assertEqual(len(pods_status.recovered), 1)
        self.assertEqual(pods_status.recovered[0].pod_name, delayed_1)
        self.assertEqual(pods_status.recovered[0].namespace, namespace)
        self.assertTrue(pods_status.recovered[0].pod_readiness_time > 0)
        self.assertTrue(pods_status.recovered[0].pod_rescheduling_time > 0)
        self.assertTrue(
            pods_status.recovered[0].total_recovery_time >= pod_delay
        )
        self.assertEqual(len(pods_status.unrecovered), 0)

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
        while not self.lib_k8s.is_pod_running(
            delayed_1, namespace
        ) and not self.lib_k8s.is_pod_running(delayed_2, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 20
        pod_delay = 21

        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(0.01)
        self.deploy_delayed_readiness_pod(
            delayed_respawn, namespace, pod_delay, label
        )

        snapshot = future.result()
        pods_status = snapshot.get_pods_status()

        self.assertEqual(len(pods_status.unrecovered), 1)
        self.assertEqual(pods_status.unrecovered[0].pod_name, delayed_respawn)
        self.assertEqual(pods_status.unrecovered[0].namespace, namespace)
        self.assertEqual(len(pods_status.recovered), 0)
        self.background_delete_ns(namespace)

    def test_pods_by_label_never_respawn(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)

        while not self.lib_k8s.is_pod_running(
            delayed_1, namespace
        ) and not self.lib_k8s.is_pod_running(delayed_2, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 15

        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )
        self.background_delete_pod(delayed_1, namespace)
        snapshot = future.result()
        pods_status = snapshot.get_pods_status()

        self.assertEqual(len(pods_status.unrecovered), 1)
        self.assertEqual(len(pods_status.recovered), 0)
        self.background_delete_ns(namespace)

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
        while (
            not self.lib_k8s.is_pod_running(delayed_1, namespace)
            and not self.lib_k8s.is_pod_running(delayed_2, namespace)
            and not self.lib_k8s.is_pod_running(delayed_3, namespace)
        ):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 20
        pod_delay = 2

        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(0.01)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_delay, label
        )

        snapshot = future.result()
        pods_status = snapshot.get_pods_status()

        self.background_delete_pod(delayed_3, namespace)
        self.background_delete_pod(delayed_respawn_1, namespace)
        self.background_delete_pod(delayed_respawn_2, namespace)

        self.assertEqual(len(pods_status.unrecovered), 0)
        self.assertEqual(len(pods_status.recovered), 2)
        self.assertTrue(
            delayed_respawn_1 in [p.pod_name for p in pods_status.recovered]
        )
        self.assertTrue(
            delayed_respawn_2 in [p.pod_name for p in pods_status.recovered]
        )
        self.background_delete_ns(namespace)

    def test_pods_by_label_multiple_respawn_one_too_late(self):
        # flaky
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
        while (
            not self.lib_k8s.is_pod_running(delayed_1, namespace)
            and not self.lib_k8s.is_pod_running(delayed_2, namespace)
            and not self.lib_k8s.is_pod_running(delayed_3, namespace)
        ):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 20
        pod_delay = 0
        pod_too_much_delay = 25
        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(0.01)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_too_much_delay, label
        )

        snapshot = future.result()
        pods_status = snapshot.get_pods_status()
        self.background_delete_ns(namespace)

        self.assertEqual(len(pods_status.unrecovered), 1)
        self.assertEqual(len(pods_status.recovered), 1)
        self.assertTrue(
            delayed_respawn_1 in [p.pod_name for p in pods_status.recovered]
        )
        self.assertTrue(
            delayed_respawn_2 in [p.pod_name for p in pods_status.unrecovered]
        )

    def test_pods_by_label_multiple_respawn_one_fails(self):
        # test pod will never recover
        namespace = "test-ns-4-" + self.get_random_string(10)
        delayed_1 = "delayed-4-" + self.get_random_string(10)
        delayed_2 = "delayed-4-" + self.get_random_string(10)
        delayed_3 = "delayed-4-" + self.get_random_string(10)
        delayed_respawn_1 = "delayed-4-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_2, namespace, 0, label)
        self.deploy_delayed_readiness_pod(delayed_3, namespace, 0, label)
        while (
            not self.lib_k8s.is_pod_running(delayed_1, namespace)
            and not self.lib_k8s.is_pod_running(delayed_2, namespace)
            and not self.lib_k8s.is_pod_running(delayed_3, namespace)
        ):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 10
        pod_delay = 1
        future = select_and_monitor_by_label(
            label_selector=f"test={label}", max_timeout=monitor_timeout
        )
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        time.sleep(0.1)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        snapshot = future.result()
        pods_status = snapshot.get_pods_status()
        self.background_delete_ns(namespace)
        self.assertEqual(len(pods_status.unrecovered), 1)
        self.assertEqual(len(pods_status.recovered), 1)

        self.assertTrue(
            delayed_respawn_1 in [p.pod_name for p in pods_status.recovered]
        )

    def test_pods_becoming_not_ready(self):
        # test pod will never recover
        namespace = "test-ns-5-" + self.get_random_string(10)
        delayed_1 = "delayed-5-" + self.get_random_string(10)
        self.deploy_namespace(namespace, [])
        self.deploy_nginx(namespace, delayed_1)
        while not self.lib_k8s.is_pod_running(delayed_1, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 20

        future = select_and_monitor_by_name_pattern_and_namespace_pattern(
            delayed_1, namespace, max_timeout=monitor_timeout
        )

        self.lib_k8s.exec_cmd_in_pod(["kill 1"], delayed_1, namespace)
        snapshot = future.result()
        pods_status = snapshot.get_pods_status()
        self.background_delete_ns(namespace)
        self.assertEqual(len(pods_status.recovered), 1)
        self.assertEqual(pods_status.recovered[0].pod_rescheduling_time, None)
        self.assertGreater(pods_status.recovered[0].pod_readiness_time, 0)
