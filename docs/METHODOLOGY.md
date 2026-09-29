# Methodology

The question this dashboard answers is the one Chapter 29 of *The Livingry Protocol* asks:
what would it look like to report life-support and ecological state in their own units,
refreshed from public sources, without collapsing them into a single score?

The manuscript is unpublished. This repository is the instrument, not the book.

## What is measured

| Family | Series | Source | Grain |
|---|---|---|---|
| Priority | Agency obligations and outlays | USAspending `budgetary_resources` | US fiscal year, eight agencies |
| Priority | Top contract recipients | USAspending `spending_by_category/recipient` | FY2025, top 15 |
| Priority | Military expenditure as a share of GDP | SIPRI via Our World in Data | Country-year |
| Provision | Daily calorie supply | FAO food balances via Our World in Data | Country-year |
| Provision | Moderate or severe food insecurity | FAO FIES, SDG 2.1.2, via Our World in Data | Country-year |
| Provision | Undernourishment | FAO, SDG 2.1.1, via the UN SDG API | World, and the US floor |
| Provision | Primary energy per person | Our World in Data, kWh per person | Country-year |
| Provision | Electricity access, safely managed water | World Bank | Country-year |
| Accounts | GDP per capita, constant 2015 dollars | World Bank | Country-year |
| Ecological state | Atmospheric CO2 | NOAA Mauna Loa monthly mean | Month |
| Ecological state | Territorial CO2 per person | Global Carbon Project via Our World in Data | Country-year |
| Ecological state | Agricultural land | FAO via Our World in Data | Country-year |
| Land per protein | Square meters per 100g protein, by food | Poore and Nemecek 2018 via Our World in Data | Cross-section, grapher year 2010 |

Places kept from the country panels are the United States and the World. The protein table keeps every food.

## What is deliberately not measured

Chapter 29 names restoration rate, rivers cleaner downstream than upstream, unpaid care,
legitimacy (cases and time to remedy), and resilience. None of those have a public feed
wired in here. They are listed in `not_measured.csv` so a later reader does not mistake
silence for a finding.

Chapter 1 refuses a vacant-homes versus homeless-people comparison. That comparison is
not computed.

Chapter 29 refuses a composite index, because any index hides the weights. No score,
weight, or index column exists. A test fails the build if one appears.

## Rules that travel with the numbers

1. **Obligations are not outlays.** An obligation is a commitment. Cash can move later.
2. **FY2026 is partial.** Claims use FY2025, the last complete fiscal year. September
   obligations are still landing, and they are not spread evenly across the year.
3. **HHS is not a livingry total.** Its obligations are mostly Medicare and Medicaid.
   It is shown, and it is never added into the four-agency group.
4. **The four-agency group is an author grouping.** Agriculture, EPA, Housing, and
   Interior. The Excel sheet states the choice as a `SUMIF` of those four names.
   Energy and Education are on the chart and outside the group.
5. **A contractor and an agency are different kinds of quantity.** Lockheed's largest
   registration (UEI G4KDGE4JFFK7) is reported next to EPA's total obligations as a
   comparison of scale. Other Lockheed registrations in the top 15 are listed and not
   summed. This is the same rule the manuscript already uses.
6. **Coexistence is not a cause.** Calories and food insecurity share a year. They do
   not share a mechanism inside this repo.
7. **GDP and CO2 share a chart and not a formula.** The annual CO2 mean uses years
   with all twelve months. The latest month is labeled as a month.
8. **FAO's undernourishment series is estimated.** Years whose footnote says the value
   is projected are not used as the endpoint of the trend. The United States is
   published as `<2.5`, which is a floor, not a rate, and not evidence that hunger is gone.
   The US shortfall on this dashboard is SDG 2.1.2.
9. **Military spending as a share of GDP is not divided into an obligation.** SIPRI and
   USAspending answer different questions and are never combined.
10. **Land per protein is not live.** It is one published study. Farmed prawns rank at
    the bottom because the metric is land. Feed, water, and energy are outside it.

## Refresh

`make refresh` re-queries every source and raises if one fails, so a missing feed cannot
quietly drop a claim. `make build` writes the extracts, the claim sheet, and the quality
log. A weekly GitHub Action does the same and commits the extracts.

Raw pulls are cached in `data/raw/` and are not committed. The committed extracts are
the aggregates above.
