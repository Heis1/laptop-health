from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6 import QtCore

pool = QtCore.QThreadPool.globalInstance()
pool.clear()
pool.waitForDone(1500)  # 1.5s max

try:
    # Best-effort validity check for QObject wrappers
    from shiboken6 import isValid as _is_valid  # type: ignore
except Exception:
    def _is_valid(obj: object) -> bool:
        return obj is not None


class WorkerSignals(QtCore.QObject):
    finished = QtCore.Signal(object)


class Worker(QtCore.QRunnable):
    """
    Shutdown-safe QRunnable wrapper.

    Fixes: RuntimeError: Signal source has been deleted
    by guarding emits when objects are already torn down.
    """

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

        # Prevent Qt auto-deleting the runnable while Python still references it.
        self.setAutoDelete(False)

    def _safe_emit_finished(self, payload: object) -> None:
        try:
            # If the signals QObject is already deleted, do nothing.
            if not _is_valid(self.signals):
                return
            self.signals.finished.emit(payload)
        except RuntimeError:
            # "Signal source has been deleted" / receiver deleted during shutdown.
            return
        except Exception:
            # Never crash the app on exit; print for debugging.
            traceback.print_exc()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as e:
            result = e
        self._safe_emit_finished(result)
