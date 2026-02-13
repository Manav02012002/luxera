from __future__ import annotations

from pathlib import Path

from luxera.gui.recent_files import add_recent_path, coerce_recent_paths


def test_coerce_recent_paths_supports_string_and_list() -> None:
    assert coerce_recent_paths(None) == []
    assert coerce_recent_paths("") == []
    assert coerce_recent_paths(" /tmp/a.json ") == ["/tmp/a.json"]
    assert coerce_recent_paths(["/a", " ", 1, "/b"]) == ["/a", "/b"]


def test_add_recent_path_deduplicates_and_caps(tmp_path: Path) -> None:
    p1 = str((tmp_path / "a.json").resolve())
    p2 = str((tmp_path / "b.json").resolve())
    p3 = str((tmp_path / "c.json").resolve())

    paths = []
    paths = add_recent_path(paths, p1, max_items=2)
    paths = add_recent_path(paths, p2, max_items=2)
    assert paths == [p2, p1]

    paths = add_recent_path(paths, p1, max_items=2)
    assert paths == [p1, p2]

    paths = add_recent_path(paths, p3, max_items=2)
    assert paths == [p3, p1]
