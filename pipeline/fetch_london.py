"""
Wandroz — full monthly crime data fetch for London boroughs (v3: all 32
boroughs, auto-discovered from the real boundary file)

WHY THIS SCRIPT EXISTS
  The original prototype data in data/raw/*.json was pulled through a
  browser text-extraction tool inside a network-restricted sandbox, which
  silently truncated each borough to its first ~170 crime records instead
  of the full month. This script replaces that hack with a real HTTP
  client (requests) that pulls the COMPLETE monthly response from the
  official UK Police API. It is meant to run in GitHub Actions (normal,
  unrestricted outbound network), not in a Claude sandbox — see
  .github/workflows/refresh-data.yml.

DATA SOURCE
  https://data.police.uk/api/crimes-street/all-crime — official "street
  level crime" endpoint. Documentation: https://data.police.uk/docs/

  v1 of this script queried by borough centroid (lat/lng), which the API
  implicitly expands to roughly a 1-mile-radius CIRCLE around that point —
  not the real administrative boundary, so incidents near a border could be
  attributed to the wrong neighbour. v2 instead POSTs each borough's real
  polygon boundary via the API's "poly" parameter (the same ONS 2021
  boundary coordinates the interactive map already draws, loaded from
  pipeline/data_zones/london_boundaries.json), so the crime count matches
  the exact shape shown on the map. POST is used rather than GET because
  several of these boundaries — Lambeth's ring alone has 135 points —
  produce a query string longer than the API's 4094-character GET limit;
  the docs explicitly say to use POST for complex polygons.

  v3 (this version) stops hand-maintaining a fixed list of borough
  centroids entirely: every borough is now discovered directly from
  london_boundaries.json (all 33 ONS boundary zones, minus the City of
  London — see EXCLUDED_ZONES), with its poly string AND its fallback
  centroid (a simple average of its boundary ring's points) both computed
  from the same real boundary data. Adding a borough to the automated
  pipeline going forward only requires adding its population/workday data
  to score_london.py — this script already covers it automatically.

  If a borough's boundary can't be found for any reason, this script falls
  back to the old point/1-mile-radius circle for that borough only, and
  records which method was actually used in manifest.json so
  score_london.py / the site can be honest about it.

WHAT THIS SCRIPT DOES
  1. Asks the API which months of data are currently available
     (GET /api/crimes-street-dates) and picks the MONTHS_TO_FETCH most
     recent ones (3 by default), unless FETCH_MONTHS is set explicitly.
     Fetching a rolling window of months (not just the latest) is what
     lets score_london.py average across them instead of a single month's
     data swinging a borough's relative position — see that module's
     docstring for why this matters.
  2. For each borough discovered from london_boundaries.json and each
     month in that window, POSTs its real polygon boundary (falling back
     to point+radius if the boundary is missing) and pulls the full crime
     list for that month.
  3. Writes data/raw/{slug}_{YYYY-MM}.json — same shape score_london.py
     already expects (a plain JSON list of raw crime records).
  4. Updates data/raw/manifest.json so re-runs don't need to re-fetch a
     month that's already saved (each borough/month pair is fetched at
     most once, ever), and so the GitHub Actions "commit only if changed"
     step has something meaningful to diff. This means the first run after
     this change fetches 2 extra months per borough (a bigger one-off
     batch); every run after that only fetches the single new month that
     rolls into the window each time the API publishes one.

USAGE
  python pipeline/fetch_london.py                # fetch latest MONTHS_TO_FETCH available months
  FETCH_MONTHS=2026-06,2026-07 python pipeline/fetch_london.py   # backfill specific months
"""

import json
import os
import re
import sys
import time
from urllib.parse import urlencode

import requests

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")
BOUNDARIES_PATH = os.path.join(BASE_DIR, "data_zones", "london_boundaries.json")

API_BASE = "https://data.police.uk/api"
USER_AGENT = "wandroz-site-fetch/0.3 (https://wandroz.com; automated monthly refresh)"
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite to a free public API
MAX_RETRIES = 3

# How many of the most recent published months to keep fetched per
# borough, when FETCH_MONTHS isn't set explicitly. score_london.py
# averages across whatever's on disk (up to this many months) rather than
# scoring off a single month — see its docstring.
MONTHS_TO_FETCH = 3

# Zones present in the boundary file that are intentionally NOT part of
# this dataset. City of London is policed by the City of London Police,
# not the Met — data.police.uk's Met Police force area doesn't cover it,
# so it's excluded rather than silently scored on the wrong force's data.
EXCLUDED_ZONES = {"city of london"}


def _slugify(name):
    """Same normalisation convention already used for the first 5
    boroughs (e.g. 'Kensington and Chelsea' -> 'kensington_chelsea'):
    lowercase, drop 'and', join remaining tokens with underscores."""
    name = name.lower().replace("&", " and ")
    tokens = [t for t in re.split(r"[\s\-_]+", name) if t and t != "and"]
    return "_".join(tokens)


def load_boroughs():
    """slug -> {"label": original boundary name, "poly": 'lat,lng:...'
    string, "centroid": (lat, lng)}, built directly from every zone in
    london_boundaries.json except EXCLUDED_ZONES. Coordinates are rounded
    to 6 decimal places (~11cm precision, far finer than needed) to keep
    the POST body a reasonable size. The centroid (a plain average of the
    boundary ring's points, not a proper geometric centroid) is only used
    as a last-resort fallback if the poly query itself fails for some
    reason — the primary fetch always uses the real polygon."""
    if not os.path.exists(BOUNDARIES_PATH):
        return {}
    with open(BOUNDARIES_PATH) as f:
        data = json.load(f)

    boroughs = {}
    for z in data.get("zones", []):
        name = z.get("name", "")
        if name.strip().lower() in EXCLUDED_ZONES:
            continue
        if not z.get("coords"):
            continue
        ring = max(z["coords"], key=len)  # largest ring if more than one
        poly = ":".join(f"{lat:.6f},{lng:.6f}" for lat, lng in ring)
        lat = sum(p[0] for p in ring) / len(ring)
        lng = sum(p[1] for p in ring) / len(ring)
        boroughs[_slugify(name)] = {"label": name, "poly": poly, "centroid": (lat, lng)}
    return boroughs


def _post(path, data):
    url = f"{API_BASE}{path}"
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, data=data, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = exc
            print(f"    request error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 503:
            last_error = RuntimeError(
                f"API reports too much data for this area/month (HTTP 503): {resp.text[:200]}"
            )
            break
        last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        print(f"    unexpected status (attempt {attempt}/{MAX_RETRIES}): {last_error}")
        time.sleep(2 * attempt)

    raise last_error


def _get(path, params=None):
    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = exc
            print(f"    request error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 200:
            return resp.json()

        # data.police.uk returns 503 with a text body when a point/radius
        # query would return too many records for one response.
        if resp.status_code == 503:
            last_error = RuntimeError(
                "API reports too much data for this point/radius/month "
                f"(HTTP 503): {resp.text[:200]}"
            )
            break

        last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        print(f"    unexpected status (attempt {attempt}/{MAX_RETRIES}): {last_error}")
        time.sleep(2 * attempt)

    raise last_error


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def latest_available_months(n=MONTHS_TO_FETCH):
    """Ask the API which months it actually has data for and return the n
    most recent ones (format 'YYYY-MM', most-recent-first). Doing this
    instead of hardcoding dates means the monthly GitHub Actions run
    always tracks whatever the API currently publishes, without needing
    edits here."""
    dates = _get("/crimes-street-dates")
    if not dates:
        raise RuntimeError("crimes-street-dates returned no months")
    # API returns most-recent-first already, but sort defensively.
    months = sorted((d["date"] for d in dates), reverse=True)
    return months[:n]


def fetch_borough_month(slug, month, poly, lat, lng):
    if poly:
        print(f"  fetching {slug} / {month} (real polygon boundary) ...")
        records = _post("/crimes-street/all-crime", {"poly": poly, "date": month})
        source = "crimes-street/all-crime (real polygon boundary)"
    else:
        print(f"  fetching {slug} / {month} (fallback: point + ~1mi radius circle) ...")
        records = _get("/crimes-street/all-crime", {"lat": lat, "lng": lng, "date": month})
        source = "crimes-street/all-crime (point+radius fallback)"
    print(f"    got {len(records)} records")
    return records, source


def write_borough_file(slug, month, records):
    os.makedirs(RAW_DIR, exist_ok=True)
    out_path = os.path.join(RAW_DIR, f"{slug}_{month}.json")
    with open(out_path, "w") as f:
        json.dump(records, f)
    return out_path


def main():
    months_env = os.environ.get("FETCH_MONTHS", "").strip()
    if months_env:
        months = [m.strip() for m in months_env.split(",") if m.strip()]
    else:
        try:
            months = latest_available_months(MONTHS_TO_FETCH)
        except Exception as exc:
            print(f"FATAL: could not determine latest available months: {exc}")
            sys.exit(1)

    boroughs = load_boroughs()
    if not boroughs:
        print("FATAL: no boroughs discovered from london_boundaries.json")
        sys.exit(1)

    print(f"Fetching months: {months}")
    print(f"Boroughs discovered from boundary file: {len(boroughs)}")
    for slug, info in boroughs.items():
        print(f"  {slug}: using real polygon boundary ({info['poly'].count(':') + 1} points)")

    manifest = load_manifest()
    any_written = False
    any_errors = False

    for month in months:
        for slug, info in boroughs.items():
            already = manifest.get(slug, {}).get(month)
            if already:
                print(f"  {slug} / {month} already fetched on {already}, skipping")
                continue
            try:
                lat, lng = info["centroid"]
                records, source = fetch_borough_month(slug, month, info["poly"], lat, lng)
            except Exception as exc:
                print(f"  ERROR fetching {slug} / {month}: {exc}")
                any_errors = True
                continue

            out_path = write_borough_file(slug, month, records)
            manifest.setdefault(slug, {})[month] = {
                "fetched_records": len(records),
                "source": source,
                "file": os.path.relpath(out_path, os.path.dirname(RAW_DIR)),
            }
            any_written = True
            time.sleep(REQUEST_DELAY_SECONDS)

    save_manifest(manifest)

    if not any_written and any_errors:
        print("No new data written and errors occurred — failing the run.")
        sys.exit(1)

    print("Done." if any_written else "Nothing new to fetch — all months already present.")


if __name__ == "__main__":
    main()
