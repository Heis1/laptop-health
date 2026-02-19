from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QGridLayout, QSizePolicy

from ui_v2.widgets.disk_usage_card import DiskUsageCard
from ui_v2.widgets.storage_io_card import StorageIOCard
from ui_v2.widgets.storage_insights_card import StorageInsightsCard
from ui_v2.workers import Worker
from ui_v2.services.storage_metrics import gather_storage, StorageSnapshot


class StoragePage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # Usage cards
        self.usage_root = DiskUsageCard(mount_path="/")
        self.usage_home = DiskUsageCard()

        for w in (self.usage_root, self.usage_home):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grid.addWidget(self.usage_root, 0, 0)
        grid.addWidget(self.usage_home, 0, 1)

        # IO cards
        self.io_root = StorageIOCard("Root I/O", accent="orange")
        self.io_home = StorageIOCard("Home I/O", accent="orange")

        grid.addWidget(self.io_root, 1, 0)
        grid.addWidget(self.io_home, 1, 1)

        # Insights (spans both columns)
        self.insights = StorageInsightsCard()
        grid.addWidget(self.insights, 2, 0, 1, 2)

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _refresh(self):
        w = Worker(lambda: gather_storage(interval_s=0.2))
        w.signals.finished.connect(self._apply)
        self.pool.start(w)

    def _apply(self, result):
        if not isinstance(result, StorageSnapshot):
            return

        # Root usage
        self.usage_root.mount_path = result.root.mount
        self.usage_root.refresh()

        # Home usage
        self.usage_home.mount_path = result.home.mount
        self.usage_home.refresh()

        # IO cards
        self.io_root.apply(result.root)
        self.io_home.apply(result.home)

        # Insights
        self.insights.apply(result.insights)
