"""Optional local NVML reader for processes with direct GPU access."""

from __future__ import annotations

import importlib
import re
from collections.abc import Sequence
from typing import Any

from .models import (
    Availability,
    Capability,
    Measurement,
    MigPartition,
    PhysicalGpu,
    utc_now,
)
from .parsers import NvidiaQuery, field_definition, supported_fields


def _string(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class LocalNvmlSource:
    """Query only NVML getters; never invoke GPU configuration functions.

    ``nvidia-ml-py`` is optional. An explicitly selected local node must be
    supplied to :class:`NvidiaGpuInspector` before this reader is used.
    """

    def __init__(self, module: Any = None):
        self._module = module

    @property
    def module(self) -> Any:
        if self._module is None:
            try:
                self._module = importlib.import_module("pynvml")
            except ImportError as exc:
                raise RuntimeError(
                    "local NVML requires optional nvidia-ml-py package"
                ) from exc
        return self._module

    def _call(
        self, name: str, *args: Any
    ) -> tuple[Any, Availability, str | None]:
        func = getattr(self.module, name, None)
        if func is None:
            return None, Availability.UNKNOWN, f"NVML binding lacks {name}"
        try:
            return func(*args), Availability.AVAILABLE, None
        except Exception as exc:
            if isinstance(
                exc, getattr(self.module, "NVMLError_NotSupported", ())
            ):
                return (
                    None,
                    Availability.UNSUPPORTED,
                    "NVML reports unsupported",
                )
            return None, Availability.UNAVAILABLE, type(exc).__name__

    def _value(
        self, handle: Any, field_name: str
    ) -> tuple[Any, Availability, str | None]:
        nvml = self.module
        memory_names = {
            "memory_total_bytes": "total",
            "memory_used_bytes": "used",
            "memory_free_bytes": "free",
        }
        if field_name in memory_names:
            memory, status, reason = self._call(
                "nvmlDeviceGetMemoryInfo", handle
            )
            return (
                (
                    getattr(memory, memory_names[field_name], None)
                    if status == Availability.AVAILABLE
                    else None
                ),
                status,
                reason,
            )
        if field_name in {
            "gpu_utilization_percent",
            "memory_activity_percent",
        }:
            rates, status, reason = self._call(
                "nvmlDeviceGetUtilizationRates", handle
            )
            attribute = (
                "gpu" if field_name == "gpu_utilization_percent" else "memory"
            )
            return (
                (
                    getattr(rates, attribute, None)
                    if status == Availability.AVAILABLE
                    else None
                ),
                status,
                reason,
            )
        clocks = {
            "sm_clock_mhz": "NVML_CLOCK_SM",
            "memory_clock_mhz": "NVML_CLOCK_MEM",
        }
        if field_name in clocks:
            kind = getattr(nvml, clocks[field_name], None)
            return self._call("nvmlDeviceGetClockInfo", handle, kind)
        if field_name == "gpu_temperature_c":
            return self._call(
                "nvmlDeviceGetTemperature",
                handle,
                getattr(nvml, "NVML_TEMPERATURE_GPU", None),
            )
        power_functions = {
            "power_draw_w": "nvmlDeviceGetPowerUsage",
            "power_limit_w": "nvmlDeviceGetPowerManagementLimit",
        }
        if field_name in power_functions:
            value, status, reason = self._call(
                power_functions[field_name], handle
            )
            return (
                value / 1000 if status == Availability.AVAILABLE else None,
                status,
                reason,
            )
        if field_name in {"power_min_limit_w", "power_max_limit_w"}:
            limits, status, reason = self._call(
                "nvmlDeviceGetPowerManagementLimitConstraints", handle
            )
            if status == Availability.AVAILABLE:
                index = 0 if field_name == "power_min_limit_w" else 1
                return limits[index] / 1000, status, reason
            return None, status, reason
        event_bits = {
            "sw_power_cap_active": "nvmlClocksEventReasonSwPowerCap",
            "hw_power_brake_active": (
                "nvmlClocksEventReasonHwPowerBrakeSlowdown"
            ),
        }
        if field_name in event_bits:
            mask, status, reason = self._call(
                "nvmlDeviceGetCurrentClocksEventReasons", handle
            )
            bit = getattr(nvml, event_bits[field_name], None)
            if status == Availability.AVAILABLE and bit is not None:
                return bool(mask & bit), status, reason
            return None, status, reason
        pcie_functions = {
            "pcie_link_generation": "nvmlDeviceGetCurrPcieLinkGeneration",
            "pcie_link_width": "nvmlDeviceGetCurrPcieLinkWidth",
            "pcie_replay_count": "nvmlDeviceGetPcieReplayCounter",
        }
        if field_name in pcie_functions:
            return self._call(pcie_functions[field_name], handle)
        ecc = {
            "ecc_volatile_corrected": (
                "NVML_MEMORY_ERROR_TYPE_CORRECTED",
                "NVML_VOLATILE_ECC",
            ),
            "ecc_volatile_uncorrected": (
                "NVML_MEMORY_ERROR_TYPE_UNCORRECTED",
                "NVML_VOLATILE_ECC",
            ),
            "ecc_lifetime_corrected": (
                "NVML_MEMORY_ERROR_TYPE_CORRECTED",
                "NVML_AGGREGATE_ECC",
            ),
            "ecc_lifetime_uncorrected": (
                "NVML_MEMORY_ERROR_TYPE_UNCORRECTED",
                "NVML_AGGREGATE_ECC",
            ),
        }
        if field_name in ecc:
            error_kind, counter_kind = ecc[field_name]
            return self._call(
                "nvmlDeviceGetTotalEccErrors",
                handle,
                getattr(nvml, error_kind, None),
                getattr(nvml, counter_kind, None),
            )
        if field_name.startswith("row_remap_"):
            remaps, status, reason = self._call(
                "nvmlDeviceGetRemappedRows", handle
            )
            if status == Availability.AVAILABLE:
                index = {
                    "row_remap_corrected": 0,
                    "row_remap_uncorrected": 1,
                    "row_remap_pending": 2,
                    "row_remap_failed": 3,
                }[field_name]
                return remaps[index], status, reason
            return None, status, reason
        if field_name in {"nvlink_link_count", "nvlink_state"}:
            maximum = getattr(nvml, "NVML_NVLINK_MAX_LINKS", 0)
            states = [
                self._call("nvmlDeviceGetNvLinkState", handle, index)
                for index in range(maximum)
            ]
            available = [
                bool(value)
                for value, status, _ in states
                if status == Availability.AVAILABLE
            ]
            if available:
                return (
                    (
                        sum(available)
                        if field_name == "nvlink_link_count"
                        else "active" if any(available) else "inactive"
                    ),
                    Availability.AVAILABLE,
                    None,
                )
            return None, Availability.UNKNOWN, "NVLink state unavailable"
        return (
            None,
            Availability.UNKNOWN,
            "no read-only NVML mapping for field",
        )

    def _measurements(
        self,
        handle: Any,
        uuid: str,
        scope: str,
        fields: set[str],
        observed_at: str,
    ) -> list[Measurement]:
        result = []
        for name in sorted(fields):
            unit, value_type = field_definition(name)
            value, status, reason = self._value(handle, name)
            if status == Availability.AVAILABLE and value is None:
                status = Availability.UNKNOWN
                reason = "NVML returned no value"
            result.append(
                Measurement(
                    device_uuid=uuid,
                    scope=scope,
                    field=name,
                    value=value,
                    unit=unit,
                    value_type=value_type,
                    source="nvml",
                    observed_at=observed_at,
                    status=status,
                    reason=reason,
                )
            )
        return result

    def _control_capabilities(
        self, handle: Any, uuid: str
    ) -> list[Capability]:
        limits, power_status, power_reason = self._call(
            "nvmlDeviceGetPowerManagementLimitConstraints", handle
        )
        if power_status == Availability.AVAILABLE:
            if limits and len(limits) == 2 and 0 < limits[0] <= limits[1]:
                power_reason = (
                    "reported power-limit range; write permission not checked"
                )
            else:
                power_status = Availability.UNKNOWN
                power_reason = "usable power-limit range not reported"

        memory_clocks, clock_status, clock_reason = self._call(
            "nvmlDeviceGetSupportedMemoryClocks", handle
        )
        if clock_status == Availability.AVAILABLE:
            if memory_clocks:
                graphics_clocks, clock_status, clock_reason = self._call(
                    "nvmlDeviceGetSupportedGraphicsClocks",
                    handle,
                    memory_clocks[0],
                )
                if clock_status == Availability.AVAILABLE:
                    if graphics_clocks:
                        clock_reason = (
                            "supported clock pair reported; "
                            "write permission not checked"
                        )
                    else:
                        clock_status = Availability.UNKNOWN
                        clock_reason = (
                            "usable supported clock pair not reported"
                        )
            else:
                clock_status = Availability.UNKNOWN
                clock_reason = "usable supported clock pair not reported"

        return [
            Capability(
                name="power_limit_control",
                status=power_status,
                source="nvml",
                device_uuid=uuid,
                reason=power_reason,
            ),
            Capability(
                name="clock_control",
                status=clock_status,
                source="nvml",
                device_uuid=uuid,
                reason=clock_reason,
            ),
        ]

    def collect(self, fields: Sequence[str] | None = None) -> NvidiaQuery:
        """Read one fresh local inventory and selected measurement fields."""

        selected = (
            set(fields) if fields is not None else set(supported_fields())
        )
        invalid = selected - supported_fields()
        if invalid:
            raise ValueError(
                f"unknown GPU fields: {', '.join(sorted(invalid))}"
            )
        nvml = self.module
        nvml.nvmlInit()
        try:
            result = NvidiaQuery()
            driver, status, _ = self._call("nvmlSystemGetDriverVersion")
            if status == Availability.AVAILABLE:
                result.driver_version = _string(driver)
            cuda, status, _ = self._call("nvmlSystemGetCudaDriverVersion_v2")
            if status == Availability.AVAILABLE:
                result.cuda_driver_supported_version = (
                    f"{cuda // 1000}.{(cuda % 1000) // 10}"
                )
            count = nvml.nvmlDeviceGetCount()
            observed_at = utc_now()
            for index in range(count):
                handle, status, reason = self._call(
                    "nvmlDeviceGetHandleByIndex", index
                )
                if status != Availability.AVAILABLE:
                    result.gpus.append(
                        PhysicalGpu(
                            uuid=None,
                            pci_bus_id=None,
                            local_index=index,
                            status=status,
                            reason=reason,
                            source="nvml",
                        )
                    )
                    continue
                uuid, uuid_status, uuid_reason = self._call(
                    "nvmlDeviceGetUUID", handle
                )
                uuid = (
                    _string(uuid)
                    if uuid_status == Availability.AVAILABLE
                    else None
                )
                name, name_status, _ = self._call("nvmlDeviceGetName", handle)
                pci, pci_status, _ = self._call("nvmlDeviceGetPciInfo", handle)
                memory, memory_status, _ = self._call(
                    "nvmlDeviceGetMemoryInfo", handle
                )
                mig, mig_status, _ = self._call("nvmlDeviceGetMigMode", handle)
                result.gpus.append(
                    PhysicalGpu(
                        uuid=uuid,
                        pci_bus_id=(
                            _string(pci.busId)
                            if pci_status == Availability.AVAILABLE
                            else None
                        ),
                        local_index=index,
                        model=(
                            _string(name)
                            if name_status == Availability.AVAILABLE
                            else None
                        ),
                        memory_total_bytes=(
                            memory.total
                            if memory_status == Availability.AVAILABLE
                            else None
                        ),
                        mig_enabled=(
                            bool(mig[0])
                            if mig_status == Availability.AVAILABLE
                            else None
                        ),
                        status=uuid_status,
                        reason=uuid_reason,
                        source="nvml",
                        observed_at=observed_at,
                    )
                )
                if uuid:
                    values = self._measurements(
                        handle, uuid, "physical_gpu", selected, observed_at
                    )
                    result.measurements.extend(values)
                    result.capabilities.extend(
                        self._control_capabilities(handle, uuid)
                    )
                    result.capabilities.extend(
                        Capability(
                            name=value.field,
                            status=value.status,
                            source="nvml",
                            device_uuid=uuid,
                            reason=value.reason,
                        )
                        for value in values
                    )
                if (
                    not uuid
                    or mig_status != Availability.AVAILABLE
                    or not mig[0]
                ):
                    continue
                maximum, max_status, _ = self._call(
                    "nvmlDeviceGetMaxMigDeviceCount", handle
                )
                if max_status != Availability.AVAILABLE:
                    continue
                for mig_index in range(maximum):
                    mig_handle, mig_status, _ = self._call(
                        "nvmlDeviceGetMigDeviceHandleByIndex",
                        handle,
                        mig_index,
                    )
                    if mig_status != Availability.AVAILABLE:
                        continue
                    mig_uuid, uuid_status, reason = self._call(
                        "nvmlDeviceGetUUID", mig_handle
                    )
                    mig_uuid = (
                        _string(mig_uuid)
                        if uuid_status == Availability.AVAILABLE
                        else None
                    )
                    mig_name, name_status, _ = self._call(
                        "nvmlDeviceGetName", mig_handle
                    )
                    profile = None
                    if name_status == Availability.AVAILABLE:
                        found = re.search(
                            r"\d+(?:c\.\d+g|g)\.\d+gb", _string(mig_name)
                        )
                        profile = found.group(0) if found else None
                    gi, gi_status, _ = self._call(
                        "nvmlDeviceGetGpuInstanceId", mig_handle
                    )
                    ci, ci_status, _ = self._call(
                        "nvmlDeviceGetComputeInstanceId", mig_handle
                    )
                    mig_memory, memory_status, _ = self._call(
                        "nvmlDeviceGetMemoryInfo", mig_handle
                    )
                    result.mig_partitions.append(
                        MigPartition(
                            parent_uuid=uuid,
                            uuid=mig_uuid,
                            profile=profile,
                            gpu_instance_id=(
                                gi
                                if gi_status == Availability.AVAILABLE
                                else None
                            ),
                            compute_instance_id=(
                                ci
                                if ci_status == Availability.AVAILABLE
                                else None
                            ),
                            memory_total_bytes=(
                                mig_memory.total
                                if memory_status == Availability.AVAILABLE
                                else None
                            ),
                            status=uuid_status,
                            reason=reason,
                            source="nvml",
                            observed_at=observed_at,
                        )
                    )
                    if mig_uuid:
                        result.measurements.extend(
                            self._measurements(
                                mig_handle,
                                mig_uuid,
                                "mig_partition",
                                selected,
                                observed_at,
                            )
                        )
            return result
        finally:
            nvml.nvmlShutdown()
