import base64
import os
import tempfile
import time
import unittest
import uuid

import boto3
import yaml

from krkn_lib.models.krkn import ChaosRunAlert, ChaosRunAlertSummary
from krkn_lib.models.telemetry import ChaosRunTelemetry, ScenarioTelemetry
from krkn_lib.tests import BaseTest


class KrknTelemetryKubernetesTests(BaseTest):
    def test_set_parameters_base_64(self):
        file_path = "src/testdata/input.yaml"
        scenario_telemetry = ScenarioTelemetry()

        config = self.lib_telemetry_k8s.set_parameters_base64(
            scenario_telemetry, file_path
        )

        self.assertTrue(isinstance(config, dict))
        self.assertGreater(len(config.keys()), 0)
        with open(file_path, "rb") as file_stream:
            input_file_data_orig = file_stream.read().decode("utf-8")
            self.assertIsNotNone(input_file_data_orig)

        input_file_yaml_orig = yaml.safe_load(input_file_data_orig)
        input_file_yaml_processed = yaml.safe_load(
            base64.b64decode(
                scenario_telemetry.parameters_base64.encode()
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
        bucket_folder = f"{int(time.time())}"
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
            "api_url": "https://9ead3157ti.execute-api.us-west-2.amazonaws.com/dev",  # NOQA
            "backup_threads": 6,
            "archive_path": test_workdir,
            "prometheus_backup": "True",
            "telemetry_group": "default",
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
        self.lib_telemetry_k8s.put_prometheus_data(
            telemetry_config, file_list, bucket_folder
        )

        s3 = boto3.client("s3")
        bucket_name = os.getenv("BUCKET_NAME")
        self.assertTrue(bucket_name)
        remote_files = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f'{telemetry_config["telemetry_group"]}/{bucket_folder}',
        )
        self.assertEqual(len(remote_files["Contents"]), len(file_list))

    def test_collect_cluster_metadata(self):
        chaos_telemetry = ChaosRunTelemetry()
        self.assertEqual(len(chaos_telemetry.node_summary_infos), 0)
        self.assertEqual(chaos_telemetry.total_node_count, 0)
        self.assertEqual(
            len(chaos_telemetry.kubernetes_objects_count.keys()), 0
        )
        self.assertEqual(len(chaos_telemetry.network_plugins), 1)
        self.assertEqual(chaos_telemetry.network_plugins[0], "Unknown")
        self.lib_telemetry_k8s.collect_cluster_metadata(chaos_telemetry)
        self.assertNotEqual(len(chaos_telemetry.node_summary_infos), 0)
        self.assertNotEqual(chaos_telemetry.total_node_count, 0)
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
            "api_url": "https://9ead3157ti.execute-api.us-west-2.amazonaws.com/dev",  # NOQA
            "backup_threads": 6,
            "archive_path": request_id,
            "prometheus_backup": "True",
            "enabled": True,
            "telemetry_group": "default",
        }
        chaos_telemetry = ChaosRunTelemetry()
        self.lib_telemetry_k8s.collect_cluster_metadata(chaos_telemetry)
        try:
            self.lib_telemetry_k8s.send_telemetry(
                telemetry_config, request_id, chaos_telemetry
            )
        except Exception as e:
            self.assertTrue(False, f"send_telemetry raised exception {str(e)}")
        s3 = boto3.client("s3")

        bucket_name = os.getenv("BUCKET_NAME")
        remote_files = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f'{telemetry_config["telemetry_group"]}/{request_id}',
        )
        self.assertTrue("Contents" in remote_files.keys())
        self.assertEqual(
            remote_files["Contents"][0]["Key"],
            f'{telemetry_config["telemetry_group"]}/'
            f"{request_id}/telemetry.json",
        )

    def test_put_alerts(self):

        request_id = f"test_folder/{int(time.time())}"
        telemetry_config = {
            "events_backup": True,
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://9ead3157ti.execute-api.us-west-2.amazonaws.com/dev",  # NOQA
            "backup_threads": 6,
            "telemetry_group": "default",
        }
        summary = ChaosRunAlertSummary()
        alert = ChaosRunAlert("testAlert", "testState", "default", "critical")
        summary.chaos_alerts.append(alert)
        self.lib_telemetry_k8s.put_critical_alerts(
            request_id, telemetry_config, summary
        )

        bucket_name = os.getenv("BUCKET_NAME")
        s3 = boto3.client("s3")
        remote_files = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f'{telemetry_config["telemetry_group"]}/{request_id}',
        )
        self.assertTrue("Contents" in remote_files.keys())
        self.assertEqual(
            remote_files["Contents"][0]["Key"],
            f'{telemetry_config["telemetry_group"]}/'
            f"{request_id}/critical-alerts-00.log",
        )

    def test_get_bucket_url_for_filename(self):
        test_workdir = f"default/test_folder/{int(time.time())}"
        telemetry_config = {
            "username": os.getenv("API_USER"),
            "password": os.getenv("API_PASSWORD"),
            "max_retries": 5,
            "api_url": "https://9ead3157ti.execute-api.us-west-2.amazonaws.com/dev",  # NOQA
            "backup_threads": 6,
            "archive_path": test_workdir,
            "prometheus_backup": "True",
            "enabled": True,
            "telemetry_group": "default",
        }
        with tempfile.NamedTemporaryFile() as file:
            file_content = self.get_random_string(100).encode("utf-8")
            file.write(file_content)
            file.flush()

            try:
                url = self.lib_telemetry_k8s.get_bucket_url_for_filename(
                    f'{telemetry_config["api_url"]}/presigned-url',
                    test_workdir,
                    os.path.basename(file.name),
                    telemetry_config["username"],
                    telemetry_config["password"],
                )
                self.lib_telemetry_k8s.put_file_to_url(url, file.name)

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


if __name__ == "__main__":
    unittest.main()
