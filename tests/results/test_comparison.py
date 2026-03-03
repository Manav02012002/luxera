from __future__ import annotations

from pathlib import Path

from luxera.results.comparison import DesignComparator, VariantResult


def _v(
    vid: str,
    name: str,
    e_avg: float,
    uniformity: float,
    compliant: bool,
    pd: float,
    ugr: float | None,
    cost: float | None,
) -> VariantResult:
    return VariantResult(
        variant_id=vid,
        variant_name=name,
        E_avg=float(e_avg),
        E_min=float(e_avg * 0.6),
        E_max=float(e_avg * 1.3),
        uniformity=float(uniformity),
        ugr_max=ugr,
        luminaire_count=10,
        total_watts=2000.0,
        power_density_W_m2=float(pd),
        leni=30.0,
        maintenance_factor=0.8,
        compliant=bool(compliant),
        cost_estimate=cost,
    )


def test_compare_two_variants() -> None:
    comp = DesignComparator()
    a = _v("A", "Variant A", 500, 0.65, True, 12.0, 19.0, 1000.0)
    b = _v("B", "Variant B", 400, 0.70, False, 10.0, 17.0, 900.0)
    report = comp.compare([a, b])
    assert report.ranked[0]["variant_id"] == "A"
    assert report.ranked[1]["score"] == 0.0


def test_normalisation() -> None:
    comp = DesignComparator()
    vals = comp._normalise([10.0, 20.0, 30.0], higher_is_better=True)
    assert vals == [0.0, 0.5, 1.0]


def test_custom_weights() -> None:
    comp = DesignComparator()
    a = _v("A", "A", 500, 0.90, True, 16.0, 17.0, 900.0)
    b = _v("B", "B", 500, 0.60, True, 10.0, 19.0, 1300.0)

    default_report = comp.compare([a, b])
    energy_heavy_report = comp.compare(
        [a, b],
        weights={"compliance": 0.1, "uniformity": 0.1, "energy_efficiency": 0.6, "ugr": 0.1, "cost": 0.1},
    )

    assert default_report.ranked[0]["variant_id"] == "A"
    assert energy_heavy_report.ranked[0]["variant_id"] == "B"
    assert default_report.ranked[0]["variant_id"] != energy_heavy_report.ranked[0]["variant_id"]


def test_comparison_table() -> None:
    comp = DesignComparator()
    variants = [
        _v("A", "Variant A", 520, 0.65, True, 12.5, 19.2, 1200.0),
        _v("B", "Variant B", 480, 0.72, True, 14.2, 17.5, 1100.0),
        _v("C", "Variant C", 510, 0.68, False, 11.8, 18.1, 1400.0),
    ]
    table = comp.generate_comparison_table(variants)
    lines = [ln for ln in table.splitlines() if ln.strip()]
    assert len(lines) >= 4
    expected_pipes = lines[0].count("|")
    assert all(ln.count("|") == expected_pipes for ln in lines)


def test_radar_chart_creation(tmp_path: Path) -> None:
    comp = DesignComparator()
    variants = [
        _v("A", "Variant A", 520, 0.65, True, 12.5, 19.2, 1200.0),
        _v("B", "Variant B", 480, 0.72, True, 14.2, 17.5, 1100.0),
    ]
    out = tmp_path / "comparison.png"
    comp.generate_comparison_chart(variants, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_single_variant() -> None:
    comp = DesignComparator()
    v = _v("A", "Only", 500, 0.70, True, 12.0, 18.0, 1000.0)
    report = comp.compare([v])
    assert len(report.ranked) == 1
    assert report.ranked[0]["score"] > 0.0
