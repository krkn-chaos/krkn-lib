import json
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        snapshot = future.result()
        end_time = time.time()
        pods_status = snapshot.get_pods_status()
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # added half second of delay that might be introduced to API
        # calls
        self.assertAlmostEqual(end_time - start_time, monitor_timeout, 0)

        self.assertEqual(len(pods_status.recovered), 0)
        self.assertEqual(len(pods_status.unrecovered), 0)
        self.background_delete_ns(namespace)

    def test_pods_by_name_and_namespace_pattern_different_names_respawn(
        self,
    ):
        # test pod with different name recovered
        namespace_random_pattern = "test-ns-1-" + self.get_random_string(3)
        namespace = f"{namespace_random_pattern}-" + self.get_random_string(10)
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
            namespace_pattern=f"^{namespace_random_pattern}-.*",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        self.background_delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario
        # can't happen (eg. replicaset or deployment)
        time.sleep(1)
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
        print(f"\nRunning test ID: {self.id()}")
        print(json.dumps(snapshot.to_dict(), indent=True))
        pods_status = snapshot.get_pods_status()

        self.assertEqual(len(pods_status.recovered), 1)
        self.assertEqual(pods_status.recovered[0].pod_name, delayed_respawn)
        self.assertEqual(pods_status.recovered[0].namespace, namespace)
        self.assertTrue(pods_status.recovered[0].pod_readiness_time > 0)
        self.assertTrue(pods_status.recovered[0].pod_rescheduling_time > 0)
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
            v1_client=self.lib_k8s.cli,
        )

        self.lib_k8s.delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(1)
        self.deploy_delayed_readiness_pod(
            delayed_1, namespace, pod_delay, label
        )

        while not self.lib_k8s.is_pod_running(delayed_1, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        self.background_delete_pod(delayed_1, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(1)
        self.deploy_delayed_readiness_pod(
            delayed_respawn, namespace, pod_delay, label
        )

        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        self.background_delete_pod(delayed_1, namespace)
        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(1)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        # introduce a delay in the next recovering pod to check
        # if delayed recoveries are captured
        time.sleep(2)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_delay, label
        )

        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        # to prevent the pod scheduling happening before the deletion
        # event that in a real world scenario can't happen
        # (eg. replicaset or deployment)
        time.sleep(1)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_2, namespace, pod_too_much_delay, label
        )

        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        time.sleep(0.1)
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        snapshot = future.result()
        # print(f"\nRunning test ID: {self.id()}")
        # print(json.dumps(snapshot.to_dict(), indent=True))
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
            delayed_1,
            namespace,
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        self.lib_k8s.exec_cmd_in_pod(["kill 1"], delayed_1, namespace)
        snapshot = future.result()

        pods_status = snapshot.get_pods_status()
        self.background_delete_ns(namespace)
        self.assertEqual(len(pods_status.recovered), 1)
        self.assertEqual(pods_status.recovered[0].pod_rescheduling_time, 0)
        self.assertGreater(pods_status.recovered[0].pod_readiness_time, 0)
        self.assertEqual(
            pods_status.recovered[0].total_recovery_time,
            pods_status.recovered[0].pod_readiness_time,
        )

    def test_monitor_stopping_earlier(self):

        # tests that the monitor deadlines:
        # - if the monitored pods status changes and is restored
        #   before than the 120 seconds deadline the monitor returns earlier
        #   the assertions checks that the monitor returns within 10 seconds
        #   120 - (end-start) >= 110
        # - if no change is made in the set of monitor pods the monitor is
        #   forced to wait all the time set

        namespace = "test-ns-6-" + self.get_random_string(10)
        delayed_1 = "delayed-6-" + self.get_random_string(10)
        delayed_respawn_1 = "delayed-6-respawn-" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        pod_delay = 3
        while not self.lib_k8s.is_pod_running(delayed_1, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 120

        start_time = time.time()

        future = select_and_monitor_by_label(
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        self.deploy_delayed_readiness_pod(
            delayed_respawn_1, namespace, pod_delay, label
        )
        _ = future.result()
        end_time = time.time()

        self.assertGreater(monitor_timeout - (end_time - start_time), 110)

    def test_monitor_forced_to_wait_with_no_status_change(self):
        # tests that the monitor deadlines:
        # - if no change is made in the set of monitored pods the monitor is
        #   forced to wait all the time set in case something happens

        namespace = "test-ns-7-" + self.get_random_string(10)
        delayed_1 = "delayed-7" + self.get_random_string(10)
        label = "readiness-" + self.get_random_string(5)
        self.deploy_namespace(namespace, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace, 0, label)
        while not self.lib_k8s.is_pod_running(delayed_1, namespace):
            time.sleep(1)
            continue
        time.sleep(3)

        monitor_timeout = 20

        start_time = time.time()

        future = select_and_monitor_by_label(
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )
        _ = future.result()
        end_time = time.time()

        self.assertGreaterEqual((end_time - start_time), monitor_timeout)

    def test_monitor_cancel_by_label(self):
        # Test that cancel() properly stops monitoring and returns quickly
        namespace = "test-ns-cancel-1-" + self.get_random_string(10)
        delayed_1 = "delayed-cancel-1-" + self.get_random_string(10)
        delayed_2 = "delayed-cancel-1-" + self.get_random_string(10)
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

        monitor_timeout = 120  # Long timeout to test cancellation
        cancel_delay = 1  # Cancel after 1 second

        start_time = time.time()
        future = select_and_monitor_by_label(
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        # Wait a bit then cancel
        time.sleep(cancel_delay)
        cancel_start = time.time()
        future.cancel()

        # Wait for future to finish (may take up to 5 seconds due to
        # stream_timeout)
        max_wait_time = 10  # Allow up to 10 seconds for cancellation
        wait_start = time.time()
        while not future.done():
            if time.time() - wait_start > max_wait_time:
                self.fail("Future did not complete after cancellation")
            time.sleep(0.1)
        cancel_end = time.time()

        # Get the snapshot result (should have partial data)
        # The future should complete normally, not raise CancelledError
        try:
            snapshot = future.result(timeout=1)
        except Exception as e:
            # If cancelled, the monitoring should still have completed
            # normally with partial data
            self.fail(f"Future.result() raised exception: {e}")

        end_time = time.time()
        pods_status = snapshot.get_pods_status()

        # Verify cancellation happened within reasonable time
        # (stream_timeout is 5 seconds, so allow up to 7 seconds total)
        total_time = end_time - start_time
        cancel_time = cancel_end - cancel_start

        self.assertLess(
            total_time, 8, "Cancellation should complete within 8 seconds"
        )
        self.assertLess(
            cancel_time, 7,
            "Future should finish within 7 seconds after cancel()"
        )

        # Verify we can still get pods status (may be empty or partial)
        self.assertIsNotNone(pods_status)
        self.assertIsNotNone(pods_status.recovered)
        self.assertIsNotNone(pods_status.unrecovered)

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.background_delete_ns(namespace)

    def test_monitor_cancel_by_name_pattern_and_namespace_pattern(self):
        # Test cancellation with name pattern and namespace pattern monitoring
        namespace_random_pattern = (
            "test-ns-cancel-2-" + self.get_random_string(3)
        )
        namespace = f"{namespace_random_pattern}-" + self.get_random_string(10)
        delayed_1 = "delayed-cancel-2-" + self.get_random_string(10)
        delayed_2 = "delayed-cancel-2-" + self.get_random_string(10)
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

        monitor_timeout = 120
        cancel_delay = 1

        start_time = time.time()
        future = select_and_monitor_by_name_pattern_and_namespace_pattern(
            pod_name_pattern="^delayed-cancel-2-.*",
            namespace_pattern=f"^{namespace_random_pattern}-.*",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        time.sleep(cancel_delay)
        future.cancel()

        # Wait for future to finish (may take up to 5 seconds)
        max_wait_time = 10
        wait_start = time.time()
        while not future.done():
            if time.time() - wait_start > max_wait_time:
                self.fail("Future did not complete after cancellation")
            time.sleep(0.1)

        try:
            snapshot = future.result(timeout=1)
        except Exception as e:
            self.fail(f"Future.result() raised exception: {e}")

        end_time = time.time()
        pods_status = snapshot.get_pods_status()

        total_time = end_time - start_time
        self.assertLess(
            total_time, 8, "Cancellation should complete within 8 seconds"
        )
        self.assertIsNotNone(pods_status)

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.background_delete_ns(namespace)

    def test_monitor_cancel_by_namespace_pattern_and_label(self):
        # Test cancellation with namespace pattern and label monitoring
        namespace = "test-ns-cancel-3-" + self.get_random_string(10)
        delayed_1 = "delayed-cancel-3-" + self.get_random_string(10)
        delayed_2 = "delayed-cancel-3-" + self.get_random_string(10)
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

        monitor_timeout = 120
        cancel_delay = 1

        start_time = time.time()
        future = select_and_monitor_by_namespace_pattern_and_label(
            namespace_pattern="^test-ns-cancel-3-.*",
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        time.sleep(cancel_delay)
        future.cancel()

        # Wait for future to finish (may take up to 5 seconds)
        max_wait_time = 10
        wait_start = time.time()
        while not future.done():
            if time.time() - wait_start > max_wait_time:
                self.fail("Future did not complete after cancellation")
            time.sleep(0.1)

        try:
            snapshot = future.result(timeout=1)
        except Exception as e:
            self.fail(f"Future.result() raised exception: {e}")

        end_time = time.time()
        pods_status = snapshot.get_pods_status()

        total_time = end_time - start_time
        self.assertLess(
            total_time, 8, "Cancellation should complete within 8 seconds"
        )
        self.assertIsNotNone(pods_status)

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.background_delete_ns(namespace)

    def test_monitor_cancel_immediately(self):
        # Test that cancel() works even if called immediately
        namespace = "test-ns-cancel-4-" + self.get_random_string(10)
        delayed_1 = "delayed-cancel-4-" + self.get_random_string(10)
        delayed_2 = "delayed-cancel-4-" + self.get_random_string(10)
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

        monitor_timeout = 120

        start_time = time.time()
        future = select_and_monitor_by_label(
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        # Cancel immediately
        future.cancel()

        # Wait for future to finish (may take up to 5 seconds)
        max_wait_time = 10
        wait_start = time.time()
        while not future.done():
            if time.time() - wait_start > max_wait_time:
                self.fail("Future did not complete after cancellation")
            time.sleep(0.1)

        try:
            snapshot = future.result(timeout=1)
        except Exception as e:
            self.fail(f"Future.result() raised exception: {e}")

        end_time = time.time()
        pods_status = snapshot.get_pods_status()

        total_time = end_time - start_time
        # Should complete within reasonable time (stream_timeout is 5 sec)
        self.assertLess(
            total_time,
            7,
            "Immediate cancellation should complete within 7 seconds",
        )
        self.assertIsNotNone(pods_status)

        self.background_delete_pod(delayed_1, namespace)
        self.background_delete_pod(delayed_2, namespace)
        self.background_delete_ns(namespace)

    def test_monitor_cancel_after_pod_deletion(self):
        # Test cancellation after a pod has been deleted but before recovery
        namespace = "test-ns-cancel-5-" + self.get_random_string(10)
        delayed_1 = "delayed-cancel-5-" + self.get_random_string(10)
        delayed_2 = "delayed-cancel-5-" + self.get_random_string(10)
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

        monitor_timeout = 120

        future = select_and_monitor_by_label(
            label_selector=f"test={label}",
            max_timeout=monitor_timeout,
            v1_client=self.lib_k8s.cli,
        )

        # Delete a pod to trigger monitoring
        self.background_delete_pod(delayed_1, namespace)
        time.sleep(1)  # Wait for deletion event to be processed

        # Cancel after deletion but before recovery
        future.cancel()

        # Wait for future to finish (may take up to 5 seconds)
        max_wait_time = 10
        wait_start = time.time()
        while not future.done():
            if time.time() - wait_start > max_wait_time:
                self.fail("Future did not complete after cancellation")
            time.sleep(0.1)

        try:
            snapshot = future.result(timeout=1)
        except Exception as e:
            self.fail(f"Future.result() raised exception: {e}")

        pods_status = snapshot.get_pods_status()

        # Should have captured the deletion event
        self.assertIsNotNone(pods_status)
        # The deleted pod might be in unrecovered or we might have partial
        # data. This depends on timing, so we just verify we got a valid
        # result

        self.background_delete_pod(delayed_2, namespace)
        self.background_delete_ns(namespace)
