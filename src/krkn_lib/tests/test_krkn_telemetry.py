import base64
import datetime
import os
import tempfile
import time
import unittest
import uuid

import boto3
import yaml

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ChaosRunTelemetry, ScenarioTelemetry
from krkn_lib.telemetry import KrknTelemetry
from krkn_lib.tests import BaseTest
from krkn_lib.utils import SafeLogger


class KrknTelemetryTests(BaseTest):
    def test_set_parameters_base_64(self):
        file_path = "src/testdata/input.yaml"
        scenario_telemetry = ScenarioTelemetry()

        self.lib_telemetry.set_parameters_base64(scenario_telemetry, file_path)
        with open(file_path, "rb") as file_stream:
            input_file_data_orig = file_stream.read().decode("utf-8")
            self.assertIsNotNone(input_file_data_orig)

        input_file_yaml_orig = yaml.safe_load(input_file_data_orig)
        input_file_yaml_processed = yaml.safe_load(
            base64.b64decode(
                scenario_telemetry.parametersBase64.encode()
            ).decode()
        )

        # once deserialized the base64 encoded parameter must be
        # equal to the original file except for the attribut kubeconfig
        # that has been set to "anonymized"
        self.assertEqual(
            len(input_file_yaml_processed["input_list"]),
            len(input_file_yaml_orig["input_list"]),
        )

        for key in input_file_yaml_orig["input_list"][0].keys():
            if key != "kubeconfig":
                self.assertEqual(
                    input_file_yaml_orig["input_list"][0][key],
                    input_file_yaml_processed["input_list"][0][key],
                )
            else:
                self.assertNotEqual(
                    input_file_yaml_orig["input_list"][0][key],
                    input_file_yaml_processed["input_list"][0][key],
                )
                self.assertEqual(
                    input_file_yaml_processed["input_list"][0][key],
                    "anonymized",
                )

    def test_upload_download_prometheus(self):
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

        prometheus_pod_name = "fedtools"
        prometheus_container_name = "fedtools"
        prometheus_namespace = namespace
        bucket_folder = f"test_folder/{int(time.time())}"
        workdir_basepath = os.getenv("TEST_WORKDIR")
        workdir = self.get_random_string(10)
        test_workdir = os.path.join(workdir_basepath, workdir)
        os.mkdir(test_workdir)
        # raises exception if archive path does not exist
        with self.assertRaises(Exception):
            self.lib_k8s.archive_and_get_path_from_pod(
                prometheus_pod_name,
                prometheus_container_name,
                prometheus_namespace,
                "/does_not_exist",
                "/test",
                str(uuid.uuid1()),
                archive_part_size=100,
                download_path=test_workdir,
            )

        # raises exception if target path does not exist
        with self.assertRaises(Exception):
            self.lib_k8s.archive_and_get_path_from_pod(
                prometheus_pod_name,
                prometheus_container_name,
                prometheus_namespace,
                "/tmp",
                "/does_not_exist",
                str(uuid.uuid1()),
                archive_part_size=100,
                download_path=test_workdir,
            )

        # raises exception if target pod does not exist
        with self.assertRaises(Exception):
            self.lib_k8s.archive_and_get_path_from_pod(
                "does_not_exist",
                prometheus_container_name,
                prometheus_namespace,
                "/tmp",
                "/does_not_exist",
                str(uuid.uuid1()),
                archive_part_size=100,
                download_path=test_workdir,
            )

        # raises exception if target container does not exist
        with self.assertRaises(Exception):
            self.lib_k8s.archive_and_get_path_from_pod(
                prometheus_pod_name,
                "does_not_exist",
                prometheus_namespace,
                "/tmp",
                "/does_not_exist",
                str(uuid.uuid1()),
                archive_part_size=100,
                download_path=test_workdir,
            )

        # raises exception if target namespace does not exist
        with self.assertRaises(Exception):
            self.lib_k8s.archive_and_get_path_from_pod(
                prometheus_pod_name,
                prometheus_container_name,
                "does_not_exist",
                "/tmp",
                "/does_not_exist",
                str(uuid.uuid1()),
                archive_part_size=100,
                download_path=test_workdir,
            )

        # happy path:
        # - creates a dummy file in the pod
        # - downloads it as multivolume tar
        # - uploads on s3
        # - check if all the files are updated in the bucket
        # create folder
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

        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://ulnmf9xv7j.execute-api.us-west-2.amazonaws.com/production",  # NOQA
            "backup_threads": 6,
            "archive_path": test_workdir,
            "prometheus_backup": "True",
        }

        file_list = self.lib_k8s.archive_and_get_path_from_pod(
            prometheus_pod_name,
            prometheus_container_name,
            prometheus_namespace,
            "/tmp",
            "/test",
            str(uuid.uuid1()),
            archive_part_size=100,
            download_path=test_workdir,
        )
        self.lib_telemetry.put_ocp_prometheus_data(
            telemetry_config, file_list, bucket_folder
        )

        s3 = boto3.client("s3")
        bucket_name = os.getenv("BUCKET_NAME")
        self.assertTrue(bucket_name)
        remote_files = s3.list_objects_v2(
            Bucket=bucket_name, Prefix=bucket_folder
        )
        self.assertEqual(len(remote_files["Contents"]), len(file_list))

    def test_collect_cluster_metadata(self):
        chaos_telemetry = ChaosRunTelemetry()
        self.assertEqual(len(chaos_telemetry.node_infos), 0)
        self.assertEqual(chaos_telemetry.node_count, 0)
        self.assertEqual(
            len(chaos_telemetry.kubernetes_objects_count.keys()), 0
        )
        self.assertEqual(len(chaos_telemetry.network_plugins), 0)
        self.lib_telemetry.collect_cluster_metadata(chaos_telemetry)
        self.assertNotEqual(len(chaos_telemetry.node_infos), 0)
        self.assertNotEqual(chaos_telemetry.node_count, 0)
        self.assertNotEqual(
            len(chaos_telemetry.kubernetes_objects_count.keys()), 0
        )
        self.assertNotEqual(len(chaos_telemetry.network_plugins), 0)

    def test_send_telemetry(self):
        request_id = f"test_folder/{int(time.time())}"
        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://ulnmf9xv7j.execute-api.us-west-2.amazonaws.com/production",  # NOQA
            "backup_threads": 6,
            "archive_path": request_id,
            "prometheus_backup": "True",
            "enabled": True,
        }
        chaos_telemetry = ChaosRunTelemetry()
        self.lib_telemetry.collect_cluster_metadata(chaos_telemetry)
        try:
            self.lib_telemetry.send_telemetry(
                telemetry_config, request_id, chaos_telemetry
            )
        except Exception as e:
            self.assertTrue(False, f"send_telemetry raised exception {str(e)}")
        s3 = boto3.client("s3")

        bucket_name = os.getenv("BUCKET_NAME")
        remote_files = s3.list_objects_v2(
            Bucket=bucket_name, Prefix=request_id
        )
        self.assertTrue("Contents" in remote_files.keys())
        self.assertEqual(
            remote_files["Contents"][0]["Key"],
            f"{request_id}/telemetry.json",
        )

    def test_get_bucket_url_for_filename(self):
        test_workdir = f"test_folder/{int(time.time())}"
        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://ulnmf9xv7j.execute-api.us-west-2.amazonaws.com/production",  # NOQA
            "backup_threads": 6,
            "archive_path": test_workdir,
            "prometheus_backup": "True",
            "enabled": True,
        }
        with tempfile.NamedTemporaryFile() as file:
            file_content = self.get_random_string(100).encode("utf-8")
            file.write(file_content)
            file.flush()

            try:
                url = self.lib_telemetry.get_bucket_url_for_filename(
                    f'{telemetry_config["api_url"]}/presigned-url',
                    test_workdir,
                    os.path.basename(file.name),
                    telemetry_config["username"],
                    telemetry_config["password"],
                )
                self.lib_telemetry.put_file_to_url(url, file.name)

                bucket_name = os.getenv("BUCKET_NAME")
                s3 = boto3.client("s3")
                remote_files = s3.list_objects_v2(
                    Bucket=bucket_name, Prefix=test_workdir
                )
                self.assertTrue("Contents" in remote_files.keys())
                self.assertEqual(
                    remote_files["Contents"][0]["Key"],
                    f"{test_workdir}/{os.path.basename(file.name)}",
                )
            except Exception as e:
                self.assertTrue(False, f"test failed with exception: {str(e)}")

    def _test_put_ocp_logs(self):
        ##################################################
        # This test is incomplete and inactive because   #
        # we don't have an OCP Integration     env yet.  #
        ##################################################

        krkn_kubernetes = KrknKubernetes(
            kubeconfig_path="~/OCP/auth/kubeconfig"
        )
        safe_logger = SafeLogger()
        krkn_telemetry = KrknTelemetry(safe_logger, krkn_kubernetes)

        test_workdir = "/tmp/"
        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://ulnmf9xv7j.execute-api.us-west-2.amazonaws.com/production",  # NOQA
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
        krkn_telemetry.put_ocp_logs(
            f"test-must-gather-{str(uuid.uuid1())}",
            telemetry_config,
            int(ten_minutes_ago.timestamp()),
            int(ten_minutes_fwd.timestamp()),
        )


if __name__ == "__main__":
    unittest.main()
