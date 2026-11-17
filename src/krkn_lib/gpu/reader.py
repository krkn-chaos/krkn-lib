"""Bounded, read-only NVIDIA queries through existing Kubernetes pods."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Protocol

from kubernetes import client
from kubernetes.stream import stream


class GpuAccessError(RuntimeError):
    """A selected GPU node or pod has no usable read-only access path."""


@dataclass(frozen=True)
class AccessPod:
    namespace: str
    pod_name: str
    container_name: str


@dataclass(frozen=True)
class QueryResult:
    stdout: str
    stderr: str
    exit_code: int | None
    source: str
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.exit_code == 0


class GpuQueryReader(Protocol):
    """Injectable boundary for GPU tests and alternative collectors."""

    def query_node(
        self, node_name: str, command: tuple[str, ...], timeout_seconds: float
    ) -> QueryResult: ...

    def query_container(
        self,
        namespace: str,
        pod_name: str,
        container_name: str,
        command: tuple[str, ...],
        timeout_seconds: float,
    ) -> QueryResult: ...


class KubernetesPodReader:
    """Run only NVIDIA queries in an existing, running container.

    A GPU Operator driver pod gives a node-wide view. An explicitly supplied
    access pod is required when the driver is installed directly on the host
    and no suitable Operator pod exists. This class never creates a pod.
    """

    def __init__(
        self,
        core_api: client.CoreV1Api,
        *,
        operator_namespace: str | None = None,
        access_pods: Mapping[str, AccessPod] | None = None,
    ):
        self.core_api = core_api
        self.operator_namespace = operator_namespace
        self.access_pods = dict(access_pods or {})

    def _driver_pod(self, node_name: str, timeout_seconds: float) -> AccessPod:
        if node_name in self.access_pods:
            selected = self.access_pods[node_name]
            pod = self.core_api.read_namespaced_pod(
                selected.pod_name,
                selected.namespace,
                _request_timeout=timeout_seconds,
            )
            if (
                pod.spec.node_name != node_name
                or pod.status.phase != "Running"
            ):
                raise GpuAccessError(
                    f"configured access pod is not running on {node_name}"
                )
            if selected.container_name not in {
                container.name for container in pod.spec.containers or []
            }:
                raise GpuAccessError("configured access container is absent")
            return selected
        kwargs = {
            "field_selector": f"spec.nodeName={node_name}",
            "_request_timeout": timeout_seconds,
        }
        if self.operator_namespace:
            pods = self.core_api.list_namespaced_pod(
                self.operator_namespace, **kwargs
            ).items
        else:
            pods = self.core_api.list_pod_for_all_namespaces(**kwargs).items
        for pod in pods:
            if (
                pod.spec.node_name != node_name
                or pod.status.phase != "Running"
            ):
                continue
            containers = [
                container.name for container in pod.spec.containers or []
            ]
            if "nvidia-driver-ctr" in containers:
                name = "nvidia-driver-ctr"
            elif pod.metadata.name.startswith("nvidia-driver-daemonset"):
                name = next(
                    (item for item in containers if "driver" in item), None
                )
            else:
                name = None
            if name:
                return AccessPod(
                    pod.metadata.namespace, pod.metadata.name, name
                )
        raise GpuAccessError(
            f"no running GPU Operator driver pod on {node_name}; "
            "supply an existing access pod"
        )

    @staticmethod
    def _check_command(command: tuple[str, ...]) -> None:
        allowed = {
            ("nvidia-smi", "-L"),
            ("nvidia-smi", "-q", "-x"),
            ("nvidia-smi", "topo", "-m"),
        }
        if command not in allowed:
            raise ValueError(
                "only approved read-only nvidia-smi queries are allowed"
            )

    def _exec(
        self,
        access: AccessPod,
        command: tuple[str, ...],
        timeout_seconds: float,
    ) -> QueryResult:
        if timeout_seconds <= 0:
            return QueryResult("", "deadline exceeded", None, "pod-exec", True)
        started = time.monotonic()
        source = (
            f"pod-exec:{access.namespace}/{access.pod_name}/"
            f"{access.container_name}"
        )
        connection = stream(
            self.core_api.connect_get_namespaced_pod_exec,
            access.pod_name,
            access.namespace,
            container=access.container_name,
            command=list(command),
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
            _request_timeout=timeout_seconds,
        )
        try:
            remaining = max(
                0.0, timeout_seconds - (time.monotonic() - started)
            )
            if remaining <= 0:
                return QueryResult("", "deadline exceeded", None, source, True)
            connection.run_forever(timeout=remaining)
            stdout = connection.read_stdout()
            stderr = connection.read_stderr()
            if connection.is_open():
                return QueryResult(stdout, stderr, None, source, True)
            try:
                exit_code = connection.returncode
            except (KeyError, TypeError, ValueError):
                exit_code = None
            return QueryResult(stdout, stderr, exit_code, source)
        finally:
            connection.close()

    def query_node(
        self, node_name: str, command: tuple[str, ...], timeout_seconds: float
    ) -> QueryResult:
        self._check_command(command)
        started = time.monotonic()
        access = self._driver_pod(node_name, timeout_seconds)
        return self._exec(
            access,
            command,
            timeout_seconds - (time.monotonic() - started),
        )

    def query_container(
        self,
        namespace: str,
        pod_name: str,
        container_name: str,
        command: tuple[str, ...],
        timeout_seconds: float,
    ) -> QueryResult:
        self._check_command(command)
        started = time.monotonic()
        pod = self.core_api.read_namespaced_pod(
            pod_name, namespace, _request_timeout=timeout_seconds
        )
        if pod.status.phase != "Running":
            raise GpuAccessError(f"pod {namespace}/{pod_name} is not running")
        if container_name not in {
            container.name for container in pod.spec.containers or []
        }:
            raise GpuAccessError(f"container {container_name} does not exist")
        return self._exec(
            AccessPod(namespace, pod_name, container_name),
            command,
            timeout_seconds - (time.monotonic() - started),
        )
