from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui_v2.services.battery import read_battery_health
from ui_v2.widgets.cards import MetricCard
from ui_v2.workers import Worker


class BatteryVisual(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.percentage = 0
        self.state = "Loading"
        self.setMinimumHeight(150)
        self.setMinimumWidth(310)

    def set_state(self, percentage: float | None, state: str, accent: str) -> None:
        self.percentage = max(0, min(100, int(round(percentage or 0))))
        self.state = state.replace("-", " ").title()
        self.accent = {"green": "#34d399", "orange": "#fb923c", "red": "#f87171", "blue": "#60a5fa"}.get(accent, "#60a5fa")
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        text = QColor("#e8f0ff")
        muted = QColor("#9fb0c6")
        outline = QColor("#49627f")
        body = self.rect().adjusted(20, 26, -46, -26)
        terminal = self.rect().adjusted(self.width() - 40, self.height() // 2 - 20, -16, -(self.height() // 2 - 20))
        painter.setPen(QPen(outline, 5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(body, 14, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(outline)
        painter.drawRoundedRect(terminal, 6, 6)
        inner = body.adjusted(10, 10, -10, -10)
        fill_width = max(0, int(inner.width() * self.percentage / 100))
        painter.setBrush(QColor(getattr(self, "accent", "#60a5fa")))
        if fill_width:
            painter.drawRoundedRect(inner.x(), inner.y(), fill_width, inner.height(), 7, 7)
        painter.setPen(text)
        font = QFont(self.font())
        font.setPointSize(25)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(body, Qt.AlignCenter, f"{self.percentage}%")
        painter.setPen(muted)
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, self.height() - 28, 0, -2), Qt.AlignHCenter | Qt.AlignVCenter, self.state)


class BatteryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        heading = QHBoxLayout()
        copy = QVBoxLayout()
        title = QLabel("Battery Health")
        title.setObjectName("PageTitle")
        copy.addWidget(title)
        subtitle = QLabel("Battery wear, charge state, cycle count, and practical care guidance from UPower.")
        subtitle.setObjectName("InspectorSub")
        subtitle.setWordWrap(True)
        copy.addWidget(subtitle)
        heading.addLayout(copy, 1)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("ActionButton")
        refresh.clicked.connect(self.refresh)
        heading.addWidget(refresh)
        outer.addLayout(heading)
        visual_card = QWidget()
        visual_card.setObjectName("Card")
        visual_l = QVBoxLayout(visual_card)
        visual_l.setContentsMargins(16, 12, 16, 12)
        visual_l.setSpacing(4)
        visual_title = QLabel("Live battery charge")
        visual_title.setObjectName("CardTitle")
        visual_l.addWidget(visual_title)
        self.battery_visual = BatteryVisual()
        visual_l.addWidget(self.battery_visual)
        outer.addWidget(visual_card)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.health = MetricCard("Battery health", "—", "Full capacity versus design capacity", "blue")
        self.charge = MetricCard("Charge", "—", "Current state", "blue")
        self.cycles = MetricCard("Charge cycles", "—", "Battery lifetime usage", "blue")
        self.capacity = MetricCard("Usable capacity", "—", "Full and design energy", "blue")
        for index, card in enumerate((self.health, self.charge, self.cycles, self.capacity)):
            grid.addWidget(card, index // 2, index % 2)
        outer.addLayout(grid)
        self.guidance = QLabel()
        self.guidance.setObjectName("CardSub")
        self.guidance.setWordWrap(True)
        outer.addWidget(self.guidance)
        outer.addStretch(1)
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self):
        worker = Worker(read_battery_health)
        worker.signals.finished.connect(self._apply)
        self.pool.start(worker)

    def _apply(self, data):
        if not isinstance(data, dict) or not data.get("available"):
            message = str((data or {}).get("error", "Battery information is unavailable."))
            for card in (self.health, self.charge, self.cycles, self.capacity):
                card.set_values("Unavailable", message, "orange")
            self.guidance.setText("Battery health needs UPower and a battery device exposed by the operating system.")
            return
        health = float(data.get("health") or 0)
        accent = "green" if health >= 85 else "orange" if health >= 70 else "red"
        self.health.set_values(f"{health:.1f}%", f"{data.get('model', 'Battery')} • {data.get('technology', 'unknown')}", accent)
        charge = data.get("percentage")
        self.charge.set_values("—" if charge is None else f"{float(charge):.0f}%", f"State: {data.get('state', 'unknown')}", "green")
        self.battery_visual.set_state(charge, str(data.get("state", "unknown")), "green" if (charge or 0) >= 35 else "orange" if (charge or 0) >= 15 else "red")
        cycles = data.get("cycles")
        self.cycles.set_values("—" if cycles is None else f"{float(cycles):.0f}", "A lower count generally indicates less cycle wear", "green")
        full, design = data.get("energy_full"), data.get("energy_design")
        self.capacity.set_values("—" if full is None else f"{float(full):.1f} Wh", "—" if design is None else f"Design capacity: {float(design):.1f} Wh", accent)
        if health >= 90:
            note = "Excellent health. Avoid sustained heat and keep software/firmware updated."
        elif health >= 80:
            note = "Healthy wear level. Avoid frequent deep discharges and prolonged heat where practical."
        else:
            note = "Noticeable wear. Consider a charge limit if your hardware supports it, and plan for a replacement if runtime no longer meets your needs."
        self.guidance.setText(note)
