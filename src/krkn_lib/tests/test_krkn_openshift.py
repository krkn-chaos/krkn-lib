import os
from datetime import datetime

from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class KrknOpenshiftTest(BaseTest):
    def test_get_cluster_version_string(self):
        # TODO
        result = self.lib_ocp.get_clusterversion_string()
        self.assertIsNotNone(result)

    def test_get_cluster_network_plugins(self):
        resp = self.lib_ocp.get_cluster_network_plugins()
        self.assertTrue(len(resp) > 0)
        self.assertEqual(resp[0], "Unknown")

    def test_get_cluster_type(self):
        resp = self.lib_ocp.get_cluster_type()
        self.assertTrue(resp)
        self.assertEqual(resp, "self-managed")

    def test_get_cloud_infrastructure(self):
        resp = self.lib_ocp.get_cloud_infrastructure()
        self.assertTrue(resp)
        self.assertEqual(resp, "Unknown")

    def test_filter_must_gather_ocp_log_folder(self):
        # 1694473200 12 Sep 2023 01:00 AM GMT+2
        # 1694476200 12 Sep 2023 01:50 AM GMT+2
        filter_patterns = [
            # Sep 9 11:20:36.123425532
            r"(\w{3}\s\d{1,2}\s\d{2}:\d{2}:\d{2}\.\d+).+",
            # kinit 2023/09/15 11:20:36 log
            r"kinit (\d+/\d+/\d+\s\d{2}:\d{2}:\d{2})\s+",
            # 2023-09-15T11:20:36.123425532Z log
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+",
        ]
        dst_dir = f"/tmp/filtered_logs.{datetime.now().timestamp()}"
        os.mkdir(dst_dir)
        self.lib_ocp.filter_must_gather_ocp_log_folder(
            "src/testdata/must-gather",
            dst_dir,
            1694473200,
            1694476200,
            "*.log",
            3,
            filter_patterns,
        )

        test_file_1 = os.path.join(
            dst_dir,
            "namespaces.openshift-monitoring.pods."
            "openshift-state-metrics-"
            "78df59b4d5-mjvhd.openshift-state-metrics."
            "openshift-state-metrics.logs.current.log",
        )

        test_file_2 = os.path.join(
            dst_dir,
            "namespaces.openshift-monitoring.pods.prometheus-"
            "k8s-0.prometheus.prometheus.logs.current.log",
        )
        self.assertTrue(os.path.exists(test_file_1))
        self.assertTrue(os.path.exists(test_file_2))

        test_file_1_lines = 0
        test_file_2_lines = 0

        with open(test_file_1) as file:
            for _ in file:
                test_file_1_lines += 1

        with open(test_file_2) as file:
            for _ in file:
                test_file_2_lines += 1

        self.assertEqual(test_file_1_lines, 7)
        self.assertEqual(test_file_2_lines, 4)

    def test_is_openshift(self):
        self.assertFalse(self.lib_ocp.is_openshift())

    def test_get_cluster_version(self):
        # TODO
        result = self.lib_ocp.get_clusterversion_string()
        self.assertIsNotNone(result)

    def _test_collect_filter_archive_ocp_logs(self):
        ##################################################
        # This test is incomplete and inactive because   #
        # we don't have an OCP Integration     env yet.  #
        ##################################################

        base_dir = os.path.join(
            "/tmp", f"log-filter-test.{datetime.now().timestamp()}"
        )
        work_dir = os.path.join(base_dir, "must-gather")
        dst_dir = os.path.join(base_dir, "filtered_logs")
        os.mkdir(base_dir)
        os.mkdir(work_dir)
        os.mkdir(dst_dir)
        start = 1695218445
        end = 1695219345
        filter_patterns = [
            # Sep 9 11:20:36.123425532
            r"(\w{3}\s\d{1,2}\s\d{2}:\d{2}:\d{2}\.\d+).+",
            # kinit 2023/09/15 11:20:36 log
            r"kinit (\d+/\d+/\d+\s\d{2}:\d{2}:\d{2})\s+",
            # 2023-09-15T11:20:36.123425532Z log
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+",
        ]
        self.lib_ocp.collect_filter_archive_ocp_logs(
            work_dir,
            dst_dir,
            "/home/tsebasti/OCP/auth/kubeconfig",
            start,
            end,
            filter_patterns,
            5,
            SafeLogger(),
        )
