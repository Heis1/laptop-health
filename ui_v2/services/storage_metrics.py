from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

STORAGE_PREFS_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "storage_prefs.json")

def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)


def _ensure_storage_config_dir() -> None:
    cfg_dir = os.path.dirname(STORAGE_PREFS_PATH)
    os.makedirs(cfg_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(cfg_dir, 0o700)
    except OSError:
        pass


def load_excluded_storage_mounts() -> set[str]:
    try:
        with open(STORAGE_PREFS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return set()
    items = data.get("excluded_mounts", []) if isinstance(data, dict) else []
    return {str(item) for item in items if isinstance(item, str)}


def save_excluded_storage_mounts(mounts: set[str]) -> None:
    _ensure_storage_config_dir()
    payload = {"excluded_mounts": sorted(mounts)}
    with open(STORAGE_PREFS_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def toggle_excluded_storage_mount(mount: str) -> bool:
    excluded = load_excluded_storage_mounts()
    if mount in excluded:
        excluded.remove(mount)
        save_excluded_storage_mounts(excluded)
        return False
    excluded.add(mount)
    save_excluded_storage_mounts(excluded)
    return True

def find_mountpoint_for_path(target_path: str) -> str:
    target = Path(target_path).resolve()
    mounts: list[tuple[Path, str]] = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    try:
                        mounts.append((Path(mp).resolve(), mp))
                    except Exception:
                        continue
    except Exception:
        return "/"

    best = "/"
    best_len = 1
    for resolved_mp, mp_str in mounts:
        try:
            if str(target) == str(resolved_mp) or str(target).startswith(str(resolved_mp) + "/"):
                l = len(str(resolved_mp))
                if l > best_len:
                    best_len = l
                    best = mp_str
        except Exception:
            continue
    return best

def home_mountpoint() -> str:
    return find_mountpoint_for_path(str(Path.home()))

def device_for_mount(mount: str) -> Optional[str]:
    try:
        out = _run(["findmnt", "-no", "SOURCE", "--target", mount]).strip()
        if out.startswith("/dev/"):
            return out
    except Exception:
        pass
    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if f" {mount} " in line:
                    parts = line.split(" - ", 1)
                    if len(parts) == 2:
                        tail = parts[1].split()
                        if len(tail) >= 2 and tail[1].startswith("/dev/"):
                            return tail[1]
    except Exception:
        pass
    return None

def devname_from_devpath(devpath: str) -> Optional[str]:
    return os.path.basename(devpath) if devpath else None


def _mapper_name_to_block_dev(mapper_name: str) -> Optional[str]:
    try:
        for entry in Path("/sys/class/block").glob("dm-*"):
            try:
                name_file = entry / "dm" / "name"
                if name_file.exists() and name_file.read_text().strip() == mapper_name:
                    return entry.name
            except Exception:
                continue
    except Exception:
        pass
    return None


def _block_slave_devname(devname: str) -> Optional[str]:
    try:
        slaves = list((Path("/sys/class/block") / devname / "slaves").iterdir())
    except Exception:
        return None
    if not slaves:
        return None
    return slaves[0].name


def resolved_devname_from_devpath(devpath: str, blk: dict[str, dict] | None = None) -> Optional[str]:
    if not devpath:
        return None
    raw = os.path.basename(devpath)
    if devpath.startswith("/dev/mapper/"):
        mapped = _mapper_name_to_block_dev(raw)
        if mapped:
            raw = mapped
    if blk is None or raw in blk:
        return raw
    try:
        resolved = os.path.realpath(devpath)
    except Exception:
        resolved = devpath
    name = os.path.basename(resolved)
    if blk is None or name in blk:
        return name
    return raw

def parent_devname(devname: str) -> str:
    m = re.match(r"^(nvme\d+n\d+)", devname)
    if m:
        return m.group(1)
    m = re.match(r"^(mmcblk\d+)", devname)
    if m:
        return m.group(1)
    m = re.match(r"^([a-z]+)\d+$", devname)
    if m:
        return m.group(1)
    return devname


def _io_device_candidates(devname: str, node: dict | None = None) -> list[str]:
    candidates: list[str] = []

    def add(name: str | None) -> None:
        if not name:
            return
        if name not in candidates:
            candidates.append(name)

    add(node.get("pkname") if isinstance(node, dict) else None)
    add(parent_devname(devname))
    add(devname)

    slave = _block_slave_devname(devname)
    add(slave)
    add(parent_devname(slave) if slave else None)
    return candidates

def read_diskstats() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    try:
        with open("/proc/diskstats", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 14:
                    continue
                name = parts[2]
                try:
                    sectors_read = int(parts[5])
                    sectors_written = int(parts[9])
                    out[name] = (sectors_read, sectors_written)
                except Exception:
                    continue
    except Exception:
        pass
    return out

def sector_size_bytes(devname: str) -> int:
    """Best-effort sector size. Prefer logical_block_size, then hw_sector_size. Default 512."""
    base = Path("/sys/class/block") / devname / "queue"
    for fname in ("logical_block_size", "hw_sector_size"):
        try:
            p = base / fname
            if p.exists():
                v = int(p.read_text().strip())
                if v in (512, 1024, 2048, 4096):
                    return v
        except Exception:
            pass
    return 512

def lsblk_info() -> dict[str, dict]:
    try:
        out = _run(["lsblk", "-J", "-o", "NAME,MODEL,SIZE,TYPE,ROTA,FSTYPE,MOUNTPOINT,PKNAME"])
        data = json.loads(out)
    except Exception:
        return {}

    info: dict[str, dict] = {}

    def walk(node: dict):
        name = node.get("name")
        if name:
            info[name] = node
        for ch in node.get("children") or []:
            walk(ch)

    for n in data.get("blockdevices") or []:
        walk(n)

    return info

def nvme_temp_c_for_dev(devname: str) -> Optional[float]:
    base = parent_devname(devname)
    try:
        hwmon_dir = Path("/sys/class/block") / base / "device" / "hwmon"
        if hwmon_dir.exists():
            for child in hwmon_dir.glob("hwmon*"):
                temp = child / "temp1_input"
                if temp.exists():
                    v = int(temp.read_text().strip())
                    return v / 1000.0
    except Exception:
        pass
    return None

def _usage(mount: str) -> tuple[int | None, float | None]:
    try:
        du = shutil.disk_usage(mount)
        used_pct = int(round((du.used / du.total) * 100))
        free_gb = du.free / (1024**3)
        return used_pct, free_gb
    except Exception:
        return None, None

def _du_top_dirs(path: str, depth: int = 1, topn: int = 8) -> list[tuple[str, str]]:
    try:
        out = _run(["bash", "-lc", f"du -x -h -d {depth} {path} 2>/dev/null | sort -hr | head -n {topn}"])
        rows = []
        for line in out.strip().splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                size, p = parts
                rows.append((p, size))
        return rows
    except Exception:
        return []

def _journal_usage() -> str | None:
    try:
        out = _run(["journalctl", "--disk-usage"])
        return out.strip()
    except Exception:
        return None

def _dir_size(path: str) -> str | None:
    try:
        out = _run(["bash", "-lc", f"du -sh {path} 2>/dev/null | awk '{{print $1}}'"])
        return out.strip() or None
    except Exception:
        return None

@dataclass
class MountMetrics:
    label: str
    mount: str
    devpath: str | None
    devname: str | None
    io_devname: str | None
    used_pct: int | None
    free_gb: float | None
    read_mbps: float | None
    write_mbps: float | None
    active: bool | None
    total_read_gb: float | None
    total_written_gb: float | None
    fstype: str | None
    size: str | None
    model: str | None
    rota: int | None
    temp_c: float | None

@dataclass
class StorageInsights:
    top_label: str
    home_top: list[tuple[str, str]]
    var_log: str | None
    apt_cache: str | None
    journal: str | None

@dataclass
class StorageSnapshot:
    root: MountMetrics
    home: MountMetrics
    mounts: list[MountMetrics]
    insights: StorageInsights


def _mount_label(mount: str, home_mount: str) -> str:
    if mount == "/":
        return "Root"
    if mount == home_mount:
        return "Home"
    if mount == "/mnt":
        return "mnt"
    if mount.startswith("/mnt/"):
        return Path(mount).name.strip() or "mnt"
    if mount == "/media":
        return "media"
    if mount.startswith("/media/"):
        return Path(mount).name.strip() or "media"
    if mount.startswith("/run/media/"):
        return Path(mount).name.strip() or "media"
    name = Path(mount).name.strip()
    return name or mount


def _additional_storage_mounts(home_mount: str) -> list[str]:
    mounts: list[str] = []
    seen: set[str] = {"/", home_mount}
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                mp = parts[1]
                if mp in seen:
                    continue
                if not (
                    mp == "/mnt"
                    or mp.startswith("/mnt/")
                    or mp == "/media"
                    or mp.startswith("/media/")
                    or mp.startswith("/run/media/")
                ):
                    continue
                devpath = device_for_mount(mp)
                if not devpath or not devpath.startswith("/dev/"):
                    continue
                mounts.append(mp)
                seen.add(mp)
    except Exception:
        return []
    return sorted(mounts)

def gather_storage(interval_s: float = 1.0) -> StorageSnapshot:
    home_mount = home_mountpoint()
    blk = lsblk_info()

    s1 = read_diskstats()
    time.sleep(max(0.5, float(interval_s)))
    s2 = read_diskstats()

    def build(label: str, mount: str) -> MountMetrics:
        devpath = device_for_mount(mount)
        devname = resolved_devname_from_devpath(devpath, blk) if devpath else None
        used_pct, free_gb = _usage(mount)

        read_mbps = write_mbps = None
        active = None
        total_read_gb = total_written_gb = None
        fstype = size = model = None
        rota = None
        temp_c = None
        io_dev = None

        if devname:
            node = blk.get(devname) or {}
            fstype = node.get("fstype")
            size = node.get("size")
            model = node.get("model")
            try:
                rota = int(node.get("rota")) if node.get("rota") is not None else None
            except Exception:
                rota = None

            io_candidates = _io_device_candidates(devname, node)
            io_dev = io_candidates[0] if io_candidates else None

            # totals (since boot) from latest sample s2
            for candidate in io_candidates:
                if candidate in s2:
                    io_dev = candidate
                    sec = sector_size_bytes(candidate)
                    r, w = s2[candidate]
                    total_read_gb = (r * sec) / (1024**3)
                    total_written_gb = (w * sec) / (1024**3)
                    break

            # speed over interval
            for candidate in io_candidates:
                if candidate in s1 and candidate in s2:
                    r1, w1 = s1[candidate]
                    r2, w2 = s2[candidate]
                    sec = sector_size_bytes(candidate)
                    dt = max(0.5, float(interval_s))
                    active = (r2 != r1) or (w2 != w1)
                    candidate_read = ((max(0, r2 - r1) * sec) / dt) / (1024**2)
                    candidate_write = ((max(0, w2 - w1) * sec) / dt) / (1024**2)
                    io_dev = candidate
                    read_mbps = candidate_read
                    write_mbps = candidate_write
                    if candidate_read > 0.0 or candidate_write > 0.0:
                        break

            temp_c = nvme_temp_c_for_dev(io_dev)

        return MountMetrics(
            label=label,
            mount=mount,
            devpath=devpath,
            devname=devname,
            io_devname=io_dev,
            used_pct=used_pct,
            free_gb=free_gb,
            read_mbps=read_mbps,
            write_mbps=write_mbps,
            active=active,
            total_read_gb=total_read_gb,
            total_written_gb=total_written_gb,
            fstype=fstype,
            size=size,
            model=(model.strip() if isinstance(model, str) else model),
            rota=rota,
            temp_c=temp_c,
        )

    root = build("Root", "/")
    home = build("Home", home_mount)
    mounts: list[MountMetrics] = [root]
    if home.mount != root.mount:
        mounts.append(home)
    for extra_mount in _additional_storage_mounts(home_mount):
        mounts.append(build(_mount_label(extra_mount, home_mount), extra_mount))

    insights = StorageInsights(
        top_label="Home",
        home_top=_du_top_dirs(str(Path.home()), depth=1, topn=8),
        var_log=_dir_size("/var/log"),
        apt_cache=_dir_size("/var/cache/apt/archives"),
        journal=_journal_usage(),
    )

    return StorageSnapshot(root=root, home=home, mounts=mounts, insights=insights)


def gather_storage_insights_for_mount(mount: str) -> StorageInsights:
    home_mount = home_mountpoint()
    label = _mount_label(mount, home_mount)
    top_path = str(Path.home()) if mount == home_mount else mount

    return StorageInsights(
        top_label=label,
        home_top=_du_top_dirs(top_path, depth=1, topn=8),
        var_log=_dir_size("/var/log") if mount == "/" else None,
        apt_cache=_dir_size("/var/cache/apt/archives") if mount == "/" else None,
        journal=_journal_usage() if mount == "/" else None,
    )
