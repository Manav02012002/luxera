from __future__ import annotations

from pathlib import Path

import pytest

from luxera.parity.packs import iter_packs, load_pack, select_scenes


def _write_pack(pack_dir: Path, content: str) -> None:
    (pack_dir / "scenes").mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.yaml").write_text(content, encoding="utf-8")


def test_load_pack_valid(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    pack_dir = parity_root / "packs" / "indoor_a"
    _write_pack(
        pack_dir,
        """
id: indoor_a
title: Indoor A
version: 1
engines:
  - direct_cpu
  - radiosity_cpu
scenes:
  - id: office_01
    path: scenes/office_01.lux.json
    tags:
      - indoor
      - fast
global:
  random_seed: 7
  deterministic: true
""".strip()
        + "\n",
    )

    pack = load_pack(pack_dir)
    assert pack.id == "indoor_a"
    assert pack.title == "Indoor A"
    assert pack.version == 1
    assert pack.engines == ("direct_cpu", "radiosity_cpu")
    assert pack.random_seed == 7
    assert pack.deterministic is True
    assert len(pack.scenes) == 1
    assert pack.scenes[0].id == "office_01"
    assert pack.scenes[0].path == "scenes/office_01.lux.json"
    assert pack.scenes[0].tags == ("indoor", "fast")

    found = list(iter_packs(parity_root))
    assert found == [pack_dir.resolve()]


def test_load_pack_missing_fields(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    pack_dir = parity_root / "packs" / "broken"
    _write_pack(
        pack_dir,
        """
id: broken
title: Broken Pack
version: 1
engines:
  - direct_cpu
scenes:
  - id: office_01
    path: scenes/office_01.lux.json
global:
  deterministic: true
""".strip()
        + "\n",
    )

    with pytest.raises(ValueError, match=r"pack\.yaml.*global\.random_seed"):
        load_pack(pack_dir)


def test_select_scenes_filters(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"

    _write_pack(
        parity_root / "packs" / "p1",
        """
id: p1
title: Pack 1
version: 1
engines:
  - direct_cpu
scenes:
  - id: s1
    path: scenes/s1.lux.json
    tags: [indoor, fast]
  - id: s2
    path: scenes/s2.lux.json
    tags: [indoor, slow]
  - id: s3
    path: scenes/s3.lux.json
    tags: [road]
global:
  random_seed: 1
  deterministic: true
""".strip()
        + "\n",
    )

    _write_pack(
        parity_root / "packs" / "p2",
        """
id: p2
title: Pack 2
version: 1
engines:
  - direct_cpu
scenes:
  - id: s1
    path: scenes/alt_s1.lux.json
    tags: [indoor, fast, night]
  - id: s4
    path: scenes/s4.lux.json
    tags: [night]
global:
  random_seed: 2
  deterministic: false
""".strip()
        + "\n",
    )

    # tags_any OR filter
    selected_any = select_scenes(parity_root, {"tags_any": ["road"]})
    assert [(p.id, s.id) for p, s in selected_any] == [("p1", "s3")]

    # tags_all AND filter
    selected_all = select_scenes(parity_root, {"tags_all": ["indoor", "fast"]})
    assert [(p.id, s.id) for p, s in selected_all] == [("p1", "s1"), ("p2", "s1")]

    # include + exclude by plain scene id and qualified id, plus max_scenes limit
    selected_mix = select_scenes(
        parity_root,
        {
            "include_packs": ["p1", "p2"],
            "include_scene_ids": ["p1/s1", "s1", "s2", "p2/s4"],
            "exclude_scene_ids": ["s2", "p2/s4"],
            "max_scenes": 2,
        },
    )
    assert [(p.id, s.id) for p, s in selected_mix] == [("p1", "s1"), ("p2", "s1")]
