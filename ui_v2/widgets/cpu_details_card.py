from __future__ import annotations

from collections import deque
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy, QHBoxLayout
from ui_v2.widgets.sparkline import Sparkline


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    return max(0.0, min(1.0, float(x)))


def _classify_power_state(ghz: float | None) -> tuple[str, str]:
    """
    Returns (label, accent)
    """
    if ghz is None:
        return ("Unknown", "green")

    if ghz < 1.2:
        return ("Idle", "blue")
    if ghz > 3.8:
        return ("Boost", "red")
    return ("Load", "green")


class CpuDetailsCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "green")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8)

        # Header row with state badge
        hdr = QHBoxLayout()
        self.title = QLabel("CPU Details")
        self.title.setObjectName("CardTitle")
        hdr.addWidget(self.title)

        hdr.addStretch(1)

        self.state_badge = QLabel("Idle")
        self.state_badge.setObjectName("Badge")
        hdr.addWidget(self.state_badge)

        outer.addLayout(hdr)

        self.line_temp = QLabel("Max Temp: —")
        self.line_temp.setObjectName("CardSub")
        outer.addWidget(self.line_temp)

        self.line_thr = QLabel("Throttle Events: —")
        self.line_thr.setObjectName("CardSub")
        outer.addWidget(self.line_thr)

        self.power_label = QLabel("Package Power")
        self.power_label.setObjectName("CardSub")
        outer.addWidget(self.power_label)

        self.power_value = QLabel("— W")
        self.power_value.setObjectName("CardBig")
        outer.addWidget(self.power_value)

        self.v_label = QLabel("Vcore")
        self.v_label.setObjectName("CardSub")
        self.v_value = QLabel("— V")
        self.v_value.setObjectName("CardSub")
        self.v_label.hide()
        self.v_value.hide()
        outer.addWidget(self.v_label)
        outer.addWidget(self.v_value)

        self.freq_label = QLabel("Frequency")
        self.freq_label.setObjectName("CardSub")
        outer.addWidget(self.freq_label)

        self.freq_value = QLabel("— GHz")
        self.freq_value.setObjectName("CardBig")
        outer.addWidget(self.freq_value)

        self._freq_hist = deque([0.0] * 36, maxlen=36)
        self.spark = Sparkline(list(self._freq_hist), accent="green")
        self.spark.setMinimumHeight(64)
        outer.addWidget(self.spark, 1)

    def update_overview(self, m) -> None:
        t = getattr(m, "cpu_temp_c", None)
        self.line_temp.setText(
            f"Max Temp: {float(t):.1f}°C" if isinstance(t, (int, float)) else "Max Temp: —"
        )

        self.line_thr.setText("Throttle Events: —")

        p = getattr(m, "cpu_package_w", None)
        self.power_value.setText(
            f"{float(p):.1f} W" if isinstance(p, (int, float)) else "— W"
        )

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

            state, accent = _classify_power_state(ghz)
            self.state_badge.setText(state)
            self.setProperty("accent", accent)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

            self._freq_hist.append(_norm01(ghz, 0.4, 4.8))
            if hasattr(self.spark, "set_points"):
                self.spark.set_points(list(self._freq_hist))
            else:
                self.spark._points = list(self._freq_hist)
                self.spark.update()
        else:
            self.freq_value.setText("— GHz")
