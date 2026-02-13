from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import LuminaireInstance, Project, RotationSpec, TransformSpec


class LuminaireForm(QtWidgets.QWidget):
    submitted = QtCore.Signal(dict)

    def __init__(self, project: Project, luminaire: LuminaireInstance, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._luminaire = luminaire
        layout = QtWidgets.QFormLayout(self)

        self.asset = QtWidgets.QComboBox()
        for a in project.photometry_assets:
            self.asset.addItem(a.metadata.get("filename", a.id), a.id)
        idx = self.asset.findData(luminaire.photometry_asset_id)
        if idx >= 0:
            self.asset.setCurrentIndex(idx)

        pos = luminaire.transform.position
        rot = luminaire.transform.rotation.euler_deg or (0.0, 0.0, 0.0)

        self.x = QtWidgets.QDoubleSpinBox(); self.x.setRange(-10000, 10000); self.x.setDecimals(3); self.x.setValue(float(pos[0]))
        self.y = QtWidgets.QDoubleSpinBox(); self.y.setRange(-10000, 10000); self.y.setDecimals(3); self.y.setValue(float(pos[1]))
        self.z = QtWidgets.QDoubleSpinBox(); self.z.setRange(-10000, 10000); self.z.setDecimals(3); self.z.setValue(float(pos[2]))
        self.yaw = QtWidgets.QDoubleSpinBox(); self.yaw.setRange(-360, 360); self.yaw.setDecimals(2); self.yaw.setValue(float(rot[0]))
        self.pitch = QtWidgets.QDoubleSpinBox(); self.pitch.setRange(-360, 360); self.pitch.setDecimals(2); self.pitch.setValue(float(rot[1]))
        self.roll = QtWidgets.QDoubleSpinBox(); self.roll.setRange(-360, 360); self.roll.setDecimals(2); self.roll.setValue(float(rot[2]))
        self.mounting_type = QtWidgets.QLineEdit(luminaire.mounting_type or "")
        self.mounting_height = QtWidgets.QDoubleSpinBox(); self.mounting_height.setRange(-100, 1000); self.mounting_height.setDecimals(3)
        self.mounting_height.setValue(float(luminaire.mounting_height_m or 0.0))
        self.mf = QtWidgets.QDoubleSpinBox(); self.mf.setRange(0.01, 2.0); self.mf.setDecimals(3); self.mf.setValue(float(luminaire.maintenance_factor))
        self.llf = QtWidgets.QDoubleSpinBox(); self.llf.setRange(0.01, 2.0); self.llf.setDecimals(3); self.llf.setValue(float(luminaire.flux_multiplier))

        layout.addRow("Asset", self.asset)
        layout.addRow("X (m)", self.x)
        layout.addRow("Y (m)", self.y)
        layout.addRow("Z (m)", self.z)
        layout.addRow("Yaw (deg)", self.yaw)
        layout.addRow("Pitch (deg)", self.pitch)
        layout.addRow("Roll (deg)", self.roll)
        layout.addRow("Mounting", self.mounting_type)
        layout.addRow("Mount Height (m)", self.mounting_height)
        layout.addRow("MF", self.mf)
        layout.addRow("LLF", self.llf)

        save = QtWidgets.QPushButton("Apply")
        save.clicked.connect(self._submit)
        layout.addRow(save)

    def _submit(self) -> None:
        transform = TransformSpec(
            position=(self.x.value(), self.y.value(), self.z.value()),
            rotation=RotationSpec(type="euler_zyx", euler_deg=(self.yaw.value(), self.pitch.value(), self.roll.value())),
        )
        self.submitted.emit(
            {
                "photometry_asset_id": str(self.asset.currentData()),
                "transform": transform,
                "mounting_type": self.mounting_type.text().strip() or None,
                "mounting_height_m": float(self.mounting_height.value()),
                "maintenance_factor": float(self.mf.value()),
                "flux_multiplier": float(self.llf.value()),
            }
        )
