from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import Project


class SceneNodeForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, project: Project, scene_node_id: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._scene_node_id = scene_node_id
        layout = QtWidgets.QFormLayout(self)

        self.name = QtWidgets.QLineEdit(scene_node_id)
        self.tx = QtWidgets.QDoubleSpinBox(); self.tx.setRange(-100000.0, 100000.0); self.tx.setDecimals(4)
        self.ty = QtWidgets.QDoubleSpinBox(); self.ty.setRange(-100000.0, 100000.0); self.ty.setDecimals(4)
        self.tz = QtWidgets.QDoubleSpinBox(); self.tz.setRange(-100000.0, 100000.0); self.tz.setDecimals(4)
        self.yaw = QtWidgets.QDoubleSpinBox(); self.yaw.setRange(-360.0, 360.0); self.yaw.setDecimals(3)
        self.pitch = QtWidgets.QDoubleSpinBox(); self.pitch.setRange(-360.0, 360.0); self.pitch.setDecimals(3)
        self.roll = QtWidgets.QDoubleSpinBox(); self.roll.setRange(-360.0, 360.0); self.roll.setDecimals(3)

        self.material = QtWidgets.QComboBox()
        self.material.addItem("(unchanged)", "")
        for m in project.materials:
            self.material.addItem(m.name, m.id)

        self._init_from_project(scene_node_id)

        layout.addRow("Scene Node", QtWidgets.QLabel(scene_node_id))
        layout.addRow("Name", self.name)
        layout.addRow("X (m)", self.tx)
        layout.addRow("Y (m)", self.ty)
        layout.addRow("Z (m)", self.tz)
        layout.addRow("Yaw (deg)", self.yaw)
        layout.addRow("Pitch (deg)", self.pitch)
        layout.addRow("Roll (deg)", self.roll)
        layout.addRow("Material", self.material)
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.clicked.connect(self._submit)
        layout.addRow(apply_btn)

    def _init_from_project(self, scene_node_id: str) -> None:
        if ":" not in scene_node_id:
            return
        prefix, oid = scene_node_id.split(":", 1)
        if prefix == "room":
            obj = next((r for r in self._project.geometry.rooms if r.id == oid), None)
            if obj:
                self.name.setText(obj.name)
                self.tx.setValue(float(obj.origin[0]))
                self.ty.setValue(float(obj.origin[1]))
                self.tz.setValue(float(obj.origin[2]))
        elif prefix == "surface":
            obj = next((s for s in self._project.geometry.surfaces if s.id == oid), None)
            if obj:
                self.name.setText(obj.name)
                if obj.vertices:
                    self.tx.setValue(float(obj.vertices[0][0]))
                    self.ty.setValue(float(obj.vertices[0][1]))
                    self.tz.setValue(float(obj.vertices[0][2]))
                idx = self.material.findData(obj.material_id or "")
                if idx >= 0:
                    self.material.setCurrentIndex(idx)
        elif prefix == "opening":
            obj = next((o for o in self._project.geometry.openings if o.id == oid), None)
            if obj:
                self.name.setText(obj.name)
                if obj.vertices:
                    self.tx.setValue(float(obj.vertices[0][0]))
                    self.ty.setValue(float(obj.vertices[0][1]))
                    self.tz.setValue(float(obj.vertices[0][2]))
        elif prefix == "luminaire":
            obj = next((l for l in self._project.luminaires if l.id == oid), None)
            if obj:
                self.name.setText(obj.name)
                self.tx.setValue(float(obj.transform.position[0]))
                self.ty.setValue(float(obj.transform.position[1]))
                self.tz.setValue(float(obj.transform.position[2]))
                rot = obj.transform.rotation.euler_deg or (0.0, 0.0, 0.0)
                self.yaw.setValue(float(rot[0]))
                self.pitch.setValue(float(rot[1]))
                self.roll.setValue(float(rot[2]))
        elif prefix == "grid":
            obj = next((g for g in self._project.grids if g.id == oid), None)
            if obj:
                self.name.setText(obj.name)
                self.tx.setValue(float(obj.origin[0]))
                self.ty.setValue(float(obj.origin[1]))
                self.tz.setValue(float(obj.origin[2]))

    def _submit(self) -> None:
        self.submitted.emit(
            {
                "scene_node_id": self._scene_node_id,
                "name": self.name.text().strip() or self._scene_node_id,
                "tx": float(self.tx.value()),
                "ty": float(self.ty.value()),
                "tz": float(self.tz.value()),
                "yaw_deg": float(self.yaw.value()),
                "pitch_deg": float(self.pitch.value()),
                "roll_deg": float(self.roll.value()),
                "material_id": str(self.material.currentData() or ""),
            }
        )
