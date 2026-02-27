from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class PackScene:
    id: str
    path: str
    tags: Tuple[str, ...] = ()
    expected: str | None = None


@dataclass(frozen=True)
class Pack:
    id: str
    title: str
    version: int
    engines: Tuple[str, ...]
    scenes: Tuple[PackScene, ...]
    random_seed: int
    deterministic: bool
    pack_dir: Path
    global_config: Dict[str, Any]


def _err(pack_yaml: Path, message: str) -> ValueError:
    return ValueError(f"Invalid parity pack YAML at {pack_yaml}: {message}")


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [str(_parse_scalar(chunk.strip())) for chunk in inner.split(",")]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1]
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _load_yaml_fallback(text: str) -> Dict[str, Any]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    payload: Dict[str, Any] = {}

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("id:"):
            payload["id"] = _parse_scalar(line.split(":", 1)[1])
        elif line.startswith("title:"):
            payload["title"] = _parse_scalar(line.split(":", 1)[1])
        elif line.startswith("version:"):
            payload["version"] = _parse_scalar(line.split(":", 1)[1])
        elif line.startswith("engines:"):
            engines: List[Any] = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                item = lines[i][4:]
                if ":" not in item:
                    engines.append(_parse_scalar(item))
                    i += 1
                    continue
                obj: Dict[str, Any] = {}
                key, raw_val = item.split(":", 1)
                obj[key.strip()] = _parse_scalar(raw_val)
                i += 1
                while i < len(lines) and lines[i].startswith("    "):
                    k, rv = lines[i].strip().split(":", 1)
                    obj[k.strip()] = _parse_scalar(rv)
                    i += 1
                engines.append(obj)
            i -= 1
            payload["engines"] = engines
        elif line.startswith("scenes:"):
            scenes: List[Any] = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                item = lines[i][4:]
                scene: Dict[str, Any] = {}
                if ":" in item:
                    key, raw_val = item.split(":", 1)
                    scene[key.strip()] = _parse_scalar(raw_val)
                i += 1
                while i < len(lines) and lines[i].startswith("    "):
                    inner = lines[i].strip()
                    if inner.startswith("tags:"):
                        after = inner.split(":", 1)[1].strip()
                        if after:
                            parsed = _parse_scalar(after)
                            scene["tags"] = parsed if isinstance(parsed, list) else [str(parsed)]
                            i += 1
                            continue
                        tags: List[str] = []
                        i += 1
                        while i < len(lines) and lines[i].startswith("      - "):
                            tags.append(str(_parse_scalar(lines[i][8:])))
                            i += 1
                        scene["tags"] = tags
                        continue
                    k, rv = inner.split(":", 1)
                    scene[k.strip()] = _parse_scalar(rv)
                    i += 1
                scenes.append(scene)
            i -= 1
            payload["scenes"] = scenes
        elif line.startswith("global:"):
            global_cfg: Dict[str, Any] = {}
            i += 1
            while i < len(lines) and lines[i].startswith("  "):
                k, rv = lines[i].strip().split(":", 1)
                global_cfg[k.strip()] = _parse_scalar(rv)
                i += 1
            i -= 1
            payload["global"] = global_cfg
        i += 1

    return payload


def _load_yaml(pack_yaml: Path) -> Dict[str, Any]:
    text = pack_yaml.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _load_yaml_fallback(text)


def _ensure_mapping(value: Any, pack_yaml: Path, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _err(pack_yaml, f"'{field}' must be an object")
    return value


def _ensure_list(value: Any, pack_yaml: Path, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise _err(pack_yaml, f"'{field}' must be a list")
    return value


def _ensure_str(value: Any, pack_yaml: Path, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _err(pack_yaml, f"'{field}' must be a non-empty string")
    return value.strip()


def _ensure_int(value: Any, pack_yaml: Path, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _err(pack_yaml, f"'{field}' must be an integer")
    return int(value)


def _ensure_bool(value: Any, pack_yaml: Path, field: str) -> bool:
    if not isinstance(value, bool):
        raise _err(pack_yaml, f"'{field}' must be a boolean")
    return bool(value)


def load_pack(pack_dir: Path) -> Pack:
    pack_dir = Path(pack_dir).expanduser().resolve()
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.exists():
        raise _err(pack_yaml, "file not found")

    raw = _load_yaml(pack_yaml)

    pack_id = _ensure_str(raw.get("id"), pack_yaml, "id")
    title = _ensure_str(raw.get("title"), pack_yaml, "title")
    version = _ensure_int(raw.get("version"), pack_yaml, "version")

    engines_raw = _ensure_list(raw.get("engines"), pack_yaml, "engines")
    engines: List[str] = []
    for idx, engine in enumerate(engines_raw):
        engines.append(_ensure_str(engine, pack_yaml, f"engines[{idx}]"))

    scenes_raw = _ensure_list(raw.get("scenes"), pack_yaml, "scenes")
    scenes: List[PackScene] = []
    for idx, scene_raw in enumerate(scenes_raw):
        scene_obj = _ensure_mapping(scene_raw, pack_yaml, f"scenes[{idx}]")
        scene_id = _ensure_str(scene_obj.get("id"), pack_yaml, f"scenes[{idx}].id")
        scene_path = _ensure_str(scene_obj.get("path"), pack_yaml, f"scenes[{idx}].path")
        expected = scene_obj.get("expected")
        if expected is not None:
            expected = _ensure_str(expected, pack_yaml, f"scenes[{idx}].expected")

        tags_raw = scene_obj.get("tags", [])
        tags_seq = _ensure_list(tags_raw, pack_yaml, f"scenes[{idx}].tags") if tags_raw is not None else []
        tags: List[str] = []
        for tidx, tag in enumerate(tags_seq):
            tags.append(_ensure_str(tag, pack_yaml, f"scenes[{idx}].tags[{tidx}]"))
        scenes.append(PackScene(id=scene_id, path=scene_path, tags=tuple(tags), expected=expected))

    global_raw = _ensure_mapping(raw.get("global"), pack_yaml, "global")
    random_seed = _ensure_int(global_raw.get("random_seed"), pack_yaml, "global.random_seed")
    deterministic = _ensure_bool(global_raw.get("deterministic"), pack_yaml, "global.deterministic")

    return Pack(
        id=pack_id,
        title=title,
        version=version,
        engines=tuple(engines),
        scenes=tuple(scenes),
        random_seed=random_seed,
        deterministic=deterministic,
        pack_dir=pack_dir,
        global_config=dict(global_raw),
    )


def iter_packs(parity_root: Path) -> Iterator[Path]:
    root = Path(parity_root).expanduser().resolve()
    packs_dir = root / "packs"
    if not packs_dir.exists() or not packs_dir.is_dir():
        return iter(())

    candidates: List[Path] = []
    for child in sorted(packs_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if (child / "pack.yaml").exists():
            candidates.append(child)
    return iter(candidates)


def _scene_key(pack: Pack, scene: PackScene) -> str:
    return f"{pack.id}/{scene.id}"


def _as_str_list(selector: Mapping[str, Any], key: str) -> List[str]:
    raw = selector.get(key, [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"selector.{key} must be a list[str]")
    values: List[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise ValueError(f"selector.{key}[{i}] must be a string")
        values.append(item)
    return values


def select_scenes(parity_root: Path, selector: dict) -> List[tuple[Pack, PackScene]]:
    if not isinstance(selector, Mapping):
        raise ValueError("selector must be an object")

    include_packs = set(_as_str_list(selector, "include_packs"))
    tags_any = set(_as_str_list(selector, "tags_any"))
    tags_all = set(_as_str_list(selector, "tags_all"))
    include_scene_ids = set(_as_str_list(selector, "include_scene_ids"))
    exclude_scene_ids = set(_as_str_list(selector, "exclude_scene_ids"))

    max_scenes_raw = selector.get("max_scenes")
    max_scenes: int | None = None
    if max_scenes_raw is not None:
        if not isinstance(max_scenes_raw, int) or isinstance(max_scenes_raw, bool) or max_scenes_raw < 0:
            raise ValueError("selector.max_scenes must be a non-negative integer")
        max_scenes = max_scenes_raw

    out: List[tuple[Pack, PackScene]] = []
    for pack_dir in iter_packs(parity_root):
        pack = load_pack(pack_dir)
        if include_packs and pack.id not in include_packs:
            continue

        for scene in pack.scenes:
            scene_tags = set(scene.tags)
            key = _scene_key(pack, scene)

            if include_scene_ids and (scene.id not in include_scene_ids and key not in include_scene_ids):
                continue
            if scene.id in exclude_scene_ids or key in exclude_scene_ids:
                continue
            if tags_any and not (scene_tags & tags_any):
                continue
            if tags_all and not tags_all.issubset(scene_tags):
                continue

            out.append((pack, scene))
            if max_scenes is not None and len(out) >= max_scenes:
                return out

    return out
