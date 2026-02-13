from __future__ import annotations

import numpy as np

from luxera.scene.scene_graph import SceneGraph, SceneNode, SceneTransform


def test_scene_graph_parent_child_transform_propagation_and_cache() -> None:
    g = SceneGraph()
    root = SceneNode(id="root", name="Root", type="group", local_transform=SceneTransform.from_translation((1.0, 0.0, 0.0)))
    child = SceneNode(id="child", name="Child", type="mesh", parent="root", local_transform=SceneTransform.from_translation((0.0, 2.0, 0.0)))
    g.add_node(root)
    g.add_node(child)

    w1 = g.world_transform("child")
    assert np.allclose(w1[:3, 3], np.array([1.0, 2.0, 0.0]))

    g.set_local_transform("root", SceneTransform.from_translation((3.0, 0.0, 0.0)))
    w2 = g.world_transform("child")
    assert np.allclose(w2[:3, 3], np.array([3.0, 2.0, 0.0]))

    # Deterministic cache reuse.
    w3 = g.world_transform("child")
    assert np.allclose(w2, w3)

