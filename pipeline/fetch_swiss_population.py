"""
Official resident population per area for Bern and Basel.

WHY
    Bern and Basel are the two cities on this site with official geography and
    no official number behind any area: neither canton publishes crime below
    the municipality, so 36 of their 49 areas ended their page saying the
    review had found nothing. That statement is true and it is also all the
    page had.

    What both cities DO publish, per area and current, is how many people live
    there. That is not a crime figure and it is not a safety verdict, and this
    script does not turn it into one. It is context a reader of a safety map
    actually uses: whether a quarter is lived-in or mostly workplaces, and
    whether "nothing reported" covers four hundred people or twenty thousand.

SOURCES
    Bern   Statistik Stadt Bern, T 01.04.040 "Bevölkerungsbestand nach Heimat
           und Geschlecht", statistische Bezirke, end of year. XLSX.
           The city's edge blocks a bare request; it serves the file to a
           browser user agent, so one is sent.
    Basel  Kanton Basel-Stadt open data, dataset 100126 "Wohnbevölkerung nach
           Geschlecht, Staatsangehörigkeit und Wohnviertel", summed per
           Wohnviertel for the latest full year. JSON API.

    Only the total is read from either. Both datasets break the figure down by
    nationality, and build_basel_zones.py already refuses that class of field
    for a reason that has not changed: colouring neighbourhoods by who lives in
    them is not what this site does.

USAGE
    python3 pipeline/fetch_swiss_population.py
"""
import io
import json
import os
import sys
import urllib.request
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_DIR = os.path.join(REPO, "data", "raw_swiss")

BERN_XLSX = ("https://www.bern.ch/themen/stadt-recht-und-politik/bern-in-zahlen/"
             "katost/01bev/01bev-xls/jahresdaten/"
             "t-01-04-040-bevolkerungsbestand-nach-heimat-und.xlsx/download")
# %20 in the query would collide with %-formatting, so the year is substituted
# by name rather than by position.
BASEL_API = ("https://data.bs.ch/api/explore/v2.1/catalog/datasets/100126/records"
             "?limit=60&group_by=wohnviertel_name"
             "&select=wohnviertel_name,sum(anzahl)%20as%20pop&where=jahr={year}")

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# The Stadtteil rows are sums of the districts above them, and the five
# colour-named medieval quarters are the parts of Innere Stadt (they add to its
# 4,149 exactly). Neither is an area on this map; both would double-count.
BERN_SKIP = {
    "Länggasse-Felsenau", "Mattenhof-Weissenbühl", "Kirchenfeld-Schosshalde",
    "Breitenrain-Lorraine", "Bümpliz-Oberbottigen",
    "Schwarzes Quartier", "Weisses Quartier", "Grünes Quartier",
    "Gelbes Quartier", "Rotes Quartier",
}


def _get(url, browser=False):
    req = urllib.request.Request(url)
    if browser:
        req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def bern():
    raw = _get(BERN_XLSX, browser=True)
    if raw[:2] != b"PK":
        raise SystemExit("bern.ch returned %d bytes that are not a spreadsheet "
                         "— the edge is blocking this request" % len(raw))
    z = zipfile.ZipFile(io.BytesIO(raw))
    sst = []
    for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
        sst.append("".join(t.text or "" for t in si.iter(MAIN + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    years = [s.get("name") for s in wb.find("m:sheets", NS)]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    out = {}
    for row in sheet.iter(MAIN + "row"):
        vals = []
        for c in row:
            v = c.find("m:v", NS)
            vals.append("" if v is None
                        else (sst[int(v.text)] if c.get("t") == "s" else v.text))
        if len(vals) > 3 and vals[2] and vals[3]:
            name = vals[2].strip()
            if name in BERN_SKIP:
                continue
            try:
                out[name] = int(float(vals[3]))
            except ValueError:
                pass
    return {"year": years[0], "source": "Statistik Stadt Bern, T 01.04.040",
            "areas": out}


def basel(year=2025):
    data = json.loads(_get(BASEL_API.format(year=year)))
    out = {r["wohnviertel_name"]: int(r["pop"]) for r in data.get("results", [])}
    if not out:
        raise SystemExit("data.bs.ch returned no rows for %d" % year)
    return {"year": str(year),
            "source": "Kanton Basel-Stadt open data, dataset 100126",
            "areas": out}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, fn in (("bern", bern), ("basel", basel)):
        doc = fn()
        path = os.path.join(OUT_DIR, "%s_population.json" % name)
        io.open(path, "w", encoding="utf-8").write(
            json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        total = sum(doc["areas"].values())
        print("%-6s %2d areas, %s residents at end %s -> %s"
              % (name, len(doc["areas"]), "{:,}".format(total), doc["year"],
                 os.path.relpath(path, REPO)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
