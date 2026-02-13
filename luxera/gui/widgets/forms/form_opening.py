from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import OpeningSpec


class OpeningForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, opening: OpeningSpec, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(opening.name)
        self.is_aperture = QtWidgets.QCheckBox("Daylight aperture")
        self.is_aperture.setChecked(bool(opening.is_daylight_aperture))
        self.vt = QtWidgets.QDoubleSpinBox(); self.vt.setRange(0.01, 1.0); self.vt.setDecimals(3)
        self.vt.setValue(float(opening.visible_transmittance or 0.70))
        self.shading = QtWidgets.QDoubleSpinBox(); self.shading.setRange(0.0, 1.0); self.shading.setDecimals(3)
        self.shading.setValue(float(opening.shading_factor or 1.0))

        layout.addRow("Name", self.name)
        layout.addRow(self.is_aperture)
        layout.addRow("Visible transmittance", self.vt)
        layout.addRow("Shading factor", self.shading)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        payload = {
            "name": self.name.text().strip() or "Opening",
            "is_daylight_aperture": bool(self.is_aperture.isChecked()),
            "visible_transmittance": float(self.vt.value()),
            "shading_factor": float(self.shading.value()),
        }
        self.submitted.emit(payload)
