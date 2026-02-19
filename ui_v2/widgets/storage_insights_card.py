from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout

from ui_v2.services.storage_metrics import StorageInsights


class StorageInsightsCard(QFrame):
    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "purple")
        self.setMinimumHeight(190)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_FileDialogInfoView).pixmap(16, 16))
        hdr.addWidget(ico)

        t = QLabel("Storage Insights")
        t.setObjectName("CardTitle")
        hdr.addWidget(t)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.summary = QLabel("—")
        self.summary.setObjectName("CardSub")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        self.top = QLabel("—")
        self.top.setObjectName("CardSub")
        self.top.setWordWrap(True)
        outer.addWidget(self.top)

    def apply(self, ins: StorageInsights):
        parts = []
        if ins.var_log:
            parts.append(f"/var/log: {ins.var_log}")
        if ins.apt_cache:
            parts.append(f"apt cache: {ins.apt_cache}")
        self.summary.setText(" • ".join(parts) if parts else "—")

        if ins.journal:
            j = ins.journal
            self.top.setText(
                (j + "\n\n" if j else "") +
                ("Top folders in Home:\n" + "\n".join([f"  {size:>6}  {path}" for path, size in ins.home_top])
                 if ins.home_top else "Top folders in Home: —")
            )
        else:
            self.top.setText(
                ("Top folders in Home:\n" + "\n".join([f"  {size:>6}  {path}" for path, size in ins.home_top])
                 if ins.home_top else "Top folders in Home: —")
            )
