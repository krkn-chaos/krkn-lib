from dataclasses import dataclass


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


@dataclass(frozen=True, order=False)
class LitmusChaosObject:
    """
    Data class to hold information regarding
    a custom object of litmus project
    """

    kind: str
    """
    Litmus Object Kind
    """
    group: str
    """
    Api Group
    """
    namespace: str
    """
    Namespace where the object is deployed
    """
    name: str
    """
    Object name
    """
    plural: str
    """
    CRD plural
    """
    version: str
    """
    Version
    """


@dataclass(frozen=True, order=False)
class ChaosEngine(LitmusChaosObject):
    """
    Data class to hold information
    regarding a ChaosEngine object
    """

    engineStatus: str
    """
    Litmus Chaos engine status
    """
    expStatus: str
    """
    Litmus Chaos Engine experiment status
    """


@dataclass(frozen=True, order=False)
class ChaosResult(LitmusChaosObject):
    """
    Data class to hold information
    regarding a ChaosResult object
    """

    verdict: str
    """
    Verdict of the chaos experiment
    """
    failStep: str
    """
    Flag to show the failure step of the ChaosExperiment
    """


class ApiRequestException(Exception):
    """
    Generic API Exception raised by k8s package
    Methods
    """

    pass
