from __future__ import annotations

from pathlib import Path

from luxera.parity.harness import test_pack


def test_parity_pack_small_indoor() -> None:
    pack = Path("luxera/scenes/refs/small_indoor")
    _, cmp = test_pack(pack)
    assert cmp.passed, "small_indoor parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_small_roadway() -> None:
    pack = Path("luxera/scenes/refs/small_roadway")
    _, cmp = test_pack(pack)
    assert cmp.passed, "small_roadway parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_roadway_luminance_metrics() -> None:
    pack = Path("luxera/scenes/refs/roadway_luminance_metrics_pack")
    _, cmp = test_pack(pack)
    assert cmp.passed, "roadway_luminance_metrics_pack parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_roadway_glare() -> None:
    pack = Path("luxera/scenes/refs/roadway_glare_pack")
    _, cmp = test_pack(pack)
    assert cmp.passed, "roadway_glare_pack parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_roadway_profile_check() -> None:
    pack = Path("luxera/scenes/refs/roadway_profile_check_pack")
    _, cmp = test_pack(pack)
    assert cmp.passed, "roadway_profile_check_pack parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_ugr_luminous_area() -> None:
    pack = Path("luxera/scenes/refs/ugr_luminous_area_pack")
    _, cmp = test_pack(pack)
    assert cmp.passed, "ugr_luminous_area_pack parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_ugr_reference_room() -> None:
    pack = Path("luxera/scenes/refs/ugr_reference_room")
    _, cmp = test_pack(pack)
    assert cmp.passed, "ugr_reference_room parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_box_room_diffuse() -> None:
    pack = Path("luxera/scenes/refs/box_room_diffuse")
    _, cmp = test_pack(pack)
    assert cmp.passed, "box_room_diffuse parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_l_room_diffuse() -> None:
    pack = Path("luxera/scenes/refs/L_room_diffuse")
    _, cmp = test_pack(pack)
    assert cmp.passed, "L_room_diffuse parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )


def test_parity_pack_occluder_room_diffuse() -> None:
    pack = Path("luxera/scenes/refs/occluder_room_diffuse")
    _, cmp = test_pack(pack)
    assert cmp.passed, "occluder_room_diffuse parity mismatches: " + "; ".join(
        f"{m.path}: {m.expected} != {m.actual}" for m in cmp.mismatches
    )
