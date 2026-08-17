"""
Wandroz — real crime-rate scoring for Berlin (Bezirksregion-level)

WHAT THIS IS
  Turns fetch_berlin.py's two raw incident-count files (bicycle theft,
  vehicle break-in/theft — both real, near-daily-updated official data,
  see that script's docstring) into per-Bezirksregion rates and a tone
  (red/yellow/green) relative to the citywide average, the same relative-
  average logic score_london.py and score_zurich.py use.

NORMALIZATION: AREA, NOT POPULATION — AND WHY
  London and Zurich normalize by population (workday population and plain
  resident population respectively) because a reliable, current, official
  population figure was available at the right geography for both. For
  Berlin's Bezirksregionen, no current small-area population dataset was
  confirmed during this research (16 August 2026) — rather than guess or
  reuse an old figure, this script normalizes by each Bezirksregion's
  AREA instead (incidents per square kilometre), computed directly from
  the same official boundary polygons used to draw the map. This is a
  real, defensible measure on its own (bicycle and vehicle theft are
  substantially about opportunity/footfall density, which area-normalized
  rates capture reasonably), but it is NOT the same thing as a per-capita
  crime rate, and is disclosed as such everywhere this data is shown. If a
  reliable current population-by-Bezirksregion source is confirmed later,
  this script should switch to it.

DEPENDS ON A BOUNDARY FILE THIS REPO DOES NOT YET HAVE
  This script reads pipeline/data_zones/berlin_boundaries.json — the same
  shape as london_boundaries.json (per-zone name, LOR code, polygon
  coords) plus a computed area_km2 per zone — which is meant to be
  produced by fetch_berlin_boundaries.py from Berlin's official LOR WFS
  (gdi.berlin.de/services/wfs/lor_2021). That WFS was returning a
  server-side maintenance page for every request (including plain
  GetCapabilities) during this research — a genuine, presumably temporary
  outage on Berlin's end, not a sandbox/tooling restriction — so that
  boundary file does not exist yet and this script has NOT been run
  against real Berlin data. Like every other script in this pipeline that
  degrades gracefully when its input isn't there yet (score_zurich.py is
  the closest precedent), this one writes an empty result rather than
  fabricating boundaries, an area, or a rate.

  UPDATE (17 Aug 2026) — checked again, still blocked, now via 4
  independent paths, and one promising-looking shortcut turned out to be a
  trap worth documenting so it isn't retried blind:
    1. gdi.berlin.de/services/wfs/lor_2021 — still "Wartungsarbeiten" on
       every request, including GetCapabilities.
    2. daten.odis-berlin.de's "WFS-Explorer" for LOR-Bezirksregionen (ab
       2021) — greyed out/inactive in its own UI; its links resolve to
       wfsexplorer.odis-berlin.de, which itself proxies gdi.berlin.de — so
       it's the same outage wearing a nicer UI, not an alternate source.
    3. github.com/rbb-data/berlin-lor — DOES have a real, fetchable
       138-Bezirksregion polygon file (berlin-lor.bezirksregionen.geojson,
       via Git LFS — fetch through
       https://media.githubusercontent.com/media/rbb-data/berlin-lor/master/berlin-lor.bezirksregionen.geojson,
       not raw.githubusercontent.com, which only returns the LFS pointer
       stub). THE TRAP: its SCHLUESSEL codes use the PRE-2021 LOR scheme.
       The live 2026 police CSVs (fetch_berlin.py) use the CURRENT
       (post-2021) scheme. Tried joining directly on the 6-digit code on
       17 Aug 2026: zero overlap between the two code sets — not a few
       missing zones, a completely different numbering. A polygon file
       built from this source was generated, scored (produced 138 zones
       all reading exactly 0 incidents — the tell that the join silently
       failed rather than raising an error) and then DELETED along with
       the bogus score output once the mismatch was caught — see git
       history / pipeline/data_zones/_unreconciled/ for the labelled
       leftover if it's still there. Do not resurrect this file and join
       it directly again without first solving the code mismatch (below).
    4. daten.berlin.de's own dataset page for "Lebensweltlich orientierte
       Räume (LOR) in Berlin" lists direct-download resources (SHP, KMZ,
       DXF, and a "LOR-Schluesselsystematik.xls" key/name crosswalk) that
       looked independent of the broken WFS — but every one of those
       resource links points at
       www.stadtentwicklung.berlin.de/planen/basisdaten_stadtentwicklung/lor/download/...,
       which now returns HTTP 410 Gone (the old stadtentwicklung.berlin.de
       site structure has been retired). Also checked govdata.de: it has
       LOR-level population datasets, not the polygon geometry itself.

  NEXT PERSON/SESSION: two realistic ways forward once gdi.berlin.de comes
  back (no ETA observed) —
    (a) fetch_berlin_boundaries.py against the real WFS once it's back —
        the clean path, gets current-scheme geometry directly, no join
        needed.
    (b) if only an old-scheme geometry source is available again, get
        LOR-Schluesselsystematik.xls (or an equivalent official
        code<->name crosswalk covering BOTH the pre- and post-2021
        schemes — it did not appear to still be hosted anywhere reachable
        as of 17 Aug 2026 either) and join old-scheme geometry to
        new-scheme crime data BY NAME instead of by code, verifying a
        sane 1:1 (or documented split/merge) match before trusting it —
        do not assume a naive name-string match is automatically correct,
        Berlin Bezirksregion names can repeat or nearly-match across
        different Bezirke.
  Either way: do not ship a joined result without confirming a nonzero,
  plausible incident count lands in most zones first (score_berlin.py's
  city_average_rate_per_km2 being exactly 0.0 across every zone, as
  happened on 17 Aug, is the giveaway that the join silently failed).

USAGE
  python pipeline/score_berlin.py
"""

import json
import os

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw_berlin")
OUT_DIR = os.path.join(BASE_DIR, "..", "data", "scores")
OUT_PATH = os.path.join(OUT_DIR, "berlin_property_crime.json")
BOUNDARIES_PATH = os.path.join(BASE_DIR, "data_zones", "berlin_boundaries.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8


def load_counts(fname):
    path = os.path.join(RAW_DIR, fname)
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def load_boundaries():
    """Expected shape: {"zones": [{"lor_code": "111002", "name": "...",
    "coords": [[lat,lng], ...], "area_km2": 1.23}, ...]}. Returns [] if the
    file doesn't exist yet (see module docstring)."""
    if not os.path.isfile(BOUNDARIES_PATH):
        return []
    with open(BOUNDARIES_PATH) as f:
        data = json.load(f)
    return data.get("zones", [])


def write_empty(reason):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump({"zones": {}, "city_average_rate_per_km2": None, "zones_covered": 0}, f, indent=2)
    print(reason)


def main():
    zones = load_boundaries()
    if not zones:
        write_empty(
            "No Berlin boundary data yet (pipeline/data_zones/berlin_boundaries.json missing) — nothing to "
            "score. Expected until Berlin's LOR WFS maintenance outage clears and fetch_berlin_boundaries.py "
            "can run; wrote an empty result so build_site.py degrades gracefully."
        )
        return

    bike_counts = load_counts("bike_theft_by_bezirksregion.json")
    vehicle_counts = load_counts("vehicle_crime_by_bezirksregion.json")
    if not bike_counts and not vehicle_counts:
        write_empty("No Berlin crime-count data on disk yet — run fetch_berlin.py first. Wrote an empty result.")
        return

    scored = {}
    for z in zones:
        code = z.get("lor_code")
        area = z.get("area_km2")
        if not code or not area:
            continue
        bikes = bike_counts.get(code, 0)
        vehicles = vehicle_counts.get(code, 0)
        bike_rate = round(bikes / area, 2)
        vehicle_rate = round(vehicles / area, 2)
        combined_rate = round((bikes + vehicles) / area, 2)
        scored[code] = {
            "lor_code": code,
            "name": z.get("name"),
            "area_km2": area,
            "bike_theft_count": bikes,
            "vehicle_crime_count": vehicles,
            "bike_theft_rate_per_km2": bike_rate,
            "vehicle_crime_rate_per_km2": vehicle_rate,
            "combined_rate_per_km2": combined_rate,
        }

    if not scored:
        write_empty("Boundary file had no zones with both a lor_code and area_km2 — wrote an empty result.")
        return

    city_avg = sum(v["combined_rate_per_km2"] for v in scored.values()) / len(scored)
    for v in scored.values():
        ratio = (v["combined_rate_per_km2"] / city_avg) if city_avg else 1.0
        v["vs_city_average"] = round(ratio, 3)
        if ratio >= RED_THRESHOLD:
            v["tone"] = "red"
        elif ratio <= GREEN_THRESHOLD:
            v["tone"] = "green"
        else:
            v["tone"] = "yellow"

    out = {
        "zones": scored,
        "city_average_rate_per_km2": round(city_avg, 2),
        "zones_covered": len(scored),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(f"Wrote {OUT_PATH} — {len(scored)} Bezirksregionen scored, city average {out['city_average_rate_per_km2']} incidents/km2")


if __name__ == "__main__":
    main()
