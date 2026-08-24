"""
Wandroz — build pipeline/data_zones/munich.json from real official Bavarian/
Munich city data: Munich's 25 official Stadtbezirke (city districts), each
with a real recorded-crime total, a real population figure, and a real
administrative boundary polygon.

SOURCES (all fetched live via the connected Chrome browser — this sandbox
has no general outbound network access from Bash/curl, reconfirmed this
session against stadt.muenchen.de and opendata.muenchen.de)
  - Crime counts: "Straftaten in den Stadtbezirken 2025" (Straftaten
    insgesamt = total recorded offences per Stadtbezirk, plus category
    breakdowns), published as a PDF table by Polizeipraesidium Muenchen /
    Statistisches Amt Muenchen —
    stadt.muenchen.de/dam/jcr:6291ac42-463d-4267-b436-c4b1a3313454/jt160904.pdf
    Extracted TWICE independently to cross-check accuracy before using it
    for a published rating: once via an automated page-fetch summary, and
    once from scratch via pdf.js running directly in the browser against
    the PDF's raw bytes (fetch + pdfjs getTextContent — Chrome's built-in
    PDF viewer failed to render this specific file, so pdf.js was loaded
    from a CDN and run against the fetched bytes instead). Both extractions
    agreed. Saved verbatim to pipeline/data_raw/munich_crime_2025.json —
    all 25 Stadtbezirke, "straftaten_insgesamt" is the total-offences
    column used here (PKS Schluesselzahl range 000000-700000, i.e. every
    recorded offence category). Blank PDF cells for "Straftaten gegen das
    Leben" (crimes against life) were confirmed to mean 0, not missing
    data, since every other column is populated for those rows.
  - Population: "Bevoelkerung in den Stadtbezirken am 31.12.2024",
    Statistisches Amt Muenchen, opendata.muenchen.de (CKAN CSV, Data
    Licence Germany Attribution 2.0), one row per Stadtbezirk. Saved to
    pipeline/data_raw/munich_population_2024.json; the 25 district
    populations sum exactly to the CSV's own published citywide total
    (1,603,776), confirming a clean, complete transcription.
  - Geometry: Munich's real official Stadtbezirke boundary polygons via
    WFS (GeoJSON), GeodatenService Muenchen, opendata.muenchen.de (Data
    Licence Germany Namensnennung 2.0). Source CRS is EPSG:25832 (ETRS89 /
    UTM zone 32N); reprojected to WGS84 (EPSG:4326) via proj4js running
    live in the browser (no pyproj/shapely available in this sandbox, and
    no network access from Bash to install them). Two districts —
    Untergiesing-Harlaching (18) and Thalkirchen-Obersendling-Forstenried-
    Fuerstenried-Solln (19) — were returned TWICE by the WFS service with
    identical attributes but different geometry (one tiny few-hundred-metre
    fragment, one full district body); the larger polygon (by point count)
    was kept for each and the tiny duplicate fragment dropped, since it is
    imperceptible at map scale and does not affect the crime/population
    figures either way. Saved to
    pipeline/data_raw/munich_boundaries_wgs84.geojson — reassembled and
    validated byte-for-byte after a multi-chunk browser-to-sandbox transfer
    (length-checked at every step; final JSON parses cleanly with all 25
    features present and a bounding box matching Munich's real extent).

WHY 2025 CRIME AGAINST 2024 POPULATION
  The crime PDF is titled "2025" (Polizeipraesidium Muenchen's most recent
  published Stadtbezirk breakdown) while the open-data population CSV's
  most recent vintage is 31.12.2024. This is a one-year mismatch in the
  same direction (population denominator slightly older than the crime
  numerator), which very slightly overstates the rate rather than
  understating it — Munich's population is essentially flat year over
  year, so the effect is minor, and it mirrors the same kind of small
  data-vintage gap already disclosed for other cities in this project
  (e.g. Zurich's burglary layer, which averages three years by design).

METHODOLOGY — MIRRORS BERLIN / AMSTERDAM / PRAGUE / OSLO, NOT THE ITALIAN
  CITIES' PRESS-RESEARCH APPROACH
  Real official crime and population statistics per zone. Rate = 2025
  total recorded offences / 2024 population * 100,000. Tone bucketing uses
  the SAME relative-to-citywide-average thresholds as those cities:
  >=1.3x average -> red, <=0.8x average -> green, else yellow. The source
  PDF has no time-of-day breakdown, so day and night tones are set equal
  per zone, exactly as Berlin/Amsterdam/Prague/Oslo do, and disclosed as
  such in the banner.

A CAVEAT WORTH FLAGGING EXPLICITLY: this rate is calculated against
  registered residents, not footfall. Altstadt-Lehel (the historic centre)
  and Ludwigsvorstadt-Isarvorstadt (which includes the Hauptbahnhof/
  Bahnhofsviertel area and the Gaertnerplatz/Glockenbach nightlife
  district) both show a rate several times the citywide average — a
  small resident base next to Munich's densest concentration of hotels,
  shops, station traffic, and nightlife, the same footfall effect already
  documented for London's West End, Prague, Amsterdam, Berlin and Oslo
  Sentrum. This is disclosed in the banner and in each affected zone's
  own text.

OUTPUT
  pipeline/data_zones/munich.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for Berlin/Amsterdam/
  Prague/Oslo: {"label","center","zoom","dataNote","zones":[{"name","slug",
  "day","night","coords","text","query"}]}. All 25 Stadtbezirke included —
  none excluded ("tutti i quartieri devono essere mappati nessuno escluso").

USAGE
  python pipeline/build_munich_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "munich.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

# High-footfall districts get an extra sentence in their zone text
# explaining the resident-vs-footfall effect, mirroring Oslo Sentrum /
# London West End / Prague centre.
FOOTFALL_NOTE = {
    "Altstadt-Lehel": (
        " Altstadt-Lehel is Munich's historic centre — Marienplatz, the "
        "main shopping streets, and a dense concentration of hotels and "
        "restaurants sit here on a comparatively small resident base, so "
        "its rate reflects huge daytime and evening footfall against few "
        "registered residents rather than elevated risk per visit."
    ),
    "Ludwigsvorstadt-Isarvorstadt": (
        " This district includes the area around Munich Hauptbahnhof "
        "(the main train station) and the Gaertnerplatz/Glockenbach "
        "nightlife district — both draw far more people through them "
        "than the district's resident count alone would suggest, which "
        "pushes its per-resident rate up without that meaning elevated "
        "risk per visit."
    ),
}


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def load_crime():
    path = os.path.join(RAW_DIR, "munich_crime_2025.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # columns: [stadtbezirk_nr, name, straftaten_insgesamt, ...]
    return {row[0]: {"name": row[1], "crimes": row[2]} for row in data["rows"]}


def load_population():
    path = os.path.join(RAW_DIR, "munich_population_2024.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {row[0]: row[2] for row in data["rows"]}


def load_geometry():
    path = os.path.join(RAW_DIR, "munich_boundaries_wgs84.geojson")
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    out = {}
    for feat in g["features"]:
        nummer = int(feat["properties"]["sb_nummer"])
        ring = feat["geometry"]["coordinates"][0]
        # GeoJSON order is [lon, lat]; Wandroz's zone JSON (Leaflet-facing)
        # uses [lat, lon], matching every other city's data_zones file.
        coords = [[lat, lon] for lon, lat in ring]
        out[nummer] = {"coords": [coords]}
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
        rel = f"roughly {ratio:.1f}x the citywide Stadtbezirk average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}x the citywide average, below it"
    else:
        rel = "close to the citywide average"
    rate_fmt = f"{rate:,.0f}"
    crimes_fmt = f"{crimes:,}"
    pop_fmt = f"{pop:,}"
    extra_note = FOOTFALL_NOTE.get(name, "")

    return (
        f"{name} is one of Munich's 25 official Stadtbezirke (city districts). "
        f"Polizeipraesidium Muenchen and the Statistisches Amt Muenchen recorded "
        f"{crimes_fmt} total offences here in 2025, across a population of {pop_fmt} "
        f"residents (31 December 2024) — a rate of {rate_fmt} offences per 100,000 "
        f"residents, {rel}. This rate is calculated against registered residents, not "
        f"footfall, so a busy central, station, or nightlife-heavy district can read "
        f"higher without that meaning it is unusually risky to walk through, and a "
        f"quiet residential district can show a low rate simply by having few "
        f"offences relative to its population.{extra_note} This is Wandroz's "
        "official-data layer for Munich — real Polizeipraesidium Muenchen / "
        "Statistisches Amt Muenchen figures, not a qualitative or press-based "
        "judgment — and the source data is not split here by time of day, so both "
        "figures shown here are the same."
    )


def main():
    crime = load_crime()
    population = load_population()
    geometry = load_geometry()

    missing_geo = [c for c in crime if c not in geometry]
    if missing_geo:
        names = [crime[c]["name"] for c in missing_geo]
        print(f"WARNING: {len(missing_geo)} Stadtbezirke with no geometry: {names}")
    missing_pop = [c for c in crime if c not in population]
    if missing_pop:
        names = [crime[c]["name"] for c in missing_pop]
        print(f"WARNING: {len(missing_pop)} Stadtbezirke with no population: {names}")

    merged = []
    for code, c in crime.items():
        if code not in geometry or code not in population:
            continue
        pop = population[code]
        crimes = c["crimes"]
        g = geometry[code]
        rate = (crimes / pop * 100000) if pop else 0.0
        merged.append({
            "code": code, "name": c["name"], "coords": g["coords"],
            "crimes": crimes, "pop": pop, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty munich.json")
    if len(merged) != 25:
        print(f"WARNING: expected 25 Stadtbezirke, merged {len(merged)} — 'tutti i quartieri' requires all of them")

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
        query = f"{z['name']}, Munich, Germany"

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
        "label": "Munich, Germany",
        "center": [48.1372, 11.5755],
        "zoom": 11,
        "dataNote": (
            "Neighbourhood shapes are Munich's real official 25 Stadtbezirke (city "
            "districts), sourced from GeodatenService Muenchen's own boundary WFS. "
            "Like Berlin, Amsterdam, Prague and Oslo, Munich's safety levels here come "
            "from a real official statistic — Polizeipraesidium Muenchen and the "
            "Statistisches Amt Muenchen's own published 2025 total-offence counts per "
            "Stadtbezirk, converted to a rate per 100,000 residents using each "
            "district's 31 December 2024 population — rather than a press-research "
            "approach. This rate is calculated against registered residents, not "
            "footfall, so busy central, station, or nightlife-heavy districts — "
            "especially Altstadt-Lehel (the historic centre) and Ludwigsvorstadt-"
            "Isarvorstadt (Hauptbahnhof and the Glockenbach nightlife district) — can "
            "read higher without that meaning elevated risk per visit — see each "
            "zone's page for the real numbers and this caveat in context, and the "
            "methodology page for full sourcing."
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
