import base64
import json
from dataclasses import dataclass

import yaml


@dataclass(order=False)
class ScenarioTelemetry:
    startTimeStamp: float
    endTimeStamp: float
    scenario: str
    exitStatus: int
    parametersBase64: str
    parameters: any

    def __init__(self, json_object: any = None):
        if json_object is not None:
            self.startTimeStamp = int(json_object.get("startTimeStamp"))
            self.endTimeStamp = json_object.get("endTimeStamp")
            self.scenario = json_object.get("scenario")
            self.exitStatus = json_object.get("exitStatus")
            self.parametersBase64 = json_object.get("parametersBase64")
            self.parameters = json_object.get("parameters")

            if (
                self.parametersBase64 is not None
                and self.parametersBase64 != ""
            ):
                try:
                    yaml_params = base64.b64decode(self.parametersBase64)
                    yaml_object = yaml.safe_load(yaml_params)
                    json_string = json.dumps(yaml_object, indent=2)
                    self.parameters = json.loads(json_string)
                    if not isinstance(
                        self.parameters, dict
                    ) and not isinstance(self.parameters, list):
                        raise Exception()
                    self.parametersBase64 = ""
                except Exception as e:
                    raise Exception(
                        "invalid parameters format: {0}".format(str(e))
                    )
        else:
            # if constructor is called without params
            # property are initialized so are available
            self.startTimeStamp = 0
            self.endTimeStamp = 0
            self.scenario = ""
            self.exitStatus = 0
            self.parametersBase64 = ""
            self.parameters = {}


@dataclass(order=False)
class NodeInfo:
    """
    Cluster node metadata
    """

    architecture: str = ""
    instance_type: str = ""
    node_type: str = ""
    kernel_version: str = ""
    kubelet_version: str = ""
    os_version: str = ""


@dataclass(order=False)
class ChaosRunTelemetry:
    scenarios: list[ScenarioTelemetry]
    node_infos: list[NodeInfo] = list[NodeInfo]
    node_count: int = 0
    cloud_infrastructure: str = "Unknown"
    kubernetes_objects_count: dict[str, int] = dict[str, int]
    network_plugins: list[str] = list[str]
    run_uuid: str = ""

    def __init__(self, json_object: any = None):
        self.scenarios = []
        if json_object is not None:
            scenarios = json_object.get("scenarios")
            if scenarios is None or isinstance(scenarios, list) is False:
                raise Exception("scenarios param must be a list of object")
            for scenario in scenarios:
                scenario_telemetry = ScenarioTelemetry(scenario)
                self.scenarios.append(scenario_telemetry)

            self.node_infos = json_object.get("node_infos")
            self.node_count = json_object.get("node_count")
            self.cloud_infrastructure = json_object.get("cloud_infrastructure")
            self.kubernetes_objects_count = json_object.get(
                "kubernetes_objects_count"
            )
            self.network_plugins = json_object.get("network_plugins")
            self.run_uuid = json_object.get("run_uuid")

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)