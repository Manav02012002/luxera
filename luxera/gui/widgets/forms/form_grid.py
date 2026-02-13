from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import CalcGrid, WorkplaneSpec


class GridForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, obj: CalcGrid | WorkplaneSpec, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_workplane = isinstance(obj, WorkplaneSpec)
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(obj.name)
        layout.addRow("Name", self.name)

        if self._is_workplane:
            wp = obj
            self.elevation = QtWidgets.QDoubleSpinBox(); self.elevation.setRange(-100, 100); self.elevation.setValue(float(wp.elevation))
            self.spacing = QtWidgets.QDoubleSpinBox(); self.spacing.setRange(0.05, 10); self.spacing.setValue(float(wp.spacing))
            self.margin = QtWidgets.QDoubleSpinBox(); self.margin.setRange(0, 10); self.margin.setValue(float(wp.margin))
            layout.addRow("Height (m)", self.elevation)
            layout.addRow("Spacing (m)", self.spacing)
            layout.addRow("Margins (m)", self.margin)
        else:
            g = obj
            self.width = QtWidgets.QDoubleSpinBox(); self.width.setRange(0.1, 500); self.width.setValue(float(g.width))
            self.height = QtWidgets.QDoubleSpinBox(); self.height.setRange(0.1, 500); self.height.setValue(float(g.height))
            self.elevation = QtWidgets.QDoubleSpinBox(); self.elevation.setRange(-100, 100); self.elevation.setValue(float(g.elevation))
            self.nx = QtWidgets.QSpinBox(); self.nx.setRange(2, 1000); self.nx.setValue(int(g.nx))
            self.ny = QtWidgets.QSpinBox(); self.ny.setRange(2, 1000); self.ny.setValue(int(g.ny))
            layout.addRow("Width (m)", self.width)
            layout.addRow("Height (m)", self.height)
            layout.addRow("Elevation (m)", self.elevation)
            layout.addRow("NX", self.nx)
            layout.addRow("NY", self.ny)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        payload = {"name": self.name.text().strip() or "Grid"}
        if self._is_workplane:
            payload.update({
                "elevation": float(self.elevation.value()),
                "spacing": float(self.spacing.value()),
                "margin": float(self.margin.value()),
            })
        else:
            payload.update({
                "width": float(self.width.value()),
                "height": float(self.height.value()),
                "elevation": float(self.elevation.value()),
                "nx": int(self.nx.value()),
                "ny": int(self.ny.value()),
            })
        self.submitted.emit(payload)
