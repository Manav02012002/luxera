from __future__ import annotations

from typing import Iterable

from PySide6 import QtCore, QtGui

from luxera.project.schema import JobSpec, Project
from luxera.scene.build import build_scene_graph_from_project


NODE_TYPE_ROLE = QtCore.Qt.UserRole + 1
OBJECT_ID_ROLE = QtCore.Qt.UserRole + 2
ACTIONS_ROLE = QtCore.Qt.UserRole + 3


def _add_group(parent: QtGui.QStandardItem, title: str) -> QtGui.QStandardItem:
    item = QtGui.QStandardItem(title)
    item.setEditable(False)
    item.setSelectable(False)
    parent.appendRow(item)
    return item


def _add_node(parent: QtGui.QStandardItem, label: str, node_type: str, object_id: str, actions: Iterable[str]) -> None:
    item = QtGui.QStandardItem(label)
    item.setEditable(False)
    item.setData(node_type, NODE_TYPE_ROLE)
    item.setData(object_id, OBJECT_ID_ROLE)
    item.setData(list(actions), ACTIONS_ROLE)
    parent.appendRow(item)


def _job_bucket(job: JobSpec) -> str:
    kind = str(job.type).lower()
    if kind in {"direct", "radiosity"}:
        return "Indoor"
    if kind == "roadway":
        return "Roadway"
    if kind == "daylight":
        return "Daylight"
    if kind == "emergency":
        return "Emergency"
    return "Other"


def build_tree(project: Project) -> QtGui.QStandardItemModel:
    model = QtGui.QStandardItemModel()
    model.setHorizontalHeaderLabels(["Project"])
    root = model.invisibleRootItem()

    project_root = _add_group(root, project.name or "Project")
    _add_node(project_root, "Project Settings", "project", "project", actions=["edit"]) 

    levels = _add_group(project_root, "Levels")
    for level in project.geometry.levels:
        _add_node(levels, level.name, "level", level.id, actions=["edit", "duplicate", "delete"])

    rooms = _add_group(project_root, "Rooms")
    for room in project.geometry.rooms:
        _add_node(rooms, room.name, "room", room.id, actions=["edit", "duplicate", "delete"])

    openings = _add_group(project_root, "Openings")
    for opening in project.geometry.openings:
        _add_node(openings, opening.name, "opening", opening.id, actions=["edit", "duplicate", "delete"])

    luminaires = _add_group(project_root, "Luminaires")
    for luminaire in project.luminaires:
        _add_node(luminaires, luminaire.name, "luminaire", luminaire.id, actions=["edit", "duplicate", "delete"])

    calc_objects = _add_group(project_root, "Calc Objects")
    workplanes = _add_group(calc_objects, "Workplane Grids")
    for workplane in project.workplanes:
        _add_node(workplanes, workplane.name, "workplane", workplane.id, actions=["edit", "duplicate", "delete"])

    vertical_planes = _add_group(calc_objects, "Vertical Planes")
    for plane in project.vertical_planes:
        _add_node(vertical_planes, plane.name, "vertical_plane", plane.id, actions=["edit", "duplicate", "delete"])

    point_sets = _add_group(calc_objects, "Point Sets")
    for point_set in project.point_sets:
        _add_node(point_sets, point_set.name, "point_set", point_set.id, actions=["edit", "duplicate", "delete"])

    roadway_grids = _add_group(calc_objects, "Roadway Grids")
    for roadway_grid in project.roadway_grids:
        _add_node(roadway_grids, roadway_grid.name, "roadway_grid", roadway_grid.id, actions=["edit", "duplicate", "delete"])

    escape_routes = _add_group(calc_objects, "Escape Routes")
    for route in project.escape_routes:
        _add_node(escape_routes, route.name or route.id, "escape_route", route.id, actions=["edit", "duplicate", "delete"])

    jobs = _add_group(project_root, "Jobs")
    buckets = {
        "Indoor": _add_group(jobs, "Indoor"),
        "Roadway": _add_group(jobs, "Roadway"),
        "Daylight": _add_group(jobs, "Daylight"),
        "Emergency": _add_group(jobs, "Emergency"),
        "Other": _add_group(jobs, "Other"),
    }
    for job in project.jobs:
        _add_node(buckets[_job_bucket(job)], job.id, "job", job.id, actions=["edit", "duplicate", "delete", "run_job"])

    results = _add_group(project_root, "Results")
    for result in project.results:
        _add_node(results, result.job_id, "result", result.job_id, actions=["view_results", "export_report"])

    variants = _add_group(project_root, "Variants")
    for variant in project.variants:
        _add_node(variants, variant.name, "variant", variant.id, actions=["edit", "duplicate", "delete"])

    scene_group = _add_group(project_root, "Scene Graph")
    scene = build_scene_graph_from_project(project)
    node_by_id = {n.id: n for n in scene.nodes}
    item_by_id: dict[str, QtGui.QStandardItem] = {}

    def ensure_item(node_id: str) -> QtGui.QStandardItem:
        if node_id in item_by_id:
            return item_by_id[node_id]
        n = node_by_id[node_id]
        label = f"{n.name} [{n.type}]"
        item = QtGui.QStandardItem(label)
        item.setEditable(False)
        item.setData("scene_node", NODE_TYPE_ROLE)
        item.setData(n.id, OBJECT_ID_ROLE)
        item.setData([], ACTIONS_ROLE)
        item_by_id[node_id] = item
        if n.parent and n.parent in node_by_id:
            ensure_item(n.parent).appendRow(item)
        else:
            scene_group.appendRow(item)
        return item

    for node_id in sorted(node_by_id.keys()):
        ensure_item(node_id)

    return model
