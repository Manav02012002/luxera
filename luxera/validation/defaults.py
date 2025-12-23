from __future__ import annotations

from luxera.validation.engine import Validator
from luxera.validation.rules.basic import (
    RuleAnglesRangeInfo,
    RuleCandelaMultiplierNotOne,
    RuleNanInfCandela,
    RuleNegativeCandela,
)
from luxera.validation.rules.advanced import (
    RuleVerticalAngleStart,
    RuleHorizontalAngleStart,
    RuleLumenOutput,
    RuleMissingKeywords,
    RuleZeroCandela,
    RuleAngleResolution,
    RuleLuminaireDimensions,
    RuleStandardVersion,
)


def default_validator() -> Validator:
    """Create validator with all default rules."""
    return Validator(
        rules=[
            # Critical errors
            RuleNegativeCandela(),
            RuleNanInfCandela(),
            RuleZeroCandela(),
            # Warnings
            RuleVerticalAngleStart(),
            RuleHorizontalAngleStart(),
            RuleLumenOutput(),
            RuleLuminaireDimensions(),
            # Info
            RuleCandelaMultiplierNotOne(),
            RuleAnglesRangeInfo(),
            RuleAngleResolution(),
            RuleMissingKeywords(),
            RuleStandardVersion(),
        ]
    )


def minimal_validator() -> Validator:
    """Create validator with only critical rules (for quick checks)."""
    return Validator(
        rules=[
            RuleNegativeCandela(),
            RuleNanInfCandela(),
            RuleZeroCandela(),
        ]
    )
