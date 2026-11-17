"""Read-only NVIDIA GPU discovery through a selected Kubernetes cluster."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .models import (
    Availability,
    Conflict,
    Evidence,
    GpuInventory,
    GpuNode,
    GpuSnapshot,
    Measurement,
    WorkloadMapping,
    utc_now,
)
from .inventory import (
    is_candidate,
    merge_devices,
    node_from_kubernetes,
    stack_components,
)
from .nvml import LocalNvmlSource
from .parsers import (
    NvidiaQuery,
    field_definition,
    parse_device_list,
    parse_gpu_xml,
    parse_topology,
    supported_fields,
)
from .reader import AccessPod, GpuQueryReader, KubernetesPodReader, QueryResult

_GPU_QUERY = ("nvidia-smi", "-q", "-x")
_GPU_LIST = ("nvidia-smi", "-L")
_GPU_TOPOLOGY = ("nvidia-smi", "topo", "-m")


def _device_scopes(node: GpuNode) -> dict[str, str]:
    scopes = {
        device.uuid: "physical_gpu"
        for device in node.physical_gpus
        if device.uuid
    }
    scopes.update(
        {
            device.uuid: "mig_partition"
            for device in node.mig_partitions
            if device.uuid
        }
    )
    return scopes


def _snapshot_targets(
    nodes: Mapping[str, GpuNode],
    node_names: Sequence[str] | None,
    device_uuids: Sequence[str] | None,
) -> tuple[dict[str, set[str]], list[str]]:
    targets: dict[str, set[str]] = {}
    errors: list[str] = []
    if node_names is not None:
        for name in node_names:
            if name not in nodes:
                errors.append(f"node {name} absent from inventory")
                continue
            node = nodes[name]
            targets[name] = {
                device.uuid
                for device in [*node.physical_gpus, *node.mig_partitions]
                if device.uuid
            }
        return targets, errors

    wanted = set(device_uuids or [])
    for node in nodes.values():
        found = wanted & {
            device.uuid
            for device in [*node.physical_gpus, *node.mig_partitions]
            if device.uuid
        }
        if found:
            targets[node.name] = found
            wanted -= found
    errors.extend(
        f"device {uuid} absent from inventory" for uuid in sorted(wanted)
    )
    return targets, errors


def _measurements_with_status(
    device_uuid: str,
    scope: str,
    fields: set[str],
    source: str,
    status: Availability,
    reason: str,
) -> list[Measurement]:
    result = []
    for field_name in sorted(fields):
        unit, value_type = field_definition(field_name)
        result.append(
            Measurement(
                device_uuid=device_uuid,
                scope=scope,
                field=field_name,
                value=None,
                unit=unit,
                value_type=value_type,
                source=source,
                observed_at=utc_now(),
                status=status,
                reason=reason,
            )
        )
    return result


def _error(exc: Exception) -> str:
    if isinstance(exc, ApiException):
        raw = str(exc.body or exc.reason or "request failed")
        raw = raw.rsplit("-+-+-", 1)[-1].strip()
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                raw = str(
                    decoded.get("message") or decoded.get("reason") or raw
                )
        except (TypeError, ValueError):
            pass
        return f"Kubernetes API {exc.status}: {raw[:180]}"
    return f"{type(exc).__name__}: {str(exc)[:180]}"


class NvidiaGpuInspector:
    """Collect current GPU state without creating pods or changing devices.

    ``from_kubeconfig`` isolates authentication for each cluster and does not
    persist refreshed credentials to the kubeconfig file. Callers with an
    existing KrknKubernetes instance can pass its ``cli`` property here.
    """

    def __init__(
        self,
        core_api: client.CoreV1Api,
        *,
        context: str | None = None,
        operator_namespace: str | None = None,
        access_pods: Mapping[str, AccessPod] | None = None,
        reader: GpuQueryReader | None = None,
        local_node_name: str | None = None,
        nvml_source: LocalNvmlSource | None = None,
    ):
        self.core_api = core_api
        self.context = context
        self.operator_namespace = operator_namespace
        self.local_node_name = local_node_name
        if nvml_source is not None:
            self.nvml_source = nvml_source
        elif local_node_name:
            self.nvml_source = LocalNvmlSource()
        else:
            self.nvml_source = None
        self._nvml_lock = threading.Lock()
        if nvml_source is not None and local_node_name is None:
            raise ValueError(
                "local_node_name is required for a local NVML source"
            )
        self.reader = (
            reader
            if reader is not None
            else KubernetesPodReader(
                core_api,
                operator_namespace=operator_namespace,
                access_pods=access_pods,
            )
        )

    @classmethod
    def from_kubeconfig(
        cls,
        kubeconfig_path: str,
        *,
        context: str | None = None,
        operator_namespace: str | None = None,
        access_pods: Mapping[str, AccessPod] | None = None,
        local_node_name: str | None = None,
    ) -> NvidiaGpuInspector:
        """Use an explicit kubeconfig path and optionally select a context."""

        contexts, current = config.list_kube_config_contexts(kubeconfig_path)
        if context is None and current is None:
            raise ValueError("kubeconfig has no current context; pass context")
        chosen = context if context is not None else current["name"]
        if chosen not in {item["name"] for item in contexts}:
            raise ValueError(f"context {chosen!r} is absent from kubeconfig")
        api_client = config.new_client_from_config(
            config_file=kubeconfig_path,
            context=chosen,
            persist_config=False,
        )
        return cls(
            client.CoreV1Api(api_client),
            context=chosen,
            operator_namespace=operator_namespace,
            access_pods=access_pods,
            local_node_name=local_node_name,
        )

    def _pods(
        self, timeout_seconds: float
    ) -> tuple[list[client.V1Pod], str | None]:
        try:
            if self.operator_namespace:
                response = self.core_api.list_namespaced_pod(
                    self.operator_namespace,
                    _request_timeout=timeout_seconds,
                )
            else:
                response = self.core_api.list_pod_for_all_namespaces(
                    _request_timeout=timeout_seconds
                )
            return response.items, None
        except Exception as exc:
            return [], _error(exc)

    def _query(
        self, node_name: str, command: tuple[str, ...], deadline: float
    ) -> QueryResult:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return QueryResult("", "deadline exceeded", None, "pod-exec", True)
        return self.reader.query_node(node_name, command, remaining)

    def _collect_nvml(
        self, fields: Sequence[str] | None, deadline: float
    ) -> NvidiaQuery:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("local NVML query deadline exceeded")
        if not self._nvml_lock.acquire(blocking=False):
            raise TimeoutError("previous local NVML query still running")

        outcome: list[NvidiaQuery | Exception] = []
        done = threading.Event()

        def collect() -> None:
            try:
                outcome.append(self.nvml_source.collect(fields=fields))
            except Exception as exc:
                outcome.append(exc)
            finally:
                # A timed-out NVML call continues; block later reads.
                self._nvml_lock.release()
                done.set()

        worker = threading.Thread(target=collect, daemon=True)
        try:
            worker.start()
        except Exception:
            self._nvml_lock.release()
            raise
        if not done.wait(max(0, deadline - time.monotonic())):
            raise TimeoutError("local NVML query deadline exceeded")
        result = outcome[0]
        if isinstance(result, Exception):
            raise result
        return result

    def _enrich_topology(self, node: GpuNode, deadline: float) -> None:
        if node.name == self.local_node_name and self.nvml_source is not None:
            node.topology_status = Availability.UNKNOWN
            node.topology_reason = "NVML topology not implemented"
            return
        try:
            response = self._query(node.name, _GPU_TOPOLOGY, deadline)
            if not response.succeeded:
                node.topology_status = Availability.UNAVAILABLE
                node.topology_reason = response.stderr or (
                    f"nvidia-smi topo exited {response.exit_code}"
                )
                return
            index_to_uuid = {
                gpu.local_index: gpu.uuid
                for gpu in node.physical_gpus
                if gpu.local_index is not None and gpu.uuid
            }
            node.topology = parse_topology(response.stdout, index_to_uuid)
            node.topology_status = Availability.AVAILABLE
        except Exception as exc:
            node.topology_status = Availability.UNAVAILABLE
            node.topology_reason = _error(exc)

    def _enrich_node(self, node: GpuNode, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        try:
            local = (
                node.name == self.local_node_name
                and self.nvml_source is not None
            )
            if local:
                queried = self._collect_nvml(None, deadline)
                source = "nvml"
                listed = ([], [])
            else:
                xml_response = self._query(node.name, _GPU_QUERY, deadline)
                if not xml_response.succeeded:
                    raise RuntimeError(
                        xml_response.stderr
                        or f"nvidia-smi exited {xml_response.exit_code}"
                    )
                queried = parse_gpu_xml(xml_response.stdout)
                source = xml_response.source
                list_response = self._query(node.name, _GPU_LIST, deadline)
                listed = ([], [])
                if list_response.succeeded:
                    listed = parse_device_list(list_response.stdout)
                else:
                    node.conflicts.append(
                        Conflict(
                            field="device_list",
                            evidence=[],
                            reason=(
                                "nvidia-smi -L unavailable; XML inventory used"
                            ),
                        )
                    )
            if not queried.gpus:
                raise RuntimeError("NVIDIA query reported no physical GPUs")
            node.stack.driver_version = queried.driver_version
            node.stack.driver_status = (
                Availability.AVAILABLE
                if queried.driver_version
                else Availability.UNKNOWN
            )
            node.stack.cuda_driver_supported_version = (
                queried.cuda_driver_supported_version
            )
            node.stack.cuda_driver_status = (
                Availability.AVAILABLE
                if queried.cuda_driver_supported_version
                else Availability.UNKNOWN
            )
            node.stack.tools["nvml" if local else "nvidia-smi"] = (
                Availability.AVAILABLE
            )
            node.capabilities = queried.capabilities
            merge_devices(node, queried, listed)
            for device in [*node.physical_gpus, *node.mig_partitions]:
                if source not in (device.source or ""):
                    device.source = f"{source}:{device.source}"
            node.status = Availability.AVAILABLE
            node.reason = None
            count = sum(
                resource.capacity or 0
                for resource in node.resources
                if resource.name == "nvidia.com/gpu"
            )
            if (
                count
                and node.physical_gpus
                and count != len(node.physical_gpus)
            ):
                node.conflicts.append(
                    Conflict(
                        field="nvidia.com/gpu capacity versus physical count",
                        evidence=[
                            Evidence("kubernetes", count, utc_now()),
                            Evidence(
                                "nvidia-smi -q -x",
                                len(node.physical_gpus),
                                utc_now(),
                            ),
                        ],
                        reason="resource count may reflect MIG or sharing",
                    )
                )
            self._enrich_topology(node, deadline)
        except Exception as exc:
            node.status = Availability.UNAVAILABLE
            node.reason = _error(exc)
            node.topology_status = Availability.UNAVAILABLE
            node.topology_reason = node.reason
            node.stack.tools[
                "nvml" if node.name == self.local_node_name else "nvidia-smi"
            ] = Availability.UNAVAILABLE

    def discover_inventory(
        self,
        node_names: Sequence[str] | None = None,
        known_inventory: GpuInventory | None = None,
        *,
        timeout_seconds: float = 30,
    ) -> GpuInventory:
        """Discover GPU nodes, including selected/known inaccessible nodes."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if (
            known_inventory is not None
            and known_inventory.context != self.context
        ):
            raise ValueError("known inventory belongs to a different context")
        selected = set(node_names or [])
        known = {
            node.name: node
            for node in (
                known_inventory.nodes if known_inventory is not None else []
            )
            if node_names is None or node.name in selected
        }
        pods, pod_error = self._pods(timeout_seconds)
        components = stack_components(pods)
        errors = [pod_error] if pod_error else []
        nodes: dict[str, GpuNode] = {}
        try:
            if node_names is None:
                sources = self.core_api.list_node(
                    _request_timeout=timeout_seconds
                ).items
            else:
                sources = []
                for name in sorted(selected):
                    try:
                        sources.append(
                            self.core_api.read_node(
                                name, _request_timeout=timeout_seconds
                            )
                        )
                    except Exception as exc:
                        errors.append(f"{name}: {_error(exc)}")
            for source in sources:
                node = node_from_kubernetes(
                    source,
                    components,
                    pod_error is None,
                    self.operator_namespace,
                )
                if is_candidate(node, known, selected):
                    nodes[node.name] = node
        except Exception as exc:
            errors.append(_error(exc))
        for name in selected | set(known):
            if name not in nodes:
                if name in known:
                    nodes[name] = replace(
                        known[name],
                        status=Availability.UNAVAILABLE,
                        reason=(
                            "node metadata unavailable in current discovery"
                        ),
                    )
                else:
                    nodes[name] = GpuNode(
                        name=name,
                        uid=None,
                        labels={},
                        resources=[],
                        status=Availability.UNAVAILABLE,
                        reason="node metadata unavailable",
                    )
        for node in nodes.values():
            if node.status != Availability.UNAVAILABLE:
                self._enrich_node(node, timeout_seconds)
        return GpuInventory(
            context=self.context,
            observed_at=utc_now(),
            nodes=sorted(nodes.values(), key=lambda item: item.name),
            errors=errors,
        )

    def resolve_container(
        self,
        namespace: str,
        pod_name: str,
        container_name: str,
        *,
        timeout_seconds: float = 30,
    ) -> WorkloadMapping:
        """Return GPU/MIG devices actually visible inside one container."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        result = WorkloadMapping(
            namespace=namespace,
            pod_name=pod_name,
            container_name=container_name,
            node_name=None,
            context=self.context,
        )
        try:
            pod = self.core_api.read_namespaced_pod(
                pod_name, namespace, _request_timeout=timeout_seconds
            )
            result.node_name = pod.spec.node_name
            response = self.reader.query_container(
                namespace,
                pod_name,
                container_name,
                _GPU_LIST,
                timeout_seconds,
            )
            if not response.succeeded:
                result.status = Availability.UNKNOWN
                result.reason = response.stderr or "container GPU query failed"
                return result
            gpus, mig = parse_device_list(response.stdout)
            result.parent_gpu_uuids = [gpu.uuid for gpu in gpus if gpu.uuid]
            visible = mig if mig else gpus
            result.visible_device_uuids = [
                item.uuid for item in visible if item.uuid
            ]
            result.mapping_source = response.source
            result.status = (
                Availability.AVAILABLE
                if result.visible_device_uuids
                else Availability.UNKNOWN
            )
            if not result.visible_device_uuids:
                result.reason = "no GPU UUID visible in container output"
            return result
        except Exception as exc:
            result.status = Availability.UNKNOWN
            result.reason = _error(exc)
            return result

    def _snapshot_node(
        self,
        name: str,
        node: GpuNode,
        uuids: set[str],
        fields: set[str],
        deadline: float,
    ) -> tuple[list[Measurement], list[str]]:
        if not uuids:
            return [], [f"node {name} has no known GPU device UUIDs"]

        scopes = _device_scopes(node)
        try:
            if name == self.local_node_name and self.nvml_source is not None:
                queried = self._collect_nvml(fields, deadline)
                source = "nvml"
            else:
                response = self._query(name, _GPU_QUERY, deadline)
                if not response.succeeded:
                    raise RuntimeError(
                        response.stderr
                        or f"nvidia-smi exited {response.exit_code}"
                    )
                queried = parse_gpu_xml(response.stdout, fields)
                source = response.source

            for measurement in queried.measurements:
                if source not in measurement.source:
                    measurement.source = f"{source}:{measurement.source}"
            present = {
                (item.device_uuid, item.field)
                for item in queried.measurements
            }
            fresh_uuids = {
                item.uuid
                for item in [*queried.gpus, *queried.mig_partitions]
                if item.uuid
            }
            measurements = [
                item
                for item in queried.measurements
                if item.device_uuid in uuids
            ]
            errors: list[str] = []
            for uuid in sorted(uuids):
                missing_device = uuid not in fresh_uuids
                if missing_device:
                    errors.append(
                        f"{name}: device {uuid} absent from fresh NVIDIA query"
                    )
                missing_fields = {
                    field_name
                    for field_name in fields
                    if (uuid, field_name) not in present
                }
                measurements.extend(
                    _measurements_with_status(
                        uuid,
                        scopes.get(uuid, "physical_gpu"),
                        missing_fields,
                        source,
                        (
                            Availability.UNAVAILABLE
                            if missing_device
                            else Availability.UNKNOWN
                        ),
                        (
                            "device absent from fresh NVIDIA query"
                            if missing_device
                            else "field absent for selected device"
                        ),
                    )
                )
            return measurements, errors
        except Exception as exc:
            reason = _error(exc)
            source = "nvml" if name == self.local_node_name else "pod-exec"
            measurements = []
            for uuid in sorted(uuids):
                measurements.extend(
                    _measurements_with_status(
                        uuid,
                        scopes.get(uuid, "physical_gpu"),
                        fields,
                        source,
                        Availability.UNAVAILABLE,
                        reason,
                    )
                )
            return measurements, [f"{name}: {reason}"]

    def snapshot(
        self,
        inventory: GpuInventory,
        *,
        node_names: Sequence[str] | None = None,
        device_uuids: Sequence[str] | None = None,
        workload: WorkloadMapping | None = None,
        fields: Sequence[str] | None = None,
        timeout_seconds: float = 30,
    ) -> GpuSnapshot:
        """Fetch fresh fields for explicitly selected nodes, devices or pod."""

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if inventory.context != self.context:
            raise ValueError("inventory belongs to a different context")
        if (
            sum(
                value is not None
                for value in (node_names, device_uuids, workload)
            )
            != 1
        ):
            raise ValueError(
                "select exactly one of node_names, device_uuids, workload"
            )
        selected_fields = (
            set(fields) if fields is not None else set(supported_fields())
        )
        invalid = selected_fields - supported_fields()
        if invalid:
            raise ValueError(
                f"unknown GPU fields: {', '.join(sorted(invalid))}"
            )
        nodes = {node.name: node for node in inventory.nodes}
        if workload is not None:
            if workload.context != self.context:
                raise ValueError(
                    "workload mapping belongs to a different context"
                )
            if workload.status != Availability.AVAILABLE:
                return GpuSnapshot(
                    self.context,
                    utc_now(),
                    [],
                    [workload.reason or "workload mapping unavailable"],
                )
            device_uuids = workload.visible_device_uuids
        targets, errors = _snapshot_targets(
            nodes, node_names, device_uuids
        )
        measurements: list[Measurement] = []
        snapshot_errors: list[str] = []
        deadline = time.monotonic() + timeout_seconds
        for name, uuids in sorted(targets.items()):
            node_measurements, node_errors = self._snapshot_node(
                name, nodes[name], uuids, selected_fields, deadline
            )
            measurements.extend(node_measurements)
            snapshot_errors.extend(node_errors)
        return GpuSnapshot(
            self.context,
            utc_now(),
            measurements,
            errors + snapshot_errors,
        )
