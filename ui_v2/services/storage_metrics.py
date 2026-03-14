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

def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

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
    total_read_gb: float | None
    total_written_gb: float | None
    fstype: str | None
    size: str | None
    model: str | None
    rota: int | None
    temp_c: float | None

@dataclass
class StorageInsights:
    home_top: list[tuple[str, str]]
    var_log: str | None
    apt_cache: str | None
    journal: str | None

@dataclass
class StorageSnapshot:
    root: MountMetrics
    home: MountMetrics
    insights: StorageInsights

def gather_storage(interval_s: float = 1.0) -> StorageSnapshot:
    home_mount = home_mountpoint()
    blk = lsblk_info()

    s1 = read_diskstats()
    time.sleep(max(0.5, float(interval_s)))
    s2 = read_diskstats()

    def build(label: str, mount: str) -> MountMetrics:
        devpath = device_for_mount(mount)
        devname = devname_from_devpath(devpath) if devpath else None
        used_pct, free_gb = _usage(mount)

        read_mbps = write_mbps = None
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

            io_dev = node.get("pkname") or parent_devname(devname)

            # totals (since boot) from latest sample s2
            if io_dev in s2:
                sec = sector_size_bytes(io_dev)
                r, w = s2[io_dev]
                total_read_gb = (r * sec) / (1024**3)
                total_written_gb = (w * sec) / (1024**3)

            # speed over interval
            if io_dev in s1 and io_dev in s2:
                r1, w1 = s1[io_dev]
                r2, w2 = s2[io_dev]
                sec = sector_size_bytes(io_dev)
                dt = max(0.5, float(interval_s))
                read_mbps = ((max(0, r2 - r1) * sec) / dt) / (1024**2)
                write_mbps = ((max(0, w2 - w1) * sec) / dt) / (1024**2)

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

    insights = StorageInsights(
        home_top=_du_top_dirs(str(Path.home()), depth=1, topn=8),
        var_log=_dir_size("/var/log"),
        apt_cache=_dir_size("/var/cache/apt/archives"),
        journal=_journal_usage(),
    )

    return StorageSnapshot(root=root, home=home, insights=insights)
