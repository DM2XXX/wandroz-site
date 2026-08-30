"""
Wandroz — Lisbon zone builder

Merges Lisbon's real official 24 "freguesia" (civil parish) boundaries with
genuine Level 2 press research (Portugal has no open, geolocated
freguesia-level crime dataset — confirmed via prior EMEA research: the
Sistema de Segurança Interna's own annual RASI ["Relatório Anual de
Segurança Interna"] report is PDF-only and reports only at
municipality/national level, with no structured, geolocated,
neighbourhood-level dataset published). So Lisbon follows the same Level 2
approach already used for Rome, Milan, Turin, Barcelona, Madrid and Vienna:
real current local/national press research per freguesia, honestly
disclosed as press-based rather than official crime statistics.

Lisbon's 24 freguesias (since the 2012 administrative reform that merged
the prior 53 into 24) are themselves the natural, complete, non-overlapping
official neighbourhood unit for the city, so all 24 are mapped here — none
excluded, per the standing instruction.

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - lisbon_boundaries_raw.json: 24 freguesia boundary polygons (GeoJSON
    FeatureCollection, already WGS84/EPSG:4326, Polygon per feature),
    sourced from the Câmara Municipal de Lisboa's own official Lisboa
    Aberta open-data portal ("Freguesias 2012" dataset, CC0), reached via
    its ArcGIS Online FeatureServer REST endpoint
    (services.arcgis.com/1dSrzEWVQn5kHHyK/.../Limite_Cartografia/
    FeatureServer/0/query), simplified server-side to ~15m tolerance
    (maxAllowableOffset=0.00015 degrees).
  - lisbon_press_research.json: one entry per freguesia (day/night tone +
    a short honest summary + sources), produced by genuine web research
    (see each entry's own "sources" field for what was actually checked).
    Honest defaults throughout: no evidence found -> green ("no
    particular concern"), never an invented incident or rating.

Name matching is accent-insensitive (NFKD-normalised, diacritics
stripped) as a safety net — the boundaries file carries full Portuguese
accents (e.g. "São Vicente", "Misericórdia") and the research entries were
written against those same names, but matching is still done on
normalised keys in case of any transcription differences; the *boundary*
name (with its correct accents) is always what is written into the final
output.

Output: pipeline/data_zones/lisbon.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city.
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "lisbon_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "lisbon_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "lisbon.json")

# A few freguesia names benefit from a more specific Booking.com search
# query since the plain name alone could be ambiguous or too broad.
QUERY_OVERRIDES = {
    "Santa Maria Maior": "Santa Maria Maior, Lisbon, Portugal",
    "Santo António": "Santo António, Lisbon, Portugal",
    "São Domingos de Benfica": "São Domingos de Benfica, Lisbon, Portugal",
    "São Vicente": "São Vicente, Lisbon, Portugal",
    "Avenidas Novas": "Avenidas Novas, Lisbon, Portugal",
    "Parque das Nações": "Parque das Nações, Lisbon, Portugal",
}


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def norm_key(s):
    return strip_accents(s).lower().strip()


def slugify(name):
    name = strip_accents(name)
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def main():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        boundaries_geo = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_key = {norm_key(r["nom"]): r for r in research}
    if len(research_by_key) != len(research):
        raise SystemExit("Duplicate normalised keys in research data — check for near-duplicate freguesia names")

    boundaries = []
    for feat in boundaries_geo["features"]:
        name = feat["properties"]["NOME"]
        cod = feat["properties"].get("COD_SIG")
        geom = feat["geometry"]
        assert geom["type"] == "Polygon", f"Unexpected geometry type for {name}: {geom['type']}"
        # Take the outer ring (index 0); ignore any interior holes, matching
        # every other city's data_zones convention. Flip GeoJSON's
        # [lon, lat] to Leaflet-style [lat, lon].
        ring = geom["coordinates"][0]
        coords = [[lat, lon] for lon, lat in ring]
        boundaries.append({"nom": name, "cod": cod, "coords": coords})

    boundaries.sort(key=lambda b: str(b["cod"]))

    missing = [b["nom"] for b in boundaries if norm_key(b["nom"]) not in research_by_key]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} freguesias: {missing}")
    extra_keys = set(research_by_key) - {norm_key(b["nom"]) for b in boundaries}
    if extra_keys:
        raise SystemExit(f"Research entries with no matching boundary: {sorted(extra_keys)}")

    zones = []
    seen_slugs = set()
    for b in boundaries:
        name = b["nom"]
        r = research_by_key[norm_key(name)]
        slug = slugify(name)
        if slug in seen_slugs:
            raise SystemExit(f"Duplicate slug generated: {slug} (from {name})")
        seen_slugs.add(slug)

        sources_note = "; ".join(r.get("sources", []))
        text = r["text"]
        if sources_note:
            text = f"{text} Sources checked: {sources_note}."

        zones.append({
            "name": name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Lisbon, Portugal"),
        })

    assert len(zones) == 24, f"Expected 24 freguesias, got {len(zones)}"

    data_note = (
        "Lisbon: neighbourhood shapes are the real official administrative boundaries of Lisbon's 24 "
        "\"freguesias\" (civil parishes, since the 2012 administrative reform that merged the prior 53 "
        "into 24), sourced directly from the Câmara Municipal de Lisboa's own official Lisboa Aberta "
        "open-data portal (\"Freguesias 2012\" dataset, CC0 license), via its ArcGIS Online FeatureServer "
        "REST endpoint. Unlike London/Berlin/Amsterdam/Prague/Oslo/Munich/Stockholm's official crime "
        "statistics, Portugal has no open, geolocated freguesia-level crime dataset (the Sistema de "
        "Segurança Interna's annual RASI report is PDF-only and reports only at municipality/national "
        "level) — so, like Rome, Milan, Turin, Barcelona, Madrid and Vienna, Lisbon's safety levels are "
        "Wandroz's Level 2 approach: genuine current local/national press research per freguesia, "
        "honestly disclosed as press-based rather than official crime statistics. Where no specific news "
        "coverage was found for a freguesia, that is stated plainly rather than assumed either way. See "
        "the methodology page for details and sources."
    )

    out = {
        "label": "Lisbon, Portugal",
        "center": [38.7223, -9.1393],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} freguesias)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
