"""
Wandroz — Vienna zone builder

Merges Vienna's real official 23 "Bezirke" (district) boundaries with
genuine Level 2 press research (Austria has no open, geolocated Bezirk-level
crime dataset — confirmed via prior EMEA research: Statistik Austria and the
Bundeskriminalamt's PKS/Kriminalitätsbericht only publish at Bundesland/state
level, and the BK's own internal "Kriminalitätsatlas" spatial-analysis tool
is explicitly for internal BMI use only, not public). So Vienna follows the
same Level 2 approach already used for Rome, Milan, Turin, Barcelona and
Madrid: real current local/national press research per district, honestly
disclosed as press-based rather than official crime statistics.

Vienna's 23 Bezirke are themselves the natural, complete, non-overlapping
official neighbourhood unit for the city (unlike Barcelona/Madrid's barrios,
there is no finer *officially bounded* neighbourhood layer below the Bezirk —
"Zählbezirke" are statistical sub-areas, not administrative neighbourhoods,
and "Grätzel" are informal/cultural, not officially bounded), so all 23
districts are mapped here — none excluded, per the standing instruction.

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - vienna_boundaries_raw.json: 23 Bezirke boundary polygons (GeoJSON
    FeatureCollection, MultiPolygon per feature, "Simplified to 99.5%" per
    the source repo's own mapshaper.org processing), sourced from
    Statistik Austria's own official "Bezirke" administrative-boundary
    dataset (data.statistik.gv.at, as of January 2021), reached in practice
    via the ginseng666/GeoJSON-TopoJSON-Austria GitHub mirror (CC BY 4.0,
    Flooh Perlot) since Vienna's own data.wien.gv.at WFS endpoint was not
    directly reachable from this build environment. Filtered down from the
    mirror's all-Austria district file to just Vienna's 23 (iso codes
    "901".."923"; iso "900" is the whole-city single feature and is
    excluded).
  - vienna_press_research.json: one entry per Bezirk (day/night tone + a
    short honest summary + sources), produced by genuine web research (see
    the entries' own "sources" field for what was actually checked). Honest
    defaults throughout: no evidence found -> green ("no particular
    concern"), never an invented incident or rating.

Output: pipeline/data_zones/vienna.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city (Milan, Rome, Turin,
Barcelona, Madrid).
"""

import json
import os
import re

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "vienna_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "vienna_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "vienna.json")

# Booking.com search query per Bezirk. Most district names are already
# specific/recognisable enough to use as-is; a couple benefit from adding
# "Wien" explicitly since the plain name alone could be ambiguous outside
# an Austrian context.
QUERY_OVERRIDES = {
    "Landstraße": "Landstraße, Vienna, Austria",
    "Favoriten": "Favoriten, Vienna, Austria",
    "Liesing": "Liesing, Vienna, Austria",
}


def slugify(name):
    name = name.lower()
    name = (name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                .replace("ß", "ss"))
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def strip_bezirk_prefix(raw_name):
    """'Wien 15.,Rudolfsheim-Fünfhaus' -> 'Rudolfsheim-Fünfhaus'"""
    _, _, rest = raw_name.partition(",")
    return rest.strip()


def main():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        boundaries_geo = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_name = {r["nom"]: r for r in research}

    boundaries = []
    for feat in boundaries_geo["features"]:
        raw_name = feat["properties"]["name"]
        name = strip_bezirk_prefix(raw_name)
        iso = feat["properties"]["iso"]
        geom = feat["geometry"]
        assert geom["type"] == "MultiPolygon", f"Unexpected geometry type for {name}: {geom['type']}"
        # Single polygon, single ring per Bezirk (verified at build time) —
        # take the outer ring, and flip GeoJSON's [lon, lat] to
        # Leaflet-style [lat, lon] like every other city's data_zones file.
        polygons = geom["coordinates"]
        assert len(polygons) == 1, f"{name} has {len(polygons)} polygon parts, expected 1"
        ring = polygons[0][0]
        coords = [[lat, lon] for lon, lat in ring]
        boundaries.append({"nom": name, "iso": iso, "coords": coords})

    boundaries.sort(key=lambda b: int(b["iso"]))

    missing = [b["nom"] for b in boundaries if b["nom"] not in research_by_name]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} Bezirke: {missing}")
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
            "name": f"{name} ({b['iso'][1:]}. Bezirk)",
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Vienna, Austria"),
        })

    assert len(zones) == 23, f"Expected 23 Bezirke, got {len(zones)}"

    data_note = (
        "Vienna: district shapes are the real official administrative boundaries of Vienna's 23 "
        "\"Bezirke\", sourced from Statistik Austria's own official boundary dataset (via a direct "
        "GeoJSON conversion of that dataset, since Vienna's own data.wien.gv.at endpoint was not "
        "directly reachable at build time). Unlike London/Berlin/Amsterdam/Prague/Oslo/Munich/"
        "Stockholm's official crime statistics, Austria has no open, geolocated Bezirk-level crime "
        "dataset (Statistik Austria and the Bundeskriminalamt only publish at Bundesland/state level; "
        "an internal police spatial-crime-analysis tool exists but is not public) — so, like Rome, "
        "Milan, Turin, Barcelona and Madrid, Vienna's safety levels are Wandroz's Level 2 approach: "
        "genuine current local/national press research per district, honestly disclosed as press-based "
        "rather than official crime statistics. Where no specific news coverage was found for a "
        "district, that is stated plainly rather than assumed either way. See the methodology page for "
        "details and sources."
    )

    out = {
        "label": "Vienna, Austria",
        "center": [48.2082, 16.3738],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} Bezirke)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
