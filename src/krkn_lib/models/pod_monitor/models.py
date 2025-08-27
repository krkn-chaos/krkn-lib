import time
from enum import Enum
from typing import Optional

from krkn_lib.models.k8s import PodsStatus, AffectedPod


class PodStatus(Enum):
    READY = 1
    NOT_READY = 2
    DELETION_SCHEDULED = 3
    DELETED = 4
    ADDED = 5


class PodEvent:
    status: PodStatus
    parent: Optional[str]

    def __init__(self):
        self._timestamp = time.time()
        self.parent = None

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        raise AttributeError("timestamp cannot be set")

    def __eq__(self, other):
        return (
            self.status == other.status and self.timestamp == other.timestamp
        )

    def __ne__(self, other):
        return self.status != other.status or self.timestamp != other.timestamp

    def __gt__(self, other):
        return self.timestamp > other.timestamp

    def __lt__(self, other):
        return self.timestamp < other.timestamp

    def __ge__(self, other):
        return self.timestamp >= other.timestamp

    def __le__(self, other):
        return self.timestamp <= other.timestamp


class MonitoredPod:
    namespace: str
    name: str
    status_changes: list[PodEvent]

    def __init__(self):
        self.namespace = ""
        self.name = ""
        self.status_changes = []


class PodsSnapshot:
    resource_version: str
    pods: dict[str, MonitoredPod]
    added_pods: list[str]
    initial_pods: list[str]

    def __init__(self):
        self.resource_version = ""
        self.pods = {}
        self.added_pods = []
        self.initial_pods = []

    def _find_rescheduled_pod(self, parent: str) -> Optional[MonitoredPod]:
        for _, v in self.pods.items():
            found_pod = next(
                filter(
                    lambda p: p.status == PodStatus.ADDED
                    and p.parent == parent,
                    v.status_changes,
                ),
                None,
            )
            if found_pod:
                return v
        return None

    def get_pods_status(self) -> PodsStatus:

        pods_status = PodsStatus()
        for pod_name in self.initial_pods:
            pod = self.pods[pod_name]
            for status_change in pod.status_changes:
                if status_change.status == PodStatus.NOT_READY:
                    ready_status = next(
                        filter(
                            lambda s: s.status == PodStatus.READY,
                            pod.status_changes,
                        ),
                        None,
                    )
                    if not ready_status:
                        pods_status.unrecovered.append(
                            AffectedPod(
                                pod_name=pod.name, namespace=pod.namespace
                            )
                        )
                    else:
                        pods_status.recovered.append(
                            AffectedPod(
                                pod_name=pod.name,
                                namespace=pod.namespace,
                                pod_readiness_time=ready_status.timestamp
                                - status_change.timestamp,
                            )
                        )
                    break

                # if there's a DELETION_SCHEDULED events
                # looks for the rescheduled pod
                # and calculates its scheduling and readiness time
                if status_change.status == PodStatus.DELETION_SCHEDULED:
                    rescheduled_pod = self._find_rescheduled_pod(pod.name)
                    if not rescheduled_pod:
                        pods_status.unrecovered.append(
                            AffectedPod(
                                pod_name=pod.name, namespace=pod.namespace
                            )
                        )
                    else:
                        rescheduled_start_ts = next(
                            map(
                                lambda e: e.timestamp,
                                filter(
                                    lambda s: s.status == PodStatus.ADDED,
                                    rescheduled_pod.status_changes,
                                ),
                            ),
                            None,
                        )
                        rescheduled_ready_ts = next(
                            map(
                                lambda e: e.timestamp,
                                filter(
                                    lambda s: s.status == PodStatus.READY,
                                    rescheduled_pod.status_changes,
                                ),
                            ),
                            None,
                        )
                        # the pod might be rescheduled correctly
                        # but do not become ready in the expected time
                        # so it must be marked as `unrecovered` in that
                        # case
                        if not rescheduled_ready_ts:
                            pods_status.unrecovered.append(
                                AffectedPod(
                                    pod_name=rescheduled_pod.name,
                                    namespace=pod.namespace,
                                )
                            )
                        else:
                            rescheduling_time = (
                                rescheduled_start_ts - status_change.timestamp
                                if rescheduled_start_ts
                                else None
                            )
                            readiness_time = (
                                rescheduled_ready_ts - status_change.timestamp
                                if rescheduled_ready_ts
                                else None
                            )
                            pods_status.recovered.append(
                                AffectedPod(
                                    pod_name=rescheduled_pod.name,
                                    namespace=rescheduled_pod.namespace,
                                    pod_rescheduling_time=rescheduling_time,
                                    pod_readiness_time=readiness_time,
                                    total_recovery_time=(
                                        rescheduling_time + readiness_time
                                        if rescheduling_time and readiness_time
                                        else None
                                    ),
                                )
                            )
                    break

        return pods_status
