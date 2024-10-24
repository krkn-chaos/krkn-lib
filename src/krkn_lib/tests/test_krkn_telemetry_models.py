import json
import unittest

from krkn_lib.models.telemetry import (
    ChaosRunTelemetry,
    ClusterEvent,
    ScenarioTelemetry,
)


class KrknTelemetryModelsTests(unittest.TestCase):
    def test_scenario_telemetry(self):
        test_valid_json = """
        {
            "start_timestamp": 1686141432,
            "end_timestamp": 1686141435,
            "scenario": "test",
            "exit_status": 0,
            "parameters_base64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0",
            "cluster_events":[
                {
                    "name":"test",
                    "creation":"2024-09-02T14:00:53Z",
                    "reason":"Failed",
                    "message":"message",
                    "namespace":"default",
                    "source_component":"kubelet",
                    "involved_object_kind":"Pod",
                    "involved_object_name":"test",
                    "involved_object_namespace":"default",
                    "type":"Normal"
                }
            ],
            "affected_pods":{
                "recovered":[
                    {
                        "pod_name":"test-pod",
                        "namespace":"test-namespace",
                        "pod_rescheduling_time":9.8,
                        "pod_readiness_time":2.71,
                        "total_recovery_time":3.14
                    }
                ],
                "unrecovered":[
                    {
                        "pod_name":"failed-pod-1",
                        "namespace":"failed-namespace"
                    },
                    {
                        "pod_name":"failed-pod-2",
                        "namespace":"failed-namespace"
                    }
                ]
             }
        }
        """  # NOQA
        # wrong base64 format
        test_invalid_json_wrong_base64 = """
        {
            "start_timestamp": 1686141432,
            "end_timestamp": 1686141435,
            "scenario": "test",
            "exit_status": 0,
            "parameters_base64": "I'm a wrong base64"
        }
        """

        test_invalid_base64_bad_format = """
        {
            "start_timestamp": 1686141432,
            "end_timestamp": 1686141435,
            "scenario": "test",
            "exit_status": 0,
            "parameters_base64": "SSdtIG5vdCBhIGdvb2Qgc3RyaW5nIDstXA=="
        }

        """
        json_obj = json.loads(test_valid_json)

        telemetry = ScenarioTelemetry(json_obj)
        self.assertEqual(telemetry.start_timestamp, 1686141432)
        self.assertEqual(telemetry.end_timestamp, 1686141435)
        self.assertEqual(telemetry.scenario, "test")
        self.assertEqual(telemetry.exit_status, 0)
        self.assertIsNotNone(telemetry.affected_pods)
        self.assertEqual(len(telemetry.affected_pods.recovered), 1)
        self.assertEqual(len(telemetry.affected_pods.unrecovered), 2)
        for recovered in telemetry.affected_pods.recovered:
            self.assertIsNotNone(recovered.pod_name)
            self.assertIsNotNone(recovered.namespace)
            self.assertIsNotNone(recovered.pod_readiness_time)
            self.assertIsNotNone(recovered.pod_rescheduling_time)
            self.assertIsNotNone(recovered.total_recovery_time)
        for unrecovered in telemetry.affected_pods.unrecovered:
            self.assertIsNotNone(unrecovered.pod_name)
            self.assertIsNotNone(unrecovered.namespace)
            self.assertIsNone(unrecovered.pod_readiness_time)
            self.assertIsNone(unrecovered.pod_rescheduling_time)
            self.assertIsNone(unrecovered.total_recovery_time)
        self.assertIsNotNone(telemetry.parameters)
        self.assertEqual(telemetry.parameters_base64, "")
        self.assertEqual(telemetry.parameters["property"]["unit"], "unit")
        self.assertEqual(telemetry.parameters["property"]["test"], "test")
        self.assertTrue(isinstance(telemetry.cluster_events, list))
        self.assertTrue(isinstance(telemetry.cluster_events[0], ClusterEvent))

        json_str = telemetry.to_json()
        self.assertIsNotNone(json_str)

        with self.assertRaises(Exception):
            ScenarioTelemetry(json.loads(test_invalid_json_wrong_base64))
        with self.assertRaises(Exception):
            ScenarioTelemetry(json.loads(test_invalid_base64_bad_format))
        try:
            # with empty constructor all the props must be available
            telemetry_empty_constructor = ScenarioTelemetry()
            self.assertIsNotNone(telemetry_empty_constructor)
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "start_timestamp")
            )
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "end_timestamp")
            )
            self.assertTrue(hasattr(telemetry_empty_constructor, "scenario"))
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "exit_status")
            )
            self.assertTrue(
                hasattr(telemetry_empty_constructor, "parameters_base64")
            )
            self.assertTrue(hasattr(telemetry_empty_constructor, "parameters"))
        except Exception:
            self.fail("constructor raised Exception unexpectedly!")

    def test_chaos_run_telemetry(self):
        test_valid_json = """
        {
            "scenarios": [{
                            "start_timestamp": 1686141432,
                            "end_timestamp": 1686141435,
                            "scenario": "test",
                            "exit_status": 0,
                            "parameters_base64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        },
                        {
                            "start_timestamp": 1686141432,
                            "end_timestamp": 1686141435,
                            "scenario": "test",
                            "exit_status": 0,
                            "parameters_base64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        }],
            "node_summary_infos": [{
                    "name": "test_node"
                }],
            "node_taints": [{
                        "node_name": "test_node",
                        "key": "key",
                        "value": "value",
                        "effect": "NoSchedule"
            }]
            
        }
        """  # NOQA

        test_invalid_json_scenarios_format = """
        {
            "scenarios":{
                        "start_timestamp": 1686141432,
                        "end_timestamp": 1686141435,
                        "scenario": "test",
                        "exit_status": 0,
                        "parameters_base64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        }
        }
        """  # NOQA

        test_invalid_json_scenarios_element = """
        {
            "scenarios": [{
                            "start_timestamp": 1686141432,
                            "end_timestamp": 1686141435,
                            "scenario": "test",
                            "exit_status": 0,
                            "parameters_base64": "cHJvcGVydHk6CiAgICB1bml0OiB1bml0CiAgICB0ZXN0OiB0ZXN0"
                        },
                        {
                            "start_timestamp": 1686141432,
                            "end_timestamp": 1686141435,
                            "scenario": "test",
                            "exit_status": 0,
                            "parameters_base64": "SSdtIG5vdCBhIGdvb2Qgc3RyaW5nIDstXA=="
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
            self.assertEqual(scenario.parameters_base64, "")

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

    def test_cluster_event(self):

        k8s_json = r"""
{
   "metadata":{
      "name":"test-sriosfvqni.17f172291963a5d1",
      "namespace":"test-fqjmcwgfam",
      "uid":"40e6930d-005e-4094-8861-1b9502591b69",
      "resourceVersion":"155813",
      "creationTimestamp":"2024-09-02T14:00:53Z",
      "managedFields":[
         {
            "manager":"kubelet",
            "operation":"Update",
            "apiVersion":"v1",
            "time":"2024-09-02T14:00:53Z",
            "fieldsType":"FieldsV1",
            "fieldsV1":{
               "f:count":{
                  
               },
               "f:firstTimestamp":{
                  
               },
               "f:involvedObject":{
                  
               },
               "f:lastTimestamp":{
                  
               },
               "f:message":{
                  
               },
               "f:reason":{
                  
               },
               "f:source":{
                  "f:component":{
                     
                  },
                  "f:host":{
                     
                  }
               },
               "f:type":{
                  
               }
            }
         }
      ]
   },
   "involvedObject":{
      "kind":"Pod",
      "namespace":"test-fqjmcwgfam",
      "name":"test-sriosfvqni",
      "uid":"afd2d26a-7bd8-4654-b575-8052d308f72a",
      "apiVersion":"v1",
      "resourceVersion":"155805",
      "fieldPath":"spec.containers{readiness}"
   },
   "reason":"Failed",
   "message":"Successfully pulled image in 1.744370722s (1.744374443s including waiting)",
   "source":{
      "component":"kubelet",
      "host":"minikube"
   },
   "firstTimestamp":"2024-09-02T14:00:53Z",
   "lastTimestamp":"2024-09-02T14:00:53Z",
   "count":1,
   "type":"Normal",
   "eventTime":null,
   "reportingComponent":"",
   "reportingInstance":""
}
        """  # NOQA

        krkn_json = """
{
    "name":"test",
    "creation":"2024-09-02T14:00:53Z",
    "reason":"Failed",
    "message":"message",
    "namespace":"default",
    "source_component":"kubelet",
    "involved_object_kind":"Pod",
    "involved_object_name":"test",
    "involved_object_namespace":"default",
    "type":"Normal"
}
    """  # NOQA

        event = ClusterEvent(k8s_json_dict=json.loads(k8s_json))
        self.assertEqual(event.name, "test-sriosfvqni.17f172291963a5d1")
        self.assertEqual(event.creation, "2024-09-02T14:00:53Z")
        self.assertEqual(event.reason, "Failed")
        self.assertEqual(
            event.message,
            "Successfully pulled image in "
            "1.744370722s (1.744374443s including waiting)",
        )
        self.assertEqual(event.namespace, "test-fqjmcwgfam")
        self.assertEqual(event.source_component, "kubelet")
        self.assertEqual(event.involved_object_kind, "Pod")
        self.assertEqual(event.involved_object_name, "test-sriosfvqni")
        self.assertEqual(event.involved_object_namespace, "test-fqjmcwgfam")
        self.assertEqual(event.type, "Normal")

        event = ClusterEvent(json_dict=json.loads(krkn_json))
        self.assertEqual(event.name, "test")
        self.assertEqual(event.creation, "2024-09-02T14:00:53Z")
        self.assertEqual(event.reason, "Failed")
        self.assertEqual(
            event.message,
            "message",
        )
        self.assertEqual(event.namespace, "default")
        self.assertEqual(event.source_component, "kubelet")
        self.assertEqual(event.involved_object_kind, "Pod")
        self.assertEqual(event.involved_object_name, "test")
        self.assertEqual(event.involved_object_namespace, "default")
        self.assertEqual(event.type, "Normal")


if __name__ == "__main__":
    unittest.main()
