from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
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
        self.title = t
        hdr.addWidget(t)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.subtitle = QLabel("Selected drive analysis")
        self.subtitle.setObjectName("CardSub")
        outer.addWidget(self.subtitle)

        body = QHBoxLayout()
        body.setSpacing(18)
        outer.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        body.addLayout(left, 1)

        self.maintenance_title = QLabel("Maintenance")
        self.maintenance_title.setObjectName("CardTitle")
        left.addWidget(self.maintenance_title)

        self.summary = QLabel("—")
        self.summary.setObjectName("CardSub")
        self.summary.setWordWrap(True)
        left.addWidget(self.summary)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(8)
        body.addLayout(right, 2)

        self.top_title = QLabel("Largest folders")
        self.top_title.setObjectName("CardTitle")
        right.addWidget(self.top_title)

        self.top = QLabel("—")
        mono = QFont()
        mono.setStyleHint(QFont.Monospace)
        mono.setFixedPitch(True)
        mono.setPointSizeF(11.5)
        self.top.setFont(mono)
        self.top.setObjectName("CardSub")
        self.top.setWordWrap(True)
        self.top.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.top, 1)

    def apply(self, ins: StorageInsights):
        self.title.setText(f"{ins.top_label} Insights")
        self.subtitle.setText(f"Analysis for {ins.top_label}")
        parts = []
        if ins.journal:
            parts.append(ins.journal)
        if ins.var_log:
            parts.append(f"/var/log uses {ins.var_log}")
        if ins.apt_cache:
            parts.append(f"APT cache uses {ins.apt_cache}")
        self.summary.setText("\n".join(parts) if parts else "No cleanup-specific insight for this drive.")
        self.top_title.setText(f"Largest folders in {ins.top_label}")

        if ins.home_top:
            self.top.setText("\n".join([f"{size:>6}  {path}" for path, size in ins.home_top]))
        else:
            self.top.setText("No folder breakdown available.")
