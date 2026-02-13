from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import VerticalPlaneSpec


class VerticalPlaneForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, plane: VerticalPlaneSpec, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(plane.name)
        self.ox = QtWidgets.QDoubleSpinBox(); self.ox.setRange(-10000, 10000); self.ox.setValue(float(plane.origin[0]))
        self.oy = QtWidgets.QDoubleSpinBox(); self.oy.setRange(-10000, 10000); self.oy.setValue(float(plane.origin[1]))
        self.oz = QtWidgets.QDoubleSpinBox(); self.oz.setRange(-10000, 10000); self.oz.setValue(float(plane.origin[2]))
        self.width = QtWidgets.QDoubleSpinBox(); self.width.setRange(0.1, 500); self.width.setValue(float(plane.width))
        self.height = QtWidgets.QDoubleSpinBox(); self.height.setRange(0.1, 500); self.height.setValue(float(plane.height))
        self.nx = QtWidgets.QSpinBox(); self.nx.setRange(2, 1000); self.nx.setValue(int(plane.nx))
        self.ny = QtWidgets.QSpinBox(); self.ny.setRange(2, 1000); self.ny.setValue(int(plane.ny))
        self.azimuth = QtWidgets.QDoubleSpinBox(); self.azimuth.setRange(-360, 360); self.azimuth.setValue(float(plane.azimuth_deg))

        layout.addRow("Name", self.name)
        layout.addRow("Origin X", self.ox)
        layout.addRow("Origin Y", self.oy)
        layout.addRow("Origin Z", self.oz)
        layout.addRow("Width (m)", self.width)
        layout.addRow("Height (m)", self.height)
        layout.addRow("NX", self.nx)
        layout.addRow("NY", self.ny)
        layout.addRow("Azimuth (deg)", self.azimuth)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        self.submitted.emit(
            {
                "name": self.name.text().strip() or "Vertical Plane",
                "origin": (self.ox.value(), self.oy.value(), self.oz.value()),
                "width": float(self.width.value()),
                "height": float(self.height.value()),
                "nx": int(self.nx.value()),
                "ny": int(self.ny.value()),
                "azimuth_deg": float(self.azimuth.value()),
            }
        )
