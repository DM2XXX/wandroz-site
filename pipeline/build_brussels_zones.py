"""
Wandroz — build pipeline/data_zones/brussels.json from real official
Brussels-Capital Region data: all 19 official communes, each with a real
recorded-crime total, a real population figure, and a real administrative
boundary polygon.

SOURCES (all fetched live via the connected Chrome browser — this sandbox
has no general outbound network access from Bash/curl, reconfirmed this
session against bisa.brussels, statbel.fgov.be and opendata.brussels.be)
  - Crime counts: BISA (Brussels Instituut voor Statistiek en Analyse /
    Institut bruxellois de statistique et d'analyse)'s published Excel
    workbook "14.1_veiligheid_crim_&_PZ", table 14.1.1.1 — total registered
    crimes and misdemeanors (all offence categories combined), per commune,
    sourced from Federale Politie (federal police), years 2016-2025.
    Parsed directly in-browser via SheetJS against the fetched .xlsx bytes.
    Saved to pipeline/data_raw/brussels_crime_2025.json — all 19 communes,
    2025 (most recent full year) is the figure used here.
  - Population: Statbel (Belgian national statistics office)'s published
    "Bevolking_per_gemeente.xlsx", sheet "Bevolking in 2025", one row per
    commune (NIS/INS code, Dutch name, men, women, total). Parsed the same
    way via SheetJS. Saved to pipeline/data_raw/brussels_population_2025.json
    — all 19 Brussels-Capital Region communes (NIS 21001-21019); the
    arrondissement-level aggregate row (NIS 21000) is excluded as it is not
    a commune.
  - Geometry: Brussels-Capital Region commune boundary polygons via the
    OpenDataSoft V2 Explore API (opendata.brussels.be), GeoJSON export.
    The raw export (777KB, 20,229 points) was simplified in-browser with a
    from-scratch Douglas-Peucker implementation (tolerance 0.00008 degrees)
    plus coordinate rounding to 5 decimal places, down to 43.8KB/2,195
    points, to make it transferable — every commune's real shape is still
    represented, just at lower vertex density (imperceptible at map
    scale). Saved to pipeline/data_raw/brussels_communes.geojson —
    properties: {name: <French commune name>, national_code: <NIS code>}.
    TWO communes — Saint-Gilles and Ixelles — came back as GeoJSON
    MultiPolygon with a second, smaller polygon part (a simplification
    artifact: Saint-Gilles' second part is a ~440x-smaller sliver entirely
    inside the main polygon's bounding box; Ixelles' second part overlaps
    the main polygon's bounding box rather than being a genuinely separate
    landmass). For both, only the LARGEST polygon part (by area) is kept
    here — the same "keep the larger polygon, drop the tiny/duplicate
    fragment" handling already used for Munich's two WFS duplicate
    districts — so every commune is still represented by one clean shape,
    and this keeps Brussels using the exact same simple single-polygon
    coords format as every other city in this codebase (no separate
    multi-polygon rendering path needed). This is a shape simplification
    only — it does not affect which communes are included (all 19 are
    mapped, none excluded) or their real crime/population figures.

WHY 2025 CRIME AGAINST 2025 POPULATION
  Both BISA's crime workbook and Statbel's population workbook publish a
  2025 figure, so — unlike Munich's one-year crime/population mismatch —
  Brussels' rate here compares same-year crime and population.

METHODOLOGY — MIRRORS BERLIN / AMSTERDAM / PRAGUE / OSLO / MUNICH / STOCKHOLM,
  NOT THE ITALIAN/SPANISH/PORTUGUESE/AUSTRIAN/FRENCH CITIES' PRESS-RESEARCH
  APPROACH
  Real official crime and population statistics per zone. Rate = 2025 total
  registered crimes and misdemeanors / 2025 population * 100,000. Tone
  bucketing uses the SAME relative-to-citywide-average thresholds as those
  cities: >=1.3x average -> red, <=0.8x average -> green, else yellow. The
  source data has no time-of-day breakdown, so day and night tones are set
  equal per zone, exactly as those cities do, and disclosed as such in the
  banner.

A CAVEAT WORTH FLAGGING EXPLICITLY: this rate is calculated against
  registered residents, not footfall. The City of Brussels ("Bruxelles" /
  "Brussel" — the commune containing the historic Pentagon centre, Gare
  Centrale, Gare du Nord, and a large share of the region's hotels, shops
  and offices) and Saint-Gilles (home to Gare du Midi, Brussels' Eurostar/
  international rail hub, plus the Barrière/Parvis nightlife area) both
  show a rate roughly double the citywide average — a comparatively modest
  resident base next to some of the region's densest concentrations of
  station traffic, tourism, and nightlife, the same footfall effect already
  documented for London's West End, Prague, Amsterdam, Berlin, Oslo Sentrum
  and Munich's Altstadt-Lehel/Ludwigsvorstadt-Isarvorstadt. This is
  disclosed in the banner and in each affected zone's own text.

OUTPUT
  pipeline/data_zones/brussels.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for Berlin/Amsterdam/
  Prague/Oslo/Munich/Stockholm: {"label","center","zoom","dataNote","zones":
  [{"name","slug","day","night","coords","text","query"}]}. All 19 official
  communes included — none excluded ("tutti i quartieri devono essere
  mappati nessuno escluso").

USAGE
  python pipeline/build_brussels_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "brussels.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

# High-footfall communes get an extra sentence in their zone text
# explaining the resident-vs-footfall effect, mirroring Oslo Sentrum /
# London West End / Prague centre / Munich Altstadt-Lehel.
FOOTFALL_NOTE = {
    "Bruxelles": (
        " The City of Brussels is the region's historic and administrative "
        "centre — the Grand-Place/Pentagon, Gare Centrale, Gare du Nord, and "
        "a large share of the region's hotels, shops and offices sit here "
        "on a comparatively modest resident base, so its rate reflects huge "
        "daytime and evening footfall against relatively few registered "
        "residents rather than elevated risk per visit."
    ),
    "Saint-Gilles": (
        " Saint-Gilles is home to Gare du Midi — Brussels' Eurostar and "
        "international rail hub, and one of Europe's busiest stations — "
        "plus the Barrière/Parvis nightlife area, both of which draw far "
        "more people through the commune than its resident count alone "
        "would suggest, which pushes its per-resident rate up without that "
        "meaning elevated risk per visit."
    ),
}


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def load_crime():
    path = os.path.join(RAW_DIR, "brussels_crime_2025.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # nis_code_map: NIS code -> Dutch commune name (the key used in
    # totals_by_commune, matching BISA's own workbook).
    nis_to_dutch = data["nis_code_map"]
    totals = data["totals_by_commune"]
    out = {}
    for code, dutch_name in nis_to_dutch.items():
        rec = totals.get(dutch_name)
        if not rec:
            continue
        out[code] = {"name_nl": dutch_name, "crimes": rec["2025"]}
    return out


def load_population():
    path = os.path.join(RAW_DIR, "brussels_population_2025.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # columns: [nis_code, name_nl, men, women, total]
    return {row[0]: row[4] for row in data["rows"]}


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
    path = os.path.join(RAW_DIR, "brussels_communes.geojson")
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    out = {}
    dropped = []
    for feat in g["features"]:
        code = feat["properties"]["national_code"]
        name_fr = feat["properties"]["name"]
        polys = feat["geometry"]["coordinates"]  # MultiPolygon: [polygon, ...], polygon = [ring, ...]
        if len(polys) > 1:
            areas = [_ring_area(p[0]) for p in polys]
            best = polys[areas.index(max(areas))]
            dropped.append((name_fr, len(polys) - 1))
        else:
            best = polys[0]
        ring = best[0]  # outer ring only — no commune in this dataset has holes
        # GeoJSON order is [lon, lat]; Wandroz's zone JSON (Leaflet-facing)
        # uses [lat, lon], matching every other city's data_zones file.
        coords = [[lat, lon] for lon, lat in ring]
        out[code] = {"name_fr": name_fr, "coords": [coords]}
    if dropped:
        names = [n for n, _ in dropped]
        print(f"NOTE: kept only the largest polygon part for {names} (see script docstring)")
    return out


def tone_for(rate, avg):
    ratio = rate / avg if avg else 1.0
    if ratio >= RED_THRESHOLD:
        return "red"
    if ratio <= GREEN_THRESHOLD:
        return "green"
    return "yellow"


def build_text(name, crimes, pop, rate, tone, avg):
    ratio = rate / avg if avg else 1.0
    if tone == "red":
        rel = f"roughly {ratio:.1f}x the citywide commune average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}x the citywide average, below it"
    else:
        rel = "close to the citywide average"
    rate_fmt = f"{rate:,.0f}"
    crimes_fmt = f"{crimes:,}"
    pop_fmt = f"{pop:,}"
    extra_note = FOOTFALL_NOTE.get(name, "")

    return (
        f"{name} is one of the 19 official communes of the Brussels-Capital Region. "
        f"BISA (Brussels Institute for Statistics and Analysis), citing Federale "
        f"Politie figures, recorded {crimes_fmt} total registered crimes and "
        f"misdemeanours here in 2025, across a population of {pop_fmt} residents "
        f"(Statbel, 2025) — a rate of {rate_fmt} offences per 100,000 residents, "
        f"{rel}. This rate is calculated against registered residents, not "
        f"footfall, so a busy central, station, or nightlife-heavy commune can read "
        f"higher without that meaning it is unusually risky to walk through, and a "
        f"quiet residential commune can show a low rate simply by having few "
        f"offences relative to its population.{extra_note} This is Wandroz's "
        "official-data layer for Brussels — real BISA / Federale Politie and "
        "Statbel figures, not a qualitative or press-based judgment — and the "
        "source data is not split here by time of day, so both figures shown here "
        "are the same."
    )


def main():
    crime = load_crime()
    population = load_population()
    geometry = load_geometry()

    missing_geo = [c for c in crime if c not in geometry]
    if missing_geo:
        names = [crime[c]["name_nl"] for c in missing_geo]
        print(f"WARNING: {len(missing_geo)} communes with no geometry: {names}")
    missing_pop = [c for c in crime if c not in population]
    if missing_pop:
        names = [crime[c]["name_nl"] for c in missing_pop]
        print(f"WARNING: {len(missing_pop)} communes with no population: {names}")

    merged = []
    for code, c in crime.items():
        if code not in geometry or code not in population:
            continue
        pop = population[code]
        crimes = c["crimes"]
        g = geometry[code]
        rate = (crimes / pop * 100000) if pop else 0.0
        merged.append({
            "code": code, "name": g["name_fr"], "coords": g["coords"],
            "crimes": crimes, "pop": pop, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty brussels.json")
    if len(merged) != 19:
        print(f"WARNING: expected 19 communes, merged {len(merged)} — 'tutti i quartieri' requires all of them")

    weighted_avg = sum(z["crimes"] for z in merged) / sum(z["pop"] for z in merged) * 100000

    zones_out = []
    seen_slugs = set()
    for z in sorted(merged, key=lambda x: x["name"]):
        display_name = z["name"]
        slug = slugify(display_name)
        base_slug = slug
        n = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        seen_slugs.add(slug)

        tone = tone_for(z["rate"], weighted_avg)
        text = build_text(display_name, z["crimes"], z["pop"], z["rate"], tone, weighted_avg)
        query = f"{z['name']}, Brussels, Belgium"

        zones_out.append({
            "name": display_name,
            "slug": slug,
            "day": tone,
            "night": tone,
            "coords": z["coords"],
            "text": text,
            "query": query,
        })

    out = {
        "label": "Brussels, Belgium",
        "center": [50.8503, 4.3517],
        "zoom": 12,
        "dataNote": (
            "Neighbourhood shapes are the Brussels-Capital Region's real official "
            "19 communes, sourced from opendata.brussels.be's own boundary dataset. "
            "Like Berlin, Amsterdam, Prague, Oslo, Munich and Stockholm, Brussels' "
            "safety levels here come from a real official statistic — BISA (Brussels "
            "Institute for Statistics and Analysis), citing Federale Politie figures, "
            "and their own published 2025 total registered crime counts per commune, "
            "converted to a rate per 100,000 residents using Statbel's own 2025 "
            "population figures per commune — rather than a press-research approach. "
            "This rate is calculated against registered residents, not footfall, so "
            "busy central, station, or nightlife-heavy communes — especially the "
            "City of Brussels (the historic Pentagon centre, Gare Centrale, Gare du "
            "Nord) and Saint-Gilles (Gare du Midi, Brussels' Eurostar/international "
            "rail hub) — can read higher without that meaning elevated risk per "
            "visit — see each commune's page for the real numbers and this caveat "
            "in context, and the methodology page for full sourcing."
        ),
        "zones": zones_out,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    tones = {}
    for z in zones_out:
        tones[z["day"]] = tones.get(z["day"], 0) + 1
    print(f"Wrote {OUT_PATH} — {len(zones_out)} zones, city (pop-weighted) average rate {weighted_avg:.1f} per 100k")
    print(f"Tone distribution: {tones}")


if __name__ == "__main__":
    main()
