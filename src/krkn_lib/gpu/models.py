"""Serializable, read-only NVIDIA GPU inventory and measurement records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Availability(str, Enum):
    """Whether a source supplied a meaningful value."""

    AVAILABLE = "available"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


def utc_now() -> str:
    """Return an RFC 3339 compatible UTC observation time."""

    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


class JsonRecord:
    """Convert nested dataclasses and enum values into JSON-safe data."""

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass
class Evidence(JsonRecord):
    source: str
    value: str | int | float | bool | None
    observed_at: str


@dataclass
class Conflict(JsonRecord):
    field: str
    evidence: list[Evidence]
    reason: str


@dataclass
class ResourceCount(JsonRecord):
    name: str
    capacity: int | None
    allocatable: int | None
    source: str = "kubernetes-node-status"


@dataclass
class SharingConfig(JsonRecord):
    resource_name: str
    strategy: str | None = None
    replicas: int | None = None
    renamed_resource: bool | None = None
    status: Availability = Availability.UNKNOWN
    reason: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class StackComponent(JsonRecord):
    role: str
    namespace: str
    pod_name: str
    node_name: str | None
    phase: str | None
    ready: bool | None
    image: str | None = None


@dataclass
class GpuStack(JsonRecord):
    operator_status: Availability = Availability.UNKNOWN
    operator_present: bool | None = None
    operator_namespace: str | None = None
    components: list[StackComponent] = field(default_factory=list)
    driver_version: str | None = None
    driver_status: Availability = Availability.UNKNOWN
    cuda_driver_supported_version: str | None = None
    cuda_driver_status: Availability = Availability.UNKNOWN
    cuda_toolkit_version: str | None = None
    cuda_toolkit_status: Availability = Availability.UNKNOWN
    tools: dict[str, Availability] = field(default_factory=dict)
    reason: str | None = None


@dataclass
class PhysicalGpu(JsonRecord):
    uuid: str | None
    pci_bus_id: str | None
    local_index: int | None
    vendor: str = "NVIDIA"
    model: str | None = None
    memory_total_bytes: int | None = None
    mig_enabled: bool | None = None
    status: Availability = Availability.UNKNOWN
    reason: str | None = None
    source: str | None = None
    observed_at: str = field(default_factory=utc_now)


@dataclass
class MigPartition(JsonRecord):
    parent_uuid: str
    uuid: str | None
    profile: str | None
    gpu_instance_id: int | None = None
    compute_instance_id: int | None = None
    memory_total_bytes: int | None = None
    resource_name: str | None = None
    status: Availability = Availability.UNKNOWN
    reason: str | None = None
    source: str | None = None
    observed_at: str = field(default_factory=utc_now)


@dataclass
class TopologyLink(JsonRecord):
    source_uuid: str
    peer: str
    peer_kind: str
    relationship: str
    cpu_affinity: str | None = None
    numa_affinity: str | None = None
    source: str = "nvidia-smi topo -m"


@dataclass
class Capability(JsonRecord):
    name: str
    status: Availability
    source: str
    device_uuid: str | None = None
    reason: str | None = None


@dataclass
class GpuNode(JsonRecord):
    name: str
    uid: str | None
    labels: dict[str, str]
    resources: list[ResourceCount]
    physical_gpus: list[PhysicalGpu] = field(default_factory=list)
    mig_partitions: list[MigPartition] = field(default_factory=list)
    sharing: list[SharingConfig] = field(default_factory=list)
    stack: GpuStack = field(default_factory=GpuStack)
    topology: list[TopologyLink] = field(default_factory=list)
    topology_status: Availability = Availability.UNKNOWN
    topology_reason: str | None = None
    capabilities: list[Capability] = field(default_factory=list)
    status: Availability = Availability.UNKNOWN
    reason: str | None = None
    conflicts: list[Conflict] = field(default_factory=list)


@dataclass
class GpuInventory(JsonRecord):
    context: str | None
    observed_at: str
    nodes: list[GpuNode]
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkloadMapping(JsonRecord):
    namespace: str
    pod_name: str
    container_name: str
    node_name: str | None
    context: str | None = None
    visible_device_uuids: list[str] = field(default_factory=list)
    parent_gpu_uuids: list[str] = field(default_factory=list)
    mapping_source: str | None = None
    status: Availability = Availability.UNKNOWN
    reason: str | None = None
    observed_at: str = field(default_factory=utc_now)


@dataclass
class Measurement(JsonRecord):
    device_uuid: str
    scope: str
    field: str
    value: int | float | bool | str | None
    unit: str | None
    value_type: str
    source: str
    observed_at: str
    status: Availability
    reason: str | None = None
    alternatives: list[Evidence] = field(default_factory=list)


@dataclass
class GpuSnapshot(JsonRecord):
    context: str | None
    observed_at: str
    measurements: list[Measurement]
    errors: list[str] = field(default_factory=list)
