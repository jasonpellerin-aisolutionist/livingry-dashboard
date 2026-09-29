"""Cover and two charts. Navy, teal, slate, blue. No red, no orange."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from livingry import EXPORTS, REPORTS

NAVY = "#1e3a5f"
TEAL = "#0f766e"
BLUE = "#2563eb"
SLATE = "#64748b"
INK = "#0f172a"
PAPER = "#f8fafc"

GROUP_COLOR = {
    "weaponry": NAVY,
    "livingry": TEAL,
    "mixed": SLATE,
    "energy": BLUE,
    "provision": "#5b8db8",
}


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.edgecolor": "#cbd5e1",
        "axes.labelcolor": INK,
        "xtick.color": SLATE,
        "ytick.color": SLATE,
        "text.color": INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.titlecolor": INK,
    })


def cover(agencies: pd.DataFrame, co2: pd.DataFrame) -> None:
    fy = agencies[(agencies["fiscal_year"] == 2025) & (agencies["agency_code"] != "075")]
    fy = fy.sort_values("obligations", ascending=True)
    fig = plt.figure(figsize=(12, 6.3), dpi=120)
    fig.patch.set_facecolor(NAVY)
    ax_text = fig.add_axes((0.04, 0.08, 0.42, 0.84))
    ax_text.set_axis_off()
    ax_text.set_xlim(0, 1)
    ax_text.set_ylim(0, 1)
    ax_text.text(0, 0.92, "The Livingry Dashboard", color="white", fontsize=20, fontweight="bold")
    ax_text.text(0, 0.84, "Indicators in their own units. No score.", color="#cbd5e1", fontsize=11)
    dod = fy.loc[fy["agency_code"] == "097", "obligations"].iloc[0] / 1e9
    epa = fy.loc[fy["agency_code"] == "068", "obligations"].iloc[0] / 1e9
    latest = co2.iloc[-1]
    lines = [
        (0.70, "FY2025", "#5eada5", 11),
        (0.58, f"${dod:.0f}B  Defense", "white", 20),
        (0.44, f"${epa:.1f}B  EPA", "#5eada5", 20),
        (0.30, f"{latest['ppm']:.1f} ppm", "white", 18),
        (0.22, f"Mauna Loa, {int(latest['year'])}-{int(latest['month']):02d}", "#cbd5e1", 10),
        (0.06, "HHS ($2.8T, mostly mandatory) is off this chart.", "#94a3b8", 8),
        (0.00, "Manuscript in progress. Not a published book.", "#94a3b8", 8),
    ]
    for y, text, color, size in lines:
        weight = "bold" if size >= 18 else "normal"
        ax_text.text(0, y, text, color=color, fontsize=size, fontweight=weight)

    ax = fig.add_axes((0.52, 0.16, 0.44, 0.68))
    ax.set_facecolor(NAVY)
    colors = [GROUP_COLOR.get(g, SLATE) for g in fy["group"]]
    # Light bars on a navy field: teal and a pale slate, still inside the allowed set.
    light = {"weaponry": "#93c5fd", "livingry": "#5eead4", "mixed": "#cbd5e1", "energy": "#bfdbfe", "provision": "#99f6e4"}
    colors = [light.get(g, "#cbd5e1") for g in fy["group"]]
    short = {
        "Department of Defense": "Defense",
        "Department of Agriculture": "Agriculture",
        "Department of Education": "Education",
        "Department of Energy": "Energy",
        "Department of Housing and Urban Development": "HUD",
        "Department of the Interior": "Interior",
        "Environmental Protection Agency": "EPA",
    }
    labels = [short.get(name, name) for name in fy["agency"]]
    ax.barh(labels, fy["obligations"] / 1e9, color=colors)
    ax.set_xlabel("FY2025 obligations, $B", color="#cbd5e1")
    ax.tick_params(colors="#e2e8f0")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_title("FY2025 obligations, HHS excluded", color="white", loc="left", fontsize=11)
    fig.savefig(REPORTS / "figures" / "cover.png", dpi=140)
    plt.close(fig)


def gdp_co2(series: pd.DataFrame, co2: pd.DataFrame) -> None:
    annual = co2.groupby("year").filter(lambda g: len(g) >= 12).groupby("year")["ppm"].mean()
    gdp = series[(series["entity"] == "United States") & (series["indicator"] == "gdp_per_capita_constant_2015_usd")]
    joined = gdp.set_index("year")["value"].to_frame("gdp").join(annual.rename("ppm"), how="inner")
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=130)
    ax.plot(joined.index, joined["gdp"] / 1000, color=TEAL, linewidth=2.2, label="GDP per person, thousand 2015 $")
    ax.set_ylabel("Thousand constant 2015 dollars", color=TEAL)
    ax2 = ax.twinx()
    ax2.plot(joined.index, joined["ppm"], color=NAVY, linewidth=2.2, label="Mauna Loa, ppm")
    ax2.set_ylabel("ppm", color=NAVY)
    ax.set_title("Two series. Not an index.")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [line.get_label() for line in lines], frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(REPORTS / "figures" / "gdp_beside_co2.png")
    plt.close(fig)


def main() -> None:
    _style()
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    agencies = pd.read_csv(EXPORTS / "agency_year.csv", dtype={"agency_code": str})
    agencies["agency_code"] = agencies["agency_code"].str.zfill(3)
    co2 = pd.read_csv(EXPORTS / "co2_monthly.csv")
    series = pd.read_csv(EXPORTS / "series.csv")
    cover(agencies, co2)
    gdp_co2(series, co2)
    print("wrote reports/figures/cover.png and gdp_beside_co2.png")


if __name__ == "__main__":
    main()
