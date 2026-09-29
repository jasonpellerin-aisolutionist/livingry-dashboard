"""Turn cached public pulls into the tables the dashboard, workbook, and tests use.

No composite index is computed. A grouping of agencies is labeled as an author
grouping. Claim verdicts are descriptive: coexistence and direction, not causes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb
import pandas as pd

from livingry import APP_DATA, COMPLETE_FY, EXPORTS, RAW, REPORTS
from livingry.fetch import AGENCIES

LIVINGRY_CODES = [code for code, (_, group) in AGENCIES.items() if group == "livingry"]
# Interior and Energy are real resource agencies, but the manuscript's Chapter 1
# comparison is about priority, and the tight group used on the dashboard is the
# four whose missions are food, environment, housing, and land.
DASHBOARD_LIVINGRY = ["012", "068", "086", "014"]


def _retrieved_at() -> str:
    stamp = RAW / "retrieved.json"
    if stamp.exists():
        return json.loads(stamp.read_text())["retrieved_at"]
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_agencies() -> pd.DataFrame:
    rows = []
    for code, (name, group) in AGENCIES.items():
        payload = json.loads((RAW / "usaspending" / f"{code}.json").read_text())
        for year in payload["agency_data_by_year"]:
            rows.append(
                {
                    "fiscal_year": int(year["fiscal_year"]),
                    "agency_code": code,
                    "agency": name,
                    "group": group,
                    "obligations": year["agency_total_obligated"],
                    "outlays": year["agency_total_outlayed"],
                    "budgetary_resources": year["agency_budgetary_resources"],
                    "partial_year": int(year["fiscal_year"]) > COMPLETE_FY,
                }
            )
    frame = pd.DataFrame(rows)
    if frame["fiscal_year"].eq(COMPLETE_FY).sum() != len(AGENCIES):
        raise SystemExit(f"FY{COMPLETE_FY} is missing for at least one agency")
    return frame


def load_recipients() -> pd.DataFrame:
    payload = json.loads((RAW / "usaspending" / "recipients_fy2025.json").read_text())
    rows = []
    for rank, item in enumerate(payload["results"], start=1):
        rows.append(
            {
                "rank": rank,
                "recipient": item.get("name"),
                "uei": item.get("uei"),
                "legacy_code": item.get("code"),
                "recipient_id": item.get("id"),
                "obligations": item.get("amount"),
                "fiscal_year": COMPLETE_FY,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty or frame["obligations"].isna().any():
        raise SystemExit(f"unexpected recipient payload keys: {payload['results'][:1]}")
    return frame


def _owid(key: str, value_name: str) -> pd.DataFrame:
    frame = pd.read_csv(RAW / "owid" / f"{key}.csv")
    skip = {"Entity", "Code", "Year"}
    value_cols = [
        c for c in frame.columns
        if c not in skip and "Annotation" not in c and "region" not in c.lower()
    ]
    if len(value_cols) != 1:
        raise SystemExit(f"{key} value columns: {value_cols}")
    out = frame.rename(columns={"Entity": "entity", "Code": "code", "Year": "year", value_cols[0]: value_name})
    out["year"] = out["year"].astype(int)
    return out


def load_series() -> pd.DataFrame:
    """Long panel. United States and World only, except the protein cross-section."""
    pieces = []

    def add(frame: pd.DataFrame, indicator: str, unit: str, family: str, source: str, entities: set[str]):
        kept = frame[frame["entity"].isin(entities)].copy()
        kept["indicator"] = indicator
        kept["unit"] = unit
        kept["family"] = family
        kept["source"] = source
        pieces.append(kept[["entity", "year", "value", "indicator", "unit", "family", "source"]])

    calories = _owid("calories", "value")
    add(calories, "daily_calorie_supply", "kcal per person per day", "provision",
        "Our World in Data, FAO food balances", {"United States", "World"})

    insecurity = _owid("food_insecurity", "value")
    add(insecurity, "food_insecurity_moderate_or_severe", "percent of population", "provision",
        "Our World in Data, FAO Food Insecurity Experience Scale (SDG 2.1.2)",
        {"United States", "World"})

    military = _owid("military_gdp", "value")
    add(military, "military_expenditure_share_gdp", "percent of GDP", "priority",
        "Our World in Data, SIPRI", {"United States", "World"})

    land = _owid("ag_land", "value")
    add(land, "agricultural_land", "hectares", "ecological_state",
        "Our World in Data, FAO", {"United States", "World"})

    co2 = _owid("co2_per_capita", "value")
    add(co2, "co2_emissions_per_capita", "tonnes per person per year", "ecological_state",
        "Our World in Data, Global Carbon Project", {"United States", "World"})

    energy = _owid("energy_per_capita", "value")
    add(energy, "energy_use_per_capita", "kWh per person per year", "provision",
        "Our World in Data (primary energy, kilowatt-hours per person)", {"United States", "World"})

    for key, indicator, unit, family in [
        ("gdp_per_capita", "gdp_per_capita_constant_2015_usd", "constant 2015 US dollars", "accounts"),
        ("electricity_access", "electricity_access", "percent of population", "provision"),
        ("safe_water", "safely_managed_water", "percent of population", "provision"),
    ]:
        payload = json.loads((RAW / "worldbank" / f"{key}.json").read_text())
        rows = []
        for item in payload[1] or []:
            if item.get("value") is None:
                continue
            rows.append({
                "entity": item["country"]["value"],
                "year": int(item["date"]),
                "value": float(item["value"]),
            })
        frame = pd.DataFrame(rows)
        add(frame, indicator, unit, family, f"World Bank {key}", {"United States", "World"})

    sdg = json.loads((RAW / "sdg" / "undernourishment.json").read_text())
    rows = []
    for item in sdg:
        name = "World" if item["geoAreaName"] == "World" else "United States"
        try:
            value = float(item["value"])
        except (TypeError, ValueError):
            # FAO censors high-income countries at "<2.5" and sometimes returns "NaN".
            # Those rows are a finding, handled in the claims, not a number to plot.
            continue
        rows.append({"entity": name, "year": int(item["timePeriodStart"]), "value": value})
    if rows:
        add(pd.DataFrame(rows), "undernourishment", "percent of population", "provision",
            "UN SDG API, FAO prevalence of undernourishment (SDG 2.1.1)", {"United States", "World"})

    series = pd.concat(pieces, ignore_index=True)
    series = series.dropna(subset=["value"])
    return series


def load_co2_monthly() -> pd.DataFrame:
    frame = pd.read_csv(RAW / "noaa" / "co2_mm_mlo.csv", comment="#")
    frame.columns = [c.strip() for c in frame.columns]
    # NOAA labels the monthly mean "average".
    value_col = "average" if "average" in frame.columns else frame.columns[3]
    out = pd.DataFrame({
        "year": frame["year"].astype(int),
        "month": frame["month"].astype(int),
        "ppm": pd.to_numeric(frame[value_col], errors="coerce"),
    })
    out = out[out["ppm"] > 0]
    if out["ppm"].iloc[-1] < 400 or out["ppm"].iloc[-1] > 500:
        raise SystemExit(f"Mauna Loa reading looks wrong: {out['ppm'].iloc[-1]}")
    return out


def load_protein() -> pd.DataFrame:
    frame = _owid("protein_land", "land_use_m2")
    # OWID's column is land use per 100g protein. Units in the grapher are m2.
    frame = frame.dropna(subset=["land_use_m2"])
    frame["source"] = "Poore and Nemecek 2018, via Our World in Data"
    frame["note"] = "Published cross-section, not a live feed. Per 100g of protein, not per calorie."
    return frame.sort_values("land_use_m2", ascending=False)


def _latest(series: pd.DataFrame, entity: str, indicator: str) -> tuple[int, float]:
    part = series[(series["entity"] == entity) & (series["indicator"] == indicator)]
    if part.empty:
        raise SystemExit(f"no rows for {entity} {indicator}")
    row = part.sort_values("year").iloc[-1]
    return int(row["year"]), float(row["value"])


def _value_in_year(series: pd.DataFrame, entity: str, indicator: str, year: int) -> float | None:
    part = series[(series["entity"] == entity) & (series["indicator"] == indicator) & (series["year"] == year)]
    if part.empty:
        return None
    return float(part["value"].iloc[0])


def build_claims(agencies: pd.DataFrame, recipients: pd.DataFrame, series: pd.DataFrame, co2: pd.DataFrame, protein: pd.DataFrame) -> pd.DataFrame:
    claims = []

    def add(**kwargs):
        claims.append(kwargs)

    fy = agencies[agencies["fiscal_year"] == COMPLETE_FY].set_index("agency_code")
    dod = float(fy.loc["097", "obligations"])
    epa = float(fy.loc["068", "obligations"])
    livingry = float(fy.loc[DASHBOARD_LIVINGRY, "obligations"].sum())
    hhs = float(fy.loc["075", "obligations"])

    add(
        claim_id="dod_and_epa_same_quantity",
        book_chapter="1 and 30",
        statement="Defense obligations and EPA obligations are different orders of magnitude in the same fiscal year.",
        verdict="magnitude_reported",
        year=COMPLETE_FY,
        evidence=(
            f"FY{COMPLETE_FY} obligations: Defense ${dod/1e9:.1f}B, EPA ${epa/1e9:.1f}B, "
            f"ratio {dod/epa:.0f} to 1. Both figures are agency obligations."
        ),
        caveat="Obligations are commitments, not cash outlays. A ratio is not a proposal to move the money.",
    )
    add(
        claim_id="author_livingry_group",
        book_chapter="30",
        statement="Defense obligations exceed the combined obligations of USDA, EPA, HUD, and Interior.",
        verdict="magnitude_reported",
        year=COMPLETE_FY,
        evidence=(
            f"FY{COMPLETE_FY}: Defense ${dod/1e9:.1f}B against ${livingry/1e9:.1f}B for the four-agency group "
            f"({dod/livingry:.1f} to 1)."
        ),
        caveat=(
            "The four-agency group is an author grouping for this dashboard, not an official category. "
            "It leaves out Energy and Education on purpose so the group stays close to food, water, shelter, and land."
        ),
    )
    add(
        claim_id="hhs_not_in_the_group",
        book_chapter="1",
        statement="HHS obligations are larger than Defense and are not treated as a livingry priority.",
        verdict="caveat_confirmed",
        year=COMPLETE_FY,
        evidence=f"FY{COMPLETE_FY} HHS obligations ${hhs/1e9:.1f}B, mostly Medicare and Medicaid.",
        caveat="Agency totals include mandatory spending. HHS is reported beside the group and never added into it.",
    )

    lockheed = recipients[recipients["recipient"].str.contains("LOCKHEED", case=False, na=False)]
    if lockheed.empty:
        add(
            claim_id="lockheed_vs_epa",
            book_chapter="1",
            statement="The manuscript compares Lockheed Martin's largest registration with EPA's total obligations.",
            verdict="not_in_top_15",
            year=COMPLETE_FY,
            evidence="No Lockheed registration is in the top 15 contract recipients for this pull.",
            caveat="Recipient receipts and agency obligations are different kinds of quantity. Do not force the comparison.",
        )
    else:
        top = lockheed.sort_values("obligations", ascending=False).iloc[0]
        others = lockheed[lockheed["uei"] != top["uei"]]
        other_text = ", ".join(
            f"UEI {row.uei} ${row.obligations/1e9:.1f}B" for row in others.itertuples()
        )
        add(
            claim_id="lockheed_vs_epa",
            book_chapter="1",
            statement="One contractor registration can be the same order of magnitude as a whole agency.",
            verdict="magnitude_reported",
            year=COMPLETE_FY,
            evidence=(
                f"Largest Lockheed registration in the FY{COMPLETE_FY} top 15 "
                f"({top['recipient']}, UEI {top['uei']}): ${top['obligations']/1e9:.1f}B. "
                f"EPA obligations the same year: ${epa/1e9:.1f}B. "
                f"Other Lockheed registrations in the top 15, not added: {other_text}."
            ),
            caveat=(
                "A recipient's contract receipts and an agency's total obligations are different kinds of quantity. "
                "The comparison is scale, not a trade-off anyone voted on."
            ),
        )

    kcal_year, kcal = _latest(series, "United States", "daily_calorie_supply")
    try:
        fi_year, fi = _latest(series, "United States", "food_insecurity_moderate_or_severe")
        fi_text = f"{fi:.1f}% moderate or severe food insecurity in {fi_year}"
        coexist = kcal >= 2500 and fi >= 5
    except SystemExit:
        fi_year, fi = None, None
        fi_text = "no United States food-insecurity row in this pull"
        coexist = False
    add(
        claim_id="calories_and_insecurity",
        book_chapter="1",
        statement="High average food supply and a large food-insecurity shortfall coexist in the United States.",
        verdict="supported_as_coexistence" if coexist else "not_supported",
        year=max(y for y in (kcal_year, fi_year) if y),
        evidence=f"United States food supply {kcal:.0f} kcal per person per day ({kcal_year}); {fi_text}.",
        caveat="Coexistence is not a cause. The years may differ. The supply figure is an average and says nothing about distribution.",
    )

    co2_annual = co2.groupby("year", as_index=False)["ppm"].mean()
    months = co2.groupby("year").size()
    complete_co2_years = months[months >= 12].index
    co2_now_year = int(complete_co2_years.max())
    co2_now = float(co2_annual.loc[co2_annual["year"] == co2_now_year, "ppm"].iloc[0])
    latest_month = co2.iloc[-1]
    gdp_year, gdp = _latest(series, "United States", "gdp_per_capita_constant_2015_usd")
    start = 1990
    gdp_then = _value_in_year(series, "United States", "gdp_per_capita_constant_2015_usd", start)
    co2_then_rows = co2_annual[co2_annual["year"] == start]
    co2_then = float(co2_then_rows["ppm"].iloc[0]) if not co2_then_rows.empty else None
    both_up = gdp_then is not None and co2_then is not None and gdp > gdp_then and co2_now > co2_then
    add(
        claim_id="gdp_beside_co2",
        book_chapter="29",
        statement="Real GDP per person and the atmospheric CO2 stock rose over the same decades.",
        verdict="descriptive_support" if both_up else "not_supported",
        year=co2_now_year,
        evidence=(
            f"United States GDP per capita (constant 2015 dollars): ${gdp_then:,.0f} in {start}, "
            f"${gdp:,.0f} in {gdp_year}. Mauna Loa annual mean, full years only: {co2_then:.1f} ppm in {start}, "
            f"{co2_now:.1f} ppm in {co2_now_year}. Latest month: {latest_month['ppm']:.2f} ppm "
            f"in {int(latest_month['year'])}-{int(latest_month['month']):02d}."
        ),
        caveat="Shown side by side on purpose. They are not combined into an index, and neither causes the other by virtue of sharing a chart.",
    )

    sdg_raw = json.loads((RAW / "sdg" / "undernourishment.json").read_text())
    world_rows = [row for row in sdg_raw if row.get("geoAreaName") == "World"]
    projected = {
        int(row["timePeriodStart"])
        for row in world_rows
        if any("projected" in str(note).lower() for note in (row.get("footnotes") or []))
    }
    world = series[(series["entity"] == "World") & (series["indicator"] == "undernourishment")].sort_values("year")
    observed = world[~world["year"].isin(projected)]
    if len(observed) >= 2 and co2_then is not None:
        first, last = observed.iloc[0], observed.iloc[-1]
        hunger_down = float(last["value"]) < float(first["value"])
        projected_latest = world[world["year"].isin(projected)].sort_values("year")
        projected_text = ""
        if not projected_latest.empty:
            tail = projected_latest.iloc[-1]
            projected_text = (
                f" FAO marks {int(projected_latest['year'].min())}-{int(tail['year'])} as projections; "
                f"{int(tail['year'])} is {float(tail['value']):.1f}%."
            )
        add(
            claim_id="delivery_and_depletion",
            book_chapter="1",
            statement="Global undernourishment fell while the atmospheric CO2 stock rose.",
            verdict="descriptive_support" if hunger_down and co2_now > co2_then else "not_supported",
            year=int(last["year"]),
            evidence=(
                f"World undernourishment {float(first['value']):.1f}% in {int(first['year'])}, "
                f"{float(last['value']):.1f}% in {int(last['year'])}, before the projection footnote."
                f"{projected_text} "
                f"Mauna Loa full-year mean {co2_then:.1f} ppm in {start}, {co2_now:.1f} ppm in {co2_now_year}."
            ),
            caveat=(
                "This is the manuscript's own concession, not a rebuttal of it: a flow can improve "
                "while a stock deteriorates. FAO's whole undernourishment series is estimated, and "
                "years marked as projections are not used as the endpoint."
            ),
        )
    else:
        add(
            claim_id="delivery_and_depletion",
            book_chapter="1",
            statement="Global undernourishment fell while the atmospheric CO2 stock rose.",
            verdict="not_measured",
            year=co2_now_year,
            evidence="The undernourishment series did not return a world trend in this pull.",
            caveat="Do not fill the gap with a remembered number.",
        )

    sdg_raw = json.loads((RAW / "sdg" / "undernourishment.json").read_text())
    usa_raw = [row for row in sdg_raw if row.get("geoAreaName") == "United States of America"]
    censored = [row for row in usa_raw if str(row.get("value")).startswith("<")]
    latest_censor = max(censored, key=lambda row: row["timePeriodStart"]) if censored else None
    add(
        claim_id="us_undernourishment_censored",
        book_chapter="29",
        statement="FAO does not publish a United States undernourishment rate. It publishes a floor.",
        verdict="censored_at_floor" if latest_censor else "not_measured",
        year=int(latest_censor["timePeriodStart"]) if latest_censor else COMPLETE_FY,
        evidence=(
            f"SDG 2.1.1 for the United States is '{latest_censor['value']}' in "
            f"{int(latest_censor['timePeriodStart'])}, and the same floor in {len(censored)} years of this pull."
            if latest_censor
            else "No censored United States row in this pull."
        ),
        caveat=(
            "Below 2.5% is not a measurement of 2.5%, and it is not evidence that hunger is gone. "
            "The United States shortfall on this dashboard is SDG 2.1.2 food insecurity."
        ),
    )

    high = protein.iloc[0]
    low = protein.iloc[-1]
    beef = protein[protein["entity"].str.contains("Beef \\(beef herd\\)", regex=True)]
    tofu = protein[protein["entity"] == "Tofu"]
    pair = ""
    if not beef.empty and not tofu.empty:
        pair = (
            f" Beef herd {float(beef['land_use_m2'].iloc[0]):.1f} m2 against tofu "
            f"{float(tofu['land_use_m2'].iloc[0]):.1f} m2 "
            f"({float(beef['land_use_m2'].iloc[0]) / float(tofu['land_use_m2'].iloc[0]):.0f} to 1)."
        )
    add(
        claim_id="protein_land_spread",
        book_chapter="13",
        statement="Land required per 100g of protein differs by more than an order of magnitude across foods.",
        verdict="magnitude_reported" if high["land_use_m2"] / low["land_use_m2"] >= 10 else "smaller_than_expected",
        year=int(high["year"]) if pd.notna(high["year"]) else 2018,
        evidence=(
            f"Highest in the table: {high['entity']} at {high['land_use_m2']:.1f} m2 per 100g protein. "
            f"Lowest: {low['entity']} at {low['land_use_m2']:.2f} m2 "
            f"({high['land_use_m2'] / low['land_use_m2']:.0f} to 1)."
            f"{pair}"
        ),
        caveat=(
            "Poore and Nemecek, Science, 2018, via Our World in Data. The grapher year is "
            f"{int(high['year']) if pd.notna(high['year']) else 'unspecified'}. A published cross-section, not a live feed. "
            "Per protein, not per calorie. Farmed prawns sit at the bottom because the metric is land, "
            "which does not count the feed, water, and energy that metric leaves out."
        ),
    )

    mil_year, mil = _latest(series, "United States", "military_expenditure_share_gdp")
    add(
        claim_id="military_share_of_gdp",
        book_chapter="30",
        statement="United States military expenditure is a few percent of GDP.",
        verdict="magnitude_reported",
        year=mil_year,
        evidence=f"SIPRI via Our World in Data: {mil:.2f}% of GDP in {mil_year}.",
        caveat="This is a share of GDP. It is not comparable to the USAspending obligation figures above, and the two are never placed in one ratio.",
    )

    return pd.DataFrame(claims)


def not_measured() -> pd.DataFrame:
    """Families Chapter 29 names that this build does not pretend to cover."""
    rows = [
        ("restoration_rate", "29", "Hectares restored, watersheds improving, soil carbon added. No public series is wired in."),
        ("rivers_downstream", "29", "Cleaner downstream than upstream. The manuscript calls this the best single test. It needs a sampling program, not an API."),
        ("time_and_care", "29", "Unpaid care hours and their distribution. GDP does not see them, and neither does this pull."),
        ("legitimacy", "28 and 29", "Cases brought, cases won, time to remedy. Not in these sources."),
        ("resilience", "29", "Local food share, storage, redundancy. Not in these sources."),
        ("vacant_homes_vs_homeless", "1", "Deliberately absent. Chapter 1 calls that comparison fungibility nonsense."),
        ("composite_index", "29", "Deliberately absent. Chapter 29 argues that weights hidden inside one number are a political act."),
    ]
    return pd.DataFrame(rows, columns=["indicator", "book_chapter", "why_it_is_absent"])


def quality_checks(agencies: pd.DataFrame, series: pd.DataFrame, co2: pd.DataFrame, claims: pd.DataFrame) -> pd.DataFrame:
    checks = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check_name": name, "passed": bool(ok), "detail": detail})

    add("every agency has the complete fiscal year",
        agencies.loc[agencies["fiscal_year"] == COMPLETE_FY, "agency_code"].nunique() == len(AGENCIES),
        f"FY{COMPLETE_FY}")
    add("FY2026 is marked partial",
        bool(agencies.loc[agencies["fiscal_year"] == 2026, "partial_year"].all()) if (agencies["fiscal_year"] == 2026).any() else False,
        "partial_year true")
    add("Mauna Loa latest ppm between 400 and 500",
        400 < float(co2["ppm"].iloc[-1]) < 500,
        f"{float(co2['ppm'].iloc[-1]):.2f}")
    add("United States calorie series exists",
        not series[(series.entity == "United States") & (series.indicator == "daily_calorie_supply")].empty,
        "daily_calorie_supply")
    add("no claim is a weighted index",
        "index" not in " ".join(claims["verdict"].astype(str)).lower() and "score" not in claims.columns,
        "verdicts are labels, not weights")
    indicator_names = " ".join(series["indicator"].astype(str).unique()).lower()
    add("vacancy and homelessness are absent",
        "vacant" not in indicator_names and "homeless" not in indicator_names,
        "chapter 1 exclusion")
    frame = pd.DataFrame(checks)
    failed = frame.loc[~frame["passed"], "check_name"].tolist()
    if failed:
        raise SystemExit(f"quality checks failed: {failed}")
    return frame


def main() -> None:
    retrieved = _retrieved_at()
    agencies = load_agencies()
    recipients = load_recipients()
    series = load_series()
    co2 = load_co2_monthly()
    protein = load_protein()
    claims = build_claims(agencies, recipients, series, co2, protein)
    gaps = not_measured()
    checks = quality_checks(agencies, series, co2, claims)

    for folder in (EXPORTS, APP_DATA, REPORTS):
        folder.mkdir(parents=True, exist_ok=True)

    tables = {
        "agency_year": agencies,
        "agency_fy2025": agencies[agencies["fiscal_year"] == COMPLETE_FY].drop(columns=["partial_year"]),
        "recipients_fy2025": recipients,
        "series": series,
        "co2_monthly": co2,
        "protein_land": protein,
        "claims": claims,
        "not_measured": gaps,
        "quality_checks": checks,
    }
    for name, frame in tables.items():
        frame.to_csv(EXPORTS / f"{name}.csv", index=False)
        frame.to_csv(APP_DATA / f"{name}.csv", index=False)

    db_path = REPORTS / "livingry.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    for name, frame in tables.items():
        con.register("tmp", frame)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp")
    con.close()

    meta = {
        "retrieved_at": retrieved,
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "complete_fy": COMPLETE_FY,
        "agencies": agencies[agencies["fiscal_year"] == COMPLETE_FY][["agency", "group", "obligations"]].to_dict("records"),
        "claims": claims[["claim_id", "verdict", "evidence"]].to_dict("records"),
        "co2_latest_ppm": float(co2["ppm"].iloc[-1]),
        "co2_latest": f"{int(co2['year'].iloc[-1])}-{int(co2['month'].iloc[-1]):02d}",
    }
    (REPORTS / "meta.json").write_text(json.dumps(meta, indent=2))
    (APP_DATA / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"built {len(claims)} claims, CO2 {meta['co2_latest']} {meta['co2_latest_ppm']:.2f} ppm")
    for row in claims.itertuples(index=False):
        print(f"  {row.claim_id}: {row.verdict}")


if __name__ == "__main__":
    main()
