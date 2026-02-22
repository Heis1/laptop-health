from __future__ import annotations

import os
import shutil
import subprocess
from typing import Tuple


def reboot_required() -> bool:
    return os.path.exists("/var/run/reboot-required")


def _run_text(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = ((p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")).strip()
        return int(p.returncode), out
    except Exception:
        return 1, ""


def _apt_list_upgradable_lines() -> list[str] | None:
    rc, out = _run_text(["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2"])
    if rc != 0:
        return None
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _count_security_from_line(line: str) -> bool:
    return "-security" in line


def get_update_count() -> Tuple[int | None, int | None]:
    """
    Returns (total_updates, security_updates) based on:
      apt list --upgradable
    """
    lines = _apt_list_upgradable_lines()
    if lines is None:
        return None, None
    total = len(lines)
    security = sum(1 for ln in lines if _count_security_from_line(ln))
    return total, security


def list_upgradable() -> list[dict]:
    """
    Returns list of dicts:
      { name, origin, security, raw }
    """
    lines = _apt_list_upgradable_lines()
    if not lines:
        return []

    items: list[dict] = []
    for ln in lines:
        first = ln.split(maxsplit=1)[0]  # name/origin
        if "/" in first:
            name, origin = first.split("/", 1)
        else:
            name, origin = first, ""
        security = "-security" in ln or "-security" in origin
        items.append({"name": name, "origin": origin, "security": security, "raw": ln})
    return items


def list_kept_back() -> list[str]:
    """
    Parse kept-back packages from:
      apt-get -s upgrade
    """
    rc, out = _run_text(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=20)
    if rc != 0 or not out:
        return []

    kept: list[str] = []
    lines = out.splitlines()

    # Find section:
    # The following packages have been kept back:
    #   pkg1 pkg2 ...
    in_section = False
    for ln in lines:
        if ln.startswith("The following packages have been kept back:"):
            in_section = True
            continue
        if in_section:
            if ln.startswith("The following packages will be upgraded:") or not ln.strip():
                break
            # wrapped list lines
            kept.extend([x for x in ln.strip().split() if x])

    # de-dupe preserving order
    seen = set()
    out_kept = []
    for k in kept:
        if k not in seen:
            seen.add(k)
            out_kept.append(k)
    return out_kept


def list_holds() -> list[str]:
    """
    Packages explicitly held back:
      apt-mark showhold
    """
    rc, out = _run_text(["bash", "-lc", "apt-mark showhold 2>/dev/null"], timeout=10)
    if rc != 0 or not out:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


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
        out = ((p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")).strip()
        return int(p.returncode), out
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    except Exception as e:
        return 1, f"Command failed: {e}"
