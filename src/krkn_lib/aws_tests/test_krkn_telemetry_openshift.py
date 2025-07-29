import datetime
import os
import uuid

from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class KrknTelemetryOpenshiftTests(BaseTest):
    def _test_put_ocp_logs(self):
        ##################################################
        # This test is incomplete and inactive because   #
        # we don't have an OCP Integration     env yet.  #
        ##################################################

        krkn_ocp = KrknOpenshift(kubeconfig_path="~/OCP/auth/kubeconfig")
        safe_logger = SafeLogger()
        krkn_telemetry_ocp = KrknTelemetryOpenshift(safe_logger, krkn_ocp)

        test_workdir = "/tmp/"
        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://9ead3157ti.execute-api.us-west-2.amazonaws.com/dev",  # NOQA
            "backup_threads": 6,
            "archive_path": test_workdir,
            "prometheus_backup": "True",
            "enabled": True,
            "logs_backup": True,
            "logs_filter_patterns": [
                # Sep 9 11:20:36.123425532
                r"(\w{3}\s\d{1,2}\s\d{2}:\d{2}:\d{2}\.\d+).+",
                # kinit 2023/09/15 11:20:36 log
                r"kinit (\d+/\d+/\d+\s\d{2}:\d{2}:\d{2})\s+",
                # 2023-09-15T11:20:36.123425532Z log
                r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).+",
            ],
        }
        now = datetime.datetime.now()

        ten_minutes_ago = now - datetime.timedelta(minutes=10)
        ten_minutes_fwd = now + datetime.timedelta(minutes=10)
        krkn_telemetry_ocp.put_ocp_logs(
            f"test-must-gather-{str(uuid.uuid1())}",
            telemetry_config,
            int(ten_minutes_ago.timestamp()),
            int(ten_minutes_fwd.timestamp()),
        )

    def test_get_kubeconfig_path(self):
        kube_path = self.lib_ocp.get_kubeconfig_path()
        self.assertIsNotNone(kube_path)
        self.assertEqual(kube_path, "~/.kube/config")
