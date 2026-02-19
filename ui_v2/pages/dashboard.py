from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QGridLayout, QWidget

from ui_v2.services.disk import get_root_usage
from ui_v2.services.system import get_cpu_temp
from ui_v2.services.updates import get_update_count, reboot_required
from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.ring import Ring
from ui_v2.workers import Worker


def accent_for_percent(p: int) -> str:
    if p >= 85:
        return "red"
    if p >= 70:
        return "orange"
    return "green"


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)

        self.cpu_card = MetricCard("CPU", "Loading…", "—", "green")
        self.disk_ring = Ring(0, "orange")
        self.disk_card = MetricCard("Disk Usage", "Loading…", "—", "orange", right_widget=self.disk_ring)
        self.updates_card = MetricCard("Pending Updates", "Loading…", "—", "red", badge=None)

        self.grid.addWidget(self.cpu_card, 0, 0)
        self.grid.addWidget(self.disk_card, 0, 1)
        self.grid.addWidget(self.updates_card, 1, 0, 1, 2)

        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(10_000)  # 10s refresh
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self) -> None:
        self._load_cpu()
        self._load_disk()
        self._load_updates()

    # ---- CPU ----
    def _load_cpu(self) -> None:
        w = Worker(get_cpu_temp)
        w.signals.finished.connect(self._cpu_done)
        self.pool.start(w)

    def _cpu_done(self, result) -> None:
        temp = result if isinstance(result, (int, float)) else None
        if temp is None:
            self.cpu_card.findChild(QWidget).findChild  # noop: keep stable even if layout changes
            self._set_card_text(self.cpu_card, "CPU", "N/A", "sensors not available", "orange")
        else:
            accent = "green" if temp < 80 else ("orange" if temp < 90 else "red")
            self._set_card_text(self.cpu_card, "CPU", f"{temp:.1f}°C", "Live CPU temperature", accent)

    # ---- Disk ----
    def _load_disk(self) -> None:
        w = Worker(get_root_usage)
        w.signals.finished.connect(self._disk_done)
        self.pool.start(w)

    def _disk_done(self, result) -> None:
        if not isinstance(result, tuple):
            self._set_card_text(self.disk_card, "Disk Usage", "N/A", "df not available", "orange")
            return
        percent, avail = result
        acc = accent_for_percent(percent)
        self.disk_card.setProperty("accent", acc)
        self.disk_card.style().unpolish(self.disk_card)
        self.disk_card.style().polish(self.disk_card)
        self.disk_ring.value = percent
        self.disk_ring.accent = acc if acc != "green" else "orange"
        self.disk_ring.update()
        self._set_card_text(self.disk_card, "Disk Usage", f"{percent}% Used", f"{avail} Free on /", acc)

    # ---- Updates ----
    def _load_updates(self) -> None:
        w = Worker(get_update_count)
        w.signals.finished.connect(self._updates_done)
        self.pool.start(w)

    def _updates_done(self, result) -> None:
        if not isinstance(result, tuple):
            self._set_card_text(self.updates_card, "Pending Updates", "N/A", "apt-check unavailable", "orange")
            return
        total, sec = result
        reboot = reboot_required()

        if total == 0:
            acc = "green"
            badge = None
        elif sec > 0 or reboot:
            acc = "red"
            badge = "Attention"
        else:
            acc = "orange"
            badge = None

        self.updates_card.setProperty("accent", acc)
        self.updates_card.style().unpolish(self.updates_card)
        self.updates_card.style().polish(self.updates_card)

        # badge on/off (rebuild title row badge simply by using subtitle)
        sub = f"{sec} security • Reboot: {'Yes' if reboot else 'No'}" if total else "System up to date"
        big = f"{total} Updates" if total else "0 Updates"

        # If you want a real badge widget later, we’ll add it—keeping this stable for now.
        self._set_card_text(self.updates_card, "Pending Updates", big, sub, acc)

    # ---- Helpers ----
    def _set_card_text(self, card: MetricCard, title: str, big: str, sub: str, accent: str) -> None:
        # MetricCard structure:
        # outer layout:
        #   [0] title row layout
        #   [1] content row layout (left column has big/sub)
        outer = card.layout()
        content_layout = outer.itemAt(1).layout()
        left_layout = content_layout.itemAt(0).layout()
        big_lbl = left_layout.itemAt(0).widget()
        sub_lbl = left_layout.itemAt(1).widget()

        big_lbl.setText(big)
        sub_lbl.setText(sub)

        card.setProperty("accent", accent)
        card.style().unpolish(card)
        card.style().polish(card)
        card.update()
