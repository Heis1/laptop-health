from __future__ import annotations

def _read_sensors_ppt_w() -> float | None:
    """CPU package power from lm-sensors output (PPT: XX.XX W)."""
    try:
        import subprocess, re
        out = subprocess.check_output(["sensors"], text=True, errors="replace")
    except Exception:
        return None

    m = re.search(r"(?mi)^\s*PPT:\s*([0-9]*\.?[0-9]+)\s*W\b", out)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass

    # fallback: power1 in mW -> W
    m = re.search(r"(?mi)^\s*power1:\s*([0-9]*\.?[0-9]+)\s*mW\b", out)
    if m:
        try:
            return float(m.group(1)) / 1000.0
        except Exception:
            pass

    return None



def _read_proc_stat_ctxt_intr() -> tuple[int | None, int | None]:
    """Return (ctxt_total, intr_total) from /proc/stat, or (None, None) if unavailable."""
    try:
        ctxt = None
        intr = None
        with open("/proc/stat", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ctxt "):
                    ctxt = int(line.split()[1])
                elif line.startswith("intr "):
                    # intr line: "intr <total> <irq0> <irq1> ..."
                    intr = int(line.split()[1])
                if ctxt is not None and intr is not None:
                    break
        return ctxt, intr
    except Exception:
        return None, None


def _sample_wakeups_over_interval(interval_s: float) -> tuple[float, float]:
    """
    Measure ctxt/s and intr/s over an interval using /proc/stat deltas.
    Falls back to wakeups service if needed.
    """
    import time as _time
    a_ctxt, a_intr = _read_proc_stat_ctxt_intr()
    t0 = _time.time()
    _time.sleep(max(0.5, float(interval_s)))
    b_ctxt, b_intr = _read_proc_stat_ctxt_intr()
    t1 = _time.time()
    dt = max(0.001, t1 - t0)

    if a_ctxt is not None and b_ctxt is not None:
        ctxt_per_s = max(0.0, (b_ctxt - a_ctxt) / dt)
    else:
        ctxt_per_s = 0.0

    if a_intr is not None and b_intr is not None:
        intr_per_s = max(0.0, (b_intr - a_intr) / dt)
    else:
        intr_per_s = 0.0

    # If both are zero, fall back to the existing service (in case it has better logic on some systems)
    if ctxt_per_s == 0.0 and intr_per_s == 0.0:
        try:
            wake = sample_wake_activity_now()
            ctxt_per_s = float(wake.get("ctxt_per_s", 0.0))
            intr_per_s = float(wake.get("intr_per_s", 0.0))
        except Exception:
            pass

    return ctxt_per_s, intr_per_s
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ui_v2.services.updates import get_update_summary
from ui_v2.services.wakeups import sample_wake_activity_now, classify_wakeup_proxy

_rapl_last_energy = None
_rapl_last_time = None

def _read_rapl_power() -> float | None:
    global _rapl_last_energy, _rapl_last_time
    try:
        with open("/sys/class/powercap/intel-rapl:0/energy_uj", "r") as f:
            energy = int(f.read().strip())
        now = time.time()
        if _rapl_last_energy is None:
            _rapl_last_energy = energy
            _rapl_last_time = now
            return None
        delta_e = energy - _rapl_last_energy
        delta_t = now - _rapl_last_time
        _rapl_last_energy = energy
        _rapl_last_time = now
        if delta_t <= 0:
            return None
        watts = (delta_e / 1_000_000) / delta_t
        return round(watts, 2)
    except Exception:
        return None


try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore


@dataclass
class OverviewMetrics:
    cpu_temp_c: float | None = None

    cpu_freq_ghz: float | None = None

    cpu_package_w: float | None = None

    cpu_vcore_v: float | None = None

    ram_used_pct: float | None = None

    ram_used_gb: float | None = None

    ram_total_gb: float | None = None


    # Home filesystem (contains Path.home())
    home_used_pct: int | None = None

    home_free_gb: float | None = None

    home_mount: str | None = None


    # Root filesystem ("/")
    root_used_pct: int | None = None

    root_free_gb: float | None = None


    down_mbps: float | None = None

    latency_ms: float | None = None

    updates_available: int | None = None

    security_updates: int | None = None

    reboot_required: bool | None = None

    kept_back_updates: int = None

    held_updates: int = None

    updates_badge: str = None

    updates_accent: str = None

    wakeups_big: str = None

    wakeups_sub: str = None

    wakeups_accent: str = None



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




def _cpu_voltage_v() -> float | None:
    try:
        base = "/sys/class/hwmon"
        if not os.path.isdir(base):
            return None

        for hw in os.listdir(base):
            hw_path = os.path.join(base, hw)
            name_file = os.path.join(hw_path, "name")
            if not os.path.exists(name_file):
                continue

            name = open(name_file).read().strip().lower()

            if not any(k in name for k in ("core", "cpu", "k10temp", "coretemp")):
                continue

            for file in os.listdir(hw_path):
                if file.startswith("in") and file.endswith("_label"):
                    label_path = os.path.join(hw_path, file)
                    label = open(label_path).read().strip().lower()

                    if any(k in label for k in ("vcore", "vdd", "svi2", "core")):
                        idx = file.replace("_label", "_input")
                        input_path = os.path.join(hw_path, idx)
                        if os.path.exists(input_path):
                            raw = float(open(input_path).read().strip())
                            if raw > 10:
                                raw /= 1000.0
                            if raw > 0:
                                return round(raw, 3)
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


def _ram_snapshot() -> tuple[float | None, float | None, float | None]:
    if psutil is None:
        return None, None, None
    try:
        vm = psutil.virtual_memory()
        total_gb = float(vm.total) / (1024 ** 3)
        used_gb = float(vm.used) / (1024 ** 3)
        used_pct = float(vm.percent)
        return used_pct, used_gb, total_gb
    except Exception:
        return None, None, None


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





# ---------------------------
# Cached (non-blocking) samplers
# ---------------------------
_net_last = None  # (t, rx_bytes, tx_bytes)
_wake_last = None # (t, ctxt_total, intr_total)

def _read_proc_stat_ctxt_intr() -> tuple[int | None, int | None]:
    try:
        ctxt = None
        intr = None
        with open("/proc/stat", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ctxt "):
                    ctxt = int(line.split()[1])
                elif line.startswith("intr "):
                    intr = int(line.split()[1])
                if ctxt is not None and intr is not None:
                    break
        return ctxt, intr
    except Exception:
        return None, None

def _wake_rates_cached() -> tuple[float | None, float | None]:
    """Return (ctxt_per_s, intr_per_s) using cached /proc/stat deltas (no sleep)."""
    global _wake_last
    now = time.time()
    ctxt, intr = _read_proc_stat_ctxt_intr()
    if ctxt is None or intr is None:
        return None, None
    if _wake_last is None:
        _wake_last = (now, ctxt, intr)
        return None, None
    t0, ctxt0, intr0 = _wake_last
    dt = max(0.001, now - t0)
    _wake_last = (now, ctxt, intr)
    return max(0.0, (ctxt - ctxt0) / dt), max(0.0, (intr - intr0) / dt)

def _net_down_mbps_cached(iface: str) -> float | None:
    """Return download Mbps using cached /proc/net/dev deltas (no sleep)."""
    global _net_last
    now = time.time()
    b = _read_iface_bytes(iface)
    if not b:
        return None
    rx, tx = b
    if _net_last is None:
        _net_last = (now, rx, tx)
        return None
    t0, rx0, tx0 = _net_last
    dt = max(0.001, now - t0)
    _net_last = (now, rx, tx)
    rx_delta = max(0, rx - rx0)
    return (rx_delta * 8.0) / (dt * 1_000_000.0)

def gather_fast() -> OverviewMetrics:
    """Fast refresh metrics (no sleeps, no apt): CPU + wakeups + net/latency."""
    iface = _default_iface()
    down_mbps = _net_down_mbps_cached(iface) if iface else None

    # Wakeups: prefer cached /proc/stat delta; fall back to existing helper
    ctxt, intr = _wake_rates_cached()
    if ctxt is None or intr is None:
        try:
            wake = sample_wake_activity_now()
            ctxt = float(wake.get("ctxt_per_s", 0.0))
            intr = float(wake.get("intr_per_s", 0.0))
        except Exception:
            ctxt, intr = 0.0, 0.0

    cpu_package_w = _read_rapl_power()
    if cpu_package_w is None:
        try:
            cpu_package_w = _read_sensors_ppt_w()
        except Exception:
            pass
    ram_used_pct, ram_used_gb, ram_total_gb = _ram_snapshot()

    return OverviewMetrics(
        cpu_temp_c=_cpu_temp(),
        cpu_freq_ghz=_cpu_freq_ghz(),
        cpu_package_w=cpu_package_w,
        cpu_vcore_v=_cpu_voltage_v(),
        ram_used_pct=ram_used_pct,
        ram_used_gb=ram_used_gb,
        ram_total_gb=ram_total_gb,
        down_mbps=down_mbps,
        latency_ms=_latency_ms(),
        wakeups_big=f"{ctxt:,.0f} ctx/s",
        wakeups_sub=f"{intr:,.0f} intr/s",
        wakeups_accent=classify_wakeup_proxy(ctxt, intr),
    )

def gather_slow() -> OverviewMetrics:
    """Slow refresh metrics (disk + updates)."""
    home_dir = str(Path.home())
    home_mount = _find_mountpoint_for_path(home_dir)

    home_used, home_free = _disk_usage(home_mount)
    root_used, root_free = _disk_usage("/")

    upd = get_update_summary()

    return OverviewMetrics(
        home_used_pct=home_used,
        home_free_gb=home_free,
        home_mount=home_mount,
        root_used_pct=root_used,
        root_free_gb=root_free,
        updates_available=upd.total,
        security_updates=upd.security,
        reboot_required=upd.reboot_required,
        kept_back_updates=upd.kept_back,
        held_updates=upd.held,
        updates_badge=upd.badge,
        updates_accent=upd.accent,
    )

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

    cpu_package_w = _read_rapl_power()
    if cpu_package_w is None:
        cpu_package_w = _read_sensors_ppt_w()
    cpu_vcore_v = _cpu_voltage_v()
    ram_used_pct, ram_used_gb, ram_total_gb = _ram_snapshot()
    ctxt, intr = _sample_wakeups_over_interval(interval_s)
    upd = get_update_summary()

    return OverviewMetrics(
        cpu_temp_c=_cpu_temp(),
        cpu_freq_ghz=_cpu_freq_ghz(),
        ram_used_pct=ram_used_pct,
        ram_used_gb=ram_used_gb,
        ram_total_gb=ram_total_gb,
        home_used_pct=home_used,
        home_free_gb=home_free,
        home_mount=home_mount,
        root_used_pct=root_used,
        root_free_gb=root_free,
        down_mbps=down_mbps,
        latency_ms=_latency_ms(),
        updates_available=upd.total,
        security_updates=upd.security,
        reboot_required=upd.reboot_required,
        kept_back_updates=upd.kept_back,
        held_updates=upd.held,
        updates_badge=upd.badge,
        updates_accent=upd.accent,
        wakeups_big=f"{ctxt:,.0f} ctx/s",
        wakeups_sub=f"{intr:,.0f} intr/s",
        wakeups_accent=classify_wakeup_proxy(ctxt, intr),
        cpu_package_w=cpu_package_w,
        cpu_vcore_v=cpu_vcore_v,
    )
