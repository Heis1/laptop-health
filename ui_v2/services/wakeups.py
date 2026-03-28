from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time

import system

POWERTOP = shutil.which("powertop") or "/usr/sbin/powertop"
_last_ctxt: int | None = None
_last_intr: int | None = None
_last_sample_ts: float | None = None


def _trusted_path(cmd: str) -> str | None:
    path = system.which(cmd)
    if not path:
        return None
    real = os.path.realpath(path)
    trusted_prefixes = (
        "/usr/bin/",
        "/bin/",
        "/usr/sbin/",
        "/sbin/",
        "/usr/local/bin/",
        "/usr/local/sbin/",
    )
    if any(real.startswith(prefix) for prefix in trusted_prefixes):
        return real
    return None

def powertop_installed() -> bool:
    return _trusted_path("powertop") is not None or os.path.exists("/usr/sbin/powertop")

def sudo_cached() -> bool:
    sudo = _trusted_path("sudo")
    if not sudo:
        return False
    try:
        subprocess.check_output([sudo, "-n", "true"], stderr=subprocess.DEVNULL)
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

# Non-blocking delta sampler for dashboards (no sleep).
_LAST_WAKE_SAMPLE: tuple[float, int, int] | None = None  # (t, ctxt, intr)

def sample_wake_activity_now() -> dict[str, float]:
    """
    Non-blocking proxy sample using /proc/stat deltas.
    Returns ctxt_per_s and intr_per_s without sleeping.
    First call returns 0.0/0.0 (no baseline).
    """
    global _LAST_WAKE_SAMPLE

    ctxt, intr = _read_proc_stat_counts()
    t = time.time()

    if _LAST_WAKE_SAMPLE is None:
        _LAST_WAKE_SAMPLE = (t, ctxt, intr)
        return {"ctxt_per_s": 0.0, "intr_per_s": 0.0}

    t0, c0, i0 = _LAST_WAKE_SAMPLE
    dt = max(0.001, t - t0)
    _LAST_WAKE_SAMPLE = (t, ctxt, intr)

    return {
        "ctxt_per_s": max(0.0, (ctxt - c0) / dt),
        "intr_per_s": max(0.0, (intr - i0) / dt),
    }

def sample_wake_activity_fast(interval_s: float = 1.0) -> dict[str, float]:
    """
    Fast, reliable proxy for wake activity:
      - ctxt_per_s
      - intr_per_s
    (Wakeups/sec is not directly available without powertop/perf privileges.)
    """
    global _last_ctxt, _last_intr, _last_sample_ts

    c2, i2 = _read_proc_stat_counts()
    now = time.time()

    if _last_ctxt is None or _last_intr is None or _last_sample_ts is None:
        _last_ctxt = c2
        _last_intr = i2
        _last_sample_ts = now
        return {"ctxt_per_s": 0.0, "intr_per_s": 0.0}

    delta_t = max(0.000_001, now - _last_sample_ts)
    delta_ctxt = max(0, c2 - _last_ctxt)
    delta_intr = max(0, i2 - _last_intr)

    _last_ctxt = c2
    _last_intr = i2
    _last_sample_ts = now

    return {
        "ctxt_per_s": max(0.0, delta_ctxt / delta_t),
        "intr_per_s": max(0.0, delta_intr / delta_t),
    }


def classify_wakeup_proxy(ctxt_per_s: float, intr_per_s: float) -> str:
    if ctxt_per_s > 200_000 or intr_per_s > 200_000:
        return "red"
    if ctxt_per_s > 80_000 or intr_per_s > 80_000:
        return "orange"
    return "green"

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
        powertop = _trusted_path("powertop")
        if not powertop:
            return None

        # Some powertop versions accept just --csv=FILE, others accept --csv and write default.
        # We'll try robustly:
        tried_cmds = [
            [powertop, f"--csv={csv_path}"],
            [powertop, "--csv", f"--csv={csv_path}"],
            [powertop, "--csv", csv_path],
        ]

        for c in tried_cmds:
            try:
                system.run_privileged("sudo", c, timeout_s=timeout_s)
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
