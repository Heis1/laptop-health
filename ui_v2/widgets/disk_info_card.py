from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThreadPool, QTimer, Qt, QEvent, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStyle,
    QVBoxLayout,
    QPushButton,
)

from ui_v2.qtworker import QtWorker
from ui_v2.services.storage_metrics import (
    gather_storage,
    StorageSnapshot,
    MountMetrics,
    load_excluded_storage_mounts,
    save_excluded_storage_mounts,
)
from ui_v2.widgets.cards import apply_responsive_card_fonts
from ui_v2.widgets.sparkline import Sparkline


def _accent_for_used(target: str, used_pct: int | None) -> str:
    if used_pct is None:
        return "purple"
    u = float(used_pct)
    if target == "/":
        if u < 75:
            return "green"
        if u < 88:
            return "orange"
        return "red"
    if u < 88:
        return "green"
    if u < 95:
        return "orange"
    return "red"


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _fmt_mbps(v: float | None) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except Exception:
        return "—"
    if v < 10:
        return f"{v:.1f}"
    return f"{v:.0f}"


def _fmt_meta(m: MountMetrics | _OverviewMount) -> str:
    bits: list[str] = []
    if m.mount:
        bits.append(f"Mount {m.mount}")
    if m.devpath:
        bits.append(m.devpath)
    if m.fstype:
        bits.append(m.fstype)
    if m.rota is not None:
        bits.append("SSD" if int(m.rota) == 0 else "HDD")
    if m.size:
        bits.append(m.size)
    if m.temp_c is not None:
        bits.append(f"{m.temp_c:.0f}°C")
    if m.total_read_gb is not None and m.total_written_gb is not None:
        bits.append(f"Total R/W {m.total_read_gb:.0f}G / {m.total_written_gb:.0f}G")
    if m.io_devname:
        bits.append(f"I/O /dev/{m.io_devname}")
    return " • ".join(bits) if bits else "—"


@dataclass
class _OverviewMount:
    mount: str
    used_pct: int | None
    free_gb: float | None
    label: str | None = None
    read_mbps: float | None = None
    write_mbps: float | None = None
    devpath: str | None = None
    fstype: str | None = None
    rota: int | None = None
    size: str | None = None
    temp_c: float | None = None
    total_read_gb: float | None = None
    total_written_gb: float | None = None
    io_devname: str | None = None


class DiskInfoCard(QFrame):
    target_changed = Signal(str, object, object, str)
    """
    Inspector tile: disk activity view with Root/Home toggle.
      - Big Read/Write MB/s + sparklines
      - Compact identity/meta line
      - Accent based on selected mount used %
      - Separate sparkline history for Root vs Home
    """

    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "purple")
        self.pool = QThreadPool()

        # Mount selection state
        self._target = "/"
        self._last_snap: StorageSnapshot | None = None
        self._overview = {"/": _OverviewMount("/", None, None)}
        self._mount_order = ["/"]
        self._excluded_mounts = load_excluded_storage_mounts()

        # Separate history buffers per mount (normalized 0..1)
        self._hist = {"/": {"read": deque([0.0] * 36, maxlen=36), "write": deque([0.0] * 36, maxlen=36)}}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveHDIcon).pixmap(16, 16))
        hdr.addWidget(ico)

        t = QLabel("Disk Info")
        t.setObjectName("CardTitle")
        hdr.addWidget(t)
        hdr.addStretch(1)

        # Clickable badge (styled like Badge)
        self.badge = QPushButton("Root")
        self.badge.setObjectName("Badge")
        self.badge.setCursor(Qt.PointingHandCursor)
        self.badge.setFlat(True)
        self.badge.setMinimumWidth(68)
        self.badge.setMaximumWidth(110)
        self.badge.clicked.connect(self._toggle_target)
        self.badge.installEventFilter(self)  # so we can refresh tooltip on hover
        hdr.addWidget(self.badge)

        self.manage_btn = QPushButton("Manage")
        self.manage_btn.setObjectName("Badge")
        self.manage_btn.setCursor(Qt.PointingHandCursor)
        self.manage_btn.setFlat(True)
        self.manage_btn.setMinimumWidth(78)
        self.manage_btn.setMaximumWidth(78)
        self.manage_btn.setToolTip("Choose which extra drives appear in the disk cycle")
        self.manage_btn.setProperty("class", "secondary")
        self.manage_btn.clicked.connect(self._open_mount_manager)
        hdr.addWidget(self.manage_btn)

        outer.addLayout(hdr)

        # Compact summary
        self.summary = QLabel("—")
        self.summary.setObjectName("CardSub")
        outer.addWidget(self.summary)

        # Read/Write grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.read_label = QLabel("Read MB/s")
        self.read_label.setObjectName("CardSub")
        self.write_label = QLabel("Write MB/s")
        self.write_label.setObjectName("CardSub")

        self.read_big = QLabel("—")
        self.read_big.setObjectName("CardBig")
        self.write_big = QLabel("—")
        self.write_big.setObjectName("CardBig")

        self.read_spark = Sparkline(list(self._hist["/"]["read"]), accent="blue")
        self.read_spark.setMinimumHeight(52)
        self.write_spark = Sparkline(list(self._hist["/"]["write"]), accent="orange")
        self.write_spark.setMinimumHeight(52)

        grid.addWidget(self.read_label, 0, 0)
        grid.addWidget(self.write_label, 0, 1)
        grid.addWidget(self.read_big, 1, 0)
        grid.addWidget(self.write_big, 1, 1)
        grid.addWidget(self.read_spark, 2, 0)
        grid.addWidget(self.write_spark, 2, 1)

        outer.addLayout(grid)

        # Meta
        self.meta = QLabel("—")
        self.meta.setObjectName("CardSub")
        self.meta.setWordWrap(True)
        outer.addWidget(self.meta)

        outer.addStretch(1)

        # initial tooltip
        self._update_badge_tooltip()

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()
        apply_responsive_card_fonts(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)

    def eventFilter(self, obj, event):
        # Update tooltip right as user hovers, so it always shows "switch to X"
        if obj is self.badge and event.type() == QEvent.Enter:
            self._update_badge_tooltip()
        return super().eventFilter(obj, event)

    def _update_badge_tooltip(self):
        if len(self._mount_order) <= 1:
            next_label = self.badge.text()
        else:
            idx = self._mount_order.index(self._target) if self._target in self._mount_order else 0
            next_key = self._mount_order[(idx + 1) % len(self._mount_order)]
            next_label = self._mount_label(next_key)
        self.badge.setToolTip(f"Click to switch to {next_label}")

    def _toggle_target(self):
        if not self._mount_order:
            return
        try:
            idx = self._mount_order.index(self._target)
        except ValueError:
            idx = 0
        self._target = self._mount_order[(idx + 1) % len(self._mount_order)]
        self.badge.setText(self._mount_label(self._target))
        self._update_badge_tooltip()

        if self._last_snap is not None:
            self._render(self._select_mount(self._last_snap), append=False)
            return
        self._render(self._overview[self._target], append=False)

    def _manageable_mounts(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for mount, node in self._overview.items():
            if mount in {"/", "/home", str(Path.home())}:
                continue
            label = getattr(node, "label", None) or self._mount_label(mount)
            items.append((mount, label))
        items.sort(key=lambda item: item[1].lower())
        return items

    def _open_mount_manager(self) -> None:
        items = self._manageable_mounts()
        if not items:
            return

        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground, True)
        host = self.window()
        dlg.setGeometry(host.geometry())

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("DiskManageScrim")
        scrim_l = QVBoxLayout(scrim)
        scrim_l.setContentsMargins(0, 0, 0, 0)
        scrim_l.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("DiskManageCard")
        card.setFixedWidth(520)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 16, 16, 16)
        card_l.setSpacing(10)

        title = QLabel("Choose which extra drives appear in the disk cycle.")
        title.setWordWrap(True)
        title.setObjectName("CardTitle")
        card_l.addWidget(title)

        checks: list[tuple[str, QCheckBox]] = []
        for mount, label in items:
            cb = QCheckBox(f"{label} ({mount})")
            cb.setChecked(mount not in self._excluded_mounts)
            card_l.addWidget(cb)
            checks.append((mount, cb))

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        actions.addWidget(cancel)
        save = QPushButton("Save")
        save.clicked.connect(dlg.accept)
        actions.addWidget(save)
        card_l.addLayout(actions)

        row.addWidget(card)
        row.addStretch(1)
        scrim_l.addStretch(1)
        scrim_l.addLayout(row)
        scrim_l.addStretch(1)
        lay.addWidget(scrim)
        dlg.setStyleSheet(
            """
            QFrame#DiskManageScrim {
                background: rgba(0, 0, 0, 0.55);
            }
            QFrame#DiskManageCard {
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid rgba(96,165,250,0.95);
                border-radius: 16px;
            }
            QCheckBox {
                color: rgba(255,255,255,0.90);
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QPushButton {
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 90px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }
            """
        )

        if dlg.exec() != QDialog.Accepted:
            return

        self._excluded_mounts = {mount for mount, cb in checks if not cb.isChecked()}
        save_excluded_storage_mounts(self._excluded_mounts)
        if self._last_snap is not None:
            self._apply(self._last_snap)

    def _select_mount(self, snap: StorageSnapshot) -> MountMetrics:
        for mount in getattr(snap, "mounts", []):
            if mount.mount == self._target:
                return mount
        if getattr(snap, "mounts", None):
            return snap.mounts[0]
        return snap.root

    def _ensure_history(self, mount: str) -> None:
        if mount in self._hist:
            return
        self._hist[mount] = {
            "read": deque([0.0] * 36, maxlen=36),
            "write": deque([0.0] * 36, maxlen=36),
        }

    def _mount_label(self, mount: str) -> str:
        node = self._overview.get(mount)
        if getattr(node, "label", None):
            return str(node.label)
        if mount == "/":
            return "Root"
        name = Path(mount).name.strip()
        return name or mount

    def _refresh(self):
        w = QtWorker(lambda: gather_storage(interval_s=1.2))
        w.signals.result.connect(self._apply)
        w.signals.error.connect(self._apply_err)
        self.pool.start(w)

    def _apply_err(self, msg: str):
        self.setProperty("accent", "red")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        if msg:
            self.meta.setText(msg)

    def _render(self, m: _OverviewMount, append: bool):
        # Compact summary line
        used = "—" if m.used_pct is None else f"{int(m.used_pct)}% used"
        free = "—" if m.free_gb is None else f"{float(m.free_gb):.0f} GB free"
        mount_label = getattr(m, "label", None) or self._mount_label(m.mount)
        self.summary.setText(f"{mount_label} • {used} • {free}")

        # Read/Write numbers
        self.read_big.setText(_fmt_mbps(m.read_mbps))
        self.write_big.setText(_fmt_mbps(m.write_mbps))

        # Update sparklines (cap at 200 MB/s for stable visuals)
        cap = 200.0
        self._ensure_history(m.mount)
        hist = self._hist[m.mount]
        if append:
            r = 0.0 if m.read_mbps is None else max(0.0, float(m.read_mbps))
            wv = 0.0 if m.write_mbps is None else max(0.0, float(m.write_mbps))
            hist["read"].append(_norm01(r, 0.0, cap))
            hist["write"].append(_norm01(wv, 0.0, cap))

        if hasattr(self.read_spark, "set_points"):
            self.read_spark.set_points(list(hist["read"]))
            self.write_spark.set_points(list(hist["write"]))
        else:
            self.read_spark._points = list(hist["read"])
            self.write_spark._points = list(hist["write"])
            self.read_spark.update()
            self.write_spark.update()

        # Meta + accent
        self.meta.setText(_fmt_meta(m))
        self.setProperty("accent", _accent_for_used(m.mount, m.used_pct))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        self._target = m.mount
        self.badge.setText(mount_label)
        self._update_badge_tooltip()
        self.target_changed.emit(self._target, m.used_pct, m.free_gb, mount_label)

    def update_overview(self, m) -> None:
        home_mount = getattr(m, "home_mount", None) or str(Path.home())
        self._overview["/"] = _OverviewMount(
            mount="/",
            label="Root",
            used_pct=getattr(m, "root_used_pct", None),
            free_gb=getattr(m, "root_free_gb", None),
        )
        if home_mount != "/":
            self._overview[home_mount] = _OverviewMount(
            mount=home_mount,
            label="Home",
            used_pct=getattr(m, "home_used_pct", None),
            free_gb=getattr(m, "home_free_gb", None),
            )
            fallback_mounts = ["/", home_mount]
        else:
            fallback_mounts = ["/"]
        if self._last_snap is None:
            self._mount_order = fallback_mounts
        elif not self._mount_order:
            self._mount_order = fallback_mounts
        if self._target not in self._mount_order and self._mount_order:
            self._target = self._mount_order[0]
        if self._last_snap is None:
            self._render(self._overview[self._target], append=False)

    def _apply(self, snap):
        if not isinstance(snap, StorageSnapshot):
            self._apply_err("Disk info error")
            return

        self._last_snap = snap
        mounts = getattr(snap, "mounts", None) or [snap.root, snap.home]
        visible_mounts = [m for m in mounts if m.mount not in self._excluded_mounts or m.mount in {"/", snap.home.mount}]
        self._mount_order = [m.mount for m in visible_mounts]
        for mount in mounts:
            self._ensure_history(mount.mount)
            self._overview[mount.mount] = _OverviewMount(
                mount=mount.mount,
                label=mount.label,
                used_pct=mount.used_pct,
                free_gb=mount.free_gb,
                read_mbps=mount.read_mbps,
                write_mbps=mount.write_mbps,
                devpath=mount.devpath,
                fstype=mount.fstype,
                rota=mount.rota,
                size=mount.size,
                temp_c=mount.temp_c,
                total_read_gb=mount.total_read_gb,
                total_written_gb=mount.total_written_gb,
                io_devname=mount.io_devname,
            )
        if self._target not in self._mount_order and self._mount_order:
            self._target = self._mount_order[0]
        m = self._select_mount(snap)
        self._render(m, append=True)
