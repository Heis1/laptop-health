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


def list_upgradable() -> list[dict]:
    """
    Returns a list of dicts:
      {
        name: str,
        origin: str,          # e.g. noble-updates,noble-security
        security: bool,       # True if "-security" in origin
        raw: str              # original apt line
      }

    Uses: apt list --upgradable
    """
    import subprocess

    try:
        out = subprocess.check_output(
            ["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2"],
            text=True,
            timeout=10,
        )
    except Exception:
        return []

    items: list[dict] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # Example:
        # libvpx9/noble-updates,noble-security 1.14.0-1ubuntu2.3 amd64 [upgradable from: 1.14.0-1ubuntu2.2]
        # Split "name/origin" token:
        first = ln.split(maxsplit=1)[0]  # name/origin
        if "/" in first:
            name, origin = first.split("/", 1)
        else:
            name, origin = first, ""
        security = "-security" in ln or "-security" in origin
        items.append({"name": name, "origin": origin, "security": security, "raw": ln})
    return items


def run_apt_action(action: str) -> tuple[int, str]:
    """
    Runs an apt action with GUI elevation via pkexec when not root.
    action:
      - "update"        -> apt-get update
      - "upgrade"       -> apt-get -y upgrade
      - "dist-upgrade"  -> apt-get -y dist-upgrade
      - "autoremove"    -> apt-get -y autoremove
    Returns (rc, combined_output)
    """
    import os
    import shutil
    import subprocess

    action = action.strip().lower()
    mapping = {
        "update": "DEBIAN_FRONTEND=noninteractive apt-get update",
        "upgrade": "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade",
        "dist-upgrade": "DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade",
        "autoremove": "DEBIAN_FRONTEND=noninteractive apt-get -y autoremove",
    }
    if action not in mapping:
        return 2, f"Unknown action: {action}"

    cmd = mapping[action]
    is_root = (getattr(os, "geteuid", lambda: 1)() == 0)

    if not is_root:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return 127, "pkexec not found. Install policykit (pkexec) or run the app as root."
        argv = [pkexec, "bash", "-lc", cmd]
    else:
        argv = ["bash", "-lc", cmd]

    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60 * 60)
        out = (p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")
        return int(p.returncode), out.strip()
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    except Exception as e:
        return 1, f"Command failed: {e}"
