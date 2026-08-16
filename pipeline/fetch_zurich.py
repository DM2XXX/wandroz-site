"""
Wandroz — real burglary data fetch for Zurich (Kreis-level)

WHY THIS SCRIPT EXISTS / WHAT IT IS AND ISN'T
  Research done 15-16 August 2026 found that, unlike London's
  data.police.uk, there is NO official crime dataset for Zurich broken
  down to the 34 "Statistische Quartiere" the map already shows — the
  Kantonspolizei Zürich's general crime statistics (PKS) dataset that
  WOULD cover all offense categories at that resolution has not actually
  been updated since 2023 (data frozen at year 2022) despite claiming an
  annual cadence, so it can't honestly be called a live automated feed.

  However, one narrower dataset IS real, current, and genuinely
  auto-updated: the Kantonspolizei Zürich's burglary statistics
  ("Einbrüche"), published via Stadt Zürich's open data portal, broken
  down by the city's 12 Stadtkreise (city districts) — last refreshed
  days before this was written, with data through 2025. This script pulls
  THAT dataset. It is intentionally narrow (burglaries only, not a
  day/night safety score) and intentionally coarser than the 34-Quartier
  map (Kreis-level, not Quartier-level) — score_zurich.py and the site
  copy are explicit about both limits rather than presenting this as
  equivalent to London's pipeline.

DATA SOURCE
  https://data.stadt-zuerich.ch/dataset/ktzh_pks_einbrueche_gemeinden_stadtkreise
  CSV: KTZH_00002042_00004083.csv — CC-BY, published by Statistisches Amt
  Kanton Zürich / Kantonspolizei Zürich. Columns include Ausgangsjahr
  (year), Gemeindename, Stadtkreis_Name ("Kreis 1".."Kreis 12" for the
  city of Zürich, or blank/other for other Kanton Zürich municipalities),
  Tatbestand (offense type: "Einbruchdiebstahl", "Einschleichdiebstahl",
  "Einbrüche insgesamt" = burglary theft / sneak-in theft / total
  burglaries), Straftaten_total, Einwohner (population), and Häufigkeitszahl
  (the OFFICIAL rate per 1000 residents — already computed by the data
  provider, used as-is rather than recomputed, since it's their own
  population baseline).

  This script (like fetch_london.py) is meant to run in GitHub Actions,
  not the Claude Cowork sandbox this was written in — this sandbox's
  network can't reach data.stadt-zuerich.ch at all (confirmed: even a
  plain curl to unrelated domains fails here), so nothing here has been
  tested end-to-end from the sandbox; it mirrors fetch_london.py's proven
  retry/manifest pattern and was validated by fetching the real CSV
  through a connected browser tab before being written into this script.

WHAT THIS SCRIPT DOES
  1. Downloads the full CSV (it's small — a few thousand rows — so no
     pagination or per-Kreis querying is needed, unlike London's API).
  2. Filters to rows where Gemeindename == "Zürich" and Stadtkreis_Name
     matches "Kreis 1".."Kreis 12" (excludes "unbekannt" and every other
     Kanton Zürich municipality in the same file).
  3. For each Kreis and year found, writes
     data/raw_zurich/kreis_{n}_{year}.json (list of row dicts for that
     Kreis/year — all Tatbestand rows, so score_zurich.py can pick the
     "Einbrüche insgesamt" total plus the sub-category breakdown).
  4. Updates data/raw_zurich/manifest.json so re-runs don't redo work for
     a Kreis/year already saved (published data for a past year doesn't
     change), mirroring fetch_london.py's manifest pattern.

USAGE
  python pipeline/fetch_zurich.py
"""

import csv
import io
import json
import os
import re
import sys
import time

import requests

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw_zurich")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")

CSV_URL = (
    "https://data.stadt-zuerich.ch/dataset/ktzh_pks_einbrueche_gemeinden_stadtkreise"
    "/download/KTZH_00002042_00004083.csv"
)
USER_AGENT = "wandroz-site-fetch/0.1 (https://wandroz.com; automated annual refresh)"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

KREIS_PATTERN = re.compile(r"^Kreis (\d{1,2})$")


def _slugify_kreis(n):
    return f"kreis_{n}"


def _download_csv():
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(CSV_URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            print(f"  request error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 200:
            return resp.content.decode("utf-8-sig")
        last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        print(f"  unexpected status (attempt {attempt}/{MAX_RETRIES}): {last_error}")
        time.sleep(2 * attempt)
    raise last_error


def parse_kreis_rows(csv_text):
    """Returns dict: (kreis_number:int, year:str) -> list of row dicts,
    restricted to the city of Zürich's 12 Stadtkreise."""
    reader = csv.DictReader(io.StringIO(csv_text))
    grouped = {}
    for row in reader:
        if row.get("Gemeindename", "").strip() != "Zürich":
            continue
        m = KREIS_PATTERN.match(row.get("Stadtkreis_Name", "").strip())
        if not m:
            continue
        kreis_n = int(m.group(1))
        year = row.get("Ausgangsjahr", "").strip()
        if not year:
            continue
        grouped.setdefault((kreis_n, year), []).append(row)
    return grouped


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def write_kreis_year_file(kreis_n, year, rows):
    os.makedirs(RAW_DIR, exist_ok=True)
    slug = _slugify_kreis(kreis_n)
    out_path = os.path.join(RAW_DIR, f"{slug}_{year}.json")
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    return out_path


def main():
    print("Downloading Kantonspolizei Zürich burglary CSV ...")
    try:
        csv_text = _download_csv()
    except Exception as exc:
        print(f"FATAL: could not download CSV: {exc}")
        sys.exit(1)

    grouped = parse_kreis_rows(csv_text)
    if not grouped:
        print("FATAL: no Kreis-level Zürich rows found in CSV — schema may have changed")
        sys.exit(1)

    years_found = sorted({year for (_, year) in grouped})
    kreise_found = sorted({k for (k, _) in grouped})
    print(f"Found {len(kreise_found)} Stadtkreise, years {years_found[0]}-{years_found[-1]}")

    manifest = load_manifest()
    any_written = False
    for (kreis_n, year), rows in grouped.items():
        slug = _slugify_kreis(kreis_n)
        already = manifest.get(slug, {}).get(year)
        if already:
            continue
        out_path = write_kreis_year_file(kreis_n, year, rows)
        manifest.setdefault(slug, {})[year] = {
            "fetched_rows": len(rows),
            "source": "ktzh_pks_einbrueche_gemeinden_stadtkreise",
            "file": os.path.relpath(out_path, os.path.dirname(RAW_DIR)),
        }
        any_written = True
        print(f"  wrote {slug} / {year} ({len(rows)} rows)")

    save_manifest(manifest)
    print("Done." if any_written else "Nothing new to fetch — all Kreis/years already present.")


if __name__ == "__main__":
    main()
