from __future__ import annotations

from collections import deque
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy
from ui_v2.widgets.sparkline import Sparkline


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


class CpuDetailsCard(QFrame):
    """Mini inspector panel: Max temp + package power + frequency sparkline. Voltage row hidden if unavailable."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "green")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8)

        self.title = QLabel("CPU Details")
        self.title.setObjectName("CardTitle")
        outer.addWidget(self.title)

        self.line_temp = QLabel("Max Temp: —")
        self.line_temp.setObjectName("CardSub")
        outer.addWidget(self.line_temp)

        self.line_thr = QLabel("Throttle Events: —")
        self.line_thr.setObjectName("CardSub")
        outer.addWidget(self.line_thr)

        # Package power: label (sub) + value (big-ish)
        self.power_label = QLabel("Package Power")
        self.power_label.setObjectName("CardSub")
        outer.addWidget(self.power_label)

        self.power_value = QLabel("— W")
        self.power_value.setObjectName("CardBig")
        outer.addWidget(self.power_value)

        # Optional voltage (hidden unless present)
        self.v_label = QLabel("Vcore")
        self.v_label.setObjectName("CardSub")
        self.v_value = QLabel("— V")
        self.v_value.setObjectName("CardSub")
        self.v_label.hide()
        self.v_value.hide()
        outer.addWidget(self.v_label)
        outer.addWidget(self.v_value)

        # Frequency: label + numeric value + chart
        self.freq_label = QLabel("Frequency")
        self.freq_label.setObjectName("CardSub")
        outer.addWidget(self.freq_label)

        self.freq_value = QLabel("— GHz")
        self.freq_value.setObjectName("CardBig")  # big white number
        outer.addWidget(self.freq_value)

        self._freq_hist = deque([0.0] * 36, maxlen=36)
        self.spark = Sparkline(list(self._freq_hist), accent="green")
        self.spark.setMinimumHeight(64)
        outer.addWidget(self.spark, 1)

    def update_overview(self, m) -> None:
        t = getattr(m, "cpu_temp_c", None)
        if isinstance(t, (int, float)):
            self.line_temp.setText(f"Max Temp: {float(t):.1f}°C")
        else:
            self.line_temp.setText("Max Temp: —")

        # throttle not wired yet
        self.line_thr.setText("Throttle Events: —")

        p = getattr(m, "cpu_package_w", None)
        if isinstance(p, (int, float)):
            self.power_value.setText(f"{float(p):.1f} W")
        else:
            self.power_value.setText("— W")

        v = getattr(m, "cpu_vcore_v", None)
        if isinstance(v, (int, float)):
            self.v_label.show()
            self.v_value.show()
            self.v_value.setText(f"{float(v):.3f} V")
        else:
            self.v_label.hide()
            self.v_value.hide()

        f = getattr(m, "cpu_freq_ghz", None)
        if isinstance(f, (int, float)):
            ghz = float(f)
            self.freq_value.setText(f"{ghz:.2f} GHz")
            self._freq_hist.append(_norm01(ghz, 0.4, 4.8))
            try:
                if hasattr(self.spark, "set_points"):
                    self.spark.set_points(list(self._freq_hist))
                else:
                    self.spark._points = list(self._freq_hist)
                    self.spark.update()
            except Exception:
                pass
        else:
            self.freq_value.setText("— GHz")
