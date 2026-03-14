from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6 import QtCore

try:
    # shiboken validity check for QObject wrappers
    from shiboken6 import isValid as _is_valid  # type: ignore
except Exception:
    def _is_valid(obj: object) -> bool:
        return obj is not None


class QtWorkerSignals(QtCore.QObject):
    # keep the same signal names your pages already use
    result = QtCore.Signal(object)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()


class QtWorker(QtCore.QRunnable):
    """
    QRunnable used across UI v2.

    Hardening:
    - Never crash the process on shutdown if signal source/receivers are deleted.
    - Prevent Qt auto-deleting the runnable unexpectedly while Python is mid-flight.
    """

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = QtWorkerSignals()

        # Important: avoid Qt deleting the runnable object automatically.
        # (Callers may still keep refs, but this removes a whole class of weirdness.)
        self.setAutoDelete(False)

    def _safe_emit(self, sig: QtCore.SignalInstance, *args: Any) -> None:
        """
        Emit a Qt signal safely.

        During shutdown, either the signal QObject ('self.signals') or the receivers
        may already be deleted. In that case, emit() raises RuntimeError.
        We swallow it so the app exits cleanly.
        """
        try:
            if not _is_valid(self.signals):
                return
            sig.emit(*args)
        except RuntimeError:
            # "Signal source has been deleted" / receiver deleted
            return
        except Exception:
            # never crash the app because of a signal emit
            traceback.print_exc()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            r = self.fn()
            self._safe_emit(self.signals.result, r)
        except Exception as e:
            self._safe_emit(self.signals.error, str(e))
        finally:
            self._safe_emit(self.signals.finished)
