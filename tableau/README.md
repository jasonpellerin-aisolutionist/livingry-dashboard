# Tableau Public

`make tableau` writes `tableau/livingry_dashboard.twbx` (generated, not committed) with
four sheets and one dashboard:

1. **Obligations.** FY2025 only. Color is the author group: navy weaponry, teal livingry,
   slate HHS, blue energy, steel education.
2. **Mauna Loa.** Monthly mean. The current calendar year is partial until December.
3. **Land per protein.** Poore and Nemecek 2018. Not a live feed.
4. **Claims.** One row per check, with the caveat in the text mark.

Palette is navy `#1e3a5f`, teal `#0f766e`, blue `#2563eb`, slate `#64748b`. No red or orange.

Open the `.twbx` in Tableau Public Desktop, check each sheet, then File > Save to Tableau
Public As. The extracts are also in `tableau/exports/` if you would rather build by hand.
