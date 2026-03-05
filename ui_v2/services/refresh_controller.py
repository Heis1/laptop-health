# ui_v2/services/refresh_controller.py
from __future__ import annotations

from dataclasses import dataclass
from PySide6 import QtCore


@dataclass
class RefreshState:
    busy: bool
    message: str = ""
    last_ok_epoch_ms: int | None = None


class RefreshController(QtCore.QObject):
    """
    Centralizes "busy" + debouncing so the dashboard feels responsive and you
    don't get overlapping refresh runs.

    Signals:
      stateChanged(RefreshState)
      refreshRequested()
    """
    stateChanged = QtCore.Signal(object)
    refreshRequested = QtCore.Signal()

    def __init__(self, min_interval_ms: int = 700) -> None:
        super().__init__()
        self._min_interval_ms = int(min_interval_ms)
        self._busy = False
        self._last_req_ms = 0

    def request_refresh(self, reason: str = "Refreshing…") -> None:
        now = int(QtCore.QDateTime.currentMSecsSinceEpoch())
        if self._busy:
            return
        if (now - self._last_req_ms) < self._min_interval_ms:
            return
        self._last_req_ms = now
        self._set_busy(True, reason)
        self.refreshRequested.emit()

    def mark_done_ok(self, message: str = "Updated") -> None:
        now = int(QtCore.QDateTime.currentMSecsSinceEpoch())
        self._busy = False
        self.stateChanged.emit(RefreshState(False, message, now))

    def mark_done_fail(self, message: str = "Refresh failed") -> None:
        self._busy = False
        self.stateChanged.emit(RefreshState(False, message, None))

    def _set_busy(self, busy: bool, message: str) -> None:
        self._busy = busy
        self.stateChanged.emit(RefreshState(busy, message, None))

