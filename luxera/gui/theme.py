from __future__ import annotations

from pathlib import Path

from PySide6 import QtGui, QtWidgets


def _load_qss(name: str) -> str:
    qss_path = Path(__file__).resolve().parent / name
    if not qss_path.exists():
        return ""
    return qss_path.read_text(encoding="utf-8")


def set_theme(app: QtWidgets.QApplication, mode: str = "light") -> None:
    if mode == "dark":
        app.setStyleSheet(_load_qss("styles_dark.qss"))
        return
    app.setStyleSheet(_load_qss("styles.qss"))


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    font = QtGui.QFont("Avenir Next", 10)
    app.setFont(font)
    set_theme(app, "light")
