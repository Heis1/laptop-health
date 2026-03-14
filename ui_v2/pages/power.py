from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QHBoxLayout, QLabel, QStyle

from ui_v2.services.perf import top_ctxt_switchers
from ui_v2.services.wakeups import (
    sample_wake_activity_fast,
    wakeups_hint_fast,
    wakeups_hint_deep,
    sample_wakeups_powertop_slow,
    classify_wakeup_proxy,
)
from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.offender_list import OffenderList
from ui_v2.workers import Worker



class PowerPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # Wakeups card
        self.wakeup_card = MetricCard("Wakeups", "Loading…", wakeups_hint_fast(), "orange")
        v.addWidget(self.wakeup_card)

        # Action row (matches dashboard aesthetic)
        actions = QFrame()
        a = QHBoxLayout(actions)
        a.setContentsMargins(0, 0, 0, 0)
        a.setSpacing(10)

        left = QLabel("Power & Wake Analysis")
        left.setObjectName("CardTitle")
        a.addWidget(left)
        a.addStretch(1)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("GhostBtn")
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_refresh.clicked.connect(self.refresh)
        a.addWidget(self.btn_refresh)

        self.btn_deep = QPushButton("Deep sample")
        self.btn_deep.setObjectName("GhostBtn")
        self.btn_deep.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))
        self.btn_deep.clicked.connect(self.deep_sample)
        a.addWidget(self.btn_deep)

        v.addWidget(actions)

        # Offenders
        self.offenders = OffenderList()
        v.addWidget(self.offenders, 1)

        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        self._load_fast_proxy()
        self._load_offenders()

    # ---- Fast proxy ----
    def _load_fast_proxy(self):
        w = Worker(lambda: sample_wake_activity_fast(1.0))
        w.signals.finished.connect(self._fast_done)
        self.pool.start(w)

    def _fast_done(self, result):
        self.btn_refresh.setEnabled(True)
        if not isinstance(result, dict):
            self._set_wakeup_text("N/A", wakeups_hint_fast(), "orange")
            return
        ctxt = float(result.get("ctxt_per_s", 0.0))
        intr = float(result.get("intr_per_s", 0.0))
        acc = classify_wakeup_proxy(ctxt, intr)
        big = f"{ctxt:,.0f} ctx/s"
        sub = f"{intr:,.0f} intr/s • {wakeups_hint_fast()}"
        self._set_wakeup_text(big, sub, acc)

    # ---- Deep sample ----
    def deep_sample(self):
        self.btn_deep.setEnabled(False)
        self._set_wakeup_text("Sampling…", wakeups_hint_deep(), "orange")
        w = Worker(lambda: sample_wakeups_powertop_slow(timeout_s=25))
        w.signals.finished.connect(self._deep_done)
        self.pool.start(w)

    def _deep_done(self, result):
        self.btn_deep.setEnabled(True)
        if isinstance(result, (int, float)):
            wps = float(result)
            self._set_wakeup_text(f"{wps:,.0f} wakeups/s", "powertop deep sample", "orange")
        else:
            self._set_wakeup_text("Deep sample failed", wakeups_hint_deep(), "orange")

    # ---- Offenders ----
    def _load_offenders(self):
        w = Worker(lambda: top_ctxt_switchers(1.0, limit=5))
        w.signals.finished.connect(self._offenders_done)
        self.pool.start(w)

    def _offenders_done(self, result):
        items = result if isinstance(result, list) else []
        self.offenders.set_items(items)

    def _set_wakeup_text(self, big: str, sub: str, accent: str):
        outer = self.wakeup_card.layout()
        content_layout = outer.itemAt(1).layout()
        left_layout = content_layout.itemAt(0).layout()
        big_lbl = left_layout.itemAt(0).widget()
        sub_lbl = left_layout.itemAt(1).widget()
        big_lbl.setText(big)
        sub_lbl.setText(sub)
        self.wakeup_card.setProperty("accent", accent)
        self.wakeup_card.style().unpolish(self.wakeup_card)
        self.wakeup_card.style().polish(self.wakeup_card)
        self.wakeup_card.update()
