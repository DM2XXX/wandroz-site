"""
Wandroz — Dublin zone builder

Merges Dublin City's real official 11 Local Electoral Areas (LEAs) —
the government-defined electoral geography used for Dublin City Council
elections (most recently 2024) — with genuine Level 2 press research.

Ireland has no current, live, geolocated neighbourhood-level crime
dataset usable for this project: the only near-candidate, the AIRO/
data.gov.ie "Crimes at Garda Stations Level 2010-15" dataset, was
directly checked and confirmed dead — it covers 2003-2015 only, the
underlying project is described in its own documentation as "effectively
completed," and no current download or live update exists. So Dublin
follows the same Level 2 approach already used for Rome, Milan, Turin,
Barcelona, Madrid, Vienna, Lisbon, Paris, Athens and Venice: real,
current, dated local/national press research per LEA, honestly disclosed
as press-based rather than official crime statistics.

The 11 LEAs are Dublin City Council's official electoral geography — a
finer, more current unit than the coarser 5 "administrative areas" listed
on Dublin City Council's own website, and the correct match for this
project's established granularity preference (matching the choice of
Municipio in Rome, Municipi in Milan, arrondissement in Paris, etc).
All 11 are mapped here, none excluded, per the standing instruction.

Inputs (both reproducible, checked into pipeline/data_raw/):
  - dublin_lea.geojson: 11 LEA boundary polygons (GeoJSON
    FeatureCollection, WGS84/EPSG:4326). Geometry source: Ordnance
    Survey Ireland (OSi)'s official "Local Electoral Areas - National
    Statutory Boundaries - Ungeneralised - 2024" dataset, published via
    OSi's ArcGIS Hub / FeatureServer, queried directly (not via the Hub's
    own dataset-download API, which returned a
    "[BLOCKED: Cookie/query string data]" WAF-style block — worked around
    by resolving the item's real FeatureServer URL via the ArcGIS Online
    Sharing REST API instead, then querying that FeatureServer's own
    /query endpoint, filtered to Dublin City's 11 LEAs by name and
    simplified server-side with maxAllowableOffset=0.0003).
  - dublin_press_research.json: one entry per LEA (day/night tone + a
    full honest summary + sources), produced by genuine web research
    (see each entry's own "sources" field). Honest defaults throughout:
    no evidence found -> green ("no particular concern"), never an
    invented incident or rating.

Matching is done by stripping the "LEA-N" seat-count suffix from each
feature's ENG_NAME_VALUE (e.g. "BALLYFERMOT-DRIMNAGH LEA-5" ->
"Ballyfermot-Drimnagh") and comparing against the press-research file's
"name" field.

Geometry note: unlike Venice's Favaro Veneto, every one of Dublin's 11
LEAs resolves to a single, clean Polygon (no MultiPolygon/disjoint-parts
complication) — confirmed by direct inspection of the source GeoJSON.

Output: pipeline/data_zones/dublin.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city.
"""

import json
import os
import re

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "dublin_lea.geojson")
RESEARCH_PATH = os.path.join(RAW_DIR, "dublin_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "dublin.json")

# Booking.com search disambiguation — plain LEA names are not always
# recognisable tourist-facing place names, so point the query at the
# best-known neighbourhood/landmark within each LEA.
QUERY_OVERRIDES = {
    "Artane-Whitehall": "Artane, Dublin, Ireland",
    "Ballyfermot-Drimnagh": "Ballyfermot, Dublin, Ireland",
    "Ballymun-Finglas": "Ballymun, Dublin, Ireland",
    "Cabra-Glasnevin": "Glasnevin, Dublin, Ireland",
    "Clontarf": "Clontarf, Dublin, Ireland",
    "Donaghmede": "Raheny, Dublin, Ireland",
    "Kimmage-Rathmines": "Rathmines, Dublin, Ireland",
    "North Inner City": "O'Connell Street, Dublin, Ireland",
    "Pembroke": "Ballsbridge, Dublin, Ireland",
    "South East Inner City": "Temple Bar, Dublin, Ireland",
    "South West Inner City": "The Liberties, Dublin, Ireland",
}

DISPLAY_NAMES = {
    "Artane-Whitehall": "Artane-Whitehall (Artane, Whitehall, Beaumont, Killester)",
    "Ballyfermot-Drimnagh": "Ballyfermot-Drimnagh (Ballyfermot, Drimnagh, Cherry Orchard, Bluebell)",
    "Ballymun-Finglas": "Ballymun-Finglas (Ballymun, Finglas, Santry)",
    "Cabra-Glasnevin": "Cabra-Glasnevin (Cabra, Glasnevin, Phibsborough)",
    "Clontarf": "Clontarf (Clontarf, Marino, Fairview, Killester)",
    "Donaghmede": "Donaghmede (Donaghmede, Kilbarrack, Raheny, Bayside, Sutton/Howth)",
    "Kimmage-Rathmines": "Kimmage-Rathmines (Rathmines, Rathgar, Terenure, Harold's Cross, Kimmage)",
    "North Inner City": "North Inner City (O'Connell Street, Smithfield, Docklands)",
    "Pembroke": "Pembroke (Ballsbridge, Donnybrook, Ranelagh, Sandymount)",
    "South East Inner City": "South East Inner City (Temple Bar, Grafton Street, Trinity College, St Stephen's Green)",
    "South West Inner City": "South West Inner City (The Liberties, Kilmainham, Rialto, Dolphin's Barn)",
}

NAME_SUFFIX_RE = re.compile(r"\s+LEA-\d+$")


def _title_case_lea(raw_name):
    """'BALLYFERMOT-DRIMNAGH LEA-5' -> 'Ballyfermot-Drimnagh'"""
    stripped = NAME_SUFFIX_RE.sub("", raw_name).strip()
    parts = re.split(r"([-\s])", stripped)
    return "".join(p if p in ("-", " ") else p.capitalize() for p in parts)


def load_geometry():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        g = json.load(f)
    out = {}
    for feat in g["features"]:
        raw_name = feat["properties"]["ENG_NAME_VALUE"]
        name = _title_case_lea(raw_name)
        geom = feat["geometry"]
        assert geom["type"] == "Polygon", f"Unexpected geometry type for {name}: {geom['type']}"
        rings = geom["coordinates"]
        assert len(rings) == 1, f"{name} has holes ({len(rings)} rings) — not handled"
        ring = rings[0]
        # GeoJSON order is [lon, lat]; Wandroz's zone JSON (Leaflet-facing)
        # uses [lat, lon], matching every other city's data_zones file.
        coords = [[lat, lon] for lon, lat in ring]
        out[name] = coords
    return out


def main():
    geometry = load_geometry()
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_name = {r["name"]: r for r in research}

    missing = sorted(set(geometry) - set(research_by_name))
    if missing:
        raise SystemExit(f"Missing press research for: {missing}")
    extra = sorted(set(research_by_name) - set(geometry))
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    for name in sorted(geometry):
        r = research_by_name[name]
        coords = geometry[name]
        display_name = DISPLAY_NAMES[name]
        slug = name.lower().replace(" ", "-")

        sources_note = "; ".join(r.get("sources", []))
        text = r["text"]
        if sources_note:
            text = f"{text} Sources checked: {sources_note}."

        zones.append({
            "name": display_name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [coords],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Dublin, Ireland"),
        })

    assert len(zones) == 11, f"Expected 11 Local Electoral Areas, got {len(zones)}"

    data_note = (
        "Dublin: neighbourhood shapes are the real official Local Electoral Areas (LEAs) of Dublin City "
        "Council, the government-defined electoral geography used for Dublin City Council elections (most "
        "recently 2024) and the finest official government-published neighbourhood-equivalent unit for the "
        "whole city, all 11 mapped here, none excluded. Geometry is sourced from Ordnance Survey Ireland "
        "(OSi)'s official 'Local Electoral Areas - National Statutory Boundaries - Ungeneralised - 2024' "
        "dataset. Ireland has no current, live, geolocated neighbourhood-level crime dataset — the only "
        "near-candidate, a historical AIRO/data.gov.ie Garda-station crime dataset, was checked directly "
        "and confirmed to cover only 2003-2015 with the underlying project 'effectively completed' and no "
        "live update — so, like Rome, Milan, Turin and Venice, Dublin's safety levels are Wandroz's Level 2 "
        "approach: genuine current local/national press research per LEA, honestly disclosed as press-based "
        "rather than official crime statistics. Where no specific news coverage was found for part of an "
        "LEA, that is stated plainly rather than assumed either way. See the methodology page for details "
        "and sources."
    )

    out = {
        "label": "Dublin, Ireland",
        "center": [53.3498, -6.2603],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} LEAs)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
