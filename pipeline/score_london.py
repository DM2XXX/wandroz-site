"""
Wandroz — London neighbourhood safety scoring (v0.2: day/night + footfall)

WHAT THIS DOES
  Reads raw street-level crime JSON (as returned by the UK Police API,
  https://data.police.uk/api/crimes-street/all-crime) for a set of London
  boroughs, splits it into a "day" score (property crime — shoplifting,
  burglary, vehicle/cycle theft, drugs) and a "night" score (violence,
  robbery, street theft, public order, anti-social behaviour), normalises
  each by an estimated workday/footfall population instead of plain
  resident population, and rates every borough against the average of the
  boroughs currently covered.

WHY DAY/NIGHT AND WHY WORKDAY POPULATION (READ THIS)
  The UK Police API does not carry a literal timestamp per incident, so the
  day/night split here is a CATEGORY-MIX PROXY, not time-stamped data: crime
  types that are overwhelmingly daytime (shoplifting, burglary, vehicle/
  cycle theft, drugs) feed the day score; crime types with a well-documented
  evening/night skew (violence, robbery, street theft, public order,
  anti-social behaviour) feed the night score. Categories that don't fit
  either pattern cleanly (criminal damage, weapons possession, "other
  theft"/"other crime") are left out of both scores rather than guessed at.

  Central, highly-visited boroughs (Westminster, Camden, Kensington &
  Chelsea especially) have far more people passing through on a typical day
  than officially live there — normalising purely by resident population
  makes them look artificially dangerous. WORKDAY_POPULATION below applies
  the ratio between resident and workday population that the ONS's 2011
  Census measured for each borough (the most recent official England &
  Wales workday-population release; no update has been published since) to
  each borough's up-to-date 2021 resident population. This is a deliberate
  approximation, not a fresh ONS statistic — see /methodology.html.

WHERE THE RAW DATA IN data/raw/*.json CAME FROM
  Pulled by fetch_london.py (real HTTP client, full monthly response) via a
  GitHub Actions run with normal outbound internet access — this sandbox's
  own network is restricted, so score_london.py only ever reads whatever
  fetch_london.py already wrote to data/raw/, it never fetches directly.

TONE THRESHOLD
  Each borough's day (and separately, night) rate is compared against the
  AVERAGE of that same rate across the boroughs currently on the automated
  pipeline (5 today) — not a true London-wide average, since only 5 of 33
  boroughs are covered so far. >=1.3x that average is flagged red ("higher
  caution"), <=0.8x is green ("relatively safer"), everything between is
  yellow ("average"). This mirrors the interactive map's existing red/
  yellow/green legend so a covered borough's page and its polygon on the
  map always agree.
"""

import glob
import json
import os
import re
from collections import Counter

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scores")

# 2021 UK Census resident population by borough (ONS). Approximate —
# should be refreshed against the latest ONS mid-year estimate in
# production rather than hardcoded.
BOROUGH_POPULATION = {
    "westminster": 204300,
    "camden": 210200,
    "islington": 215700,
    "kensington_chelsea": 143400,
    "lambeth": 317600,
}

BOROUGH_LABEL = {
    "westminster": "Westminster",
    "camden": "Camden",
    "islington": "Islington",
    "kensington_chelsea": "Kensington & Chelsea",
    "lambeth": "Lambeth",
}

# ONS "The workday population of England and Wales" (2011 Census release,
# published 2013-10-31) — resident vs workday population, ages 16-74:
#   Westminster            176,000 -> 644,000  (+267%)
#   Camden                 174,000 -> 337,000  (+94%)
#   Islington               165,000 -> 226,000  (+37%)
#   Kensington & Chelsea    126,000 -> 161,000  (+28%)
#   Lambeth: not in that release's named tables (its workday population is
#     below its resident population); the release's borough density table
#     gives resident 89/hectare vs workday 78/hectare, so the ratio 78/89
#     is used instead of an exact headcount.
# These ratios are applied to each borough's 2021 resident population
# above, since no newer official workday-population release exists.
WORKDAY_POPULATION_RATIO = {
    "westminster": 644 / 176,
    "camden": 337 / 174,
    "islington": 226 / 165,
    "kensington_chelsea": 161 / 126,
    "lambeth": 78 / 89,
}

WORKDAY_POPULATION = {
    name: round(BOROUGH_POPULATION[name] * ratio)
    for name, ratio in WORKDAY_POPULATION_RATIO.items()
}

# Rough severity weights (higher = more relevant to a traveller's sense of
# safety). Anti-social-behaviour is intentionally down-weighted since it is
# heavily over-represented in the API relative to violent/serious crime.
CATEGORY_WEIGHT = {
    "violent-crime": 3.0,  # data.police.uk id "violent-crime" = "Violence and sexual offences"
    "robbery": 3.0,
    "possession-of-weapons": 2.5,
    "burglary": 2.0,
    "vehicle-crime": 1.2,
    "theft-from-the-person": 2.0,
    "other-theft": 1.0,
    "bicycle-theft": 0.8,
    "criminal-damage-arson": 1.5,
    "drugs": 1.0,
    "public-order": 1.2,
    "anti-social-behaviour": 0.5,
    "shoplifting": 0.3,
    "other-crime": 1.0,
}
DEFAULT_WEIGHT = 1.0

# Category-mix day/night proxy — see module docstring. Categories not
# listed here (criminal-damage-arson, possession-of-weapons, other-theft,
# other-crime) intentionally count towards neither score.
DAY_CATEGORIES = {"shoplifting", "burglary", "vehicle-crime", "bicycle-theft", "drugs"}
NIGHT_CATEGORIES = {
    "violent-crime", "robbery", "theft-from-the-person",
    "public-order", "anti-social-behaviour",
}

RED_THRESHOLD = 1.3   # rate >= 1.3x the covered-boroughs average -> red
GREEN_THRESHOLD = 0.8  # rate <= 0.8x the covered-boroughs average -> green


def load_manifest():
    manifest_path = os.path.join(RAW_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def latest_raw_file(name):
    """Pick the most recent data/raw/{name}_{YYYY-MM}.json on disk for this
    borough, rather than a hardcoded month — fetch_london.py always writes
    whatever the API's current latest month is, which drifts over time."""
    pattern = os.path.join(RAW_DIR, f"{name}_*.json")
    candidates = []
    for path in glob.glob(pattern):
        m = re.search(r"_(\d{4}-\d{2})\.json$", os.path.basename(path))
        if m:
            candidates.append((m.group(1), path))
    if not candidates:
        return None, None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    month, path = candidates[0]
    return month, path


def load_borough(name):
    month, path = latest_raw_file(name)
    if path is None:
        raise FileNotFoundError(f"no raw data files found for borough '{name}'")
    with open(path) as f:
        return month, json.load(f)


def _weighted_rate(counts, category_set, workday_pop):
    weighted = sum(
        n * CATEGORY_WEIGHT.get(cat, DEFAULT_WEIGHT)
        for cat, n in counts.items()
        if cat in category_set
    )
    return round((weighted / workday_pop) * 1000, 4)


def score_borough(name, month, records, manifest):
    pop = BOROUGH_POPULATION[name]
    workday_pop = WORKDAY_POPULATION[name]
    counts = Counter(r.get("category", "unknown") for r in records)
    total = sum(counts.values())

    day_rate = _weighted_rate(counts, DAY_CATEGORIES, workday_pop)
    night_rate = _weighted_rate(counts, NIGHT_CATEGORIES, workday_pop)

    # Distinguish data pulled by fetch_london.py's full HTTP client from
    # the original v0.1 prototype files (truncated by a browser text
    # tool), and — since fetch_london.py v2 — distinguish a real polygon
    # boundary query from the old point+radius circle fallback.
    fetched_via = manifest.get(name, {}).get(month, {}).get("source", "")
    if "polygon boundary" in fetched_via:
        completeness = "full_polygon_boundary"
    elif fetched_via:
        completeness = "full_point_radius_fallback"
    else:
        completeness = "partial_sample_legacy"

    return {
        "borough": BOROUGH_LABEL[name],
        "slug": name,
        "population": pop,
        "workday_population": workday_pop,
        "workday_population_ratio": round(WORKDAY_POPULATION_RATIO[name], 3),
        "sample_record_count": total,
        "category_breakdown": dict(counts),
        "day_rate_per_1000": day_rate,
        "night_rate_per_1000": night_rate,
        "data_month": month,
        "data_completeness": completeness,
    }


def _tone(rate, average):
    if average <= 0:
        return "grey"
    ratio = rate / average
    if ratio >= RED_THRESHOLD:
        return "red"
    if ratio <= GREEN_THRESHOLD:
        return "green"
    return "yellow"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = load_manifest()
    results = []
    for name in BOROUGH_POPULATION:
        try:
            month, records = load_borough(name)
        except FileNotFoundError:
            continue
        results.append(score_borough(name, month, records, manifest))

    if results:
        avg_day = sum(r["day_rate_per_1000"] for r in results) / len(results)
        avg_night = sum(r["night_rate_per_1000"] for r in results) / len(results)
        for r in results:
            r["day_tone"] = _tone(r["day_rate_per_1000"], avg_day)
            r["night_tone"] = _tone(r["night_rate_per_1000"], avg_night)
            r["day_vs_covered_average"] = round(r["day_rate_per_1000"] / avg_day, 2) if avg_day else None
            r["night_vs_covered_average"] = round(r["night_rate_per_1000"] / avg_night, 2) if avg_night else None

        # Combined rank (average of day+night rate) purely for the
        # "relative rank X among boroughs covered" sentence on each page —
        # the day/night badges are what actually convey the ratings.
        results.sort(key=lambda r: (r["day_rate_per_1000"] + r["night_rate_per_1000"]) / 2)
        for i, r in enumerate(results, start=1):
            r["relative_rank"] = i

    out_path = os.path.join(OUT_DIR, "london.json")
    with open(out_path, "w") as f:
        json.dump({"city": "London", "boroughs": results}, f, indent=2)

    print(f"Wrote {out_path}")
    for r in results:
        print(
            f"  #{r['relative_rank']} {r['borough']:<22} "
            f"sample={r['sample_record_count']:>4}  "
            f"day={r['day_rate_per_1000']}/1000 ({r['day_tone']})  "
            f"night={r['night_rate_per_1000']}/1000 ({r['night_tone']})"
        )


if __name__ == "__main__":
    main()
