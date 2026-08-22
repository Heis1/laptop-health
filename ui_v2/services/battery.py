from __future__ import annotations

import re
import shutil
import subprocess


def _number(value: str) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value or "")
    return float(match.group(0)) if match else None


def read_battery_health() -> dict[str, object]:
    if not shutil.which("upower"):
        return {"available": False, "error": "UPower is not installed."}
    try:
        devices = subprocess.run(["upower", "-e"], capture_output=True, text=True, timeout=3, check=False)
        battery = next((line.strip() for line in devices.stdout.splitlines() if "battery_BAT" in line), "")
        if not battery:
            return {"available": False, "error": "No battery was reported by UPower."}
        result = subprocess.run(["upower", "-i", battery], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": str(exc)}
    if result.returncode != 0:
        return {"available": False, "error": (result.stderr or "UPower query failed").strip()}
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        values[key.strip()] = value.strip()
    full = _number(values.get("energy-full", ""))
    design = _number(values.get("energy-full-design", ""))
    health = (full / design * 100.0) if full and design else _number(values.get("capacity", ""))
    return {
        "available": True,
        "health": health,
        "percentage": _number(values.get("percentage", "")),
        "cycles": _number(values.get("charge-cycles", "")),
        "state": values.get("state", "unknown"),
        "energy_full": full,
        "energy_design": design,
        "rate": _number(values.get("energy-rate", "")),
        "technology": values.get("technology", "unknown"),
        "model": values.get("model", "Battery"),
    }
