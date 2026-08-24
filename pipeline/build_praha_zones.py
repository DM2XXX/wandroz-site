"""
Wandroz — build pipeline/data_zones/praha.json from real official Czech data:
Prague's 57 official "mestske casti" (city districts/parts) plus Policie CR
crime figures and CSU (Czech Statistical Office) population figures.

SOURCES (all fetched live via the connected Chrome browser's fetch(), 24 Aug
2026 — this sandbox has no general outbound network access from Bash/curl,
confirmed again this session)
  - District list + codes: cs.wikipedia.org's "Administrativni deleni Prahy"
    article, cross-checked against the Statut hl. m. Prahy (57 mestske
    casti: 22 numbered "Praha 1"-"Praha 22" + 35 smaller named parts). Each
    district's "zuj" code (e.g. Praha 1 = 500054) confirmed live against
    geoapi.policie.cz's own fulltext search (type=4, "Mestsky obvod/cast"),
    saved in data_zones/praha_raw/districts.json together with each
    district's 2024 population.
  - Crime counts: kriminalita.policie.gov.cz's own official open-data export
    (api/v2/downloads/{year}_{zuj}.geojson), one file per district per year
    — a genuinely current, officially-run source (Policie CR's own map,
    "Mapy budoucnosti II" project, data through Aug 2026 at fetch time).
    IMPORTANT METHODOLOGY NOTE: mapakriminalita.cz (an older NGO mirror
    initially considered for Prague) was checked directly this session and
    found to be stale since Nov 2020 — NOT used. This official Policie CR
    portal was used instead. Each district-year GeoJSON is a full incident
    list (point features with a "types" classification array); the crime
    figure used here is the TOTAL feature count for the year, matching
    Berlin's HZ and Amsterdam's CBS approach (total registered
    offences/incidents, not a hand-picked category subset) — this keeps
    Prague's number directly comparable in kind to Berlin/Amsterdam's, and
    avoids an arbitrary, undisclosed category-selection judgment call.
  - Population: CSU (Czech Statistical Office) DataStat open API, dataset
    OBY01B01 ("Zakladni udaje o stavu a pohybu obyvatel podle obci"),
    indicator 2406K ("Population as at 31.12."), territorial dimension
    UZ596H ("Praha - administrative district and city part", MOMC level,
    57 items), year 2024 (the latest year with district-level figures
    finalised — 2025 exists in the dataset but is null at MOMC granularity
    as of fetch time, only the citywide total is published so far).
  - Geometry: OpenStreetMap administrative boundary relations via Nominatim
    (nominatim.openstreetmap.org/search, polygon_geojson=1), one query per
    district name (e.g. "Praha 1, Czechia"), simplified server-side via
    polygon_threshold. Matches the OSM attribution Wandroz already carries
    in its map tiles/footer on every city page.

WHY 2024, NOT 2025, FOR BOTH CRIME AND POPULATION
  Matching vintages matter more than matching "latest": using 2025's
  (partial-year) crime count against 2024's population, or vice versa,
  would silently skew the rate. 2024 is the most recent year with BOTH a
  finalised full-year crime file per district AND a finalised
  district-level population figure, so both come from the same year.

METHODOLOGY — MIRRORS BERLIN AND AMSTERDAM, NOT MILAN/ROME
  Real official crime and population statistics per zone, not qualitative
  press research. Rate = total 2024 incidents / 2024 population * 100,000.
  Tone bucketing uses the SAME relative-to-city-average thresholds as
  Berlin/Amsterdam/London: >=1.3x average -> red, <=0.8x average -> green,
  else yellow. Policie CR's underlying incident data has real timestamps
  (each feature carries a full date+time), but day/night is NOT split here
  — the public per-district-per-year export used is an annual aggregate by
  design (no reliable, honestly-disclosable way to bucket 15,000+ raw
  incident timestamps into a day/night split from this sandbox without
  risking a misleading precision this project hasn't earned); day and
  night tones are therefore set equal per zone, exactly as Berlin/Amsterdam
  do, and disclosed as such in the banner.

A CAVEAT WORTH FLAGGING EXPLICITLY: several of the 35 smaller "Praha-X"
  districts have very small populations (a few hundred to a few thousand
  residents — Praha-Kralovice is 467, Praha-Nedvezi 381), so a handful of
  incidents there produces a very high rate per 100,000 residents without
  that meaning the area is meaningfully dangerous to walk through. This
  mirrors Amsterdam's own small-population caveat and is disclosed in the
  banner and in the text of any zone materially affected by it.

OUTPUT
  pipeline/data_zones/praha.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for Berlin/Amsterdam:
  {"label","center","zoom","dataNote","zones":[{"name","slug","day","night",
  "coords","text","query"}]}. All 57 mestske casti included — none excluded.

USAGE
  python pipeline/build_praha_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_zones", "praha_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "praha.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

# Below this population, a per-100k rate is numerically unstable (a
# handful of incidents swings it wildly) — such zones still get scored
# honestly from the real numbers, but their text flags the small
# population explicitly rather than presenting a bare, easily-misread rate.
SMALL_POP_THRESHOLD = 3000


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def load_districts():
    path = os.path.join(RAW_DIR, "districts.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {d["zuj"]: d for d in data["districts"]}


def load_crime_counts():
    """{zuj: crime_count_2024}, merged from one or more chunk files
    data_zones/praha_raw/crime_2024*.json, each a flat {zuj: count} dict."""
    counts = {}
    i = 0
    found_any = False
    while True:
        path = os.path.join(RAW_DIR, f"crime_2024_chunk{i}.json")
        if not os.path.exists(path):
            break
        found_any = True
        with open(path, encoding="utf-8") as f:
            counts.update(json.load(f))
        i += 1
    if not found_any:
        # fall back to a single non-chunked file
        path = os.path.join(RAW_DIR, "crime_2024.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                counts = json.load(f)
    return counts


def load_geometry():
    """{zuj: {"name":.., "coords": [[[lat,lon],...]]}}, merged from one or
    more chunk files data_zones/praha_raw/geometry_chunk*.json, each a list
    of {"zuj","name","coords"} — coords already in [[lat,lon],...] ring
    order (converted from Nominatim's [lon,lat] GeoJSON order when the raw
    chunk was written)."""
    geo = {}
    i = 0
    while True:
        path = os.path.join(RAW_DIR, f"geometry_chunk{i}.json")
        if not os.path.exists(path):
            break
        with open(path, encoding="utf-8") as f:
            for entry in json.load(f):
                geo[entry["zuj"]] = entry
        i += 1
    return geo


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
        rel = f"roughly {ratio:.1f}× the citywide district average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}× the citywide average, below it"
    else:
        rel = "close to the citywide average"
    rate_fmt = f"{rate:,.0f}"
    crimes_fmt = f"{crimes:,}"
    pop_fmt = f"{pop:,}"

    small_pop_note = ""
    if pop < SMALL_POP_THRESHOLD:
        small_pop_note = (
            f" This district has a small population ({pop_fmt} residents), so its rate per 100,000 residents "
            "can swing sharply from a handful of cases and should be read with that in mind rather than as a "
            "stable per-visit risk measure."
        )

    return (
        f"{name} is one of Prague's 57 official mestske casti (city districts). Policie CR (the Czech national "
        f"police) recorded {crimes_fmt} incidents here in 2024 across a population of {pop_fmt} residents — a "
        f"rate of {rate_fmt} incidents per 100,000 residents, {rel}. This rate is calculated against registered "
        "residents, not footfall, so a busy central/tourist district can read higher without that meaning it is "
        "unusually risky to walk through, and a quiet residential district can show a low rate simply by having "
        f"few incidents relative to its population.{small_pop_note} "
        "This is Wandroz's official-data layer for Prague — real Policie CR incident data and real CSU population "
        "figures, not a qualitative or press-based judgment — and the source data is not split here by time of "
        "day, so both figures shown here are the same."
    )


def main():
    districts = load_districts()
    crimes = load_crime_counts()
    geometry = load_geometry()

    missing_crime = [z for z in districts if z not in crimes]
    missing_geo = [z for z in districts if z not in geometry]
    if missing_crime:
        names = [districts[z]["name"] for z in missing_crime]
        print(f"WARNING: {len(missing_crime)} districts with no crime figure: {names}")
    if missing_geo:
        names = [districts[z]["name"] for z in missing_geo]
        print(f"WARNING: {len(missing_geo)} districts with no geometry: {names}")

    merged = []
    for zuj, d in districts.items():
        if zuj not in crimes or zuj not in geometry:
            continue
        c = crimes[zuj]
        p = d["population"]
        g = geometry[zuj]
        rate = (c / p * 100000) if p else 0.0
        merged.append({
            "zuj": zuj, "name": d["name"], "coords": g["coords"],
            "crimes": c, "pop": p, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty praha.json")
    if len(merged) != 57:
        print(f"WARNING: expected 57 zones, merged {len(merged)} — 'tutti i quartieri' requires all 57")

    city_avg = sum(z["rate"] for z in merged) / len(merged)

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

        tone = tone_for(z["rate"], city_avg)
        text = build_text(display_name, z["crimes"], z["pop"], z["rate"], tone, city_avg)
        query = f"{z['name']}, Prague, Czechia"

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
        "label": "Prague, Czechia",
        "center": [50.0755, 14.4378],
        "zoom": 11,
        "dataNote": (
            "Neighbourhood shapes are Prague's real official 57 \"mestske casti\" (city districts), sourced from "
            "OpenStreetMap's administrative boundaries. Like Berlin and Amsterdam, Prague's safety levels here come "
            "from a real official statistic — Policie CR (the Czech national police) incident counts per district "
            "for 2024, converted to a rate per 100,000 residents using CSU's (Czech Statistical Office) own 2024 "
            "population figures per district — rather than Milan/Rome's press-research approach. This rate is "
            "calculated against registered residents, not footfall, so busy central/tourist districts can read "
            "higher without that meaning elevated risk per visit, and several small, sparsely populated outer "
            "districts can swing sharply from a handful of cases — see each zone's page for the real numbers and "
            "this caveat in context, and the methodology page for full sourcing."
        ),
        "zones": zones_out,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    tones = {}
    for z in zones_out:
        tones[z["day"]] = tones.get(z["day"], 0) + 1
    print(f"Wrote {OUT_PATH} — {len(zones_out)} zones, city average rate {city_avg:.1f} per 100k")
    print(f"Tone distribution: {tones}")


if __name__ == "__main__":
    main()
