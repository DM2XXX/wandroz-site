"""
Wandroz — Edinburgh zone builder

Edinburgh's 17 official City of Edinburgh Council wards, boundaries sourced
directly from the Council's own ArcGIS MapServer (edinburghcouncilmaps.info,
layer "Edinburgh Wards", Open Government Licence v3.0 — reached via the
Council's Open Spatial Data Portal item dc96624b1db849db926f59806e287d44).
These 17 wards are the natural, complete, non-overlapping neighbourhood unit
for the city (Scotland has no finer officially-bounded sub-ward layer that
is also a recognisable neighbourhood name) — none excluded, per the standing
instruction.

Unlike most other Level 2 (press-research) cities in this project, Edinburgh
has a genuine, real, per-ward NUMERIC crime dataset available, cross-checked
across two independent sources both ultimately sourced from official Police
Scotland / Scottish Government data:
  1. Churchill Support Services' analysis of Scottish Government crime
     statistics for 2023/24, reported by the Scottish Daily Express
     (28 Nov 2024) — exact crimes-per-1,000-population figure for all 17
     wards.
  2. datamap-scotland.co.uk's independent analysis of Police Scotland's own
     published crime data through end of 2025, which ranks all wards into
     five crime-rate bands and explicitly names the wards in the highest and
     lowest bands.

Both sources agree on the same wards at the top (Almond, City Centre, Leith,
Sighthill/Gorgie) and bottom (Colinton/Fairmilehead, Morningside) of the
crime-rate distribution, so the tone banding here is not a subjective
press-research judgement call the way it is for most Level 2 cities — it is
directly anchored to real official crime-rate-per-1000-population numbers,
independently corroborated. Day and night use the same tone throughout,
since neither official source publishes a time-of-day breakdown (disclosed
plainly in each zone's text, exactly as done for London's category-mix proxy
elsewhere in this project) — the one qualitative refinement applied is
genuine, dated local press coverage (Edinburgh News/The Scotsman) of
recurring nightlife-related disturbances specifically in the Cowgate/
Grassmarket area of City Centre ward, folded into that ward's text.

Inputs (checked into pipeline/data_raw/):
  - edinburgh_boundaries_raw.json: 17 ward boundary polygons (GeoJSON
    FeatureCollection, Polygon or MultiPolygon per feature), sourced as
    above. Almond is the only MultiPolygon (a mainland part plus two tiny
    exclaves); the largest part by vertex count is used as the
    representative shape, consistent with how other cities in this project
    (Brussels, Venice) have handled small disjoint boundary fragments.
  - edinburgh_press_research.json: one entry per ward (day/night tone + a
    short honest summary + sources), anchored to the two real numeric crime
    datasets described above plus targeted genuine press research. Honest
    defaults throughout: no evidence found beyond the numeric rate -> tone
    follows the rate band, described plainly as "no specific incidents
    found," never an invented incident.

Output: pipeline/data_zones/edinburgh.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "edinburgh_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "edinburgh_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "edinburgh.json")

QUERY_OVERRIDES = {
    "Colinton / Fairmilehead": "Colinton, Edinburgh, UK",
    "Corstorphine / Murrayfield": "Corstorphine, Edinburgh, UK",
    "Craigentinny / Duddingston": "Craigentinny, Edinburgh, UK",
    "Drum Brae / Gyle": "Drum Brae, Edinburgh, UK",
    "Fountainbridge / Craiglockhart": "Fountainbridge, Edinburgh, UK",
    "Liberton / Gilmerton": "Liberton, Edinburgh, UK",
    "Portobello / Craigmillar": "Portobello, Edinburgh, UK",
    "Sighthill / Gorgie": "Gorgie, Edinburgh, UK",
    "Southside / Newington": "Newington, Edinburgh, UK",
}


def slugify(name):
    name = name.lower()
    name = name.replace("/", "-")
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def largest_ring(geom):
    """Return the outer ring (list of [lon, lat]) of the largest part of a
    Polygon or MultiPolygon, by vertex count (a simple, adequate proxy for
    area on boundaries of this shape)."""
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    assert geom["type"] == "MultiPolygon", f"Unexpected geometry type: {geom['type']}"
    parts = geom["coordinates"]
    outer_rings = [p[0] for p in parts]
    return max(outer_rings, key=len)


def main():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        boundaries_geo = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_name = {r["nom"]: r for r in research}

    boundaries = []
    for feat in boundaries_geo["features"]:
        name = feat["properties"]["Ward_Name"].strip()
        ward_no = int(feat["properties"]["Ward_No"])
        ring = largest_ring(feat["geometry"])
        coords = [[lat, lon] for lon, lat in ring]
        boundaries.append({"nom": name, "no": ward_no, "coords": coords})

    boundaries.sort(key=lambda b: b["no"])

    missing = [b["nom"] for b in boundaries if b["nom"] not in research_by_name]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} wards: {missing}")
    extra = [name for name in research_by_name if name not in {b["nom"] for b in boundaries}]
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    seen_slugs = set()
    for b in boundaries:
        name = b["nom"]
        r = research_by_name[name]
        slug = slugify(name)
        if slug in seen_slugs:
            raise SystemExit(f"Duplicate slug generated: {slug} (from {name})")
        seen_slugs.add(slug)

        sources_note = "; ".join(r.get("sources", []))
        text = r["text"]
        if sources_note:
            text = f"{text} Sources checked: {sources_note}."

        zones.append({
            "name": f"{name} (Ward {b['no']})",
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Edinburgh, UK"),
        })

    assert len(zones) == 17, f"Expected 17 wards, got {len(zones)}"

    data_note = (
        "Edinburgh: ward shapes are the real official administrative boundaries of the City of "
        "Edinburgh Council's 17 wards, sourced directly from the Council's own ArcGIS map service "
        "(edinburghcouncilmaps.info, Open Government Licence v3.0). Unlike most other press-research "
        "cities in this project, Edinburgh's safety levels here are anchored to genuine, real, numeric "
        "crimes-per-1,000-population figures per ward for 2023/24 (Churchill Support Services' analysis "
        "of Scottish Government data, published via the Scottish Daily Express), independently "
        "corroborated by a second analysis of Police Scotland's own published crime data through end of "
        "2025 (datamap-scotland.co.uk) — both agree on the same highest- and lowest-crime wards. Neither "
        "official source splits crime by time of day, so day and night ratings are the same for every "
        "ward unless specific, dated local press coverage documented a night-specific pattern (as for "
        "City Centre's Cowgate/Grassmarket nightlife area). Where no such specific incident was found, "
        "that is stated plainly rather than assumed either way. See the methodology page for details and "
        "sources."
    )

    out = {
        "label": "Edinburgh, United Kingdom",
        "center": [55.9533, -3.1883],
        "zoom": 11,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} wards)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
