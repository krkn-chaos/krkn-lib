import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from krkn_lib.models.k8s import AffectedPod, PodsStatus


# Tolerance for timestamp precision issues (10ms)
TIMESTAMP_TOLERANCE = 0.01


def _validate_time_difference(
    end_ts: float,
    start_ts: float,
    pod_name: str,
    metric_name: str
) -> float:
    """
    Validate and sanitize time difference between timestamps.

    :param end_ts: End timestamp
    :param start_ts: Start timestamp
    :param pod_name: Pod name for logging
    :param metric_name: Name of metric being calculated (for logging)
    :return: Non-negative time difference (clamped to 0 if negative)
    """
    raw_diff = end_ts - start_ts

    if raw_diff < 0:
        if raw_diff < -TIMESTAMP_TOLERANCE:
            # Significant negative value - log error
            logging.error(
                f"Invalid timestamp ordering for pod {pod_name}: "
                f"end timestamp ({end_ts}) is {abs(raw_diff):.3f}s "
                f"before start timestamp ({start_ts}) for {metric_name}. "
                f"This indicates a data integrity issue. Using 0."
            )
        else:
            # Small negative value - likely precision issue
            logging.debug(
                f"Minor timestamp precision issue for pod {pod_name}: "
                f"{metric_name} = {raw_diff:.6f}s "
                f"(within {TIMESTAMP_TOLERANCE}s tolerance). Treating as 0."
            )

    return max(0, round(raw_diff, 8))


def _get_last_ready_timestamp(
    pod_status_changes: list,
    pod_name: str,
    creation_ts: Optional[float] = None
) -> Optional[float]:
    """
    Extract and validate the last (most recent) READY timestamp
    from pod status changes.

    :param pod_status_changes: List of PodEvent objects
    :param pod_name: Pod name for logging
    :param creation_ts: Optional creation timestamp for validation
    :return: Validated ready timestamp or None
    """
    # Get the LAST (most recent) READY event
    ready_events = [
        e for e in pod_status_changes
        if e.status == PodStatus.READY
    ]

    if not ready_events:
        return None

    ready_ts = ready_events[-1].server_timestamp

    return ready_ts


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

    def __init__(
        self, timestamp: float = None, server_timestamp: float = None
    ):
        self.status = PodStatus.UNDEFINED
        if not timestamp:
            self._timestamp = time.time()
        else:
            self._timestamp = timestamp
        # server_timestamp is the actual Kubernetes server-side timestamp
        # when the event occurred, providing more accurate timing
        self._server_timestamp = (
            server_timestamp if server_timestamp else self._timestamp
        )

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        raise AttributeError("timestamp cannot be set")

    @property
    def server_timestamp(self):
        return self._server_timestamp

    @server_timestamp.setter
    def server_timestamp(self, value):
        raise AttributeError("server_timestamp cannot be set")


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
                {
                    "status": v.status.name,
                    "timestamp": v.timestamp,
                    "server_timestamp": v.server_timestamp,
                }
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
                    # Support both old format (timestamp only)
                    # and new format (with server_timestamp)
                    server_ts = status.get(
                        "server_timestamp", status["timestamp"]
                    )
                    s = PodEvent(
                        timestamp=status["timestamp"],
                        server_timestamp=server_ts,
                    )
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
                        # Use server timestamps for both NOT_READY
                        # and READY for consistent timing measurement
                        recovery_time = (
                            ready_status.server_timestamp
                            - status_change.server_timestamp
                        )

                        # Ensure non-negative time (handle clock skew)
                        recovery_time = round(recovery_time, 8)
                        pods_status.recovered.append(
                            AffectedPod(
                                pod_name=pod.name,
                                namespace=pod.namespace,
                                pod_readiness_time=recovery_time,
                                pod_rescheduling_time=0.0,
                                total_recovery_time=recovery_time,
                            )
                        )
                    break

                # if there's a DELETION_SCHEDULED event
                # looks for the rescheduled pod
                # and calculates its scheduling and readiness time
                if status_change.status in (
                    PodStatus.DELETION_SCHEDULED,
                ):
                    rescheduled_pod = self._find_rescheduled_pod(pod_name)
                    if not rescheduled_pod:
                        pods_status.unrecovered.append(
                            AffectedPod(
                                pod_name=pod.name, namespace=pod.namespace
                            )
                        )
                    else:
                        # Use server timestamp for ADDED event
                        # (pod creation time) for consistent
                        # comparison with deletion timestamp
                        rescheduled_start_ts = next(
                            map(
                                lambda e: e.server_timestamp,
                                filter(
                                    lambda s: s.status == PodStatus.ADDED,
                                    rescheduled_pod.status_changes,
                                ),
                            ),
                            None,
                        )
                        # Get and validate the most recent
                        # READY timestamp
                        rescheduled_ready_ts = _get_last_ready_timestamp(
                            rescheduled_pod.status_changes,
                            rescheduled_pod.name,
                            rescheduled_start_ts
                        )

                        if not rescheduled_ready_ts:
                            pods_status.unrecovered.append(
                                AffectedPod(
                                    pod_name=rescheduled_pod.name,
                                    namespace=pod.namespace,
                                )
                            )
                        else:
                            # Always use server timestamp (deletionTimestamp)
                            # for consistency with other Kubernetes timestamps.
                            # DELETION_SCHEDULED events have
                            # pod.metadata.deletion_timestamp from Kubernetes.
                            deletion_ts = status_change.server_timestamp

                            logging.info(
                                f"Pod {rescheduled_pod.name} recovery "
                                f"calculation: deletion_ts={deletion_ts}, "
                                f"rescheduled_start_ts="
                                f"{rescheduled_start_ts}, "
                                f"rescheduled_ready_ts="
                                f"{rescheduled_ready_ts}"
                            )

                            # Calculate rescheduling time
                            # (time from deletion to pod added)
                            rescheduling_time = (
                                _validate_time_difference(
                                    rescheduled_start_ts,
                                    deletion_ts,
                                    rescheduled_pod.name,
                                    "rescheduling time"
                                )
                                if rescheduled_start_ts
                                else None
                            )


                            pods_status.recovered.append(
                                AffectedPod(
                                    pod_name=rescheduled_pod.name,
                                    namespace=rescheduled_pod.namespace,
                                    pod_rescheduling_time=rescheduling_time,
                                    pod_readiness_time=rescheduled_ready_ts,
                                    total_recovery_time=(
                                        rescheduling_time + rescheduled_ready_ts
                                        if rescheduling_time is not None
                                        and rescheduled_ready_ts is not None
                                        else None
                                    ),
                                )
                            )
                    break

        return pods_status
