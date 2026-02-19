from __future__ import annotations
import subprocess

def get_cpu_temp() -> float | None:
    """
    Best-effort CPU temp from `sensors`.
    Works on most Ryzen/Intel setups. Returns None if unavailable.
    """
    try:
        out = subprocess.check_output(["sensors"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            # common labels
            if "Tctl:" in line or "Package id 0:" in line or "CPU Temp:" in line:
                parts = line.replace("(", " ").replace(")", " ").split()
                for p in parts:
                    if p.startswith("+") and "°C" in p:
                        try:
                            return float(p.replace("+", "").replace("°C", ""))
                        except ValueError:
                            pass
    except Exception:
        return None
    return None
