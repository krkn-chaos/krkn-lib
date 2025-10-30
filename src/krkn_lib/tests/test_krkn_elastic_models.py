import uuid

from krkn_lib.models.elastic.models import ElasticChaosRunTelemetry
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.tests import BaseTest
import datetime


class TestKrknElasticModels(BaseTest):

    def check_test_ElasticChaosRunTelemetry(
        self, elastic_telemetry: ElasticChaosRunTelemetry, run_uuid: str
    ):

        self.assertTrue(elastic_telemetry.job_status)
        self.assertEqual(len(elastic_telemetry.scenarios), 1)
        # scenarios
        self.assertEqual(
            elastic_telemetry.scenarios[0].start_timestamp, 1628493021.0
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0].end_timestamp, 1628496621.0
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0].scenario, "example_scenario.yaml"
        )
        self.assertEqual(elastic_telemetry.scenarios[0].exit_status, 0)
        self.assertEqual(elastic_telemetry.scenarios[0].parameters_base64, "")
        self.assertEqual(
            elastic_telemetry.scenarios[0].parameters,
            self.get_ChaosRunTelemetry_json(run_uuid).get("scenarios")[0][
                "parameters"
            ],
        )

        # scenarios -> affected_pods
        self.assertEqual(
            len(elastic_telemetry.scenarios[0].affected_pods.recovered), 1
        )
        self.assertEqual(
            len(elastic_telemetry.scenarios[0].affected_pods.unrecovered), 1
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_pods.error, "some error"
        )

        # scenarios -> affected_pods -> recovered
        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_pods.recovered[0].pod_name,
            "pod1",
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.recovered[0]
            .namespace,
            "default",
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.recovered[0]
            .total_recovery_time,
            10.0,
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.recovered[0]
            .pod_readiness_time,
            5.0,
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.recovered[0]
            .pod_rescheduling_time,
            2.0,
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_pods.recovered[0].pod_name,
            "pod1",
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_pods.recovered[0].pod_name,
            "pod1",
        )

        # scenarios -> affected_pods -> unrecovered
        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.unrecovered[0]
            .pod_name,
            "pod2",
        )
        self.assertEqual(
            elastic_telemetry.scenarios[0]
            .affected_pods.unrecovered[0]
            .namespace,
            "default",
        )
        print(
            "elastic affected nodes"
            + str(
                elastic_telemetry.scenarios[0].affected_nodes[0].not_ready_time
            )
        )
        # affected_nodes
        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].node_name,
            "kind-control-plane",
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].node_id,
            "test",
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].ready_time,
            2.71,
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].not_ready_time,
            3.14,
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].stopped_time,
            0,
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].running_time,
            0,
        )

        self.assertEqual(
            elastic_telemetry.scenarios[0].affected_nodes[0].terminating_time,
            0,
        )

        # node_summary_infos
        self.assertEqual(len(elastic_telemetry.node_summary_infos), 1)

        self.assertEqual(elastic_telemetry.node_summary_infos[0].count, 5)
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].architecture, "aarch64"
        )
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].instance_type, "m2i.xlarge"
        )
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].nodes_type, "master"
        )
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].kernel_version,
            "5.4.0-66-generic",
        )
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].kubelet_version, "v2.1.2"
        )
        self.assertEqual(
            elastic_telemetry.node_summary_infos[0].os_version, "Linux"
        )

        # node_taints
        self.assertEqual(len(elastic_telemetry.node_taints), 1)

        self.assertEqual(
            elastic_telemetry.node_taints[0].key,
            "node.kubernetes.io/unreachable",
        )
        self.assertEqual(elastic_telemetry.node_taints[0].value, "NoExecute")
        self.assertEqual(elastic_telemetry.node_taints[0].effect, "NoExecute")

        # objects_count
        self.assertEqual(
            len(elastic_telemetry.kubernetes_objects_count.to_dict().keys()), 2
        )
        self.assertEqual(
            elastic_telemetry.kubernetes_objects_count.to_dict().get("Pod"), 5
        )
        self.assertEqual(
            elastic_telemetry.kubernetes_objects_count.to_dict().get(
                "Service"
            ),
            2,
        )

        # network_plugins

        self.assertEqual(len(elastic_telemetry.network_plugins), 1)
        self.assertEqual(elastic_telemetry.network_plugins[0], "Calico")

        # obejct properties
        self.assertEqual(elastic_telemetry.timestamp, "2023-05-22T14:55:02Z")

        # health_check
        self.assertEqual(len(elastic_telemetry.health_checks), 1)
        self.assertEqual(
            elastic_telemetry.health_checks[0].url, "http://example.com"
        )
        self.assertEqual(elastic_telemetry.health_checks[0].status, True)
        self.assertEqual(elastic_telemetry.health_checks[0].status_code, "200")
        self.assertEqual(
            elastic_telemetry.health_checks[0].start_timestamp,
            datetime.datetime.fromisoformat("2025-03-12T14:57:54.706000"),
        )
        self.assertEqual(
            elastic_telemetry.health_checks[0].end_timestamp,
            datetime.datetime.fromisoformat("2025-03-12T15:02:13.819742"),
        )
        self.assertEqual(
            elastic_telemetry.health_checks[0].duration, 259.113742
        )

        # virt_checks
        self.assertEqual(len(elastic_telemetry.virt_checks), 3)
        self.assertEqual(
            elastic_telemetry.virt_checks[0].vm_name, "windows-vm-50"
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[0].ip_address, "0.0.0.0"
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[0].new_ip_address, ""
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[2].new_ip_address, "0.0.0.3"
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[0].namespace, "benchmark-runner"
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[0].node_name, "h03-r660"
        )

        self.assertEqual(elastic_telemetry.virt_checks[0].status, True)
        self.assertEqual(
            elastic_telemetry.virt_checks[0].start_timestamp,
            datetime.datetime.fromisoformat("2025-03-12T14:57:34.555878"),
        )
        self.assertEqual(
            elastic_telemetry.virt_checks[0].end_timestamp,
            datetime.datetime.fromisoformat("2025-03-12T14:57:54.904352"),
        )
        self.assertEqual(elastic_telemetry.virt_checks[0].duration, 20.348474)

        self.assertEqual(elastic_telemetry.total_node_count, 3)
        self.assertEqual(elastic_telemetry.cloud_infrastructure, "AWS")
        self.assertEqual(elastic_telemetry.cloud_type, "EC2")
        self.assertEqual(elastic_telemetry.run_uuid, run_uuid)
        self.assertEqual(
            elastic_telemetry.build_url,
            "https://github.com/krkn-chaos/krkn-lib/actions/runs/16724993547",
        )

    def test_ElasticChaosRunTelemetry(self):
        run_uuid = str(uuid.uuid4())
        example_data = self.get_ChaosRunTelemetry_json(run_uuid)
        telemetry = ChaosRunTelemetry(json_dict=example_data)
        # building from object (to save in elastic)
        elastic_telemetry_object = ElasticChaosRunTelemetry(
            chaos_run_telemetry=telemetry
        )
        # building from dictionary (to retrieve from elastic)
        elastic_telemetry_dic = ElasticChaosRunTelemetry(None, **example_data)

        self.check_test_ElasticChaosRunTelemetry(
            elastic_telemetry_object, run_uuid
        )
        self.check_test_ElasticChaosRunTelemetry(
            elastic_telemetry_dic, run_uuid
        )
