from __future__ import annotations

from collections import deque

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QSizePolicy

from ui_v2.widgets.cards import MetricCard, UpdatesCard
from ui_v2.widgets.disk_usage_card import DiskUsageCard
from ui_v2.widgets.network_card import NetworkCard
from ui_v2.widgets.inspector import Inspector
from ui_v2.workers import Worker
from ui_v2.services.overview_metrics import gather_overview, OverviewMetrics
from ui_v2.services.gpu_metrics import get_gpu, GpuInfo


def _fix_top_row_heights(*widgets, h: int = 165) -> None:
    # Force consistent height for top-row cards (CPU/GPU/Disk Usage)
    for w in widgets:
        try:
            w.setMinimumHeight(h)
            w.setMaximumHeight(h)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


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
        self._workers: list[object] = []

        # Sparkline histories (store 0..1 floats)
        self._cpu_hist = deque([0.0] * 30, maxlen=30)
        self._gpu_hist = deque([0.0] * 30, maxlen=30)

        # GPU last-known values (avoid flicker / avoid overwriting with None)
        self._gpu_last_temp: float | None = None
        self._gpu_last_util: float | None = None
        self._gpu_last_name: str | None = None

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
        self.cpu = MetricCard("CPU", "—", "—", "green", spark_points=[0.0]*24)
        self.gpu = MetricCard("GPU", "—", "—", "blue", spark_points=[0.0]*24)

        self.disk = DiskUsageCard(0, "—")
        try:
            self.disk.title.setText("Disk Usage (Home)")
        except Exception:
            pass

        _fix_top_row_heights(self.cpu, self.gpu, self.disk, h=165)

        grid.addWidget(self.cpu, 0, 0)
        grid.addWidget(self.gpu, 0, 1)
        grid.addWidget(self.disk, 0, 2, 1, 2)

        # Second row
        self.wakeups = MetricCard("Wakeups", "—", "—", "green")
        self.updates = UpdatesCard("red")
        self.updates.details_requested.connect(self._go_updates)
        self.net = NetworkCard()

        for w in (self.wakeups, self.updates, self.net):
            w.setFixedHeight(170)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grid.addWidget(self.wakeups, 1, 0)
        grid.addWidget(self.updates, 1, 1)
        grid.addWidget(self.net, 1, 2, 1, 2)

        outer.addLayout(grid)
        self.inspector = Inspector()
        outer.addWidget(self.inspector)

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)  # set to 1000 if you want “live-live”
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _refresh(self):
        # Overview (CPU/disk/network/updates)
        w = Worker(lambda: gather_overview(interval_s=1.0))
        self._workers.append(w)
        def _done_overview(res):
            try:
                self._apply(res)
            finally:
                try:
                    self._workers.remove(w)
                except ValueError:
                    pass
        w.signals.finished.connect(_done_overview)
        self.pool.start(w)

        # GPU (separate worker so Overview doesn’t block)
        w_gpu = Worker(get_gpu)
        self._workers.append(w_gpu)
        def _done_gpu(res):
            try:
                self._apply_gpu(res)
            finally:
                try:
                    self._workers.remove(w_gpu)
                except ValueError:
                    pass
        w_gpu.signals.finished.connect(_done_gpu)
        self.pool.start(w_gpu)

    def _apply_gpu(self, r):
        # Ignore garbage / failures (don’t overwrite UI with — every tick)
        if not isinstance(r, GpuInfo):
            return

        if r.name:
            self._gpu_last_name = r.name
        if r.temp_c is not None:
            self._gpu_last_temp = r.temp_c
        if r.busy_pct is not None:
            self._gpu_last_util = r.busy_pct

        # If still nothing useful, show once but don’t flicker
        if self._gpu_last_temp is None and self._gpu_last_util is None:
            self.gpu.set_values("—", "GPU metrics unavailable", "blue")
            return

        # Spark: prefer util, else temp
        try:
            if self._gpu_last_util is not None:
                self._gpu_hist.append(_norm01(self._gpu_last_util, 0.0, 100.0))
            elif self._gpu_last_temp is not None:
                self._gpu_hist.append(_norm01(self._gpu_last_temp, 30.0, 95.0))
            self.gpu.set_spark(list(self._gpu_hist))
        except Exception:
            pass

        # Display
        if self._gpu_last_temp is None:
            big = "—"
            accent = "blue"
        else:
            big = f"{self._gpu_last_temp:.0f}°C"
            accent = "green" if self._gpu_last_temp < 60 else ("orange" if self._gpu_last_temp < 80 else "red")

        util = "—" if self._gpu_last_util is None else f"{self._gpu_last_util:.0f}% load"
        name = self._gpu_last_name or "GPU"
        self.gpu.set_values(big, f"{name} • {util}", accent)

    def _apply(self, result):
        if not isinstance(result, OverviewMetrics):
            return

        # CPU numbers + spark (temp mapped 30..95°C)
        big, sub, accent = _fmt_cpu(result.cpu_temp_c, result.cpu_freq_ghz)
        self.cpu.set_values(big, sub, accent)
        if result.cpu_temp_c is not None:
            self._cpu_hist.append(_norm01(result.cpu_temp_c, 30.0, 95.0))
            try:
                self.cpu.set_spark(list(self._cpu_hist))
            except Exception:
                pass

        # Disk (Home + Root in subtitle)
        home_used = result.home_used_pct
        home_free = result.home_free_gb
        root_free = result.root_free_gb

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

        if home_used is None:
            self.disk.big.setText("—")
            self.disk.bar.setValue(0)
        else:
            self.disk.big.setText(f"{int(home_used)}% Used")
            self.disk.bar.setValue(max(0, min(100, int(home_used))))

        if home_free is None and root_free is None:
            self.disk.sub.setText("—")
        else:
            hf = "—" if home_free is None else f"{home_free:.0f} GB Free"
            rf = "—" if root_free is None else f"{root_free:.0f} GB Free"
            self.disk.sub.setText(f"Home: {hf}   •   Root: {rf}")

        # Wakeups + Network + Updates
        self.wakeups.set_values(result.wakeups_big, result.wakeups_sub, result.wakeups_accent)
        self.net.set_network(result.down_mbps, result.latency_ms)
        self.updates.set_updates(
            getattr(result, 'updates_available', None),
            getattr(result, 'security_updates', None),
            getattr(result, 'reboot_required', None),
            getattr(result, 'kept_back_updates', 0),
            getattr(result, 'held_updates', 0),
            getattr(result, 'updates_badge', None),
            getattr(result, 'updates_accent', None),
        )
        try:
            self.inspector.update_overview(result)
        except Exception:
            pass


    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
        super().closeEvent(event)


    def _go_updates(self):
        # MainWindow owns the QStackedWidget + _go("updates")
        w = self.window()
        if hasattr(w, "_go"):
            w._go("updates")
