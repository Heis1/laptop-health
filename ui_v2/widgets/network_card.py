from __future__ import annotations
from PySide6.QtGui import QFont

from PySide6.QtCore import QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QPushButton

from ui_v2.qtworker import QtWorker
from ui_v2.services.network_metrics import sample_network, NetworkSnapshot, active_ifaces
from ui_v2.widgets.cards import apply_responsive_card_fonts


def _fmt_mbps(v: float | None) -> str | None:
    if v is None:
        return None
    try:
        v = float(v)
    except Exception:
        return None
    if v < 10:
        return f"{v:.1f}"
    return f"{v:.0f}"


class NetworkCard(QFrame):
    iface_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "blue")
        self.setProperty("_responsive_width_divisor", 2)

        self.pool = QThreadPool()

        # last-known values so transient None/errors don't blank the tile
        self._last_down: str = "— Mbps ↓"
        self._last_up: str = "— Mbps ↑"
        self._last_ip: str = "—"
        self._last_ping: str = "—"
        self._ifaces: list[str] = []
        self._selected_iface: str | None = None
        self._refresh_in_flight = False

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
        self.iface_badge = QPushButton("Auto")
        self.iface_badge.setObjectName("Badge")
        self.iface_badge.setCursor(Qt.PointingHandCursor)
        self.iface_badge.clicked.connect(self._cycle_iface)
        hdr.addWidget(self.iface_badge)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.big = QLabel("—")


        f = QFont()


        f.setStyleHint(QFont.Monospace)


        f.setFixedPitch(True)


        

        self.big.setFont(f)

        self.big.setStyleSheet("")
        self.big.setObjectName("CardHuge")
        self.big.setWordWrap(True)

        self.sub = QLabel("—")
        self.sub.setStyleSheet("")
        self.sub.setObjectName("CardSub")
        self.sub.setWordWrap(True)

        self.meta = QLabel("—")
        self.meta.setObjectName("CardSub")
        self.meta.setWordWrap(True)

        outer.addWidget(self.big)
        outer.addWidget(self.sub)
        outer.addWidget(self.meta)

        # paint with defaults immediately
        self._render()
        apply_responsive_card_fonts(self)

        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)

    # Dashboard compatibility (if dashboard calls it)
    def set_network(self, down_mbps: float | None, latency_ms: float | None) -> None:
        d = _fmt_mbps(down_mbps)
        if d is not None:
            self._last_down = f"{d} Mbps ↓"

        if latency_ms is not None:
            self._last_ping = f"{latency_ms:.0f} ms ping"

        # keep last_up/ip
        self._render()

        accent = "blue"
        if latency_ms is not None:
            if latency_ms > 80:
                accent = "red"
            elif latency_ms > 35:
                accent = "orange"
            else:
                accent = "green"
        self.setProperty("accent", accent)
        self._restyle()

    def _render(self):
        self.big.setText(f"{self._last_down}   {self._last_up}")
        self.sub.setText(f"{self._last_ping} • IP {self._last_ip}")

    def _refresh(self):
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        self._ifaces = active_ifaces()
        if self._selected_iface not in self._ifaces:
            self._selected_iface = self._ifaces[0] if self._ifaces else None
        self._sync_iface_badge()
        w = QtWorker(lambda: sample_network(0.75, iface_override=self._selected_iface))
        w.signals.result.connect(self._apply)
        w.signals.error.connect(self._apply_error)
        w.signals.finished.connect(lambda: setattr(self, "_refresh_in_flight", False))
        self.pool.start(w)

    def _cycle_iface(self):
        if len(self._ifaces) <= 1:
            return
        if self._selected_iface not in self._ifaces:
            self._selected_iface = self._ifaces[0]
        else:
            idx = self._ifaces.index(self._selected_iface)
            self._selected_iface = self._ifaces[(idx + 1) % len(self._ifaces)]
        self.iface_changed.emit(self._selected_iface or "")
        self._sync_iface_badge()
        self._refresh()

    def _sync_iface_badge(self):
        if not self._ifaces:
            self.iface_badge.setText("Auto")
            self.iface_badge.setEnabled(False)
            return
        current = self._selected_iface or self._ifaces[0]
        self.iface_badge.setText(current)
        self.iface_badge.setEnabled(len(self._ifaces) > 1)
        tip = "Click to switch active network interface" if len(self._ifaces) > 1 else "Only one active network interface"
        self.iface_badge.setToolTip(tip)

    def _apply_error(self, msg: str):
        # IMPORTANT: do NOT blank/overwrite displayed values on transient errors
        self.setProperty("accent", "red")
        self._restyle()
        # Put error in meta only (optional)
        if msg:
            self.meta.setText(msg)

    def _apply(self, r):
        if not isinstance(r, NetworkSnapshot) or r.error:
            self._apply_error((r.error if isinstance(r, NetworkSnapshot) else None) or "Network error")
            return

        # Accent based on ping
        accent = "green"
        if r.latency_ms is not None:
            if r.latency_ms > 80:
                accent = "red"
            elif r.latency_ms > 35:
                accent = "orange"
        self.setProperty("accent", accent)
        self._restyle()

        # Update last-known values ONLY when present
        d = _fmt_mbps(r.rx_mbps)
        if d is not None:
            self._last_down = f"{d} Mbps ↓"

        u = _fmt_mbps(r.tx_mbps)
        if u is not None:
            self._last_up = f"{u} Mbps ↑"

        if r.ip:
            self._last_ip = r.ip

        if r.latency_ms is not None:
            self._last_ping = f"{r.latency_ms:.0f} ms ping"

        self._render()

        bits = []
        if r.iface:
            bits.append(r.iface)
        if r.ssid:
            bits.append(f"Wi-Fi: {r.ssid}")
        if r.signal is not None:
            bits.append(f"Signal {r.signal}%")
        if r.rate:
            bits.append(f"Link {r.rate}")
        self.meta.setText(" • ".join(bits) if bits else self.meta.text())

    def _restyle(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
