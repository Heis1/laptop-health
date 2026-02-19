from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QSizePolicy

from ui_v2.widgets.cards import MetricCard, UpdatesCard
from ui_v2.widgets.disk_usage_card import DiskUsageCard
from ui_v2.widgets.network_card import NetworkCard
from ui_v2.widgets.inspector import Inspector
from ui_v2.workers import Worker
from ui_v2.services.overview_metrics import gather_overview, OverviewMetrics


def _fmt_cpu(temp_c: float | None, ghz: float | None) -> tuple[str, str, str]:
    if temp_c is None:
        big = "—"
        accent = "blue"
    else:
        big = f"{temp_c:.0f}°C"
        accent = "green" if temp_c < 55 else ("orange" if temp_c < 75 else "red")
    sub = "—" if ghz is None else f"{ghz:.1f} GHz"
    return big, sub, accent


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 2)

        # Top row
        self.cpu = MetricCard("CPU", "—", "—", "green", spark_points=[0.35,0.45,0.42,0.52,0.49,0.6,0.55])
        self.gpu = MetricCard("GPU", "—", "—", "blue", spark_points=[0.22,0.28,0.26,0.35,0.3,0.38,0.33])

        self.disk = DiskUsageCard(0, "—")
        try:
            self.disk.title.setText("Disk Usage (Home)")
        except Exception:
            pass

        for w in (self.cpu, self.gpu, self.disk):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grid.addWidget(self.cpu, 0, 0)
        grid.addWidget(self.gpu, 0, 1)
        grid.addWidget(self.disk, 0, 2, 1, 2)

        # Second row
        self.updates = UpdatesCard("red")
        self.net = NetworkCard()

        self.updates.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.net.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grid.addWidget(self.updates, 1, 0, 1, 2)
        grid.addWidget(self.net, 1, 2, 1, 2)

        outer.addLayout(grid)
        outer.addWidget(Inspector())

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _refresh(self):
        w = Worker(lambda: gather_overview(interval_s=1.0))
        w.signals.finished.connect(self._apply)
        self.pool.start(w)

    def _apply(self, result):
        if not isinstance(result, OverviewMetrics):
            return

        big, sub, accent = _fmt_cpu(result.cpu_temp_c, result.cpu_freq_ghz)
        self.cpu.set_values(big, sub, accent)

        # GPU stays placeholder until wired
        self.gpu.set_values("—", "Not wired yet", "blue")

        # Home disk main, root warning in subtitle
        home_used = result.home_used_pct
        home_free = result.home_free_gb
        root_free = result.root_free_gb

        # Accent based on root free space (because root is operational risk)
        disk_accent = "orange"
        if root_free is not None:
            if root_free < 5:
                disk_accent = "red"
            elif root_free < 8:
                disk_accent = "orange"
            else:
                disk_accent = "orange"

        self.disk.setProperty("accent", disk_accent)
        self.disk.style().unpolish(self.disk)
        self.disk.style().polish(self.disk)
        self.disk.update()

        # Set displayed values (home)
        if home_used is None:
            self.disk.big.setText("—")
            self.disk.bar.setValue(0)
        else:
            self.disk.big.setText(f"{int(home_used)}% Used")
            self.disk.bar.setValue(max(0, min(100, int(home_used))))

        # Subtitle: Home free + Root free
        if home_free is None and root_free is None:
            self.disk.sub.setText("—")
        else:
            hf = "—" if home_free is None else f"{home_free:.0f} GB Free"
            rf = "—" if root_free is None else f"{root_free:.0f} GB Free"
            self.disk.sub.setText(f"Home: {hf}   •   Root: {rf}")

        self.net.set_network(result.down_mbps, result.latency_ms)
        self.updates.set_updates(result.updates_available)
