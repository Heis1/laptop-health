from __future__ import annotations
from PySide6.QtCore import QObject, QRunnable, Signal

class WorkerSignals(QObject):
    finished = Signal(object)

class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn()
        except Exception as e:
            result = e
        self.signals.finished.emit(result)
