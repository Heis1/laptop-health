"""
Sensors module (temps/fans/battery).
Move hardware/sensor reading code here in small commits.
"""
from __future__ import annotations

import re
import system

# -------------------- sensors parsing --------------------
def parse_sensors_text(raw: str) -> dict:
    cpu = None
    gpu = None
    ssd = None

    lines = raw.splitlines()
    current_chip = ""
    for line in lines:
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" not in line:
            current_chip = line.strip().lower()
            continue

        m = re.search(r"([A-Za-z0-9 _/\-\.]+):\s*([+\-]?\d+(?:\.\d+)?)\s*(?:°C|C)\b", line)

        if not m:
            continue

        name = m.group(1).strip().lower()
        val = float(m.group(2))
        chip = current_chip

        # CPU: prefer tctl/tdie/package
        if not any(k in chip for k in ["amdgpu", "radeon", "nvidia", "nvme"]):
            if any(k in name for k in ["tctl", "tdie", "package", "cpu", "core", "temp1"]):
                cpu = val if cpu is None else max(cpu, val)

        # AMD GPU
        if any(k in chip for k in ["amdgpu", "radeon"]) or "gpu" in name:
            if any(k in name for k in ["edge", "junction", "gpu", "temp1"]):
                gpu = val if gpu is None else max(gpu, val)

        # NVMe via sensors: prefer Composite if present
        if "nvme" in chip or any(k in name for k in ["composite", "nvme"]):
            if "composite" in name:
                ssd = val
            else:
                if ssd is None:
                    ssd = val
                else:
                    # only upgrade if we didn't see Composite
                    ssd = max(ssd, val)

    return {"cpu": cpu, "gpu": gpu, "ssd": ssd, "raw": raw}


def read_sensors() -> tuple[dict, str]:
    if not system.which("sensors"):
        return {"cpu": None, "gpu": None, "ssd": None, "raw": ""}, "missing: sensors (lm-sensors)"
    rc, out, err = system.run_cmd(["sensors"], timeout_s=2)
    if rc != 0:
        return {"cpu": None, "gpu": None, "ssd": None, "raw": out + ("\n" + err if err else "")}, f"sensors failed (rc={rc}): {err or out}"
    return parse_sensors_text(out), ""


def read_nvidia_gpu_temp() -> tuple[float | None, str]:
    if not system.which("nvidia-smi"):
        return None, "missing: nvidia-smi"
    rc, out, err = system.run_cmd(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], timeout_s=2)
    if rc != 0:
        return None, f"nvidia-smi failed (rc={rc}): {err or out}"
    try:
        vals = [float(x.strip()) for x in out.splitlines() if x.strip()]
        return (max(vals) if vals else None), ""
    except Exception as e:
        return None, f"nvidia-smi parse error: {e}"


def find_nvme_devices() -> list[str]:
    devs = []
    if not system.which("nvme"):
        return devs
    try:
        for name in os.listdir("/dev"):
            if re.fullmatch(r"nvme\d+", name):
                devs.append("/dev/" + name)
    except Exception:
        pass
    return sorted(devs)


def read_nvme_temp() -> tuple[float | None, str]:
    if not system.which("nvme"):
        return None, "missing: nvme (nvme-cli)"
    devs = find_nvme_devices()
    if not devs:
        return None, "no /dev/nvmeX devices found"

    temps = []
    last_err = ""
    for dev in devs:
        rc, out, err = system.run_cmd(["nvme", "smart-log", dev], timeout_s=2)
        if rc != 0:
            last_err = f"{dev}: rc={rc}: {err or out}"
            continue
        m = re.search(r"temperature\s*:\s*(\d+)\s*C", out, re.IGNORECASE)
        if m:
            temps.append(float(m.group(1)))

    if temps:
        return max(temps), ""
    return None, (last_err or "nvme smart-log did not expose temperature")
