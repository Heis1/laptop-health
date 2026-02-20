from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass

@dataclass
class NetworkSnapshot:
    iface: str | None
    ip: str | None
    ssid: str | None
    signal: int | None
    rate: str | None
    rx_mbps: float | None
    tx_mbps: float | None
    latency_ms: float | None
    error: str | None = None

def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

def _default_iface() -> str | None:
    try:
        out = _run(["ip", "route", "show", "default"])
        m = re.search(r"\bdev\s+(\S+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    # fallback
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

def _iface_ip(iface: str) -> str | None:
    try:
        out = _run(["ip", "-4", "addr", "show", "dev", iface])
        m = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None

def _nmcli_wifi_info(iface: str) -> tuple[str | None, int | None, str | None]:
    """
    Returns (ssid, signal, rate). Best-effort; works on NetworkManager systems.
    """
    try:
        out = _run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,RATE,DEVICE", "dev", "wifi"])
        for line in out.splitlines():
            # *:MySSID:76:270 Mbit/s:wlp192s0
            parts = line.split(":")
            if len(parts) >= 5:
                inuse, ssid, sig, rate, dev = parts[0], parts[1], parts[2], parts[3], parts[4]
                if inuse.strip() == "*" and dev.strip() == iface:
                    try:
                        sig_i = int(sig) if sig.strip() else None
                    except Exception:
                        sig_i = None
                    return (ssid or None, sig_i, rate or None)
    except Exception:
        pass
    return (None, None, None)

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
        return float(m.group(1)) if m else None
    except Exception:
        return None

def sample_network(interval_s: float = 0.5) -> NetworkSnapshot:
    try:
        iface = _default_iface()
        if not iface:
            return NetworkSnapshot(None, None, None, None, None, None, None, None, error="No active interface")

        ip = _iface_ip(iface)
        ssid, signal, rate = _nmcli_wifi_info(iface)

        b1 = _read_iface_bytes(iface)
        time.sleep(max(0.2, float(interval_s)))
        b2 = _read_iface_bytes(iface)

        rx_mbps = tx_mbps = None
        if b1 and b2:
            rx1, tx1 = b1
            rx2, tx2 = b2
            dt = max(0.2, float(interval_s))
            rx_mbps = (max(0, rx2 - rx1) * 8.0) / (dt * 1_000_000.0)
            tx_mbps = (max(0, tx2 - tx1) * 8.0) / (dt * 1_000_000.0)

        lat = _latency_ms()
        return NetworkSnapshot(iface, ip, ssid, signal, rate, rx_mbps, tx_mbps, lat, error=None)
    except Exception as e:
        return NetworkSnapshot(None, None, None, None, None, None, None, None, error=str(e))
