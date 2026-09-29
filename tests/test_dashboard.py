"""The dashboard is not allowed to become an index, and a few claims have to stay true to the pull."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "tableau" / "exports"


def table(name: str) -> pd.DataFrame:
    return pd.read_csv(EXPORTS / f"{name}.csv")


def test_extracts_exist():
    for name in ("agency_year", "claims", "series", "co2_monthly", "protein_land", "not_measured", "quality_checks"):
        assert (EXPORTS / f"{name}.csv").exists()


def test_quality_checks_pass():
    checks = table("quality_checks")
    assert checks["passed"].all()


def test_no_composite_score():
    claims = table("claims")
    assert "score" not in claims.columns
    assert "weight" not in claims.columns
    blob = " ".join(claims["verdict"].astype(str)).lower()
    assert "index" not in blob


def test_chapter_one_exclusion_is_named_and_absent():
    gaps = table("not_measured")
    assert "vacant_homes_vs_homeless" in set(gaps["indicator"])
    series = table("series")
    assert not series["indicator"].str.contains("homeless|vacant", case=False).any()


def test_co2_comparison_uses_a_full_year():
    claims = table("claims").set_index("claim_id")
    evidence = claims.loc["gdp_beside_co2", "evidence"]
    assert "in 2025" in evidence or "in 2024" in evidence
    # The latest month may be 2026. The annual comparison must not be the partial year.
    assert "ppm in 2026" not in evidence.split("Latest month")[0]


def test_lockheed_is_not_summed():
    claims = table("claims").set_index("claim_id")
    evidence = claims.loc["lockheed_vs_epa", "evidence"]
    assert "G4KDGE4JFFK7" in evidence
    assert "not added" in evidence


def test_hhs_is_not_in_the_livingry_sum_story():
    claims = table("claims").set_index("claim_id")
    assert claims.loc["hhs_not_in_the_group", "verdict"] == "caveat_confirmed"
    evidence = claims.loc["author_livingry_group", "evidence"]
    assert "HHS" not in evidence
