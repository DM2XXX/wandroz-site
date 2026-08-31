"""
Wandroz — Paris zone builder

Merges Paris's real official 80 "quartier administratif" boundaries with
genuine Level 2 press research (France's SSMSI crime dataset is explicitly
published "à l'échelle communale" — commune level — and Paris is a single
commune, so no official arrondissement- or quartier-level crime breakdown
exists). So Paris follows the same Level 2 approach already used for Rome,
Milan, Turin, Barcelona, Madrid, Vienna and Lisbon: real current
local/national press research per quartier, honestly disclosed as
press-based rather than official crime statistics.

Paris's 80 official quartiers administratifs (4 per arrondissement x 20
arrondissements) are themselves the finest-grain official neighbourhood
subdivision of the city — finer than the 20 arrondissements alone — so all
80 are mapped here, none excluded, per the standing instruction.

Inputs (both reproducible, both checked into pipeline/data_raw/):
  - paris_boundaries_raw.json: 80 quartier boundary objects
    {n_sq_qu, c_qu, l_qu, c_ar, coords}, coords already [lat, lon] and
    already simplified (Douglas-Peucker, ~0.00025 deg tolerance) — sourced
    from opendata.paris.fr's "quartier_paris" dataset (ODbL license) via
    its OpenDataSoft REST API, reassembled from a browser-side extraction.
  - paris_press_research.json: one entry per quartier (day/night tone + a
    short honest summary + sources), produced by 5 parallel genuine-research
    passes (one per group of ~4 arrondissements). Honest defaults
    throughout: no evidence found -> green ("no particular concern"),
    never an invented incident or rating.

Name matching is accent-insensitive (NFKD-normalised, diacritics stripped)
as a safety net, though in practice the research was written directly
against the boundary file's own quartier names. The *boundary* name (with
its correct accents) is always what is written into the final output.

Output: pipeline/data_zones/paris.json, in the same
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

BOUNDARIES_PATH = os.path.join(RAW_DIR, "paris_boundaries_raw.json")
RESEARCH_PATH = os.path.join(RAW_DIR, "paris_press_research.json")
OUT_PATH = os.path.join(OUT_DIR, "paris.json")

# A handful of quartier names are generic enough (or share a name with
# something else entirely) that the plain "{name}, Paris, France" query
# risks a bad Booking.com match — give those a more specific search string.
QUERY_OVERRIDES = {
    "Bel-Air": "Quartier du Bel-Air, Paris 12e, France",
    "Saint-Georges": "Quartier Saint-Georges, Paris 9e, France",
    "Gare": "Quartier de la Gare, Paris 13e, France",
    "Europe": "Quartier de l'Europe, Paris 8e, France",
    "Mail": "Quartier du Mail, Paris 2e, France",
    "Monnaie": "Quartier de la Monnaie, Paris 6e, France",
    "Combat": "Quartier du Combat, Paris 19e, France",
    "Villette": "La Villette, Paris 19e, France",
    "Amérique": "Quartier d'Amérique, Paris 19e, France",
    "Saint-Gervais": "Quartier Saint-Gervais, Paris 4e, France",
    "Saint-Victor": "Quartier Saint-Victor, Paris 5e, France",
    "Saint-Lambert": "Quartier Saint-Lambert, Paris 15e, France",
    "Saint-Vincent-de-Paul": "Quartier Saint-Vincent-de-Paul, Paris 10e, France",
    "Saint-Fargeau": "Quartier Saint-Fargeau, Paris 20e, France",
    "Sainte-Marguerite": "Quartier Sainte-Marguerite, Paris 11e, France",
    "Hôpital-Saint-Louis": "Quartier de l'Hôpital-Saint-Louis, Paris 10e, France",
    "Croulebarbe": "Quartier de la Croulebarbe, Paris 13e, France",
    "Salpêtrière": "Quartier de la Salpêtrière, Paris 13e, France",
    "Necker": "Quartier Necker, Paris 15e, France",
    "Pont-de-Flandre": "Quartier de Pont-de-Flandre, Paris 19e, France",
    "Grandes-Carrières": "Quartier des Grandes-Carrières, Paris 18e, France",
    "Epinettes": "Quartier des Épinettes, Paris 17e, France",
    "Archives": "Quartier des Archives, Paris 3e, France",
    "Arsenal": "Quartier de l'Arsenal, Paris 4e, France",
    "Vivienne": "Quartier Vivienne, Paris 2e, France",
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
        boundaries_raw = json.load(f)
    with open(RESEARCH_PATH, encoding="utf-8") as f:
        research = json.load(f)

    research_by_key = {norm_key(r["nom"]): r for r in research}
    if len(research_by_key) != len(research):
        raise SystemExit("Duplicate normalised keys in research data — check for near-duplicate quartier names")

    boundaries = []
    for z in boundaries_raw:
        name = z["l_qu"]
        coords = z["coords"]  # already [lat, lon], already a single flat ring
        boundaries.append({"nom": name, "cod": z["c_qu"], "c_ar": z["c_ar"], "coords": coords})

    # Sort by arrondissement then by quartier code, matching the dataset's
    # own numbering convention (c_qu increments across arrondissements).
    boundaries.sort(key=lambda b: (b["c_ar"], int(b["cod"])))

    missing = [b["nom"] for b in boundaries if norm_key(b["nom"]) not in research_by_key]
    if missing:
        raise SystemExit(f"Missing press research for {len(missing)} quartiers: {missing}")
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

        display_name = f"{name} ({b['c_ar']}e arr.)"

        zones.append({
            "name": display_name,
            "slug": slug,
            "day": r["day"],
            "night": r["night"],
            "coords": [b["coords"]],  # wrap flat ring into [ring] like every other city's data_zones file
            "text": text,
            "query": QUERY_OVERRIDES.get(name, f"{name}, Paris, France"),
        })

    assert len(zones) == 80, f"Expected 80 quartiers, got {len(zones)}"

    data_note = (
        "Paris: neighbourhood shapes are the real official administrative boundaries of Paris's 80 "
        "\"quartiers administratifs\" (4 per arrondissement x 20 arrondissements, the finest-grain "
        "official neighbourhood subdivision of the city), sourced directly from the City of Paris's own "
        "opendata.paris.fr open-data portal (\"quartier_paris\" dataset, ODbL license). Unlike "
        "London/Berlin/Amsterdam/Prague/Oslo/Munich/Stockholm's official crime statistics, France's SSMSI "
        "crime dataset is published only at commune level, and Paris is a single commune — so, like Rome, "
        "Milan, Turin, Barcelona, Madrid, Vienna and Lisbon, Paris's safety levels are Wandroz's Level 2 "
        "approach: genuine current local/national press research per quartier, honestly disclosed as "
        "press-based rather than official crime statistics. Where no specific news coverage was found for "
        "a quartier, that is stated plainly rather than assumed either way. See the methodology page for "
        "details and sources."
    )

    out = {
        "label": "Paris, France",
        "center": [48.8566, 2.3522],
        "zoom": 12,
        "dataNote": data_note,
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} ({len(zones)} quartiers)")
    day_counts = {}
    night_counts = {}
    for z in zones:
        day_counts[z["day"]] = day_counts.get(z["day"], 0) + 1
        night_counts[z["night"]] = night_counts.get(z["night"], 0) + 1
    print(f"Day tone distribution: {day_counts}")
    print(f"Night tone distribution: {night_counts}")


if __name__ == "__main__":
    main()
