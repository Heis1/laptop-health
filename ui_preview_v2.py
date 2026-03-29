#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from PySide6.QtWidgets import QApplication

def main() -> int:
    argv = list(sys.argv)
    if "--dev" in argv:
        os.environ["LAPTOP_HEALTH_DEV"] = "1"
        argv.remove("--dev")

    from ui_v2.app import MainWindow

    app = QApplication(argv)
    w = MainWindow()
    w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
