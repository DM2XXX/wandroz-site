"""
How many places are there to break into in each Zurich district?

WHY THIS EXISTS
    Zurich's burglary figures were published per 1,000 residents, and Kreis 1
    came out at 39.5 — four times the city average, the worst district by a
    wide margin, covering Lindenhof, Rathaus, City and Hochschulen. Those are
    the four quarters this site otherwise calls the best places in Zurich to
    stay. One of the two statements had to be wrong.

    Neither was. The rate was arithmetically correct and it was measuring the
    wrong thing. Burglary is a crime against premises — someone breaks into a
    building. A district's homes are roughly its residents; its shops, offices
    and hotels are roughly its workplaces. Kreis 1 has 5,492 residents and
    78,087 people working in it. Dividing break-ins at all of those premises by
    the residents alone counts the burglaries and ignores most of the places
    they happened.

    Corrected, Kreis 1 goes from 3.84x the city average to 0.80x: not the most
    burgled district in Zurich, one of the least, for the number of places
    there are to burgle.

WHAT THIS FETCHES
    STATENT (Statistik der Unternehmensstruktur), employees per Stadtkreis,
    from the City of Zurich's open data portal — dataset
    bfs_wir_statent_ast_beschaeftigte_vza_sektor_jahr_od2551, annual since
    2011. The same source also breaks down to the 34 Quartiere, which is finer
    than the burglary data (12 Kreise), so the Kreis level is what is used.

    An older dataset on the same portal gives workplaces per Quartier but stops
    at the 2008 Betriebszählung. Zurich West was an industrial estate in 2008
    and is a business district now; a seventeen-year-old denominator would
    import a bigger error than the one being fixed.

USAGE
    python3 pipeline/fetch_zurich_premises.py
"""
import csv
import io
import json
import os
import re
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "..", "data", "raw_zurich", "employees_by_kreis.json")

URL = ("https://data.stadt-zuerich.ch/dataset/"
       "bfs_wir_statent_ast_beschaeftigte_vza_sektor_jahr_od2551/download/WIR255OD2551.csv")

KREIS_RE = re.compile(r"Kreis (\d+)$")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "wandroz/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8-sig")

    by_kreis = {}
    for row in csv.DictReader(io.StringIO(text)):
        # "Alle Sektoren" is the all-industries total; without this filter every
        # district would be counted once per economic sector.
        if row["BrancheLang"] != "Alle Sektoren":
            continue
        m = KREIS_RE.match(row["RaumLang"])
        if not m:
            continue
        by_kreis.setdefault(int(m.group(1)), {})[int(row["Jahr"])] = int(row["AnzBesch"])

    if len(by_kreis) != 12:
        raise SystemExit("expected 12 Kreise, got %d — schema changed" % len(by_kreis))

    year = max(y for years in by_kreis.values() for y in years)
    employees = {}
    for k, years in by_kreis.items():
        if year not in years:
            raise SystemExit("Kreis %d has no %d figure" % (k, year))
        employees["kreis_%d" % k] = years[year]

    out = {
        "source": URL,
        "source_name": ("STATENT / Statistik der Unternehmensstruktur, "
                        "Statistik Stadt Zürich"),
        "year": year,
        "employees": employees,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print("Wrote %s — %d Kreise, %d employees citywide, year %d"
          % (OUT_PATH, len(employees), sum(employees.values()), year))


if __name__ == "__main__":
    main()
