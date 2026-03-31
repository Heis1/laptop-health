from __future__ import annotations

import json
import time

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ui_v2.services.probe import ProbeConfig, fetch_probe_snapshot, load_probe_configs, metric_as_float, new_probe_config, remove_probe_config
from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.probe_deploy_dialog import ProbeDeployDialog
from ui_v2.widgets.probe_remove_dialog import ProbeRemoveDialog
from ui_v2.widgets.prompt_dialog import PromptDialog
from ui_v2.workers import Worker


def _cpu_accent(temp_c: float | None) -> str:
    if temp_c is None:
        return "blue"
    if temp_c < 55:
        return "green"
    if temp_c < 75:
        return "orange"
    return "red"


class RemotePage(QWidget):
    def __init__(self, open_settings, parent=None):
        super().__init__()
        self.pool = QThreadPool()
        self._workers: list[object] = []
        self._open_settings = open_settings
        self._configs: list[ProbeConfig] = []
        self._selected_index = 0
        self._last_payload: dict | None = None
        self._last_error = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        top = QVBoxLayout()
        self.title = QLabel("Probe/s")
        self.title.setObjectName("PageTitle")
        top.addWidget(self.title)

        self.subtitle = QLabel("Monitor and manage Raspberry Pi probes from one place.")
        self.subtitle.setObjectName("InspectorSub")
        top.addWidget(self.subtitle)

        actions = QHBoxLayout()
        self.settings_btn = QPushButton("Edit Current")
        self.settings_btn.setObjectName("ActionButton")
        self.settings_btn.clicked.connect(self._edit_current)
        actions.addWidget(self.settings_btn)

        self.add_btn = QPushButton("Add Probe")
        self.add_btn.setObjectName("ActionButton")
        self.add_btn.clicked.connect(self._add_probe)
        actions.addWidget(self.add_btn)

        self.install_btn = QPushButton("Reinstall Current")
        self.install_btn.setObjectName("ActionButton")
        self.install_btn.clicked.connect(self._install_current)
        actions.addWidget(self.install_btn)

        self.remove_btn = QPushButton("Remove Current")
        self.remove_btn.setObjectName("ActionButton")
        self.remove_btn.clicked.connect(self._remove_probe)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        top.addLayout(actions)

        selector = QHBoxLayout()
        selector.setSpacing(8)
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setObjectName("ActionButton")
        self.prev_btn.clicked.connect(self._prev_probe)
        selector.addWidget(self.prev_btn)

        self.selector_lbl = QLabel("No probes configured")
        self.selector_lbl.setObjectName("InspectorSub")
        selector.addWidget(self.selector_lbl)

        self.next_btn = QPushButton("▶")
        self.next_btn.setObjectName("ActionButton")
        self.next_btn.clicked.connect(self._next_probe)
        selector.addWidget(self.next_btn)
        selector.addStretch(1)
        top.addLayout(selector)
        outer.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.status = MetricCard("Probe Status", "—", "—", "blue")
        self.cpu = MetricCard("Probe CPU", "—", "—", "blue")
        self.memory = MetricCard("Probe RAM", "—", "—", "blue")
        self.disk = MetricCard("Probe Disk", "—", "—", "blue")

        grid.addWidget(self.status, 0, 0)
        grid.addWidget(self.cpu, 0, 1)
        grid.addWidget(self.memory, 1, 0)
        grid.addWidget(self.disk, 1, 1)
        outer.addLayout(grid)

        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setObjectName("InspectorContainer")
        outer.addWidget(self.raw, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh_now)
        self.timer.start()
        self.refresh_now()

    def reload_probe_config(self) -> None:
        self._reload_configs()

    def _reload_configs(self) -> None:
        old_id = self.current_probe.id if self.current_probe else None
        self._configs = load_probe_configs()
        if not self._configs:
            self._selected_index = 0
        elif old_id:
            for index, cfg in enumerate(self._configs):
                if cfg.id == old_id:
                    self._selected_index = index
                    break
            else:
                self._selected_index = min(self._selected_index, len(self._configs) - 1)
        else:
            self._selected_index = min(self._selected_index, len(self._configs) - 1)
        self._sync_selector()

    @property
    def current_probe(self) -> ProbeConfig | None:
        if not self._configs:
            return None
        return self._configs[self._selected_index]

    def _sync_selector(self) -> None:
        current = self.current_probe
        has_many = len(self._configs) > 1
        self.prev_btn.setEnabled(has_many)
        self.next_btn.setEnabled(has_many)
        self.settings_btn.setEnabled(current is not None)
        self.install_btn.setEnabled(current is not None)
        self.remove_btn.setEnabled(current is not None)
        if current is None:
            self.selector_lbl.setText("No probes configured")
        else:
            status = "enabled" if current.enabled else "disabled"
            self.selector_lbl.setText(f"{self._selected_index + 1}/{len(self._configs)} • {current.name} • {status}")

    def _add_probe(self) -> None:
        dlg = ProbeDeployDialog(new_probe_config(name=f"Probe {len(self._configs) + 1}"), self)
        dlg.exec()
        self.refresh_now()

    def _install_current(self) -> None:
        current = self.current_probe
        if current is None:
            self._add_probe()
            return
        dlg = ProbeDeployDialog(current, self)
        dlg.exec()
        self.refresh_now()

    def _edit_current(self) -> None:
        current = self.current_probe
        if current is None:
            return
        self._open_settings(current.id)

    def _remove_probe(self) -> None:
        current = self.current_probe
        if current is None:
            return
        confirm = PromptDialog(
            self,
            "Remove Probe",
            (
                f"Remove '{current.name}' from Laptop Health and uninstall the probe service from the monitored device?\n\n"
                "The app entry will be removed immediately. Device cleanup will then continue in the remove window."
            ),
            accent="red",
            ok_text="Remove Probe",
            cancel_text="Cancel",
        )
        if confirm.exec() != QDialog.Accepted:
            return
        remove_probe_config(current.id)
        self.refresh_now()
        dlg = ProbeRemoveDialog(current, self)
        dlg.exec()
        self.refresh_now()

    def _prev_probe(self) -> None:
        if len(self._configs) > 1:
            self._selected_index = (self._selected_index - 1) % len(self._configs)
            self.refresh_now()

    def _next_probe(self) -> None:
        if len(self._configs) > 1:
            self._selected_index = (self._selected_index + 1) % len(self._configs)
            self.refresh_now()

    def refresh_now(self) -> None:
        self._reload_configs()
        current = self.current_probe
        if current is None:
            self._apply_disabled("No probes configured")
            return
        if not current.enabled:
            self._apply_disabled(f"'{current.name}' is disabled")
            return
        if not current.url:
            self._apply_disabled(f"'{current.name}' has no probe URL configured")
            return

        w = Worker(lambda: fetch_probe_snapshot(current))
        self._workers.append(w)

        def _done(res):
            try:
                if isinstance(res, Exception):
                    self._apply_error(str(res))
                else:
                    self._apply_payload(res if isinstance(res, dict) else {})
            finally:
                try:
                    self._workers.remove(w)
                except ValueError:
                    pass

        w.signals.finished.connect(_done)
        self.pool.start(w)

    def _apply_disabled(self, message: str) -> None:
        self.status.set_values("Disabled", message, "blue")
        self.cpu.set_values("—", "No active probe", "blue")
        self.memory.set_values("—", "No active probe", "blue")
        self.disk.set_values("—", "No active probe", "blue")
        self.raw.setPlainText(message)

    def _apply_error(self, message: str) -> None:
        current = self.current_probe
        name = current.name if current else "Probe"
        self._last_payload = None
        self._last_error = message
        self.status.set_values("Offline", f"{name} • {message}", "red")
        self.cpu.set_values("—", "Probe unreachable", "blue")
        self.memory.set_values("—", "Probe unreachable", "blue")
        self.disk.set_values("—", "Probe unreachable", "blue")
        self.raw.setPlainText(message)

    def _apply_payload(self, payload: dict) -> None:
        current = self.current_probe
        if current is None:
            return
        self._last_payload = payload
        self._last_error = ""

        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        hostname = str(payload.get("hostname") or current.name)
        ip_addr = str(payload.get("ip_address") or "—")
        cpu_temp = metric_as_float(metrics.get("cpu_temp_c"))
        mem = metrics.get("memory") if isinstance(metrics.get("memory"), dict) else {}
        disk = metrics.get("disk_root") if isinstance(metrics.get("disk_root"), dict) else {}
        loadavg = metrics.get("loadavg") if isinstance(metrics.get("loadavg"), dict) else {}
        uptime_s = metric_as_float(metrics.get("uptime_seconds"))

        load_1m = metric_as_float(loadavg.get("1m"))
        mem_used = metric_as_float(mem.get("used_percent"))
        disk_used = metric_as_float(disk.get("used_percent"))

        status_sub = f"{current.name} • {hostname} • {ip_addr}"
        self.status.set_values("Online", status_sub, "green")

        cpu_big = "—" if cpu_temp is None else f"{cpu_temp:.0f}°C"
        cpu_sub = "Load: —" if load_1m is None else f"Load avg (1m): {load_1m:.2f}"
        if uptime_s is not None:
            cpu_sub += f" • Uptime: {uptime_s / 3600.0:.1f}h"
        self.cpu.set_values(cpu_big, cpu_sub, _cpu_accent(cpu_temp))

        mem_big = "—" if mem_used is None else f"{mem_used:.0f}%"
        self.memory.set_values(mem_big, "Probe RAM usage", "green" if (mem_used or 0.0) < 75 else "orange")

        disk_big = "—" if disk_used is None else f"{disk_used:.0f}%"
        self.disk.set_values(disk_big, f"Updated {time.strftime('%H:%M:%S')}", "green" if (disk_used or 0.0) < 80 else "orange")

        self.raw.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
