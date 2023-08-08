import base64
import os
import tempfile

# import time
import unittest

# import uuid

# import boto3
import yaml

from krkn_lib_kubernetes import ScenarioTelemetry
from krkn_lib_kubernetes.tests.base_test import BaseTest


class KrknTelemetryTests(BaseTest):
    def test_deep_set_attribute(self):
        deep_yaml = """
            test:
                - element: __MARKER__
                  property_1: test
                  property_2: test
                  obj_1:
                    element: __MARKER__
                    obj_1:
                        element: __MARKER__
                        property_1: test
                        property_2:
                            - property_3: test
                              property_4: test
                            - property_5:
                                element: __MARKER__
            """  # NOQA

        deep_obj = yaml.safe_load(deep_yaml)
        self.lib_telemetry.deep_set_attribute(
            "element", "__UPDATED__", deep_obj
        )

        unserialized_updated_object = yaml.safe_dump(deep_obj, indent=4)
        self.assertEqual(unserialized_updated_object.count("__UPDATED__"), 4)
        self.assertEqual(unserialized_updated_object.count("__MARKER__"), 0)

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

    def test_decode_base64_file(self):
        test_workdir = os.getenv("TEST_WORKDIR")
        test_string = "Tester McTesty!"
        with tempfile.NamedTemporaryFile(
            dir=test_workdir
        ) as src, tempfile.NamedTemporaryFile(
            dir=test_workdir
        ) as dst:  # NOQA
            with open(src.name, "w+") as source, open(dst.name, "w+") as dest:
                encoded_test_byte = base64.b64encode(
                    test_string.encode("utf-8")
                )
                source.write(encoded_test_byte.decode("utf-8"))
                source.flush()
                self.lib_telemetry.decode_base64_file(source.name, dest.name)
                test_read = dest.read()
                self.assertEqual(test_string, test_read)

    # def test_upload_download_prometheus(self):
    #     namespace = "test-" + self.get_random_string(10)
    #     self.deploy_namespace(namespace, [])
    #     self.deploy_fedtools(namespace=namespace)
    #     count = 0
    #     MAX_RETRIES = 5
    #     while not self.lib_k8s.is_pod_running("fedtools", namespace):
    #         if count > MAX_RETRIES:
    #             self.assertFalse(True, "container failed to become ready")
    #         count += 1
    #         time.sleep(3)
    #         continue
    #
    #     prometheus_pod_name = "fedtools"
    #     prometheus_container_name = "fedtools"
    #     prometheus_namespace = namespace
    #     bucket_folder = f"test_folder/{int(time.time())}"
    #     test_workdir = os.getenv("TEST_WORKDIR")
    #
    #     # raises exception if archive path does not exist
    #     with self.assertRaises(Exception):
    #         self.lib_k8s.archive_and_get_path_from_pod(
    #             prometheus_pod_name,
    #             prometheus_container_name,
    #             prometheus_namespace,
    #             "/does_not_exist",
    #             "/test",
    #             str(uuid.uuid1()),
    #             archive_part_size=100,
    #             download_path=test_workdir,
    #         )
    #
    #     # raises exception if target path does not exist
    #     with self.assertRaises(Exception):
    #         self.lib_k8s.archive_and_get_path_from_pod(
    #             prometheus_pod_name,
    #             prometheus_container_name,
    #             prometheus_namespace,
    #             "/tmp",
    #             "/does_not_exist",
    #             str(uuid.uuid1()),
    #             archive_part_size=100,
    #             download_path=test_workdir,
    #         )
    #
    #     # raises exception if target pod does not exist
    #     with self.assertRaises(Exception):
    #         self.lib_k8s.archive_and_get_path_from_pod(
    #             "does_not_exist",
    #             prometheus_container_name,
    #             prometheus_namespace,
    #             "/tmp",
    #             "/does_not_exist",
    #             str(uuid.uuid1()),
    #             archive_part_size=100,
    #             download_path=test_workdir,
    #         )
    #
    #     # raises exception if target container does not exist
    #     with self.assertRaises(Exception):
    #         self.lib_k8s.archive_and_get_path_from_pod(
    #             prometheus_pod_name,
    #             "does_not_exist",
    #             prometheus_namespace,
    #             "/tmp",
    #             "/does_not_exist",
    #             str(uuid.uuid1()),
    #             archive_part_size=100,
    #             download_path=test_workdir,
    #         )
    #
    #     # raises exception if target namespace does not exist
    #     with self.assertRaises(Exception):
    #         self.lib_k8s.archive_and_get_path_from_pod(
    #             prometheus_pod_name,
    #             prometheus_container_name,
    #             "does_not_exist",
    #             "/tmp",
    #             "/does_not_exist",
    #             str(uuid.uuid1()),
    #             archive_part_size=100,
    #             download_path=test_workdir,
    #         )
    #
    #     # happy path:
    #     # - creates a dummy file in the pod
    #     # - downloads it as multivolume tar
    #     # - uploads on s3
    #     # - check if all the files are updated in the bucket
    #     # create folder
    #     self.lib_k8s.exec_cmd_in_pod(
    #         ["mkdir /test"], "fedtools", namespace, "fedtools"
    #     )
    #     # create test file
    #     self.lib_k8s.exec_cmd_in_pod(
    #         ["dd if=/dev/urandom of=/test/test.bin bs=1024 count=500"],
    #         "fedtools",
    #         namespace,
    #         "fedtools",
    #     )
    #
    #     telemetry_config = {
    #         "username": os.getenv("API_USER"),
    #         "password": os.getenv("API_PASSWORD"),
    #         "max_retries": 5,
    #         "api_url": "https://ulnmf9xv7j.execute-api.us-west-2.amazonaws.com/production",  # NOQA
    #         "backup_threads": "6",
    #         "archive_path": "/tmp/prometheus",
    #         "prometheus_backup": "True",
    #     }
    #
    #     file_list = self.lib_k8s.archive_and_get_path_from_pod(
    #         prometheus_pod_name,
    #         prometheus_container_name,
    #         prometheus_namespace,
    #         "/tmp",
    #         "/test",
    #         str(uuid.uuid1()),
    #         archive_part_size=100,
    #         download_path=test_workdir,
    #     )
    #     self.lib_telemetry.put_ocp_prometheus_data(
    #         telemetry_config, file_list, bucket_folder
    #     )
    #
    #     s3 = boto3.client("s3")
    #     bucket_name = os.getenv("BUCKET_NAME")
    #     remote_files = s3.list_objects_v2(
    #         Bucket=bucket_name, Prefix=bucket_folder
    #     )
    #     self.assertEqual(len(remote_files["Contents"]), len(file_list))


if __name__ == "__main__":
    unittest.main()
