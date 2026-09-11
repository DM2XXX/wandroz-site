"""
Wandroz — Naples (Napoli) zone builder

Naples' 10 official "Municipalità" (established by municipal council
resolution in Feb-Mar 2005, each grouping several traditional quartieri,
replacing a previous 21-district system) — the finest official
government-defined neighbourhood-equivalent unit for the whole city. All 10
are mapped, none excluded, per the standing instruction.

Boundary provenance: the Comune di Napoli's own GIS/open-data portal
(sit.comune.napoli.it) has a broken server-side SSL certificate chain
(CERTIFICATE_VERIFY_FAILED, confirmed independently via two separate fetch
mechanisms) and could not be reached by any means available in this build
environment. Boundaries were instead sourced from OpenStreetMap's own
tagged administrative-boundary relations for each Municipalità
(admin_level=10, boundary=administrative), confirmed via Nominatim/Overpass
to be genuine, officially-modelled geometry (cross-referenced with
Wikidata/Wikipedia IDs) rather than an approximation — the same underlying
real administrative division, reached through a working channel instead of
the Comune's own broken one.

Unlike Edinburgh (which has genuine numeric crimes-per-1,000 data), Naples
has no official open geolocated crime dataset at Municipalità level, so
this follows Wandroz's standard "Level 2" approach used for Milan, Rome,
Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens, Venice and Dublin:
genuine, current, dated local/national press research per Municipalità,
honestly disclosed as press-based rather than official crime statistics.
Where no specific news coverage was found, that is stated plainly rather
than an incident being invented.

Inputs (checked into pipeline/data_raw/):
  - napoli_boundaries_raw.json: GeoJSON FeatureCollection, one feature per
    Municipalità, properties {name: "Municipalità N", no: N}, geometry
    Polygon or MultiPolygon, built from the OpenStreetMap relations above.
  - napoli_press_research.json: one entry per Municipalità (nom matching
    "Municipalità N", quartieri list, day/night tone, text, sources).

Output: pipeline/data_zones/napoli.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "napoli_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "napoli_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "napoli.json")

# Quartiere-based query overrides so Booking.com search lands on a
# recognisable place name rather than the bureaucratic "Municipalità N".
QUERY_OVERRIDES = {
    1: "Chiaia, Napoli, Italy",
    2: "Quartieri Spagnoli, Napoli, Italy",
    3: "Sanita, Napoli, Italy",
    4: "Piazza Garibaldi, Napoli, Italy",
    5: "Vomero, Napoli, Italy",
    6: "Ponticelli, Napoli, Italy",
    7: "Secondigliano, Napoli, Italy",
    8: "Scampia, Napoli, Italy",
    9: "Pianura, Napoli, Italy",
    10: "Fuorigrotta, Napoli, Italy",
}


def slugify(name):
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def largest_ring(geom):
    """Return the outer ring (list of [lon, lat]) of the largest part of a
    Polygon or MultiPolygon, by vertex count — consistent with how Edinburgh
    (Almond ward) and other cities in this project handle small disjoint
    boundary fragments."""
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
        name = feat["properties"]["name"].strip()
        no = int(feat["properties"]["no"])
        ring = largest_ring(feat["geometry"])
        coords = [[lat, lon] for lon, lat in ring]
        boundaries.append({"nom": name, "no": no, "coords": coords})

    boundaries.sort(key=lambda b: b["no"])

    missing = [b["nom"] for b in boundaries if b["nom"] not in research_by_name]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} municipalità: {missing}")
    extra = [name for name in research_by_name if name not in {b["nom"] for b in boundaries}]
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    seen_slugs = set()
    for b in boundaries:
        name = b["nom"]
        r = research_by_name[name]
        quartieri = r["quartieri"]
        display_name = f"{quartieri} (Municipalità {b['no']})"
        slug = slugify(f"municipalita-{b['no']}")
        if slug in seen_slugs:
            raise SystemExit(f"Duplicate slug generated: {slug} (from {name})")
        seen_slugs.add(slug)

        sources_note = "; ".join(r.get("sources", []))
        text = r["text"]
        if sources_note:
            text = f"{text} Sources checked: {sources_note}."

        zones.append({
            "name": display_name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],
            "text": text,
            "query": QUERY_OVERRIDES.get(b["no"], f"{quartieri}, Napoli, Italy"),
        })

    assert len(zones) == 10, f"Expected 10 Municipalità, got {len(zones)}"

    data_note = (
        "Naples: zone shapes are the real official administrative boundaries of the city's 10 Municipalità "
        "(established 2005), sourced from OpenStreetMap's tagged administrative-boundary relations after the "
        "Comune di Napoli's own GIS portal proved unreachable (broken server-side SSL certificate). Naples has no "
        "official open geolocated crime dataset at Municipalità level, so safety levels here are Wandroz's Level "
        "2 approach: genuine current local/national press research per Municipalità, honestly disclosed as "
        "press-based rather than official crime statistics. Where no specific news coverage was found, that is "
        "stated plainly rather than assumed either way. All 10 official Municipalità are mapped, none excluded. "
        "See the methodology page for details and sources."
    )

    out = {
        "label": "Naples, Italy",
        "center": [40.8518, 14.2681],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} municipalità)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
