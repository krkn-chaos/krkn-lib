import base64
import yaml
import json
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True, order=False)
class Volume:
    """Data class to hold information regarding volumes in a pod"""

    name: str
    pvcName: str


@dataclass(order=False)
class VolumeMount:
    """Data class to hold information regarding volume mounts"""

    name: str
    mountPath: str


@dataclass(frozen=True, order=False)
class PVC:
    """Data class to hold information regarding persistent volume claims"""

    name: str
    capacity: str
    volumeName: str
    podNames: List[str]
    namespace: str


@dataclass(order=False)
class Container:
    """Data class to hold information regarding containers in a pod"""

    image: str
    name: str
    volumeMounts: List[VolumeMount]
    ready: bool = False


@dataclass(frozen=True, order=False)
class Pod:
    """
    Data class to hold
    information regarding a pod
    """

    name: str
    podIP: str
    namespace: str
    containers: List[Container]
    nodeName: str
    volumes: List[Volume]


@dataclass(frozen=True, order=False)
class LitmusChaosObject:
    """
    Data class to hold information regarding
    a custom object of litmus project
    """

    kind: str
    group: str
    namespace: str
    name: str
    plural: str
    version: str


@dataclass(frozen=True, order=False)
class ChaosEngine(LitmusChaosObject):
    """
    Data class to hold information
    regarding a ChaosEngine object
    """

    engineStatus: str
    expStatus: str


@dataclass(frozen=True, order=False)
class ChaosResult(LitmusChaosObject):
    """
    Data class to hold information
    regarding a ChaosResult object
    """

    verdict: str
    failStep: str


class ApiRequestException(Exception):
    pass


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
                    if not isinstance(self.parameters, dict):
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
class ChaosRunTelemetry:
    scenarios: list[ScenarioTelemetry]

    def __init__(self, json_object: any = None):
        self.scenarios = []
        if json_object is not None:
            scenarios = json_object.get("scenarios")
            if scenarios is None or isinstance(scenarios, list) is False:
                raise Exception("scenarios param must be a list of object")
            for scenario in scenarios:
                scenario_telemetry = ScenarioTelemetry(scenario)
                self.scenarios.append(scenario_telemetry)

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)
