from krkn_lib.models.k8s import AffectedPod, PodsStatus
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
