from __future__ import annotations
from PySide6.QtWidgets import QWidget, QGridLayout
from ui_v2.widgets.cards import MetricCard, UpdatesCard, demo_disk_card

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cpu = MetricCard("CPU", "32°C", "2.8 GHz", "green", spark_points=[0.35,0.45,0.42,0.52,0.49,0.6,0.55])
        gpu = MetricCard("GPU", "42°C", "iGPU 3W", "blue", spark_points=[0.22,0.28,0.26,0.35,0.3,0.38,0.33])
        disk = demo_disk_card()
        updates = UpdatesCard("red")
        net = MetricCard("Network", "120 Mbps Down", "15 ms Latency", "purple", spark_points=[0.2,0.36,0.31,0.52,0.41,0.66,0.58])

        grid.addWidget(cpu, 0, 0)
        grid.addWidget(gpu, 0, 1)
        grid.addWidget(disk, 0, 2)
        grid.addWidget(updates, 1, 0, 1, 2)
        grid.addWidget(net, 1, 2)
