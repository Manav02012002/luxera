from __future__ import annotations

from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ldt
from luxera.photometry.canonical import CanonicalPhotometry, canonical_from_photometry


def parse_ldt_canonical(text: str) -> CanonicalPhotometry:
    parsed = parse_ldt_text(text)
    phot = photometry_from_parsed_ldt(parsed)
    return canonical_from_photometry(phot, source_format="LDT")
