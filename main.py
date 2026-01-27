#!/usr/bin/env python3
# Laptop Health (Linux) — Diagnostics + Warnings + Network Module
#
# venv deps:
#   PySide6, psutil
#
# optional tools:
#   lm-sensors (sensors), nvme-cli (nvme), powerprofilesctl (power-profiles-daemon), nvidia-smi (NVIDIA)
#   nmcli (NetworkManager) for Wi-Fi SSID/signal
#   speedtest (Ookla CLI) OR speedtest-cli for speed testing

import ui
import sensors
import system
import os
import sys

# Must run inside venv
if sys.prefix == sys.base_prefix:
    raise RuntimeError(
        "Virtual environment not active.\n"
        "Run: source .venv/bin/activate"
    )

import time
import json
from collections import deque
from dataclasses import dataclass

import psutil
from PySide6 import QtCore, QtGui, QtWidgets


APP_NAME = "Laptop Health"
REFRESH_MS = 1000
BACKEND_REFRESH_MS = 3000
HIST_LEN = 120

# CLI flag
DEV_MODE = "--dev" in sys.argv

# Temperature thresholds (status + visuals) — tune to taste
CPU_WARM, CPU_HOT = 75, 85
GPU_WARM, GPU_HOT = 70, 80
SSD_WARM, SSD_HOT = 60, 70


@dataclass
class BackendStatus:
    sensors_ok: bool = False
    sensors_err: str = ""
    nvidia_ok: bool = False
    nvidia_err: str = ""
    nvme_ok: bool = False
    nvme_err: str = ""
    power_ok: bool = False
    power_err: str = ""
    nmcli_ok: bool = False
    nmcli_err: str = ""
    speedtest_ok: bool = False
    speedtest_err: str = ""


# -------------------- UI widgets --------------------
class Sparkline(QtWidgets.QWidget):
    def __init__(self, series: deque, parent=None):
        super().__init__(parent)
        self.series = series
        self.setFixedHeight(32)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect()

        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 30), 1))
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 8, 8)

        vals = [v for v in self.series if isinstance(v, (int, float))]
        if len(vals) < 2:
            return

        vmin, vmax = min(vals), max(vals)
        if vmax - vmin < 0.01:
            vmax = vmin + 1.0

        pad = 7
        w = max(1, r.width() - pad * 2)
        h = max(1, r.height() - pad * 2)

        path = QtGui.QPainterPath()
        for i, v in enumerate(vals):
            x = r.left() + pad + (i / (len(vals) - 1)) * w
            y = r.top() + pad + (1.0 - (v - vmin) / (vmax - vmin)) * h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        p.setPen(QtGui.QPen(QtGui.QColor("#0f766e"), 2))
        p.drawPath(path)


class Card(QtWidgets.QFrame):
    def __init__(self, title: str, series: deque | None = None):
        super().__init__()
        self.setObjectName("card")
        self.setProperty("state", "normal")

        self.title = QtWidgets.QLabel(f"<b>{title}</b>")
        self.value = QtWidgets.QLabel("—")
        self.value.setObjectName("value")

        self.sub = QtWidgets.QPlainTextEdit()
        self.sub.setReadOnly(True)
        self.sub.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.sub.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.sub.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.sub.setMaximumHeight(160)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(self.title)
        lay.addWidget(self.value)

        self.spark = None
        if series is not None:
            self.spark = Sparkline(series)
            lay.addWidget(self.spark)

        lay.addWidget(self.sub, 1)

    def set_text(self, value: str, sub: str):
        self.value.setText(value)
        self.sub.setPlainText(sub)
        if self.spark:
            self.spark.update()

    def set_state(self, state: str):
        s = (state or "unknown").lower()
        if s not in ("normal", "warm", "hot", "unknown"):
            s = "unknown"

        self.setProperty("state", s)

        # Force a full repolish of this card AND its children so #value colour reverts reliably
        for w in [self, self.title, self.value, self.sub]:
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()

class DiagnosticsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnostics")
        self.resize(980, 640)

        self.box = QtWidgets.QPlainTextEdit()
        self.box.setReadOnly(True)

        self.btn_copy = QtWidgets.QPushButton("Copy to clipboard")
        self.btn_close = QtWidgets.QPushButton("Close")

        self.btn_copy.clicked.connect(self.copy_all)
        self.btn_close.clicked.connect(self.close)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btn_copy)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.box, 1)
        lay.addLayout(btns)

    def set_text(self, txt: str):
        self.box.setPlainText(txt)
        self.box.moveCursor(QtGui.QTextCursor.Start)

    def copy_all(self):
        system.clip_set_text(self.box.toPlainText())
        QtWidgets.QMessageBox.information(self, "Copied", "Diagnostics copied to clipboard.")


# -------------------- Speed test worker --------------------
class SpeedTestWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, str)  # ok, message

    @QtCore.Slot()
    def run(self):
        if system.which("speedtest"):
            rc_v, out_v, err_v = system.run_cmd(["speedtest", "--version"], timeout_s=5)
            ver = (out_v or err_v or "").lower()

            # speedtest-cli (python)
            if "speedtest-cli" in ver or "sivel" in ver:
                rc, out, err = system.run_cmd(["speedtest", "--json"], timeout_s=180)
                if rc != 0 or not out:
                    self.finished.emit(
                        False,
                        f"speedtest-cli failed (rc={rc}).\n\nstdout:\n{out or '(empty)'}\n\nstderr:\n{err or '(empty)'}",
                    )
                    return
                try:
                    data = json.loads(out)
                    down_bps = data.get("download")
                    up_bps = data.get("upload")
                    ping = data.get("ping")
                    server = (data.get("server") or {}).get("sponsor") or (data.get("server") or {}).get("name")
                    isp = data.get("client", {}).get("isp")

                    down_mbps = (down_bps / 1_000_000) if down_bps else None
                    up_mbps = (up_bps / 1_000_000) if up_bps else None

                    msg = ["=== SPEEDTEST (speedtest-cli) ==="]
                    if isp:
                        msg.append(f"ISP: {isp}")
                    if server:
                        msg.append(f"Server: {server}")
                    if ping is not None:
                        msg.append(f"Ping: {ping:.1f} ms")
                    if down_mbps is not None:
                        msg.append(f"Download: {down_mbps:.2f} Mbps")
                    if up_mbps is not None:
                        msg.append(f"Upload: {up_mbps:.2f} Mbps")
                    msg.append("")
                    self.finished.emit(True, "\n".join(msg))
                    return
                except Exception as e:
                    self.finished.emit(False, f"speedtest-cli JSON parse error: {e}\n\nRaw:\n{out[:3000]}")
                    return

            # Ookla CLI
            candidates = [
                ["speedtest", "--accept-license", "--accept-gdpr", "-f", "json"],
                ["speedtest", "--accept-license", "--accept-gdpr", "--format=json"],
                ["speedtest", "-f", "json"],
                ["speedtest", "--format=json"],
            ]
            last_out, last_err = "", ""
            for cmd in candidates:
                rc, out, err = system.run_cmd(cmd, timeout_s=120)
                last_out, last_err = out, err
                if not out:
                    continue
                try:
                    data = json.loads(out)
                except Exception:
                    continue

                down = data.get("download", {}).get("bandwidth")  # bytes/s
                up = data.get("upload", {}).get("bandwidth")      # bytes/s
                ping = data.get("ping", {}).get("latency")
                isp = data.get("isp")
                server = (data.get("server", {}) or {}).get("name")
                down_mbps = (down * 8 / 1_000_000) if down else None
                up_mbps = (up * 8 / 1_000_000) if up else None

                msg = ["=== SPEEDTEST (Ookla) ==="]
                if isp:
                    msg.append(f"ISP: {isp}")
                if server:
                    msg.append(f"Server: {server}")
                if ping is not None:
                    msg.append(f"Ping: {ping:.1f} ms")
                if down_mbps is not None:
                    msg.append(f"Download: {down_mbps:.2f} Mbps")
                if up_mbps is not None:
                    msg.append(f"Upload: {up_mbps:.2f} Mbps")
                msg.append("")
                self.finished.emit(True, "\n".join(msg))
                return

            self.finished.emit(
                False,
                "speedtest exists but didn't return JSON I can parse.\n\n"
                f"--version:\n{out_v or err_v or '(empty)'}\n\n"
                f"Last stdout:\n{last_out or '(empty)'}\n\nLast stderr:\n{last_err or '(empty)'}",
            )
            return

        if system.which("speedtest-cli"):
            rc, out, err = system.run_cmd(["speedtest-cli", "--json"], timeout_s=180)
            if rc != 0 or not out:
                self.finished.emit(False, f"speedtest-cli failed (rc={rc}).\n\nstdout:\n{out or '(empty)'}\n\nstderr:\n{err or '(empty)'}")
                return
            try:
                data = json.loads(out)
                down_bps = data.get("download")
                up_bps = data.get("upload")
                ping = data.get("ping")
                down_mbps = (down_bps / 1_000_000) if down_bps else None
                up_mbps = (up_bps / 1_000_000) if up_bps else None
                msg = ["=== SPEEDTEST (speedtest-cli) ==="]
                if ping is not None:
                    msg.append(f"Ping: {ping:.1f} ms")
                if down_mbps is not None:
                    msg.append(f"Download: {down_mbps:.2f} Mbps")
                if up_mbps is not None:
                    msg.append(f"Upload: {up_mbps:.2f} Mbps")
                msg.append("")
                self.finished.emit(True, "\n".join(msg))
                return
            except Exception as e:
                self.finished.emit(False, f"speedtest-cli JSON parse error: {e}\n\nRaw:\n{out[:3000]}")
                return

        self.finished.emit(False, "No speedtest tool found.")


# -------------------- Main window --------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1040, 740)

        # dev overrides (None = disabled)
        self.dev_override_cpu: float | None = None
        self.dev_override_gpu: float | None = None
        self.dev_override_ssd: float | None = None

        self.cpu_hist = deque(maxlen=HIST_LEN)
        self.gpu_hist = deque(maxlen=HIST_LEN)
        self.ssd_hist = deque(maxlen=HIST_LEN)
        self.down_hist = deque(maxlen=HIST_LEN)
        self.up_hist = deque(maxlen=HIST_LEN)

        self.backend_status = BackendStatus()
        self.last_sensors_raw = ""
        self.last_nvme_err = ""
        self.last_nvidia_err = ""

        # net counters
        self._net_prev_ts = time.time()
        self._net_prev = psutil.net_io_counters(pernic=True)
        self._net_iface = None
        self._net_ip = None

        # state tracking (notify + flashing)
        self.prev_overall_state = "Normal"
        self.notifications_enabled = True
        self.flash_on_hot_enabled = True
        self._flashing = False
        self._flash_tick = False

        # --- top bar ---
        top = QtWidgets.QWidget()
        top_l = QtWidgets.QHBoxLayout(top)
        top_l.setContentsMargins(12, 12, 12, 6)

        self.status = QtWidgets.QLabel("<b>Status:</b> —")
        self.badge = QtWidgets.QLabel("Mode: —")
        self.badge.setObjectName("badge")

        self.banner = QtWidgets.QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setVisible(False)

        top_l.addWidget(self.status)
        top_l.addWidget(self.badge)
        top_l.addSpacing(8)
        top_l.addWidget(self.banner, 1)

        self.btn_quiet = QtWidgets.QPushButton("Quiet")
        self.btn_bal = QtWidgets.QPushButton("Balanced")
        self.btn_perf = QtWidgets.QPushButton("Performance")
        for b in (self.btn_quiet, self.btn_bal, self.btn_perf):
            b.setCheckable(True)
            b.setObjectName("modebtn")

        self.btn_quiet.clicked.connect(lambda: self.set_mode("Quiet"))
        self.btn_bal.clicked.connect(lambda: self.set_mode("Balanced"))
        self.btn_perf.clicked.connect(lambda: self.set_mode("Performance"))

        self.btn_speed = QtWidgets.QPushButton("Speed test")
        self.btn_speed.setObjectName("copybtn")
        self.btn_speed.clicked.connect(self.run_speed_test)

        self.btn_copy = QtWidgets.QPushButton("Copy diagnostics")
        self.btn_copy.setObjectName("copybtn")
        self.btn_copy.clicked.connect(self.copy_diagnostics)

        self.btn_show = QtWidgets.QPushButton("Show diagnostics")
        self.btn_show.setObjectName("copybtn")
        self.btn_show.clicked.connect(self.show_diagnostics)

        # Dev tools button (only if --dev)
        self.btn_dev = None
        if DEV_MODE:
            self.btn_dev = QtWidgets.QPushButton("Dev tools")
            self.btn_dev.setObjectName("copybtn")
            self.btn_dev.clicked.connect(self.open_dev_tools)

        top_l.addWidget(self.btn_quiet)
        top_l.addWidget(self.btn_bal)
        top_l.addWidget(self.btn_perf)
        top_l.addWidget(self.btn_speed)
        top_l.addWidget(self.btn_copy)
        top_l.addWidget(self.btn_show)
        if self.btn_dev:
            top_l.addWidget(self.btn_dev)

        # --- cards ---
        body = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(body)
        grid.setContentsMargins(12, 6, 12, 12)
        grid.setSpacing(12)

        self.card_cpu = Card("CPU", self.cpu_hist)
        self.card_gpu = Card("GPU", self.gpu_hist)
        self.card_ssd = Card("SSD / NVMe", self.ssd_hist)
        self.card_net = Card("Network", self.down_hist)
        self.card_sys = Card("System")

        grid.addWidget(self.card_cpu, 0, 0)
        grid.addWidget(self.card_gpu, 0, 1)
        grid.addWidget(self.card_ssd, 1, 0)
        grid.addWidget(self.card_net, 1, 1)
        grid.addWidget(self.card_sys, 2, 0, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)

        root = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(top)
        v.addWidget(body, 1)
        self.setCentralWidget(root)

        # tray
        self.icon_ok = QtGui.QIcon.fromTheme("utilities-system-monitor")
        if self.icon_ok.isNull():
            self.icon_ok = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon)

        self.icon_warn = QtGui.QIcon.fromTheme("dialog-warning")
        if self.icon_warn.isNull():
            self.icon_warn = self.icon_ok

        self.tray = QtWidgets.QSystemTrayIcon(self.icon_ok, self)
        menu = QtWidgets.QMenu()
        menu.addAction("Show", self.showNormal)
        menu.addAction("Hide", self.hide)
        menu.addSeparator()

        act_notify = menu.addAction("Notifications")
        act_notify.setCheckable(True)
        act_notify.setChecked(True)
        act_notify.toggled.connect(lambda v: setattr(self, "notifications_enabled", bool(v)))

        act_flash = menu.addAction("Flash tray on HOT")
        act_flash.setCheckable(True)
        act_flash.setChecked(True)
        act_flash.toggled.connect(self._toggle_flash)

        if DEV_MODE:
            menu.addSeparator()
            menu.addAction("Dev tools", self.open_dev_tools)
            menu.addAction("Clear dev overrides", self.clear_dev_overrides)

        menu.addSeparator()
        menu.addAction("Speed test", self.run_speed_test)
        menu.addAction("Show diagnostics", self.show_diagnostics)
        menu.addAction("Copy diagnostics", self.copy_diagnostics)
        menu.addSeparator()
        menu.addAction("Quit", self.shutdown)

        self.tray.setContextMenu(menu)
        self.tray.show()

        self.flash_timer = QtCore.QTimer(self)
        self.flash_timer.setInterval(500)
        self.flash_timer.timeout.connect(self._flash_step)

        self.apply_style()
        self.diag_dialog = DiagnosticsDialog(self)

        # timers
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh_fast)
        self.timer.start(REFRESH_MS)

        self.backend_timer = QtCore.QTimer(self)
        self.backend_timer.timeout.connect(self.refresh_backends)
        self.backend_timer.start(BACKEND_REFRESH_MS)

        self.refresh_backends()
        self.refresh_fast()

    # -------- window close behaviour --------
    def closeEvent(self, e):
        # hide to tray
        e.ignore()
        self.hide()

    # -------- styles --------
    def apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow { background: #f5f5f4; }
            QLabel { color: rgba(0,0,0,0.84); }

            #badge {
                padding: 4px 10px;
                border-radius: 999px;
                background: rgba(0,0,0,0.06);
            }

            #banner {
                padding: 6px 10px;
                border-radius: 12px;
                background: rgba(0,0,0,0.06);
                color: rgba(0,0,0,0.85);
            }
            #banner[state="warm"] { background: rgba(245,158,11,0.18); border: 1px solid rgba(245,158,11,0.45); }
            #banner[state="hot"]  { background: rgba(239,68,68,0.18);  border: 1px solid rgba(239,68,68,0.50); }

            #modebtn {
                padding: 6px 12px;
                border-radius: 999px;
                background: rgba(0,0,0,0.06);
                border: 1px solid rgba(0,0,0,0.08);
            }
            #modebtn:checked {
                background: rgba(20,184,166,0.22);
                border: 1px solid rgba(20,184,166,0.55);
            }
            #copybtn {
                padding: 6px 12px;
                border-radius: 999px;
                background: rgba(2,132,199,0.12);
                border: 1px solid rgba(2,132,199,0.25);
            }

            #card {
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.10);
                border-radius: 14px;
            }
            #value { font-size: 28px; font-weight: 800; color: rgba(0,0,0,0.90); }

            #card[state="normal"] { border: 1px solid rgba(0,0,0,0.10); }
            #card[state="warm"]   { border: 2px solid rgba(245,158,11,0.55); }
            #card[state="hot"]    { border: 2px solid rgba(239,68,68,0.60); }
            #card[state="unknown"]{ border: 1px dashed rgba(0,0,0,0.18); }

            #card[state="warm"]  #value { color: rgba(245,158,11,0.95); }
            #card[state="hot"]   #value { color: rgba(239,68,68,0.95); }

            QPlainTextEdit { background: transparent; color: rgba(0,0,0,0.75); }
            """
        )

    # -------- dev tools --------
    def open_dev_tools(self):
        # Single dialog controls all overrides; Cancel = do nothing
        v, ok = QtWidgets.QInputDialog.getDouble(
            self,
            "Dev override",
            "Set CPU/GPU/SSD temp override (°C). Use -1 to clear.",
            100.0,   # value
            -1.0,    # min
            120.0,   # max
            1        # decimals
        )

        if not ok:
            return

        if v < 0:
            self.clear_dev_overrides()
            return

        self.dev_override_cpu = v
        self.dev_override_gpu = v
        self.dev_override_ssd = v

    def clear_dev_overrides(self):
        self.dev_override_cpu = None
        self.dev_override_gpu = None
        self.dev_override_ssd = None

    # -------- tray flashing + notifications --------
    def _toggle_flash(self, v: bool):
        self.flash_on_hot_enabled = bool(v)
        if not self.flash_on_hot_enabled:
            self._stop_flashing()

    def _flash_step(self):
        if not self._flashing:
            return
        self._flash_tick = not self._flash_tick
        self.tray.setIcon(self.icon_warn if self._flash_tick else self.icon_ok)

    def _start_flashing(self):
        if self._flashing:
            return
        self._flashing = True
        self._flash_tick = False
        self.flash_timer.start()

    def _stop_flashing(self):
        self._flashing = False
        self.flash_timer.stop()
        self.tray.setIcon(self.icon_ok)

    def _notify(self, title: str, msg: str):
        if not self.notifications_enabled:
            return
        try:
            self.tray.showMessage(title, msg, self.icon_warn, 7000)
        except Exception:
            pass

    # -------- power mode --------
    def set_mode(self, mode: str):
        ok, err = system.powerprofiles_set(mode)
        if not ok:
            QtWidgets.QMessageBox.warning(self, "Power mode failed", err)
        self.refresh_backends()

    def highlight_mode_buttons(self, mode_label: str):
        self.btn_quiet.setChecked(False)
        self.btn_bal.setChecked(False)
        self.btn_perf.setChecked(False)
        if mode_label == "Quiet":
            self.btn_quiet.setChecked(True)
        elif mode_label == "Balanced":
            self.btn_bal.setChecked(True)
        elif mode_label == "Performance":
            self.btn_perf.setChecked(True)

    # -------- speed test --------
    def run_speed_test(self):
        self.btn_speed.setEnabled(False)
        self.btn_speed.setText("Speed test…")

        self._notify(APP_NAME, "Running speed test…")

        self.worker = SpeedTestWorker()
        self.thread = QtCore.QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._speedtest_done)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _speedtest_done(self, ok: bool, msg: str):
        self.btn_speed.setEnabled(True)
        self.btn_speed.setText("Speed test")

        system.clip_set_text(msg)
        if ok:
            self._notify(APP_NAME, "Speed test complete (copied to clipboard).")
            QtWidgets.QMessageBox.information(self, "Speed test", msg + "\n(copied to clipboard)")
        else:
            QtWidgets.QMessageBox.warning(self, "Speed test failed", msg)

    # -------- diagnostics --------
    def build_diagnostics(self) -> str:
        parts = []
        parts.append("=== STATUS ===")
        parts.append(self.status.text())
        parts.append("\n=== MODE ===")
        parts.append(self.badge.text())

        parts.append("\n=== BACKENDS ===")
        parts.append(f"sensors: {system.which('sensors') or 'missing'}")
        parts.append(f"nvidia-smi: {system.which('nvidia-smi') or 'missing'}")
        parts.append(f"nvme: {system.which('nvme') or 'missing'}")
        parts.append(f"powerprofilesctl: {system.which('powerprofilesctl') or 'missing'}")
        parts.append(f"nmcli: {system.which('nmcli') or 'missing'}")
        parts.append(f"speedtest: {system.which('speedtest') or system.which('speedtest-cli') or 'missing'}")

        if (self.last_sensors_raw or "").strip():
            parts.append("\n=== sensors (raw) ===")
            parts.append(self.last_sensors_raw.strip())

        parts.append("\n=== RUNTIME ===")
        parts.append(f"Python: {sys.version}")
        parts.append(f"Executable: {sys.executable}")
        parts.append(f"App file: {os.path.abspath(__file__)}")

        parts.append("\n=== SYSTEM ===")
        try:
            parts.append(f"Kernel: {os.uname().release}")
        except Exception:
            pass
        parts.append(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(parts).strip()

    def copy_diagnostics(self):
        system.clip_set_text(self.build_diagnostics())
        QtWidgets.QMessageBox.information(self, "Copied", "Diagnostics copied to clipboard.")

    def show_diagnostics(self):
        self.diag_dialog.set_text(self.build_diagnostics())
        self.diag_dialog.show()
        self.diag_dialog.raise_()
        self.diag_dialog.activateWindow()


    # -------------------- helpers --------------------

    def _read_total_interrupts(self) -> int | None:
        """
        Total interrupts across all CPUs from /proc/interrupts.
        Proxy for wakeups/sec (always available, no root).
        """
        try:
            total = 0
            with open("/proc/interrupts", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if ":" not in line:
                        continue
                    _left, right = line.split(":", 1)
                    parts = right.strip().split()
                    for p in parts:
                        if p.isdigit():
                            total += int(p)
                        else:
                            break
            return total
        except Exception:
            return None

    def _read_ctx_switches(self) -> int | None:
        """
        Context switches from /proc/stat (line: 'ctxt <num>').
        """
        try:
            with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("ctxt "):
                        return int(line.split()[1])
            return None
        except Exception:
            return None


    # -------- backend refresh --------
    def refresh_backends(self):
        prof, err = system.powerprofiles_get_active()
        self.backend_status.power_ok = (err == "")
        self.backend_status.power_err = err
        self.badge.setText(f"Mode: {prof}")
        self.highlight_mode_buttons(prof)

        self.backend_status.nmcli_ok = bool(system.which("nmcli"))
        self.backend_status.nmcli_err = "" if self.backend_status.nmcli_ok else "missing: nmcli"

        self.backend_status.speedtest_ok = bool(system.which("speedtest") or system.which("speedtest-cli"))
        self.backend_status.speedtest_err = "" if self.backend_status.speedtest_ok else "missing: speedtest"

    # -------- network refresh --------
    def refresh_network(self) -> tuple[float | None, float | None, str]:
        now = time.time()
        dt = max(0.001, now - self._net_prev_ts)

        pernic = psutil.net_io_counters(pernic=True)
        iface, ip = system.get_default_iface_and_ip()
        self._net_iface, self._net_ip = iface, ip

        down_bps = None
        up_bps = None

        if iface and iface in pernic and iface in self._net_prev:
            cur = pernic[iface]
            prev = self._net_prev[iface]
            down_bps = (cur.bytes_recv - prev.bytes_recv) / dt
            up_bps = (cur.bytes_sent - prev.bytes_sent) / dt

        self._net_prev = pernic
        self._net_prev_ts = now

        ssid, signal, rate = system.nmcli_wifi_status()

        lines = []
        lines.append(f"Interface: {iface or '—'}")
        lines.append(f"IP: {ip or '—'}")
        if ssid or signal is not None:
            lines.append(f"Wi-Fi: {ssid or '—'} • Signal: {signal if signal is not None else '—'}%")
        if rate:
            lines.append(f"Wi-Fi rate: {rate}")

        return down_bps, up_bps, "\n".join(lines)

    # -------- main refresh --------
    def refresh_fast(self):
        cpu_u = psutil.cpu_percent(interval=None)
        mem_u = psutil.virtual_memory().percent

        temps_s, sensors_err = sensors.read_sensors()
        self.last_sensors_raw = temps_s.get("raw", "")
        cpu_t = temps_s.get("cpu")
        gpu_t_s = temps_s.get("gpu")
        ssd_t_s = temps_s.get("ssd")

        nvgpu, _ = sensors.read_nvidia_gpu_temp()
        nvme_t, _ = sensors.read_nvme_temp()

        gpu_t = nvgpu if isinstance(nvgpu, (int, float)) else gpu_t_s
        ssd_t = nvme_t if isinstance(nvme_t, (int, float)) else ssd_t_s

        cpu_state = system.state_for(cpu_t, CPU_WARM, CPU_HOT) or "Unknown"
        gpu_state = system.state_for(gpu_t, GPU_WARM, GPU_HOT) or "Unknown"
        ssd_state = system.state_for(ssd_t, SSD_WARM, SSD_HOT) or "Unknown"

        # dev overrides: must happen BEFORE set_state/set_text
        if DEV_MODE:
            if self.dev_override_cpu is not None:
                cpu_t = float(self.dev_override_cpu)
            if self.dev_override_gpu is not None:
                gpu_t = float(self.dev_override_gpu)
            if self.dev_override_ssd is not None:
                ssd_t = float(self.dev_override_ssd)

            temps_s["cpu"] = cpu_t
            temps_s["gpu"] = gpu_t
            temps_s["ssd"] = ssd_t

            cpu_state = system.state_for(cpu_t, CPU_WARM, CPU_HOT) or "Unknown"
            gpu_state = system.state_for(gpu_t, GPU_WARM, GPU_HOT) or "Unknown"
            ssd_state = system.state_for(ssd_t, SSD_WARM, SSD_HOT) or "Unknown"

        # cards: states first (colour), then text
        self.card_cpu.set_state(cpu_state)
        self.card_gpu.set_state(gpu_state)
        self.card_ssd.set_state(ssd_state)

        if isinstance(cpu_t, (int, float)):
            self.cpu_hist.append(cpu_t)
            self.card_cpu.set_text(f"{cpu_t:.0f}°C", f"CPU Util: {cpu_u:.0f}% • RAM Util: {mem_u:.0f}%")
        else:
            self.card_cpu.set_text("—", f"CPU Util: {cpu_u:.0f}% • RAM Util: {mem_u:.0f}%")

        if isinstance(gpu_t, (int, float)):
            self.gpu_hist.append(gpu_t)
            src = "nvidia-smi" if isinstance(nvgpu, (int, float)) else "sensors"
            self.card_gpu.set_text(f"{gpu_t:.0f}°C", f"GPU temp via {src}")
        else:
            self.card_gpu.set_text("—", "GPU temp unavailable")

        if isinstance(ssd_t, (int, float)):
            self.ssd_hist.append(ssd_t)
            src = "nvme smart-log" if isinstance(nvme_t, (int, float)) else "sensors"
            self.card_ssd.set_text(f"{ssd_t:.0f}°C", f"SSD temp via {src}")
        else:
            self.card_ssd.set_text("—", "SSD temp unavailable")

        # network
        down_bps, up_bps, net_info = self.refresh_network()
        if isinstance(down_bps, (int, float)) and isinstance(up_bps, (int, float)):
            self.down_hist.append(system.bps_to_mbps(down_bps))
            self.up_hist.append(system.bps_to_mbps(up_bps))
            self.card_net.set_state("normal")
            self.card_net.set_text(
                f"↓ {system.bps_to_mbps(down_bps):.2f} Mbps",
                f"↑ {system.bps_to_mbps(up_bps):.2f} Mbps\n{net_info}",
            )
        else:
            self.card_net.set_state("unknown")
            self.card_net.set_text("—", net_info or "Network stats unavailable")

        # system tile
        sys_lines = [
            f"Updated: {time.strftime('%H:%M:%S')}",
            f"sensors: {'OK' if system.which('sensors') else 'missing'}",
            f"nvme-cli: {'OK' if system.which('nvme') else 'missing'}",
            f"nvidia: {'OK' if system.which('nvidia-smi') else 'missing'}",
            f"nmcli: {'OK' if system.which('nmcli') else 'missing'}",
            f"speedtest: {'OK' if (system.which('speedtest') or system.which('speedtest-cli')) else 'missing'}",
        ]
        self.card_sys.set_state("normal")
        self.card_sys.set_text("System", "\n".join(sys_lines))

        # overall
        present = [s for s in (cpu_state, gpu_state, ssd_state) if s in ("Normal", "Warm", "Hot")]
        overall = system.worst_state(present) if present else "Normal"
        self.status.setText(f"<b>Status:</b> {overall}")

        if overall == "Normal":
            self.banner.setVisible(False)
            self.banner.setProperty("state", "normal")
            self.banner.style().unpolish(self.banner)
            self.banner.style().polish(self.banner)
            self._stop_flashing()
        else:
            self.banner.setVisible(True)
            self.banner.setProperty("state", overall.lower())
            bits = []
            if cpu_state in ("Warm", "Hot") and isinstance(cpu_t, (int, float)):
                bits.append(f"CPU {cpu_t:.0f}°C ({cpu_state})")
            if gpu_state in ("Warm", "Hot") and isinstance(gpu_t, (int, float)):
                bits.append(f"GPU {gpu_t:.0f}°C ({gpu_state})")
            if ssd_state in ("Warm", "Hot") and isinstance(ssd_t, (int, float)):
                bits.append(f"SSD {ssd_t:.0f}°C ({ssd_state})")
            self.banner.setText(" • ".join(bits) if bits else f"System is {overall}")
            self.banner.style().unpolish(self.banner)
            self.banner.style().polish(self.banner)

            if overall == "Hot" and self.flash_on_hot_enabled:
                self._start_flashing()
            else:
                self._stop_flashing()

    # -------- shutdown --------
    def shutdown(self):
        # stop timers
        for name in ("flash_timer", "timer", "backend_timer"):
            t = getattr(self, name, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass

        # stop worker/thread if running
        try:
            if hasattr(self, "worker") and getattr(self, "worker", None) is not None:
                if hasattr(self.worker, "stop"):
                    self.worker.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "thread") and getattr(self, "thread", None) is not None:
                self.thread.quit()
                self.thread.wait(1500)
        except Exception:
            pass

        # tray cleanup (prevents ghost icons)
        try:
            tray = getattr(self, "tray", None)
            if tray is not None:
                tray.hide()
                tray.setVisible(False)
                tray.deleteLater()
        except Exception:
            pass

        QtWidgets.QApplication.quit()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    w = MainWindow()
    w.show()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        QtWidgets.QApplication.quit()


if __name__ == "__main__":
    main()
