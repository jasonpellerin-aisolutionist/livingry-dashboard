"""The Livingry Dashboard: public indicators for an unpublished manuscript."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
EXPORTS = ROOT / "tableau" / "exports"
APP_DATA = ROOT / "app" / "data"
REPORTS = ROOT / "reports"

# Last complete US fiscal year. FY2026 ends 2026-09-30 and September obligations
# are still landing, so FY2026 is stored and labeled partial. Claims use this year.
COMPLETE_FY = 2025
