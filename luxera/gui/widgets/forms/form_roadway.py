from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import RoadwayGridSpec, RoadwaySpec


class RoadwayForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, roadway: RoadwaySpec | RoadwayGridSpec, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_grid = isinstance(roadway, RoadwayGridSpec)
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(roadway.name)
        layout.addRow("Name", self.name)

        if self._is_grid:
            rg = roadway
            self.num_lanes = QtWidgets.QSpinBox(); self.num_lanes.setRange(1, 20); self.num_lanes.setValue(int(rg.num_lanes))
            self.lane_width = QtWidgets.QDoubleSpinBox(); self.lane_width.setRange(1.0, 10.0); self.lane_width.setValue(float(rg.lane_width))
            self.road_length = QtWidgets.QDoubleSpinBox(); self.road_length.setRange(1.0, 10000.0); self.road_length.setValue(float(rg.road_length))
            self.nx = QtWidgets.QSpinBox(); self.nx.setRange(2, 10000); self.nx.setValue(int(rg.nx))
            self.ny = QtWidgets.QSpinBox(); self.ny.setRange(2, 10000); self.ny.setValue(int(rg.ny))
            self.mount_h = QtWidgets.QDoubleSpinBox(); self.mount_h.setRange(0.0, 100.0); self.mount_h.setValue(float(rg.mounting_height_m or 0.0))
            self.pole_spacing = QtWidgets.QDoubleSpinBox(); self.pole_spacing.setRange(0.0, 200.0); self.pole_spacing.setValue(float(rg.pole_spacing_m or 0.0))
            layout.addRow("Lanes", self.num_lanes)
            layout.addRow("Lane width (m)", self.lane_width)
            layout.addRow("Road length (m)", self.road_length)
            layout.addRow("NX", self.nx)
            layout.addRow("NY", self.ny)
            layout.addRow("Mount height (m)", self.mount_h)
            layout.addRow("Pole spacing (m)", self.pole_spacing)
        else:
            rw = roadway
            self.num_lanes = QtWidgets.QSpinBox(); self.num_lanes.setRange(1, 20); self.num_lanes.setValue(int(rw.num_lanes))
            self.lane_width = QtWidgets.QDoubleSpinBox(); self.lane_width.setRange(1.0, 10.0); self.lane_width.setValue(float(rw.lane_width))
            self.mount_h = QtWidgets.QDoubleSpinBox(); self.mount_h.setRange(0.0, 100.0); self.mount_h.setValue(float(rw.mounting_height_m or 0.0))
            self.pole_spacing = QtWidgets.QDoubleSpinBox(); self.pole_spacing.setRange(0.0, 200.0); self.pole_spacing.setValue(float(rw.pole_spacing_m or 0.0))
            layout.addRow("Lanes", self.num_lanes)
            layout.addRow("Lane width (m)", self.lane_width)
            layout.addRow("Mount height (m)", self.mount_h)
            layout.addRow("Pole spacing (m)", self.pole_spacing)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        payload = {
            "name": self.name.text().strip() or "Roadway",
            "num_lanes": int(self.num_lanes.value()),
            "lane_width": float(self.lane_width.value()),
            "mounting_height_m": float(self.mount_h.value()),
            "pole_spacing_m": float(self.pole_spacing.value()),
        }
        if self._is_grid:
            payload.update(
                {
                    "road_length": float(self.road_length.value()),
                    "nx": int(self.nx.value()),
                    "ny": int(self.ny.value()),
                }
            )
        self.submitted.emit(payload)
