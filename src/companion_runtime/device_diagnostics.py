"""Local hardware snapshots. No network, identifiers, window or process listing."""
from __future__ import annotations
import csv
import ctypes
import datetime as dt
import io
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

SCHEMA_VERSION = 1
RENDERER_RESERVE_MIB = 2048  # Planning allowance, not measured renderer demand.
CUDA124_MIN_WINDOWS_DRIVER = (551, 61)


def _windows_memory() -> dict:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total_phys", "available_phys", "total_page", "available_page", "total_virtual", "available_virtual", "available_extended")]
    status = MemoryStatus(); status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"available": False, "reason": "memory_query_failed"}
    return {"available": True, "total_mib": round(status.total_phys / 1048576),
            "available_mib": round(status.available_phys / 1048576), "source": "GlobalMemoryStatusEx"}


def _cpu_name() -> str | None:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()[:160]
        except OSError:
            return None
    return platform.processor().strip()[:160] or None


def parse_nvidia_csv(text: str) -> list[dict]:
    """Parse only the four requested public hardware fields, never arbitrary logs."""
    devices = []
    for index, row in enumerate(csv.reader(io.StringIO(text[:16384]))):
        if index >= 8: break
        if len(row) != 4: raise ValueError("Unexpected NVIDIA hardware fields")
        name, total, free, driver = [value.strip() for value in row]
        total_value, free_value = float(total), float(free)
        if not math.isfinite(total_value) or not math.isfinite(free_value):raise ValueError('Non-finite NVIDIA memory')
        total_mib, free_mib = int(total_value), int(free_value)
        if not 0 < total_mib < 1048576 or not 0 <= free_mib <= total_mib: raise ValueError("Invalid NVIDIA memory")
        numbers = driver.split(".")
        minimum = len(numbers) >= 2 and all(value.isdigit() for value in numbers[:2]) and tuple(map(int, numbers[:2])) >= CUDA124_MIN_WINDOWS_DRIVER
        devices.append({"name": name[:160], "memory_total_mib": total_mib,
                        "memory_free_mib": free_mib, "driver_version": driver[:32],
                        "cuda124_conservative_driver_policy_met": bool(minimum),
                        "model_budget_after_renderer_reserve_mib": max(0, free_mib - RENDERER_RESERVE_MIB)})
    return devices


def _nvidia_snapshot() -> dict:
    candidates = []
    if os.name == "nt":
        candidates = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/nvidia-smi.exe",
                      Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe"]
    discovered = shutil.which("nvidia-smi")
    if discovered: candidates.append(Path(discovered))
    executable = next((path for path in candidates if path.is_file()), None)
    if not executable: return {"available": False, "reason": "nvidia_smi_unavailable", "devices": []}
    try:
        result = subprocess.run([str(executable), "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if result.returncode: return {"available": False, "reason": "nvidia_query_failed", "devices": []}
        devices = parse_nvidia_csv(result.stdout)
        return {"available": bool(devices), "devices": devices, "source": "nvidia-smi hardware-only query"}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "nvidia_query_timeout", "devices": []}
    except (OSError, ValueError):
        return {"available": False, "reason": "nvidia_query_unavailable_or_invalid", "devices": []}


def own_process_metrics() -> dict:
    """Measure this Python backend only; no process discovery or command lines."""
    value = {"cpu_seconds": round(os.times().user + os.times().system, 4), "scope": "this Python process only; excludes Electron and child processes"}
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("page_faults", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in
                ("peak_working_set", "working_set", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private_usage")]
        info = Counters(); info.cb = ctypes.sizeof(info)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb):
            value.update({"working_set_mib": round(info.working_set / 1048576, 2), "private_mib": round(info.private_usage / 1048576, 2), "source": "GetProcessMemoryInfo"})
    return value


def collect_diagnostics() -> dict:
    """Read-only snapshot; callers should cache for >=30 seconds to avoid polling SMI."""
    started = time.monotonic()
    memory = _windows_memory() if os.name == "nt" else {"available": False, "reason": "windows_memory_probe_not_applicable"}
    gpu = _nvidia_snapshot()
    result = {"schema_version": SCHEMA_VERSION, "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "platform": {"system": platform.system(), "release": platform.release(), "architecture": platform.machine()},
              "cpu": {"name": _cpu_name(), "logical_processors": os.cpu_count()}, "ram": memory, "nvidia": gpu,
              "backend_process": own_process_metrics(),
              "renderer_reserve": {"mib": RENDERER_RESERVE_MIB, "status": "planning_allowance_not_measurement", "basis": "Candidate headroom for the requested 8GB-class GPU; verify actual renderer and model peaks"},
              "cuda": {"profile": "cu124", "conservative_windows_driver_floor": "551.61", "gpu_acceleration_confirmed": False,
                       "driver_policy_note": "CUDA 12.4 GA driver table used conservatively; CUDA 12.x minor compatibility can allow older drivers, subject to NVIDIA limitations",
                       "meaning": "Physical GPU/driver snapshot does not establish loaded CUDA wheel, actual model offload, or performance",
                       "driver_requirement_source": "https://docs.nvidia.com/cuda/archive/12.4.0/cuda-toolkit-release-notes/index.html"},
              "privacy": {"network_requests": 0, "window_capture": False, "process_list": False, "hardware_serials_or_uuids": False}}
    result["collection_seconds"] = round(time.monotonic() - started, 3)
    return result
