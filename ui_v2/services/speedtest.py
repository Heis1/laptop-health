from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass


@dataclass
class SpeedTestResult:
    ok: bool
    ping_ms: float | None
    down_mbps: float | None
    up_mbps: float | None
    server: str | None
    isp: str | None
    when: float
    error: str | None = None


def _run_capture(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, (p.stdout or "")


def _extract_json(text: str) -> dict:
    t = (text or "").strip()
    if not t:
        raise ValueError("No output from speedtest")
    if t.startswith("{") and t.endswith("}"):
        return json.loads(t)
    a = t.find("{")
    b = t.rfind("}")
    if a == -1 or b == -1 or b <= a:
        raise ValueError(f"Output was not JSON (first 200 chars): {t[:200]!r}")
    return json.loads(t[a : b + 1])


def _parse_ookla_json(data: dict, when: float) -> SpeedTestResult:
    ping_ms = None
    try:
        ping_ms = float((data.get("ping") or {}).get("latency"))
    except Exception:
        pass

    def bps_to_mbps_bandwidth(bw_bytes_per_s):
        try:
            return float(bw_bytes_per_s) * 8 / 1_000_000
        except Exception:
            return None

    down = bps_to_mbps_bandwidth((data.get("download") or {}).get("bandwidth"))
    up = bps_to_mbps_bandwidth((data.get("upload") or {}).get("bandwidth"))

    server = None
    try:
        srv = data.get("server") or {}
        name = (srv.get("name") or "").strip()
        loc = (srv.get("location") or "").strip()
        server = f"{name} ({loc})".strip()
        if server.strip(" ()") == "":
            server = None
    except Exception:
        pass

    isp = (data.get("isp") or None)

    return SpeedTestResult(True, ping_ms, down, up, server, isp, when)


def _parse_speedtest_cli_json(data: dict, when: float) -> SpeedTestResult:
    ping_ms = float(data.get("ping")) if data.get("ping") is not None else None
    down = (float(data.get("download")) / 1_000_000) if data.get("download") is not None else None
    up = (float(data.get("upload")) / 1_000_000) if data.get("upload") is not None else None

    srv = data.get("server") or {}
    sponsor = (srv.get("sponsor") or "").strip()
    name = (srv.get("name") or "").strip()
    server = " - ".join([x for x in (sponsor, name) if x]) or None

    client = data.get("client") or {}
    isp = client.get("isp") if isinstance(client, dict) else None

    return SpeedTestResult(True, ping_ms, down, up, server, isp, when)


def run_speedtest() -> SpeedTestResult:
    when = time.time()

    # Prefer speedtest-cli JSON, but it can be flaky (403). Retry once.
    if shutil.which("speedtest-cli"):
        for attempt in (1, 2):
            rc, out = _run_capture(["speedtest-cli", "--json"], timeout=120)
            try:
                data = _extract_json(out)
                return _parse_speedtest_cli_json(data, when)
            except Exception as e:
                msg = f"speedtest-cli --json failed (rc={rc}, attempt={attempt}). {e}"
                snippet = out.strip().splitlines()[:8]
                if snippet:
                    msg += " | output: " + " / ".join(snippet)[:300]
                last_err = msg
                # short pause then retry
                time.sleep(0.8)

        return SpeedTestResult(False, None, None, None, None, None, when, error=last_err)

    # If speedtest-cli not installed, nothing else to do.
    return SpeedTestResult(False, None, None, None, None, None, when, error="speedtest-cli not installed")