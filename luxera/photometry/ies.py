from __future__ import annotations

from pathlib import Path

from luxera.parser.ies_parser import parse_ies_text
from luxera.photometry.model import photometry_from_parsed_ies
from luxera.photometry.canonical import CanonicalPhotometry, canonical_from_photometry


def parse_ies_canonical(text: str, source_path: str | Path | None = None) -> CanonicalPhotometry:
    parsed = parse_ies_text(text, source_path=source_path)
    phot = photometry_from_parsed_ies(parsed)
    return canonical_from_photometry(phot, source_format="IES")
