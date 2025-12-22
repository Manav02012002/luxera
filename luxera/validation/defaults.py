from __future__ import annotations

from luxera.validation.engine import Validator
from luxera.validation.rules.basic import (
    RuleAnglesRangeInfo,
    RuleCandelaMultiplierNotOne,
    RuleNanInfCandela,
    RuleNegativeCandela,
)


def default_validator() -> Validator:
    return Validator(
        rules=[
            RuleNegativeCandela(),
            RuleNanInfCandela(),
            RuleCandelaMultiplierNotOne(),
            RuleAnglesRangeInfo(),
        ]
    )
