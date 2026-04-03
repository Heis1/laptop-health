from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QHBoxLayout, QLabel, QStyle

import system
from ui_v2.services.perf import top_ctxt_switchers
from ui_v2.services.wakeups import (
    sample_wake_activity_fast,
    wakeups_hint_fast,
    wakeups_hint_deep,
    deep_sample_ready,
    deep_sample_state,
    deep_sample_debug_text,
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

        self.header = QFrame()
        self.header.setObjectName("Card")
        self.header.setProperty("accent", "orange")
        h = QVBoxLayout(self.header)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        left = QLabel("Power & Thermal Analysis")
        left.setObjectName("CardTitle")
        title_box.addWidget(left)

        self.header_sub = QLabel("Track wake activity, context-switch churn, and deep powertop sampling readiness.")
        self.header_sub.setObjectName("CardSub")
        self.header_sub.setWordWrap(True)
        title_box.addWidget(self.header_sub)

        top.addLayout(title_box, 1)

        self.deep_status = QLabel("Checking deep analysis")
        self.deep_status.setObjectName("Badge")
        top.addWidget(self.deep_status, 0, Qt.AlignTop)
        h.addLayout(top)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("ActionButton")
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_refresh.clicked.connect(self.refresh)
        actions.addWidget(self.btn_refresh)

        self.btn_deep = QPushButton("Run Deep Analysis")
        self.btn_deep.setObjectName("ActionButton")
        self.btn_deep.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))
        self.btn_deep.clicked.connect(self.deep_sample)
        actions.addWidget(self.btn_deep)
        actions.addStretch(1)
        h.addLayout(actions)

        self.deep_hint = QLabel("—")
        self.deep_hint.setObjectName("CardSub")
        self.deep_hint.setWordWrap(True)
        h.addWidget(self.deep_hint)

        self.deep_debug = QLabel("")
        self.deep_debug.setObjectName("CardSub")
        self.deep_debug.setWordWrap(True)
        self.deep_debug.hide()
        h.addWidget(self.deep_debug)

        helper_row = QHBoxLayout()
        helper_row.setContentsMargins(0, 0, 0, 0)
        helper_row.setSpacing(8)

        self.btn_helper = QPushButton("Copy `sudo -v`")
        self.btn_helper.setObjectName("Badge")
        self.btn_helper.setCursor(Qt.PointingHandCursor)
        self.btn_helper.clicked.connect(self._helper_action)
        helper_row.addWidget(self.btn_helper)
        helper_row.addStretch(1)
        h.addLayout(helper_row)

        v.addWidget(self.header)

        # Wakeups card
        self.wakeup_card = MetricCard("Wakeups", "Loading…", wakeups_hint_fast(), "orange")
        v.addWidget(self.wakeup_card)

        # Offenders
        self.offenders = OffenderList()
        v.addWidget(self.offenders, 1)

        self._sync_deep_status()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _sync_deep_status(self) -> None:
        state, msg = deep_sample_state()
        self.deep_debug.setText(deep_sample_debug_text())
        ready = state == "ready"
        self.btn_deep.setEnabled(ready)
        if state == "ready":
            self.deep_status.setText("Deep Ready")
            self.btn_helper.hide()
            self.deep_hint.setText(wakeups_hint_deep())
        elif state == "needs_auth":
            self.deep_status.setText("Needs sudo auth")
            self.btn_helper.setText("Copy `sudo -v`")
            self.btn_helper.show()
            self.deep_hint.setText(msg)
        elif state == "missing_powertop":
            self.deep_status.setText("powertop missing")
            self.btn_helper.setText("Install `powertop`")
            self.btn_helper.show()
            self.deep_hint.setText(msg)
        else:
            self.deep_status.setText("Deep blocked")
            self.btn_helper.hide()
            self.deep_hint.setText(msg)

    def _helper_action(self) -> None:
        state, _ = deep_sample_state()
        if state == "needs_auth":
            try:
                system.clip_set_text("sudo -v")
                self.deep_hint.setText("Copied `sudo -v`. Run it in a terminal, then return here and click Refresh.")
            except Exception:
                self.deep_hint.setText("Run `sudo -v` in a terminal, then return here and click Refresh.")
        elif state == "missing_powertop":
            self.deep_hint.setText("Install `powertop`, then return here and click Refresh.")

    def refresh(self):
        self.btn_refresh.setEnabled(False)
        self._sync_deep_status()
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
        ready, msg = deep_sample_ready()
        if not ready:
            self._sync_deep_status()
            self._set_wakeup_text("Deep analysis unavailable", msg, "orange")
            return
        self.btn_deep.setEnabled(False)
        self._set_wakeup_text("Sampling…", wakeups_hint_deep(), "orange")
        w = Worker(lambda: sample_wakeups_powertop_slow(timeout_s=25))
        w.signals.finished.connect(self._deep_done)
        self.pool.start(w)

    def _deep_done(self, result):
        self._sync_deep_status()
        if isinstance(result, (int, float)):
            wps = float(result)
            self._set_wakeup_text(f"{wps:,.0f} wakeups/s", "powertop deep sample", "orange")
        else:
            ready, msg = deep_sample_ready()
            detail = msg if not ready else "powertop sample failed or produced no parsable wakeup data"
            self._set_wakeup_text("Deep sample failed", detail, "orange")

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
