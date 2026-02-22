from __future__ import annotations

import os
import subprocess
from typing import Tuple


def reboot_required() -> bool:
    return os.path.exists("/var/run/reboot-required")


def _run_text(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        out = (p.stdout or "").strip()
        return p.returncode, out
    except Exception:
        return 1, ""


def _apt_list_upgradable() -> list[str] | None:
    # Using apt list because it works reliably on your system
    rc, out = _run_text(["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2"])
    if rc != 0:
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines


def _count_security_from_line(line: str) -> bool:
    # apt list line includes origin tags like: "... noble-updates,noble-security ..."
    # We treat anything containing "-security" as a security update.
    return "-security" in line


def get_update_count() -> Tuple[int | None, int | None]:
    """
    Returns (total_updates, security_updates).

    We use `apt list --upgradable` as primary source (works on Mint/Ubuntu),
    and count security updates by presence of '-security' in the origin tags.
    """
    lines = _apt_list_upgradable()
    if lines is None:
        return None, None

    total = len(lines)
    security = sum(1 for ln in lines if _count_security_from_line(ln))
    return total, security
