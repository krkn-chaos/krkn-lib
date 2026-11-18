# NVIDIA GPU discovery

`krkn_lib.gpu.NvidiaGpuInspector` provides current GPU inventory and on-demand
measurements for scenario code. It reads Kubernetes Nodes and Pods, then runs
only `nvidia-smi -L`, `nvidia-smi -q -x`, and `nvidia-smi topo -m` in an existing
GPU Operator driver Pod. It never creates Pods or changes GPU settings.

## Kubeconfig

Keep kubeconfig outside this repository and restrict its file permissions to
your user (`chmod 600 /absolute/path/to/kube_config.yaml`). Pass its absolute
path to `from_kubeconfig`; do not copy credentials into source code or commit
the file. Replace the example path below with your own path.

```bash
kubectl --kubeconfig /absolute/path/to/kube_config.yaml config get-contexts
kubectl --kubeconfig /absolute/path/to/kube_config.yaml config current-context
```

Use the context name shown by `kubectl config get-contexts` and the namespace
where GPU Operator runs. `from_kubeconfig` creates an isolated Kubernetes
client and does not persist refreshed credentials to the kubeconfig.

## Python API

```python
import json

from krkn_lib.gpu import NvidiaGpuInspector

inspector = NvidiaGpuInspector.from_kubeconfig(
    "/absolute/path/to/kube_config.yaml",
    context="your-context",
    operator_namespace="nvidia-gpu-operator",
)
inventory = inspector.discover_inventory(timeout_seconds=30)
print(json.dumps(inventory.to_dict(), indent=2))

gpu_nodes = [node.name for node in inventory.nodes if node.resources]
if gpu_nodes:
    snapshot = inspector.snapshot(
        inventory,
        node_names=gpu_nodes,
        fields=[
            "memory_used_bytes",
            "gpu_utilization_percent",
            "sm_clock_mhz",
            "power_draw_w",
            "sw_power_cap_active",
            "hw_power_brake_active",
            "pcie_replay_count",
        ],
        timeout_seconds=30,
    )
    print(json.dumps(snapshot.to_dict(), indent=2))
```

`discover_inventory(node_names=[...])` limits discovery to named nodes.
`snapshot` accepts exactly one selector: `node_names`, `device_uuids`, or a
`workload` mapping. Each call fetches new measurements; it does not reuse
measurements cached in inventory.

To resolve devices seen by a running workload container:

```python
mapping = inspector.resolve_container(
    namespace="my-test-namespace",
    pod_name="my-running-gpu-pod",
    container_name="gpu-test",
)
snapshot = inspector.snapshot(
    inventory,
    workload=mapping,
    fields=["memory_used_bytes", "gpu_utilization_percent"],
)
```

The container must be running and contain `nvidia-smi`. A Pod whose sole
command is `nvidia-smi` normally finishes immediately, so it is useful for a
one-time smoke test but not later workload mapping. `visible_device_uuids`
contains MIG UUIDs when MIG is active; `parent_gpu_uuids` lists physical
parents separately. If the container cannot be queried, mapping is `unknown`.

For a standalone driver installation, pass an existing running access Pod on
each selected node:

```python
from krkn_lib.gpu import AccessPod

inspector = NvidiaGpuInspector.from_kubeconfig(
    "/absolute/path/to/kube_config.yaml",
    context="your-context",
    access_pods={
        "gpu-node-name": AccessPod(
            "existing-namespace", "existing-access-pod", "container-with-nvidia-smi"
        )
    },
)
```

If this Python process actually runs on a selected GPU node, install optional
NVML support (`poetry install -E gpu`) and pass `local_node_name="that-node"`.
NVML data is then attached only to that explicit Kubernetes node. Do not set
`local_node_name` when running on a laptop.

## Data and access requirements

- Node `capacity` and `allocatable` are both preserved, including `0`.
  Physical GPUs and MIG partitions have separate lists. Sharing strategy is
  reported only when Node labels establish it; missing evidence stays
  `unknown`.
- Measurements include value, unit, source, observation time, and status:
  `available`, `unsupported`, `unavailable`, or `unknown`. A real zero is
  `available`. Missing XML fields are `unknown`; an explicit `N/A` is
  `unsupported`. Node and snapshot errors retain partial results.
- Driver version and CUDA version reported by `nvidia-smi` describe the
  driver and its supported CUDA API. They do not prove CUDA toolkit version
  installed in workload images. CUDA toolkit remains `unknown` unless another
  source is added.
- Xid history, NVLink counters, and some MIG metrics may not appear in
  `nvidia-smi -q -x`; those fields remain `unknown`. No Prometheus or DCGM
  installation is required. Topology is reported when `nvidia-smi topo -m`
  succeeds. NVML local mode does not provide topology in this release.
- Physical GPU capabilities include `power_limit_control` and `clock_control`.
  `available` means a read-only source reported an allowed power range or a
  supported memory/graphics clock pair. It does not establish write permission.
  Missing evidence remains `unknown`; an explicit `N/A` or NVML unsupported
  result is `unsupported`.
- A local NVML read returns by the requested timeout. A timed-out native NVML
  call may finish later; subsequent local reads remain unavailable until it
  completes.
- Kubernetes permissions: `get/list` Nodes, `get/list` Pods in the Operator
  namespace, and `create` on the `pods/exec` subresource there. Workload
  mapping also needs `get` Pods and `create` `pods/exec` in that workload's
  namespace. `pods/exec` RBAC uses the verb `create`; the library does not
  create a Pod.

Only run workload mapping in an approved test namespace. Discovery and
snapshots leave cluster resources unchanged.
