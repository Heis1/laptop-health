from __future__ import annotations

import time
import json
from collections import deque

from PySide6.QtCore import QPoint, QThreadPool, QTimer, Qt
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QWidget, QGridLayout, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStyle, QComboBox, QLineEdit, QSizePolicy, QDialog, QFileDialog, QScrollArea

from ui_v2.qtworker import QtWorker
from ui_v2.theme import current_theme_mode
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
    light = current_theme_mode() == "light"
    text = "rgba(27,36,48,0.96)" if light else "rgba(255,255,255,0.96)"
    base = f"padding: 5px 12px; border-radius: 999px; color: {text};"
    if accent == "green":
        return base + (" background: rgba(34,197,94,0.16); border: 1px solid rgba(34,197,94,0.42);" if light else " background: rgba(34,197,94,0.22); border: 1px solid rgba(34,197,94,0.70);")
    if accent == "orange":
        return base + (" background: rgba(245,158,11,0.16); border: 1px solid rgba(245,158,11,0.40);" if light else " background: rgba(245,158,11,0.22); border: 1px solid rgba(245,158,11,0.70);")
    if accent == "red":
        return base + (" background: rgba(239,68,68,0.14); border: 1px solid rgba(239,68,68,0.40);" if light else " background: rgba(239,68,68,0.22); border: 1px solid rgba(239,68,68,0.70);")
    return base + (" background: rgba(59,130,246,0.14); border: 1px solid rgba(59,130,246,0.38);" if light else " background: rgba(59,130,246,0.22); border: 1px solid rgba(59,130,246,0.70);")


def _text_style(role: str) -> str:
    light = current_theme_mode() == "light"
    if role == "hero":
        return "color: rgba(27,36,48,0.98);" if light else "color: rgba(255,255,255,0.98);"
    if role == "strong":
        return "color: rgba(27,36,48,0.84);" if light else "color: rgba(255,255,255,0.84);"
    if role == "body":
        return "color: rgba(27,36,48,0.92);" if light else "color: rgba(232,240,255,0.92);"
    if role == "muted":
        return "color: rgba(103,119,139,0.94);" if light else "color: rgba(255,255,255,0.70);"
    if role == "service":
        return (
            "color: rgba(27,36,48,0.96); background: rgba(27,36,48,0.04); border-radius: 10px; padding: 10px 12px; line-height: 1.35em;"
            if light else
            "color: rgba(244,248,255,0.96); background: rgba(255,255,255,0.06); border-radius: 10px; padding: 10px 12px; line-height: 1.35em;"
        )
    if role == "service_idle":
        return (
            "color: rgba(86,101,118,0.96); background: rgba(27,36,48,0.04); border-radius: 10px; padding: 10px 12px; line-height: 1.35em;"
            if light else
            "color: rgba(187,202,222,0.96); background: rgba(255,255,255,0.05); border-radius: 10px; padding: 10px 12px; line-height: 1.35em;"
        )
    return ""


def _scroll_style() -> str:
    if current_theme_mode() == "light":
        return (
            "QScrollArea#DiscoveryScroll {"
            "background: rgba(27,36,48,0.03);"
            "border: 1px solid rgba(27,36,48,0.10);"
            "border-radius: 12px;"
            "}"
            "QWidget#DiscoveryScrollViewport {"
            "background: transparent;"
            "}"
        )
    return (
        "QScrollArea#DiscoveryScroll {"
        "background: rgba(255,255,255,0.02);"
        "border: 1px solid rgba(255,255,255,0.08);"
        "border-radius: 12px;"
        "}"
        "QWidget#DiscoveryScrollViewport {"
        "background: transparent;"
        "}"
    )


def _dialog_style() -> str:
    if current_theme_mode() == "light":
        return """
            QDialog {
                background: rgba(243, 239, 231, 0.84);
            }
            QFrame#Card {
                background: rgba(255, 250, 242, 0.98);
                border-radius: 18px;
            }
            QWidget#DiscoveryResultsHost {
                background: transparent;
            }
            """
    return """
            QDialog {
                background: rgba(3, 7, 18, 0.84);
            }
            QFrame#Card {
                background: rgba(10, 14, 22, 0.98);
                border-radius: 18px;
            }
            QWidget#DiscoveryResultsHost {
                background: transparent;
            }
            """


def _device_payload(dev: DiscoveredDevice) -> dict[str, object]:
    payload: dict[str, object] = {"ip": dev.ip}
    if dev.hostname:
        payload["hostname"] = dev.hostname
    if dev.mac:
        payload["mac"] = dev.mac
    if dev.vendor:
        payload["vendor"] = dev.vendor
    if dev.os_name:
        payload["os_name"] = dev.os_name
    if dev.services_summary:
        payload["services"] = dev.services_summary
    if dev.open_ports:
        payload["open_ports"] = dev.open_ports
    return payload


def _detail_row(label_text: str, value_text: str) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    label = QLabel(label_text)
    label.setObjectName("Badge")
    label.setMinimumWidth(92)
    layout.addWidget(label, 0)

    value = QLabel(value_text or "—")
    value.setObjectName("CardSub")
    value.setStyleSheet(_text_style("body"))
    value.setWordWrap(True)
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(value, 1)
    return row


def _port_line(port: dict[str, str]) -> str:
    left = f"{port.get('port', '—')}/{port.get('protocol') or 'tcp'}"
    detail_parts = [
        port.get("service", ""),
        port.get("product", ""),
        port.get("version", ""),
    ]
    detail = " ".join(part for part in detail_parts if part).strip()
    reason = port.get("reason", "").strip()
    text = left
    if detail:
        text += f"  {detail}"
    if reason:
        text += f"  [{reason}]"
    return text


NOISY_PRESETS = {
    "Default noisy": "",
    "Service focus": "-sV --version-light",
    "SMB profile": "--script smb-os-discovery,smb-protocols",
    "Web profile": "--script http-title,http-server-header",
    "Safe vuln hints": "--script vuln",
}


class DeviceRow(QFrame):
    def __init__(self, dev: DiscoveredDevice, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "blue" if dev.services_summary else "green")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        title = QLabel(dev.hostname or dev.ip)
        title.setObjectName("CardTitle")
        _set_font(title, 13, True)
        top.addWidget(title)

        if dev.hostname and dev.hostname != dev.ip:
            ip_badge = QLabel(dev.ip)
            ip_badge.setObjectName("Badge")
            top.addWidget(ip_badge)

        top.addStretch(1)
        outer.addLayout(top)

        details: list[str] = []
        if dev.mac:
            mac_text = dev.mac
            if dev.vendor:
                mac_text += f" ({dev.vendor})"
            details.append(mac_text)
        if dev.os_name:
            details.append(dev.os_name)

        meta = QLabel(" • ".join(details) if details else "No device metadata")
        meta.setObjectName("CardSub")
        meta.setStyleSheet(_text_style("body"))
        meta.setWordWrap(True)
        outer.addWidget(meta)

        services = QLabel(dev.services_summary or "Host discovery only")
        services.setObjectName("CardSub")
        services.setWordWrap(True)
        services.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        services.setTextFormat(Qt.PlainText)
        services.setStyleSheet(_text_style("service" if dev.services_summary else "service_idle"))
        outer.addWidget(services)

        data_title = QLabel("Structured Details")
        data_title.setObjectName("CardTitle")
        outer.addWidget(data_title)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_card.setProperty("accent", "slate")
        details_l = QVBoxLayout(details_card)
        details_l.setContentsMargins(12, 10, 12, 10)
        details_l.setSpacing(8)

        details_l.addWidget(_detail_row("Primary IP", dev.ip))
        if dev.hostname:
            details_l.addWidget(_detail_row("Hostname", dev.hostname))
        if dev.mac:
            details_l.addWidget(_detail_row("MAC", dev.mac))
        if dev.vendor:
            details_l.addWidget(_detail_row("Vendor", dev.vendor))
        if dev.os_name:
            details_l.addWidget(_detail_row("OS hint", dev.os_name))
        details_l.addWidget(_detail_row("Discovery", "Noisy service scan" if dev.open_ports else "Host discovery only"))
        outer.addWidget(details_card)

        ports_title = QLabel("Open Ports & Services")
        ports_title.setObjectName("CardTitle")
        outer.addWidget(ports_title)

        ports_card = QFrame()
        ports_card.setObjectName("Card")
        ports_card.setProperty("accent", "purple" if dev.open_ports else "slate")
        ports_l = QVBoxLayout(ports_card)
        ports_l.setContentsMargins(12, 10, 12, 10)
        ports_l.setSpacing(6)

        if dev.open_ports:
            for port in dev.open_ports:
                line = QLabel(_port_line(port))
                line.setObjectName("CardSub")
                line.setWordWrap(True)
                line.setTextFormat(Qt.PlainText)
                line.setTextInteractionFlags(Qt.TextSelectableByMouse)
                line.setStyleSheet(_text_style("service"))
                ports_l.addWidget(line)
        else:
            idle = QLabel("No open ports captured for this host in the current scan.")
            idle.setObjectName("CardSub")
            idle.setWordWrap(True)
            idle.setStyleSheet(_text_style("service_idle"))
            ports_l.addWidget(idle)
        outer.addWidget(ports_card)
        outer.addStretch(0)


class DiscoveryResultsDialog(QDialog):
    def __init__(self, parent: QWidget, result: DiscoveryResult):
        super().__init__(parent)
        self._result = result
        self._drag_offset: QPoint | None = None
        self.setModal(True)
        self.resize(860, 640)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("Card")
        card.setProperty("accent", "blue")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        title = QLabel("Discovery Results")
        title.setObjectName("CardTitle")
        _set_font(title, 15, True)
        title_box.addWidget(title)

        mode_label = "Quiet" if result.mode == "quiet" else "Noisy"
        subtitle = QLabel(f"{len(result.devices)} device{'s' if len(result.devices) != 1 else ''} • {mode_label} scan • {result.target or '—'}")
        subtitle.setObjectName("CardSub")
        subtitle.setStyleSheet(_text_style("body"))
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        hdr.addLayout(title_box, 1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("ActionButton")
        close_btn.clicked.connect(self.accept)
        hdr.addWidget(close_btn)
        outer.addLayout(hdr)

        note = result.note or "Save these results as text or JSON for later review."
        note_lbl = QLabel(note)
        note_lbl.setObjectName("CardSub")
        note_lbl.setStyleSheet(_text_style("body"))
        note_lbl.setWordWrap(True)
        outer.addWidget(note_lbl)

        self.summary_card = QFrame()
        self.summary_card.setObjectName("Card")
        self.summary_card.setProperty("accent", "purple")
        summary_l = QVBoxLayout(self.summary_card)
        summary_l.setContentsMargins(14, 12, 14, 12)
        summary_l.setSpacing(8)

        summary_title = QLabel("Quick Summary")
        summary_title.setObjectName("CardTitle")
        summary_l.addWidget(summary_title)

        self.summary_text = QLabel(self._summary_lines())
        self.summary_text.setObjectName("CardSub")
        self.summary_text.setStyleSheet(_text_style("body"))
        self.summary_text.setWordWrap(True)
        summary_l.addWidget(self.summary_text)
        outer.addWidget(self.summary_card)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)

        self.save_txt_btn = QPushButton("Download TXT")
        self.save_txt_btn.setObjectName("ActionButton")
        self.save_txt_btn.clicked.connect(self._save_txt)
        actions.addWidget(self.save_txt_btn)

        self.save_json_btn = QPushButton("Download JSON")
        self.save_json_btn.setObjectName("ActionButton")
        self.save_json_btn.clicked.connect(self._save_json)
        actions.addWidget(self.save_json_btn)
        actions.addStretch(1)
        outer.addLayout(actions)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setObjectName("DiscoveryScroll")
        self.scroll.viewport().setObjectName("DiscoveryScrollViewport")
        self.scroll.setStyleSheet(_scroll_style())
        self.results_host = QWidget()
        self.results_host.setObjectName("DiscoveryResultsHost")
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(8, 8, 8, 8)
        self.results_layout.setSpacing(8)
        for dev in result.devices:
            row = DeviceRow(dev)
            self.results_layout.addWidget(row)
        self.results_layout.addStretch(1)
        self.scroll.setWidget(self.results_host)
        outer.addWidget(self.scroll, 1)

        root.addWidget(card)
        self.setStyleSheet(_dialog_style())

    def apply_theme_mode(self, mode: str) -> None:
        self.scroll.setStyleSheet(_scroll_style())
        self.setStyleSheet(_dialog_style())

    def _summary_lines(self) -> str:
        lines: list[str] = []
        for dev in self._result.devices:
            head = dev.hostname or dev.ip
            parts = [head]
            if dev.hostname and dev.hostname != dev.ip:
                parts.append(dev.ip)
            if dev.os_name:
                parts.append(dev.os_name)
            if dev.vendor:
                parts.append(dev.vendor)
            if dev.services_summary:
                parts.append(dev.services_summary)
            else:
                parts.append("Host discovery only")
            lines.append(" • ".join(parts))
        return "\n".join(lines) if lines else "No devices discovered."

    def _can_drag_from(self, pos) -> bool:
        widget = self.childAt(pos)
        while widget is not None:
            if isinstance(widget, (QPushButton, QScrollArea)):
                return False
            widget = widget.parentWidget()
        return pos.y() < 120

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._can_drag_from(event.position().toPoint()):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def _result_text(self) -> str:
        lines = [
            "Laptop Health Network Discovery",
            f"Mode: {'Quiet' if self._result.mode == 'quiet' else 'Noisy'}",
            f"Target: {self._result.target or '—'}",
            f"Devices: {len(self._result.devices)}",
        ]
        if self._result.note:
            lines.append(f"Note: {self._result.note}")
        lines.append("")
        for index, dev in enumerate(self._result.devices, start=1):
            lines.append(f"[{index}] {dev.hostname or dev.ip}")
            lines.append(f"IP: {dev.ip}")
            if dev.mac:
                mac_text = dev.mac + (f" ({dev.vendor})" if dev.vendor else "")
                lines.append(f"MAC: {mac_text}")
            if dev.os_name:
                lines.append(f"OS: {dev.os_name}")
            if dev.services_summary:
                lines.append(f"Open: {dev.services_summary}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _save_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Discovery Results",
            "network-discovery.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self._result_text())

    def _save_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Discovery Results",
            "network-discovery.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        payload = {
            "target": self._result.target,
            "mode": self._result.mode,
            "note": self._result.note,
            "devices": [
                {
                    "ip": dev.ip,
                    "hostname": dev.hostname,
                    "mac": dev.mac,
                    "vendor": dev.vendor,
                    "os_name": dev.os_name,
                    "services_summary": dev.services_summary,
                    "open_ports": dev.open_ports,
                }
                for dev in self._result.devices
            ],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


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
        self._scan_profile = "Default noisy"
        self._last_discovery_result: DiscoveryResult | None = None
        self._discovery_windows: list[DiscoveryResultsDialog] = []
        self._live_refresh_in_flight = False

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
        self.rx.setStyleSheet(_text_style("hero"))
        hero.addWidget(self.rx)

        self.tx = QLabel("— Mbps ↑")
        _set_font(self.tx, 44, True)
        self.tx.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.tx.setStyleSheet(_text_style("hero"))
        hero.addWidget(self.tx)

        hero.addStretch(1)
        lv.addLayout(hero)

        self.live_sub = QLabel("—")
        _set_font(self.live_sub, 14, True)
        self.live_sub.setAlignment(Qt.AlignHCenter)
        self.live_sub.setStyleSheet(_text_style("strong"))
        lv.addWidget(self.live_sub)

        self.live_meta = QLabel("—")
        _set_font(self.live_meta, 12, False)
        self.live_meta.setAlignment(Qt.AlignHCenter)
        self.live_meta.setWordWrap(True)
        self.live_meta.setStyleSheet(_text_style("muted"))
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
        self.down.setStyleSheet(_text_style("hero"))
        hero2.addWidget(self.down)

        self.up = QLabel("— Mbps ↑")
        _set_font(self.up, 44, True)
        self.up.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.up.setStyleSheet(_text_style("hero"))
        hero2.addWidget(self.up)

        hero2.addStretch(1)
        v.addLayout(hero2)

        # Sub line: ping + server/isp go below, not competing with hero numbers
        self.ping_line = QLabel("—")
        _set_font(self.ping_line, 14, True)
        self.ping_line.setAlignment(Qt.AlignHCenter)
        self.ping_line.setStyleSheet(_text_style("strong"))
        v.addWidget(self.ping_line)

        self.meta = QLabel("—")
        _set_font(self.meta, 12, False)
        self.meta.setAlignment(Qt.AlignHCenter)
        self.meta.setWordWrap(True)
        self.meta.setStyleSheet(_text_style("muted"))
        v.addWidget(self.meta)

        self.hist = QLabel("No results yet.")
        _set_font(self.hist, 12, False)
        self.hist.setAlignment(Qt.AlignHCenter)
        self.hist.setWordWrap(True)
        self.hist.setStyleSheet(_text_style("muted"))
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

        self.discovery_pill = QPushButton("0 Devices")
        self.discovery_pill.setObjectName("Badge")
        self.discovery_pill.setCursor(Qt.PointingHandCursor)
        self.discovery_pill.setEnabled(False)
        self.discovery_pill.clicked.connect(self._open_discovery_results)
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
        self.discovery_sub.setStyleSheet(_text_style("strong"))
        dv.addWidget(self.discovery_sub)

        opts = QHBoxLayout()
        opts.setSpacing(10)

        self.target_input = QLineEdit()
        self.target_input.setObjectName("ActionInput")
        self.target_input.setPlaceholderText("Target range, e.g. 192.168.1.0/24 or 192.168.1.10-40")
        self.target_input.setMinimumHeight(36)
        opts.addWidget(self.target_input, 2)

        self.preset_select = QComboBox()
        self.preset_select.setObjectName("ActionSelect")
        for label in NOISY_PRESETS:
            self.preset_select.addItem(label)
        self.preset_select.currentTextChanged.connect(self._on_preset_changed)
        self.preset_select.setMinimumHeight(36)
        opts.addWidget(self.preset_select, 1)

        self.options_input = QLineEdit()
        self.options_input.setObjectName("ActionInput")
        self.options_input.setPlaceholderText("Extra nmap options for noisy scans, e.g. -sV --script smb-os-discovery")
        self.options_input.setMinimumHeight(36)
        opts.addWidget(self.options_input, 3)

        dv.addLayout(opts)

        self.discovery_meta = QLabel("—")
        _set_font(self.discovery_meta, 12, False)
        self.discovery_meta.setWordWrap(True)
        self.discovery_meta.setStyleSheet(_text_style("muted"))
        dv.addWidget(self.discovery_meta)

        grid.addWidget(self.live, 0, 0)
        grid.addWidget(self.card, 1, 0)
        grid.addWidget(self.discovery, 2, 0)

        self.scan_feedback_timer = QTimer(self)
        self.scan_feedback_timer.setInterval(350)
        self.scan_feedback_timer.timeout.connect(self._tick_scan_feedback)

        self._refresh_live()
        self.discovery_sub.setText("Choose Quiet or Noisy mode, then run a scan when you want discovery results.")
        self.discovery_meta.setText("Quiet is fast host discovery. Noisy adds ports, services, and OS hints.")
        self.preset_select.setVisible(False)
        self.options_input.setVisible(False)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh_live)
        self.timer.start()

    def apply_theme_mode(self, mode: str) -> None:
        self.live_pill.setStyleSheet(_pill_style(self.live.property("accent") or "blue"))
        self.speed_pill.setStyleSheet(_pill_style(self.card.property("accent") or "blue"))
        self.discovery_pill.setStyleSheet(_pill_style(self.discovery.property("accent") or "blue"))
        self.rx.setStyleSheet(_text_style("hero"))
        self.tx.setStyleSheet(_text_style("hero"))
        self.live_sub.setStyleSheet(_text_style("strong"))
        self.live_meta.setStyleSheet(_text_style("muted"))
        self.down.setStyleSheet(_text_style("hero"))
        self.up.setStyleSheet(_text_style("hero"))
        self.ping_line.setStyleSheet(_text_style("strong"))
        self.meta.setStyleSheet(_text_style("muted"))
        self.hist.setStyleSheet(_text_style("muted"))
        self.discovery_sub.setStyleSheet(_text_style("strong"))
        self.discovery_meta.setStyleSheet(_text_style("muted"))
        for win in list(self._discovery_windows):
            try:
                win.apply_theme_mode(mode)
            except Exception:
                pass

    def _restyle(self, w: QFrame):
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()

    # -------- Live Network --------
    def _refresh_live(self):
        if self._live_refresh_in_flight:
            return
        self._live_refresh_in_flight = True
        w = QtWorker(lambda: sample_network(0.75))
        w.signals.result.connect(self._apply_live)
        w.signals.error.connect(self._apply_live_error)
        w.signals.finished.connect(lambda: setattr(self, "_live_refresh_in_flight", False))
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
        self.preset_select.setEnabled(False)
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
        self.preset_select.setEnabled(self._discovery_mode == "noisy")
        self.target_input.setEnabled(True)
        self.options_input.setEnabled(self._discovery_mode == "noisy")
        if self.btn_scan.text() == "Scanning…":
            self.btn_scan.setText("Scan devices")

    def _on_scan_mode_changed(self, text: str):
        self._discovery_mode = "noisy" if text.strip().lower() == "noisy" else "quiet"
        if self._discovery_mode == "noisy":
            self.preset_select.setVisible(True)
            self.preset_select.setEnabled(True)
            self.options_input.setVisible(True)
            self.options_input.setEnabled(True)
            self.options_input.setPlaceholderText("Extra nmap options for noisy scans, e.g. -sV --script smb-os-discovery")
            self.discovery_sub.setText("Noisy scan inspects open ports, service banners, and OS hints")
            if not self.options_input.text().strip():
                self.discovery_meta.setText("Tip: add scripts like --script smb-os-discovery for deeper LAN profiling")
        else:
            self.preset_select.setVisible(False)
            self.preset_select.setEnabled(False)
            self.options_input.setVisible(False)
            self.options_input.setEnabled(False)
            self.discovery_sub.setText("Discover devices on the active subnet")
            self.discovery_meta.setText("Quiet mode does fast host discovery only.")

    def _on_preset_changed(self, text: str):
        self._scan_profile = text or "Default noisy"
        preset = NOISY_PRESETS.get(self._scan_profile, "")
        if self._discovery_mode == "noisy" and preset and not self.options_input.text().strip():
            self.options_input.setText(preset)

    def _apply_discovery_error(self, msg: str):
        self._last_discovery_result = None
        self.discovery.setProperty("accent", "red")
        self.discovery_pill.setText("0 Devices")
        self.discovery_pill.setEnabled(False)
        self._restyle(self.discovery)
        self.discovery_sub.setText(msg or "Network discovery failed")
        self.discovery_meta.setText("—")

    def _apply_discovery(self, result):
        if not isinstance(result, DiscoveryResult):
            self._apply_discovery_error("Network discovery failed")
            return
        self._last_discovery_result = result

        if result.error:
            accent = "orange" if "nmap is not installed" in result.error.lower() else "red"
            self.discovery.setProperty("accent", accent)
            self.discovery_pill.setText("0 Devices")
            self.discovery_pill.setEnabled(False)
            self._restyle(self.discovery)
            self.discovery_sub.setText(result.error)
            self.discovery_meta.setText(f"Subnet: {result.target or '—'}")
            return

        count = len(result.devices)
        accent = "green" if count > 0 else "blue"
        self.discovery.setProperty("accent", accent)
        self.discovery_pill.setText(f"{count} Device{'s' if count != 1 else ''}")
        self.discovery_pill.setEnabled(count > 0)
        self._restyle(self.discovery)

        mode_label = "Quiet" if result.mode == "quiet" else "Noisy"
        self.discovery_sub.setText(f"Discovered {count} device{'s' if count != 1 else ''} with {mode_label} scan. Click the device count to open the full report.")
        meta = f"Subnet: {result.target or '—'} • Mode: {mode_label}"
        if result.note:
            meta += f" • {result.note}"
        elif result.mode == "noisy":
            meta += " • Includes open ports, service banners, and OS hints when available"
        self.discovery_meta.setText(meta)

        self._show_discovery_results(result)

    def _open_discovery_results(self):
        if not self._last_discovery_result or not self._last_discovery_result.devices:
            return
        self._show_discovery_results(self._last_discovery_result)

    def _show_discovery_results(self, result: DiscoveryResult) -> None:
        dlg = DiscoveryResultsDialog(self, result)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda *args, w=dlg: self._discovery_windows.remove(w) if w in self._discovery_windows else None)
        self._discovery_windows.append(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _tick_scan_feedback(self):
        dots = "." * ((self._scan_feedback_step % 3) + 1)
        elapsed = 0
        if self._scan_started_at > 0:
            elapsed = max(0, int(time.monotonic() - self._scan_started_at))
        mode_label = "Quiet" if self._discovery_mode == "quiet" else "Noisy"
        self.discovery_sub.setText(f"{mode_label} scan in progress{dots}")
        self.discovery_meta.setText(f"Elapsed: {elapsed}s • Target: {self._scan_target_text}")
        self._scan_feedback_step += 1
