from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore


@dataclass
class OverviewMetrics:
    cpu_temp_c: float | None
    cpu_freq_ghz: float | None

    # Home filesystem (contains Path.home())
    home_used_pct: int | None
    home_free_gb: float | None
    home_mount: str | None

    # Root filesystem ("/")
    root_used_pct: int | None
    root_free_gb: float | None

    down_mbps: float | None
    latency_ms: float | None
    updates_available: int | None


def _cpu_temp() -> float | None:
    if psutil is not None:
        try:
            temps = psutil.sensors_temperatures(fahrenheit=False) or {}
            for key in ("k10temp", "coretemp", "cpu_thermal", "acpitz"):
                if key in temps and temps[key]:
                    vals = [t.current for t in temps[key] if t.current is not None]
                    if vals:
                        return float(max(vals))
            for arr in temps.values():
                vals = [t.current for t in arr if t.current is not None]
                if vals:
                    return float(max(vals))
        except Exception:
            pass
    try:
        base = "/sys/class/thermal"
        if os.path.isdir(base):
            best = None
            for name in os.listdir(base):
                if not name.startswith("thermal_zone"):
                    continue
                p = os.path.join(base, name, "temp")
                try:
                    raw = open(p, "r", encoding="utf-8").read().strip()
                    if not raw:
                        continue
                    v = float(raw)
                    if v > 1000:
                        v /= 1000.0
                    best = v if best is None else max(best, v)
                except Exception:
                    continue
            if best is not None:
                return float(best)
    except Exception:
        pass
    return None


def _cpu_freq_ghz() -> float | None:
    if psutil is not None:
        try:
            f = psutil.cpu_freq()
            if f and f.current:
                return float(f.current) / 1000.0
        except Exception:
            pass
    try:
        mhz = []
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "cpu MHz" in line:
                    m = re.search(r"cpu MHz\s*:\s*([0-9.]+)", line)
                    if m:
                        mhz.append(float(m.group(1)))
        if mhz:
            return (sum(mhz) / len(mhz)) / 1000.0
    except Exception:
        pass
    return None


def _find_mountpoint_for_path(target_path: str) -> str:
    target = Path(target_path).resolve()
    mounts: list[tuple[Path, str]] = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    try:
                        mounts.append((Path(mp).resolve(), mp))
                    except Exception:
                        continue
    except Exception:
        return "/"

    best = "/"
    best_len = 1
    for resolved_mp, mp_str in mounts:
        try:
            if str(target) == str(resolved_mp) or str(target).startswith(str(resolved_mp) + "/"):
                l = len(str(resolved_mp))
                if l > best_len:
                    best_len = l
                    best = mp_str
        except Exception:
            continue
    return best


def _disk_usage(mount: str) -> tuple[int | None, float | None]:
    try:
        du = shutil.disk_usage(mount)
        used_pct = int(round((du.used / du.total) * 100))
        free_gb = du.free / (1024**3)
        return used_pct, free_gb
    except Exception:
        return None, None


def _default_iface() -> str | None:
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL)
        m = re.search(r"\bdev\s+(\S+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        with open("/proc/net/dev", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if ":" not in line:
                    continue
                iface = line.split(":", 1)[0].strip()
                if iface and iface != "lo":
                    return iface
    except Exception:
        pass
    return None


def _read_iface_bytes(iface: str) -> tuple[int, int] | None:
    try:
        with open("/proc/net/dev", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if f"{iface}:" in line:
                    data = line.split(":", 1)[1].split()
                    rx = int(data[0])
                    tx = int(data[8])
                    return rx, tx
    except Exception:
        pass
    return None


def _latency_ms() -> float | None:
    try:
        out = subprocess.check_output(
            ["ping", "-n", "-c", "1", "-W", "1", "1.1.1.1"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        m = re.search(r"time=([0-9.]+)\s*ms", out)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def _updates_available() -> int | None:
    try:
        out = subprocess.check_output(["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2 | wc -l"], text=True)
        return int(out.strip())
    except Exception:
        return None


def gather_overview(interval_s: float = 1.0) -> OverviewMetrics:
    iface = _default_iface()
    down_mbps = None

    if iface:
        b1 = _read_iface_bytes(iface)
        if b1:
            time.sleep(max(0.5, float(interval_s)))
            b2 = _read_iface_bytes(iface)
            if b2:
                rx1, _ = b1
                rx2, _ = b2
                rx_delta = max(0, rx2 - rx1)
                down_mbps = (rx_delta * 8.0) / (max(0.5, float(interval_s)) * 1_000_000.0)

    home_dir = str(Path.home())
    home_mount = _find_mountpoint_for_path(home_dir)

    home_used, home_free = _disk_usage(home_mount)
    root_used, root_free = _disk_usage("/")

    return OverviewMetrics(
        cpu_temp_c=_cpu_temp(),
        cpu_freq_ghz=_cpu_freq_ghz(),
        home_used_pct=home_used,
        home_free_gb=home_free,
        home_mount=home_mount,
        root_used_pct=root_used,
        root_free_gb=root_free,
        down_mbps=down_mbps,
        latency_ms=_latency_ms(),
        updates_available=_updates_available(),
    )
