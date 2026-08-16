"""
Wandroz — real crime data fetch for Berlin (Bezirksregion-level)

WHY THIS SCRIPT EXISTS / WHAT IT IS AND ISN'T
  Researched 16 August 2026 as the next city after London (full automated
  pipeline) and Zurich (one narrow automated layer on a manual map).
  Berlin's own "Kriminalitätsatlas" (crime atlas) looked like the obvious
  source, but its only bulk-downloadable file is a single XLSX at
  Bezirk level (12 units — coarser than useful) with a CC-BY-SA
  (share-alike) license. Two SEPARATE, narrower datasets from the same
  publisher (Polizei Berlin / LKA St 14) turned out to be a much better
  fit: individually geocoded, near-daily-updated incident records for
  bicycle theft and vehicle break-in/theft, both licensed CC-BY (no
  share-alike restriction), both tagged with an official 8-digit LOR
  (Lebensweltlich orientierte Raum) location code per incident — Berlin's
  standard statistical geography, which lets US choose the aggregation
  level rather than being stuck with whatever the publisher pre-aggregated
  to. This script fetches both.

  Verified live via a real HTTP fetch on 16 August 2026 (through a
  connected browser tab, since this sandbox has no general outbound
  network access — see fetch_zurich.py's docstring for the same
  limitation): the newest rows in both files were dated two days before
  that check (14 August 2026), confirming these are genuinely live feeds,
  not stale exports. This script itself has NOT been run end-to-end in
  this sandbox for the same network-access reason — it mirrors
  fetch_london.py's and fetch_zurich.py's proven retry pattern and was
  written directly against the real CSV headers and a real data sample
  fetched during that verification.

WHAT THIS IS NOT
  Like Zurich's burglary layer, this is intentionally narrow: bicycle
  theft and vehicle break-in/theft only, not a broad day/night safety
  score like London's. Unlike Zurich, it's NOT layered onto an existing
  hand-curated day/night map — Berlin has no existing Wandroz zone data,
  and rather than inventing "general knowledge" ratings for a city no one
  on this project has direct local knowledge of, Berlin's first layer on
  Wandroz is this real data standing on its own, honestly scoped as a
  property-crime indicator, not a general safety score.

GEOGRAPHY
  Every incident carries an 8-digit LOR code: 2 digits Bezirk (district) +
  2 digits Prognoseraum + 2 digits Bezirksregion + 2 digits Planungsraum
  (Berlin's official nested statistical hierarchy, confirmed via the LOR
  2021 dataset description on daten.berlin.de — Amt für Statistik
  Berlin-Brandenburg, CC-BY-DE 3.0). This script aggregates to
  Bezirksregion level (the first 6 digits) — 138-143 units depending on
  vintage, matching the granularity Berlin's own Kriminalitätsatlas map
  uses for its interactive display, and a reasonable middle ground between
  the 12 Bezirke (too coarse) and ~450-540 Planungsräume (too fine-grained
  for a first pass, and noisier per-zone with these narrower crime
  categories).

  NOTE — boundary polygons for the Bezirksregionen are NOT fetched by this
  script. That requires Berlin's official LOR WFS service
  (gdi.berlin.de/services/wfs/lor_2021), which was returning a server-side
  "Wartungsarbeiten" (maintenance) page for every request during this
  research, including plain GetCapabilities — a genuine outage on Berlin's
  end, not a sandbox/tooling restriction. A separate script
  (fetch_berlin_boundaries.py, not yet written) will fetch those once the
  service is back, the same way london_boundaries.json was obtained once
  and reused rather than re-fetched every run. Without real boundaries,
  Wandroz will not render a Berlin map or publish per-zone rates — no
  invented geometry, no invented population figures, consistent with how
  this project has handled every other gap so far.

DATA SOURCES
  Bicycle theft: https://daten.berlin.de/datensaetze/fahrraddiebstahl-in-berlin
    CSV (comma-delimited): https://www.polizei-berlin.eu/Fahrraddiebstahl/Fahrraddiebstahl.csv
    Columns: ANGELEGT_AM, TATZEIT_ANFANG_DATUM, TATZEIT_ANFANG_STUNDE,
    TATZEIT_ENDE_DATUM, TATZEIT_ENDE_STUNDE, LOR, SCHADENSHOEHE, VERSUCH,
    ART_DES_FAHRRADS, DELIKT, ERFASSUNGSGRUND. License CC-BY.

  Vehicle break-in/theft: https://daten.berlin.de/datensaetze/diebstahl-an-aus-kfz
    CSV (PIPE-delimited — different from the bike file): https://www.polizei-berlin.eu/Kfzdiebstahl/Kfzdiebstahl.csv
    Columns: ANGELEGT_AM|TATZEIT_ANFANG_DATUM|TATZEIT_ANFANG_STUNDE|
    TATZEIT_ENDE_DATUM|TATZEIT_ENDE_STUNDE|LOR|SCHADENSHOEHE|VERSUCH|
    DELIKT|EINDRINGEN_IN_KFZ|ERLANGTES_GUT. License CC-BY. DELIKT
    distinguishes "Einfacher Diebstahl an/aus Kfz" (simple) from
    "Schwerer Diebstahl an/aus Kfz" (aggravated) — both counted together
    here for a first pass.

  Both files are a ROLLING window of recent incidents (not a fixed
  historical archive going back years), refreshed close to daily. This
  script filters to the most recent 365 days found in each file (relative
  to that file's own newest record, not today's date, so a delayed run
  still gets a full year) rather than assuming a fixed window, and
  discovers the actual dates present at fetch time rather than hardcoding
  an assumption about how far back the data goes.

WHAT THIS SCRIPT DOES
  1. Downloads both CSVs.
  2. Parses each, filtering to the most recent 365 days by
     TATZEIT_ANFANG_DATUM (the actual offence date, not the record-created
     date), skipping rows with unparseable dates or malformed LOR codes.
  3. Aggregates incident counts per Bezirksregion (LOR code truncated to
     6 digits).
  4. Writes data/raw_berlin/bike_theft_by_bezirksregion.json and
     data/raw_berlin/vehicle_crime_by_bezirksregion.json (each a dict of
     6-digit Bezirksregion code -> incident count for the window), plus
     data/raw_berlin/manifest.json recording the fetch timestamp, the
     actual date window used per file, total rows read, and rows skipped.

USAGE
  python pipeline/fetch_berlin.py
"""

import csv
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw_berlin")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")

USER_AGENT = "wandroz-site-fetch/0.1 (https://wandroz.com; automated refresh)"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
WINDOW_DAYS = 365

SOURCES = {
    "bike_theft": {
        "url": "https://www.polizei-berlin.eu/Fahrraddiebstahl/Fahrraddiebstahl.csv",
        "delimiter": ",",
        "out_file": "bike_theft_by_bezirksregion.json",
        "dataset_page": "https://daten.berlin.de/datensaetze/fahrraddiebstahl-in-berlin",
    },
    "vehicle_crime": {
        "url": "https://www.polizei-berlin.eu/Kfzdiebstahl/Kfzdiebstahl.csv",
        "delimiter": "|",
        "out_file": "vehicle_crime_by_bezirksregion.json",
        "dataset_page": "https://daten.berlin.de/datensaetze/diebstahl-an-aus-kfz",
    },
}


def _download_csv(url):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*"}, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            print(f"  request error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 200:
            return resp.content.decode("utf-8", errors="replace")
        last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        print(f"  unexpected status (attempt {attempt}/{MAX_RETRIES}): {last_error}")
        time.sleep(2 * attempt)
    raise last_error


def _parse_date(raw):
    """Berlin police CSVs use DD.MM.YYYY. Returns a date object or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_and_aggregate(csv_text, delimiter):
    """Returns (counts_by_bezirksregion: dict[str,int], window_start, window_end,
    rows_total, rows_kept, rows_skipped_date, rows_skipped_lor)."""
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    rows = list(reader)
    rows_total = len(rows)

    dates = [d for d in (_parse_date(r.get("TATZEIT_ANFANG_DATUM")) for r in rows) if d]
    if not dates:
        return {}, None, None, rows_total, 0, rows_total, 0
    newest = max(dates)
    window_start = newest - timedelta(days=WINDOW_DAYS)

    counts = {}
    rows_skipped_date = 0
    rows_skipped_lor = 0
    rows_kept = 0
    for row in rows:
        d = _parse_date(row.get("TATZEIT_ANFANG_DATUM"))
        if not d or d < window_start:
            rows_skipped_date += 1
            continue
        lor = (row.get("LOR") or "").strip()
        if len(lor) < 6 or not lor[:6].isdigit():
            rows_skipped_lor += 1
            continue
        bzr = lor[:6]
        counts[bzr] = counts.get(bzr, 0) + 1
        rows_kept += 1

    return counts, window_start.isoformat(), newest.isoformat(), rows_total, rows_kept, rows_skipped_date, rows_skipped_lor


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    manifest = {"fetched_sources": {}}
    any_success = True

    for key, cfg in SOURCES.items():
        print(f"Downloading {key} from {cfg['url']} ...")
        try:
            csv_text = _download_csv(cfg["url"])
        except Exception as exc:
            print(f"FATAL: could not download {key}: {exc}")
            any_success = False
            continue

        counts, window_start, window_end, total, kept, skip_date, skip_lor = parse_and_aggregate(csv_text, cfg["delimiter"])
        if not counts:
            print(f"FATAL: no usable rows parsed for {key} — schema may have changed")
            any_success = False
            continue

        out_path = os.path.join(RAW_DIR, cfg["out_file"])
        with open(out_path, "w") as f:
            json.dump(counts, f, indent=2, sort_keys=True)

        manifest["fetched_sources"][key] = {
            "source_csv": cfg["url"],
            "dataset_page": cfg["dataset_page"],
            "window_start": window_start,
            "window_end": window_end,
            "rows_total": total,
            "rows_kept": kept,
            "rows_skipped_out_of_window": skip_date,
            "rows_skipped_bad_lor": skip_lor,
            "bezirksregionen_covered": len(counts),
            "file": os.path.relpath(out_path, os.path.dirname(RAW_DIR)),
        }
        print(f"  {key}: {kept}/{total} rows kept, {len(counts)} Bezirksregionen, window {window_start} to {window_end}")

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    if not any_success:
        print("FATAL: at least one source failed entirely — see above")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
