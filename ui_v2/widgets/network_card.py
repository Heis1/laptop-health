from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout

from ui_v2.qtworker import QtWorker
from ui_v2.services.network_metrics import sample_network, NetworkSnapshot


class NetworkCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "blue")

        self.pool = QThreadPool()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveNetIcon).pixmap(16, 16))
        hdr.addWidget(ico)

        t = QLabel("Network")
        t.setObjectName("CardTitle")
        hdr.addWidget(t)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.big = QLabel("—"); self.big.setObjectName("CardHuge")
        self.sub = QLabel("—"); self.sub.setObjectName("CardSub"); self.sub.setWordWrap(True)
        self.meta = QLabel("—"); self.meta.setObjectName("CardSub"); self.meta.setWordWrap(True)
        outer.addWidget(self.big)
        outer.addWidget(self.sub)
        outer.addWidget(self.meta)

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    # Dashboard compatibility
    def set_network(self, down_mbps: float | None, latency_ms: float | None) -> None:
        # Only use if dashboard calls it; we keep it mild and never force red unless latency is real.
        accent = "blue"
        if latency_ms is not None:
            if latency_ms > 80: accent = "red"
            elif latency_ms > 35: accent = "orange"
            else: accent = "green"
        self.setProperty("accent", accent)
        self._restyle()

        d = "—" if down_mbps is None else f"{down_mbps:.0f} Mbps ↓"
        l = "—" if latency_ms is None else f"{latency_ms:.0f} ms ping"
        self.big.setText(d)
        self.sub.setText(l)

    def _refresh(self):
        w = QtWorker(lambda: sample_network(0.4))
        w.signals.result.connect(self._apply)
        w.signals.error.connect(self._apply_error)
        self.pool.start(w)

    def _apply_error(self, msg: str):
        self.setProperty("accent", "red")
        self._restyle()
        self.big.setText("—")
        self.sub.setText(msg or "Network error")
        self.meta.setText("—")

    def _apply(self, r):
        if not isinstance(r, NetworkSnapshot) or r.error:
            self._apply_error((r.error if isinstance(r, NetworkSnapshot) else None) or "Network error")
            return

        accent = "green"
        if r.latency_ms is not None:
            if r.latency_ms > 80: accent = "red"
            elif r.latency_ms > 35: accent = "orange"
        self.setProperty("accent", accent)
        self._restyle()

        down = "—" if r.rx_mbps is None else f"{r.rx_mbps:.0f} Mbps ↓"
        up = "—" if r.tx_mbps is None else f"{r.tx_mbps:.0f} Mbps ↑"
        self.big.setText(f"{down}   {up}")

        lat = "—" if r.latency_ms is None else f"{r.latency_ms:.0f} ms ping"
        ip = r.ip or "—"
        self.sub.setText(f"{lat} • IP {ip}")

        bits = []
        if r.iface: bits.append(r.iface)
        if r.ssid: bits.append(f"Wi-Fi: {r.ssid}")
        if r.signal is not None: bits.append(f"Signal {r.signal}%")
        if r.rate: bits.append(f"Link {r.rate}")
        self.meta.setText(" • ".join(bits) if bits else "—")

    def _restyle(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
