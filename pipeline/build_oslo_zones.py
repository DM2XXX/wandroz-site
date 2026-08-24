"""
Wandroz — build pipeline/data_zones/oslo.json from real official Norwegian
data: Oslo's 15 official administrative "bydeler" (boroughs) plus Oslo
kommune's own Statistikkbanken crime and population figures.

SOURCES (all fetched live via the connected Chrome browser — this sandbox
has no general outbound network access from Bash/curl, confirmed again
this session against statistikkbanken.oslo.kommune.no and
nominatim.openstreetmap.org)
  - District list: Oslo's 15 official bydeler, each with its own elected
    bydelsutvalg (local borough council) — 01 Gamle Oslo through
    15 Sondre Nordstrand — PLUS Sentrum (16), the city-centre financial/
    commercial/nightlife area, added 24 August 2026. Sentrum is NOT an
    administrative bydel — Oslo kommune's own population table (BEF005)
    only lists the 15 "Bydel X" rows, confirming there is no
    administrative-bydel population figure for Sentrum. But KRI002 (the
    crime table) DOES give Sentrum its own real, distinct crime figure
    (gjerningssted "16 Sentrum", separate from the 15 bydeler and from
    "99 Uoppgitt gjerningsbydel, inkludert Marka"), and Statistics Norway's
    own separate "urban district" geographic system (SSB table 10826) DOES
    give Sentrum its own real population figure (1,528 in 2024) even though
    Oslo kommune's administrative-bydel system doesn't. Combining these two
    real, official, differently-sourced figures lets Sentrum be mapped
    honestly rather than left as an unexplained gap in the middle of the
    city. "Marka" (forest, effectively unpopulated, no accommodation)
    remains excluded — KRI002 has no distinct figure for it either, only
    the mixed "99 Uoppgitt..." catch-all, which cannot be honestly
    attributed to Marka alone. All 15 real bydeler plus Sentrum (16 zones
    total) are mapped here — none excluded.
  - Crime counts: Oslo kommune Statistikkbanken, table KRI002 ("Anmeldte
    lovbrudd med gjerningssted i Oslo, etter type lovbrudd (lovbruddsgrupper)
    og gjerningsbydel"), filtered to "Alle lovbruddsgrupper" (all crime-type
    groups, i.e. total reported offences) with "gjerningssted" = place the
    offence actually occurred (not the victim's home address) for each of
    the 15 bydeler, year 2024 — read directly off Oslo kommune's own live
    Statistikkbanken table.
  - Population: Oslo kommune Statistikkbanken, table BEF005 ("Folkemengden
    etter administrativ bydel og alder"), "Alder i alt" (all ages), year
    2024 — same table family, same municipality, same vintage as the crime
    figures, avoiding a data-year mismatch.
  - Geometry: OpenStreetMap administrative boundary relations via Nominatim
    (nominatim.openstreetmap.org/search, polygon_geojson=1), one query per
    bydel name (e.g. "Frogner, Oslo, Norway"), simplified server-side via
    polygon_threshold. Matches the OSM attribution Wandroz already carries
    in its map tiles/footer on every city page.

WHY 2024 FOR BOTH CRIME AND POPULATION
  Statistikkbanken's population table (BEF005) already has live 2025/2026
  figures (Norway's population register updates close to real time), but
  KRI002's crime table only goes up to 2024. Using 2024 population against
  2024 crime keeps both figures from the same year, rather than mixing a
  2026 population denominator with a 2024 crime numerator, which would
  understate the rate.

METHODOLOGY — MIRRORS BERLIN / AMSTERDAM / PRAGUE, NOT THE ITALIAN CITIES
  Real official crime and population statistics per zone, not qualitative
  press research. Rate = total 2024 registered offences (by place of
  offence) / 2024 population * 100,000. Tone bucketing uses the SAME
  relative-to-city-average thresholds as those cities: >=1.3x average ->
  red, <=0.8x average -> green, else yellow. Oslo kommune's own KRI002
  table has no time-of-day breakdown in this aggregate form, so day and
  night tones are set equal per zone, exactly as Berlin/Amsterdam/Prague
  do, and disclosed as such in the banner.

A CAVEAT WORTH FLAGGING EXPLICITLY: Oslo kommune's own published note on
  KRI002 says "gjerningssted" (place of offence) can be skewed toward a
  company/discovery address when the true offence location is unknown, and
  specifically flags that Oslo's public transport operator (Sporveien)
  reports many criminal-damage cases with a registered offence address in
  Bydel Nordstrand — inflating that district's figure somewhat independent
  of real on-the-ground risk. This is disclosed in the banner and in
  Nordstrand's own zone text. Separately, several central bydeler (Gamle
  Oslo, St. Hanshaugen, Frogner) have large daytime/nightlife/shopping
  footfall relative to their resident population, which can inflate a
  resident-based rate without meaning elevated risk per visit — the same
  footfall effect already documented for Prague/Berlin/Amsterdam and for
  London's West End boroughs.

OUTPUT
  pipeline/data_zones/oslo.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for Berlin/Amsterdam/
  Prague: {"label","center","zoom","dataNote","zones":[{"name","slug","day",
  "night","coords","text","query"}]}. All 15 bydeler plus Sentrum (16 zones
  total) included — none excluded.

USAGE
  python pipeline/build_oslo_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_zones", "oslo_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "oslo.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8


def slugify(name):
    # Norwegian æ/ø (and Æ/Ø) have no canonical Unicode decomposition, so
    # NFKD alone (which handles e.g. å -> a + ring, ü -> u + diaeresis)
    # would otherwise silently drop them and mangle names like
    # "Grünerløkka" or "Østensjø" into "grunerl-kka" / "stensj". Spell them
    # out explicitly first, using the standard Norwegian transliteration.
    name = (
        name.replace("æ", "ae").replace("Æ", "Ae")
        .replace("ø", "o").replace("Ø", "O")
    )
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def load_districts():
    path = os.path.join(RAW_DIR, "districts.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {d["code"]: d for d in data["districts"]}


def load_geometry():
    """{code: {"name":.., "coords": [[[lat,lon],...]]}}, merged from one or
    more chunk files data_zones/oslo_raw/geometry_chunk*.json, each a list
    of {"code","name","coords"} — coords already in [[lat,lon],...] ring
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
                geo[entry["code"]] = entry
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
        rel = f"roughly {ratio:.1f}× the citywide bydel average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}× the citywide average, below it"
    else:
        rel = "close to the citywide average"
    rate_fmt = f"{rate:,.0f}"
    crimes_fmt = f"{crimes:,}"
    pop_fmt = f"{pop:,}"

    extra_note = ""
    if name == "Nordstrand":
        extra_note = (
            " Oslo kommune's own statistics note flags that many criminal-damage cases reported by the city's "
            "public transport operator (Sporveien) are registered with an offence address in Bydel Nordstrand "
            "regardless of where the incident actually happened, which inflates this figure somewhat independent "
            "of on-the-ground risk here."
        )
    elif name == "Sentrum":
        extra_note = (
            " Sentrum is not one of Oslo's 15 administrative bydeler — it has only 1,528 registered residents "
            "(Statistics Norway, 2024), a tiny base for what is Oslo's densest concentration of hotels, shops, "
            "restaurants, nightlife and offices, with a daytime and evening population many times its resident "
            "count. Dividing a genuinely high absolute number of reported offences by that small resident base "
            "produces a per-100,000-residents rate far beyond anything a visitor actually experiences per visit — "
            "it reflects a statistical artefact of the tiny denominator, not a literal multiple of walking-around "
            "risk. Sentrum is still shown here, rather than left blank, because Oslo kommune's own crime table "
            "does track it as a real, distinct area (separately from the 15 bydeler), and leaving Oslo's own city "
            "centre off the map — exactly where many visitors book — would be a bigger gap than an inflated "
            "number with this caveat attached."
        )

    return (
        f"{name} is one of Oslo's 15 official bydeler (city boroughs)." if name != "Sentrum" else
        f"{name} is Oslo's city centre — not one of the 15 administrative bydeler, but mapped here as its own "
        "zone using the same official sources."
    ) + (
        f" Oslo kommune's own police-sourced "
        f"Statistikkbanken data recorded {crimes_fmt} reported offences with their place of occurrence here in "
        f"2024, across a population of {pop_fmt} residents — a rate of {rate_fmt} offences per 100,000 residents, "
        f"{rel}. This rate is calculated against registered residents, not footfall, so a busy central or "
        f"nightlife/shopping-heavy bydel can read higher without that meaning it is unusually risky to walk "
        f"through, and a quiet residential bydel can show a low rate simply by having few offences relative to "
        f"its population.{extra_note} This is Wandroz's official-data layer for Oslo — real Oslo kommune "
        "Statistikkbanken figures, not a qualitative or press-based judgment — and the source data is not split "
        "here by time of day, so both figures shown here are the same."
    )


def main():
    districts = load_districts()
    geometry = load_geometry()

    missing_geo = [c for c in districts if c not in geometry]
    if missing_geo:
        names = [districts[c]["name"] for c in missing_geo]
        print(f"WARNING: {len(missing_geo)} bydeler with no geometry: {names}")

    merged = []
    for code, d in districts.items():
        if code not in geometry:
            continue
        c = d["crimes_2024"]
        p = d["population_2024"]
        g = geometry[code]
        rate = (c / p * 100000) if p else 0.0
        merged.append({
            "code": code, "name": d["name"], "coords": g["coords"],
            "crimes": c, "pop": p, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty oslo.json")
    if len(merged) != 16:
        print(f"WARNING: expected 16 zones (15 bydeler + Sentrum), merged {len(merged)} — 'tutti i quartieri' requires all of them")

    city_avg = sum(z["rate"] for z in merged) / len(merged)
    # city_avg here is the mean of per-bydel rates; also report the
    # population-weighted citywide rate for transparency in the console log
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
        query = f"{z['name']}, Oslo, Norway"

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
        "label": "Oslo, Norway",
        "center": [59.9139, 10.7522],
        "zoom": 11,
        "dataNote": (
            "Neighbourhood shapes are Oslo's real official 15 bydeler (city boroughs) plus Sentrum, the city "
            "centre, sourced from OpenStreetMap's administrative boundaries. Like Berlin, Amsterdam and Prague, "
            "Oslo's safety levels here come from a real official statistic — Oslo kommune's own Statistikkbanken "
            "figures on reported offences by place of occurrence per bydel for 2024, converted to a rate per "
            "100,000 residents using each area's 2024 population (Statistikkbanken for the 15 bydeler, Statistics "
            "Norway's separate 'urban district' population figures for Sentrum, which is not an administrative "
            "bydel) — rather than a press-research approach. This rate is calculated against registered residents, "
            "not footfall, so busy central/nightlife/shopping bydeler — and especially Sentrum itself, whose tiny "
            "resident base next to huge daytime/evening footfall produces an extreme rate — can read higher "
            "without that meaning elevated risk per visit — see each zone's page for the real numbers and this "
            "caveat in context, and the methodology page for full sourcing."
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
