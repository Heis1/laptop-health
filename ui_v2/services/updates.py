from __future__ import annotations

import os
import shutil
import subprocess
from typing import Tuple


def reboot_required() -> bool:
    return os.path.exists("/var/run/reboot-required")


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = ((p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")).strip()
        return int(p.returncode), out
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    except Exception as e:
        return 1, str(e)


def _parse_upgrade_sim(out: str) -> list[dict]:
    """
    Parse `apt-get -s upgrade` output into items:
      - name
      - origin (best-effort)
      - security (best-effort: origin mentions security)
      - raw
    """
    items: list[dict] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line.startswith("Inst "):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[1].strip()

        origin = ""
        if "(" in line and ")" in line:
            try:
                inside = line.split("(", 1)[1].rsplit(")", 1)[0].strip()
                # inside commonly: "<newver> <repo ...> [arch]"
                # keep everything after version token as "origin"
                toks = inside.split(maxsplit=1)
                if len(toks) == 2:
                    origin = toks[1].strip()
            except Exception:
                origin = ""

        low = (origin or "").lower()
        security = ("security" in low) or ("-security" in low)

        items.append({"name": name, "origin": origin, "security": security, "raw": line})
    return items


def list_upgradable() -> list[dict]:
    # Use apt-get simulation (stable for scripting, no actual changes)
    rc, out = _run(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=25)
    if rc != 0 or not out:
        return []
    return _parse_upgrade_sim(out)


def get_update_count() -> Tuple[int | None, int | None]:
    items = list_upgradable()
    if not items:
        # Could be genuinely 0 updates OR a failure.
        # Disambiguate by checking the command return code quickly.
        rc, _ = _run(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=10)
        if rc != 0:
            return None, None
        return 0, 0
    total = len(items)
    security = sum(1 for it in items if bool(it.get("security")))
    return total, security


def list_kept_back() -> list[str]:
    # Parse kept-back list from apt-get simulation output
    rc, out = _run(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=25)
    if rc != 0 or not out:
        return []
    kept: list[str] = []
    in_section = False
    for line in out.splitlines():
        if line.startswith("The following packages have been kept back:"):
            in_section = True
            continue
        if in_section:
            if not line.strip() or line.startswith("The following"):
                break
            kept.extend(line.strip().split())
    # de-dupe preserve order
    seen = set()
    out_kept = []
    for k in kept:
        if k not in seen:
            seen.add(k)
            out_kept.append(k)
    return out_kept


def list_holds() -> list[str]:
    rc, out = _run(["bash", "-lc", "apt-mark showhold 2>/dev/null"])
    if rc != 0 or not out:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def run_apt_action(action: str) -> tuple[int, str]:
    """
    Runs apt actions using apt-get (stable for scripting).
    Uses pkexec when not root.

    Supported actions:
      update        -> apt-get update
      upgrade       -> apt-get -y upgrade
      dist-upgrade  -> apt-get -y dist-upgrade
      full-upgrade  -> alias of dist-upgrade
      autoremove    -> apt-get -y autoremove
    """
    action = (action or "").strip().lower()

    mapping = {
        "update": "DEBIAN_FRONTEND=noninteractive apt-get update",
        "upgrade": "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade",
        "dist-upgrade": "DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade",
        "full-upgrade": "DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade",
        "autoremove": "DEBIAN_FRONTEND=noninteractive apt-get -y autoremove",
    }

    if action not in mapping:
        return 2, f"Unknown action: {action}"

    cmd = mapping[action]
    is_root = (getattr(os, "geteuid", lambda: 1)() == 0)

    if not is_root:
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return 127, "pkexec not found. Install policykit (pkexec)."
        argv = [pkexec, "bash", "-lc", cmd]
    else:
        argv = ["bash", "-lc", cmd]

    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
        out = ((p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")).strip()
        return int(p.returncode), out
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    except Exception as e:
        return 1, f"Command failed: {e}"
