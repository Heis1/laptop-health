from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget
)
from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.shadow import apply_card_shadow
from ui_v2.widgets.cpu_details_card import CpuDetailsCard

class Inspector(QFrame):
    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ----- Header -----
        hdr = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.setObjectName("InspectorToggle")
        self.toggle.setText("System Inspector")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.DownArrow)
        self.toggle.clicked.connect(self._toggle)

        hdr.addWidget(self.toggle)
        hdr.addStretch(1)

        dots = QLabel("• • •")
        dots.setObjectName("InspectorDots")
        hdr.addWidget(dots)
        outer.addLayout(hdr)

        # ----- Bordered container (this is what was missing) -----
        self.container = QFrame()
        self.container.setObjectName("InspectorContainer")
        apply_card_shadow(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # Three mini panels
        self.cpu_details = CpuDetailsCard()
        disk = MetricCard(
            "Disk Info", "Disk Info", "Root used • Journal • SMART",
            "purple", spark_points=[0.12,0.18,0.15,0.22,0.19,0.27,0.24]
        )
        wake = MetricCard(
            "Wakeup Analysis", "Wakeup Analysis", "Top offender • Suggestions • Chart",
            "orange", spark_points=[0.15,0.45,0.22,0.62,0.3,0.75,0.4]
        )

        grid.addWidget(self.cpu_details, 0, 0)
        grid.addWidget(disk, 0, 1)
        grid.addWidget(wake, 0, 2)

        container_layout.addLayout(grid)
        outer.addWidget(self.container)

    def _toggle(self):
        self.container.setVisible(self.toggle.isChecked())
        self.toggle.setArrowType(
            Qt.DownArrow if self.toggle.isChecked() else Qt.RightArrow
        )

    def update_overview(self, m) -> None:
        """Receive OverviewMetrics from DashboardPage and fan out to sub-cards."""
        try:
            w = getattr(self, "cpu_details", None)
            if w is not None and hasattr(w, "update_overview"):
                w.update_overview(m)
        except Exception:
            pass
