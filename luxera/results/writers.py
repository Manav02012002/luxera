from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List


def write_tables_json(out_dir: Path, payload: Dict[str, object]) -> Path:
    p = out_dir / "tables.json"
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return p


def write_tables_csv(out_dir: Path, rows: List[Dict[str, object]]) -> Path:
    p = out_dir / "tables.csv"
    if not rows:
        p.write_text("", encoding="utf-8")
        return p
    keys = list(rows[0].keys())
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    return p
