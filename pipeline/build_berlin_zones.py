"""
Wandroz — build pipeline/data_zones/berlin.json from the raw Berlin data
acquired via the Kriminalitätsatlas Berlin (kriminalitaetsatlas.berlin.de),
published by Polizei Berlin (LKA St 14) on the InstantAtlas platform.

WHY THIS EXISTS / HOW IT DIFFERS FROM THE EARLIER fetch_berlin.py ATTEMPT
  An earlier session (16-17 Aug 2026, see fetch_berlin.py / score_berlin.py
  docstrings) tried a different, narrower approach: live bicycle-theft and
  vehicle-crime CSVs from polizei-berlin.eu, area-normalized (not
  population-normalized, since no population-by-Bezirksregion source was
  found), and it got permanently stuck because the official LOR boundary
  WFS (gdi.berlin.de) was down for the entire research window, with no
  usable substitute (see score_berlin.py for the full trail of dead ends).

  This script instead uses the Kriminalitätsatlas Berlin directly — the
  city's own official interactive crime map, which bundles BOTH the
  boundary geometry AND a real overall crime-rate figure ("Straftaten
  -insgesamt-", i.e. total recorded offences) for the same 143
  Bezirksregionen, already population-normalized as HZ (Häufigkeitszahl —
  cases per 100,000 residents), a standard German police statistic. This
  sidesteps the WFS outage entirely and is a strictly better fit: real
  data AND real geometry from the same authoritative source, already
  normalized, no area/population workaround needed. fetch_berlin.py and
  score_berlin.py's area-normalized bicycle/vehicle-crime approach is left
  in place as dead code / historical record, not used by this build.

INPUTS (pipeline/data_zones/berlin_raw/, hand-acquired via Chrome browser
automation on 23 Aug 2026, since this sandbox has no route to
kriminalitaetsatlas.berlin.de — see project conversation history):
  - features.json: [{"id": 6-digit Bezirksregion code, "name", "bezirk"}]
    for all 143 zones, giving each zone its parent Bezirk (needed because
    two zones nationwide share the plain name "Heerstraße" — one in
    Charlottenburg-Wilmersdorf, one in Spandau).
  - hz2025_raw.txt: raw "<name> <HZ 2025> <Fälle 2025>" lines copied from
    the Kriminalitätsatlas's own "Straftaten -insgesamt-" table, German
    thousands-separator notation (e.g. "28.817" = 28817).
  - berlin_zones_geometry.json: [{"id", "name", "coords": [[[lat,lon],...]]}]
    — polygon rings per zone, decoded from the atlas's InstantAtlas
    UTM33N pixel-delta format and simplified with Douglas-Peucker at 12m
    tolerance (matching the Torino precedent), 7,532 points across 143
    zones.

OUTPUT
  pipeline/data_zones/berlin.json, matching the exact schema
  render_illustrative_city() in build_site.py already consumes for
  Torino/Zurigo/Milano/Roma: {"label","center","zoom","dataNote","zones":
  [{"name","slug","day","night","coords","text","query"}]}.

METHODOLOGY NOTES
  - Tone bucketing uses the SAME relative-to-city-average thresholds as
    score_london.py and score_berlin.py's own (unused) area-normalized
    attempt: >=1.3x average -> red, <=0.8x average -> yellow/green
    boundary at 0.8x, else yellow. This keeps Wandroz's tone semantics
    consistent across every city that has real quantitative data.
  - Berlin's HZ figure has NO day/night breakdown (it's an annual total),
    unlike London's category-mix day/night split. Rather than inventing a
    day/night difference that isn't in the source data, "day" and "night"
    are set to the SAME tone for every zone — an honest choice, disclosed
    in the banner text, not a bug.
  - HZ is defined by Polizei Berlin against REGISTERED RESIDENTS only, not
    the daytime/footfall population — so a zone with heavy commuter/
    tourist/shopping traffic (Mitte's Regierungsviertel, Alexanderplatz,
    Tempelhof-Schöneberg's Lietzenburger Straße/KaDeWe area) can show a
    very high HZ without that meaning "unusually dangerous for a visitor
    walking through" — it's diluted case-count-over-few-residents, not
    necessarily elevated risk per visit. This is disclosed in the banner
    and in each zone's text rather than left as a bare, easily
    misread number.
  - The Heerstraße/Heerstraße duplicate is disambiguated by appending the
    Bezirk to both the display name and the slug.
  - "text" per zone is intentionally DATA-DRIVEN, not invented local
    color: this project has done Level-2 press research for Milan/Rome and
    general-knowledge judgment for Torino/Zurigo, but has no genuine local
    knowledge or press research for 143 individual Berlin
    Bezirksregionen, so — following London's precedent for its real-data
    layer — the text states the real numbers and their meaning plainly
    rather than fabricating neighbourhood color that hasn't actually been
    researched.

USAGE
  python pipeline/build_berlin_zones.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "data_zones", "berlin_raw")
OUT_PATH = os.path.join(BASE_DIR, "data_zones", "berlin.json")

RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8


def slugify(name):
    """Same convention already used for milano.json/roma.json (NFKD
    strip-diacritics, lowercase, non-alphanumeric -> hyphen) plus an
    explicit ß->ss step, since German eszett isn't decomposed by NFKD the
    way ö/ü/ä are, and a raw ß would produce a non-ASCII URL segment."""
    name = name.replace("ß", "ss").replace("ẞ", "SS")
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-")


def parse_hz_line(line):
    """'<name, possibly with spaces/commas/slashes> <HZ> <Fälle>' — the
    last two whitespace-separated tokens are always the two numbers
    (German thousands-separator notation, e.g. '28.817' = 28817), the
    rest is the name."""
    parts = line.strip().split(" ")
    if len(parts) < 3:
        return None
    fälle_raw = parts[-1]
    hz_raw = parts[-2]
    name = " ".join(parts[:-2]).strip()
    hz = int(hz_raw.replace(".", ""))
    fälle = int(fälle_raw.replace(".", ""))
    return name, hz, fälle


def load_hz_by_name():
    """Returns {name: [(hz, fälle), ...]} — a list per name because
    'Heerstraße' appears twice with no district info in this file; the
    two occurrences are consumed in file order and paired with the two
    features.json entries for that name in THEIR file order (see module
    docstring — both lists come from iterating the same underlying LOR-
    ordered source, so file order is the best available disambiguator)."""
    path = os.path.join(RAW_DIR, "hz2025_raw.txt")
    by_name = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parsed = parse_hz_line(line)
            if not parsed:
                continue
            name, hz, fälle = parsed
            by_name.setdefault(name, []).append((hz, fälle))
    return by_name


def load_features():
    path = os.path.join(RAW_DIR, "features.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_geometry():
    path = os.path.join(RAW_DIR, "berlin_zones_geometry.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {z["id"]: z["coords"] for z in data}


def tone_for(hz, avg):
    ratio = hz / avg if avg else 1.0
    if ratio >= RED_THRESHOLD:
        return "red"
    if ratio <= GREEN_THRESHOLD:
        return "green"
    return "yellow"


def build_text(name, bezirk, hz, fälle, tone, avg):
    ratio = hz / avg if avg else 1.0
    if tone == "red":
        rel = f"roughly {ratio:.1f}× the citywide Bezirksregion average"
    elif tone == "green":
        rel = f"roughly {ratio:.1f}× the citywide average, below it"
    else:
        rel = "close to the citywide average"
    # Site copy is English throughout, so use English comma thousands
    # separators here even though the source table itself uses German
    # period notation (parsed away in parse_hz_line).
    hz_fmt = f"{hz:,}"
    fälle_fmt = f"{fälle:,}"
    return (
        f"{name} is one of Berlin's 143 official Bezirksregionen, part of the Bezirk of {bezirk}. "
        f"Polizei Berlin's 2025 Kriminalitätsatlas records a Häufigkeitszahl (HZ) of {hz_fmt} here — total "
        f"recorded offences per 100,000 registered residents — with {fälle_fmt} cases recorded for the year, "
        f"{rel}. "
        f"HZ is calculated against registered residents, not footfall, so a busy shopping, transit or tourist "
        f"area can show a higher HZ without that meaning it is unusually risky to walk through, and a quiet "
        f"residential zone can show a low HZ simply by having few offences relative to its population. This is "
        f"Wandroz's only rating layer for Berlin so far — a real official police statistic, not a qualitative "
        f"or press-based judgment — and the source data does not distinguish day from night, so both figures "
        f"shown here are the same."
    )


def main():
    features = load_features()
    geometry = load_geometry()
    hz_by_name = load_hz_by_name()

    # Consume the Heerstraße HZ pairs in features.json's own file order.
    hz_cursor = {name: 0 for name in hz_by_name}

    merged = []
    missing_geom = []
    missing_hz = []
    for feat in features:
        fid = feat["id"]
        name = feat["name"]
        bezirk = feat["bezirk"]

        coords = geometry.get(fid)
        if not coords:
            missing_geom.append((fid, name))
            continue

        occurrences = hz_by_name.get(name)
        if not occurrences:
            missing_hz.append((fid, name))
            continue
        idx = hz_cursor[name]
        if idx >= len(occurrences):
            idx = len(occurrences) - 1
        hz, fälle = occurrences[idx]
        hz_cursor[name] = idx + 1

        merged.append({
            "id": fid, "name": name, "bezirk": bezirk,
            "hz": hz, "fälle": fälle, "coords": coords,
        })

    if missing_geom:
        print(f"WARNING: {len(missing_geom)} zones with no geometry match: {missing_geom}")
    if missing_hz:
        print(f"WARNING: {len(missing_hz)} zones with no HZ match: {missing_hz}")

    if not merged:
        raise SystemExit("FATAL: no zones merged — aborting rather than writing an empty berlin.json")

    city_avg = sum(z["hz"] for z in merged) / len(merged)

    # Disambiguate duplicate display names (currently just "Heerstraße")
    # by appending the Bezirk, both for the shown name and the slug.
    name_counts = {}
    for z in merged:
        name_counts[z["name"]] = name_counts.get(z["name"], 0) + 1

    zones_out = []
    seen_slugs = set()
    for z in merged:
        display_name = z["name"]
        if name_counts[z["name"]] > 1:
            display_name = f"{z['name']} ({z['bezirk']})"
        slug = slugify(display_name)
        base_slug = slug
        n = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        seen_slugs.add(slug)

        tone = tone_for(z["hz"], city_avg)
        text = build_text(display_name, z["bezirk"], z["hz"], z["fälle"], tone, city_avg)
        query = f"{z['name']}, Berlin, Germany"

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
        "label": "Berlin, Germany",
        "center": [52.5200, 13.4050],
        "zoom": 10,
        "dataNote": (
            "Berlin: neighbourhood shapes are Polizei Berlin's real official \"Bezirksregion\" boundaries (143 "
            "zones, via the Kriminalitätsatlas Berlin / LKA St 14), the finest grain the atlas publishes. Unlike "
            "Milan and Rome, Berlin's safety levels here come from a real official police statistic — the 2025 "
            "Häufigkeitszahl (total recorded offences per 100,000 registered residents) for each zone, the same "
            "kind of open geolocated data London's automated pipeline uses, though here as a single annual figure "
            "rather than a live day/night feed. HZ is calculated against registered residents, not footfall, so "
            "high-traffic tourist/shopping/transit areas can read higher without that meaning elevated risk per "
            "visit — see each zone's page for the real numbers and this caveat in context, and the methodology "
            "page for full sourcing."
        ),
        "zones": zones_out,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    tones = {}
    for z in zones_out:
        tones[z["day"]] = tones.get(z["day"], 0) + 1
    print(f"Wrote {OUT_PATH} — {len(zones_out)} zones, city average HZ {city_avg:.1f}")
    print(f"Tone distribution: {tones}")


if __name__ == "__main__":
    main()
