import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml

from krkn_lib.models.k8s import PodsStatus


@dataclass(order=False)
class ScenarioTelemetry:
    """
    Scenario Telemetry collection
    """

    start_timestamp: float
    """
    Timestamp when the Krkn run started
    """
    end_timestamp: float
    """
    Timestamp when the Krkn run ended
    """
    scenario: str
    """
    Scenario filename
    """
    exit_status: int
    """
    Exit Status of the Scenario Run
    """
    parameters_base64: str
    """
    Scenario configuration file base64 encoded
    """
    parameters: any

    """
    Pods affected by the chaos scenario
    """

    affected_pods: PodsStatus

    def __init__(self, json_object: any = None):
        if json_object is not None:
            self.start_timestamp = int(json_object.get("start_timestamp"))
            self.end_timestamp = int(json_object.get("end_timestamp"))
            self.scenario = json_object.get("scenario")
            self.exit_status = json_object.get("exit_status")
            self.parameters_base64 = json_object.get("parameters_base64")
            self.parameters = json_object.get("parameters")
            self.affected_pods = PodsStatus(
                json_object=json_object.get("affected_pods")
            )

            if (
                self.parameters_base64 is not None
                and self.parameters_base64 != ""
            ):
                try:
                    yaml_params = base64.b64decode(self.parameters_base64)
                    yaml_object = yaml.safe_load(yaml_params)
                    json_string = json.dumps(yaml_object, indent=2)
                    self.parameters = json.loads(json_string)
                    if not isinstance(
                        self.parameters, dict
                    ) and not isinstance(self.parameters, list):
                        raise Exception()
                    self.parameters_base64 = ""
                except Exception as e:
                    raise Exception(
                        "invalid parameters format: {0}".format(str(e))
                    )
        else:
            # if constructor is called without params
            # property are initialized so are available
            self.start_timestamp = 0
            self.end_timestamp = 0
            self.scenario = ""
            self.exit_status = 0
            self.parameters_base64 = ""
            self.parameters = {}
            self.affected_pods = PodsStatus()


@dataclass(order=False)
class Taint:
    """
    Cluster Node Taint details
    """

    node_name: str = ""
    """
    node name
    """
    effect: str = ""
    """
    effect of the taint in the node
    """
    key: str = ""
    """
    Taint key
    """
    value: str = ""
    """
    Taint Value
    """

    def __init__(self, json_dict: dict = None):
        if json_dict is not None:
            self.node_name = (
                json_dict["node_name"] if "node_name" in json_dict else None
            )
            self.effect = (
                json_dict["effect"] if "effect" in json_dict else None
            )
            self.key = json_dict["key"] if "key" in json_dict else None
            self.value = json_dict["value"] if "value" in json_dict else None


@dataclass(order=False)
class NodeInfo:
    """
    Cluster node telemetry infos
    """

    count: int = 1
    """
    number of nodes of this kind
    """

    architecture: str = ""
    """
    CPU Architecture
    """
    instance_type: str = ""
    """
    Cloud instance type (if available)
    """
    node_type: str = ""
    """
    Node Type (worker/infra/master etc.)
    """
    kernel_version: str = ""
    "Node kernel version"
    kubelet_version: str = ""
    "Kubelet Version"
    os_version: str = ""
    "Operating system version"

    def __init__(self, json_dict: dict = None):
        if json_dict is not None:
            self.count = json_dict["count"] if "count" in json_dict else None
            self.architecture = (
                json_dict["architecture"]
                if "architecture" in json_dict
                else None
            )
            self.instance_type = (
                json_dict["instance_type"]
                if "instance_type" in json_dict
                else None
            )
            self.node_type = (
                json_dict["node_type"] if "node_type" in json_dict else None
            )
            self.kernel_version = (
                json_dict["kernel_version"]
                if "kernel_version" in json_dict
                else None
            )
            self.kubelet_version = (
                json_dict["kubelet_version"]
                if "kubelet_version" in json_dict
                else None
            )
            self.os_version = (
                json_dict["os_version"] if "os_version" in json_dict else None
            )

    def __eq__(self, other):
        if isinstance(other, NodeInfo):
            return (
                other.architecture == self.architecture
                and other.instance_type == self.instance_type
                and other.node_type == self.node_type
                and other.kernel_version == self.kernel_version
                and other.kubelet_version == self.kubelet_version
                and other.os_version == self.os_version
            )
        else:
            return False

    def __repr__(self):
        return (
            f"{self.architecture} {self.instance_type} "
            f"{self.node_type} {self.kernel_version} "
            f"{self.kubelet_version} {self.os_version}"
        )

    def __hash__(self):
        return hash(self.__repr__())


@dataclass(order=False)
class ChaosRunTelemetry:
    """
    Root object for the Telemetry Collection
    """

    scenarios: list[ScenarioTelemetry]
    """
    List of the scenarios performed during the chaos run
    """
    node_summary_infos: list[NodeInfo]
    """
    Summary of node Infos collected from the target cluster.
    It will report all the master and infra nodes and only one
    of the workers that usually are configured to have the same
    resources.
    """
    node_taints: list[Taint]
    """
    The list of node taints detected
    """

    kubernetes_objects_count: dict[str, int]
    """
    Dictionary containing the number of objects deployed
    in the cluster during the chaos run
    """
    network_plugins: list[str]
    """
    Network plugins deployed in the target cluster
    """
    total_node_count: int = 0
    """
    Number of all kind of nodes in the target cluster
    """
    cloud_infrastructure: str = "Unknown"
    """
    Cloud infrastructure (if available) of the target cluster
    """
    version: str = "Unknown"
    """
    K8s or OCP version
    """
    cloud_type: str = "self-managed"
    """
    Cloud Type (if available) of the target cluster: self-managed, rosa, etc
    """
    run_uuid: str = ""
    """
    Run uuid generated by Krkn for the Run
    """
    timestamp: str = ""
    """
    Current time stamp of run
    """

    affected_pods: PodsStatus = PodsStatus()

    def __init__(self, json_dict: any = None):
        self.scenarios = list[ScenarioTelemetry]()
        self.node_summary_infos = list[NodeInfo]()
        self.node_taints = list[Taint]()
        self.kubernetes_objects_count = dict[str, int]()
        self.network_plugins = ["Unknown"]
        self.timestamp = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        if json_dict is not None:
            scenarios = json_dict.get("scenarios")
            if scenarios is None or isinstance(scenarios, list) is False:
                raise Exception("scenarios param must be a list of object")

            self.scenarios = [ScenarioTelemetry(s) for s in scenarios]

            self.node_summary_infos = [
                NodeInfo(j) for j in json_dict.get("node_summary_infos")
            ]
            self.node_taints = [Taint(t) for t in json_dict.get("node_taints")]
            self.total_node_count = json_dict.get("total_node_count")
            self.cloud_infrastructure = json_dict.get("cloud_infrastructure")
            self.cloud_type = json_dict.get("cloud_type")
            self.version = json_dict.get("version")
            self.kubernetes_objects_count = json_dict.get(
                "kubernetes_objects_count"
            )
            self.network_plugins = json_dict.get("network_plugins")
            self.run_uuid = json_dict.get("run_uuid")
            self.timestamp = json_dict.get("timestamp")

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)


@dataclass(order=False)
class S3BucketObject:
    """
    Class that represents an S3 bucket object provided
    by the telemetry webservice
    """

    type: str
    """
    can be "folder" or "file"
    """

    path: str
    """
    the path or the filename wit
    """

    size: int
    """
    if it's a file represents the file size
    """

    modified: str
    """
    if it's a file represents the date when the file
    has been created/modified
    """
