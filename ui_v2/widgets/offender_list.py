from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

class OffenderList(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "orange")

        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(16, 16, 16, 16)
        self.v.setSpacing(10)

        title_row = QHBoxLayout()
        t = QLabel("Top Offenders (ctx switch delta)")
        t.setObjectName("CardTitle")
        title_row.addWidget(t)
        title_row.addStretch(1)
        self.v.addLayout(title_row)

        self.rows: list[QLabel] = []
        for _ in range(5):
            lbl = QLabel("—")
            lbl.setObjectName("CardSub")
            self.rows.append(lbl)
            self.v.addWidget(lbl)

        self.v.addStretch(1)

    def set_items(self, items: list[tuple[int, str, int]]):
        # items: [(pid, comm, delta), ...]
        if not items:
            for i, r in enumerate(self.rows):
                r.setText("—")
            return

        max_delta = max(d for _, _, d in items)
        # accent based on worst offender
        acc = "red" if max_delta > 50_000 else ("orange" if max_delta > 15_000 else "green")
        self.setProperty("accent", acc)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        for idx in range(len(self.rows)):
            if idx < len(items):
                pid, comm, delta = items[idx]
                self.rows[idx].setText(f"{idx+1}. {comm} (PID {pid})  +{delta:,}/s")
            else:
                self.rows[idx].setText("—")
