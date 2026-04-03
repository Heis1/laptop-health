from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore

_NET_LAST: dict[str, tuple[float, int, int]] = {}

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

def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return None

def _is_wireless_iface(iface: str) -> bool:
    return os.path.isdir(f"/sys/class/net/{iface}/wireless")

def _is_virtual_iface(iface: str) -> bool:
    if iface == "lo":
        return True
    prefixes = (
        "br-", "docker", "veth", "virbr", "vmnet", "vboxnet", "zt", "tailscale",
        "wg", "tun", "tap", "ham", "ifb",
    )
    if iface.startswith(prefixes):
        return True
    return os.path.islink(f"/sys/class/net/{iface}/device") is False and not _is_wireless_iface(iface)

def _iface_has_carrier(iface: str) -> bool | None:
    carrier = _read_text(f"/sys/class/net/{iface}/carrier")
    if carrier in {"0", "1"}:
        return carrier == "1"
    operstate = _read_text(f"/sys/class/net/{iface}/operstate")
    if operstate:
        return operstate == "up"
    return None

def _iface_link_rate(iface: str) -> str | None:
    if _is_wireless_iface(iface):
        ssid, _signal, rate = _nmcli_wifi_info(iface)
        return rate
    speed = _read_text(f"/sys/class/net/{iface}/speed")
    if speed and speed.isdigit():
        return f"{speed} Mb/s"
    if psutil is not None:
        try:
            st = (psutil.net_if_stats() or {}).get(iface)
            if st and getattr(st, "speed", 0):
                return f"{int(st.speed)} Mb/s"
        except Exception:
            pass
    return None

def _route_ifaces() -> list[str]:
    candidates: list[str] = []
    cmds = [
        ["ip", "-o", "route", "get", "1.1.1.1"],
        ["ip", "route", "show", "default"],
    ]
    for cmd in cmds:
        try:
            out = _run(cmd)
        except Exception:
            continue
        for iface in re.findall(r"\bdev\s+(\S+)", out):
            if iface not in candidates:
                candidates.append(iface)
    return candidates

def _default_iface() -> str | None:
    ranked = active_ifaces()
    if ranked:
        return ranked[0]

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


def active_ifaces() -> list[str]:
    route_ifaces = _route_ifaces()

    if psutil is not None:
        try:
            stats = psutil.net_if_stats() or {}
            addrs = psutil.net_if_addrs() or {}
            ranked: list[tuple[int, str]] = []
            for iface, st in stats.items():
                if iface == "lo" or not getattr(st, "isup", False):
                    continue
                iface_addrs = addrs.get(iface) or []
                has_ipv4 = any(getattr(a, "family", None) == socket.AF_INET for a in iface_addrs)
                carrier = _iface_has_carrier(iface)
                score = 0
                if iface in route_ifaces:
                    score += 80
                if has_ipv4:
                    score += 50
                if carrier is True:
                    score += 40
                if not _is_virtual_iface(iface):
                    score += 20
                if _is_wireless_iface(iface):
                    score += 5
                ranked.append((score, iface))
            if ranked:
                ranked.sort(key=lambda item: (-item[0], item[1]))
                return [iface for _score, iface in ranked]
        except Exception:
            pass

    return route_ifaces

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

def _iface_details(iface: str) -> tuple[str | None, int | None, str | None]:
    if _is_wireless_iface(iface):
        return _nmcli_wifi_info(iface)
    return (None, None, _iface_link_rate(iface))

def _read_iface_bytes(iface: str) -> tuple[int, int] | None:
    if psutil is not None:
        try:
            counters = psutil.net_io_counters(pernic=True) or {}
            nic = counters.get(iface)
            if nic is not None:
                return int(getattr(nic, "bytes_recv", 0)), int(getattr(nic, "bytes_sent", 0))
        except Exception:
            pass
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

def _throughput_mbps(iface: str) -> tuple[float | None, float | None]:
    now = time.monotonic()
    counters = _read_iface_bytes(iface)
    if not counters:
        return (None, None)
    rx, tx = counters
    prev = _NET_LAST.get(iface)
    _NET_LAST[iface] = (now, rx, tx)
    if prev is None:
        return (None, None)
    t0, rx0, tx0 = prev
    dt = max(0.001, now - t0)
    rx_mbps = (max(0, rx - rx0) * 8.0) / (dt * 1_000_000.0)
    tx_mbps = (max(0, tx - tx0) * 8.0) / (dt * 1_000_000.0)
    return (rx_mbps, tx_mbps)

def sample_network(interval_s: float = 0.5, iface_override: str | None = None) -> NetworkSnapshot:
    try:
        iface = iface_override or _default_iface()
        if not iface:
            return NetworkSnapshot(None, None, None, None, None, None, None, None, error="No active interface")

        ip = _iface_ip(iface)
        ssid, signal, rate = _iface_details(iface)

        # Use deltas between refreshes so each reading covers the full elapsed
        # interval instead of a short sleep window that can miss burst traffic.
        rx_mbps, tx_mbps = _throughput_mbps(iface)

        # normalize missing rates to 0.0 (idle is valid, not 'unknown')
        if rx_mbps is None:
            rx_mbps = 0.0
        if tx_mbps is None:
            tx_mbps = 0.0

        lat = _latency_ms()
        return NetworkSnapshot(iface, ip, ssid, signal, rate, rx_mbps, tx_mbps, lat, error=None)
    except Exception as e:
        return NetworkSnapshot(None, None, None, None, None, None, None, None, error=str(e))
