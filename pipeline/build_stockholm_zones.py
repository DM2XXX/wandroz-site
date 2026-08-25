"""
Wandroz — build pipeline/data_zones/stockholm.json from real official Swedish
data: Stockholm's 11 official stadsdelsnamnder (city district committees),
each with a real recorded-crime total, a real population figure, and a real
administrative boundary polygon.

SOURCES (all fetched live via the connected Chrome browser — this sandbox
has no general outbound network access from Bash/curl)
  - Crime counts: Bra (Brottsforebyggande radet, Sweden's national crime-
    prevention council), live query tool at statistik.bra.se/solwebb
    (NOT kriminalstatistik.bra.se, which does not resolve — the wrong
    hostname is likely why an earlier research pass on this project
    couldn't load the tool). Queried "Totalt antal brott" (total reported
    offences), year 2025, for exactly the 11 currently-active "Stadsdels-
    omrade X (Sthlm)" areas in the tool's own region list — a long tail of
    older, discontinued district schemes (marked "upphorde [date]" in the
    same list, most recently a 2024-01-01 reorganisation) were excluded.
    Saved to pipeline/data_raw/stockholm_crime_2025.json.
  - Population: Stockholms stad's own "Befolkningsoversikt Arsrapport 2024"
    (published 2025-06-23), Table 2, population per stadsdelsomrade as of
    31 December 2024. The report's citywide total (995,574) includes a
    "Restomrade" row of 3,637 residents registered without a known
    physical/district address; the 11 named districts sum to 991,937
    (995,574 - 3,637), confirmed by direct cross-check before use. Saved
    to pipeline/data_raw/stockholm_population_2024.json.
  - Geometry: Stockholms stad's official "Stadskartans Stadsdelsnamnder
    2023 (11 st)" boundary shapefile (Stadsbyggnadskontoret, CC0), via
    dataportalen.stockholm.se. Parsed client-side in the browser with
    shpjs (which also reprojected SWEREF99 TM to WGS84 using the
    shapefile's own .prj) — no pyproj/shapely/GDAL available in this
    sandbox. Saved to pipeline/data_raw/stockholm_boundaries_2023.json;
    reassembled and validated byte-for-byte after a 3-chunk browser-to-
    sandbox transfer (all 11 rings closed, i.e. first point == last point).

A NOTE ON WHAT "11 STADSDELSOMRADEN" MEANS HERE: Brа's own police-district
  naming initially looked like it might be a separate scheme from
  Stockholm's real administrative divisions, but Stockholms stad's own
  website (start.stockholm) confirms the city currently has exactly these
  same 11 stadsdelsnamnder as its real, current, single official
  administrative division (following a reform that reduced the count from
  more districts, evidenced by "upphorde 2024-01-01" entries for the old
  Norrmalm/Ostermalm/Rinkeby-Kista/Spanga-Tensta names in Bra's district
  list). All three sources — crime, population, geometry — line up on the
  same 11 real districts, none excluded.

WHY 2025 CRIME AGAINST 2024 POPULATION
  Bra's crime query supports 2025 as the latest full year; Stockholms
  stad's own population report's latest vintage is 31 December 2024 (its
  2025 edition was not yet available). Same one-year mismatch pattern
  already disclosed for Munich (2025 crime vs 2024 population) elsewhere
  on this site — population is comparatively stable year over year, so the
  effect on the rate is minor.

METHODOLOGY — MIRRORS BERLIN / AMSTERDAM / PRAGUE / OSLO / MUNICH
  Real official crime and population statistics per zone. Rate = 2025
  total reported offences / 2024 population * 100,000. Tone bucketing uses
  the SAME relative-to-citywide-average thresholds as those cities:
  >=1.3x average -> red, <=0.8x average -> green, else yellow. Bra's
  district-level totals have no time-of-day breakdown, so day and night
  tones are set equal per zone, exactly as the other official-data cities
  do, and disclosed as such in the banner.

A CAVEAT WORTH FLAGGING EXPLICITLY: this rate is calculated against
  registered residents, not footfall. Norra innerstaden (Stockholm's dense
  inner-city core, covering the former Norrmalm/Ostermalm — Centralstationen,
  Sergels torg, the main shopping streets around Drottninggatan/Hamngatan)
  and Sodermalm (a major nightlife and restaurant district) both show a
  rate meaningfully above the citywide average — the same footfall effect
  already documented for London's West End, Prague, Amsterdam, Berlin,
  Oslo's Sentrum and Munich's Altstadt-Lehel. This is disclosed in the
  banner and in each affected zone's own text.

OUTPUT
  pipeline/data_zones/stockholm.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for the other
  official-data cities: {"label","center","zoom","dataNote","zones":[
  {"name","slug","day","night","coords","text","query"}]}. All 11
  stadsdelsnamnder included — none excluded ("tutti i quartieri devono
  essere mappati nessuno escluso").

USAGE
  python pipeline/build_stockholm_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "stockholm.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

# The source shapefile's "Namn" property uses Swedish genitive forms for
# some districts. Map each raw geometry name to the canonical base-form
# name used by the crime/population sources.
GEOMETRY_NAME_MAP = {
    "Kungsholmens": "Kungsholmen",
    "Farsta": "Farsta",
    "Bromma": "Bromma",
    "Hässelby-Vällingby": "Hässelby-Vällingby",
    "Skärholmens": "Skärholmen",
    "Skarpnäcks": "Skarpnäck",
    "Södermalms": "Södermalm",
    "Enskede-Årsta-Vantörs": "Enskede-Årsta-Vantör",
    "Hägersten-Älvsjö": "Hägersten-Älvsjö",
    "Järva": "Järva",
    "Norra innerstadens": "Norra innerstaden",
}

# High-footfall districts get an extra sentence in their zone text
# explaining the resident-vs-footfall effect, mirroring Oslo Sentrum /
# Munich Altstadt-Lehel / London West End.
FOOTFALL_NOTE = {
    "Norra innerstaden": (
        " Norra innerstaden covers Stockholm's dense inner-city core — "
        "Centralstationen (the main train station), Sergels torg, and the "
        "main shopping streets around Drottninggatan and Hamngatan all sit "
        "here on a comparatively small resident base, so its rate reflects "
        "huge daytime and evening footfall against few registered "
        "residents rather than elevated risk per visit."
    ),
    "Södermalm": (
        " Sodermalm is one of Stockholm's most visited nightlife and "
        "restaurant districts (SoFo, Hornstull, Slussen) — it draws far "
        "more people through it than its resident count alone would "
        "suggest, which pushes its per-resident rate up without that "
        "meaning elevated risk per visit."
    ),
}


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def norm(name):
    """Normalize Bra's ' - ' hyphen spacing to match the canonical form."""
    return name.replace(" - ", "-").replace(" – ", "-").strip()


def load_crime():
    path = os.path.join(RAW_DIR, "stockholm_crime_2025.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {norm(row["name"]): row["crimes_2025"] for row in data["rows"]}


def load_population():
    path = os.path.join(RAW_DIR, "stockholm_population_2024.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {norm(row["name"]): row["population_2024"] for row in data["rows"]}


def load_geometry():
    path = os.path.join(RAW_DIR, "stockholm_boundaries_2023.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for row in data["rows"]:
        raw_name = row["name"]
        canonical = GEOMETRY_NAME_MAP.get(raw_name, raw_name)
        # coords_ring0 is already [lat, lon] pairs (converted at capture time).
        out[canonical] = {"coords": [row["coords_ring0"]]}
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
        rel = f"roughly {ratio:.1f}x the citywide district average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}x the citywide average, below it"
    else:
        rel = "close to the citywide average"
    rate_fmt = f"{rate:,.0f}"
    crimes_fmt = f"{crimes:,}"
    pop_fmt = f"{pop:,}"
    extra_note = FOOTFALL_NOTE.get(name, "")

    return (
        f"{name} is one of Stockholm's 11 official stadsdelsnamnder (city "
        f"district committees). Bra (Brottsforebyggande radet), Sweden's "
        f"national crime-prevention council, recorded {crimes_fmt} total "
        f"reported offences here in 2025, across a population of {pop_fmt} "
        f"residents (Stockholms stad, 31 December 2024) — a rate of "
        f"{rate_fmt} offences per 100,000 residents, {rel}. This rate is "
        f"calculated against registered residents, not footfall, so a busy "
        f"central, station, or nightlife-heavy district can read higher "
        f"without that meaning it is unusually risky to walk through, and "
        f"a quiet residential district can show a low rate simply by "
        f"having few offences relative to its population.{extra_note} "
        "This is Wandroz's official-data layer for Stockholm — real Bra / "
        "Stockholms stad figures, not a qualitative or press-based "
        "judgment — and the source data is not split here by time of day, "
        "so both figures shown here are the same."
    )


def main():
    crime = load_crime()
    population = load_population()
    geometry = load_geometry()

    all_names = set(crime) | set(population) | set(geometry)
    missing_geo = [n for n in all_names if n not in geometry]
    missing_pop = [n for n in all_names if n not in population]
    missing_crime = [n for n in all_names if n not in crime]
    if missing_geo:
        print(f"WARNING: no geometry for: {missing_geo}")
    if missing_pop:
        print(f"WARNING: no population for: {missing_pop}")
    if missing_crime:
        print(f"WARNING: no crime data for: {missing_crime}")

    merged = []
    for name in sorted(all_names):
        if name not in geometry or name not in population or name not in crime:
            continue
        pop = population[name]
        crimes = crime[name]
        g = geometry[name]
        rate = (crimes / pop * 100000) if pop else 0.0
        merged.append({
            "name": name, "coords": g["coords"],
            "crimes": crimes, "pop": pop, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty stockholm.json")
    if len(merged) != 11:
        print(f"WARNING: expected 11 stadsdelsnamnder, merged {len(merged)} — 'tutti i quartieri' requires all of them")

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
        query = f"{z['name']}, Stockholm, Sweden"

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
        "label": "Stockholm, Sweden",
        "center": [59.3293, 18.0686],
        "zoom": 11,
        "dataNote": (
            "Neighbourhood shapes are Stockholm's real official 11 "
            "stadsdelsnamnder (city district committees), sourced from "
            "Stockholms stad's own 'Stadskartans Stadsdelsnamnder 2023' "
            "boundary dataset. Like Berlin, Amsterdam, Prague, Oslo and "
            "Munich, Stockholm's safety levels here come from a real "
            "official statistic — Bra (Brottsforebyggande radet)'s own "
            "2025 total reported-offence counts per district, converted "
            "to a rate per 100,000 residents using each district's 31 "
            "December 2024 population (Stockholms stad) — rather than a "
            "press-research approach. This rate is calculated against "
            "registered residents, not footfall, so busy central, "
            "station, or nightlife-heavy districts — especially Norra "
            "innerstaden (the inner-city core around Centralstationen) "
            "and Sodermalm (nightlife and restaurants) — can read higher "
            "without that meaning elevated risk per visit — see each "
            "zone's page for the real numbers and this caveat in context, "
            "and the methodology page for full sourcing."
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
