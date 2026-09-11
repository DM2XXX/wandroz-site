"""
Wandroz — Budapest zone builder

Budapest's 23 official kerületek (districts) — established administrative
units, each with its own local government — the finest official
government-defined neighbourhood-equivalent unit for the whole city. All 23
are mapped, none excluded, per the standing instruction.

Boundary provenance: Budapest's own PRE-STAT crime-statistics portal
(prestat.lechnerkozpont.hu) was checked first as a possible official
district-level data source, since it had been flagged as an unconfirmed
lead in earlier research. It turned out not to be usable for this build:
citizen access requires an authenticated Hungarian government-portal
(Ügyfélkapu) login this environment does not have, and — separately — its
own documentation states it breaks data down to settlement/járás/county/
regional level, not specifically by Budapest kerület. A search of KSH
(the Central Statistical Office) and Hungary's open-data portal likewise
turned up only national- and county-level registered-crime datasets, no
per-kerület breakdown. So, as with Venice, Athens and Naples, boundaries
were instead sourced from OpenStreetMap's own tagged administrative-
boundary relations for each kerület (admin_level=9, boundary=administrative),
confirmed via Overpass + Nominatim to be genuine, officially-modelled
geometry rather than an approximation.

Unlike Edinburgh (which has genuine numeric crimes-per-1,000 data), Budapest
has no accessible official open geolocated crime dataset at kerület level,
so this follows Wandroz's standard "Level 2" approach used for Milan, Rome,
Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens, Venice, Dublin and
Naples: genuine, current, dated local/national press research per kerület,
honestly disclosed as press-based rather than official crime statistics.
Where no specific news coverage was found, that is stated plainly rather
than an incident being invented, and where sources genuinely disagree
(District XV), both findings are disclosed rather than one being picked.

Inputs (checked into pipeline/data_raw/):
  - budapest_boundaries_raw.json: GeoJSON FeatureCollection, one feature per
    kerület, properties {name: "N. kerület", no: N}, geometry Polygon, built
    from OpenStreetMap admin_level=9 relations via Nominatim lookup.
  - budapest_press_research.json: one entry per kerület (nom matching
    "N. kerület", quartieri list, day/night tone, text, sources).

Output: pipeline/data_zones/budapest.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "budapest_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "budapest_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "budapest.json")

# Neighbourhood-based query overrides so Booking.com search lands on a
# recognisable place name rather than the bureaucratic "N. kerület".
QUERY_OVERRIDES = {
    1: "Var, Budapest, Hungary",
    2: "Rozsadomb, Budapest, Hungary",
    3: "Obuda, Budapest, Hungary",
    4: "Ujpest, Budapest, Hungary",
    5: "Belvaros, Budapest, Hungary",
    6: "Terezvaros, Budapest, Hungary",
    7: "Erzsebetvaros, Budapest, Hungary",
    8: "Jozsefvaros, Budapest, Hungary",
    9: "Ferencvaros, Budapest, Hungary",
    10: "Kobanya, Budapest, Hungary",
    11: "Ujbuda, Budapest, Hungary",
    12: "Hegyvidek, Budapest, Hungary",
    13: "Angyalfold, Budapest, Hungary",
    14: "Zuglo, Budapest, Hungary",
    15: "Rakospalota, Budapest, Hungary",
    16: "Matyasfold, Budapest, Hungary",
    17: "Rakosmente, Budapest, Hungary",
    18: "Pestszentlorinc, Budapest, Hungary",
    19: "Kispest, Budapest, Hungary",
    20: "Pesterzsebet, Budapest, Hungary",
    21: "Csepel, Budapest, Hungary",
    22: "Budafok, Budapest, Hungary",
    23: "Soroksar, Budapest, Hungary",
}


def slugify(name):
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def largest_ring(geom):
    """Return the outer ring (list of [lon, lat]) of the largest part of a
    Polygon or MultiPolygon, by vertex count — consistent with how every
    other city in this project handles small disjoint boundary fragments."""
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
        raise SystemExit(f"Missing press research for {len(missing)} kerület: {missing}")
    extra = [name for name in research_by_name if name not in {b["nom"] for b in boundaries}]
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    seen_slugs = set()
    for b in boundaries:
        name = b["nom"]
        r = research_by_name[name]
        quartieri = r["quartieri"]
        display_name = f"{quartieri} ({b['no']}. kerület)"
        slug = slugify(f"kerulet-{b['no']}")
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
            "query": QUERY_OVERRIDES.get(b["no"], f"{quartieri}, Budapest, Hungary"),
        })

    assert len(zones) == 23, f"Expected 23 kerület, got {len(zones)}"

    data_note = (
        "Budapest: zone shapes are the real official administrative boundaries of the city's 23 kerületek "
        "(districts), sourced from OpenStreetMap's tagged administrative-boundary relations after Hungary's "
        "PRE-STAT crime-statistics portal proved unusable (requires an authenticated Hungarian government-portal "
        "login this build could not obtain, and its own documentation says it does not break data down to "
        "kerület level in any case) and no other official open geolocated crime dataset at kerület level could "
        "be found. Safety levels here are Wandroz's Level 2 approach: genuine current local/national press "
        "research per kerület, honestly disclosed as press-based rather than official crime statistics. Where "
        "no specific news coverage was found, or where sources genuinely disagreed, that is stated plainly "
        "rather than assumed either way. All 23 official kerületek are mapped, none excluded. See the "
        "methodology page for details and sources."
    )

    out = {
        "label": "Budapest, Hungary",
        "center": [47.4979, 19.0402],
        "zoom": 11,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} kerület)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
