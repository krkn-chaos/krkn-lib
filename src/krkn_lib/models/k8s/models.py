from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, order=False)
class Volume:
    """Data class to hold information regarding volumes in a pod"""

    name: str
    """
    Volume Name
    """
    pvcName: str
    """
    Persistent Volume Claim Name associated with the Volume
    """


@dataclass(order=False)
class VolumeMount:
    """Data class to hold information regarding volume mounts"""

    name: str
    """
    VolumeMount Name
    """
    mountPath: str
    """
    Path where the molume is mounted in the POD
    """


@dataclass(frozen=True, order=False)
class PVC:
    """Data class to hold information regarding persistent volume claims"""

    name: str
    """
    Persistent Volume Claim Name
    """
    capacity: str
    """
    PVC size
    """
    volumeName: str
    """
    Name of the projected Volume
    """
    podNames: list[str]
    """
    Pods Claiming the PVC
    """
    namespace: str
    """
    Namespace where the PVC is deployed
    """


@dataclass(order=False)
class Container:
    """Data class to hold information regarding containers in a pod"""

    image: str
    """
    Container images
    """
    name: str
    """
    Container Name
    """
    volumeMounts: list[VolumeMount]
    """
    List of volumes mounted in the Container
    """
    ready: bool = False
    """
    Container Ready status
    """


@dataclass(frozen=True, order=False)
class Pod:
    """
    Data class to hold
    information regarding a pod
    """

    name: str
    """
    Pod Name
    """
    status: str
    """
    Status of the Pod
    """
    podIP: str
    """
    Pod ip address
    """
    namespace: str
    """
    Pod Namespaces
    """
    containers: list[Container]
    """
    List of containers in the Pod
    """
    nodeName: str
    """
    Node name where the Pod is deployed
    """
    volumes: list[Volume]
    """
    Volumes mounted in the Pod
    """


class ApiRequestException(Exception):
    """
    Generic API Exception raised by k8s package
    Methods
    """

    pass


class AffectedPod:
    """
    A pod affected by a chaos scenario
    """

    pod_name: str
    """
    Name of the pod
    """
    namespace: str
    """
    Namespace of the pod
    """
    pod_rescheduling_time: float
    """
    The time that the cluster took to reschedule
    the pod after the kill scenario
    """
    pod_readiness_time: float
    """
    The time the pod took to become ready after being scheduled
    """
    total_recovery_time: float
    """
    Total amount of time the pod took to become ready
    """

    def __init__(
        self,
        pod_name: str,
        namespace: str,
        total_recovery_time: float = None,
        pod_readiness_time: float = None,
        pod_rescheduling_time: float = None,
    ):
        self.pod_name = pod_name
        self.namespace = namespace
        self.total_recovery_time = total_recovery_time
        self.pod_readiness_time = pod_readiness_time
        self.pod_rescheduling_time = pod_rescheduling_time


class PodsStatus:
    """
    Return value of wait_for_pods_to_become_ready_by_label and
    wait_for_pods_to_become_ready_by_name_pattern containing the list
    of the pods that did recover (pod_name, namespace,
    time needed to become ready) and the list of pods that did
    not recover from the chaos
    """

    recovered: list[AffectedPod]
    unrecovered: list[AffectedPod]
    error: Optional[str]

    def __init__(self, json_object: str = None):
        self.recovered = []
        self.unrecovered = []
        self.error = None

        if json_object:
            for recovered in json_object["recovered"]:
                self.recovered.append(
                    AffectedPod(
                        recovered["pod_name"],
                        recovered["namespace"],
                        float(recovered["total_recovery_time"]),
                        float(recovered["pod_readiness_time"]),
                        float(recovered["pod_rescheduling_time"]),
                    )
                )
            for unrecovered in json_object["unrecovered"]:
                self.unrecovered.append(
                    AffectedPod(
                        unrecovered["pod_name"],
                        unrecovered["namespace"],
                    )
                )
            if "error" in json_object:
                self.error = json_object["error"]

    def merge(self, pods_status: "PodsStatus"):
        for recovered in pods_status.recovered:
            self.recovered.append(recovered)
        for unrecovered in pods_status.unrecovered:
            self.unrecovered.append(unrecovered)


class PodsMonitorThread:
    executor: ThreadPoolExecutor
    future: Future

    def __init__(self, executor: ThreadPoolExecutor, future: Future):
        self.future = future
        self.executor = executor

    def join(self, timeout: int = 120) -> PodsStatus:
        try:
            result = self.future.result(timeout=timeout)
            self.executor.shutdown(wait=False, cancel_futures=True)
            return result
        except Exception as e:
            pods_status = PodsStatus()
            pods_status.error = Exception(
                f"Thread pool did not shutdown correctly,"
                f"aborting.\nException: {e}"
            )
            return pods_status


class ServiceHijacking:
    pod_name: str
    namespace: str
    selector: str
    config_map_name: str

    def __init__(
        self,
        pod_name: str,
        namespace: str,
        selector: str,
        config_map_name: str,
    ):
        self.pod_name = pod_name
        self.namespace = namespace
        self.selector = selector
        self.config_map_name = config_map_name
