from krkn_lib.models.k8s import (
    AffectedNode,
    AffectedNodeStatus,
    AffectedPod,
    PodsStatus,
)
from krkn_lib.tests import BaseTest


class TestKrknKubernetesModels(BaseTest):
    def test_pods_status(self):
        pods_status_1 = PodsStatus()
        pods_status_2 = PodsStatus()
        pods_status_merge = PodsStatus()

        pods_status_1.recovered.append(
            AffectedPod(pod_name="test_1", namespace="default")
        )
        pods_status_1.recovered.append(
            AffectedPod(pod_name="test_2", namespace="default")
        )

        pods_status_1.unrecovered.append(
            AffectedPod(pod_name="test_1_unrecovered", namespace="default")
        )
        pods_status_1.unrecovered.append(
            AffectedPod(pod_name="test_2_unrecovered", namespace="default")
        )

        pods_status_2.recovered.append(
            AffectedPod(pod_name="test_3", namespace="default")
        )
        pods_status_2.recovered.append(
            AffectedPod(pod_name="test_4", namespace="default")
        )
        pods_status_2.unrecovered.append(
            AffectedPod(pod_name="test_3_unrecovered", namespace="default")
        )
        pods_status_2.unrecovered.append(
            AffectedPod(pod_name="test_4_unrecovered", namespace="default")
        )

        pods_status_merge.merge(pods_status_1)
        pods_status_merge.merge(pods_status_2)

        for index in range(4):
            self.assertTrue(
                f"test_{index+1}"
                in [p.pod_name for p in pods_status_merge.recovered]
            )
        for index in range(4):
            self.assertTrue(
                f"test_{index+1}_unrecovered"
                in [p.pod_name for p in pods_status_merge.unrecovered]
            )

    def test_nodes_status(self):
        nodes_status_1 = AffectedNodeStatus()

        affected_node = AffectedNode(node_name="test_1")
        affected_node.set_affected_node_status("False", 0.737)
        affected_node.set_affected_node_status("True", 0.12)
        nodes_status_1.affected_nodes.append(affected_node)

        affected_node2 = AffectedNode(node_name="test_1")
        affected_node2.set_affected_node_status("True", 0.12)
        affected_node2.set_affected_node_status("running", 0.11)
        
        nodes_status_1.affected_nodes.append(affected_node2)
        self.assertEqual(len(nodes_status_1.affected_nodes), 2)
        nodes_status_1.merge_affected_nodes()

        self.assertEqual(len(nodes_status_1.affected_nodes), 1)
        self.assertEqual(nodes_status_1.affected_nodes[0].node_name, "test_1")
        self.assertEqual(
            nodes_status_1.affected_nodes[0].ready_time, 0.24
        )
        self.assertEqual(
            nodes_status_1.affected_nodes[0].not_ready_time, 0.737
        )
        self.assertEqual(
            nodes_status_1.affected_nodes[0].running_time, 0.11
        )