"""
Wandroz — Barcelona zone builder

Merges Barcelona's real official "barri" (neighbourhood) boundaries with
genuine Level 2 press research (no open barri-level crime dataset exists
for Barcelona — its own open-data portal was bot-gated when checked, and
Madrid's equivalent portal explicitly declined to publish this data too,
so this city follows the same Level 2 approach already used for Rome,
Milan and Turin: real current local/national press research per area,
honestly disclosed as press-based rather than official crime statistics).

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - barcelona_boundaries_2023.json: 73 barris' simplified boundary
    polygons (Douglas-Peucker, ~15m tolerance), sourced from the
    Ajuntament de Barcelona's own official administrative-units dataset
    ("20170706-districtes-barris" / Unitats_Administratives_BCN.shp),
    reached in practice via a direct GeoJSON conversion mirror
    (github.com/martgnz/bcn-geodata) since the Ajuntament's own portal
    was bot-gated for automated/browser-tool access at build time.
  - barcelona_press_research.json: one entry per barri (day/night tone +
    a short honest summary + sources), produced by genuine web research
    (see the entries' own "sources" field for what was actually checked).
    Honest defaults throughout: no evidence found -> green ("no
    particular concern"), never an invented incident or rating.

Output: pipeline/data_zones/barcelona.json, in the same
{label, center, zoom, dataNote, zones: [{name, slug, day, night, coords,
text, query}]} shape build_site.py's render_illustrative_city() expects
for every other illustrative/press-research city (Milan, Rome, Turin).
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_DIR = os.path.join(BASE_DIR, "data_zones")

BOUNDARIES_PATH = os.path.join(RAW_DIR, "barcelona_boundaries_2023.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "barcelona_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "barcelona.json")

# District code -> official district name, purely for reference/debug
# output (not written into the final zone records, which are flat like
# every other illustrative city here).
DISTRICT_NAMES = {
    "01": "Ciutat Vella", "02": "L'Eixample", "03": "Sants-Montjuïc",
    "04": "Les Corts", "05": "Sarrià-Sant Gervasi", "06": "Gràcia",
    "07": "Horta-Guinardó", "08": "Nou Barris", "09": "Sant Andreu",
    "10": "Sant Martí",
}

# Booking.com search query per barri. Most barri names are already
# specific/recognisable enough to use as-is; a handful of compound names
# (district-style "X - Y" or "X, Y i Z" names) are trimmed to the more
# commonly-searched part, mirroring how Milan's build handled its own
# compound micro-neighbourhood names.
QUERY_OVERRIDES = {
    "Sant Pere, Santa Caterina i la Ribera": "El Born, Barcelona, Spain",
    "Sants - Badal": "Sants, Barcelona, Spain",
    "la Maternitat i Sant Ramon": "Sant Ramon, Barcelona, Spain",
    "Sant Gervasi - la Bonanova": "La Bonanova, Barcelona, Spain",
    "Sant Gervasi - Galvany": "Galvany, Barcelona, Spain",
    "el Putxet i el Farró": "El Putxet, Barcelona, Spain",
    "Vallvidrera, el Tibidabo i les Planes": "Tibidabo, Barcelona, Spain",
    "el Camp d'en Grassot i Gràcia Nova": "Camp d'en Grassot, Barcelona, Spain",
    "el Camp de l'Arpa del Clot": "Camp de l'Arpa, Barcelona, Spain",
    "el Parc i la Llacuna del Poblenou": "Poblenou, Barcelona, Spain",
    "la Vila Olímpica del Poblenou": "Vila Olímpica, Barcelona, Spain",
    "Diagonal Mar i el Front Marítim del Poblenou": "Diagonal Mar, Barcelona, Spain",
    "Provençals del Poblenou": "Provençals, Barcelona, Spain",
    "Sant Martí de Provençals": "Sant Martí, Barcelona, Spain",
    "la Verneda i la Pau": "La Verneda, Barcelona, Spain",
    "Vilapicina i la Torre Llobeta": "Vilapicina, Barcelona, Spain",
    "el Turó de la Peira": "Turó de la Peira, Barcelona, Spain",
    "la Vall d'Hebron": "Vall d'Hebron, Barcelona, Spain",
    "Sant Genís dels Agudells": "Sant Genís dels Agudells, Barcelona, Spain",
    "el Congrés i els Indians": "El Congrés, Barcelona, Spain",
}


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def main():
    with open(BOUNDARIES_PATH, encoding="utf-8") as f:
        boundaries = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_name = {r["nom"]: r for r in research}

    missing = [b["nom"] for b in boundaries if b["nom"] not in research_by_name]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} barris: {missing}")
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
            "name": name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Barcelona, Spain"),
        })

    assert len(zones) == 73, f"Expected 73 barris, got {len(zones)}"

    data_note = (
        "Barcelona: neighbourhood shapes are the Ajuntament de Barcelona's real official administrative "
        "boundaries (73 official \"barris\", grouped into 10 districts), reached via a direct GeoJSON conversion "
        "of the Ajuntament's own shapefile dataset (the portal's own raw endpoint was bot-gated for automated "
        "access at build time, so a mirror that republishes the same official geometry unmodified was used "
        "instead). Unlike London/Berlin/Amsterdam/Prague/Oslo/Munich/Stockholm's official crime statistics, "
        "Barcelona has no open, geolocated barri-level crime dataset (the city's own open-data portal does not "
        "publish one) — so, like Rome, Milan and Turin, Barcelona's safety levels are Wandroz's Level 2 "
        "approach: genuine current local/national press research per barri, honestly disclosed as press-based "
        "rather than official crime statistics. Where no specific news coverage was found for a barri, that is "
        "stated plainly rather than assumed either way. See the methodology page for details and sources."
    )

    out = {
        "label": "Barcelona, Spain",
        "center": [41.3874, 2.1686],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    by_district_count = {}
    print(f"Wrote {OUT_PATH} ({len(zones)} barris)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
