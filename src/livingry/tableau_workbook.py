"""Build tableau/livingry_dashboard.twbx from the extracts.

Open it in Tableau Public, check the four sheets, then File > Save to Tableau Public As.
The workbook is generated, not committed.
"""

from __future__ import annotations

import csv
import hashlib
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from tableauhyperapi import (
    Connection,
    CreateMode,
    HyperProcess,
    Inserter,
    SqlType,
    TableDefinition,
    TableName,
    Telemetry,
)

from livingry import EXPORTS, ROOT

OUT = ROOT / "tableau" / "livingry_dashboard.twbx"
BUILD = "2026.2.3 (20262.26.0912.1023)"
NAVY, TEAL, BLUE, SLATE, STEEL = "#1e3a5f", "#0f766e", "#2563eb", "#64748b", "#5b8db8"
INK = "#0f172a"
DIMENSIONS = {"year", "month", "fiscal_year", "rank"}


def a(value: object) -> str:
    s = str(value)
    for old, new in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("'", "&apos;"), ('"', "&quot;")):
        s = s.replace(old, new)
    return s


def t(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def member(value: str) -> str:
    return a(f'"{value}"')


def ident(seed: str) -> str:
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while len(out) < 28:
        digest, r = divmod(digest, 36)
        out += alphabet[r]
    return out


def simple_id(seed: str) -> str:
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "livingry/" + seed)).upper() + "}"


def infer_type(values: list[str]) -> str:
    if values and all(v.lower() in ("true", "false") for v in values):
        return "boolean"
    try:
        [int(v) for v in values]
        return "integer"
    except ValueError:
        pass
    try:
        [float(v) for v in values]
        return "real"
    except ValueError:
        return "string"


def infer_columns(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    out = []
    for i, col in enumerate(header):
        values = [r[i] for r in body if i < len(r) and r[i] != ""]
        out.append((col, infer_type(values)))
    return out


def parse_value(raw: str, dtype: str):
    if raw == "":
        return None
    if dtype == "integer":
        return int(float(raw)) if "." in raw else int(raw)
    if dtype == "real":
        return float(raw)
    if dtype == "boolean":
        return raw.lower() == "true"
    return raw


def role_of(col: str, dtype: str) -> tuple[str, str]:
    if col in DIMENSIONS:
        return "dimension", "ordinal"
    if dtype in ("integer", "real"):
        return "measure", "quantitative"
    return "dimension", "nominal"


@dataclass
class Datasource:
    caption: str
    filename: str
    formats: dict[str, str] = field(default_factory=dict)
    styles: str = ""

    def __post_init__(self) -> None:
        self.name = "federated." + ident(self.caption)
        self.conn = "hyper." + ident(self.filename)
        self.columns = infer_columns(EXPORTS / self.filename)

    def ref(self, instance: str) -> str:
        return f"[{self.name}].[{instance}]"

    def column_decls(self) -> str:
        out = []
        for col, dtype in self.columns:
            role, kind = role_of(col, dtype)
            fmt = self.formats.get(col)
            fmt_attr = f" default-format='{a(fmt)}'" if fmt else ""
            out.append(
                f"<column datatype='{dtype}'{fmt_attr} name='[{a(col)}]' role='{role}' type='{kind}' />"
            )
        return "\n        ".join(out)

    @property
    def hyper_path(self) -> str:
        return f"Data/Extracts/{Path(self.filename).stem}.hyper"

    def write_hyper(self, target: Path) -> int:
        types = {"integer": SqlType.big_int(), "real": SqlType.double(), "string": SqlType.text(), "boolean": SqlType.bool()}
        table = TableDefinition(
            TableName("Extract", "Extract"),
            [TableDefinition.Column(col, types[dtype]) for col, dtype in self.columns],
        )
        with (EXPORTS / self.filename).open(newline="", encoding="utf-8") as fh:
            records = [
                [parse_value(row.get(col, ""), dtype) for col, dtype in self.columns]
                for row in csv.DictReader(fh)
            ]
        target.parent.mkdir(parents=True, exist_ok=True)
        with (
            HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU, parameters={"log_config": ""}) as hyper,
            Connection(hyper.endpoint, target, CreateMode.CREATE_AND_REPLACE) as conn,
        ):
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(table)
            with Inserter(conn, table) as inserter:
                inserter.add_rows(records)
                inserter.execute()
        return len(records)

    def xml(self) -> str:
        return f"""
    <datasource caption='{a(self.caption)}' inline='true' name='{self.name}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{a(Path(self.filename).stem)}' name='{self.conn}'>
            <connection authentication='auth-none' author-locale='en_US' class='hyper' dbname='{a(self.hyper_path)}' default-settings='yes' port='' sslmode='' username='tableau_internal_user' />
          </named-connection>
        </named-connections>
        <relation connection='{self.conn}' name='Extract' table='[Extract].[Extract]' type='table' />
      </connection>
      <aliases enabled='yes' />
        {self.column_decls()}
      <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />
      <style><style-rule element='mark'>{self.styles}</style-rule></style>
    </datasource>"""


def color_map(field_name: str, pairs: list[tuple[str, str]]) -> str:
    maps = "".join(f"<map to='{c}'><bucket>{member(v)}</bucket></map>" for v, c in pairs)
    return f"<encoding attr='color' field='{a(field_name)}' type='palette'>{maps}</encoding>"


agencies = Datasource(
    "Agency year",
    "agency_fy2025.csv",
    formats={"obligations": '"$"#,##0'},
)
agencies.styles = color_map(
    agencies.ref("none:group:nk"),
    [("weaponry", NAVY), ("livingry", TEAL), ("mixed", SLATE), ("energy", BLUE), ("provision", STEEL)],
)
co2 = Datasource("Mauna Loa", "co2_monthly.csv", formats={"ppm": "#,##0.00"})
protein = Datasource("Protein land", "protein_land.csv", formats={"land_use_m2": "#,##0.0"})
claims = Datasource("Claims", "claims.csv")
SOURCES = [agencies, co2, protein, claims]


@dataclass
class Sheet:
    name: str
    title: str
    ds: Datasource
    rows: str
    cols: str
    mark: str
    encodings: list[tuple[str, str]] = field(default_factory=list)
    instances: list[str] = field(default_factory=list)
    filters: str = ""
    style: str = ""

    def xml(self) -> str:
        inst = []
        for item in self.instances:
            prefix, col, tk = item.split(":")
            derivation = {"none": "None", "sum": "Sum", "avg": "Avg"}[prefix]
            kind = {"nk": "nominal", "ok": "ordinal", "qk": "quantitative"}[tk]
            inst.append(
                f"<column-instance column='[{a(col)}]' derivation='{derivation}' "
                f"name='[{a(item)}]' pivot='key' type='{kind}' />"
            )
        enc = "".join(f"<{kind} column='{a(ref)}' />" for kind, ref in self.encodings)
        # <style> only accepts <style-rule>. A bare <encoding> fails workbook load.
        style = self.style.strip()
        if style and not style.startswith("<style-rule"):
            style = f"<style-rule element='mark'>{style}</style-rule>"
        return f"""
    <worksheet name='{a(self.name)}'>
      <layout-options><title><formatted-text>
        <run bold='true' fontcolor='{INK}' fontsize='12'>{t(self.title)}</run>
      </formatted-text></title></layout-options>
      <table>
        <view>
          <datasources><datasource caption='{a(self.ds.caption)}' name='{self.ds.name}' /></datasources>
          <datasource-dependencies datasource='{self.ds.name}'>
            {self.ds.column_decls()}
            {" ".join(inst)}
          </datasource-dependencies>
          {self.filters}
          <aggregation value='true' />
        </view>
        <style>{style}</style>
        <panes><pane>
          <view><breakdown value='auto' /></view>
          <mark class='{self.mark}' />
          <encodings>{enc}</encodings>
        </pane></panes>
        <rows>{a(self.rows)}</rows>
        <cols>{a(self.cols)}</cols>
      </table>
      <simple-id uuid='{simple_id("sheet/" + self.name)}' />
    </worksheet>"""


sheets = [
    Sheet(
        "Obligations",
        "FY2025 obligations. Teal is the author group. HHS stays visible and is not added in.",
        agencies,
        agencies.ref("none:agency:nk"),
        agencies.ref("sum:obligations:qk"),
        "Bar",
        encodings=[("color", agencies.ref("none:group:nk"))],
        instances=["none:agency:nk", "sum:obligations:qk", "none:group:nk"],
        style=agencies.styles,
    ),
    Sheet(
        "Mauna Loa",
        "Monthly mean CO2, Mauna Loa. The current year is partial until December.",
        co2,
        co2.ref("avg:ppm:qk"),
        co2.ref("none:year:ok"),
        "Line",
        encodings=[("color", co2.ref("avg:ppm:qk"))],
        instances=["avg:ppm:qk", "none:year:ok"],
    ),
    Sheet(
        "Land per protein",
        "Square meters of land per 100g protein. Poore and Nemecek 2018, not a live feed.",
        protein,
        protein.ref("none:entity:nk"),
        protein.ref("sum:land_use_m2:qk"),
        "Bar",
        instances=["none:entity:nk", "sum:land_use_m2:qk"],
    ),
    Sheet(
        "Claims",
        "Verdicts are labels, not weights. Read the caveat column.",
        claims,
        claims.ref("none:statement:nk"),
        claims.ref("none:verdict:nk"),
        "Text",
        encodings=[("text", claims.ref("none:evidence:nk")), ("color", claims.ref("none:verdict:nk"))],
        instances=["none:statement:nk", "none:evidence:nk", "none:verdict:nk"],
    ),
]


def zone(sheet: str, zid: int, x: int, y: int, w: int, h: int) -> str:
    return (
        f"<zone h='{h}' id='{zid}' name='{a(sheet)}' w='{w}' x='{x}' y='{y}'>"
        f"<layout-cache minheight='180' type-h='fixed' type-w='fixed' /></zone>"
    )


def dashboard_xml() -> str:
    title = (
        "<zone h='8000' id='3' type-v2='text' w='100000' x='0' y='0'><formatted-text>"
        f"<run bold='true' fontcolor='{INK}' fontsize='18'>The Livingry Dashboard</run></formatted-text></zone>"
    )
    note = (
        "<zone h='5000' id='4' type-v2='text' w='100000' x='0' y='8000'><formatted-text>"
        "<run fontcolor='#334155' fontsize='10'>Each pane keeps its own unit. Nothing on this dashboard is summed into a score. "
        "HHS is mostly mandatory spending. The four teal agencies are an author grouping.</run></formatted-text></zone>"
    )
    zones = "\n".join([
        title,
        note,
        zone("Obligations", 5, 0, 14000, 56000, 42000),
        zone("Mauna Loa", 6, 56000, 14000, 44000, 42000),
        zone("Land per protein", 7, 0, 57000, 48000, 40000),
        zone("Claims", 8, 48000, 57000, 52000, 40000),
    ])
    return f"""
    <dashboard name='Livingry Dashboard'>
      <style />
      <size maxheight='1100' maxwidth='1200' minheight='1100' minwidth='1200' />
      <zones>
        <zone h='100000' id='2' type-v2='layout-basic' w='100000' x='0' y='0'>
          {zones}
        </zone>
      </zones>
      <simple-id uuid='{simple_id("dashboard")}' />
    </dashboard>"""


def window(sheet: Sheet) -> str:
    return f"""
    <window class='worksheet' name='{a(sheet.name)}'>
      <cards>
        <edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' /></strip></edge>
        <edge name='top'>
          <strip size='2147483647'><card type='columns' /></strip>
          <strip size='2147483647'><card type='rows' /></strip>
          <strip size='31'><card type='title' /></strip>
        </edge>
      </cards>
      <simple-id uuid='{simple_id("window/" + sheet.name)}' />
    </window>"""


def workbook_xml() -> str:
    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='{BUILD}' source-platform='mac' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <SheetIdentifierTracking />
    <SortTagCleanup />
    <WindowsPersistSimpleIdentifiers />
  </document-format-change-manifest>
  <preferences>
    <color-palette name='Livingry' type='regular'>
      <color>{NAVY}</color><color>{TEAL}</color><color>{BLUE}</color><color>{SLATE}</color><color>{STEEL}</color>
    </color-palette>
  </preferences>
  <datasources>{"".join(ds.xml() for ds in SOURCES)}</datasources>
  <worksheets>{"".join(s.xml() for s in sheets)}</worksheets>
  <dashboards>{dashboard_xml()}</dashboards>
  <windows source-height='30'>
    {"".join(window(s) for s in sheets)}
    <window class='dashboard' maximized='true' name='Livingry Dashboard'>
      <viewpoints>{"".join(f"<viewpoint name='{a(s.name)}'><zoom type='entire-view' /></viewpoint>" for s in sheets)}</viewpoints>
      <active id='-1' />
      <device-preview>
        <device is-portrait='true' name='Generic Phone' type='Phone' />
      </device-preview>
      <simple-id uuid='{simple_id("window/dashboard")}' />
    </window>
  </windows>
</workbook>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as twbx:
        twbx.writestr(OUT.with_suffix(".twb").name, workbook_xml())
        for ds in SOURCES:
            hyper = Path(tmp) / Path(ds.hyper_path).name
            rows = ds.write_hyper(hyper)
            twbx.write(hyper, ds.hyper_path)
            print(f"{ds.filename}: {rows} rows")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
