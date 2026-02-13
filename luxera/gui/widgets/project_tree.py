from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.gui.models.project_tree_model import ACTIONS_ROLE, NODE_TYPE_ROLE, OBJECT_ID_ROLE, build_tree
from luxera.project.schema import Project


class ProjectTreeWidget(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(str, str)
    action_requested = QtCore.Signal(str, str, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QtWidgets.QTreeView()
        self.view.setHeaderHidden(False)
        self.view.setAlternatingRowColors(True)
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.view.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.view)
        self._model: QtGui.QStandardItemModel | None = None

    def set_project(self, project: Project | None) -> None:
        if project is None:
            model = QtGui.QStandardItemModel()
            model.setHorizontalHeaderLabels(["Project"])
        else:
            model = build_tree(project)
        self._model = model
        self.view.setModel(model)
        self.view.expandAll()
        if self.view.selectionModel() is not None:
            self.view.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection) -> None:  # noqa: ARG002
        indexes = selected.indexes()
        if not indexes:
            return
        idx = indexes[0]
        node_type = idx.data(NODE_TYPE_ROLE)
        object_id = idx.data(OBJECT_ID_ROLE)
        if node_type and object_id:
            self.selection_changed.emit(str(node_type), str(object_id))

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        node_type = idx.data(NODE_TYPE_ROLE)
        object_id = idx.data(OBJECT_ID_ROLE)
        actions = idx.data(ACTIONS_ROLE) or []
        if not node_type or not object_id or not actions:
            return

        menu = QtWidgets.QMenu(self)
        labels = {
            "edit": "Edit",
            "duplicate": "Duplicate",
            "delete": "Delete",
            "run_job": "Run Job",
            "export_report": "Export Report",
            "view_results": "View Results",
        }
        for action_key in actions:
            action = menu.addAction(labels.get(str(action_key), str(action_key)))
            action.triggered.connect(
                lambda checked=False, ak=str(action_key), nt=str(node_type), oid=str(object_id): self.action_requested.emit(ak, nt, oid)
            )
        menu.exec(self.view.viewport().mapToGlobal(pos))
