from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SceneTransform:
    """Stable SE(3) transform with optional decomposed TRS and 4x4 matrix form."""

    matrix: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    translation: Optional[Tuple[float, float, float]] = None
    rotation_matrix: Optional[np.ndarray] = None
    scale: Optional[Tuple[float, float, float]] = None

    def __post_init__(self) -> None:
        self.matrix = np.asarray(self.matrix, dtype=float).reshape(4, 4)
        if self.translation is not None or self.rotation_matrix is not None or self.scale is not None:
            t = np.array(self.translation or (0.0, 0.0, 0.0), dtype=float).reshape(3)
            r = np.asarray(self.rotation_matrix if self.rotation_matrix is not None else np.eye(3, dtype=float), dtype=float).reshape(3, 3)
            s = np.array(self.scale or (1.0, 1.0, 1.0), dtype=float).reshape(3)
            m = np.eye(4, dtype=float)
            m[:3, :3] = r @ np.diag(s)
            m[:3, 3] = t
            self.matrix = m

    @classmethod
    def identity(cls) -> "SceneTransform":
        return cls(matrix=np.eye(4, dtype=float))

    @classmethod
    def from_translation(cls, xyz: Tuple[float, float, float]) -> "SceneTransform":
        m = np.eye(4, dtype=float)
        m[:3, 3] = np.array(xyz, dtype=float)
        return cls(matrix=m, translation=xyz)

    def compose(self, other: "SceneTransform") -> "SceneTransform":
        return SceneTransform(matrix=self.matrix @ other.matrix)


@dataclass
class SceneNode:
    id: str
    name: str
    type: str
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    local_transform: SceneTransform = field(default_factory=SceneTransform.identity)
    world_transform_cache: Optional[np.ndarray] = None
    mesh_ref: Optional[str] = None
    material_ref: Optional[str] = None
    # Optional reference to shared authored geometry for instancing.
    instance_ref: Optional[str] = None
    tags: Dict[str, object] = field(default_factory=dict)
    # Backward-compatible payload accepted by existing importers.
    transform: Dict[str, object] = field(default_factory=lambda: {"position": (0.0, 0.0, 0.0)})

    def __post_init__(self) -> None:
        if self.local_transform.matrix.shape != (4, 4):
            self.local_transform = SceneTransform.identity()
        if self.transform:
            pos = self.transform.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) == 3 and np.allclose(self.local_transform.matrix, np.eye(4, dtype=float)):
                self.local_transform = SceneTransform.from_translation((float(pos[0]), float(pos[1]), float(pos[2])))


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    boundary_polygon: List[Tuple[float, float]]
    height: float
    surface_refs: List[str] = field(default_factory=list)


@dataclass
class SceneGraph:
    nodes: List[SceneNode] = field(default_factory=list)
    rooms: List[Room] = field(default_factory=list)

    def _node_map(self) -> Dict[str, SceneNode]:
        return {n.id: n for n in self.nodes}

    def get_node(self, node_id: str) -> SceneNode:
        lookup = self._node_map()
        if node_id not in lookup:
            raise KeyError(f"Unknown scene node: {node_id}")
        return lookup[node_id]

    def add_node(self, node: SceneNode) -> None:
        if any(n.id == node.id for n in self.nodes):
            raise ValueError(f"Scene node already exists: {node.id}")
        self.nodes.append(node)
        if node.parent:
            parent = self.get_node(node.parent)
            if node.id not in parent.children:
                parent.children.append(node.id)
        self.invalidate_world_cache(node.id)

    def set_parent(self, node_id: str, parent_id: Optional[str]) -> None:
        node = self.get_node(node_id)
        if node.parent == parent_id:
            return
        if node.parent is not None:
            old_parent = self.get_node(node.parent)
            old_parent.children = [c for c in old_parent.children if c != node_id]
        node.parent = parent_id
        if parent_id is not None:
            parent = self.get_node(parent_id)
            if node_id not in parent.children:
                parent.children.append(node_id)
        self.invalidate_world_cache(node_id)

    def set_local_transform(self, node_id: str, transform: SceneTransform) -> None:
        node = self.get_node(node_id)
        node.local_transform = transform
        node.transform = {"position": tuple(float(x) for x in transform.matrix[:3, 3])}
        self.invalidate_world_cache(node_id)

    def invalidate_world_cache(self, node_id: str) -> None:
        node = self.get_node(node_id)
        stack = [node]
        while stack:
            cur = stack.pop()
            cur.world_transform_cache = None
            for cid in cur.children:
                stack.append(self.get_node(cid))

    def world_transform(self, node_id: str) -> np.ndarray:
        node = self.get_node(node_id)
        if node.world_transform_cache is not None:
            return np.asarray(node.world_transform_cache, dtype=float)
        if node.parent is None:
            world = np.asarray(node.local_transform.matrix, dtype=float)
        else:
            world = self.world_transform(node.parent) @ node.local_transform.matrix
        node.world_transform_cache = np.asarray(world, dtype=float)
        return world
