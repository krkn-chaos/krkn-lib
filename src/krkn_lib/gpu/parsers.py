"""Parsers for read-only output from NVIDIA tools."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .models import (
    Availability,
    Capability,
    Measurement,
    MigPartition,
    PhysicalGpu,
    TopologyLink,
    utc_now,
)

_GPU_LINE = re.compile(r"^GPU\s+(\d+):\s+(.+?)\s+\(UUID:\s*(GPU-[^)]+)\)")
_MIG_LINE = re.compile(
    r"^MIG\s+(.+?)\s+Device\s+\d+:\s+\(UUID:\s*(MIG-[^)]+)\)"
)
_NUMBER = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$")
_MIG_LEGACY = re.compile(r"^MIG-(GPU-.+)/(\d+)/(\d+)$")
_UNSUPPORTED = {"n/a", "not supported", "unsupported", "-"}


@dataclass
class NvidiaQuery:
    gpus: list[PhysicalGpu] = field(default_factory=list)
    mig_partitions: list[MigPartition] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    driver_version: str | None = None
    cuda_driver_supported_version: str | None = None


def parse_device_list(
    output: str,
) -> tuple[list[PhysicalGpu], list[MigPartition]]:
    """Parse ``nvidia-smi -L`` without counting MIG children as cards."""

    gpus: list[PhysicalGpu] = []
    partitions: list[MigPartition] = []
    parent_uuid: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = _GPU_LINE.match(line)
        if match:
            index, model, parent_uuid = match.groups()
            gpus.append(
                PhysicalGpu(
                    uuid=parent_uuid,
                    pci_bus_id=None,
                    local_index=int(index),
                    model=model,
                    status=Availability.AVAILABLE,
                    source="nvidia-smi -L",
                )
            )
            continue
        match = _MIG_LINE.match(line)
        if match and parent_uuid:
            profile, mig_uuid = match.groups()
            legacy = _MIG_LEGACY.match(mig_uuid)
            partitions.append(
                MigPartition(
                    parent_uuid=parent_uuid,
                    uuid=mig_uuid,
                    profile=profile,
                    gpu_instance_id=int(legacy.group(2)) if legacy else None,
                    compute_instance_id=(
                        int(legacy.group(3)) if legacy else None
                    ),
                    status=Availability.AVAILABLE,
                    source="nvidia-smi -L",
                )
            )
    return gpus, partitions


_METRICS: dict[str, tuple[tuple[str, ...], str | None, str]] = {
    "memory_total_bytes": (("fb_memory_usage/total",), "bytes", "int"),
    "memory_used_bytes": (("fb_memory_usage/used",), "bytes", "int"),
    "memory_free_bytes": (("fb_memory_usage/free",), "bytes", "int"),
    "gpu_utilization_percent": (("utilization/gpu_util",), "percent", "float"),
    "memory_activity_percent": (
        ("utilization/memory_util",),
        "percent",
        "float",
    ),
    "sm_clock_mhz": (("clocks/sm_clock",), "MHz", "int"),
    "memory_clock_mhz": (("clocks/mem_clock",), "MHz", "int"),
    "gpu_temperature_c": (("temperature/gpu_temp",), "C", "float"),
    "memory_temperature_c": (("temperature/memory_temp",), "C", "float"),
    "power_draw_w": (
        (
            "gpu_power_readings/instant_power_draw",
            "gpu_power_readings/power_draw",
            "power_readings/instantaneous_power_draw",
            "power_readings/power_draw",
        ),
        "W",
        "float",
    ),
    "power_limit_w": (
        (
            "gpu_power_readings/current_power_limit",
            "power_readings/power_limit",
            "power_readings/current_power_limit",
        ),
        "W",
        "float",
    ),
    "power_enforced_limit_w": (
        (
            "gpu_power_readings/enforced_power_limit",
            "power_readings/enforced_power_limit",
        ),
        "W",
        "float",
    ),
    "power_min_limit_w": (
        (
            "gpu_power_readings/min_power_limit",
            "power_readings/min_power_limit",
        ),
        "W",
        "float",
    ),
    "power_max_limit_w": (
        (
            "gpu_power_readings/max_power_limit",
            "power_readings/max_power_limit",
        ),
        "W",
        "float",
    ),
    "sw_power_cap_active": (
        (
            "clocks_event_reasons/clocks_event_reason_sw_power_cap",
            "clocks_throttle_reasons/clocks_throttle_reason_sw_power_cap",
        ),
        None,
        "bool",
    ),
    "hw_power_brake_active": (
        (
            "clocks_event_reasons/clocks_event_reason_hw_power_brake_slowdown",
            "clocks_throttle_reasons/"
            "clocks_throttle_reason_hw_power_brake_slowdown",
        ),
        None,
        "bool",
    ),
    "pcie_link_generation": (
        ("pci/pci_gpu_link_info/pcie_gen/current_link_gen",),
        "generation",
        "int",
    ),
    "pcie_link_width": (
        ("pci/pci_gpu_link_info/link_widths/current_link_width",),
        "lanes",
        "int",
    ),
    "pcie_replay_count": (("pci/replay_counter",), "count", "int"),
    "ecc_volatile_corrected": (
        ("ecc_errors/volatile/single_bit/total",),
        "count",
        "int",
    ),
    "ecc_volatile_uncorrected": (
        ("ecc_errors/volatile/double_bit/total",),
        "count",
        "int",
    ),
    "ecc_lifetime_corrected": (
        ("ecc_errors/aggregate/single_bit/total",),
        "count",
        "int",
    ),
    "ecc_lifetime_uncorrected": (
        ("ecc_errors/aggregate/double_bit/total",),
        "count",
        "int",
    ),
    "row_remap_corrected": (
        ("remapped_rows/correctable",),
        "count",
        "int",
    ),
    "row_remap_uncorrected": (
        ("remapped_rows/uncorrectable",),
        "count",
        "int",
    ),
    "row_remap_pending": (("remapped_rows/pending",), None, "bool"),
    "row_remap_failed": (("remapped_rows/failed",), None, "bool"),
    "recovery_action": (("gpu_recovery_action",), None, "str"),
    "xid_last_code": (("xid_error",), None, "int"),
    "nvlink_link_count": (("nvlink/link_count",), "count", "int"),
    "nvlink_state": (("nvlink/link_state",), None, "str"),
    "nvlink_error_count": (("nvlink/error_counter",), "count", "int"),
    "nvlink_rx_bytes": (("nvlink/rx_bytes",), "bytes", "int"),
    "nvlink_tx_bytes": (("nvlink/tx_bytes",), "bytes", "int"),
}


def supported_fields() -> frozenset[str]:
    """Recognized fields; availability depends on GPU and selected source."""

    return frozenset(_METRICS)


def field_definition(name: str) -> tuple[str | None, str]:
    """Return normalized unit and value type for a supported field."""

    _, unit, value_type = _METRICS[name]
    return unit, value_type


def _find_text(element: ET.Element, paths: tuple[str, ...]) -> str | None:
    for path in paths:
        text = element.findtext(path)
        if text is not None:
            return text.strip()
    return None


def _read_value(
    raw: str | None, unit: str | None, value_type: str
) -> tuple[int | float | bool | str | None, Availability, str | None]:
    if raw is None or not raw.strip():
        return None, Availability.UNKNOWN, "field absent from source"
    raw = raw.strip()
    if raw.lower() in _UNSUPPORTED:
        return None, Availability.UNSUPPORTED, f"source reported {raw}"
    if raw.lower() in {"unknown", "not available"}:
        return None, Availability.UNKNOWN, f"source reported {raw}"
    if value_type == "str":
        return raw, Availability.AVAILABLE, None
    if value_type == "bool":
        if raw.lower() in {"active", "enabled", "yes", "true"}:
            return True, Availability.AVAILABLE, None
        if raw.lower() in {"not active", "disabled", "no", "false"}:
            return False, Availability.AVAILABLE, None
        return None, Availability.UNKNOWN, f"unrecognized value: {raw}"
    match = _NUMBER.match(raw)
    if not match:
        return None, Availability.UNKNOWN, f"unrecognized value: {raw}"
    number, raw_unit = match.groups()
    if unit == "bytes":
        multipliers = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3}
        multiplier = multipliers.get(raw_unit.strip().lower())
        if multiplier is None:
            return (
                None,
                Availability.UNKNOWN,
                f"unknown memory unit: {raw_unit}",
            )
        return int(float(number) * multiplier), Availability.AVAILABLE, None
    expected = {
        "percent": {"%"},
        "MHz": {"MHz"},
        "C": {"C"},
        "W": {"W"},
        "count": {""},
        "generation": {""},
        "lanes": {"x", ""},
    }
    if unit in expected and raw_unit.strip() not in expected[unit]:
        return None, Availability.UNKNOWN, f"unexpected unit: {raw_unit}"
    value = float(number)
    return (
        int(value) if value_type == "int" else value,
        Availability.AVAILABLE,
        None,
    )


def parse_gpu_xml(output: str, fields: set[str] | None = None) -> NvidiaQuery:
    """Parse a bounded ``nvidia-smi -q -x`` response.

    Missing tags remain unknown; ``N/A`` is unsupported. Nothing becomes zero
    merely because XML omits a field.
    """

    if len(output) > 8 * 1024 * 1024:
        raise ValueError("nvidia-smi XML exceeds 8 MiB")
    root = ET.fromstring(output)
    if root.tag != "nvidia_smi_log":
        raise ValueError("unexpected nvidia-smi XML root")
    result = NvidiaQuery(
        driver_version=root.findtext("driver_version"),
        cuda_driver_supported_version=root.findtext("cuda_version"),
    )
    selected = set(_METRICS) if fields is None else fields
    invalid = selected - _METRICS.keys()
    if invalid:
        raise ValueError(f"unknown GPU fields: {', '.join(sorted(invalid))}")
    observed_at = utc_now()
    for index, element in enumerate(root.findall("gpu")):
        uuid = element.findtext("uuid")
        pci = _find_text(element, ("pci/pci_bus_id",)) or element.get("id")
        mig_raw = _find_text(element, ("mig_mode/current_mig",))
        mig_enabled = None
        if mig_raw in {"Enabled", "Disabled"}:
            mig_enabled = mig_raw == "Enabled"
        memory_raw = _find_text(element, ("fb_memory_usage/total",))
        memory, _, _ = _read_value(memory_raw, "bytes", "int")
        gpu = PhysicalGpu(
            uuid=uuid,
            pci_bus_id=pci,
            local_index=index,
            model=element.findtext("product_name"),
            memory_total_bytes=memory if isinstance(memory, int) else None,
            mig_enabled=mig_enabled,
            status=Availability.AVAILABLE if uuid else Availability.UNKNOWN,
            reason=None if uuid else "GPU UUID missing from source",
            source="nvidia-smi -q -x",
        )
        result.gpus.append(gpu)
        if not uuid:
            continue
        min_power, min_status, _ = _read_value(
            _find_text(element, _METRICS["power_min_limit_w"][0]), "W", "float"
        )
        max_power, max_status, _ = _read_value(
            _find_text(element, _METRICS["power_max_limit_w"][0]), "W", "float"
        )
        power_status = Availability.UNKNOWN
        if min_status == max_status == Availability.AVAILABLE:
            if 0 < min_power <= max_power:
                power_status = Availability.AVAILABLE
        elif Availability.UNSUPPORTED in (min_status, max_status):
            power_status = Availability.UNSUPPORTED
        result.capabilities.append(
            Capability(
                name="power_limit_control",
                status=power_status,
                source="nvidia-smi -q -x",
                device_uuid=uuid,
                reason=(
                    "reported power-limit range; write permission not checked"
                    if power_status == Availability.AVAILABLE
                    else "usable power-limit range not reported"
                ),
            )
        )
        supported_clocks = element.find("supported_clocks")
        clock_pairs = (
            supported_clocks.findall("supported_mem_clock")
            if supported_clocks is not None
            else []
        )
        clock_available = False
        clock_unsupported = (
            supported_clocks is not None
            and (supported_clocks.text or "").strip().lower() in _UNSUPPORTED
        )
        for mem in clock_pairs:
            mem_status = _read_value(mem.findtext("value"), "MHz", "int")[1]
            graphics_statuses = [
                _read_value(graphics.text, "MHz", "int")[1]
                for graphics in mem.findall("supported_graphics_clock")
            ]
            if mem_status == Availability.AVAILABLE:
                clock_available = (
                    clock_available
                    or Availability.AVAILABLE in graphics_statuses
                )
            clock_unsupported = (
                clock_unsupported
                or mem_status == Availability.UNSUPPORTED
                or Availability.UNSUPPORTED in graphics_statuses
            )
        if clock_available:
            clock_status = Availability.AVAILABLE
        elif clock_unsupported:
            clock_status = Availability.UNSUPPORTED
        else:
            clock_status = Availability.UNKNOWN
        result.capabilities.append(
            Capability(
                name="clock_control",
                status=clock_status,
                source="nvidia-smi -q -x",
                device_uuid=uuid,
                reason=(
                    "supported clock pair reported; "
                    "write permission not checked"
                    if clock_status == Availability.AVAILABLE
                    else "usable supported clock pair not reported"
                ),
            )
        )
        for name in sorted(selected):
            paths, unit, value_type = _METRICS[name]
            raw = _find_text(element, paths)
            value, status, reason = _read_value(raw, unit, value_type)
            result.measurements.append(
                Measurement(
                    device_uuid=uuid,
                    scope="physical_gpu",
                    field=name,
                    value=value,
                    unit=unit,
                    value_type=value_type,
                    source="nvidia-smi -q -x",
                    observed_at=observed_at,
                    status=status,
                    reason=reason,
                )
            )
            result.capabilities.append(
                Capability(
                    name=name,
                    status=status,
                    source="nvidia-smi -q -x",
                    device_uuid=uuid,
                )
            )
        for mig in element.findall("mig_devices/mig_device"):
            partition_uuid = _find_text(mig, ("uuid", "mig_uuid"))
            profile = _find_text(mig, ("gpu_instance_profile_name", "profile"))
            gi, _, _ = _read_value(
                mig.findtext("gpu_instance_id"), None, "int"
            )
            ci, _, _ = _read_value(
                mig.findtext("compute_instance_id"), None, "int"
            )
            mig_memory, _, _ = _read_value(
                _find_text(
                    mig, ("fb_memory_usage/total", "memory_usage/total")
                ),
                "bytes",
                "int",
            )
            result.mig_partitions.append(
                MigPartition(
                    parent_uuid=uuid,
                    uuid=partition_uuid,
                    profile=profile,
                    gpu_instance_id=gi if isinstance(gi, int) else None,
                    compute_instance_id=ci if isinstance(ci, int) else None,
                    memory_total_bytes=(
                        mig_memory if isinstance(mig_memory, int) else None
                    ),
                    status=(
                        Availability.AVAILABLE
                        if partition_uuid
                        else Availability.UNKNOWN
                    ),
                    reason=None if partition_uuid else "MIG UUID missing",
                    source="nvidia-smi -q -x",
                )
            )
            if partition_uuid:
                for name in sorted(
                    selected
                    & {
                        "memory_total_bytes",
                        "memory_used_bytes",
                        "memory_free_bytes",
                    }
                ):
                    paths, unit, value_type = _METRICS[name]
                    value, status, reason = _read_value(
                        _find_text(mig, paths), unit, value_type
                    )
                    result.measurements.append(
                        Measurement(
                            device_uuid=partition_uuid,
                            scope="mig_partition",
                            field=name,
                            value=value,
                            unit=unit,
                            value_type=value_type,
                            source="nvidia-smi -q -x",
                            observed_at=observed_at,
                            status=status,
                            reason=reason,
                        )
                    )
    return result


def parse_topology(
    output: str, gpu_index_to_uuid: dict[int, str]
) -> list[TopologyLink]:
    """Read GPU-pair and GPU-NIC relationships from ``nvidia-smi topo -m``."""

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    header = next(
        (line.split() for line in lines if line.startswith("GPU0")), []
    )
    peers = [item for item in header if re.fullmatch(r"GPU\d+|NIC\d+", item)]
    links: list[TopologyLink] = []
    for line in lines:
        parts = line.split()
        if not parts or not re.fullmatch(r"GPU\d+", parts[0]):
            continue
        source_index = int(parts[0][3:])
        source_uuid = gpu_index_to_uuid.get(source_index)
        if not source_uuid or len(parts) <= len(peers):
            continue
        cpu_affinity = (
            parts[len(peers) + 1] if len(parts) > len(peers) + 1 else None
        )
        numa_affinity = (
            parts[len(peers) + 2] if len(parts) > len(peers) + 2 else None
        )
        for column, peer in enumerate(peers):
            relation = parts[column + 1]
            if relation in {"X", "N/A"}:
                continue
            if peer.startswith("GPU"):
                peer_uuid = gpu_index_to_uuid.get(int(peer[3:]))
                if not peer_uuid:
                    continue
                kind = "gpu"
                peer_name = peer_uuid
            else:
                kind = "nic"
                peer_name = peer
            links.append(
                TopologyLink(
                    source_uuid=source_uuid,
                    peer=peer_name,
                    peer_kind=kind,
                    relationship=relation,
                    cpu_affinity=cpu_affinity,
                    numa_affinity=numa_affinity,
                )
            )
    return links
