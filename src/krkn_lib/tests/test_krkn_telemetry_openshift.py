import datetime
import os
import uuid

from jinja2 import Environment, FileSystemLoader

from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger
from unittest.mock import MagicMock


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

    def test_get_vm_infos(self):
        environment = Environment(loader=FileSystemLoader("src/testdata/"))
        template = environment.get_template("virtualization_api_result.j2")
        api_result = template.render()
        krkn_ocp_mock = MagicMock()
        krkn_ocp_mock.kubeconfig_path = "~/.kube/config"
        krkn_ocp_mock.api_client.call_api.return_value = [api_result, 200]
        safe_logger = SafeLogger()
        krkn_telemetry_ocp = KrknTelemetryOpenshift(safe_logger, krkn_ocp_mock)
        self.assertEqual(krkn_telemetry_ocp.get_vm_number(), 3)
        krkn_ocp_mock.api_client.call_api.return_value = [None, 404]
        self.assertEqual(krkn_telemetry_ocp.get_vm_number(), 0)
