from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from krkn_lib.models.telemetry import ChaosRunTelemetry


@dataclass(order=False)
class ChaosRunAlert:
    """
    Represents a single alert collected from prometheus
    """

    alertname: str
    """
    prometheus alert name
    """
    alertstate: str
    """
    prometheus alert state
    """
    namespace: str
    """
    namespace where the alert has been fired
    """
    severity: str
    """
    severity of the alert
    """

    def __init__(
        self, alertname: str, alertstate: str, namespace: str, severity: str
    ):
        self.alertname = alertname
        self.alertstate = alertstate
        self.namespace = namespace
        self.severity = severity


@dataclass(order=False)
class ChaosRunAlertSummary:
    """
    Represents a summary of the collected alerts
    """

    run_id: str
    """
    Chaos run id
    """

    scenario: str
    """
    scenario that caused critical alerts
    """

    chaos_alerts: list[ChaosRunAlert]
    """
    alerts collected during the chaos
    """

    post_chaos_alerts: list[ChaosRunAlert]
    """
    alerts collected after the chaos run
    """

    def __init__(self):
        self.chaos_alerts = []
        self.post_chaos_alerts = []

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)


@dataclass(order=False)
class ChaosRunOutput:
    """
    The krkn full json output. this is meant to be injected
    into Elastic search to be indexed
    """

    telemetry: ChaosRunTelemetry | None
    """
    the cluster telemetry collected by krkn
    """
    critical_alerts: ChaosRunAlertSummary | None
    """
    the prometheus critical alerts collected during and after the chaos
    run
    """

    def __init__(self):
        self.telemetry = None
        self.critical_alerts = None

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)


class HogType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"


class HogConfig:
    type: HogType
    image: str
    # cpu hog
    cpu_load_percentage: int
    cpu_method: str

    # io hog
    io_block_size: str
    io_write_bytes: str
    io_target_pod_folder: str
    io_target_pod_volume: dict[str, any]

    # memory hog
    memory_vm_bytes: str

    workers: int
    duration: int
    namespace: str
    node_selector: dict[str, str]

    def __init__(self):
        self.type = HogType.CPU
        self.image = "quay.io/krkn-chaos/krkn-hog"
        self.cpu_load_percentage = 80
        self.cpu_method = "all"
        self.io_block_size = "1m"
        self.io_write_bytes = "10m"
        self.io_target_pod_folder = "/hog-data"
        self.io_target_pod_volume = {
            "hostPath": {"path": "/tmp"},
            "name": "node-volume",
        }
        self.memory_vm_bytes = "10%"
        self.workers = 1
        self.duration = 30
        self.namespace = "default"
        self.node_selector = {}
