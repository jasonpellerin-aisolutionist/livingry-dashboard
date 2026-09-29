"""Pull the public series the dashboard is allowed to use. No keys.

Caches land in data/raw/ and are not committed. Re-run to refresh. A failed
source raises: a missing series must not silently become a missing claim.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import requests

from livingry import RAW

UA = {"User-Agent": "livingry-dashboard/0.1 (research; jason@jasonpellerin.com)"}
TIMEOUT = 90

# Toptier codes from USAspending. Group is an author grouping, stated as such
# everywhere it appears. HHS is mixed because its total is mostly mandatory
# spending (Medicare, Medicaid), which the manuscript refuses to treat as a
# discretionary priority.
AGENCIES = {
    "097": ("Department of Defense", "weaponry"),
    "012": ("Department of Agriculture", "livingry"),
    "068": ("Environmental Protection Agency", "livingry"),
    "086": ("Department of Housing and Urban Development", "livingry"),
    "014": ("Department of the Interior", "livingry"),
    "089": ("Department of Energy", "energy"),
    "091": ("Department of Education", "provision"),
    "075": ("Department of Health and Human Services", "mixed"),
}

OWID = {
    "calories": "daily-per-capita-caloric-supply",
    "food_insecurity": "share-of-population-with-moderate-or-severe-food-insecurity",
    "military_gdp": "military-expenditure-share-gdp",
    "ag_land": "agricultural-land",
    "co2_per_capita": "co-emissions-per-capita",
    "energy_per_capita": "per-capita-energy-use",
    "protein_land": "land-use-protein-poore",
}

WORLD_BANK = {
    "gdp_per_capita": "NY.GDP.PCAP.KD",
    "electricity_access": "EG.ELC.ACCS.ZS",
    "safe_water": "SH.H2O.SMDW.ZS",
}

KEEP_ENTITIES = {"United States", "World"}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def _get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise SystemExit(f"GET failed: {url} ({last})")


def _post(session: requests.Session, url: str, payload: dict) -> dict:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = session.post(url, json=payload, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise SystemExit(f"POST failed: {url} ({last})")


def fetch_agencies(session: requests.Session) -> None:
    out = RAW / "usaspending"
    out.mkdir(parents=True, exist_ok=True)
    for code, (name, group) in AGENCIES.items():
        url = f"https://api.usaspending.gov/api/v2/agency/{code}/budgetary_resources/"
        payload = _get(session, url).json()
        payload["_name"] = name
        payload["_group"] = group
        (out / f"{code}.json").write_text(json.dumps(payload))
        print(f"agency {code} {name}: {len(payload['agency_data_by_year'])} years")


def fetch_recipients(session: requests.Session) -> None:
    """Top contract recipients for the last complete fiscal year.

    Same endpoint the manuscript used. Obligations on a recipient registration
    are not the same quantity as an agency's total obligations.
    """
    payload = _post(
        session,
        "https://api.usaspending.gov/api/v2/search/spending_by_category/recipient/",
        {
            "filters": {
                "time_period": [{"start_date": "2024-10-01", "end_date": "2025-09-30"}],
                "award_type_codes": ["A", "B", "C", "D"],
            },
            "limit": 15,
        },
    )
    out = RAW / "usaspending"
    out.mkdir(parents=True, exist_ok=True)
    (out / "recipients_fy2025.json").write_text(json.dumps(payload))
    print(f"recipients FY2025: {len(payload.get('results', []))} rows")


def fetch_owid(session: requests.Session) -> None:
    out = RAW / "owid"
    out.mkdir(parents=True, exist_ok=True)
    for key, slug in OWID.items():
        url = f"https://ourworldindata.org/grapher/{slug}.csv"
        text = _get(session, url).text
        (out / f"{key}.csv").write_text(text)
        print(f"owid {key}: {text.count(chr(10))} lines")


def fetch_world_bank(session: requests.Session) -> None:
    out = RAW / "worldbank"
    out.mkdir(parents=True, exist_ok=True)
    for key, code in WORLD_BANK.items():
        url = (
            "https://api.worldbank.org/v2/country/USA;WLD/indicator/"
            f"{code}?format=json&per_page=500"
        )
        payload = _get(session, url).json()
        (out / f"{key}.json").write_text(json.dumps(payload))
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        print(f"world bank {key}: {len(rows or [])} rows")


def fetch_sdg(session: requests.Session) -> None:
    """FAO undernourishment (SDG 2.1.1). Often unpublished for high-income countries."""
    url = (
        "https://unstats.un.org/SDGAPI/v1/sdg/Indicator/Data"
        "?indicator=2.1.1&pageSize=8000"
    )
    payload = _get(session, url).json()
    keep = [
        row
        for row in payload.get("data", [])
        if row.get("geoAreaName") in {"World", "United States of America"}
        and row.get("series") == "SN_ITK_DEFC"
    ]
    out = RAW / "sdg"
    out.mkdir(parents=True, exist_ok=True)
    (out / "undernourishment.json").write_text(json.dumps(keep))
    print(f"sdg 2.1.1: {len(keep)} kept rows")


def fetch_co2(session: requests.Session) -> None:
    url = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv"
    text = _get(session, url).text
    out = RAW / "noaa"
    out.mkdir(parents=True, exist_ok=True)
    (out / "co2_mm_mlo.csv").write_text(text)
    print(f"noaa co2: {text.count(chr(10))} lines")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    session = _session()
    fetch_agencies(session)
    fetch_recipients(session)
    fetch_owid(session)
    fetch_world_bank(session)
    fetch_sdg(session)
    fetch_co2(session)
    stamp = {
        "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "complete_fy": 2025,
    }
    (RAW / "retrieved.json").write_text(json.dumps(stamp, indent=2))
    print(f"retrieved {stamp['retrieved_at']}")


if __name__ == "__main__":
    main()
