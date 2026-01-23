"""
System module (cpu/ram/disk/net/uptime).
Move general system/stat collection code here in small commits.
"""

from __future__ import annotations

import shutil
import subprocess
import socket

import psutil

# Optional Qt (clipboard). Prefer PySide6 (matches main.py), fallback to PyQt6.
try:
    from PySide6 import QtCore, QtWidgets  # type: ignore
except Exception:
    try:
        from PyQt6 import QtCore, QtWidgets  # type: ignore
    except Exception:
        QtCore = None  # type: ignore
        QtWidgets = None  # type: ignore

# -------------------- helpers --------------------
def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run_cmd(args: list[str], timeout_s: int = 4) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        return cp.returncode, (cp.stdout or "").strip(), (cp.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout_s}s"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"

def clip_set_text(text: str):
    if QtWidgets is None or QtCore is None:
        raise RuntimeError("Qt clipboard unavailable (PyQt6 not installed/importable in system.py)")
    cb = QtWidgets.QApplication.clipboard()
    md = QtCore.QMimeData()
    md.setText(text)
    cb.setMimeData(md)

def worst_state(states: list[str]) -> str:
    if "Hot" in states:
        return "Hot"
    if "Warm" in states:
        return "Warm"
    return "Normal"


def state_for(v: float | None, warm: float, hot: float) -> str | None:
    if v is None:
        return None
    if v < warm:
        return "Normal"
    if v < hot:
        return "Warm"
    return "Hot"


def human_bps(bps: float) -> str:
    # bytes/sec to human string
    if bps < 1024:
        return f"{bps:.0f} B/s"
    kb = bps / 1024.0
    if kb < 1024:
        return f"{kb:.1f} KB/s"
    mb = kb / 1024.0
    if mb < 1024:
        return f"{mb:.2f} MB/s"
    gb = mb / 1024.0
    return f"{gb:.2f} GB/s"


def bps_to_mbps(bps_bytes_per_s: float) -> float:
    # bytes/s -> megabits/s
    return (bps_bytes_per_s * 8.0) / 1_000_000.0

# -------------------- power profiles --------------------
def powerprofiles_get_active() -> tuple[str, str]:
    if not which("powerprofilesctl"):
        return "—", "missing: powerprofilesctl"
    rc, out, err = run_cmd(["powerprofilesctl", "get"], timeout_s=2)
    if rc != 0:
        return "—", f"powerprofilesctl get failed (rc={rc}): {err or out}"
    v = out.strip().lower()
    if "power-saver" in v or "power saver" in v:
        return "Quiet", ""
    if "balanced" in v:
        return "Balanced", ""
    if "performance" in v:
        return "Performance", ""
    return out.strip() or "—", ""


def powerprofiles_set(mode: str) -> tuple[bool, str]:
    if not which("powerprofilesctl"):
        return False, "powerprofilesctl not installed"
    mapping = {"Quiet": "power-saver", "Balanced": "balanced", "Performance": "performance"}
    prof = mapping.get(mode)
    if not prof:
        return False, "unknown mode"
    rc, out, err = run_cmd(["powerprofilesctl", "set", prof], timeout_s=2)
    if rc != 0:
        return False, (err or out or f"rc={rc}")
    return True, ""


# -------------------- network helpers --------------------
def get_default_iface_and_ip() -> tuple[str | None, str | None]:
    # Prefer the system default route (most accurate)
    try:
        rc, out, _ = run_cmd(["ip", "-o", "-4", "route", "show", "to", "default"], timeout_s=2)
        if rc == 0 and out:
            # example: "default via 192.168.1.1 dev wlp192s0 proto dhcp src 192.168.1.20 metric 600"
            parts = out.split()
            if "dev" in parts and "src" in parts:
                nic = parts[parts.index("dev") + 1]
                ip = parts[parts.index("src") + 1]
                return nic, ip
    except Exception:
        pass

    # Fallback: choose interface with non-loopback IPv4 and is up
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for nic, st in stats.items():
            if not st.isup or nic.lower().startswith("lo"):
                continue
            for a in addrs.get(nic, []):
                if a.family == socket.AF_INET and a.address and not a.address.startswith("127."):
                    return nic, a.address
    except Exception:
        pass

    return None, None

def nmcli_wifi_status() -> tuple[str | None, int | None, str | None]:
    """
    Returns (ssid, signal_percent, rate) for active wifi if nmcli exists.

    Supports both:
      - ACTIVE style: "yes:<ssid>:<signal>:<rate>" (when using ACTIVE field)
      - IN-USE style: "*:<ssid>:<signal>:<rate>"  (common default on Mint)
    """
    if not which("nmcli"):
        return None, None, None

    # 1) Try ACTIVE format (yes:)
    rc, out, err = run_cmd(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,RATE", "dev", "wifi"], timeout_s=3)
    if rc == 0 and out:
        for line in out.splitlines():
            if line.startswith("yes:"):
                parts = line.split(":")
                if len(parts) >= 4:
                    ssid = parts[1] or None
                    try:
                        signal = int(parts[2]) if parts[2].isdigit() else None
                    except Exception:
                        signal = None
                    rate = parts[3] or None
                    return ssid, signal, rate

    # 2) Fallback: IN-USE format (*:)
    rc, out, err = run_cmd(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,RATE", "dev", "wifi"], timeout_s=3)
    if rc == 0 and out:
        for line in out.splitlines():
            # "*:Private:76:270 Mbit/s"
            if line.startswith("*:"):
                parts = line.split(":")
                if len(parts) >= 4:
                    ssid = parts[1] or None
                    try:
                        signal = int(parts[2]) if parts[2].isdigit() else None
                    except Exception:
                        signal = None
                    rate = parts[3] or None
                    return ssid, signal, rate

    return None, None, None
