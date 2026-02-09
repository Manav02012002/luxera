from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "out",
    "dist",
    "build",
    ".venv",
    "luxera.egg-info",
}
FILE_NAMES = {".DS_Store"}


def _remove_path(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    return True


def clean(root: Path) -> list[Path]:
    removed: list[Path] = []
    for p in root.rglob("*"):
        if p.name in FILE_NAMES:
            if _remove_path(p):
                removed.append(p)
            continue
        if p.name in DIR_NAMES and p.is_dir():
            if _remove_path(p):
                removed.append(p)
    for name in DIR_NAMES:
        top = root / name
        if _remove_path(top):
            removed.append(top)
    for name in FILE_NAMES:
        top = root / name
        if _remove_path(top):
            removed.append(top)
    return sorted(set(removed))


def main() -> int:
    removed = clean(ROOT)
    if not removed:
        print("Nothing to clean.")
        return 0
    print("Removed:")
    for p in removed:
        print(f"- {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
