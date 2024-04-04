import time

from krkn_lib.k8s.pods_monitor_pool import PodsMonitorPool
from krkn_lib.tests import BaseTest


class TestKrknKubernetesPodsMonitorPool(BaseTest):
    def test_pods_monitor_pool(self):
        namespace_1 = "test-pool-ns-0-" + self.get_random_string(10)
        label_1 = "readiness-1"
        delayed_1 = "delayed-pool-0-1-" + self.get_random_string(10)
        delayed_2 = "delayed-pool-0-2-" + self.get_random_string(10)

        delayed_1_respawn = "delayed-pool-0-r-2-" + self.get_random_string(10)
        self.deploy_namespace(namespace_1, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace_1, 0, label_1)
        self.deploy_delayed_readiness_pod(delayed_2, namespace_1, 0, label_1)

        namespace_2 = "test-pool-ns-1-" + self.get_random_string(10)
        label_2 = "readiness-2"
        delayed_3 = "delayed-pool-1-3-" + self.get_random_string(10)
        delayed_4 = "delayed-pool-1-4-" + self.get_random_string(10)
        delayed_3_respawn = "delayed-pool-1-r-4-" + self.get_random_string(10)
        self.deploy_namespace(namespace_2, [])
        self.deploy_delayed_readiness_pod(delayed_3, namespace_2, 0, label_2)
        self.deploy_delayed_readiness_pod(delayed_4, namespace_2, 0, label_2)

        namespace_3 = "test-pool-ns-2-" + self.get_random_string(10)
        label_3 = "readiness-3"
        delayed_5 = "delayed-pool-2-5-" + self.get_random_string(10)
        delayed_6 = "delayed-pool-2-6-" + self.get_random_string(10)
        delayed_5_respawn = "delayed-pool-2-r-5-" + self.get_random_string(10)
        self.deploy_namespace(namespace_3, [])
        self.deploy_delayed_readiness_pod(delayed_5, namespace_3, 0, label_3)
        self.deploy_delayed_readiness_pod(delayed_6, namespace_3, 0, label_3)
        # waiting the pods to become ready
        time.sleep(10)
        print("starting monitoring")
        pod_delay = 1
        monitor_timeout = 10

        pool = PodsMonitorPool(self.lib_k8s)

        pool.select_and_monitor_by_label(
            label_selector=f"test={label_1}",
            max_timeout=monitor_timeout,
        )

        pool.select_and_monitor_by_namespace_pattern_and_label(
            namespace_pattern="^test-pool-ns-1-.*",
            label_selector=f"test={label_2}",
            max_timeout=monitor_timeout,
        )

        pool.select_and_monitor_by_name_pattern_and_namespace_pattern(
            pod_name_pattern="^delayed-pool-2-.*",
            namespace_pattern="^test-pool-ns-2-.*",
            max_timeout=monitor_timeout,
        )

        self.background_delete_pod(delayed_1, namespace_1)
        self.background_delete_pod(delayed_3, namespace_2)
        self.background_delete_pod(delayed_5, namespace_3)
        # these two will recover the previously deleted pods
        self.deploy_delayed_readiness_pod(
            delayed_1_respawn, namespace_1, pod_delay, label_1
        )
        self.deploy_delayed_readiness_pod(
            delayed_3_respawn, namespace_2, pod_delay, label_2
        )
        # this one will not recover
        self.deploy_delayed_readiness_pod(
            delayed_5_respawn, namespace_3, monitor_timeout + 5, label_3
        )
        start_time = time.time()
        status = pool.join()
        # added 1 second threshold that may
        # happen because of intermediate api call delay
        self.assertTrue(0 < time.time() - start_time < monitor_timeout + 1)
        self.background_delete_pod(delayed_1_respawn, namespace_1)
        self.background_delete_pod(delayed_2, namespace_1)
        self.background_delete_pod(delayed_3_respawn, namespace_2)

        self.background_delete_pod(delayed_4, namespace_2)
        self.background_delete_pod(delayed_5_respawn, namespace_3)
        self.background_delete_pod(delayed_6, namespace_3)

        self.assertIsNone(status.error)
        self.assertEqual(len(status.recovered), 2)
        self.assertEqual(len(status.unrecovered), 1)

    def test_cancel(self):
        namespace_1 = "test-pool-ns-0-" + self.get_random_string(10)
        label_1 = "readiness-1"
        delayed_1 = "delayed-pool-0-1-" + self.get_random_string(10)
        delayed_2 = "delayed-pool-0-2-" + self.get_random_string(10)

        delayed_1_respawn = "delayed-pool-0-r-2-" + self.get_random_string(10)
        self.deploy_namespace(namespace_1, [])
        self.deploy_delayed_readiness_pod(delayed_1, namespace_1, 0, label_1)
        self.deploy_delayed_readiness_pod(delayed_2, namespace_1, 0, label_1)
        monitor_timeout = 60
        pool = PodsMonitorPool(self.lib_k8s)

        pool.select_and_monitor_by_label(
            label_selector=f"test={label_1}",
            max_timeout=monitor_timeout,
        )
        self.background_delete_pod(delayed_1, namespace_1)
        self.deploy_delayed_readiness_pod(
            delayed_1_respawn, namespace_1, monitor_timeout + 5, label_1
        )
        start_time = time.time()
        pool.cancel()
        _ = pool.join()
        end_time = time.time() - start_time
        self.background_delete_pod(delayed_1_respawn, namespace_1)
        self.background_delete_pod(delayed_2, namespace_1)
        # give the time to wrap up the threads and return
        self.assertLess(end_time, 1)
