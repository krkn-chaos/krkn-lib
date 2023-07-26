import base64
import unittest
import uuid
from tempfile import NamedTemporaryFile

import yaml
from kubernetes import config

from krkn_lib_kubernetes import (
    KrknTelemetry,
    ScenarioTelemetry,
    KrknLibKubernetes,
)


class KrknTelemetryTests(unittest.TestCase):
    lib_telemetry: KrknTelemetry
    lib_k8s: KrknLibKubernetes

    @classmethod
    def setUpClass(cls):
        cls.lib_telemetry = KrknTelemetry()
        cls.lib_k8s = KrknLibKubernetes(config.KUBE_CONFIG_DEFAULT_LOCATION)

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
        telemetry = KrknTelemetry()
        telemetry.set_parameters_base64(scenario_telemetry, file_path)
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
        test_string = "Tester McTesty!"
        with tempfile.NamedTemporaryFile() as src, tempfile.NamedTemporaryFile() as dst:  # NOQA
            with open(src.name, "w+") as source, open(dst.name, "w+") as dest:
                encoded_test_byte = base64.b64encode(
                    test_string.encode("utf-8")
                )
                source.write(encoded_test_byte.decode("utf-8"))
                source.flush()
                self.lib_telemetry.decode_base64_file(source.name, dest.name)
                test_read = dest.read()
                self.assertEqual(test_string, test_read)

    def test_upload_multipart_b64_prometheus_archives(self):
        test_string = "Tester McTesty!"
        filename = f"/tmp/{str(uuid.uuid1())}.b64"
        with open(filename, "wb+") as source:
            encoded_test_byte = base64.b64encode(test_string.encode("utf-8"))
            source.write(encoded_test_byte)
            source.flush()
            telemetry_config = {
                "username": "test",
                "password": "test",
                "api_url": "http://localhost:5000/prometheus",
                "prometheus_backup": "True",
                "backup_threads": "1",
            }
            archive_volumes = [(0, filename)]
            request_id = "test_upload"

            self.lib_telemetry.upload_multipart_b64_prometheus_archives(
                telemetry_config, archive_volumes, request_id
            )


if __name__ == "__main__":
    unittest.main()
