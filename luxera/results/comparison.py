from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from luxera.project.schema import Project


@dataclass(frozen=True)
class VariantResult:
    variant_id: str
    variant_name: str
    E_avg: float
    E_min: float
    E_max: float
    uniformity: float
    ugr_max: Optional[float]
    luminaire_count: int
    total_watts: float
    power_density_W_m2: float
    leni: Optional[float]
    maintenance_factor: float
    compliant: bool
    cost_estimate: Optional[float]


@dataclass(frozen=True)
class ComparisonReport:
    ranked: List[Dict[str, Any]]
    weights: Dict[str, float]
    best_variant_id: Optional[str]
    best_variant_name: Optional[str]


class DesignComparator:
    """
    Compare multiple design variants and rank them.
    """

    def compare(
        self,
        variants: List[VariantResult],
        weights: Optional[Dict[str, float]] = None,
    ) -> ComparisonReport:
        if not variants:
            return ComparisonReport(ranked=[], weights={}, best_variant_id=None, best_variant_name=None)

        default_weights = {
            "compliance": 0.30,
            "uniformity": 0.20,
            "energy_efficiency": 0.20,
            "ugr": 0.15,
            "cost": 0.15,
        }
        eff_weights = dict(default_weights)
        if weights:
            for k, v in weights.items():
                if k in eff_weights:
                    eff_weights[k] = max(0.0, float(v))

        total_w = sum(eff_weights.values())
        if total_w <= 1e-12:
            eff_weights = dict(default_weights)
            total_w = sum(eff_weights.values())
        eff_weights = {k: v / total_w for k, v in eff_weights.items()}

        uniformity_scores = self._normalise([float(v.uniformity) for v in variants], higher_is_better=True)
        energy_scores = self._normalise([float(v.power_density_W_m2) for v in variants], higher_is_better=False)

        ugr_values = [float(v.ugr_max) if v.ugr_max is not None else np.nan for v in variants]
        has_ugr = np.isfinite(np.asarray(ugr_values, dtype=float))
        if np.any(has_ugr):
            valid = [float(x) for x in ugr_values if np.isfinite(x)]
            norm_valid = self._normalise(valid, higher_is_better=False)
            it = iter(norm_valid)
            ugr_scores = [next(it) if np.isfinite(x) else 0.5 for x in ugr_values]
        else:
            ugr_scores = [0.5 for _ in variants]

        cost_values = [float(v.cost_estimate) if v.cost_estimate is not None else np.nan for v in variants]
        has_cost = np.isfinite(np.asarray(cost_values, dtype=float))
        if np.any(has_cost):
            valid = [float(x) for x in cost_values if np.isfinite(x)]
            norm_valid = self._normalise(valid, higher_is_better=False)
            it = iter(norm_valid)
            cost_scores = [next(it) if np.isfinite(x) else 0.5 for x in cost_values]
        else:
            cost_scores = [0.5 for _ in variants]

        ranked: List[Dict[str, Any]] = []
        for idx, v in enumerate(variants):
            compliance_score = 1.0 if bool(v.compliant) else 0.0
            breakdown = {
                "compliance": compliance_score,
                "uniformity": float(uniformity_scores[idx]),
                "energy_efficiency": float(energy_scores[idx]),
                "ugr": float(ugr_scores[idx]),
                "cost": float(cost_scores[idx]),
            }
            if not v.compliant:
                score = 0.0
            else:
                score = float(sum(eff_weights[k] * breakdown[k] for k in eff_weights.keys()))

            ranked.append(
                {
                    "variant_id": v.variant_id,
                    "variant_name": v.variant_name,
                    "score": score,
                    "breakdown": breakdown,
                    "variant": v,
                }
            )

        ranked.sort(key=lambda r: (float(r["score"]), float(r["variant"].E_avg)), reverse=True)

        best = ranked[0] if ranked else None
        return ComparisonReport(
            ranked=ranked,
            weights=eff_weights,
            best_variant_id=(best["variant_id"] if best else None),
            best_variant_name=(best["variant_name"] if best else None),
        )

    def _normalise(self, values: List[float], higher_is_better: bool) -> List[float]:
        """Normalise values to [0,1]. Handle single-variant edge case."""
        if not values:
            return []
        if len(values) == 1:
            return [1.0]
        vmin = min(values)
        vmax = max(values)
        if abs(vmax - vmin) <= 1e-12:
            return [1.0 for _ in values]
        if higher_is_better:
            return [float((v - vmin) / (vmax - vmin)) for v in values]
        return [float((vmax - v) / (vmax - vmin)) for v in values]

    def generate_comparison_table(self, variants: List[VariantResult]) -> str:
        report = self.compare(variants)
        ranked_by_id = {r["variant_id"]: r for r in report.ranked}

        headers = ["Criterion", *[v.variant_name for v in variants], "Best"]
        lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["-" * (len(h) + 2) for h in headers]) + "|",
        ]

        def _best_idx(vals: List[float], higher: bool) -> Optional[int]:
            if not vals:
                return None
            return int(np.argmax(vals)) if higher else int(np.argmin(vals))

        rows: List[tuple[str, List[str], Optional[int]]] = []
        e_avg_vals = [float(v.E_avg) for v in variants]
        rows.append(("E_avg (lux)", [f"{v.E_avg:.1f}" for v in variants], _best_idx(e_avg_vals, True)))

        uni_vals = [float(v.uniformity) for v in variants]
        rows.append(("Uniformity", [f"{v.uniformity:.3f}" for v in variants], _best_idx(uni_vals, True)))

        ugr_vals = [float(v.ugr_max) if v.ugr_max is not None else 1e9 for v in variants]
        rows.append(("UGR", [f"{v.ugr_max:.2f}" if v.ugr_max is not None else "N/A" for v in variants], _best_idx(ugr_vals, False)))

        p_vals = [float(v.power_density_W_m2) for v in variants]
        rows.append(("Power (W/m²)", [f"{v.power_density_W_m2:.2f}" for v in variants], _best_idx(p_vals, False)))

        leni_vals = [float(v.leni) if v.leni is not None else 1e9 for v in variants]
        rows.append(("LENI", [f"{v.leni:.2f}" if v.leni is not None else "N/A" for v in variants], _best_idx(leni_vals, False)))

        rows.append(("Compliant", ["✓" if v.compliant else "✗" for v in variants], None))

        score_vals = [float(ranked_by_id[v.variant_id]["score"]) for v in variants]
        rows.append(("SCORE", [f"{s:.2f}" for s in score_vals], _best_idx(score_vals, True)))

        for name, values, best_idx in rows:
            best_name = variants[best_idx].variant_name if best_idx is not None else "-"
            lines.append("| " + " | ".join([name, *values, best_name]) + " |")

        return "\n".join(lines)

    def generate_comparison_chart(
        self,
        variants: List[VariantResult],
        output_path: Path,
    ):
        report = self.compare(variants)
        if not report.ranked:
            raise ValueError("No variants to chart")

        criteria = ["Compliance", "Uniformity", "Energy", "UGR", "Cost"]
        n = len(criteria)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]

        fig = plt.figure(figsize=(7.0, 7.0), dpi=150)
        ax = fig.add_subplot(111, polar=True)

        for row in report.ranked:
            b = row["breakdown"]
            vals = [float(b["compliance"]), float(b["uniformity"]), float(b["energy_efficiency"]), float(b["ugr"]), float(b["cost"])]
            vals += vals[:1]
            ax.plot(angles, vals, linewidth=2, label=f"{row['variant_name']} ({row['score']:.2f})")
            ax.fill(angles, vals, alpha=0.15)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(criteria)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_ylim(0.0, 1.0)
        ax.set_title("Design Variant Comparison")
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15), fontsize=8)

        output_path = Path(output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), bbox_inches="tight")
        plt.close(fig)


class VariantRunner:
    """
    Run calculations for all project variants and collect results.
    """

    def run_all_variants(self, project: Project) -> List[VariantResult]:
        """
        For each variant defined in project.variants:
        1. Apply the variant's diff operations to get modified project.
        2. Run the full calculation pipeline.
        3. Collect results into VariantResult.
        4. Return list.
        """
        from luxera.project.runner import run_job_in_memory
        from luxera.project.variants import _apply_variant

        if not project.variants:
            return []
        if not project.jobs:
            raise ValueError("Project has no jobs; cannot run variant comparison")

        base = copy.deepcopy(project)
        job_id = base.jobs[0].id
        out: List[VariantResult] = []

        for variant in base.variants:
            vp = _apply_variant(base, variant)
            ref = run_job_in_memory(vp, job_id)
            summary = dict(ref.summary) if isinstance(ref.summary, dict) else {}

            e_avg = self._num(summary, "mean_lux", "avg_illuminance", "E_avg", default=0.0)
            e_min = self._num(summary, "min_lux", "E_min", default=0.0)
            e_max = self._num(summary, "max_lux", "E_max", default=0.0)
            uniformity = self._num(summary, "uniformity_ratio", "U0", default=0.0)
            ugr_max = self._opt_num(summary, "ugr_worst_case", "ugr_max")
            leni = self._opt_num(summary, "leni", "LENI")
            total_watts = self._estimate_total_watts(vp, summary)
            area_m2 = self._room_area(vp)
            power_density = total_watts / area_m2 if area_m2 > 1e-9 else 0.0
            maint = self._avg_maintenance_factor(vp)
            compliant = self._is_compliant(summary)
            cost = self._opt_num(summary, "cost_estimate", "cost")

            out.append(
                VariantResult(
                    variant_id=variant.id,
                    variant_name=variant.name,
                    E_avg=float(e_avg),
                    E_min=float(e_min),
                    E_max=float(e_max),
                    uniformity=float(uniformity),
                    ugr_max=(float(ugr_max) if ugr_max is not None else None),
                    luminaire_count=len(vp.luminaires),
                    total_watts=float(total_watts),
                    power_density_W_m2=float(power_density),
                    leni=(float(leni) if leni is not None else None),
                    maintenance_factor=float(maint),
                    compliant=bool(compliant),
                    cost_estimate=(float(cost) if cost is not None else None),
                )
            )

        return out

    @staticmethod
    def _num(summary: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
        for k in keys:
            v = summary.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return float(default)

    @staticmethod
    def _opt_num(summary: Dict[str, Any], *keys: str) -> Optional[float]:
        for k in keys:
            v = summary.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None

    @staticmethod
    def _room_area(project: Project) -> float:
        if project.geometry.rooms:
            room = project.geometry.rooms[0]
            return max(float(room.width) * float(room.length), 0.0)
        return 0.0

    @staticmethod
    def _avg_maintenance_factor(project: Project) -> float:
        if not project.luminaires:
            return 1.0
        vals = [float(getattr(l, "maintenance_factor", 1.0) or 1.0) for l in project.luminaires]
        return float(sum(vals) / max(len(vals), 1))

    @staticmethod
    def _estimate_total_watts(project: Project, summary: Dict[str, Any]) -> float:
        direct = summary.get("total_watts")
        if isinstance(direct, (int, float)):
            return float(direct)

        assets = {a.id: a for a in project.photometry_assets}
        total = 0.0
        for lum in project.luminaires:
            asset = assets.get(lum.photometry_asset_id)
            per = None
            if asset is not None and isinstance(asset.metadata, dict):
                for k in ("power_w", "watts", "input_watts"):
                    v = asset.metadata.get(k)
                    if isinstance(v, (int, float)):
                        per = float(v)
                        break
            if per is None:
                per = 50.0
            total += per * float(getattr(lum, "flux_multiplier", 1.0) or 1.0)
        return float(total)

    @staticmethod
    def _is_compliant(summary: Dict[str, Any]) -> bool:
        c = summary.get("compliance")
        if isinstance(c, dict):
            status = c.get("status")
            if isinstance(status, str):
                return status.strip().upper() == "PASS"
            if isinstance(c.get("pass"), bool):
                return bool(c.get("pass"))
        if isinstance(c, bool):
            return c
        return True


def report_to_jsonable(report: ComparisonReport) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for r in report.ranked:
        v: VariantResult = r["variant"]
        rows.append(
            {
                "variant_id": r["variant_id"],
                "variant_name": r["variant_name"],
                "score": float(r["score"]),
                "breakdown": dict(r["breakdown"]),
                "metrics": {
                    "E_avg": v.E_avg,
                    "E_min": v.E_min,
                    "E_max": v.E_max,
                    "uniformity": v.uniformity,
                    "ugr_max": v.ugr_max,
                    "luminaire_count": v.luminaire_count,
                    "total_watts": v.total_watts,
                    "power_density_W_m2": v.power_density_W_m2,
                    "leni": v.leni,
                    "maintenance_factor": v.maintenance_factor,
                    "compliant": v.compliant,
                    "cost_estimate": v.cost_estimate,
                },
            }
        )

    return {
        "best_variant_id": report.best_variant_id,
        "best_variant_name": report.best_variant_name,
        "weights": dict(report.weights),
        "ranked": rows,
    }


def save_comparison_report(report: ComparisonReport, out_path: Path) -> Path:
    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report_to_jsonable(report), indent=2, sort_keys=True), encoding="utf-8")
    return out
