from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

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


class HogType(str, Enum):
    cpu = "cpu"
    memory = "memory"
    io = "io"


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

    workers: Optional[int]
    number_of_nodes: Optional[int]
    duration: int
    namespace: str
    node_selector: str
    tolerations: list[str]

    def __init__(self):
        self.type = HogType.cpu
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
        self.workers = None
        self.number_of_nodes = None
        self.duration = 30
        self.namespace = "default"
        self.node_selector = ""
        self.tolerations = []

    @staticmethod
    def from_yaml_dict(yaml_dict: dict[str, str]) -> HogConfig:
        config = HogConfig()
        missing_fields = []
        if "hog-type" not in yaml_dict.keys() or not yaml_dict["hog-type"]:
            missing_fields.append("hog-type")

        if len(missing_fields) > 0:
            missing = ",".join(missing_fields)
            raise Exception(
                f"missing mandatory fields on hog config file: {missing}"
            )

        config.type = HogType[yaml_dict["hog-type"]]
        config.node_selector = yaml_dict["node-selector"]

        if "duration" in yaml_dict.keys() and yaml_dict["duration"]:
            config.duration = yaml_dict["duration"]
        if "namespace" in yaml_dict.keys() and yaml_dict["namespace"]:
            config.namespace = yaml_dict["namespace"]
        if "workers" in yaml_dict.keys() and yaml_dict["workers"]:
            config.workers = yaml_dict["workers"]
        if (
            "number-of-nodes" in yaml_dict.keys()
            and yaml_dict["number-of-nodes"]
        ):
            config.number_of_nodes = yaml_dict["number-of-nodes"]
        if "image" in yaml_dict.keys() and yaml_dict["image"]:
            config.image = yaml_dict["image"]

        if "taints" in yaml_dict.keys() and yaml_dict["taints"]:
            for taint in yaml_dict["taints"]:
                key_value_part, effect = taint.split(":", 1)
                if "=" in key_value_part:
                    key, value = key_value_part.split("=", 1)
                    operator = "Equal"
                else:
                    key = key_value_part
                    value = None
                    operator = "Exists"
                toleration = {
                    "key": key,
                    "operator": operator,
                    "effect": effect,
                }
                if value is not None:
                    toleration["value"] = value
                config.tolerations.append(toleration)

        if config.type == HogType.cpu:
            if (
                "cpu-load-percentage" in yaml_dict.keys()
                and yaml_dict["cpu-load-percentage"]
            ):
                config.cpu_load_percentage = yaml_dict["cpu-load-percentage"]
            if "cpu-method" in yaml_dict.keys() and yaml_dict["cpu-method"]:
                config.cpu_method = yaml_dict["cpu-method"]
        elif config.type == HogType.io:
            if (
                "io-block-size" in yaml_dict.keys()
                and yaml_dict["io-block-size"]
            ):
                config.io_block_size = yaml_dict["io-block-size"]
            if (
                "io-write-bytes" in yaml_dict.keys()
                and yaml_dict["io-write-bytes"]
            ):
                config.io_write_bytes = yaml_dict["io-write-bytes"]
            if (
                "io-target-pod-folder" in yaml_dict.keys()
                and yaml_dict["io-target-pod-folder"]
            ):
                config.io_target_pod_folder = yaml_dict["io-target-pod-folder"]
            if (
                "io-target-pod-volume" in yaml_dict.keys()
                and yaml_dict["io-target-pod-volume"]
            ):
                config.io_target_pod_volume = yaml_dict["io-target-pod-volume"]
        elif config.type == HogType.memory:
            if (
                "memory-vm-bytes" in yaml_dict.keys()
                and yaml_dict["memory-vm-bytes"]
            ):
                config.memory_vm_bytes = yaml_dict["memory-vm-bytes"]

        return config
