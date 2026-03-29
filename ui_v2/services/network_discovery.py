from __future__ import annotations

import ipaddress
import re
import shutil
import shlex
import socket
import subprocess
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import system as system_utils


@dataclass
class DiscoveredDevice:
    ip: str
    hostname: str | None = None
    mac: str | None = None
    vendor: str | None = None
    os_name: str | None = None


@dataclass
class DiscoveryResult:
    target: str | None
    devices: list[DiscoveredDevice]
    mode: str
    error: str | None = None
    note: str | None = None


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)


def _run_completed(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _run_privileged_completed(cmd: list[str], timeout_s: float = 180.0) -> tuple[int, str, str, str | None]:
    failures: list[str] = []
    for tool in ("pkexec", "sudo"):
        if not system_utils.which(tool):
            continue
        rc, out, err = system_utils.run_privileged(tool, cmd, timeout_s=timeout_s)
        if rc == 0:
            note = None if not failures else " ".join(failures)
            return rc, out, err, note
        msg = (err or out or f"rc={rc}").strip()
        failures.append(f"Privileged scan via {tool} failed: {msg}")
    if failures:
        return 1, "", failures[-1], " ".join(failures)
    return 127, "", "Neither pkexec nor sudo is available.", "Privileged scan unavailable: pkexec/sudo not found."


def _default_iface() -> str | None:
    try:
        out = _run(["ip", "route", "show", "default"])
        m = re.search(r"\bdev\s+(\S+)", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _iface_network(iface: str) -> str | None:
    try:
        out = _run(["ip", "-o", "-4", "addr", "show", "dev", iface])
        m = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", out)
        if not m:
            return None
        return str(ipaddress.ip_interface(m.group(1)).network)
    except Exception:
        return None


def _parse_extra_options(extra_options: str | None) -> tuple[list[str], str | None]:
    text = str(extra_options or "").strip()
    if not text:
        return [], None
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        return [], f"Invalid extra options: {exc}"

    blocked = ("-oX", "-oN", "-oG", "-oA", "-oS", "--webxml", "--stylesheet", "--resume", "-iL", "-iR")
    for part in parts:
        if part in blocked:
            return [], f"Unsupported option for app-managed scan: {part}"
        if any(part.startswith(flag + "=") for flag in blocked):
            return [], f"Unsupported option for app-managed scan: {part.split('=', 1)[0]}"
    return parts, None


def _neighbor_table(iface: str) -> dict[str, tuple[str | None, str | None]]:
    rows: dict[str, tuple[str | None, str | None]] = {}
    try:
        out = _run(["ip", "neigh", "show", "dev", iface])
    except Exception:
        return rows
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 1:
            continue
        ip = parts[0]
        mac = None
        vendor = None
        if "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts):
                mac = parts[idx + 1].upper()
        rows[ip] = (mac, vendor)
    return rows


def _reverse_lookup(ip: str) -> str | None:
    try:
        host, _aliases, _ips = socket.gethostbyaddr(ip)
        host = (host or "").rstrip(".").strip()
        if host and host != ip:
            return host
    except Exception:
        pass
    try:
        out = _run(["getent", "hosts", ip])
        parts = out.strip().split()
        if len(parts) >= 2:
            host = parts[1].rstrip(".").strip()
            if host and host != ip:
                return host
    except Exception:
        pass
    return None


def _parse_xml_nmap(output: str) -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    root = ET.fromstring(output)
    for host in root.findall("host"):
        status = host.find("status")
        if status is not None and status.get("state") != "up":
            continue

        ip = None
        mac = None
        vendor = None
        for addr in host.findall("address"):
            addr_type = (addr.get("addrtype") or "").lower()
            if addr_type == "ipv4":
                ip = addr.get("addr")
            elif addr_type == "mac":
                mac = (addr.get("addr") or "").upper() or None
                vendor = (addr.get("vendor") or "").strip() or None
        if not ip:
            continue

        hostname = None
        hostnames = host.find("hostnames")
        if hostnames is not None:
            hostname_el = hostnames.find("hostname")
            if hostname_el is not None:
                hostname = (hostname_el.get("name") or "").strip() or None

        os_name = None
        os_el = host.find("os")
        if os_el is not None:
            best_match = os_el.find("osmatch")
            if best_match is not None:
                os_name = (best_match.get("name") or "").strip() or None

        devices.append(
            DiscoveredDevice(
                ip=ip,
                hostname=hostname,
                mac=mac,
                vendor=vendor,
                os_name=os_name,
            )
        )

    devices.sort(key=lambda d: tuple(int(part) for part in d.ip.split(".")))
    return devices


def _merge_devices(base: list[DiscoveredDevice], extra: list[DiscoveredDevice]) -> list[DiscoveredDevice]:
    merged: dict[str, DiscoveredDevice] = {dev.ip: dev for dev in base}
    for dev in extra:
        current = merged.get(dev.ip)
        if current is None:
            merged[dev.ip] = dev
            continue
        merged[dev.ip] = DiscoveredDevice(
            ip=dev.ip,
            hostname=dev.hostname or current.hostname,
            mac=dev.mac or current.mac,
            vendor=dev.vendor or current.vendor,
            os_name=dev.os_name or current.os_name,
        )
    return sorted(merged.values(), key=lambda d: tuple(int(part) for part in d.ip.split(".")))


def _enrich_devices(devices: list[DiscoveredDevice], iface: str) -> list[DiscoveredDevice]:
    neigh = _neighbor_table(iface)
    enriched: list[DiscoveredDevice] = []
    for dev in devices:
        mac, vendor = neigh.get(dev.ip, (None, None))
        hostname = dev.hostname or _reverse_lookup(dev.ip)
        enriched.append(
            DiscoveredDevice(
                ip=dev.ip,
                hostname=hostname,
                mac=dev.mac or mac,
                vendor=dev.vendor or vendor,
                os_name=dev.os_name,
            )
        )
    return enriched


def discover_network_devices(
    mode: str = "quiet",
    *,
    target_override: str | None = None,
    extra_options: str | None = None,
) -> DiscoveryResult:
    mode = str(mode or "quiet").strip().lower()
    if mode not in {"quiet", "noisy"}:
        mode = "quiet"

    if not shutil.which("nmap"):
        return DiscoveryResult(None, [], mode, "nmap is not installed")

    iface = _default_iface()
    if not iface:
        return DiscoveryResult(None, [], mode, "No active interface")

    target = str(target_override or "").strip() or _iface_network(iface)
    if not target:
        return DiscoveryResult(None, [], mode, f"Unable to determine subnet for {iface}")

    extra_args, extra_error = _parse_extra_options(extra_options)
    if extra_error:
        return DiscoveryResult(target, [], mode, extra_error)

    try:
        if mode != "noisy":
            cmd = ["nmap", "-sn", "-PR", *extra_args, target, "-oX", "-"]
            out = _run(cmd)
            return DiscoveryResult(target, _enrich_devices(_parse_xml_nmap(out), iface), mode)

        baseline_devices: list[DiscoveredDevice] = []
        privileged_note: str | None = None
        try:
            baseline_out = _run(["nmap", "-sn", "-PR", target, "-oX", "-"])
            baseline_devices = _enrich_devices(_parse_xml_nmap(baseline_out), iface)
        except Exception:
            baseline_devices = []

        primary_rc, primary_out, primary_err, privileged_note = _run_privileged_completed(
            ["nmap", "-sS", "-T4", "-O", "-Pn", *extra_args, target, "-oX", "-"],
            timeout_s=240.0,
        )
        if primary_rc == 0 and primary_out.strip():
            return DiscoveryResult(
                target,
                _enrich_devices(_merge_devices(baseline_devices, _parse_xml_nmap(primary_out)), iface),
                mode,
                note=privileged_note,
            )

        fallback = _run_completed(["nmap", "-sT", "-T4", "-Pn", "-F", "-sV", *extra_args, target, "-oX", "-"])
        if fallback.returncode == 0 and fallback.stdout.strip():
            note = "Noisy scan fell back to non-privileged mode; host discovery data was preserved, but OS detection may be unavailable."
            if privileged_note:
                note = f"{privileged_note} {note}"
            return DiscoveryResult(
                target,
                _enrich_devices(_merge_devices(baseline_devices, _parse_xml_nmap(fallback.stdout)), iface),
                mode,
                note=note,
            )

        err = (primary_err or primary_out or fallback.stderr or fallback.stdout or "").strip()
        if baseline_devices:
            note = f"Noisy scan failed; showing host discovery results only. {err or 'Detailed scan unavailable.'}"
            if privileged_note:
                note = f"{privileged_note} {note}"
            return DiscoveryResult(
                target,
                baseline_devices,
                mode,
                note=note,
            )
        return DiscoveryResult(target, [], mode, err or "nmap scan failed")
    except Exception as exc:
        return DiscoveryResult(target, [], mode, str(exc))
