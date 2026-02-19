from __future__ import annotations
import os
import subprocess

APT_CHECK = "/usr/lib/update-notifier/apt-check"

def get_update_count() -> tuple[int, int]:
    """
    Returns (total_updates, security_updates) using apt-check if available.
    Falls back to (0,0) if unavailable.
    """
    if not os.path.exists(APT_CHECK):
        return 0, 0
    try:
        out = subprocess.check_output([APT_CHECK, "--human-readable"], text=True, stderr=subprocess.DEVNULL)
        total = 0
        security = 0
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if "updates can be applied immediately" in line:
                # "12 updates can be applied immediately."
                total = int(line.split()[0])
            if "security updates" in line:
                # "3 of these updates are security updates."
                security = int(line.split()[0])
        return total, security
    except Exception:
        return 0, 0

def reboot_required() -> bool:
    return os.path.exists("/var/run/reboot-required")
