from __future__ import annotations

from collections import deque
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy, QHBoxLayout
from ui_v2.widgets.cards import apply_responsive_card_fonts
from ui_v2.widgets.sparkline import Sparkline


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    return max(0.0, min(1.0, float(x)))


def _state_accent(state: str) -> str:
    return {"Idle": "blue", "Load": "green", "Boost": "red"}.get(state, "green")


def _hysteresis_next_state(current: str, ghz: float) -> str:
    """
    Hysteresis thresholds to prevent flicker:
      - Idle <-> Load around ~1.2 GHz
      - Load <-> Boost around ~3.8 GHz

    We use a band (±0.1 GHz) so it won't bounce on boundaries.
    """
    # bands
    idle_to_load = 1.30
    load_to_idle = 1.10
    load_to_boost = 3.90
    boost_to_load = 3.70

    if current == "Idle":
        return "Load" if ghz >= idle_to_load else "Idle"

    if current == "Boost":
        return "Load" if ghz <= boost_to_load else "Boost"

    # current == Load (or unknown)
    if ghz <= load_to_idle:
        return "Idle"
    if ghz >= load_to_boost:
        return "Boost"
    return "Load"


class CpuDetailsCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "green")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # anti-flicker state machine
        self._state: str = "Load"
        self._pending_state: str | None = None
        self._pending_hits: int = 0
        self._freq_smoothed: float | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(8)

        # Header row with state badge
        hdr = QHBoxLayout()
        self.title = QLabel("CPU Details")
        self.title.setObjectName("CardTitle")
        hdr.addWidget(self.title)
        hdr.addStretch(1)

        self.state_badge = QLabel(self._state)
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
        self.spark.setMinimumHeight(52)
        outer.addWidget(self.spark)
        apply_responsive_card_fonts(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)

    def _apply_state(self, new_state: str) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        self.state_badge.setText(new_state)

        accent = _state_accent(new_state)
        self.setProperty("accent", accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _update_state_smoothed(self, ghz: float) -> None:
        # hysteresis gives target; then require 2 consecutive hits to switch
        target = _hysteresis_next_state(self._state, ghz)

        if target == self._state:
            self._pending_state = None
            self._pending_hits = 0
            return

        if self._pending_state != target:
            self._pending_state = target
            self._pending_hits = 1
            return

        self._pending_hits += 1
        if self._pending_hits >= 2:
            self._apply_state(target)
            self._pending_state = None
            self._pending_hits = 0

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

            self._update_state_smoothed(ghz)

            if self._freq_smoothed is None:
                self._freq_smoothed = ghz
            else:
                # Smooth the visual trend so it behaves like the calmer dashboard sparklines.
                self._freq_smoothed = (self._freq_smoothed * 0.7) + (ghz * 0.3)

            self._freq_hist.append(_norm01(self._freq_smoothed, 0.4, 4.8))
            if hasattr(self.spark, "set_points"):
                self.spark.set_points(list(self._freq_hist))
            else:
                self.spark._points = list(self._freq_hist)
                self.spark.update()
        else:
            self.freq_value.setText("— GHz")
            self._freq_smoothed = None
