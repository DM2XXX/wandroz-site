"""
Wandroz — full monthly crime data fetch for London boroughs (v2: real
polygon boundary, not a circle)

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
  attributed to the wrong neighbour. v2 (this version) instead POSTs the
  borough's real polygon boundary via the API's "poly" parameter (the same
  ONS 2021 boundary coordinates the interactive map already draws, loaded
  from pipeline/data_zones/london_boundaries.json), so the crime count now
  matches the exact shape shown on the map. POST is used rather than GET
  because several of these boundaries — Lambeth's ring alone has 135
  points — produce a query string longer than the API's 4094-character GET
  limit; the docs explicitly say to use POST for complex polygons.

  If a borough's boundary can't be found in london_boundaries.json for any
  reason, this script falls back to the old point/1-mile-radius circle for
  that borough only, and records which method was actually used in
  manifest.json so score_london.py / the site can be honest about it.

WHAT THIS SCRIPT DOES
  1. Asks the API which months of data are currently available
     (GET /api/crimes-street-dates) and picks the most recent one, unless
     FETCH_MONTHS is set explicitly.
  2. For each configured borough, POSTs its real polygon boundary (falling
     back to point+radius if the boundary is missing) and pulls the full
     crime list for that month.
  3. Writes data/raw/{slug}_{YYYY-MM}.json — same shape score_london.py
     already expects (a plain JSON list of raw crime records).
  4. Updates data/raw/manifest.json so re-runs don't need to re-fetch a
     month that's already saved, and so the GitHub Actions "commit only if
     changed" step has something meaningful to diff.

USAGE
  python pipeline/fetch_london.py                # fetch latest available month
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
USER_AGENT = "wandroz-site-fetch/0.2 (https://wandroz.com; automated monthly refresh)"
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite to a free public API
MAX_RETRIES = 3

# Borough centroids — used ONLY as a fallback if a borough's real polygon
# boundary can't be loaded from london_boundaries.json (see _load_boundary_polys
# below). Approximate landmark/civic centres, not a formal centroid
# calculation — fine for a clearly-labelled fallback circle, not for
# claiming exact boundary coverage.
BOROUGH_CENTROIDS = {
    "westminster": (51.4975, -0.1357),
    "camden": (51.5290, -0.1255),
    "islington": (51.5416, -0.1022),
    "kensington_chelsea": (51.4991, -0.1938),
    "lambeth": (51.4607, -0.1163),
}


def _canon(name):
    """Same normalisation build_site.py uses, so 'Kensington & Chelsea' in
    the boundary file matches 'kensington_chelsea' in BOROUGH_CENTROIDS."""
    name = name.lower().replace("&", " and ")
    tokens = [t for t in re.split(r"[\s\-_]+", name) if t and t != "and"]
    return "".join(tokens)


def _load_boundary_polys():
    """slug -> 'lat,lng:lat,lng:...' poly string, for every borough in
    BOROUGH_CENTROIDS that has a matching real boundary. Coordinates are
    rounded to 6 decimal places (~11cm precision, far finer than needed)
    to keep the POST body a reasonable size."""
    if not os.path.exists(BOUNDARIES_PATH):
        return {}
    with open(BOUNDARIES_PATH) as f:
        data = json.load(f)
    by_canon = {_canon(z["name"]): z for z in data.get("zones", [])}

    polys = {}
    for slug in BOROUGH_CENTROIDS:
        z = by_canon.get(_canon(slug))
        if not z or not z.get("coords"):
            continue
        ring = max(z["coords"], key=len)  # largest ring if more than one
        polys[slug] = ":".join(f"{lat:.6f},{lng:.6f}" for lat, lng in ring)
    return polys


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


def latest_available_month():
    """Ask the API which months it actually has data for and return the
    single most recent one (format 'YYYY-MM'). Doing this instead of
    hardcoding a date means the monthly GitHub Actions run always tracks
    whatever the API currently publishes, without needing edits here."""
    dates = _get("/crimes-street-dates")
    if not dates:
        raise RuntimeError("crimes-street-dates returned no months")
    # API returns most-recent-first already, but sort defensively.
    months = sorted((d["date"] for d in dates), reverse=True)
    return months[0]


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
            months = [latest_available_month()]
        except Exception as exc:
            print(f"FATAL: could not determine latest available month: {exc}")
            sys.exit(1)

    print(f"Fetching months: {months}")
    boundary_polys = _load_boundary_polys()
    for slug in BOROUGH_CENTROIDS:
        if slug in boundary_polys:
            print(f"  {slug}: using real polygon boundary ({boundary_polys[slug].count(':') + 1} points)")
        else:
            print(f"  {slug}: WARNING — no boundary found, falling back to point+radius circle")

    manifest = load_manifest()
    any_written = False
    any_errors = False

    for month in months:
        for slug, (lat, lng) in BOROUGH_CENTROIDS.items():
            already = manifest.get(slug, {}).get(month)
            if already:
                print(f"  {slug} / {month} already fetched on {already}, skipping")
                continue
            try:
                records, source = fetch_borough_month(slug, month, boundary_polys.get(slug), lat, lng)
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
