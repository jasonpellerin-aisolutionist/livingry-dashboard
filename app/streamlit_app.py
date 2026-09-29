"""Live reader for the Livingry Dashboard. Reads the committed extracts, so it
opens without re-pulling the sources. Refresh the extracts with `make refresh`."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
NAVY, TEAL, BLUE, SLATE = "#1e3a5f", "#0f766e", "#2563eb", "#64748b"
GROUP_COLOR = {
    "weaponry": NAVY,
    "livingry": TEAL,
    "mixed": SLATE,
    "energy": BLUE,
    "provision": "#5b8db8",
}

st.set_page_config(page_title="The Livingry Dashboard", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem;}
      h1, h2, h3 {color: #0f172a;}
    </style>
    """,
    unsafe_allow_html=True,
)

agencies = pd.read_csv(DATA / "agency_year.csv", dtype={"agency_code": str})
agencies["agency_code"] = agencies["agency_code"].str.zfill(3)
series = pd.read_csv(DATA / "series.csv")
claims = pd.read_csv(DATA / "claims.csv")
co2 = pd.read_csv(DATA / "co2_monthly.csv")
protein = pd.read_csv(DATA / "protein_land.csv")
gaps = pd.read_csv(DATA / "not_measured.csv")
meta = pd.read_json(DATA / "meta.json", typ="series")

st.title("The Livingry Dashboard")
st.caption(
    "Indicators from The Livingry Protocol, an unpublished manuscript. "
    f"Sources retrieved {meta['retrieved_at']}. Each number keeps its own unit. "
    "This app does not compute a score."
)

fy = agencies[agencies["fiscal_year"] == 2025]
dod = float(fy.loc[fy["agency_code"] == "097", "obligations"].iloc[0])
epa = float(fy.loc[fy["agency_code"] == "068", "obligations"].iloc[0])
latest = co2.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Defense obligations, FY2025", f"${dod/1e9:.0f}B")
c2.metric("EPA obligations, FY2025", f"${epa/1e9:.1f}B")
c3.metric("Defense per EPA dollar", f"{dod/epa:.0f}")
c4.metric(
    f"Mauna Loa, {int(latest['year'])}-{int(latest['month']):02d}",
    f"{latest['ppm']:.1f} ppm",
)

tab_priority, tab_provision, tab_gdp, tab_land, tab_claims = st.tabs(
    ["Priority", "Provision", "GDP beside CO2", "Land per protein", "Claims and gaps"]
)

with tab_priority:
    st.subheader("FY2025 agency obligations")
    st.write(
        "HHS is on the chart because hiding it would make the picture flattering. "
        "Most of it is Medicare and Medicaid, so it is not added into the livingry group. "
        "The teal bars (Agriculture, EPA, Housing, Interior) are an author grouping, not an official category."
    )
    plot = fy.sort_values("obligations", ascending=True)
    fig = go.Figure(go.Bar(
        y=plot["agency"],
        x=plot["obligations"] / 1e9,
        orientation="h",
        marker_color=[GROUP_COLOR[g] for g in plot["group"]],
        hovertemplate="%{y}<br>$%{x:.1f}B<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Obligations, $ billions",
        height=460,
        margin=dict(l=20, r=20, t=10, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Obligations are commitments, not cash outlays. FY2026 is partial and is not shown.")

with tab_provision:
    st.subheader("Supply and shortfall, side by side")
    want = ["daily_calorie_supply", "food_insecurity_moderate_or_severe", "energy_use_per_capita", "electricity_access", "safely_managed_water"]
    latest_rows = (
        series[series["indicator"].isin(want)]
        .sort_values("year")
        .groupby(["entity", "indicator"], as_index=False)
        .tail(1)
    )
    st.dataframe(
        latest_rows.sort_values(["indicator", "entity"])[["entity", "indicator", "year", "value", "unit", "source"]],
        hide_index=True,
        use_container_width=True,
    )
    usa_cal = series[(series.entity == "United States") & (series.indicator == "daily_calorie_supply")]
    usa_fi = series[(series.entity == "United States") & (series.indicator == "food_insecurity_moderate_or_severe")]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=usa_cal["year"], y=usa_cal["value"], name="kcal per person per day", line=dict(color=TEAL)))
    fig.add_trace(go.Scatter(x=usa_fi["year"], y=usa_fi["value"], name="food insecurity, %", line=dict(color=NAVY), yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title="kcal"),
        yaxis2=dict(title="percent", overlaying="y", side="right"),
        height=380,
        legend=dict(orientation="h"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("The two lines share a chart and not a unit. Coexistence is not a cause. FAO censors US undernourishment at below 2.5%, so that series is not drawn.")

with tab_gdp:
    st.subheader("A flow and a stock")
    annual = co2.groupby("year").filter(lambda g: len(g) >= 12).groupby("year", as_index=False)["ppm"].mean()
    gdp = series[(series.entity == "United States") & (series.indicator == "gdp_per_capita_constant_2015_usd")]
    joined = gdp.merge(annual, on="year")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=joined["year"], y=joined["value"], name="GDP per person, 2015 $", line=dict(color=TEAL)))
    fig.add_trace(go.Scatter(x=joined["year"], y=joined["ppm"], name="Mauna Loa annual mean, ppm", line=dict(color=NAVY), yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title="constant 2015 dollars"),
        yaxis2=dict(title="ppm", overlaying="y", side="right"),
        height=420,
        legend=dict(orientation="h"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Partial years of CO2 are left out of the annual line. The latest month is in the metric at the top. Nothing here is subtracted from GDP.")

with tab_land:
    st.subheader("Land per 100g of protein")
    st.write("Poore and Nemecek, Science, 2018, via Our World in Data. A published cross-section, not a live feed.")
    ordered = protein.sort_values("land_use_m2", ascending=True)
    fig = go.Figure(go.Bar(
        y=ordered["entity"],
        x=ordered["land_use_m2"],
        orientation="h",
        marker_color=TEAL,
        hovertemplate="%{y}<br>%{x:.1f} m2<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Square meters per 100g protein",
        height=720,
        margin=dict(l=20, r=20, t=10, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Farmed prawns use little land. The metric does not count their feed, water, or energy. That is the point of refusing a single number.")

with tab_claims:
    st.subheader("What was checked")
    st.dataframe(
        claims[["book_chapter", "statement", "verdict", "year", "evidence", "caveat"]],
        hide_index=True,
        use_container_width=True,
    )
    st.subheader("What Chapter 29 asks for that this build does not pretend to measure")
    st.dataframe(gaps, hide_index=True, use_container_width=True)
