import json
import unittest

from krkn_lib.models.telemetry import ChaosRunTelemetry, ScenarioTelemetry


class KrknTelemetryModelsTests(unittest.TestCase):
    def test_scenario_telemetry(self):
        test_valid_json = """
        {
            "startTimeStamp": 1686141432,
            "endTimeStamp": 1686141435,
            "scenario": "test",
            "exitStatus": 0,
            "parametersBase64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
        }
        """  # NOQA
        # wrong base64 format
        test_invalid_json_wrong_base64 = """
        {
            "startTimeStamp": 1686141432,
            "endTimeStamp": 1686141435,
            "scenario": "test",
            "exitStatus": 0,
            "parametersBase64": "I'm a wrong base64"
        }
        """

        test_invalid_base64_bad_format = """
        {
            "startTimeStamp": 1686141432,
            "endTimeStamp": 1686141435,
            "scenario": "test",
            "exitStatus": 0,
            "parametersBase64": "SSdtIG5vdCBhIGdvb2Qgc3RyaW5nIDstXA=="
        }

        """
        json_obj = json.loads(test_valid_json)

        telemetry = ScenarioTelemetry(json_obj)
        self.assertEqual(telemetry.startTimeStamp, 1686141432)
        self.assertEqual(telemetry.endTimeStamp, 1686141435)
        self.assertEqual(telemetry.scenario, "test")
        self.assertEqual(telemetry.exitStatus, 0)
        self.assertIsNotNone(telemetry.parameters)
        self.assertEqual(telemetry.parametersBase64, "")
        self.assertEqual(telemetry.parameters["property"]["unit"], "unit")
        self.assertEqual(telemetry.parameters["property"]["test"], "test")
        with self.assertRaises(Exception):
            ScenarioTelemetry(json.loads(test_invalid_json_wrong_base64))
        with self.assertRaises(Exception):
            ScenarioTelemetry(json.loads(test_invalid_base64_bad_format))
        try:
            # with empty constructor all the props must be available
            telemetry_empty_constructor = ScenarioTelemetry()
            self.assertIsNotNone(telemetry_empty_constructor)
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "startTimeStamp")
            )
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "endTimeStamp")
            )
            self.assertTrue(hasattr(telemetry_empty_constructor, "scenario"))
            self.assertTrue(hasattr(telemetry_empty_constructor, "exitStatus"))
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "parametersBase64")
            )
            self.assertTrue(hasattr(telemetry_empty_constructor, "parameters"))
        except Exception:
            self.fail("constructor raised Exception unexpectedly!")

    def test_chaos_run_telemetry(self):
        test_valid_json = """
        {
            "scenarios": [{
                            "startTimeStamp": 1686141432,
                            "endTimeStamp": 1686141435,
                            "scenario": "test",
                            "exitStatus": 0,
                            "parametersBase64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        },
                        {
                            "startTimeStamp": 1686141432,
                            "endTimeStamp": 1686141435,
                            "scenario": "test",
                            "exitStatus": 0,
                            "parametersBase64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        }],
            "node_infos": [{
                    "name": "test_node",
                    "taints": [{
                        "key": "key",
                        "value": "value",
                        "effect": "NoSchedule"
                    }]
                }]
        }
        """  # NOQA

        test_invalid_json_scenarios_format = """
        {
            "scenarios":{
                        "startTimeStamp": 1686141432,
                        "endTimeStamp": 1686141435,
                        "scenario": "test",
                        "exitStatus": 0,
                        "parametersBase64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        }
        }
        """  # NOQA

        test_invalid_json_scenarios_element = """
        {
            "scenarios": [{
                            "startTimeStamp": 1686141432,
                            "endTimeStamp": 1686141435,
                            "scenario": "test",
                            "exitStatus": 0,
                            "parametersBase64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        },
                        {
                            "startTimeStamp": 1686141432,
                            "endTimeStamp": 1686141435,
                            "scenario": "test",
                            "exitStatus": 0,
                            "parametersBase64": "SSdtIG5vdCBhIGdvb2Qgc3RyaW5nIDstXA=="
                        }

                       ]
        }
        """  # NOQA

        json_obj = json.loads(test_valid_json)
        telemetry = ChaosRunTelemetry(json_obj)
        self.assertIsNotNone(telemetry)
        self.assertEqual(len(telemetry.scenarios), 2)
        # tests that all scenarios have base64 parameter set to empty string
        for scenario in telemetry.scenarios:
            self.assertEqual(scenario.parametersBase64, "")

        # test deserialization
        try:
            dumped_json = telemetry.to_json()
            self.assertIsNotNone(dumped_json)
        except Exception:
            self.fail("failed to deserialize nested object")

        # passing scenario as an object not as a list
        json_obj = json.loads(test_invalid_json_scenarios_format)
        with self.assertRaises(Exception):
            ChaosRunTelemetry(json_obj)

        # passing scenarios with a wrongly formatted base64 expecting
        # ScenarioTelemetry to raise an exception on initialization
        json_obj = json.loads(test_invalid_json_scenarios_element)
        with self.assertRaises(Exception):
            ChaosRunTelemetry(json_obj)

        try:
            telemetry = ChaosRunTelemetry()
            self.assertIsNotNone(telemetry)
            self.assertTrue(hasattr(telemetry, "scenarios"))
        except Exception:
            self.fail("constructor raised Exception unexpectedly!")


if __name__ == "__main__":
    unittest.main()
