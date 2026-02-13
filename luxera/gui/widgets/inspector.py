from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from luxera.gui.widgets.forms import EmergencyRouteForm, GridForm, LuminaireForm, OpeningForm, RoadwayForm, SceneNodeForm, VerticalPlaneForm
from luxera.project.schema import Project


class PropertiesInspector(QtWidgets.QWidget):
    apply_requested = QtCore.Signal(str, str, dict)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._title = QtWidgets.QLabel("Inspector")
        self._title.setObjectName("InspectorTitle")
        self._layout.addWidget(self._title)
        self._stack = QtWidgets.QStackedWidget()
        self._layout.addWidget(self._stack, 1)

        self._empty = QtWidgets.QLabel("Select an object from the project tree.")
        self._empty.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self._empty.setWordWrap(True)
        empty_wrap = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(empty_wrap)
        empty_layout.addWidget(self._empty)
        empty_layout.addStretch(1)
        self._stack.addWidget(empty_wrap)
        self._stack.setCurrentIndex(0)

    def clear(self) -> None:
        self._title.setText("Inspector")
        self._stack.setCurrentIndex(0)

    def set_context(self, project: Project, node_type: str, object_id: str) -> None:
        self.clear()

        form = self._build_form(project, node_type, object_id)
        if form is None:
            self._empty.setText("No editable form for this item.")
            return

        form.submitted.connect(lambda payload, nt=node_type, oid=object_id: self.apply_requested.emit(nt, oid, payload))
        self._title.setText(f"Inspector: {node_type}")
        self._stack.addWidget(form)
        self._stack.setCurrentWidget(form)

    def _build_form(self, project: Project, node_type: str, object_id: str) -> Any:
        if node_type == "luminaire":
            obj = next((x for x in project.luminaires if x.id == object_id), None)
            return LuminaireForm(project, obj) if obj else None
        if node_type == "opening":
            obj = next((x for x in project.geometry.openings if x.id == object_id), None)
            return OpeningForm(obj) if obj else None
        if node_type == "grid":
            obj = next((x for x in project.grids if x.id == object_id), None)
            return GridForm(obj) if obj else None
        if node_type == "workplane":
            obj = next((x for x in project.workplanes if x.id == object_id), None)
            return GridForm(obj) if obj else None
        if node_type == "vertical_plane":
            obj = next((x for x in project.vertical_planes if x.id == object_id), None)
            return VerticalPlaneForm(obj) if obj else None
        if node_type == "roadway":
            obj = next((x for x in project.roadways if x.id == object_id), None)
            return RoadwayForm(obj) if obj else None
        if node_type == "roadway_grid":
            obj = next((x for x in project.roadway_grids if x.id == object_id), None)
            return RoadwayForm(obj) if obj else None
        if node_type == "escape_route":
            obj = next((x for x in project.escape_routes if x.id == object_id), None)
            return EmergencyRouteForm(obj) if obj else None
        if node_type == "scene_node":
            return SceneNodeForm(project, object_id)
        return None
