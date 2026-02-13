from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import EscapeRouteSpec


class EmergencyRouteForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, route: EscapeRouteSpec, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(route.name or route.id)
        self.width = QtWidgets.QDoubleSpinBox(); self.width.setRange(0.1, 20.0); self.width.setValue(float(route.width_m))
        self.spacing = QtWidgets.QDoubleSpinBox(); self.spacing.setRange(0.05, 10.0); self.spacing.setValue(float(route.spacing_m))
        self.margin = QtWidgets.QDoubleSpinBox(); self.margin.setRange(0.0, 10.0); self.margin.setValue(float(route.end_margin_m))
        self.height = QtWidgets.QDoubleSpinBox(); self.height.setRange(-10.0, 20.0); self.height.setValue(float(route.height_m))

        self.poly = QtWidgets.QPlainTextEdit()
        self.poly.setPlaceholderText("One point per line: x,y,z")
        lines = [f"{p[0]},{p[1]},{p[2]}" for p in route.polyline]
        self.poly.setPlainText("\n".join(lines))

        layout.addRow("Name", self.name)
        layout.addRow("Width (m)", self.width)
        layout.addRow("Spacing (m)", self.spacing)
        layout.addRow("End margin (m)", self.margin)
        layout.addRow("Height (m)", self.height)
        layout.addRow("Polyline", self.poly)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        points = []
        for raw in self.poly.toPlainText().splitlines():
            if not raw.strip():
                continue
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) != 3:
                continue
            try:
                points.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                continue
        payload = {
            "name": self.name.text().strip() or "Route",
            "polyline": points,
            "width_m": float(self.width.value()),
            "spacing_m": float(self.spacing.value()),
            "end_margin_m": float(self.margin.value()),
            "height_m": float(self.height.value()),
        }
        self.submitted.emit(payload)
