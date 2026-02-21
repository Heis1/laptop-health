from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStyle

from ui_v2.qtworker import QtWorker
from ui_v2.services.network_metrics import sample_network, NetworkSnapshot
from ui_v2.services.speedtest import run_speedtest, SpeedTestResult


def _fmt_mbps(v: float | None) -> str:
    if v is None:
        return "—"
    if v < 10:
        return f"{v:.1f}"
    return f"{v:.0f}"


def _accent_for_ping(ping_ms: float | None) -> tuple[str, str]:
    if ping_ms is None:
        return ("blue", "IDLE")
    if ping_ms <= 35:
        return ("green", "GOOD")
    if ping_ms <= 80:
        return ("orange", "DEGRADED")
    return ("red", "ISSUE")


def _accent_for_speed(down_mbps: float | None) -> tuple[str, str]:
    if down_mbps is None:
        return ("red", "ISSUE")
    if down_mbps >= 100:
        return ("green", "EXCELLENT")
    if down_mbps >= 40:
        return ("blue", "GOOD")
    if down_mbps >= 15:
        return ("orange", "SLOW")
    return ("red", "ISSUE")


def _set_font(label: QLabel, size: int, bold: bool = True) -> None:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    label.setFont(f)


def _pill_style(accent: str) -> str:
    base = "padding: 5px 12px; border-radius: 999px; color: rgba(255,255,255,0.96);"
    if accent == "green":
        return base + " background: rgba(34,197,94,0.22); border: 1px solid rgba(34,197,94,0.70);"
    if accent == "orange":
        return base + " background: rgba(245,158,11,0.22); border: 1px solid rgba(245,158,11,0.70);"
    if accent == "red":
        return base + " background: rgba(239,68,68,0.22); border: 1px solid rgba(239,68,68,0.70);"
    return base + " background: rgba(59,130,246,0.22); border: 1px solid rgba(59,130,246,0.70);"


class NetworkPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.history: deque[SpeedTestResult] = deque(maxlen=8)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # =========================
        # Live Network (BIG + CENTER)
        # =========================
        self.live = QFrame()
        self.live.setObjectName("Card")
        self.live.setProperty("accent", "blue")

        lv = QVBoxLayout(self.live)
        lv.setContentsMargins(18, 16, 18, 16)
        lv.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveNetIcon).pixmap(18, 18))
        hdr.addWidget(ico)

        title = QLabel("Live Network")
        title.setObjectName("CardTitle")
        _set_font(title, 14, True)
        hdr.addWidget(title)
        hdr.addStretch(1)

        self.live_pill = QLabel("IDLE")
        _set_font(self.live_pill, 11, True)
        self.live_pill.setStyleSheet(_pill_style("blue"))
        hdr.addWidget(self.live_pill)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("ActionButton")
        self.btn_refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_refresh.clicked.connect(self._refresh_live)
        self.btn_refresh.setMinimumHeight(34)
        hdr.addWidget(self.btn_refresh)

        lv.addLayout(hdr)

        hero = QHBoxLayout()
        hero.addStretch(1)

        self.rx = QLabel("— Mbps ↓")
        _set_font(self.rx, 44, True)
        self.rx.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.rx.setStyleSheet("color: rgba(255,255,255,0.98);")
        hero.addWidget(self.rx)

        self.tx = QLabel("— Mbps ↑")
        _set_font(self.tx, 44, True)
        self.tx.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.tx.setStyleSheet("color: rgba(255,255,255,0.98);")
        hero.addWidget(self.tx)

        hero.addStretch(1)
        lv.addLayout(hero)

        self.live_sub = QLabel("—")
        _set_font(self.live_sub, 14, True)
        self.live_sub.setAlignment(Qt.AlignHCenter)
        self.live_sub.setStyleSheet("color: rgba(255,255,255,0.84);")
        lv.addWidget(self.live_sub)

        self.live_meta = QLabel("—")
        _set_font(self.live_meta, 12, False)
        self.live_meta.setAlignment(Qt.AlignHCenter)
        self.live_meta.setWordWrap(True)
        self.live_meta.setStyleSheet("color: rgba(255,255,255,0.70);")
        lv.addWidget(self.live_meta)

        # =========================
        # Speed Test (MATCH LIVE STYLE)
        # =========================
        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card.setProperty("accent", "blue")

        v = QVBoxLayout(self.card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        hdr2 = QHBoxLayout()
        ico2 = QLabel()
        ico2.setPixmap(self.style().standardIcon(QStyle.SP_BrowserReload).pixmap(18, 18))
        hdr2.addWidget(ico2)

        title2 = QLabel("Speed Test")
        title2.setObjectName("CardTitle")
        _set_font(title2, 14, True)
        hdr2.addWidget(title2)
        hdr2.addStretch(1)

        self.speed_pill = QLabel("IDLE")
        _set_font(self.speed_pill, 11, True)
        self.speed_pill.setStyleSheet(_pill_style("blue"))
        hdr2.addWidget(self.speed_pill)

        self.btn = QPushButton("Run speed test")
        self.btn.setObjectName("ActionButton")
        self.btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn.clicked.connect(self._run_speedtest)
        self.btn.setMinimumHeight(34)
        hdr2.addWidget(self.btn)

        v.addLayout(hdr2)

        # Hero row like Live Network: big down + up with arrows/units
        hero2 = QHBoxLayout()
        hero2.addStretch(1)

        self.down = QLabel("— Mbps ↓")
        _set_font(self.down, 44, True)
        self.down.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.down.setStyleSheet("color: rgba(255,255,255,0.98);")
        hero2.addWidget(self.down)

        self.up = QLabel("— Mbps ↑")
        _set_font(self.up, 44, True)
        self.up.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.up.setStyleSheet("color: rgba(255,255,255,0.98);")
        hero2.addWidget(self.up)

        hero2.addStretch(1)
        v.addLayout(hero2)

        # Sub line: ping + server/isp go below, not competing with hero numbers
        self.ping_line = QLabel("—")
        _set_font(self.ping_line, 14, True)
        self.ping_line.setAlignment(Qt.AlignHCenter)
        self.ping_line.setStyleSheet("color: rgba(255,255,255,0.84);")
        v.addWidget(self.ping_line)

        self.meta = QLabel("—")
        _set_font(self.meta, 12, False)
        self.meta.setAlignment(Qt.AlignHCenter)
        self.meta.setWordWrap(True)
        self.meta.setStyleSheet("color: rgba(255,255,255,0.70);")
        v.addWidget(self.meta)

        self.hist = QLabel("No results yet.")
        _set_font(self.hist, 12, False)
        self.hist.setAlignment(Qt.AlignHCenter)
        self.hist.setWordWrap(True)
        self.hist.setStyleSheet("color: rgba(255,255,255,0.65);")
        v.addWidget(self.hist)

        grid.addWidget(self.live, 0, 0)
        grid.addWidget(self.card, 1, 0)

        self._refresh_live()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._refresh_live)
        self.timer.start()

    def _restyle(self, w: QFrame):
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()

    # -------- Live Network --------
    def _refresh_live(self):
        w = QtWorker(lambda: sample_network(0.4))
        w.signals.result.connect(self._apply_live)
        w.signals.error.connect(self._apply_live_error)
        self.pool.start(w)

    def _apply_live_error(self, msg: str):
        self.live.setProperty("accent", "red")
        self.live_pill.setText("ISSUE")
        self.live_pill.setStyleSheet(_pill_style("red"))
        self._restyle(self.live)

        self.rx.setText("— Mbps ↓")
        self.tx.setText("— Mbps ↑")
        self.live_sub.setText(msg or "Network error")
        self.live_meta.setText("—")

    def _apply_live(self, r):
        if not isinstance(r, NetworkSnapshot) or r.error:
            self._apply_live_error((r.error if isinstance(r, NetworkSnapshot) else None) or "Network error")
            return

        accent, pill = _accent_for_ping(r.latency_ms)
        self.live.setProperty("accent", accent)
        self.live_pill.setText(pill)
        self.live_pill.setStyleSheet(_pill_style(accent))
        self._restyle(self.live)

        self.rx.setText(f"{_fmt_mbps(r.rx_mbps)} Mbps ↓")
        self.tx.setText(f"{_fmt_mbps(r.tx_mbps)} Mbps ↑")

        lat = "—" if r.latency_ms is None else f"{r.latency_ms:.0f} ms ping"
        ip = r.ip or "—"
        self.live_sub.setText(f"{lat} • IP {ip}")

        bits = []
        if r.iface: bits.append(r.iface)
        if r.ssid: bits.append(f"Wi-Fi: {r.ssid}")
        if r.signal is not None: bits.append(f"Signal {r.signal}%")
        if r.rate: bits.append(f"Link {r.rate}")
        self.live_meta.setText(" • ".join(bits) if bits else "—")

    # -------- Speed Test --------
    def _run_speedtest(self):
        self.btn.setEnabled(False)
        self.btn.setText("Running…")
        self.card.setProperty("accent", "orange")
        self.speed_pill.setText("RUNNING")
        self.speed_pill.setStyleSheet(_pill_style("orange"))
        self._restyle(self.card)

        w = QtWorker(run_speedtest)
        w.signals.result.connect(self._apply_speed)
        w.signals.error.connect(lambda m: self._apply_speed(SpeedTestResult(False, None, None, None, None, None, time.time(), error=m)))
        w.signals.finished.connect(self._speed_done)
        self.pool.start(w)

    def _speed_done(self):
        self.btn.setEnabled(True)
        if self.btn.text() == "Running…":
            self.btn.setText("Run speed test")

    def _apply_speed(self, r):
        if not isinstance(r, SpeedTestResult) or not r.ok:
            self.card.setProperty("accent", "red")
            self.speed_pill.setText("ISSUE")
            self.speed_pill.setStyleSheet(_pill_style("red"))
            self._restyle(self.card)

            self.meta.setText(getattr(r, "error", None) or "Speed test failed.")
            # keep last-known Down on failure (do not blank)
            # keep last-known Up on failure (do not blank)
            # keep last-known Ping on failure (do not blank)
            return

        self.history.appendleft(r)

        accent, pill = _accent_for_speed(r.down_mbps)
        self.card.setProperty("accent", accent)
        self.speed_pill.setText(pill)
        self.speed_pill.setStyleSheet(_pill_style(accent))
        self._restyle(self.card)

        self.down.setText(f"{_fmt_mbps(r.down_mbps)} Mbps ↓")
        self.up.setText(f"{_fmt_mbps(r.up_mbps)} Mbps ↑")

        ping = "—" if r.ping_ms is None else f"{r.ping_ms:.0f} ms ping"
        self.ping_line.setText(ping)

        bits = []
        if r.server: bits.append(f"Server: {r.server}")
        if r.isp: bits.append(f"ISP: {r.isp}")
        self.meta.setText(" • ".join(bits) if bits else "—")

        lines = []
        for x in list(self.history)[:4]:
            ts = time.strftime("%H:%M", time.localtime(x.when))
            lines.append(f"{ts} ↓{x.down_mbps:.0f} ↑{x.up_mbps:.0f} p{x.ping_ms:.0f}")
        self.hist.setText("Recent:  " + "   |   ".join(lines))
