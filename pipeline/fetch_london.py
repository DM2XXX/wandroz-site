"""
Wandroz — full monthly crime data fetch for London boroughs (v1)

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

  Queried by borough centroid (lat/lng), which the API implicitly expands
  to roughly a 1-mile-radius catchment around that point for the given
  month. This is NOT the exact administrative borough polygon — it is an
  approximation, same limitation the original prototype had, just now
  with the FULL response for that catchment instead of a truncated one.

  UPGRADE PATH (not done yet, tracked on the project dashboard): swap the
  point/radius query for the borough's real polygon boundary (e.g. via
  ONS/GLA boundary files or the Police "neighbourhood boundary" API
  aggregated by borough) so coverage matches administrative boundaries
  exactly instead of a circle. Left as a TODO because it needs boundary
  data verified against a live response, which this authoring session's
  sandbox could not reach (network restricted here — see README.md).

WHAT THIS SCRIPT DOES
  1. Asks the API which months of data are currently available
     (GET /api/crimes-street-dates) and picks the most recent one, unless
     FETCH_MONTHS is set explicitly.
  2. For each configured borough centroid, pulls the full crime list for
     that month.
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
import sys
import time
from urllib.parse import urlencode

import requests

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")

API_BASE = "https://data.police.uk/api"
USER_AGENT = "wandroz-site-fetch/0.1 (https://wandroz.com; automated monthly refresh)"
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite to a free public API
MAX_RETRIES = 3

# Borough centroids used as the query point. Approximate landmark/civic
# centres, not a formal geographic centroid calculation — good enough for
# a clearly-labelled sample catchment, not for claiming exact boundary
# coverage (see UPGRADE PATH above).
BOROUGH_CENTROIDS = {
    "westminster": (51.4975, -0.1357),
    "camden": (51.5290, -0.1255),
    "islington": (51.5416, -0.1022),
    "kensington_chelsea": (51.4991, -0.1938),
    "lambeth": (51.4607, -0.1163),
}


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


def fetch_borough_month(slug, lat, lng, month):
    print(f"  fetching {slug} / {month} ...")
    records = _get(
        "/crimes-street/all-crime", {"lat": lat, "lng": lng, "date": month}
    )
    print(f"    got {len(records)} records")
    return records


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
                records = fetch_borough_month(slug, lat, lng, month)
            except Exception as exc:
                print(f"  ERROR fetching {slug} / {month}: {exc}")
                any_errors = True
                continue

            out_path = write_borough_file(slug, month, records)
            manifest.setdefault(slug, {})[month] = {
                "fetched_records": len(records),
                "source": "crimes-street/all-crime (point+radius)",
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
