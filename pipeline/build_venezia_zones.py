"""
Wandroz — Venice (Venezia) zone builder

Merges Venice's real official 6 "Municipalità" (the decentralized
administrative subdivisions of the Comune di Venezia, established 2005,
replacing the previous 13 quartieri) with genuine Level 2 press research.
Italy has no open, geolocated neighbourhood-level crime dataset (already
established for Rome, Milan, Turin), so Venice follows the same Level 2
approach: real current local/national press research per Municipalità,
honestly disclosed as press-based rather than official crime statistics.

The 6 Municipalità are the finest official government-published
administrative unit for the whole Comune di Venezia (mainland Mestre/
Marghera/Favaro/Chirignago-Zelarino included, not just the historic
lagoon islands) — so all 6 are mapped here, none excluded, per the
standing instruction. (Venice's historic "sestieri" — San Marco,
Cannaregio, Castello, Dorsoduro, San Polo, Santa Croce — are older,
still-used informal subdivisions with their own real official boundary
layer, but they only cover part of one Municipalità (Venezia-Murano-
Burano) and don't cover the mainland at all, so they are not the unit
used here.)

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - venezia_municipalita.geojson: 6 Municipalità boundary polygons
    (GeoJSON FeatureCollection, WGS84/EPSG:4326). Geometry source: the
    OpenStreetMap administrative boundary relations for Venice's 6
    Municipalità (admin_level=10), fetched via the Overpass API and
    converted to clean polygons via polygons.openstreetmap.fr. This was
    used after an extensive but unsuccessful search for a directly
    downloadable official municipal/regional GIS boundary layer for the
    Municipalità specifically (Comune di Venezia's own ArcGIS/Geocortex
    GIS portal only publishes the historic-center "Sestiere"/"Insulario"
    civic-addressing layer, not a Municipalità layer, and its "Limiti
    Amministrativi" layer sits on an internal-only server not reachable
    from outside the portal's own viewer). OSM's boundaries for Venice
    were themselves originally imported from the Comune's own official
    open data during community mapping parties (~2013-2015), so this is
    a faithful, verifiable proxy for the official geometry rather than a
    crowd-sourced guess — disclosed honestly here and in methodology.html.
  - venezia_press_research.json: one entry per Municipalità (day/night
    tone + a full honest summary + sources), produced by genuine web
    research (see each entry's own "sources" field). Honest defaults
    throughout: no evidence found -> green ("no particular concern"),
    never an invented incident or rating.

Matching is done on the "name" field, which is identical and stable
across both files (the official Municipalità name, e.g.
"Venezia-Murano-Burano").

Geometry note — Favaro Veneto: its OSM relation resolves to 2 disjoint
polygon parts (not a duplicate/fragment artifact — the two parts'
bounding boxes don't overlap at all, confirmed by direct inspection).
The smaller part (~5% of the total area) is a real but small outlying
piece of Favaro Veneto's official territory. Since every other part of
this codebase (Leaflet's L.polygon, build_site.py's _extend_bbox(), and
templates/index.html's pointInRing address-search function) assumes a
single-polygon 2D structure (coords = [ring]), the largest part is kept
and the smaller outlying part is not separately rendered — the same
kind of disclosed geometric simplification already used for Brussels'
Saint-Gilles/Ixelles and Munich's Stadtbezirke, though here the dropped
part is a genuine small disjoint area rather than a duplicate fragment.
Favaro Veneto itself is still fully mapped and rated; only a small
sliver of its official shape is not drawn.

Output: pipeline/data_zones/venezia.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city.
"""

import json
import os

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "venezia_municipalita.geojson")
RESEARCH_PATH = os.path.join(RAW_DIR, "venezia_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "venezia.json")

# Plain Municipalità names are already real, well-known place names in
# Venice (unlike Athens' ordinal districts), but some benefit from a
# disambiguating query for Booking.com since "Marghera"/"Favaro Veneto"
# alone could be ambiguous outside Venice context.
QUERY_OVERRIDES = {
    "Venezia-Murano-Burano": "Venice, Italy",
    "Lido-Pellestrina": "Lido di Venezia, Venice, Italy",
    "Marghera": "Marghera, Venice, Italy",
    "Mestre-Carpenedo": "Mestre, Venice, Italy",
    "Chirignago-Zelarino": "Chirignago, Venice, Italy",
    "Favaro Veneto": "Favaro Veneto, Venice, Italy",
}

DISPLAY_NAMES = {
    "Venezia-Murano-Burano": "Venezia-Murano-Burano (historic Venice, Giudecca, Murano, Burano)",
    "Lido-Pellestrina": "Lido-Pellestrina (Venice Lido, Pellestrina)",
    "Marghera": "Marghera (mainland industrial port district)",
    "Mestre-Carpenedo": "Mestre-Carpenedo (mainland urban centre, train station)",
    "Chirignago-Zelarino": "Chirignago-Zelarino (mainland residential district)",
    "Favaro Veneto": "Favaro Veneto (mainland district near Marco Polo Airport)",
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
        name = feat["properties"]["name"]
        geom = feat["geometry"]
        assert geom["type"] == "MultiPolygon", f"Unexpected geometry type for {name}: {geom['type']}"
        polys = geom["coordinates"]  # MultiPolygon: [polygon, ...], polygon = [ring, ...]
        if len(polys) > 1:
            areas = [_ring_area(p[0]) for p in polys]
            best = polys[areas.index(max(areas))]
            print(f"NOTE: {name} had {len(polys)} polygon parts — kept only the largest ({max(areas):.6f} vs {sorted(areas)[:-1]})")
        else:
            best = polys[0]
        ring = best[0]  # outer ring only — no Municipalità in this dataset has holes
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
        slug = name.lower().replace("à", "a").replace(" ", "-")

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
            "query": QUERY_OVERRIDES.get(name, f"{name}, Venice, Italy"),
        })

    assert len(zones) == 6, f"Expected 6 Municipalità, got {len(zones)}"

    data_note = (
        "Venice: neighbourhood shapes are the real official administrative boundaries of the Comune di "
        "Venezia's 6 Municipalità (established 2005), the finest official government-published "
        "neighbourhood-equivalent unit for the whole city, mainland districts (Mestre, Marghera, Favaro "
        "Veneto, Chirignago-Zelarino) included, not just the historic lagoon islands. Geometry is sourced "
        "from OpenStreetMap's administrative boundary relations for these 6 Municipalità, which were "
        "themselves originally imported from the Comune di Venezia's own official open data during "
        "community mapping efforts — used after Comune di Venezia's own GIS portal was found to publish "
        "only a historic-center civic-addressing layer (sestieri), not a Municipalità boundary layer, at "
        "a reachable endpoint. Italy has no open, geolocated neighbourhood-level crime dataset (as already "
        "established for Rome, Milan and Turin) — so, like those cities, Venice's safety levels are "
        "Wandroz's Level 2 approach: genuine current local/national press research per Municipalità, "
        "honestly disclosed as press-based rather than official crime statistics. Where no specific news "
        "coverage was found for part of a district, that is stated plainly rather than assumed either way. "
        "All 6 official Municipalità are mapped here, none excluded. See the methodology page for details "
        "and sources."
    )

    out = {
        "label": "Venice, Italy",
        "center": [45.4408, 12.3155],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} Municipalità)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
