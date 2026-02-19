from __future__ import annotations
import subprocess

def get_root_usage() -> tuple[int, str] | None:
    """
    Returns (percent_used, avail_human) for mount '/' using df.
    Example: (80, '7.1G')
    """
    try:
        out = subprocess.check_output(
            ["df", "-h", "--output=pcent,avail,target"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("Use%"):
                continue
            # Expect: "80%  7.1G  /"
            parts = line.split()
            if len(parts) >= 3 and parts[-1] == "/":
                percent = int(parts[0].replace("%", ""))
                avail = parts[1]
                return percent, avail
    except Exception:
        return None
    return None
