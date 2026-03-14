from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Tuple


UPDATE_ACCENT_RGBA = {
    "green": "rgba(120, 255, 190, 0.95)",
    "orange": "rgba(255, 190, 120, 0.95)",
    "red": "rgba(255, 130, 130, 0.95)",
    "blue": "rgba(150, 190, 255, 0.95)",
    "purple": "rgba(200, 170, 255, 0.95)",
}


@dataclass
class UpdateSummary:
    total: int | None
    security: int | None
    reboot_required: bool
    kept_back: int
    held: int
    badge: str
    accent: str


def classify_update_status(total: int | None, security: int | None, reboot: bool, kept: int = 0, held: int = 0) -> tuple[str, str]:
    if total is None:
        return "Unknown", "red"

    sec = 0 if security is None else int(security)
    tot = int(total)

    # Priority: Held > Security/Reboot > Kept > Updates > Clean
    if held > 0:
        return "Held", "red"
    if sec > 0 or reboot:
        return "Attention", "red"
    if kept > 0:
        return "Kept back", "orange"
    if tot > 0:
        return "Updates", "orange"
    return "OK", "green"


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
    rc, out = _run(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=25)
    if rc != 0 or not out:
        return []
    return _parse_upgrade_sim(out)


def get_update_count() -> Tuple[int | None, int | None]:
    items = list_upgradable()
    if not items:
        rc, _ = _run(["bash", "-lc", "apt-get -s upgrade 2>/dev/null"], timeout=10)
        if rc != 0:
            return None, None
        return 0, 0
    total = len(items)
    security = sum(1 for it in items if bool(it.get("security")))
    return total, security


def list_kept_back() -> list[str]:
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


def get_update_summary() -> UpdateSummary:
    total, security = get_update_count()
    reboot = bool(reboot_required())
    kept = len(list_kept_back())
    held = len(list_holds())
    badge, accent = classify_update_status(total, security, reboot, kept, held)
    return UpdateSummary(
        total=total,
        security=security,
        reboot_required=reboot,
        kept_back=kept,
        held=held,
        badge=badge,
        accent=accent,
    )


def get_apt_action_argv(action: str) -> list[str]:
    """
    Build argv for apt actions in a way that is safe for live streaming output.
    Uses:
      - Dpkg::Use-Pty=0        -> disables pseudo-tty so output streams cleanly
      - Dpkg::Progress-Fancy=1 -> keeps dpkg progress/status visible
    """
    action = (action or "").strip().lower()

    mapping = {
        "update": [
            "env", "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "-o", "Dpkg::Use-Pty=0",
            "update",
        ],
        "upgrade": [
            "env", "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "-o", "Dpkg::Use-Pty=0",
            "-o", "Dpkg::Progress-Fancy=1",
            "-y", "upgrade",
        ],
        "dist-upgrade": [
            "env", "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "-o", "Dpkg::Use-Pty=0",
            "-o", "Dpkg::Progress-Fancy=1",
            "-y", "dist-upgrade",
        ],
        "full-upgrade": [
            "env", "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "-o", "Dpkg::Use-Pty=0",
            "-o", "Dpkg::Progress-Fancy=1",
            "-y", "dist-upgrade",
        ],
        "autoremove": [
            "env", "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            "-o", "Dpkg::Use-Pty=0",
            "-o", "Dpkg::Progress-Fancy=1",
            "-y", "autoremove",
        ],
    }

    if action not in mapping:
        raise ValueError(f"Unknown action: {action}")

    inner = mapping[action]
    is_root = (getattr(os, "geteuid", lambda: 1)() == 0)

    if is_root:
        return inner

    pkexec = shutil.which("pkexec")
    if not pkexec:
        raise FileNotFoundError("pkexec not found. Install policykit (pkexec).")

    return [pkexec] + inner


def run_apt_action(action: str) -> tuple[int, str]:
    """
    Compatibility helper for existing callers.
    Executes the full command and returns combined output only after completion.
    Live streaming callers should use get_apt_action_argv(action) with Popen.
    """
    try:
        argv = get_apt_action_argv(action)
    except ValueError as e:
        return 2, str(e)
    except FileNotFoundError as e:
        return 127, str(e)
    except Exception as e:
        return 1, f"Command failed: {e}"

    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
        out = ((p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")).strip()
        return int(p.returncode), out
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    except Exception as e:
        return 1, f"Command failed: {e}"
