from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple


def _read_proc_stat_counts() -> tuple[int, int]:
    """
    Returns (ctxt_total, intr_total) from /proc/stat.
    ctxt = total context switches since boot
    intr = total interrupts since boot
    """
    ctxt = 0
    intr = 0
    with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("ctxt "):
                # ctxt 123456789
                parts = line.split()
                if len(parts) >= 2:
                    ctxt = int(parts[1])
            elif line.startswith("intr "):
                # intr 123456789 ...
                parts = line.split()
                if len(parts) >= 2:
                    intr = int(parts[1])
    return ctxt, intr


def sample_system_rates(interval_s: float = 1.0) -> Dict[str, float]:
    """
    Samples /proc/stat twice and returns rates per second:
      - ctxt_per_s
      - intr_per_s
    """
    interval_s = max(0.25, float(interval_s))
    c1, i1 = _read_proc_stat_counts()
    time.sleep(interval_s)
    c2, i2 = _read_proc_stat_counts()
    return {
        "ctxt_per_s": max(0.0, (c2 - c1) / interval_s),
        "intr_per_s": max(0.0, (i2 - i1) / interval_s),
    }


def _read_pid_ctxt(pid: int) -> tuple[str, int]:
    """
    Returns (comm, total_ctxt_switches) for a PID from /proc/<pid>/status.
    total = voluntary + nonvoluntary
    """
    comm = str(pid)
    vol = 0
    invol = 0
    path = f"/proc/{pid}/status"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("Name:"):
                comm = line.split(":", 1)[1].strip()
            elif line.startswith("voluntary_ctxt_switches:"):
                vol = int(line.split(":", 1)[1].strip())
            elif line.startswith("nonvoluntary_ctxt_switches:"):
                invol = int(line.split(":", 1)[1].strip())
    return comm, (vol + invol)


def top_ctxt_switchers(interval_s: float = 1.0, limit: int = 5) -> List[Tuple[int, str, int]]:
    """
    Scans /proc for per-process context switches and returns the top offenders
    by delta over interval_s:
      [(pid, comm, delta), ...]
    Best-effort: processes may exit / deny access; those are skipped.
    """
    interval_s = max(0.25, float(interval_s))
    limit = max(1, int(limit))

    pids: list[int] = []
    for name in os.listdir("/proc"):
        if name.isdigit():
            pids.append(int(name))

    # Snapshot 1
    snap1: dict[int, tuple[str, int]] = {}
    for pid in pids:
        try:
            snap1[pid] = _read_pid_ctxt(pid)
        except Exception:
            continue

    time.sleep(interval_s)

    # Snapshot 2 + deltas
    deltas: list[tuple[int, str, int]] = []
    for pid, (comm1, v1) in snap1.items():
        try:
            comm2, v2 = _read_pid_ctxt(pid)
            comm = comm2 or comm1
            d = v2 - v1
            if d > 0:
                deltas.append((pid, comm, d))
        except Exception:
            continue

    deltas.sort(key=lambda x: x[2], reverse=True)
    return deltas[:limit]
