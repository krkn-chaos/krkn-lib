"""GPU tests use fake sources; no cluster or GPU device is required."""

import json
import time
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import patch

from kubernetes.client.rest import ApiException

from krkn_lib.gpu import Availability, NvidiaGpuInspector
from krkn_lib.gpu.inspector import _error
from krkn_lib.gpu.models import Evidence
from krkn_lib.gpu.nvml import LocalNvmlSource
from krkn_lib.gpu.parsers import parse_device_list, parse_gpu_xml
from krkn_lib.gpu.reader import AccessPod, KubernetesPodReader, QueryResult

GPU_XML = """\
<nvidia_smi_log>
  <driver_version>550.54.15</driver_version>
  <cuda_version>12.4</cuda_version>
  <gpu id="00000000:01:00.0">
    <product_name>NVIDIA H100</product_name>
    <uuid>GPU-aaaa</uuid>
    <pci><pci_bus_id>00000000:01:00.0</pci_bus_id>
      <pci_gpu_link_info><pcie_gen><current_link_gen>5</current_link_gen></pcie_gen>
        <link_widths><current_link_width>16x</current_link_width></link_widths>
      </pci_gpu_link_info>
      <replay_counter>0</replay_counter>
    </pci>
    <fb_memory_usage><total>80 MiB</total><used>0 MiB</used><free>80 MiB</free></fb_memory_usage>
    <utilization><gpu_util>0 %</gpu_util><memory_util>N/A</memory_util></utilization>
    <temperature><gpu_temp>35 C</gpu_temp><memory_temp>N/A</memory_temp></temperature>
    <power_readings><power_draw>72.5 W</power_draw><power_limit>350 W</power_limit>
      <min_power_limit>200 W</min_power_limit><max_power_limit>400 W</max_power_limit>
    </power_readings>
    <clocks><sm_clock>810 MHz</sm_clock><mem_clock>1500 MHz</mem_clock></clocks>
    <clocks_event_reasons><clocks_event_reason_sw_power_cap>Not Active</clocks_event_reason_sw_power_cap>
      <clocks_event_reason_hw_power_brake_slowdown>Not Active</clocks_event_reason_hw_power_brake_slowdown>
    </clocks_event_reasons>
    <mig_mode><current_mig>Enabled</current_mig></mig_mode>
    <mig_devices><mig_device><uuid>MIG-1111</uuid><profile>1g.10gb</profile>
      <gpu_instance_id>1</gpu_instance_id><compute_instance_id>0</compute_instance_id>
      <fb_memory_usage><total>10 MiB</total><used>0 MiB</used><free>10 MiB</free></fb_memory_usage>
    </mig_device></mig_devices>
  </gpu>
</nvidia_smi_log>
"""

GPU_LIST = """\
GPU 0: NVIDIA H100 (UUID: GPU-aaaa)
  MIG 1g.10gb Device 0: (UUID: MIG-1111)
"""

TOPOLOGY = """\
        GPU0    NIC0    CPU Affinity    NUMA Affinity
GPU0     X      PHB     0-31            0
"""


def node(name="gpu-node", capacity=None, allocatable=None, labels=None):
    return Obj(
        metadata=Obj(name=name, uid=f"uid-{name}", labels=labels or {}),
        status=Obj(
            capacity=(
                capacity if capacity is not None else {"nvidia.com/gpu": "1"}
            ),
            allocatable=(
                allocatable
                if allocatable is not None
                else {"nvidia.com/gpu": "1"}
            ),
        ),
    )


def pod(
    name, node_name, namespace="gpu-operator", container="nvidia-driver-ctr"
):
    return Obj(
        metadata=Obj(name=name, namespace=namespace),
        spec=Obj(
            node_name=node_name,
            containers=[Obj(name=container, image="nvidia/driver:test")],
        ),
        status=Obj(
            phase="Running",
            container_statuses=[Obj(name=container, ready=True)],
        ),
    )


class FakeApi:
    def __init__(self, nodes=None, pods=None):
        self.nodes = {item.metadata.name: item for item in (nodes or [])}
        self.pods = pods or []
        self.read_failures = set()

    def list_node(self, **kwargs):
        return Obj(items=list(self.nodes.values()))

    def read_node(self, name, **kwargs):
        if name in self.read_failures:
            raise RuntimeError("node read denied")
        return self.nodes[name]

    def list_pod_for_all_namespaces(self, **kwargs):
        return Obj(items=self.pods)

    def list_namespaced_pod(self, namespace, **kwargs):
        return Obj(
            items=[
                item
                for item in self.pods
                if item.metadata.namespace == namespace
            ]
        )

    def read_namespaced_pod(self, name, namespace, **kwargs):
        for item in self.pods:
            if (
                item.metadata.name == name
                and item.metadata.namespace == namespace
            ):
                return item
        raise RuntimeError("pod read denied")

    def connect_get_namespaced_pod_exec(self, *args, **kwargs):
        raise AssertionError("stream mock should intercept pod exec")


class FakeReader:
    def __init__(self):
        self.responses = {
            ("gpu-node", ("nvidia-smi", "-q", "-x")): GPU_XML,
            ("gpu-node", ("nvidia-smi", "-L")): GPU_LIST,
            ("gpu-node", ("nvidia-smi", "topo", "-m")): TOPOLOGY,
        }
        self.container_response = GPU_LIST

    def query_node(self, node_name, command, timeout_seconds):
        value = self.responses.get((node_name, command))
        if isinstance(value, Exception):
            raise value
        if value is None:
            return QueryResult("", "driver inaccessible", 1, "fake")
        return QueryResult(value, "", 0, "fake")

    def query_container(
        self, namespace, pod_name, container_name, command, timeout_seconds
    ):
        value = self.container_response
        if isinstance(value, Exception):
            raise value
        return QueryResult(value, "", 0, "fake")


class GpuDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi(
            nodes=[node(allocatable={"nvidia.com/gpu": "0"})],
            pods=[pod("nvidia-driver-daemonset-abc", "gpu-node")],
        )
        self.reader = FakeReader()
        self.inspector = NvidiaGpuInspector(
            self.api, context="ibm-test", reader=self.reader
        )

    def test_zero_allocatable_node_remains_and_zero_metric_is_available(self):
        inventory = self.inspector.discover_inventory()
        self.assertEqual(len(inventory.nodes), 1)
        item = inventory.nodes[0]
        self.assertEqual(item.resources[0].capacity, 1)
        self.assertEqual(item.resources[0].allocatable, 0)
        self.assertEqual(len(item.physical_gpus), 1)
        self.assertEqual(item.physical_gpus[0].uuid, "GPU-aaaa")
        self.assertEqual(item.physical_gpus[0].pci_bus_id, "00000000:01:00.0")
        self.assertEqual(item.stack.driver_version, "550.54.15")
        self.assertEqual(item.stack.cuda_driver_supported_version, "12.4")
        snapshot = self.inspector.snapshot(
            inventory,
            device_uuids=["GPU-aaaa"],
            fields=[
                "memory_used_bytes",
                "gpu_utilization_percent",
                "memory_activity_percent",
            ],
        )
        values = {value.field: value for value in snapshot.measurements}
        self.assertEqual(values["memory_used_bytes"].value, 0)
        self.assertEqual(
            values["memory_used_bytes"].status, Availability.AVAILABLE
        )
        self.assertEqual(values["gpu_utilization_percent"].value, 0.0)
        self.assertEqual(
            values["memory_activity_percent"].status, Availability.UNSUPPORTED
        )
        self.assertIsNone(values["memory_activity_percent"].value)

    def test_partial_device_query_failure_keeps_kubernetes_node(self):
        self.api.nodes["second"] = node("second")
        inventory = self.inspector.discover_inventory()
        self.assertEqual(
            [item.name for item in inventory.nodes], ["gpu-node", "second"]
        )
        self.assertEqual(inventory.nodes[0].status, Availability.AVAILABLE)
        self.assertEqual(inventory.nodes[1].status, Availability.UNAVAILABLE)
        self.assertEqual(inventory.nodes[1].resources[0].capacity, 1)

    def test_topology_failure_keeps_physical_inventory(self):
        self.reader.responses[("gpu-node", ("nvidia-smi", "topo", "-m"))] = (
            RuntimeError("topology denied")
        )
        inventory = self.inspector.discover_inventory()
        item = inventory.nodes[0]
        self.assertEqual(item.status, Availability.AVAILABLE)
        self.assertEqual(item.physical_gpus[0].uuid, "GPU-aaaa")
        self.assertEqual(item.topology_status, Availability.UNAVAILABLE)
        self.assertIn("topology denied", item.topology_reason)

    def test_known_node_survives_later_api_failure(self):
        inventory = self.inspector.discover_inventory()
        self.api.read_failures.add("gpu-node")
        later = self.inspector.discover_inventory(
            node_names=["gpu-node"], known_inventory=inventory
        )
        self.assertEqual(len(later.nodes), 1)
        self.assertEqual(later.nodes[0].uid, "uid-gpu-node")
        self.assertEqual(later.nodes[0].status, Availability.UNAVAILABLE)

    def test_mig_and_sharing_do_not_increase_physical_count(self):
        self.api.nodes["gpu-node"] = node(
            capacity={"nvidia.com/mig-1g.10gb": "4"},
            allocatable={"nvidia.com/mig-1g.10gb": "4"},
            labels={
                "nvidia.com/mig-1g.10gb.sharing-strategy": "time-slicing",
                "nvidia.com/mig-1g.10gb.replicas": "4",
            },
        )
        inventory = self.inspector.discover_inventory()
        item = inventory.nodes[0]
        self.assertEqual(len(item.physical_gpus), 1)
        self.assertEqual(len(item.mig_partitions), 1)
        self.assertEqual(item.mig_partitions[0].parent_uuid, "GPU-aaaa")
        self.assertEqual(
            item.mig_partitions[0].resource_name, "nvidia.com/mig-1g.10gb"
        )
        self.assertEqual(item.sharing[0].strategy, "time-slicing")
        self.assertEqual(item.sharing[0].replicas, 4)

    def test_container_mapping_uses_mig_uuid_not_parent(self):
        self.api.pods.append(pod("worker", "gpu-node", "jobs", "trainer"))
        mapping = self.inspector.resolve_container("jobs", "worker", "trainer")
        self.assertEqual(mapping.visible_device_uuids, ["MIG-1111"])
        self.assertEqual(mapping.parent_gpu_uuids, ["GPU-aaaa"])
        self.assertEqual(mapping.status, Availability.AVAILABLE)
        self.assertEqual(mapping.context, "ibm-test")
        other = NvidiaGpuInspector(
            self.api, context="other", reader=self.reader
        )
        with self.assertRaisesRegex(ValueError, "different context"):
            other.snapshot(
                other.discover_inventory(),
                workload=mapping,
                fields=["memory_used_bytes"],
            )
        self.reader.container_response = RuntimeError("exec denied")
        missing = self.inspector.resolve_container("jobs", "worker", "trainer")
        self.assertEqual(missing.status, Availability.UNKNOWN)
        self.assertEqual(missing.visible_device_uuids, [])

    def test_container_mapping_requires_positive_timeout(self):
        with self.assertRaisesRegex(
            ValueError, "timeout_seconds must be positive"
        ):
            self.inspector.resolve_container(
                "jobs", "worker", "trainer", timeout_seconds=0
            )

    def test_evidence_serialization_rejects_non_json_values(self):
        evidence = Evidence(
            "nvidia-smi", object(), "2026-01-01T00:00:00+00:00"
        )

        with self.assertRaisesRegex(TypeError, "not JSON serializable"):
            evidence.to_dict()

    def test_missing_metric_and_json_round_trip(self):
        inventory = self.inspector.discover_inventory()
        snapshot = self.inspector.snapshot(
            inventory,
            node_names=["gpu-node"],
            fields=["xid_last_code", "memory_used_bytes"],
        )
        decoded = json.loads(json.dumps(snapshot.to_dict()))
        self.assertEqual(decoded["context"], "ibm-test")
        self.assertEqual(decoded["measurements"][0]["status"], "available")
        xid = next(
            item
            for item in snapshot.measurements
            if item.field == "xid_last_code"
        )
        self.assertEqual(xid.status, Availability.UNKNOWN)
        self.assertIsNone(xid.value)

    def test_snapshot_failure_preserves_field_identity(self):
        inventory = self.inspector.discover_inventory()
        self.reader.responses[("gpu-node", ("nvidia-smi", "-q", "-x"))] = (
            RuntimeError("GPU lost")
        )
        snapshot = self.inspector.snapshot(
            inventory, device_uuids=["GPU-aaaa"], fields=["memory_used_bytes"]
        )
        self.assertEqual(
            snapshot.measurements[0].status, Availability.UNAVAILABLE
        )
        self.assertEqual(snapshot.measurements[0].unit, "bytes")
        self.assertIn("GPU lost", snapshot.errors[0])

    def test_disappeared_device_is_unavailable_in_fresh_snapshot(self):
        inventory = self.inspector.discover_inventory()
        self.reader.responses[("gpu-node", ("nvidia-smi", "-q", "-x"))] = (
            "<nvidia_smi_log></nvidia_smi_log>"
        )
        snapshot = self.inspector.snapshot(
            inventory,
            device_uuids=["GPU-aaaa"],
            fields=["memory_used_bytes"],
        )
        self.assertEqual(
            snapshot.measurements[0].status, Availability.UNAVAILABLE
        )
        self.assertIn("absent from fresh", snapshot.errors[0])

    def test_missing_snapshot_measurements_have_stable_order(self):
        inventory = self.inspector.discover_inventory()
        self.reader.responses[("gpu-node", ("nvidia-smi", "-q", "-x"))] = (
            "<nvidia_smi_log></nvidia_smi_log>"
        )

        snapshot = self.inspector.snapshot(
            inventory,
            node_names=["gpu-node"],
            fields=["xid_last_code", "memory_used_bytes"],
        )

        self.assertEqual(
            [
                (item.device_uuid, item.field)
                for item in snapshot.measurements
            ],
            [
                ("GPU-aaaa", "memory_used_bytes"),
                ("GPU-aaaa", "xid_last_code"),
                ("MIG-1111", "memory_used_bytes"),
                ("MIG-1111", "xid_last_code"),
            ],
        )

    def test_kubernetes_exec_error_excludes_handshake_headers(self):
        exc = ApiException(
            status=0,
            reason=(
                "Handshake status 500 -+-+- {'audit-id': 'private'} -+-+- "
                '{"message":"error dialing backend"}'
            ),
        )
        self.assertEqual(
            _error(exc), "Kubernetes API 0: error dialing backend"
        )

    def test_conflicting_capacity_and_model_are_reported(self):
        self.api.nodes["gpu-node"] = node(
            capacity={"nvidia.com/gpu": "4"},
            allocatable={"nvidia.com/gpu": "4"},
        )
        self.reader.responses[("gpu-node", ("nvidia-smi", "-L"))] = (
            "GPU 0: Different Model (UUID: GPU-aaaa)"
        )
        inventory = self.inspector.discover_inventory()
        fields = {conflict.field for conflict in inventory.nodes[0].conflicts}
        self.assertIn("GPU-aaaa.model", fields)
        self.assertIn("nvidia.com/gpu capacity versus physical count", fields)

    def test_kubeconfig_uses_named_context_without_persisting_credentials(
        self,
    ):
        contexts = ([{"name": "ibm-test"}], {"name": "ibm-test"})
        with (
            patch(
                "krkn_lib.gpu.inspector.config.list_kube_config_contexts",
                return_value=contexts,
            ) as listed,
            patch(
                "krkn_lib.gpu.inspector.config.new_client_from_config",
                return_value=Obj(),
            ) as created,
        ):
            inspector = NvidiaGpuInspector.from_kubeconfig(
                "/private/config/kube_config.yaml", context="ibm-test"
            )
        listed.assert_called_once_with("/private/config/kube_config.yaml")
        created.assert_called_once_with(
            config_file="/private/config/kube_config.yaml",
            context="ibm-test",
            persist_config=False,
        )
        self.assertEqual(inspector.context, "ibm-test")

    def test_local_nvml_source_is_bound_to_explicit_node(self):
        nvml = Obj(
            nvmlInit=lambda: None,
            nvmlShutdown=lambda: None,
            nvmlDeviceGetCount=lambda: 1,
            nvmlDeviceGetHandleByIndex=lambda index: "handle",
            nvmlDeviceGetUUID=lambda handle: b"GPU-aaaa",
            nvmlDeviceGetName=lambda handle: b"NVIDIA H100",
            nvmlDeviceGetPciInfo=lambda handle: Obj(busId=b"00000000:01:00.0"),
            nvmlDeviceGetMemoryInfo=lambda handle: Obj(
                total=80 * 1024**3, used=0, free=80 * 1024**3
            ),
            nvmlDeviceGetUtilizationRates=lambda handle: Obj(gpu=0, memory=0),
            nvmlDeviceGetMigMode=lambda handle: (0, 0),
            nvmlSystemGetDriverVersion=lambda: b"550.54.15",
            nvmlSystemGetCudaDriverVersion_v2=lambda: 12040,
        )
        source = LocalNvmlSource(nvml)
        with self.assertRaisesRegex(ValueError, "local_node_name"):
            NvidiaGpuInspector(self.api, nvml_source=source)
        inspector = NvidiaGpuInspector(
            self.api,
            context="ibm-test",
            reader=self.reader,
            local_node_name="gpu-node",
            nvml_source=source,
        )
        self.reader.responses.clear()
        inventory = inspector.discover_inventory()
        self.assertEqual(inventory.nodes[0].status, Availability.AVAILABLE)
        self.assertEqual(
            inventory.nodes[0].stack.tools["nvml"], Availability.AVAILABLE
        )
        snapshot = inspector.snapshot(
            inventory,
            device_uuids=["GPU-aaaa"],
            fields=["memory_used_bytes", "gpu_utilization_percent"],
        )
        values = {item.field: item for item in snapshot.measurements}
        self.assertEqual(values["memory_used_bytes"].value, 0)
        self.assertEqual(values["gpu_utilization_percent"].value, 0)
        self.assertEqual(
            values["memory_used_bytes"].status, Availability.AVAILABLE
        )

    def test_nvml_reports_control_capabilities_without_setting_devices(self):
        setter_calls = []
        nvml = Obj(
            nvmlInit=lambda: None,
            nvmlShutdown=lambda: None,
            nvmlDeviceGetCount=lambda: 1,
            nvmlDeviceGetHandleByIndex=lambda index: "handle",
            nvmlDeviceGetUUID=lambda handle: b"GPU-aaaa",
            nvmlDeviceGetPowerManagementLimitConstraints=(
                lambda handle: (200_000, 400_000)
            ),
            nvmlDeviceGetSupportedMemoryClocks=lambda handle: [1500],
            nvmlDeviceGetSupportedGraphicsClocks=(
                lambda handle, memory_clock: [810]
            ),
            nvmlDeviceSetPowerManagementLimit=(
                lambda *args: setter_calls.append(args)
            ),
            nvmlDeviceSetGpuLockedClocks=(
                lambda *args: setter_calls.append(args)
            ),
        )

        query = LocalNvmlSource(nvml).collect(fields=[])
        controls = {item.name: item for item in query.capabilities}

        self.assertIn("power_limit_control", controls)
        self.assertIn("clock_control", controls)
        self.assertEqual(
            controls["power_limit_control"].status, Availability.AVAILABLE
        )
        self.assertEqual(
            controls["clock_control"].status, Availability.AVAILABLE
        )
        self.assertEqual(setter_calls, [])

    def test_local_nvml_snapshot_returns_when_deadline_expires(self):
        inventory = self.inspector.discover_inventory()

        class SlowNvml:
            def collect(self, fields=None):
                time.sleep(0.3)
                return parse_gpu_xml("<nvidia_smi_log/>", set(fields or []))

        inspector = NvidiaGpuInspector(
            self.api,
            context="ibm-test",
            reader=self.reader,
            local_node_name="gpu-node",
            nvml_source=SlowNvml(),
        )
        started = time.monotonic()
        snapshot = inspector.snapshot(
            inventory,
            device_uuids=["GPU-aaaa"],
            fields=["memory_used_bytes"],
            timeout_seconds=0.01,
        )

        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(
            snapshot.measurements[0].status, Availability.UNAVAILABLE
        )
        self.assertIn("deadline", snapshot.errors[0])

    def test_local_nvml_discovery_keeps_node_when_deadline_expires(self):
        class SlowNvml:
            def collect(self, fields=None):
                time.sleep(0.3)
                return parse_gpu_xml("<nvidia_smi_log/>")

        inspector = NvidiaGpuInspector(
            self.api,
            context="ibm-test",
            reader=self.reader,
            local_node_name="gpu-node",
            nvml_source=SlowNvml(),
        )
        started = time.monotonic()
        inventory = inspector.discover_inventory(timeout_seconds=0.01)

        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(inventory.nodes[0].resources[0].capacity, 1)
        self.assertEqual(inventory.nodes[0].status, Availability.UNAVAILABLE)
        self.assertIn("deadline", inventory.nodes[0].reason)


class NvidiaParserTests(unittest.TestCase):
    def test_xml_reports_control_capabilities_from_read_only_ranges(self):
        xml = GPU_XML.replace(
            "</power_readings>",
            "</power_readings><supported_clocks><supported_mem_clock>"
            "<value>1500 MHz</value>"
            "<supported_graphics_clock>810 MHz</supported_graphics_clock>"
            "</supported_mem_clock></supported_clocks>",
            1,
        )
        result = parse_gpu_xml(xml, set())
        controls = {item.name: item for item in result.capabilities}

        self.assertIn("power_limit_control", controls)
        self.assertIn("clock_control", controls)
        self.assertEqual(
            controls["power_limit_control"].status, Availability.AVAILABLE
        )
        self.assertEqual(
            controls["clock_control"].status, Availability.AVAILABLE
        )

    def test_xml_nested_na_clock_range_is_unsupported(self):
        xml = GPU_XML.replace(
            "</power_readings>",
            "</power_readings><supported_clocks><supported_mem_clock>"
            "<value>N/A</value><supported_graphics_clock>N/A"
            "</supported_graphics_clock></supported_mem_clock>"
            "</supported_clocks>",
            1,
        )
        result = parse_gpu_xml(xml, set())
        clock = next(
            item
            for item in result.capabilities
            if item.name == "clock_control"
        )

        self.assertEqual(clock.status, Availability.UNSUPPORTED)

    def test_gpu_power_readings_from_recent_nvidia_xml(self):
        xml = """\
<nvidia_smi_log><gpu><uuid>GPU-new</uuid><gpu_power_readings>
  <instant_power_draw>17.22 W</instant_power_draw>
  <current_power_limit>72.00 W</current_power_limit>
  <min_power_limit>40.00 W</min_power_limit>
  <max_power_limit>72.00 W</max_power_limit>
</gpu_power_readings></gpu></nvidia_smi_log>
"""
        result = parse_gpu_xml(
            xml,
            {
                "power_draw_w",
                "power_limit_w",
                "power_min_limit_w",
                "power_max_limit_w",
            },
        )
        values = {item.field: item for item in result.measurements}
        self.assertEqual(values["power_draw_w"].value, 17.22)
        self.assertEqual(values["power_limit_w"].value, 72.0)
        self.assertEqual(values["power_min_limit_w"].value, 40.0)
        self.assertEqual(values["power_max_limit_w"].value, 72.0)
        self.assertTrue(
            all(
                item.status == Availability.AVAILABLE
                for item in values.values()
            )
        )

    def test_list_and_xml_keep_mig_separate(self):
        gpus, partitions = parse_device_list(GPU_LIST)
        self.assertEqual(len(gpus), 1)
        self.assertEqual(len(partitions), 1)
        result = parse_gpu_xml(GPU_XML, {"memory_total_bytes"})
        self.assertEqual(result.gpus[0].memory_total_bytes, 80 * 1024**2)
        self.assertEqual(
            result.mig_partitions[0].memory_total_bytes, 10 * 1024**2
        )

    def test_unrecognized_output_is_not_zero(self):
        malformed = GPU_XML.replace(
            "<used>0 MiB</used>", "<used>garbage</used>", 1
        )
        result = parse_gpu_xml(malformed, {"memory_used_bytes"})
        self.assertEqual(result.measurements[0].status, Availability.UNKNOWN)
        self.assertIsNone(result.measurements[0].value)

    def test_capabilities_mirror_physical_measurement_status(self):
        result = parse_gpu_xml(
            GPU_XML, {"gpu_utilization_percent", "memory_activity_percent"}
        )

        measurements = {item.field: item for item in result.measurements}
        capabilities = {
            item.name: item
            for item in result.capabilities
            if item.name in measurements
        }
        self.assertEqual(capabilities.keys(), measurements.keys())
        for name, measurement in measurements.items():
            self.assertEqual(
                capabilities[name].device_uuid, measurement.device_uuid
            )
            self.assertEqual(capabilities[name].status, measurement.status)


class PodReaderTests(unittest.TestCase):
    def test_explicit_access_pod_must_be_on_selected_node(self):
        api = FakeApi(pods=[pod("driver", "wrong-node")])
        reader = KubernetesPodReader(
            api,
            access_pods={
                "gpu-node": AccessPod(
                    "gpu-operator", "driver", "nvidia-driver-ctr"
                )
            },
        )
        with self.assertRaisesRegex(Exception, "not running on gpu-node"):
            reader.query_node("gpu-node", ("nvidia-smi", "-L"), 1)

    def test_node_query_rejects_setting_command_before_pod_lookup(self):
        reader = KubernetesPodReader(FakeApi())
        with self.assertRaisesRegex(ValueError, "approved read-only"):
            reader.query_node("gpu-node", ("nvidia-smi", "-pl", "100"), 1)

    def test_container_query_rejects_setting_command_before_pod_lookup(self):
        reader = KubernetesPodReader(FakeApi())
        with self.assertRaisesRegex(ValueError, "approved read-only"):
            reader.query_container(
                "jobs",
                "worker",
                "trainer",
                ("nvidia-smi", "-pl", "100"),
                1,
            )

    def test_exec_reads_exit_code_and_timeout(self):
        api = FakeApi(pods=[pod("nvidia-driver-daemonset-abc", "gpu-node")])
        reader = KubernetesPodReader(api)

        class Connection:
            def __init__(self, open_after=False):
                self.open_after = open_after
                self.closed = False
                self.returncode = 0

            def run_forever(self, timeout):
                pass

            def read_stdout(self):
                return GPU_LIST

            def read_stderr(self):
                return ""

            def is_open(self):
                return self.open_after

            def close(self):
                self.closed = True

        connection = Connection()
        with patch("krkn_lib.gpu.reader.stream", return_value=connection):
            result = reader.query_node("gpu-node", ("nvidia-smi", "-L"), 1)
        self.assertTrue(result.succeeded)
        self.assertTrue(connection.closed)
        timeout_connection = Connection(open_after=True)
        with patch(
            "krkn_lib.gpu.reader.stream", return_value=timeout_connection
        ):
            result = reader.query_node("gpu-node", ("nvidia-smi", "-L"), 1)
        self.assertTrue(result.timed_out)
        self.assertTrue(timeout_connection.closed)


if __name__ == "__main__":
    unittest.main()
