#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

from ui_v2.services.update_checker import (
    LATEST_RELEASE_API,
    RELEASES_PAGE_URL,
    _pick_deb_asset_url,
)


def _fetch_latest_release() -> dict:
    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "User-Agent": "LaptopHealthDownloader",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def _resolve_download(data: dict, preferred_arch: str) -> tuple[str, str]:
    assets = data.get("assets") or []
    if preferred_arch:
        arch_assets = [
            asset for asset in assets
            if preferred_arch.lower() in str(asset.get("name") or "").lower()
        ]
        url = _pick_deb_asset_url(arch_assets)
        if url:
            return url, os.path.basename(url)

    url = _pick_deb_asset_url(assets)
    if url:
        return url, os.path.basename(url)

    raise RuntimeError(
        f"No .deb asset found in the latest release. Check {RELEASES_PAGE_URL}"
    )


def _download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as fh:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the latest Laptop Health .deb from GitHub Releases."
    )
    parser.add_argument(
        "--arch",
        default="amd64",
        help="Preferred asset architecture substring to match. Default: amd64",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write the downloaded file into. Default: current directory",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        release = _fetch_latest_release()
        url, filename = _resolve_download(release, args.arch)
        destination = out_dir / filename
        print(f"Downloading {url}")
        _download(url, destination)
        print(f"Saved to {destination}")
        if destination.parent == Path.cwd():
            install_target = f"./{destination.name}"
        else:
            install_target = str(destination)
        print(f"Install with: pkexec apt install {install_target}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
