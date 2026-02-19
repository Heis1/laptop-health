from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time

POWERTOP = shutil.which("powertop") or "/usr/sbin/powertop"

def powertop_installed() -> bool:
    return shutil.which("powertop") is not None or os.path.exists("/usr/sbin/powertop")

def sudo_cached() -> bool:
    try:
        subprocess.check_output(["sudo", "-n", "true"], stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def _read_proc_stat_counts() -> tuple[int, int]:
    ctxt = 0
    intr = 0
    with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("ctxt "):
                parts = line.split()
                if len(parts) >= 2:
                    ctxt = int(parts[1])
            elif line.startswith("intr "):
                parts = line.split()
                if len(parts) >= 2:
                    intr = int(parts[1])
    return ctxt, intr

def sample_wake_activity_fast(interval_s: float = 1.0) -> dict[str, float]:
    """
    Fast, reliable proxy for wake activity:
      - ctxt_per_s
      - intr_per_s
    (Wakeups/sec is not directly available without powertop/perf privileges.)
    """
    interval_s = max(0.5, float(interval_s))
    c1, i1 = _read_proc_stat_counts()
    time.sleep(interval_s)
    c2, i2 = _read_proc_stat_counts()
    return {
        "ctxt_per_s": max(0.0, (c2 - c1) / interval_s),
        "intr_per_s": max(0.0, (i2 - i1) / interval_s),
    }

def wakeups_hint_fast() -> str:
    return "Proxy: ctxt/s + intr/s (fast, no admin)"

def wakeups_hint_deep() -> str:
    if not powertop_installed():
        return "powertop not installed"
    if not sudo_cached():
        return "Run `sudo -v` first"
    return "Deep sample uses powertop (~20s)"

def sample_wakeups_powertop_slow(timeout_s: int = 25) -> float | None:
    """
    Slow/accurate-ish: attempt powertop CSV and parse wakeups/sec.
    Your build appears to run ~20s measurements even with --time 1, so we treat it as slow.
    Uses sudo -n (no prompts). Returns None on failure.
    """
    if not powertop_installed() or not sudo_cached():
        return None

    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "powertop.csv")
        cmd = ["sudo", "-n", POWERTOP, "--csv", f"--csv={csv_path}"]

        # Some powertop versions accept just --csv=FILE, others accept --csv and write default.
        # We'll try robustly:
        tried_cmds = [
            ["sudo", "-n", POWERTOP, f"--csv={csv_path}"],
            ["sudo", "-n", POWERTOP, "--csv", f"--csv={csv_path}"],
            ["sudo", "-n", POWERTOP, "--csv", csv_path],
        ]

        for c in tried_cmds:
            try:
                subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_s)
            except Exception:
                pass

            if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                break

        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            return None

        data = open(csv_path, "r", encoding="utf-8", errors="ignore").read()

    patterns = [
        r'Wakeups-from-idle per second[^0-9]*"?([0-9]+(?:\.[0-9]+)?)"?',
        r'Wakeups per second[^0-9]*"?([0-9]+(?:\.[0-9]+)?)"?',
        r'([0-9]+(?:\.[0-9]+)?)\s*wakeups?/s',
    ]
    for pat in patterns:
        m = re.search(pat, data, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    return None
