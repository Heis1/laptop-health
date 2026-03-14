
from dataclasses import dataclass
import urllib.request
import json
import re

GITHUB_REPO = "Heis1/laptop-health"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

@dataclass
class UpdateCheckResult:
    ok: bool
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    update_available: bool = False
    error: str | None = None


def _normalize(v: str):
    v = v.lower().strip()
    v = v.lstrip("v")
    nums = re.findall(r"\d+", v)
    return tuple(int(x) for x in nums[:3])


def check_for_updates(current_version: str) -> UpdateCheckResult:
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_API,
            headers={"User-Agent": "LaptopHealth"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())

        latest = data.get("tag_name")
        url = data.get("html_url")

        if not latest:
            raise RuntimeError("Invalid release response")

        update_available = _normalize(latest) > _normalize(current_version)

        return UpdateCheckResult(
            ok=True,
            current_version=current_version,
            latest_version=latest,
            release_url=url,
            update_available=update_available,
        )

    except Exception as e:
        return UpdateCheckResult(
            ok=False,
            current_version=current_version,
            error=str(e)
        )
