from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStyle, QListWidget, QListWidgetItem, QComboBox, QLineEdit

from ui_v2.qtworker import QtWorker
from ui_v2.services.network_discovery import discover_network_devices, DiscoveryResult, DiscoveredDevice
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


def _device_text(dev: DiscoveredDevice) -> str:
    lines = [f"IP: {dev.ip}"]
    if dev.hostname:
        lines.append(f"Host: {dev.hostname}")
    if dev.mac:
        mac_text = f"MAC: {dev.mac}"
        if dev.vendor:
            mac_text += f" ({dev.vendor})"
        lines.append(mac_text)
    if dev.os_name:
        lines.append(f"OS: {dev.os_name}")
    return "\n".join(lines)


class NetworkPage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.history: deque[SpeedTestResult] = deque(maxlen=8)
        self._discovery_mode = "quiet"
        self._last_rx = "— Mbps ↓"
        self._last_tx = "— Mbps ↑"
        self._last_live_sub = "—"
        self._last_live_meta = "—"
        self._scan_started_at = 0.0
        self._scan_feedback_step = 0
        self._scan_target_text = ""

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

        # =========================
        # Device Discovery
        # =========================
        self.discovery = QFrame()
        self.discovery.setObjectName("Card")
        self.discovery.setProperty("accent", "blue")

        dv = QVBoxLayout(self.discovery)
        dv.setContentsMargins(18, 16, 18, 16)
        dv.setSpacing(10)

        hdr3 = QHBoxLayout()
        ico3 = QLabel()
        ico3.setPixmap(self.style().standardIcon(QStyle.SP_FileDialogContentsView).pixmap(18, 18))
        hdr3.addWidget(ico3)

        title3 = QLabel("Device Discovery")
        title3.setObjectName("CardTitle")
        _set_font(title3, 14, True)
        hdr3.addWidget(title3)
        hdr3.addStretch(1)

        self.discovery_pill = QLabel("IDLE")
        _set_font(self.discovery_pill, 11, True)
        self.discovery_pill.setStyleSheet(_pill_style("blue"))
        hdr3.addWidget(self.discovery_pill)

        self.scan_mode = QComboBox()
        self.scan_mode.setObjectName("ActionSelect")
        self.scan_mode.addItem("Quiet")
        self.scan_mode.addItem("Noisy")
        self.scan_mode.currentTextChanged.connect(self._on_scan_mode_changed)
        self.scan_mode.setMinimumHeight(34)
        hdr3.addWidget(self.scan_mode)

        self.btn_scan = QPushButton("Scan devices")
        self.btn_scan.setObjectName("ActionButton")
        self.btn_scan.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_scan.clicked.connect(self._scan_devices)
        self.btn_scan.setMinimumHeight(34)
        hdr3.addWidget(self.btn_scan)

        dv.addLayout(hdr3)

        self.discovery_sub = QLabel("Discover devices on the active subnet")
        _set_font(self.discovery_sub, 14, True)
        self.discovery_sub.setWordWrap(True)
        self.discovery_sub.setStyleSheet("color: rgba(255,255,255,0.84);")
        dv.addWidget(self.discovery_sub)

        opts = QHBoxLayout()
        opts.setSpacing(10)

        self.target_input = QLineEdit()
        self.target_input.setObjectName("ActionInput")
        self.target_input.setPlaceholderText("Target range, e.g. 192.168.1.0/24 or 192.168.1.10-40")
        self.target_input.setMinimumHeight(36)
        opts.addWidget(self.target_input, 2)

        self.options_input = QLineEdit()
        self.options_input.setObjectName("ActionInput")
        self.options_input.setPlaceholderText("Extra nmap options for noisy scans, e.g. -sV --script smb-os-discovery")
        self.options_input.setMinimumHeight(36)
        opts.addWidget(self.options_input, 3)

        dv.addLayout(opts)

        self.discovery_meta = QLabel("—")
        _set_font(self.discovery_meta, 12, False)
        self.discovery_meta.setWordWrap(True)
        self.discovery_meta.setStyleSheet("color: rgba(255,255,255,0.70);")
        dv.addWidget(self.discovery_meta)

        self.device_list = QListWidget()
        self.device_list.setStyleSheet(
            "QListWidget {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 12px;"
            "padding: 6px;"
            "color: rgba(255,255,255,0.92);"
            "}"
            "QListWidget::item { padding: 10px 12px; border-radius: 8px; }"
            "QListWidget::item:selected { background: rgba(96,165,250,0.18); }"
        )
        dv.addWidget(self.device_list, 1)

        grid.addWidget(self.live, 0, 0)
        grid.addWidget(self.card, 1, 0)
        grid.addWidget(self.discovery, 2, 0)

        self.scan_feedback_timer = QTimer(self)
        self.scan_feedback_timer.setInterval(350)
        self.scan_feedback_timer.timeout.connect(self._tick_scan_feedback)

        self._refresh_live()
        self._scan_devices()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh_live)
        self.timer.start()

    def _restyle(self, w: QFrame):
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()

    # -------- Live Network --------
    def _refresh_live(self):
        w = QtWorker(lambda: sample_network(0.75))
        w.signals.result.connect(self._apply_live)
        w.signals.error.connect(self._apply_live_error)
        self.pool.start(w)

    def _apply_live_error(self, msg: str):
        self.live.setProperty("accent", "red")
        self.live_pill.setText("ISSUE")
        self.live_pill.setStyleSheet(_pill_style("red"))
        self._restyle(self.live)

        self.live_sub.setText(msg or "Network error")
        self.live_meta.setText(self._last_live_meta)

    def _apply_live(self, r):
        if not isinstance(r, NetworkSnapshot) or r.error:
            self._apply_live_error((r.error if isinstance(r, NetworkSnapshot) else None) or "Network error")
            return

        accent, pill = _accent_for_ping(r.latency_ms)
        self.live.setProperty("accent", accent)
        self.live_pill.setText(pill)
        self.live_pill.setStyleSheet(_pill_style(accent))
        self._restyle(self.live)

        if r.rx_mbps is not None:
            self._last_rx = f"{_fmt_mbps(r.rx_mbps)} Mbps ↓"
        if r.tx_mbps is not None:
            self._last_tx = f"{_fmt_mbps(r.tx_mbps)} Mbps ↑"
        self.rx.setText(self._last_rx)
        self.tx.setText(self._last_tx)

        lat = "—" if r.latency_ms is None else f"{r.latency_ms:.0f} ms ping"
        ip = r.ip or "—"
        self._last_live_sub = f"{lat} • IP {ip}"
        self.live_sub.setText(self._last_live_sub)

        bits = []
        if r.iface: bits.append(r.iface)
        if r.ssid: bits.append(f"Wi-Fi: {r.ssid}")
        if r.signal is not None: bits.append(f"Signal {r.signal}%")
        if r.rate: bits.append(f"Link {r.rate}")
        self._last_live_meta = " • ".join(bits) if bits else "—"
        self.live_meta.setText(self._last_live_meta)

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

    # -------- Device Discovery --------
    def _scan_devices(self):
        target_text = self.target_input.text().strip()
        extra_options = self.options_input.text().strip()
        self.btn_scan.setEnabled(False)
        self.scan_mode.setEnabled(False)
        self.target_input.setEnabled(False)
        self.options_input.setEnabled(False)
        self.btn_scan.setText("Scanning…")
        self._scan_started_at = time.monotonic()
        self._scan_feedback_step = 0
        self._scan_target_text = target_text or "active subnet"
        self.discovery.setProperty("accent", "blue")
        self.discovery_pill.setText("SCANNING")
        self.discovery_pill.setStyleSheet(_pill_style("blue"))
        self._restyle(self.discovery)
        self._tick_scan_feedback()
        self.scan_feedback_timer.start()

        w = QtWorker(
            lambda: discover_network_devices(
                self._discovery_mode,
                target_override=target_text or None,
                extra_options=extra_options or None,
            )
        )
        w.signals.result.connect(self._apply_discovery)
        w.signals.error.connect(self._apply_discovery_error)
        w.signals.finished.connect(self._scan_done)
        self.pool.start(w)

    def _scan_done(self):
        self.scan_feedback_timer.stop()
        self.btn_scan.setEnabled(True)
        self.scan_mode.setEnabled(True)
        self.target_input.setEnabled(True)
        self.options_input.setEnabled(True)
        if self.btn_scan.text() == "Scanning…":
            self.btn_scan.setText("Scan devices")

    def _on_scan_mode_changed(self, text: str):
        self._discovery_mode = "noisy" if text.strip().lower() == "noisy" else "quiet"

    def _apply_discovery_error(self, msg: str):
        self.discovery.setProperty("accent", "red")
        self.discovery_pill.setText("ISSUE")
        self.discovery_pill.setStyleSheet(_pill_style("red"))
        self._restyle(self.discovery)
        self.discovery_sub.setText(msg or "Network discovery failed")
        self.discovery_meta.setText("—")
        self.device_list.clear()

    def _apply_discovery(self, result):
        if not isinstance(result, DiscoveryResult):
            self._apply_discovery_error("Network discovery failed")
            return

        if result.error:
            accent = "orange" if "nmap is not installed" in result.error.lower() else "red"
            pill = "MISSING" if accent == "orange" else "ISSUE"
            self.discovery.setProperty("accent", accent)
            self.discovery_pill.setText(pill)
            self.discovery_pill.setStyleSheet(_pill_style(accent))
            self._restyle(self.discovery)
            self.discovery_sub.setText(result.error)
            self.discovery_meta.setText(f"Subnet: {result.target or '—'}")
            self.device_list.clear()
            return

        count = len(result.devices)
        accent = "green" if count > 0 else "blue"
        self.discovery.setProperty("accent", accent)
        self.discovery_pill.setText(f"{count} DEVICES")
        self.discovery_pill.setStyleSheet(_pill_style(accent))
        self._restyle(self.discovery)

        mode_label = "Quiet" if result.mode == "quiet" else "Noisy"
        self.discovery_sub.setText(f"Discovered {count} device{'s' if count != 1 else ''} with {mode_label} scan")
        meta = f"Subnet: {result.target or '—'} • Mode: {mode_label}"
        if result.note:
            meta += f" • {result.note}"
        self.discovery_meta.setText(meta)
        self.device_list.clear()
        for dev in result.devices:
            self.device_list.addItem(QListWidgetItem(_device_text(dev)))

    def _tick_scan_feedback(self):
        dots = "." * ((self._scan_feedback_step % 3) + 1)
        elapsed = 0
        if self._scan_started_at > 0:
            elapsed = max(0, int(time.monotonic() - self._scan_started_at))
        mode_label = "Quiet" if self._discovery_mode == "quiet" else "Noisy"
        self.discovery_sub.setText(f"{mode_label} scan in progress{dots}")
        self.discovery_meta.setText(f"Elapsed: {elapsed}s • Target: {self._scan_target_text}")
        self._scan_feedback_step += 1
