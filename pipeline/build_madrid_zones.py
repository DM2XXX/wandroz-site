"""
Wandroz — Madrid zone builder

Merges Madrid's real official "barrio" (neighbourhood) boundaries with
genuine Level 2 press research (Madrid has no official neighbourhood-level
crime dataset — confirmed absent from both the Ayuntamiento's open-data
portal and the Comunidad de Madrid's statistical offerings — so this city
follows the same Level 2 approach already used for Rome, Milan, Turin and
Barcelona: real current local/national press research per area, honestly
disclosed as press-based rather than official crime statistics).

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - madrid_boundaries_2026.json: 131 barrios' simplified boundary polygons
    (Douglas-Peucker, ~15m tolerance), sourced from the Ayuntamiento de
    Madrid's own official Geoportal TopoJSON dataset
    (geoportal.madrid.es, LIMITES_ADMINISTRATIVOS/Barrios), confirmed
    already in WGS84 (no reprojection needed) via the TopoJSON's own
    transform.translate origin.
  - madrid_press_research.json: one entry per barrio (day/night tone +
    a short honest summary + sources), produced by genuine web research
    (see each entry's own "sources" field for what was actually checked).
    Honest defaults throughout: no evidence found -> green ("no
    particular concern"), never an invented incident or rating.

Name matching is accent-insensitive (NFKD-normalised, diacritics
stripped) because the boundaries file carries full Spanish accents
(e.g. "Peñagrande", "Vicálvaro") while some research entries were
transcribed in plain ASCII — the *boundary* name (with its correct
accents) is always what is written into the final output.

Output: pipeline/data_zones/madrid.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "madrid_boundaries_2026.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "madrid_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "madrid.json")

# District code -> official district name, purely for reference/debug
# output (not written into the final zone records).
DISTRICT_NAMES = {
    "1": "Centro", "2": "Arganzuela", "3": "Retiro", "4": "Salamanca",
    "5": "Chamartín", "6": "Tetuán", "7": "Chamberí",
    "8": "Fuencarral - El Pardo", "9": "Moncloa - Aravaca", "10": "Latina",
    "11": "Carabanchel", "12": "Usera", "13": "Puente de Vallecas",
    "14": "Moratalaz", "15": "Ciudad Lineal", "16": "Hortaleza",
    "17": "Villaverde", "18": "Villa de Vallecas", "19": "Vicálvaro",
    "20": "San Blas - Canillejas", "21": "Barajas",
}

# A handful of barrio names are long/compound; give them a more
# commonly-searched Booking.com query, mirroring how Barcelona/Rome
# handled their own compound names.
QUERY_OVERRIDES = {
    "Villaverde Alto - Casco Histórico de Villaverde": "Villaverde Alto, Madrid, Spain",
    "Casco Histórico de Vallecas": "Puente de Vallecas, Madrid, Spain",
    "Casco Histórico de Vicálvaro": "Vicálvaro, Madrid, Spain",
    "Casco Histórico de Barajas": "Barajas, Madrid, Spain",
    "Palos de la Frontera": "Méndez Álvaro, Madrid, Spain",
    "San Juan Bautista": "Ciudad Lineal, Madrid, Spain",
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
        boundaries = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_key = {norm_key(r["nom"]): r for r in research}
    if len(research_by_key) != len(research):
        raise SystemExit("Duplicate normalised keys in research data — check for near-duplicate barrio names")

    boundary_keys = {norm_key(b["nom"]) for b in boundaries}
    missing = [b["nom"] for b in boundaries if norm_key(b["nom"]) not in research_by_key]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} barrios: {missing}")
    extra = [r["nom"] for r in research if norm_key(r["nom"]) not in boundary_keys]
    if extra:
        raise SystemExit(f"Research entries with no matching boundary: {extra}")

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
            "query": QUERY_OVERRIDES.get(name, f"{name}, Madrid, Spain"),
        })

    assert len(zones) == 131, f"Expected 131 barrios, got {len(zones)}"

    data_note = (
        "Madrid: neighbourhood shapes are the Ayuntamiento de Madrid's real official administrative "
        "boundaries (131 official \"barrios\", grouped into 21 districts), sourced directly from the "
        "city's own Geoportal (geoportal.madrid.es) TopoJSON dataset. Unlike London/Berlin/Amsterdam/"
        "Prague/Oslo/Munich/Stockholm's official crime statistics, Madrid has no open, geolocated "
        "barrio-level crime dataset published by the Ayuntamiento or the Comunidad de Madrid — so, like "
        "Rome, Milan, Turin and Barcelona, Madrid's safety levels are Wandroz's Level 2 approach: genuine "
        "current local/national press research per barrio, honestly disclosed as press-based rather than "
        "official crime statistics. Where no specific news coverage was found for a barrio, that is stated "
        "plainly rather than assumed either way. See the methodology page for details and sources."
    )

    out = {
        "label": "Madrid, Spain",
        "center": [40.4168, -3.7038],
        "zoom": 11,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} barrios)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
