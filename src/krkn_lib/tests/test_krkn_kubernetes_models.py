from krkn_lib.models.k8s import (
    AffectedNode,
    AffectedNodeStatus,
    AffectedPod,
    PodsStatus,
)
from krkn_lib.models.krkn import HogConfig, HogType
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

    def test_hog_config(self):
        wrong_type = {"hog-type": "io_wrong", "node-selector": "test"}
        with self.assertRaises(KeyError):
            HogConfig.from_yaml_dict(wrong_type)

        wrong_type = {"hog-type": "", "node-selector": "test"}
        with self.assertRaises(Exception):
            HogConfig.from_yaml_dict(wrong_type)

        memory_config = {
            "duration": 14,
            "workers": 23,
            "hog-type": "memory",
            "image": "testimage",
            "namespace": "testnamespace",
            "memory-vm-bytes": "99%",
            "node-selector": "test-selector",
            "taints": ["example-key:NoSchedule"],
        }

        config = HogConfig.from_yaml_dict(memory_config)
        self.assertEqual(config.duration, 14)
        self.assertEqual(config.workers, 23)
        self.assertEqual(config.type, HogType.memory)
        self.assertEqual(config.image, "testimage")
        self.assertEqual(config.namespace, "testnamespace")
        self.assertEqual(config.memory_vm_bytes, "99%")
        self.assertEqual(config.node_selector, "test-selector")
        self.assertEqual(
            config.tolerations,
            [
                {
                    "key": "example-key",
                    "operator": "Exists",
                    "effect": "NoSchedule",
                }
            ],
        )
        io_config_volume = {
            "name": "test-volume",
            "hostPath": {"path": "/test-path"},
        }
        io_config = {
            "duration": 15,
            "workers": 24,
            "hog-type": "io",
            "image": "testimage",
            "namespace": "testnamespace",
            "io-block-size": "15m",
            "io-write-bytes": "16m",
            "io-target-pod-folder": "/test-path",
            "io-target-pod-volume": io_config_volume,
            "node-selector": "test-selector",
            "taints": [],
        }

        config = HogConfig.from_yaml_dict(io_config)
        self.assertEqual(config.duration, 15)
        self.assertEqual(config.workers, 24)
        self.assertEqual(config.type, HogType.io)
        self.assertEqual(config.image, "testimage")
        self.assertEqual(config.namespace, "testnamespace")
        self.assertEqual(config.io_block_size, "15m")
        self.assertEqual(config.io_write_bytes, "16m")
        self.assertEqual(config.io_target_pod_folder, "/test-path")
        self.assertEqual(config.io_target_pod_volume, io_config_volume)
        self.assertEqual(config.node_selector, "test-selector")
        self.assertEqual(config.tolerations, [])

        memory_config = {
            "duration": 44,
            "workers": 45,
            "hog-type": "memory",
            "image": "testimage",
            "namespace": "testnamespace",
            "memory-vm-bytes": "95%",
            "node-selector": "test-selector",
        }

        config = HogConfig.from_yaml_dict(memory_config)
        self.assertEqual(config.duration, 44)
        self.assertEqual(config.workers, 45)
        self.assertEqual(config.type, HogType.memory)
        self.assertEqual(config.image, "testimage")
        self.assertEqual(config.namespace, "testnamespace")
        self.assertEqual(config.memory_vm_bytes, "95%")
        self.assertEqual(config.node_selector, "test-selector")
        self.assertEqual(config.tolerations, [])

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
        self.assertEqual(nodes_status_1.affected_nodes[0].ready_time, 0.24)
        self.assertEqual(
            nodes_status_1.affected_nodes[0].not_ready_time, 0.737
        )
        self.assertEqual(nodes_status_1.affected_nodes[0].running_time, 0.11)
