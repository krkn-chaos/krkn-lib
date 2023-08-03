import base64
import datetime
import logging

import yaml
import json
from dataclasses import dataclass
from typing import List
from queue import Queue, Empty
from threading import Thread


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


class SafeLogger:
    _filename: str = None

    def __init__(self, filename: str = None, write_mode: str = None):
        """
        SafeLogger provides a mechanism to thread-safely log
        if initialized with a filename and optionally with a write mode
        (default is w+) otherwise will work as a wrapper around the logging
        package.
        The double working mechanism is meant to not force file logging to
        the methods that depend on it.
        :param filename: the log file name, if `None` the class will behave as
        a simple logger
        :param write_mode: file write mode, default is `w+`
        """
        if filename is not None:
            self._filename = filename
            if write_mode is None:
                write_mode = "w+"
            self.filewriter = open(filename, write_mode)
            self.queue = Queue()
            self.finished = False
            Thread(
                name="SafeLogWriter", target=self.write_worker, daemon=True
            ).start()
        else:
            self.filewriter = None
            self.finished = True

    def _write(self, data: str):
        if self.filewriter and self.queue:
            self.queue.put(data)

    def error(self, data: str):
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[ERR] {data}"
            )
        else:
            logging.error(data)

    def warning(self, data: str):
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[WRN] {data}"
            )
        else:
            logging.warning(data)

    def info(self, data: str):
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[INF] {data}"
            )
        else:
            logging.info(data)

    @property
    def log_file_name(self):
        return self._filename

    def write_worker(self):
        while not self.finished:
            try:
                data = self.queue.get(True)
            except Empty:
                continue
            self.filewriter.write(f"{data}\n")
            self.filewriter.flush()
            self.queue.task_done()

    def close(self):
        self.queue.join()
        self.finished = True
        self.filewriter.close()
