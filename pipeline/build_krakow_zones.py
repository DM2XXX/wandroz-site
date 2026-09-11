"""
Wandroz — Kraków zone builder

Kraków's 18 official dzielnice (districts) — established administrative
units, each with its own local government (rada dzielnicy), the finest
official government-defined neighbourhood-equivalent unit for the whole
city. All 18 are mapped, none excluded, per the standing instruction.

Boundary provenance: Poland's official "Krajowa Mapa Zagrożeń
Bezpieczeństwa" (National Security Threat Map, mapy.geoportal.gov.pl,
run by the national police) was checked first as a possible official
district-level crime-data source. It turned out not usable for this
build: it is a crowd-sourced map of individual citizen-reported nuisance
pins (speeding, public drinking, stray animals, etc.), not aggregated
crime statistics, has no per-dzielnica breakdown or export, and its map
tiles would not even render in this build environment. So, as with
Venice, Athens, Naples and Budapest, boundaries were instead sourced from
OpenStreetMap's own tagged administrative-boundary relations for each
dzielnica (admin_level=9, boundary=administrative, each cross-checked
against its own Polish Wikipedia "Dzielnica N ..." article via the
relation's wikipedia tag), confirmed via Nominatim to be genuine,
officially-modelled geometry rather than an approximation. The official
list of the 18 dzielnice names and numbers was independently confirmed
against the City of Kraków's own municipal website (krakow.pl).

Kraków has no accessible official open geolocated crime dataset at
dzielnica level, so this follows Wandroz's standard "Level 2" approach
used for Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris,
Athens, Venice, Dublin, Naples and Budapest: genuine, current, dated
local press and official-survey research per dzielnica, honestly
disclosed as press/survey-based rather than an official crime feed.
Two of the sources used report district data only in police-defined
groupings that combine two or three dzielnice — this is disclosed
per-zone rather than presented as a precise single-district figure.
Where sources genuinely disagree (Bronowice, Bieńczyce, Wzgórza
Krzesławickie), both findings are disclosed rather than one being
picked.

Inputs (checked into pipeline/data_raw/):
  - krakow_boundaries_raw.json: GeoJSON FeatureCollection, one feature
    per dzielnica, properties {name: "Stare Miasto", no: N}, geometry
    Polygon, built from OpenStreetMap admin_level=9 relations via
    Nominatim lookup.
  - krakow_press_research.json: one entry per dzielnica (nom matching
    the boundary's "name" property, quartieri label, day/night tone,
    text, sources).

Output: pipeline/data_zones/krakow.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "krakow_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "krakow_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "krakow.json")

# Neighbourhood-based query overrides so Booking.com search lands on a
# recognisable, ASCII place name rather than a Polish-diacritic string
# Booking's search box may not resolve cleanly.
QUERY_OVERRIDES = {
    1: "Stare Miasto, Krakow, Poland",
    2: "Grzegorzki, Krakow, Poland",
    3: "Pradnik Czerwony, Krakow, Poland",
    4: "Pradnik Bialy, Krakow, Poland",
    5: "Krowodrza, Krakow, Poland",
    6: "Bronowice, Krakow, Poland",
    7: "Zwierzyniec, Krakow, Poland",
    8: "Debniki, Krakow, Poland",
    9: "Lagiewniki, Krakow, Poland",
    10: "Swoszowice, Krakow, Poland",
    11: "Podgorze Duchackie, Krakow, Poland",
    12: "Prokocim, Krakow, Poland",
    13: "Podgorze, Krakow, Poland",
    14: "Czyzyny, Krakow, Poland",
    15: "Mistrzejowice, Krakow, Poland",
    16: "Bienczyce, Krakow, Poland",
    17: "Wzgorza Krzeslawickie, Krakow, Poland",
    18: "Nowa Huta, Krakow, Poland",
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
        raise SystemExit(f"Missing press research for {len(missing)} dzielnica: {missing}")
    extra = [name for name in research_by_name if name not in {b["nom"] for b in boundaries}]
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

    zones = []
    seen_slugs = set()
    for b in boundaries:
        name = b["nom"]
        r = research_by_name[name]
        quartieri = r["quartieri"]
        display_name = f"{quartieri} (dzielnica {b['no']})"
        slug = slugify(f"dzielnica-{b['no']}")
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
            "query": QUERY_OVERRIDES.get(b["no"], f"{quartieri}, Krakow, Poland"),
        })

    assert len(zones) == 18, f"Expected 18 dzielnice, got {len(zones)}"

    data_note = (
        "Kraków: zone shapes are the real official administrative boundaries of the city's 18 dzielnice "
        "(districts), sourced from OpenStreetMap's tagged administrative-boundary relations after Poland's "
        "national Krajowa Mapa Zagrożeń Bezpieczeństwa (National Security Threat Map) proved unusable — it is "
        "a crowd-sourced map of individual citizen-reported nuisances, not aggregated crime statistics, with no "
        "per-district breakdown or export — and no other official open geolocated crime dataset at dzielnica "
        "level could be found. Safety levels here are Wandroz's Level 2 approach: genuine current local press "
        "reporting and the City of Kraków's own official resident-safety survey, honestly disclosed as press- "
        "and survey-based rather than official crime statistics. Two sources report figures only in police-"
        "defined groupings spanning two or three dzielnice at once — this is disclosed per zone. Where sources "
        "genuinely disagreed, that is stated plainly rather than one being picked. All 18 official dzielnice "
        "are mapped, none excluded. See the methodology page for details and sources."
    )

    out = {
        "label": "Kraków, Poland",
        "center": [50.0619, 19.9368],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} dzielnice)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
