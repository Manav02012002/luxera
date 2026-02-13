from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

Point2 = Tuple[float, float]


@dataclass(frozen=True)
class RoundtripPolyline:
    layer: str
    vertices: List[Point2] = field(default_factory=list)
    bulges: List[float] = field(default_factory=list)
    closed: bool = False


@dataclass(frozen=True)
class RoundtripLine:
    layer: str
    start: Point2
    end: Point2


@dataclass(frozen=True)
class RoundtripDoc:
    polylines: List[RoundtripPolyline] = field(default_factory=list)
    lines: List[RoundtripLine] = field(default_factory=list)


def _pairs(text: str) -> List[Tuple[int, str]]:
    raw = [ln.rstrip("\r") for ln in text.splitlines()]
    out: List[Tuple[int, str]] = []
    i = 0
    while i + 1 < len(raw):
        c = raw[i].strip()
        v = raw[i + 1].strip()
        i += 2
        if not c:
            continue
        try:
            out.append((int(c), v))
        except ValueError:
            continue
    return out


def _entity_chunks(pairs: Sequence[Tuple[int, str]]) -> List[List[Tuple[int, str]]]:
    chunks: List[List[Tuple[int, str]]] = []
    in_entities = False
    cur: List[Tuple[int, str]] = []

    for code, val in pairs:
        if code == 0 and val == "SECTION":
            continue
        if code == 2 and val == "ENTITIES":
            in_entities = True
            continue
        if in_entities and code == 0 and val == "ENDSEC":
            if cur:
                chunks.append(cur)
            break
        if not in_entities:
            continue

        if code == 0:
            if cur:
                chunks.append(cur)
            cur = [(code, val)]
        else:
            cur.append((code, val))

    return chunks


def _parse_lwpolyline(chunk: Sequence[Tuple[int, str]]) -> RoundtripPolyline:
    layer = "0"
    closed = False
    verts: List[Point2] = []
    bulges: List[float] = []

    x_pending: float | None = None
    y_pending: float | None = None
    b_pending: float = 0.0

    def flush_vertex() -> None:
        nonlocal x_pending, y_pending, b_pending
        if x_pending is None or y_pending is None:
            return
        verts.append((float(x_pending), float(y_pending)))
        bulges.append(float(b_pending))
        x_pending = None
        y_pending = None
        b_pending = 0.0

    for code, val in chunk:
        if code == 8:
            layer = val or "0"
        elif code == 70:
            try:
                closed = (int(val) & 1) == 1
            except ValueError:
                closed = False
        elif code == 10:
            flush_vertex()
            try:
                x_pending = float(val)
            except ValueError:
                x_pending = 0.0
        elif code == 20:
            try:
                y_pending = float(val)
            except ValueError:
                y_pending = 0.0
        elif code == 42:
            try:
                b_pending = float(val)
            except ValueError:
                b_pending = 0.0

    flush_vertex()
    if len(bulges) < len(verts):
        bulges.extend([0.0] * (len(verts) - len(bulges)))

    return RoundtripPolyline(layer=str(layer), vertices=verts, bulges=bulges[: len(verts)], closed=bool(closed))


def _parse_line(chunk: Sequence[Tuple[int, str]]) -> RoundtripLine | None:
    layer = "0"
    x0 = y0 = x1 = y1 = 0.0
    for code, val in chunk:
        if code == 8:
            layer = val or "0"
        elif code == 10:
            x0 = float(val)
        elif code == 20:
            y0 = float(val)
        elif code == 11:
            x1 = float(val)
        elif code == 21:
            y1 = float(val)
    return RoundtripLine(layer=str(layer), start=(x0, y0), end=(x1, y1))


def load_roundtrip_dxf(path: str | Path) -> RoundtripDoc:
    p = Path(path).expanduser().resolve()
    pairs = _pairs(p.read_text(encoding="utf-8", errors="replace"))
    chunks = _entity_chunks(pairs)
    polylines: List[RoundtripPolyline] = []
    lines: List[RoundtripLine] = []

    for ch in chunks:
        etype = ch[0][1] if ch and ch[0][0] == 0 else ""
        if etype == "LWPOLYLINE":
            poly = _parse_lwpolyline(ch)
            if len(poly.vertices) >= 2:
                polylines.append(poly)
        elif etype == "LINE":
            line = _parse_line(ch)
            if line is not None:
                lines.append(line)

    return RoundtripDoc(polylines=polylines, lines=lines)


def _f(v: float) -> str:
    return f"{float(v):.12g}"


def _write_layers(layers: Iterable[str]) -> str:
    out = "0\nTABLE\n2\nLAYER\n70\n0\n"
    for layer in sorted({str(x) for x in layers if str(x)}):
        out += f"0\nLAYER\n2\n{layer}\n70\n0\n62\n7\n6\nCONTINUOUS\n"
    out += "0\nENDTAB\n"
    return out


def _write_lwpolyline(poly: RoundtripPolyline) -> str:
    out = (
        "0\nLWPOLYLINE\n"
        f"8\n{poly.layer}\n"
        f"90\n{len(poly.vertices)}\n"
        f"70\n{1 if poly.closed else 0}\n"
    )
    for i, (x, y) in enumerate(poly.vertices):
        b = float(poly.bulges[i]) if i < len(poly.bulges) else 0.0
        out += f"10\n{_f(x)}\n20\n{_f(y)}\n"
        if abs(b) > 0.0:
            out += f"42\n{_f(b)}\n"
    return out


def _write_line(line: RoundtripLine) -> str:
    return (
        "0\nLINE\n"
        f"8\n{line.layer}\n"
        f"10\n{_f(line.start[0])}\n20\n{_f(line.start[1])}\n30\n0.0\n"
        f"11\n{_f(line.end[0])}\n21\n{_f(line.end[1])}\n31\n0.0\n"
    )


def export_roundtrip_dxf(doc: RoundtripDoc, out_path: str | Path) -> Path:
    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    layers = ["0"]
    layers.extend(p.layer for p in doc.polylines)
    layers.extend(l.layer for l in doc.lines)

    content = "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"
    content += "0\nSECTION\n2\nTABLES\n"
    content += _write_layers(layers)
    content += "0\nENDSEC\n"
    content += "0\nSECTION\n2\nENTITIES\n"
    for p in doc.polylines:
        content += _write_lwpolyline(p)
    for l in doc.lines:
        content += _write_line(l)
    content += "0\nENDSEC\n0\nEOF\n"

    out.write_text(content, encoding="utf-8")
    return out


def roundtrip_dxf(src_path: str | Path, out_path: str | Path) -> Path:
    doc = load_roundtrip_dxf(src_path)
    return export_roundtrip_dxf(doc, out_path)
