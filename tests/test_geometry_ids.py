from __future__ import annotations

from luxera.derived import derived_id as derived_id_from_derived
from luxera.derived import stable_id as stable_id_from_derived
from luxera.geometry.id import derived_id, stable_id


def test_stable_id_is_deterministic_for_semantically_same_payload() -> None:
    p1 = {"a": 1, "b": [1.0, 2.0], "c": {"x": 3, "y": 4}}
    p2 = {"c": {"y": 4, "x": 3}, "b": [1.0, 2.0], "a": 1}
    assert stable_id("surface", p1) == stable_id("surface", p2)
    assert stable_id("surface", p1) == stable_id("surface", p1)


def test_derived_id_is_deterministic_and_parameter_sensitive() -> None:
    base = derived_id("room:abc", "wall", {"edge": [0, 1], "h": 3.0})
    same = derived_id("room:abc", "wall", {"h": 3.0, "edge": [0, 1]})
    changed = derived_id("room:abc", "wall", {"edge": [1, 2], "h": 3.0})
    assert base == same
    assert base != changed


def test_derived_package_re_exports_id_utilities() -> None:
    payload = {"k": "v", "n": 1}
    assert stable_id_from_derived("x", payload) == stable_id("x", payload)
    assert derived_id_from_derived("p", "k", payload) == derived_id("p", "k", payload)

