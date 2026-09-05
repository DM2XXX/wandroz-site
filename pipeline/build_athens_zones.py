"""
Wandroz — Athens zone builder

Merges Athens' real official 7 "Δημοτικές Κοινότητες" (Municipal
Districts — the "Kallikratis" 2011 reform holdover, previously called
δημοτικά διαμερίσματα) boundaries with genuine Level 2 press research.
Greece has no open, geolocated neighbourhood-level crime dataset (the
Hellenic Police publish only national/regional aggregate statistics), so
Athens follows the same Level 2 approach already used for Rome, Milan,
Turin, Barcelona, Madrid, Vienna, Lisbon and Paris: real current
local/national press research per district, honestly disclosed as
press-based rather than official crime statistics.

The 7 Municipal Districts are themselves the finest official government
neighbourhood-equivalent unit for the Municipality of Athens (they
subdivide into 48 unofficial συνοικίες and 129 γειτονιές, but only the 7
Municipal Districts have real, government-published boundaries) — so all
7 are mapped here, none excluded, per the standing instruction.

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - athens_communities.geojson: 7 Municipal District boundary polygons
    (GeoJSON FeatureCollection, already WGS84/EPSG:4326, MultiPolygon per
    feature though every feature in practice has exactly one polygon
    part), sourced from the City of Athens' own official GIS portal
    (gis.cityofathens.gr), a GeoNode instance, via its underlying
    GeoServer WFS endpoint (layer geonode:dimotikes_koinotites0,
    CC BY v3.0 Greece license, uploaded 2023-10-06 by the Δήμος Αθηναίων
    GIS department).
  - athens_press_research.json: one entry per district (day/night tone +
    a short honest summary + sources), produced by genuine web research
    (see each entry's own "sources" field for what was actually
    checked). Honest defaults throughout: no evidence found -> green
    ("no particular concern"), never an invented incident or rating.

Matching is done on the "no" field (1-7), which is stable across both
files and unambiguous (unlike the Greek "name"/"name_en" fields, which
are just ordinals like "1st").

Output: pipeline/data_zones/athens.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city.
"""

import json
import os

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "athens_communities.geojson")
RESEARCH_PATH = os.path.join(RAW_DIR, "athens_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "athens.json")

# Plain ordinal names ("1st Municipal District") are ambiguous on their
# own for a Booking.com search, so every district gets an explicit,
# disambiguating query built from its real constituent neighbourhoods.
QUERY_OVERRIDES = {
    1: "Syntagma, Athens, Greece",
    2: "Pangrati, Athens, Greece",
    3: "Thiseio, Athens, Greece",
    4: "Sepolia, Athens, Greece",
    5: "Patisia, Athens, Greece",
    6: "Kypseli, Athens, Greece",
    7: "Ampelokipoi, Athens, Greece",
}

DISPLAY_NAMES = {
    1: "1st Municipal District (Syntagma, Plaka, Monastiraki, Omonoia, Kolonaki, Exarchia)",
    2: "2nd Municipal District (Pangrati, Mets, Neos Kosmos)",
    3: "3rd Municipal District (Thiseio, Petralona, Votanikos)",
    4: "4th Municipal District (Kolonos, Sepolia, Akadimia Platonos)",
    5: "5th Municipal District (Patisia, Agios Eleftherios)",
    6: "6th Municipal District (Kypseli, Victoria Square, Agios Panteleimonas)",
    7: "7th Municipal District (Ampelokipoi, Goudi, Gyzi)",
}


def _ring_area(ring):
    """Shoelace formula, used only to compare polygon parts by size (not a
    real-world area unit — coordinates are still in degrees)."""
    total = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def load_geometry():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        g = json.load(f)
    out = {}
    for feat in g["features"]:
        no = feat["properties"]["no"]
        geom = feat["geometry"]
        assert geom["type"] == "MultiPolygon", f"Unexpected geometry type for district {no}: {geom['type']}"
        polys = geom["coordinates"]  # MultiPolygon: [polygon, ...], polygon = [ring, ...]
        if len(polys) > 1:
            areas = [_ring_area(p[0]) for p in polys]
            best = polys[areas.index(max(areas))]
            print(f"NOTE: district {no} had {len(polys)} polygon parts — kept only the largest")
        else:
            best = polys[0]
        ring = best[0]  # outer ring only — no district in this dataset has holes
        # GeoJSON order is [lon, lat]; Wandroz's zone JSON (Leaflet-facing)
        # uses [lat, lon], matching every other city's data_zones file.
        coords = [[lat, lon] for lon, lat in ring]
        out[no] = coords
    return out


def main():
    geometry = load_geometry()
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_no = {r["no"]: r for r in research}

    missing = sorted(set(geometry) - set(research_by_no))
    if missing:
        raise SystemExit(f"Missing press research for districts: {missing}")
    extra = sorted(set(research_by_no) - set(geometry))
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    for no in sorted(geometry):
        r = research_by_no[no]
        coords = geometry[no]
        name = DISPLAY_NAMES[no]
        slug = f"{no}-municipal-district"

        sources_note = "; ".join(r.get("sources", []))
        text = r["text"]
        if sources_note:
            text = f"{text} Sources checked: {sources_note}."

        zones.append({
            "name": name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [coords],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(no, f"{name}, Athens, Greece"),
        })

    assert len(zones) == 7, f"Expected 7 Municipal Districts, got {len(zones)}"

    data_note = (
        "Athens: neighbourhood shapes are the real official administrative boundaries of Athens' 7 "
        "Δημοτικές Κοινότητες "
        "(Municipal Districts, a holdover unit from the 2011 \"Kallikratis\" local-government reform), "
        "sourced directly from the City of Athens' own official GIS portal (gis.cityofathens.gr, "
        "CC BY v3.0 Greece license), via its underlying GeoServer WFS endpoint. Greece has no open, "
        "geolocated neighbourhood-level crime dataset (the Hellenic Police publish only national and "
        "regional aggregate statistics) — so, like Rome, Milan, Turin, Barcelona, Madrid, Vienna, Lisbon "
        "and Paris, Athens' safety levels are Wandroz's Level 2 approach: genuine current local/national "
        "press research per district, honestly disclosed as press-based rather than official crime "
        "statistics. Where no specific news coverage was found for part of a district, that is stated "
        "plainly rather than assumed either way. All 7 official Municipal Districts are mapped here, "
        "none excluded. See the methodology page for details and sources."
    )

    out = {
        "label": "Athens, Greece",
        "center": [37.9838, 23.7275],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} municipal districts)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
