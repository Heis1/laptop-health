from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QStyle, QVBoxLayout
from ui_v2.widgets.sparkline import Sparkline

class NetworkCard(QFrame):
    def __init__(
        self,
        down_big: str = "—",
        down_unit: str = "Mbps Down",
        latency_big: str = "—",
        latency_unit: str = "ms Latency",
        left_points=None,
        right_points=None,
        parent: Optional[object] = None,
    ):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "purple")
        self.setMinimumHeight(150)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveNetIcon).pixmap(18, 18))
        hdr.addWidget(ico)

        title = QLabel("Network")
        title.setObjectName("CardTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)

        self.down_big = QLabel(down_big); self.down_big.setObjectName("CardHuge")
        self.down_unit = QLabel(down_unit); self.down_unit.setObjectName("CardSub")
        left = QVBoxLayout(); left.addWidget(self.down_big); left.addWidget(self.down_unit)

        self.lat_big = QLabel(latency_big); self.lat_big.setObjectName("CardHuge")
        self.lat_unit = QLabel(latency_unit); self.lat_unit.setObjectName("CardSub")
        right = QVBoxLayout(); right.addWidget(self.lat_big); right.addWidget(self.lat_unit)

        grid.addLayout(left, 0, 0)
        grid.addLayout(right, 0, 1)

        lp = left_points or [0.15,0.22,0.18,0.35,0.26,0.44,0.38]
        rp = right_points or [0.30,0.28,0.33,0.27,0.36,0.31,0.34]

        self.spark_down = Sparkline(lp, accent="green")
        self.spark_lat = Sparkline(rp, accent="purple")
        grid.addWidget(self.spark_down, 1, 0)
        grid.addWidget(self.spark_lat, 1, 1)

        outer.addLayout(grid)

    def set_network(self, down_mbps: float | None, latency_ms: float | None):
        self.down_big.setText("—" if down_mbps is None else f"{down_mbps:.0f}")
        self.lat_big.setText("—" if latency_ms is None else f"{latency_ms:.0f}")
