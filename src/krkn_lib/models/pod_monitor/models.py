import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from krkn_lib.models.k8s import PodsStatus, AffectedPod


class PodStatus(Enum):
    UNDEFINED = 0
    READY = 1
    NOT_READY = 2
    DELETION_SCHEDULED = 3
    DELETED = 4
    ADDED = 5


@dataclass
class PodEvent:
    status: PodStatus

    def __init__(self, timestamp: float = None):
        self.status = PodStatus.UNDEFINED
        if not timestamp:
            self._timestamp = time.time()
        else:
            self._timestamp = timestamp

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        raise AttributeError("timestamp cannot be set")


@dataclass
class MonitoredPod:
    namespace: str
    name: str
    status_changes: list[PodEvent]

    def __init__(self):
        self.namespace = ""
        self.name = ""
        self.status_changes = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "status_changes": [
                {"status": v.status.name, "timestamp": v.timestamp}
                for v in self.status_changes
            ],
        }


@dataclass
class PodsSnapshot:
    resource_version: str
    pods: dict[str, MonitoredPod]
    added_pods: list[str]
    initial_pods: list[str]
    _found_rescheduled_pods: dict[str, str]

    def __init__(self, json_str: str = None):
        self.resource_version = ""
        self.pods = {}
        self.added_pods = []
        self.initial_pods = []
        self._found_rescheduled_pods = {}
        if json_str:
            json_obj = json.loads(json_str)
            for _, pod in json_obj["pods"]:
                p = MonitoredPod()
                p.name = pod["name"]
                p.namespace = pod["namespace"]
                for status in pod["status_changes"]:
                    s = PodEvent(timestamp=status["timestamp"])
                    if status["status"] == "READY":
                        s.status = PodStatus.READY
                    elif status["status"] == "NOT_READY":
                        s.status = PodStatus.NOT_READY
                    elif status["status"] == "DELETION_SCHEDULED":
                        s.status = PodStatus.DELETION_SCHEDULED
                    elif status["status"] == "DELETED":
                        s.status = PodStatus.DELETED
                    elif status["status"] == "ADDED":
                        s.status = PodStatus.ADDED
                    p.status_changes.append(s)
                self.pods[p.name] = p
            for p in json_obj["added_pods"]:
                self.added_pods.append(p)
            for p in json_obj["initial_pods"]:
                self.initial_pods.append(p)

                pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_version": self.resource_version,
            "pods": [[k, v.to_dict()] for k, v in self.pods.items()],
            "added_pods": self.added_pods,
            "initial_pods": self.initial_pods,
        }

    def _find_rescheduled_pod(self, parent: str) -> Optional[MonitoredPod]:
        for _, v in self.pods.items():
            found_pod = next(
                filter(
                    lambda p: p.status == PodStatus.ADDED,
                    v.status_changes,
                ),
                None,
            )
            if found_pod and v.name not in self._found_rescheduled_pods:
                # just pick rescheduled pods once
                # keeping the parent for future uses
                self._found_rescheduled_pods[v.name] = parent
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

                        # pod stayed ready but was restarted
                        # or has a failed container
                        pods_status.recovered.append(
                            AffectedPod(
                                pod_name=pod.name,
                                namespace=pod.namespace,
                                pod_readiness_time=ready_status.timestamp
                                - status_change.timestamp,
                                pod_rescheduling_time=0,
                                total_recovery_time=ready_status.timestamp
                                - status_change.timestamp,
                            )
                        )
                    break

                # if there's a DELETION_SCHEDULED events
                # looks for the rescheduled pod
                # and calculates its scheduling and readiness time
                if status_change.status == PodStatus.DELETION_SCHEDULED:
                    rescheduled_pod = self._find_rescheduled_pod(pod_name)
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
