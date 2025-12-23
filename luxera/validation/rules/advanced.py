"""
Advanced validation rules for IES photometric files.

These rules check for common issues and compliance with LM-63 standards.
"""

from __future__ import annotations

import math
from typing import List

from luxera.models.validation import ValidationFinding
from luxera.parser.ies_parser import ParsedIES


class RuleVerticalAngleStart:
    """Check that vertical angles start at appropriate value for photometric type."""
    id = "LUXERA_ANG_VSTART"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.angles is None or doc.photometry is None:
            return []
        
        v0 = doc.angles.vertical_deg[0]
        ptype = doc.photometry.photometric_type
        
        # Type C (most common): vertical 0° = nadir, should start at 0°
        # Type B: vertical 0° = horizontal, can start at -90° or 0°
        # Type A: vertical 0° = horizontal, can start at -90° or 0°
        
        if ptype == 1:  # Type C
            if abs(v0) > 1e-6:
                return [ValidationFinding(
                    id=self.id,
                    severity="WARN",
                    title="Type C vertical angles don't start at 0°",
                    message=f"For photometric type C, vertical angles typically start at 0° (nadir). "
                            f"Found start angle: {v0}°",
                    evidence={"vertical_start": v0, "photometric_type": ptype},
                    line_refs=[doc.angles.vertical_line_span],
                    suggested_fix="Verify the photometric type or angle data.",
                )]
        return []


class RuleHorizontalAngleStart:
    """Check that horizontal angles start at 0° for Type C photometry."""
    id = "LUXERA_ANG_HSTART"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.angles is None or doc.photometry is None:
            return []
        
        h0 = doc.angles.horizontal_deg[0]
        ptype = doc.photometry.photometric_type
        
        if ptype == 1:  # Type C
            if abs(h0) > 1e-6:
                return [ValidationFinding(
                    id=self.id,
                    severity="WARN",
                    title="Type C horizontal angles don't start at 0°",
                    message=f"For photometric type C, horizontal angles should start at 0°. "
                            f"Found start angle: {h0}°",
                    evidence={"horizontal_start": h0, "photometric_type": ptype},
                    line_refs=[doc.angles.horizontal_line_span],
                    suggested_fix="Verify the photometric type or angle data.",
                )]
        return []


class RuleLumenOutput:
    """
    Check that integrated candela approximately matches declared lumens.
    
    This is a sanity check: the total flux computed from the candela distribution
    should be reasonably close to the declared lumens (num_lamps × lumens_per_lamp).
    """
    id = "LUXERA_FLUX_CHECK"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.angles is None or doc.candela is None or doc.photometry is None:
            return []
        
        # Only check Type C for now (most common)
        if doc.photometry.photometric_type != 1:
            return []
        
        declared_lumens = doc.photometry.num_lamps * doc.photometry.lumens_per_lamp
        if declared_lumens <= 0:
            return []
        
        # Integrate candela over solid angle using trapezoidal rule
        # For Type C: Φ = ∫∫ I(θ,φ) sin(θ) dθ dφ
        # where θ is vertical angle (0 at nadir), φ is horizontal angle
        
        v_deg = doc.angles.vertical_deg
        h_deg = doc.angles.horizontal_deg
        candela = doc.candela.values_cd_scaled
        
        # Simple integration assuming full symmetry coverage
        # This is approximate but catches gross errors
        total_flux = 0.0
        
        for hi in range(len(h_deg)):
            # Get angular width for this horizontal slice
            if hi == 0:
                dh = (h_deg[1] - h_deg[0]) / 2 if len(h_deg) > 1 else 360.0
            elif hi == len(h_deg) - 1:
                dh = (h_deg[-1] - h_deg[-2]) / 2
            else:
                dh = (h_deg[hi + 1] - h_deg[hi - 1]) / 2
            
            for vi in range(len(v_deg)):
                # Get angular width for this vertical slice
                if vi == 0:
                    dv = (v_deg[1] - v_deg[0]) / 2 if len(v_deg) > 1 else 180.0
                elif vi == len(v_deg) - 1:
                    dv = (v_deg[-1] - v_deg[-2]) / 2
                else:
                    dv = (v_deg[vi + 1] - v_deg[vi - 1]) / 2
                
                theta = math.radians(v_deg[vi])
                dtheta = math.radians(dv)
                dphi = math.radians(dh)
                
                I = candela[hi][vi]
                # Solid angle element
                dOmega = abs(math.sin(theta)) * dtheta * dphi
                total_flux += I * dOmega
        
        # Account for symmetry (approximate)
        h_range = h_deg[-1] - h_deg[0]
        if h_range < 180:
            # Quadrant symmetry - multiply by 4
            total_flux *= 4
        elif h_range < 360:
            # Bilateral symmetry - multiply by 2
            total_flux *= 2
        
        # Check if within reasonable tolerance (30%)
        ratio = total_flux / declared_lumens if declared_lumens > 0 else 0
        
        if ratio < 0.5 or ratio > 2.0:
            return [ValidationFinding(
                id=self.id,
                severity="WARN",
                title="Integrated flux doesn't match declared lumens",
                message=f"Computed flux ({total_flux:.0f} lm) differs significantly from "
                        f"declared lumens ({declared_lumens:.0f} lm). Ratio: {ratio:.2f}",
                evidence={
                    "computed_lumens": round(total_flux, 1),
                    "declared_lumens": declared_lumens,
                    "ratio": round(ratio, 3),
                },
                line_refs=[doc.photometry.line_no],
                suggested_fix="Verify the candela values and declared lamp lumens.",
            )]
        
        return []


class RuleMissingKeywords:
    """Check for missing recommended IES keywords."""
    id = "LUXERA_KW_MISSING"
    
    RECOMMENDED_KEYWORDS = ["MANUFAC", "LUMCAT", "LUMINAIRE"]
    OPTIONAL_KEYWORDS = ["LAMPCAT", "LAMP", "TESTLAB", "DATE", "ISSUEDATE"]

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        missing = [k for k in self.RECOMMENDED_KEYWORDS if k not in doc.keywords]
        
        if not missing:
            return []
        
        return [ValidationFinding(
            id=self.id,
            severity="INFO",
            title="Missing recommended keywords",
            message=f"The following recommended keywords are missing: {', '.join(missing)}",
            evidence={"missing_keywords": missing},
            line_refs=[],
            suggested_fix="Add missing keywords for better file identification.",
        )]


class RuleZeroCandela:
    """Check if all candela values are zero (likely invalid file)."""
    id = "LUXERA_CDL_ALL_ZERO"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.candela is None:
            return []
        
        if doc.candela.max_cd == 0 and doc.candela.min_cd == 0:
            return [ValidationFinding(
                id=self.id,
                severity="ERROR",
                title="All candela values are zero",
                message="The candela distribution contains only zero values, "
                        "which indicates invalid or placeholder photometric data.",
                evidence={},
                line_refs=[doc.candela.line_span],
                suggested_fix="Obtain valid photometric data from the manufacturer.",
            )]
        return []


class RuleAngleResolution:
    """Check if angle resolution is too coarse for accurate calculations."""
    id = "LUXERA_ANG_RESOLUTION"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.angles is None:
            return []
        
        findings = []
        
        # Check vertical resolution
        v = doc.angles.vertical_deg
        if len(v) >= 2:
            v_spacing = (v[-1] - v[0]) / (len(v) - 1)
            if v_spacing > 15:
                findings.append(ValidationFinding(
                    id=f"{self.id}_V",
                    severity="INFO",
                    title="Coarse vertical angle resolution",
                    message=f"Average vertical spacing is {v_spacing:.1f}°. "
                            f"Resolutions >15° may reduce calculation accuracy.",
                    evidence={"vertical_spacing_deg": round(v_spacing, 1), "num_angles": len(v)},
                    line_refs=[doc.angles.vertical_line_span],
                ))
        
        # Check horizontal resolution
        h = doc.angles.horizontal_deg
        if len(h) >= 2:
            h_spacing = (h[-1] - h[0]) / (len(h) - 1)
            if h_spacing > 30:
                findings.append(ValidationFinding(
                    id=f"{self.id}_H",
                    severity="INFO",
                    title="Coarse horizontal angle resolution",
                    message=f"Average horizontal spacing is {h_spacing:.1f}°. "
                            f"Resolutions >30° may reduce calculation accuracy.",
                    evidence={"horizontal_spacing_deg": round(h_spacing, 1), "num_angles": len(h)},
                    line_refs=[doc.angles.horizontal_line_span],
                ))
        
        return findings


class RuleLuminaireDimensions:
    """Check for physically unreasonable luminaire dimensions."""
    id = "LUXERA_DIM_CHECK"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.photometry is None:
            return []
        
        ph = doc.photometry
        findings = []
        
        # Convert to meters if in feet
        scale = 0.3048 if ph.units_type == 1 else 1.0
        w_m = ph.width * scale
        l_m = ph.length * scale
        h_m = ph.height * scale
        
        # Check for very large dimensions (> 5m)
        if w_m > 5 or l_m > 5 or h_m > 5:
            findings.append(ValidationFinding(
                id=f"{self.id}_LARGE",
                severity="WARN",
                title="Unusually large luminaire dimensions",
                message=f"Luminaire dimensions ({w_m:.2f}m × {l_m:.2f}m × {h_m:.2f}m) "
                        f"exceed 5m in at least one dimension.",
                evidence={
                    "width_m": round(w_m, 3),
                    "length_m": round(l_m, 3),
                    "height_m": round(h_m, 3),
                },
                line_refs=[ph.line_no],
                suggested_fix="Verify the dimensions and units type.",
            ))
        
        # Check for zero dimensions (point source should have all zeros)
        dims = [w_m, l_m, h_m]
        non_zero = sum(1 for d in dims if d > 0)
        if non_zero == 1 or non_zero == 2:
            findings.append(ValidationFinding(
                id=f"{self.id}_PARTIAL",
                severity="INFO",
                title="Partial luminaire dimensions",
                message="Some dimensions are zero and some are non-zero. "
                        "This may be intentional for linear or area sources.",
                evidence={
                    "width_m": round(w_m, 3),
                    "length_m": round(l_m, 3),
                    "height_m": round(h_m, 3),
                },
                line_refs=[ph.line_no],
            ))
        
        return findings


class RuleStandardVersion:
    """Check the IES standard version."""
    id = "LUXERA_STD_VERSION"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.standard_line is None:
            return [ValidationFinding(
                id=self.id,
                severity="INFO",
                title="No standard header line",
                message="File does not begin with IESNA:LM-63 standard identifier. "
                        "This may indicate an older or non-standard file format.",
                evidence={},
                line_refs=[1],
                suggested_fix="Consider re-exporting with a modern photometry tool.",
            )]
        
        upper = doc.standard_line.upper()
        
        if "LM-63-2002" in upper or "LM-63-2019" in upper:
            return []  # Current standards
        elif "LM-63-1995" in upper or "LM-63-1991" in upper:
            return [ValidationFinding(
                id=self.id,
                severity="INFO",
                title="Older IES standard version",
                message=f"File uses older standard: {doc.standard_line}. "
                        f"Consider updating to LM-63-2019.",
                evidence={"standard_line": doc.standard_line},
                line_refs=[1],
            )]
        
        return []
