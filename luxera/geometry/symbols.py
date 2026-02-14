from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from luxera.project.schema import BlockInstanceSpec, LuminaireInstance, Project, Symbol2DSpec


Point2 = Tuple[float, float]


@dataclass(frozen=True)
class SymbolPlacement:
    id: str
    symbol_id: str
    anchor: Point2
    rotation_deg: float
    scale: float
    layer_id: str


def symbol_by_id(project: Project, symbol_id: str) -> Symbol2DSpec | None:
    return next((s for s in project.symbols_2d if s.id == symbol_id), None)


def luminaire_symbol_placement(lum: LuminaireInstance, *, symbol_id: str = "LUM_SYMBOL") -> SymbolPlacement:
    x, y, _z = lum.transform.position
    yaw = (lum.transform.rotation.euler_deg or (0.0, 0.0, 0.0))[0]
    return SymbolPlacement(
        id=f"lum:{lum.id}",
        symbol_id=symbol_id,
        anchor=(float(x), float(y)),
        rotation_deg=float(yaw),
        scale=1.0,
        layer_id=str(lum.layer_id or "luminaire"),
    )


def block_symbol_placement(project: Project, inst: BlockInstanceSpec) -> SymbolPlacement:
    sym = symbol_by_id(project, inst.symbol_id)
    if sym is None:
        raise ValueError(f"Unknown symbol_id: {inst.symbol_id}")
    x = float(inst.position[0]) + float(sym.anchor[0])
    y = float(inst.position[1]) + float(sym.anchor[1])
    return SymbolPlacement(
        id=f"block:{inst.id}",
        symbol_id=str(inst.symbol_id),
        anchor=(x, y),
        rotation_deg=float(inst.rotation_deg) + float(sym.default_rotation_deg),
        scale=float(inst.scale) * float(sym.default_scale),
        layer_id=str(inst.layer_id or sym.layer_id or "symbol"),
    )


def all_symbol_placements(project: Project) -> List[SymbolPlacement]:
    out: List[SymbolPlacement] = []
    out.extend(luminaire_symbol_placement(l) for l in project.luminaires)
    for b in project.block_instances:
        try:
            out.append(block_symbol_placement(project, b))
        except ValueError:
            continue
    out.sort(key=lambda s: (s.layer_id, s.symbol_id, s.id))
    return out

