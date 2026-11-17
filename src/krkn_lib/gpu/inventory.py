"""Build GPU inventory records from Kubernetes and NVIDIA query data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubernetes import client

from .models import (
    Availability,
    Conflict,
    Evidence,
    GpuNode,
    GpuStack,
    MigPartition,
    PhysicalGpu,
    ResourceCount,
    SharingConfig,
    StackComponent,
    utc_now,
)
from .parsers import NvidiaQuery

_ROLES = {
    "nvidia-driver": "driver",
    "nvidia-container-toolkit": "toolkit",
    "nvidia-device-plugin": "device-plugin",
    "nvidia-dcgm-exporter": "exporter",
    "dcgm-exporter": "exporter",
    "gpu-operator": "operator",
}


def _resource_count(
    name: str,
    capacity: Mapping[str, object],
    allocatable: Mapping[str, object],
) -> ResourceCount:
    def integer(value: object) -> int | None:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    return ResourceCount(
        name=name,
        capacity=integer(capacity.get(name)),
        allocatable=integer(allocatable.get(name)),
    )


def _gpu_resource(name: str) -> bool:
    return (
        name == "nvidia.com/gpu"
        or name.startswith("nvidia.com/gpu.")
        or name.startswith("nvidia.com/mig-")
    )


def _relevant_labels(labels: Mapping[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in labels.items()
        if name.startswith("nvidia.com/")
        or name.startswith("feature.node.kubernetes.io/pci-10de")
    }


def _component_role(pod: client.V1Pod) -> str | None:
    tokens = [pod.metadata.name]
    tokens.extend(container.name for container in pod.spec.containers or [])
    for token in tokens:
        for marker, role in _ROLES.items():
            if marker in token:
                return role
    return None


def stack_components(pods: Sequence[client.V1Pod]) -> list[StackComponent]:
    components: list[StackComponent] = []
    for pod in pods:
        role = _component_role(pod)
        if role is None:
            continue
        statuses = {
            status.name: status.ready
            for status in (pod.status.container_statuses or [])
        }
        containers = pod.spec.containers or []
        role_container = next(
            (container for container in containers if role in container.name),
            containers[0] if containers else None,
        )
        components.append(
            StackComponent(
                role=role,
                namespace=pod.metadata.namespace,
                pod_name=pod.metadata.name,
                node_name=pod.spec.node_name,
                phase=pod.status.phase,
                ready=(
                    statuses.get(role_container.name)
                    if role_container is not None
                    else None
                ),
                image=(
                    role_container.image
                    if role_container is not None
                    else None
                ),
            )
        )
    return components


def _sharing(
    resources: list[ResourceCount], labels: Mapping[str, str]
) -> list[SharingConfig]:
    result: list[SharingConfig] = []
    for resource in resources:
        base = resource.name.removesuffix(".shared")
        suffix = base.removeprefix("nvidia.com/")
        strategy = labels.get(f"nvidia.com/{suffix}.sharing-strategy")
        raw_replicas = labels.get(f"nvidia.com/{suffix}.replicas")
        replicas = None
        if raw_replicas is not None:
            try:
                replicas = int(raw_replicas)
            except ValueError:
                pass
        evidence = []
        if strategy is not None:
            evidence.append(f"nvidia.com/{suffix}.sharing-strategy={strategy}")
        if raw_replicas is not None:
            evidence.append(f"nvidia.com/{suffix}.replicas={raw_replicas}")
        if strategy in {"time-slicing", "mps"} and replicas and replicas > 0:
            status = Availability.AVAILABLE
            reason = None
        elif strategy == "none":
            strategy = "exclusive"
            status = Availability.AVAILABLE
            reason = None
            replicas = 1
        else:
            status = Availability.UNKNOWN
            reason = (
                "effective sharing strategy or replica count not established"
            )
        result.append(
            SharingConfig(
                resource_name=resource.name,
                strategy=strategy,
                replicas=replicas,
                renamed_resource=resource.name.endswith(".shared"),
                status=status,
                reason=reason,
                evidence=evidence,
            )
        )
    return result


def _mig_resource(node: GpuNode, partition: MigPartition) -> str | None:
    if partition.profile:
        profile = partition.profile.split()[0]
        candidate = f"nvidia.com/mig-{profile}"
        if any(resource.name == candidate for resource in node.resources):
            return candidate
    if (
        len({part.profile for part in node.mig_partitions}) == 1
        and any(
            resource.name == "nvidia.com/gpu" for resource in node.resources
        )
        and node.labels.get("nvidia.com/mig.config", "").startswith("all-")
    ):
        return "nvidia.com/gpu"
    return None


def merge_devices(
    node: GpuNode,
    xml_result: NvidiaQuery,
    list_result: tuple[list[PhysicalGpu], list[MigPartition]],
) -> None:
    listed_gpus, listed_partitions = list_result
    by_uuid = {gpu.uuid: gpu for gpu in xml_result.gpus if gpu.uuid}
    for listed in listed_gpus:
        if listed.uuid in by_uuid:
            queried = by_uuid[listed.uuid]
            queried.local_index = listed.local_index
            if (
                queried.model
                and listed.model
                and queried.model != listed.model
            ):
                node.conflicts.append(
                    Conflict(
                        field=f"{listed.uuid}.model",
                        evidence=[
                            Evidence(
                                "nvidia-smi -q -x", queried.model, utc_now()
                            ),
                            Evidence("nvidia-smi -L", listed.model, utc_now()),
                        ],
                        reason="NVIDIA sources disagree on GPU model",
                    )
                )
        else:
            by_uuid[listed.uuid] = listed
    listed_indices = {gpu.local_index for gpu in listed_gpus}
    unknown_gpus = [
        gpu
        for gpu in xml_result.gpus
        if not gpu.uuid and gpu.local_index not in listed_indices
    ]
    node.physical_gpus = list(by_uuid.values()) + unknown_gpus
    partitions = {
        part.uuid: part for part in xml_result.mig_partitions if part.uuid
    }
    for listed in listed_partitions:
        if listed.uuid in partitions:
            existing = partitions[listed.uuid]
            existing.profile = existing.profile or listed.profile
            existing.gpu_instance_id = (
                existing.gpu_instance_id
                if existing.gpu_instance_id is not None
                else listed.gpu_instance_id
            )
            existing.compute_instance_id = (
                existing.compute_instance_id
                if existing.compute_instance_id is not None
                else listed.compute_instance_id
            )
        else:
            partitions[listed.uuid] = listed
    node.mig_partitions = list(partitions.values())
    for part in node.mig_partitions:
        part.resource_name = _mig_resource(node, part)


def node_from_kubernetes(
    source: client.V1Node,
    components: list[StackComponent],
    pod_listing_available: bool,
    operator_namespace: str | None,
) -> GpuNode:
    labels = _relevant_labels(source.metadata.labels or {})
    capacity = source.status.capacity or {}
    allocatable = source.status.allocatable or {}
    names = sorted(
        name
        for name in set(capacity) | set(allocatable)
        if _gpu_resource(name)
    )
    resources = [
        _resource_count(name, capacity, allocatable) for name in names
    ]
    return GpuNode(
        name=source.metadata.name,
        uid=source.metadata.uid,
        labels=labels,
        resources=resources,
        sharing=_sharing(resources, labels),
        stack=GpuStack(
            operator_status=(
                Availability.AVAILABLE
                if pod_listing_available
                else Availability.UNAVAILABLE
            ),
            operator_present=(
                any(item.role == "operator" for item in components)
                if pod_listing_available
                else None
            ),
            operator_namespace=next(
                (
                    item.namespace
                    for item in components
                    if item.role == "operator"
                ),
                operator_namespace,
            ),
            components=[
                item
                for item in components
                if item.node_name == source.metadata.name
                or item.role == "operator"
            ],
        ),
    )


def is_candidate(
    node: GpuNode, known: Mapping[str, GpuNode], selected: set[str]
) -> bool:
    return (
        node.name in selected
        or node.name in known
        or bool(node.resources)
        or bool(node.labels)
        or any(
            component.role in {"driver", "device-plugin"}
            for component in node.stack.components
        )
    )
