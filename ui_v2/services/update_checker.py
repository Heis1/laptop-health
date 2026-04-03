from dataclasses import dataclass
import json
import re
import urllib.request
from urllib.parse import urlparse

GITHUB_REPO = "Heis1/laptop-health"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
EXPECTED_RELEASE_HOST = "github.com"
EXPECTED_RELEASE_PATH_PREFIX = f"/{GITHUB_REPO}/releases/"
EXPECTED_DOWNLOAD_PATH_PREFIX = f"/{GITHUB_REPO}/releases/download/"
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com")
MAX_UPDATE_RESPONSE_BYTES = 256 * 1024

@dataclass
class UpdateCheckResult:
    ok: bool
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    deb_download_url: str | None = None
    update_available: bool = False
    error: str | None = None


def _normalize(v: str):
    v = v.lower().strip()
    v = v.lstrip("v")
    nums = re.findall(r"\d+", v)
    return tuple(int(x) for x in nums[:3])


def _validated_release_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.netloc.lower() != EXPECTED_RELEASE_HOST:
        return None
    if not parsed.path.startswith(EXPECTED_RELEASE_PATH_PREFIX):
        return None
    return url


def _validated_download_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.netloc.lower() not in ALLOWED_DOWNLOAD_HOSTS:
        return None
    if parsed.netloc.lower() == "github.com" and not parsed.path.startswith(EXPECTED_DOWNLOAD_PATH_PREFIX):
        return None
    if ".deb" not in parsed.path:
        return None
    return url


def _pick_deb_asset_url(assets: list[dict]) -> str | None:
    candidates = []
    for asset in assets:
        url = _validated_download_url(asset.get("browser_download_url"))
        if not url:
            continue
        name = str(asset.get("name") or "").lower()
        score = 0
        if "amd64" in name:
            score += 2
        if name.endswith(".deb"):
            score += 1
        candidates.append((score, name, url))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def check_for_updates(current_version: str) -> UpdateCheckResult:
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_API,
            headers={
                "User-Agent": "LaptopHealth",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read(MAX_UPDATE_RESPONSE_BYTES + 1)
        if len(raw) > MAX_UPDATE_RESPONSE_BYTES:
            raise RuntimeError(f"Release response exceeded {MAX_UPDATE_RESPONSE_BYTES} bytes")
        data = json.loads(raw.decode())

        latest = data.get("tag_name")
        url = _validated_release_url(data.get("html_url")) or RELEASES_PAGE_URL
        deb_download_url = _pick_deb_asset_url(data.get("assets") or [])

        if not latest:
            raise RuntimeError("Invalid release response")

        update_available = _normalize(latest) > _normalize(current_version)

        return UpdateCheckResult(
            ok=True,
            current_version=current_version,
            latest_version=latest,
            release_url=url,
            deb_download_url=deb_download_url,
            update_available=update_available,
        )

    except Exception as e:
        return UpdateCheckResult(
            ok=False,
            current_version=current_version,
            error=str(e)
        )
