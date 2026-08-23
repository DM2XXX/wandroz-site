"""
Wandroz — build pipeline/data_zones/amsterdam.json from real official Dutch
data: Amsterdam's own wijk (district) boundaries plus CBS (Statistics
Netherlands) registered-crime and population figures.

SOURCES (all fetched live via the connected Chrome browser's fetch(), 23
Aug 2026 — this sandbox has no general outbound network access from
Bash/curl, see project conversation history)
  - Geometry: api.data.amsterdam.nl's WFS "gebieden" service, TYPENAMES=
    app:wijken, requested with SRSNAME=urn:ogc:def:crs:EPSG::4326 so the
    coordinates come back already reprojected to WGS84 (lon,lat) by the
    server — no manual RD (EPSG:28992) transform needed, unlike London's
    OSGB36 conversion. Filtered client-side to eind_geldigheid === null
    (currently-valid zone versions only) and simplified with a hand-written
    Douglas-Peucker (EPS=0.00015, ~15m at this latitude). 110 wijken, saved
    in 4 chunks under data_zones/amsterdam_raw/ (chunk0-3.json) to work
    around a discovered get_page_text truncation ceiling (~50KB even for
    "saved to file" output).
  - Crime counts: CBS table 47018NED ("Geregistreerde misdrijven; soort
    misdrijf, wijk, buurt, jaarcijfers"), hosted on dataderden.cbs.nl,
    filtered to SoortMisdrijf='0.0.0' (Totaal misdrijven — total registered
    crimes) and Perioden='2025JJ00' (2025, the latest full year available),
    RegioS starting with WK0363 (Amsterdam's CBS gemeente code). Saved as
    data_zones/amsterdam_raw/crime_totaal_2025.json, [[cbs_code, count],...].
  - Population: CBS table 86165NED ("Kerncijfers wijken en buurten 2025"),
    hosted on opendata.cbs.nl, field AantalInwoners_5, same WK0363 filter,
    same 2025 vintage as the crime data. Saved as
    data_zones/amsterdam_raw/population_2025.json, [[cbs_code, pop],...].

WHY WIJK LEVEL, NOT BUURT
  Amsterdam's WFS also publishes "buurten" (518 zones) — far finer than any
  other Wandroz city and too granular to be a useful travel-safety unit.
  "Wijken" (110 zones) is comparable in scale to Berlin (143) and Rome
  (155), and wijk names are the ones visitors and residents actually
  recognise (De Wallen, Jordaan, De Pijp, etc.).

METHODOLOGY — MIRRORS BERLIN, NOT MILAN/ROME
  Like Berlin, this is Wandroz's official-data layer, not Level 2 press
  research: a real CBS crime-rate figure per zone, computed here as total
  registered crimes per 100,000 residents (the same "Häufigkeitszahl"-style
  metric Polizei Berlin publishes directly; CBS's own table only gives raw
  counts, so the rate is computed here from CBS's own crime and population
  tables, both real official statistics, both 2025 vintage). Tone bucketing
  uses the SAME relative-to-city-average thresholds as Berlin/London:
  >=1.3x average -> red, <=0.8x average -> green, else yellow. The data has
  no day/night split, so day and night tones are set equal per zone,
  exactly as Berlin does, and disclosed as such.

A CAVEAT WORTH FLAGGING EXPLICITLY: a small number of wijken are very
  sparsely populated (harbour/industrial/rural-fringe areas like Driemond
  or the IJ-oevers reclamation zones — some under 500 residents, one at
  30), so a handful of recorded crimes there produces a very high rate per
  100,000 residents without that meaning the area is meaningfully
  dangerous to walk through. This mirrors Berlin's own HZ caveat about
  registered-resident normalisation vs. footfall, and is disclosed in the
  banner and in the text of any zone materially affected by it (small
  population flagged explicitly rather than silently producing a
  misleading "red").

OUTPUT
  pipeline/data_zones/amsterdam.json, matching the exact schema
  render_illustrative_city() in build_site.py consumes for Rome/Berlin:
  {"label","center","zoom","dataNote","zones":[{"name","slug","day","night",
  "coords","text","query"}]}. All 110 wijken included — none excluded.

USAGE
  python pipeline/build_amsterdam_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_zones", "amsterdam_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "amsterdam.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

# Below this population, a per-100k rate is numerically unstable (a
# handful of crimes swings it wildly) — such zones still get scored
# honestly from the real numbers, but their text flags the small
# population explicitly rather than presenting a bare, easily-misread
# rate.
SMALL_POP_THRESHOLD = 1000


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def load_geometry():
    """Merges the 4 chunk files back into one {cbs_code: {"naam":..,
    "coords": [[lat,lon],...]}} dict, swapping each WFS [lon,lat] pair to
    the [lat,lon] order build_site.py's other city files use (Berlin,
    Rome)."""
    all_wijken = []
    for i in range(4):
        path = os.path.join(RAW_DIR, f"chunk{i}.json")
        with open(path, encoding="utf-8") as f:
            all_wijken.extend(json.load(f))

    out = {}
    for w in all_wijken:
        code = w["cbs_code"].strip()
        rings_out = []
        # coords is [[[lon,lat], ...]] for a Polygon (single ring list) —
        # every chunk was built from Polygon features only (confirmed
        # during extraction: no MultiPolygon wijken in this WFS layer).
        for ring in w["coords"]:
            rings_out.append([[pt[1], pt[0]] for pt in ring])
        out[code] = {"naam": w["naam"], "coords": rings_out}
    return out


def load_pairs(fname):
    path = os.path.join(RAW_DIR, fname)
    with open(path, encoding="utf-8") as f:
        pairs = json.load(f)
    return {code.strip(): val for code, val in pairs}


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
        rel = f"roughly {ratio:.1f}× the citywide wijk average"
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
            f" This wijk has a small registered population ({pop_fmt} residents), so its rate per 100,000 "
            "residents can swing sharply from a handful of cases and should be read with that in mind rather "
            "than as a stable per-visit risk measure."
        )

    return (
        f"{name} is one of Amsterdam's 110 official wijken (CBS/gemeente boundaries). CBS (Statistics "
        f"Netherlands) recorded {crimes_fmt} registered crimes here in 2025 across a population of {pop_fmt} "
        f"residents — a rate of {rate_fmt} crimes per 100,000 residents, {rel}. This rate is calculated against "
        "registered residents, not footfall, so a busy shopping, transit or tourist area (like the city centre) "
        "can read higher without that meaning it is unusually risky to walk through, and a quiet residential "
        "wijk can show a low rate simply by having few offences relative to its population."
        f"{small_pop_note} "
        "This is Wandroz's official-data layer for Amsterdam — real CBS crime and population statistics, not a "
        "qualitative or press-based judgment — and the source data does not distinguish day from night, so both "
        "figures shown here are the same."
    )


def main():
    geometry = load_geometry()
    crimes = load_pairs("crime_totaal_2025.json")
    pop = load_pairs("population_2025.json")

    missing_crime = [c for c in geometry if c not in crimes]
    missing_pop = [c for c in geometry if c not in pop]
    if missing_crime:
        print(f"WARNING: {len(missing_crime)} wijken with no crime figure: {missing_crime}")
    if missing_pop:
        print(f"WARNING: {len(missing_pop)} wijken with no population figure: {missing_pop}")

    merged = []
    for code, geo in geometry.items():
        if code not in crimes or code not in pop:
            continue
        c = crimes[code]
        p = pop[code]
        rate = (c / p * 100000) if p else 0.0
        merged.append({
            "code": code, "name": geo["naam"], "coords": geo["coords"],
            "crimes": c, "pop": p, "rate": rate,
        })

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty amsterdam.json")

    city_avg = sum(z["rate"] for z in merged) / len(merged)

    name_counts = {}
    for z in merged:
        name_counts[z["name"]] = name_counts.get(z["name"], 0) + 1

    zones_out = []
    seen_slugs = set()
    # Sort by name for a stable, readable output order.
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
        query = f"{z['name']}, Amsterdam, Netherlands"

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
        "label": "Amsterdam, Netherlands",
        "center": [52.3676, 4.9041],
        "zoom": 11,
        "dataNote": (
            "Neighbourhood shapes are the Gemeente Amsterdam's real official \"wijk\" boundaries (110 zones, via "
            "api.data.amsterdam.nl). Like Berlin, Amsterdam's safety levels here come from a real official "
            "statistic — CBS (Statistics Netherlands) registered crimes per wijk for 2025, converted to a rate "
            "per 100,000 residents using CBS's own 2025 population figures per wijk — rather than Milan/Rome's "
            "press-research approach. This rate is calculated against registered residents, not footfall, so "
            "high-traffic tourist/shopping/transit areas (like the city centre) can read higher without that "
            "meaning elevated risk per visit, and a few very sparsely populated wijken (harbour/industrial "
            "fringe areas) can swing sharply from a handful of cases — see each zone's page for the real numbers "
            "and this caveat in context, and the methodology page for full sourcing."
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
