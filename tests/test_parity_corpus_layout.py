from __future__ import annotations

from pathlib import Path

from luxera.parity.packs import load_pack


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_parity_corpus_layout_and_pack_yaml() -> None:
    required_paths = [
        REPO_ROOT / "parity/README.md",
        REPO_ROOT / "parity/packs/indoor_basic/pack.yaml",
        REPO_ROOT / "parity/packs/indoor_basic/scenes",
        REPO_ROOT / "parity/packs/indoor_basic/assets",
        REPO_ROOT / "parity/packs/indoor_basic/expected/luxera/v1",
        REPO_ROOT / "parity/tolerances",
        REPO_ROOT / "parity/ci/fast_selection.yaml",
        REPO_ROOT / "parity/ci/nightly_selection.yaml",
        REPO_ROOT / "parity/tools",
        REPO_ROOT / "parity/.gitignore",
    ]
    for path in required_paths:
        assert path.exists(), f"Missing required parity path: {path}"

    pack = load_pack(REPO_ROOT / "parity/packs/indoor_basic")
    assert pack.id == "indoor_basic"
    assert pack.title.strip()
    assert isinstance(pack.version, int)
    assert pack.engines
    assert pack.scenes
    assert pack.scenes[0].path == "scenes/office_01.lux.json"
    assert isinstance(pack.random_seed, int)
    assert isinstance(pack.deterministic, bool)
