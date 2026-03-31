#!/usr/bin/env python3
from __future__ import annotations

import json
import hmac
import os
import platform
import shutil
import socket
import ssl
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_expected_token() -> str:
    token_file = (os.getenv("PI_PROBE_TOKEN_FILE") or "").strip()
    if token_file:
        try:
            with open(token_file, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as exc:
            raise RuntimeError(f"Unable to read PI_PROBE_TOKEN_FILE: {exc}") from exc
    return (os.getenv("PI_PROBE_TOKEN") or "").strip()


def read_cpu_temp_c() -> float | None:
    for path in (
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
    ):
        try:
            raw = open(path, "r", encoding="utf-8").read().strip()
            if not raw:
                continue
            value = float(raw)
            return round(value / 1000.0, 1) if value > 1000 else round(value, 1)
        except (OSError, ValueError):
            continue
    return None


def read_loadavg() -> dict[str, float] | None:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return None
    return {"1m": round(one, 2), "5m": round(five, 2), "15m": round(fifteen, 2)}


def read_meminfo() -> dict[str, float] | None:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw_value = line.split(":", 1)
                parts = raw_value.strip().split()
                if parts:
                    values[key] = int(parts[0]) * 1024
    except OSError:
        return None

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None

    used = total - available
    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "used_percent": round((used / total) * 100.0, 1),
    }


def read_disk_usage(path: str = "/") -> dict[str, float] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None

    return {
        "path": path,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round((usage.used / usage.total) * 100.0, 1) if usage.total else 0.0,
    }


def read_uptime_seconds() -> float | None:
    try:
        raw = open("/proc/uptime", "r", encoding="utf-8").read().split()[0]
        return round(float(raw), 1)
    except (OSError, ValueError, IndexError):
        return None


def read_network_counters() -> dict[str, dict[str, int]]:
    counters: dict[str, dict[str, int]] = {}
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            lines = handle.readlines()[2:]
    except OSError:
        return counters

    for line in lines:
        if ":" not in line:
            continue
        iface, payload = line.split(":", 1)
        iface = iface.strip()
        if iface == "lo":
            continue
        fields = payload.split()
        if len(fields) < 16:
            continue
        counters[iface] = {
            "rx_bytes": int(fields[0]),
            "rx_packets": int(fields[1]),
            "tx_bytes": int(fields[8]),
            "tx_packets": int(fields[9]),
        }
    return counters


def get_primary_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def collect_snapshot() -> dict[str, Any]:
    return {
        "timestamp": int(time.time()),
        "hostname": socket.gethostname(),
        "ip_address": get_primary_ip(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "metrics": {
            "cpu_temp_c": read_cpu_temp_c(),
            "loadavg": read_loadavg(),
            "memory": read_meminfo(),
            "disk_root": read_disk_usage("/"),
            "uptime_seconds": read_uptime_seconds(),
            "network": read_network_counters(),
        },
    }


class ProbeHandler(BaseHTTPRequestHandler):
    server_version = "PiProbe/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": "pi-probe"})
            return

        if parsed.path == "/metrics":
            if not self.authorized(parsed):
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            self.send_json(HTTPStatus.OK, collect_snapshot())
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def authorized(self, parsed) -> bool:
        expected = load_expected_token()
        if not expected:
            return True

        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        supplied = auth_header.removeprefix("Bearer ").strip()
        if not supplied:
            return False
        return hmac.compare_digest(supplied, expected)

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = os.getenv("PI_PROBE_HOST", "0.0.0.0")
    port = env_int("PI_PROBE_PORT", 9821)
    tls_cert = (os.getenv("PI_PROBE_TLS_CERT") or "").strip()
    tls_key = (os.getenv("PI_PROBE_TLS_KEY") or "").strip()
    load_expected_token()
    server = ThreadingHTTPServer((host, port), ProbeHandler)
    scheme = "http"

    if tls_cert or tls_key:
        if not tls_cert or not tls_key:
            raise RuntimeError("Both PI_PROBE_TLS_CERT and PI_PROBE_TLS_KEY must be set to enable TLS")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=tls_cert, keyfile=tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"pi-probe listening on {scheme}://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
