import time
import unittest


from krkn_lib.models.k8s import PodsStatus, AffectedPod
from krkn_lib.models.pod_monitor.models import (
    PodEvent,
    PodStatus,
    MonitoredPod,
    PodsSnapshot,
)


class TestMonitorPodsMonitorModels(unittest.TestCase):
    def test_init_affectedpod(self):
        # Test with required arguments only
        pod = AffectedPod("my-pod", "my-namespace")
        self.assertEqual(pod.pod_name, "my-pod")
        self.assertEqual(pod.namespace, "my-namespace")
        self.assertIsNone(pod.total_recovery_time)
        self.assertIsNone(pod.pod_readiness_time)
        self.assertIsNone(pod.pod_rescheduling_time)

        # Test with all arguments
        pod = AffectedPod(
            "my-pod-2",
            "my-namespace-2",
            total_recovery_time=10.5,
            pod_readiness_time=5.5,
            pod_rescheduling_time=5.0,
        )
        self.assertEqual(pod.pod_name, "my-pod-2")
        self.assertEqual(pod.namespace, "my-namespace-2")
        self.assertEqual(pod.total_recovery_time, 10.5)
        self.assertEqual(pod.pod_readiness_time, 5.5)
        self.assertEqual(pod.pod_rescheduling_time, 5.0)

    def test_init_podsstatus(self):
        pods_status = PodsStatus()
        self.assertEqual(len(pods_status.recovered), 0)
        self.assertEqual(len(pods_status.unrecovered), 0)
        self.assertIsNone(pods_status.error)

    def test_merge_podsstatus(self):
        status1 = PodsStatus()
        status1.recovered.append(AffectedPod("pod-1", "ns-1", 10.0, 5.0, 5.0))
        status1.unrecovered.append(AffectedPod("pod-2", "ns-2"))

        status2 = PodsStatus()
        status2.recovered.append(
            AffectedPod("pod-3", "ns-3", 20.0, 10.0, 10.0)
        )
        status2.unrecovered.append(AffectedPod("pod-4", "ns-4"))

        status1.merge(status2)

        self.assertEqual(len(status1.recovered), 2)
        self.assertEqual(len(status1.unrecovered), 2)

        self.assertEqual(status1.recovered[0].pod_name, "pod-1")
        self.assertEqual(status1.recovered[1].pod_name, "pod-3")
        self.assertEqual(status1.unrecovered[0].pod_name, "pod-2")
        self.assertEqual(status1.unrecovered[1].pod_name, "pod-4")

    def test_init_podevent(self):
        event = PodEvent()
        self.assertIsInstance(event.timestamp, float)
        # Verify that timestamp is close to the current time
        self.assertLess(abs(event.timestamp - time.time()), 0.1)

    def test_timestamp_setter_raises_attribute_error_podevent(self):
        event = PodEvent()
        with self.assertRaises(AttributeError):
            event.timestamp = 123456789.0

    def test_equality_podevent(self):
        event1 = PodEvent()
        event1.status = PodStatus.READY
        # Create a second event with a similar timestamp
        event2 = PodEvent()
        event2.status = PodStatus.READY
        # Patch the timestamp to be equal for a fair comparison
        event2._timestamp = event1.timestamp
        self.assertEqual(event1, event2)

    def test_init_monitoredpod(self):
        pod = MonitoredPod()
        self.assertEqual(pod.namespace, "")
        self.assertEqual(pod.name, "")
        self.assertEqual(len(pod.status_changes), 0)

    def test_init_podssnapshot(self):
        snapshot = PodsSnapshot()
        self.assertEqual(snapshot.resource_version, "")
        self.assertEqual(len(snapshot.pods), 0)
        self.assertEqual(len(snapshot.added_pods), 0)
        self.assertEqual(len(snapshot.initial_pods), 0)

    def test_find_rescheduled_pod_found_podssnapshot(self):
        snapshot = PodsSnapshot()
        parent_pod = MonitoredPod()
        parent_pod.name = "parent-pod"

        rescheduled_pod = MonitoredPod()
        rescheduled_pod.name = "rescheduled-pod"
        added_event = PodEvent()
        added_event.status = PodStatus.ADDED
        added_event.parent = "parent-pod"
        rescheduled_pod.status_changes.append(added_event)

        snapshot.pods = {
            "parent-pod": parent_pod,
            "rescheduled-pod": rescheduled_pod,
        }
        found_pod = snapshot._find_rescheduled_pod(parent_pod.name)
        self.assertEqual(found_pod.name, "rescheduled-pod")

    def test_find_rescheduled_pod_not_found_podssnapshot(self):
        snapshot = PodsSnapshot()
        parent_pod = MonitoredPod()
        parent_pod.name = "parent-pod"
        snapshot.pods = {"parent-pod": parent_pod}
        found_pod = snapshot._find_rescheduled_pod(parent_pod.name)
        self.assertIsNone(found_pod)

    def test_get_pods_status_not_ready_unrecovered_podssnapshot(self):
        snapshot = PodsSnapshot()
        pod = MonitoredPod()
        pod.name = "test-pod"
        pod.namespace = "test-ns"
        event = PodEvent()
        event.status = PodStatus.NOT_READY
        pod.status_changes.append(event)
        snapshot.initial_pods = ["test-pod"]
        snapshot.pods = {"test-pod": pod}

        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 1)
        self.assertEqual(len(status.recovered), 0)
        self.assertEqual(status.unrecovered[0].pod_name, "test-pod")

    def test_get_pods_status_not_ready_recovered_podssnapshot(self):
        snapshot = PodsSnapshot()
        pod = MonitoredPod()
        pod.name = "test-pod"
        pod.namespace = "test-ns"
        not_ready_event = PodEvent()
        not_ready_event.status = PodStatus.NOT_READY
        not_ready_event._timestamp = time.time() - 10
        ready_event = PodEvent()
        ready_event.status = PodStatus.READY
        ready_event._timestamp = time.time()
        pod.status_changes.extend([not_ready_event, ready_event])
        snapshot.initial_pods = ["test-pod"]
        snapshot.pods = {"test-pod": pod}

        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 0)
        self.assertEqual(len(status.recovered), 1)
        self.assertEqual(status.recovered[0].pod_name, "test-pod")
        self.assertAlmostEqual(
            status.recovered[0].pod_readiness_time, 10.0, places=1
        )

    def test_get_pods_status_deletion_scheduled_unrecovered_podssnapshot(
        self,
    ):
        snapshot = PodsSnapshot()
        pod = MonitoredPod()
        pod.name = "test-pod"
        pod.namespace = "test-ns"
        event = PodEvent()
        event.status = PodStatus.DELETION_SCHEDULED
        pod.status_changes.append(event)
        snapshot.initial_pods = ["test-pod"]
        snapshot.pods = {"test-pod": pod}

        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 1)
        self.assertEqual(len(status.recovered), 0)
        self.assertEqual(status.unrecovered[0].pod_name, "test-pod")

    def test_get_pods_status_deletion_scheduled_recovered_podssnapshot(self):
        snapshot = PodsSnapshot()

        parent_pod = MonitoredPod()
        parent_pod.name = "parent-pod"
        parent_pod.namespace = "parent-ns"
        deletion_event = PodEvent()
        deletion_event.status = PodStatus.DELETION_SCHEDULED
        deletion_event._timestamp = time.time() - 20
        parent_pod.status_changes.append(deletion_event)

        rescheduled_pod = MonitoredPod()
        rescheduled_pod.name = "rescheduled-pod"
        rescheduled_pod.namespace = "parent-ns"
        added_event = PodEvent()
        added_event.status = PodStatus.ADDED
        added_event.parent = "parent-pod"
        added_event._timestamp = time.time() - 10
        ready_event = PodEvent()
        ready_event.status = PodStatus.READY
        ready_event._timestamp = time.time()
        rescheduled_pod.status_changes.extend([added_event, ready_event])

        snapshot.initial_pods = ["parent-pod"]
        snapshot.pods = {
            "parent-pod": parent_pod,
            "rescheduled-pod": rescheduled_pod,
        }

        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 0)
        self.assertEqual(len(status.recovered), 1)

        recovered_pod = status.recovered[0]
        self.assertEqual(recovered_pod.pod_name, "rescheduled-pod")
        self.assertEqual(recovered_pod.namespace, "parent-ns")
        self.assertAlmostEqual(
            recovered_pod.pod_rescheduling_time, 10.0, delta=0.001
        )
        self.assertAlmostEqual(
            recovered_pod.pod_readiness_time, 20.0, delta=0.001
        )
        self.assertAlmostEqual(
            recovered_pod.total_recovery_time, 30.0, delta=0.001
        )

    def test_get_pods_status_deletion_scheduled_unrecovered_no_ready_podssnapshot(  # NOQA
        self,
    ):
        snapshot = PodsSnapshot()

        parent_pod = MonitoredPod()
        parent_pod.name = "parent-pod"
        parent_pod.namespace = "parent-ns"
        deletion_event = PodEvent()
        deletion_event.status = PodStatus.DELETION_SCHEDULED
        parent_pod.status_changes.append(deletion_event)

        rescheduled_pod = MonitoredPod()
        rescheduled_pod.name = "rescheduled-pod"
        rescheduled_pod.namespace = "parent-ns"
        added_event = PodEvent()
        added_event.status = PodStatus.ADDED
        added_event.parent = "parent-pod"
        rescheduled_pod.status_changes.append(added_event)

        snapshot.initial_pods = ["parent-pod"]
        snapshot.pods = {
            "parent-pod": parent_pod,
            "rescheduled-pod": rescheduled_pod,
        }

        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 1)
        self.assertEqual(len(status.recovered), 0)
        self.assertEqual(status.unrecovered[0].pod_name, "rescheduled-pod")

    def test_respawn_buggy_input(self):
        buggy_json = """
     {
 "resource_version": "3370",
 "pods": [
  [
   "delayed-3-bjojvqzxou",
   {
    "namespace": "test-ns-3-cprfhlhdox",
    "name": "delayed-3-bjojvqzxou",
    "status_changes": []
   }
  ],
  [
   "delayed-3-ogjrbicxis",
   {
    "namespace": "test-ns-3-cprfhlhdox",
    "name": "delayed-3-ogjrbicxis",
    "status_changes": [
     {
      "parent": null,
      "status": "DELETION_SCHEDULED",
      "timestamp": 1.0
     }
    ]
   }
  ],
  [
   "delayed-respawn-3-giuxefqrps",
   {
    "namespace": "test-ns-3-cprfhlhdox",
    "name": "delayed-respawn-3-giuxefqrps",
    "status_changes": [
     {
      "parent": null,
      "status": "ADDED",
      "timestamp": 1.0
     },
     {
      "parent": null,
      "status": "NOT_READY",
      "timestamp": 2.0
     },
     {
      "parent": null,
      "status": "NOT_READY",
      "timestamp": 3.0
     },
     {
      "parent": null,
      "status": "NOT_READY",
      "timestamp": 4.0
     }
    ]
   }
  ]
 ],
 "added_pods": [
  "delayed-respawn-3-giuxefqrps"
 ],
 "initial_pods": [
  "delayed-3-bjojvqzxou",
  "delayed-3-ogjrbicxis"
 ]
}
"""
        snapshot = PodsSnapshot(json_str=buggy_json)
        status = snapshot.get_pods_status()
        self.assertEqual(len(status.unrecovered), 1)
        self.assertEqual(
            status.unrecovered[0].pod_name, "delayed-respawn-3-giuxefqrps"
        )

        another_buggy_json = """
{
 "resource_version": "3584",
 "pods": [
  [
   "delayed-1-fsghkeirdl",
   {
    "namespace": "test-ns-1-tyu-crsltvqclh",
    "name": "delayed-1-fsghkeirdl",
    "status_changes": [
     {
      "status": "DELETION_SCHEDULED",
      "timestamp": 1756824656.2687368
     }
    ]
   }
  ],
  [
   "delayed-1-sxaelejdul",
   {
    "namespace": "test-ns-1-tyu-crsltvqclh",
    "name": "delayed-1-sxaelejdul",
    "status_changes": []
   }
  ],
  [
   "delayed-1-respawn-lcfmnhgxzs",
   {
    "namespace": "test-ns-1-tyu-crsltvqclh",
    "name": "delayed-1-respawn-lcfmnhgxzs",
    "status_changes": [
     {
      "status": "ADDED",
      "timestamp": 1756824656.2621553
     },
     {
      "status": "NOT_READY",
      "timestamp": 1756824656.2722685
     },
     {
      "status": "NOT_READY",
      "timestamp": 1756824656.2776031
     },
     {
      "status": "NOT_READY",
      "timestamp": 1756824657.1519113
     },
     {
      "status": "READY",
      "timestamp": 1756824658.1827428
     }
    ]
   }
  ]
 ],
 "added_pods": [
  "delayed-1-respawn-lcfmnhgxzs"
 ],
 "initial_pods": [
  "delayed-1-fsghkeirdl",
  "delayed-1-sxaelejdul"
 ]
}
        """
        snapshot = PodsSnapshot(json_str=another_buggy_json)
        status = snapshot.get_pods_status()
        self.assertTrue(len(status.recovered), 1)
        self.assertTrue(status.recovered[0].pod_readiness_time > 0)
        # Tests a real case where the pod has been rescheduled before
        # The event of the deletion has been emitted measuring a negative
        # rescheduling time.
        self.assertTrue(status.recovered[0].pod_rescheduling_time < 0)
        self.assertTrue(status.recovered[0].total_recovery_time > 0)
