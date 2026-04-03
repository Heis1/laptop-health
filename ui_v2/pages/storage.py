from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui_v2.services.storage_metrics import (
    MountMetrics,
    StorageSnapshot,
    gather_storage,
    gather_storage_insights_for_mount,
)
from ui_v2.widgets.disk_usage_card import DiskUsageCard
from ui_v2.widgets.storage_insights_card import StorageInsightsCard
from ui_v2.widgets.storage_io_card import StorageIOCard
from ui_v2.workers import Worker


class StoragePage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self._mounts: list[MountMetrics] = []
        self._selected_mount = "/"
        self._insights_mount: str | None = None
        self._drive_buttons: dict[str, QPushButton] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        self.drive_panel = QFrame()
        self.drive_panel.setObjectName("Card")
        self.drive_panel.setProperty("accent", "blue")
        self.drive_panel.setFixedWidth(232)
        drive_outer = QVBoxLayout(self.drive_panel)
        drive_outer.setContentsMargins(16, 16, 16, 16)
        drive_outer.setSpacing(10)

        drive_title = QLabel("Drives")
        drive_title.setObjectName("CardTitle")
        drive_outer.addWidget(drive_title)

        drive_sub = QLabel("Select a mounted drive to inspect its usage, I/O, and largest folders.")
        drive_sub.setObjectName("CardSub")
        drive_sub.setWordWrap(True)
        drive_outer.addWidget(drive_sub)

        self.drive_list = QVBoxLayout()
        self.drive_list.setContentsMargins(0, 6, 0, 0)
        self.drive_list.setSpacing(8)
        drive_outer.addLayout(self.drive_list)
        drive_outer.addStretch(1)

        outer.addWidget(self.drive_panel, 0)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)
        outer.addLayout(right, 1)

        self.header = QFrame()
        self.header.setObjectName("Card")
        self.header.setProperty("accent", "purple")
        header_outer = QVBoxLayout(self.header)
        header_outer.setContentsMargins(18, 16, 18, 16)
        header_outer.setSpacing(8)

        header_top = QHBoxLayout()
        header_top.setContentsMargins(0, 0, 0, 0)
        header_top.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        self.mount_label = QLabel("Storage")
        self.mount_label.setObjectName("CardBig")
        title_box.addWidget(self.mount_label)

        self.mount_hint = QLabel("No drives detected")
        self.mount_hint.setObjectName("CardSub")
        self.mount_hint.setWordWrap(True)
        title_box.addWidget(self.mount_hint)
        header_top.addLayout(title_box, 1)

        self.insights_btn = QPushButton("Hide Insights")
        self.insights_btn.setObjectName("Badge")
        self.insights_btn.setCursor(Qt.PointingHandCursor)
        self.insights_btn.setMinimumWidth(116)
        self.insights_btn.clicked.connect(self._toggle_insights)
        header_top.addWidget(self.insights_btn, 0, Qt.AlignTop)

        header_outer.addLayout(header_top)

        self.mount_meta = QLabel("—")
        self.mount_meta.setObjectName("CardSub")
        self.mount_meta.setWordWrap(True)
        header_outer.addWidget(self.mount_meta)

        right.addWidget(self.header)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(12)

        self.usage = DiskUsageCard(mount_path="/")
        self.io = StorageIOCard("Storage I/O", accent="orange")
        for widget in (self.usage, self.io):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(176)
            widget.setMaximumHeight(176)

        cards_row.addWidget(self.usage, 1)
        cards_row.addWidget(self.io, 1)
        right.addLayout(cards_row)

        self.insights = StorageInsightsCard()
        self.insights.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.insights.setMaximumHeight(280)
        right.addWidget(self.insights, 0)
        right.addStretch(1)

        self._sync_drive_buttons()
        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _clear_drive_buttons(self) -> None:
        while self.drive_list.count():
            item = self.drive_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._drive_buttons.clear()

    def _select_mount(self, mount: str) -> None:
        self._selected_mount = mount
        self._insights_mount = None
        self._apply_current()

    def _make_drive_button(self, mount: MountMetrics) -> QPushButton:
        btn = QPushButton(mount.label or mount.mount)
        btn.setCheckable(True)
        btn.setObjectName("ActionButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(lambda checked=False, m=mount.mount: self._select_mount(m))
        btn.setToolTip(mount.mount)
        return btn

    def _sync_drive_buttons(self) -> None:
        self._clear_drive_buttons()
        if not self._mounts:
            empty = QLabel("No drives detected")
            empty.setObjectName("CardSub")
            empty.setWordWrap(True)
            self.drive_list.addWidget(empty)
            return
        for mount in self._mounts:
            btn = self._make_drive_button(mount)
            self._drive_buttons[mount.mount] = btn
            self.drive_list.addWidget(btn)
        self.drive_list.addStretch(1)
        self._sync_button_states()

    def _sync_button_states(self) -> None:
        for mount, btn in self._drive_buttons.items():
            btn.setChecked(mount == self._selected_mount)

    def _current_mount(self) -> MountMetrics | None:
        for mount in self._mounts:
            if mount.mount == self._selected_mount:
                return mount
        return self._mounts[0] if self._mounts else None

    def _refresh(self) -> None:
        w = Worker(lambda: gather_storage(interval_s=1.0))
        w.signals.finished.connect(self._apply)
        self.pool.start(w)

    def _toggle_insights(self) -> None:
        visible = not self.insights.isVisible()
        self.insights.setVisible(visible)
        self.insights_btn.setText("Hide Insights" if visible else "Show Insights")
        if visible:
            self._refresh_insights(force=True)

    def _refresh_insights(self, force: bool = False) -> None:
        if not self.insights.isVisible():
            return
        if not force and self._insights_mount == self._selected_mount:
            return
        mount = self._selected_mount
        w = Worker(lambda: (mount, gather_storage_insights_for_mount(mount)))
        w.signals.finished.connect(self._apply_insights)
        self.pool.start(w)

    def _apply_insights(self, result) -> None:
        if not isinstance(result, tuple) or len(result) != 2:
            return
        mount, insights = result
        if mount != self._selected_mount:
            return
        self._insights_mount = mount
        self.insights.apply(insights)

    def _apply_current(self) -> None:
        current = self._current_mount()
        self._sync_button_states()
        if current is None:
            self.mount_label.setText("Storage")
            self.mount_hint.setText("No drives detected")
            self.mount_meta.setText("—")
            self.usage.set_disk(None, None)
            return

        self.mount_label.setText(current.label or current.mount)
        self.mount_hint.setText(current.mount)

        meta: list[str] = []
        if current.size:
            meta.append(f"Size {current.size}")
        if current.fstype:
            meta.append(f"FS {current.fstype.upper()}")
        if current.rota is not None:
            meta.append("SSD" if current.rota == 0 else "HDD")
        if current.devpath:
            meta.append(current.devpath)
        self.mount_meta.setText(" • ".join(meta) if meta else "Mounted drive")

        self.usage.mount_path = current.mount
        self.usage.title.setText(f"Disk Usage ({current.label})")
        self.usage.set_disk(current.used_pct, current.free_gb, target=current.mount, mount_label=current.label)
        self.io.apply(current)
        self._refresh_insights(force=True)

    def _apply(self, result) -> None:
        if not isinstance(result, StorageSnapshot):
            return
        self._mounts = getattr(result, "mounts", None) or [result.root, result.home]
        if self._selected_mount not in {m.mount for m in self._mounts} and self._mounts:
            self._selected_mount = self._mounts[0].mount
        self._sync_drive_buttons()
        self._apply_current()
