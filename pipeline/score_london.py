"""
Wandroz — London neighbourhood safety scoring (v0.4: multi-month average)

WHAT THIS DOES
  Reads raw street-level crime JSON (as returned by the UK Police API,
  https://data.police.uk/api/crimes-street/all-crime) for every London
  borough except the City of London (policed by a separate force, not
  covered by this dataset), splits it into a "day" score (property crime —
  shoplifting, burglary, vehicle/cycle theft, drugs) and a "night" score
  (violence, robbery, street theft, public order, anti-social behaviour),
  normalises each by an estimated workday/footfall population instead of
  plain resident population, and rates every borough against the average of
  the boroughs currently covered.

  Each score is now an AVERAGE over the most recent MONTHS_TO_AVERAGE
  months of data on disk (up to 3), not a single month. fetch_london.py
  keeps a rolling window of that many months fetched per borough; this
  script averages per-category counts across whatever's actually
  available for a borough (fewer than MONTHS_TO_AVERAGE is handled
  gracefully — e.g. right after a borough is first added). A single
  unusual month swings the average less this way, which was flagged as a
  known limitation in /methodology.html until this change.

WHY DAY/NIGHT AND WHY WORKDAY POPULATION (READ THIS)
  The UK Police API does not carry a literal timestamp per incident, so the
  day/night split here is a CATEGORY-MIX PROXY, not time-stamped data: crime
  types that are overwhelmingly daytime (shoplifting, burglary, vehicle/
  cycle theft, drugs) feed the day score; crime types with a well-documented
  evening/night skew (violence, robbery, street theft, public order,
  anti-social behaviour) feed the night score. Categories that don't fit
  either pattern cleanly (criminal damage, weapons possession, "other
  theft"/"other crime") are left out of both scores rather than guessed at.

  Central, highly-visited boroughs have far more people passing through on
  a typical day than officially live there — normalising purely by resident
  population makes them look artificially dangerous. WORKDAY_POPULATION
  below applies a resident-vs-workday ratio to each borough's up-to-date
  2021 resident population. This is a deliberate approximation, not a fresh
  ONS statistic — see /methodology.html. Three tiers of confidence apply,
  recorded per borough as WORKDAY_RATIO_SOURCE (also surfaced in each
  borough's JSON as "workday_population_source" so the site can disclose it
  honestly rather than presenting every ratio as equally solid):

    measured_headcount — the ONS's 2011 Census "workday population" release
      (the most recent official England & Wales workday-population release;
      no update has been published since) named this borough directly in
      its resident/workday headcount tables (ages 16-74). Most reliable
      tier available.
    measured_density   — the same 2011 release didn't name this borough in
      its headcount tables, but its "workday population density" table
      (persons/hectare) covers it, so the resident/workday DENSITY ratio is
      used as a proxy for the population ratio instead.
    no_data            — this borough appears in neither table of the 2011
      release. Rather than inventing a number, the ratio defaults to 1.0
      (i.e. no correction applied — workday population = resident
      population), and the site says so explicitly. This is a real
      limitation, not a hidden guess.

WHERE THE RAW DATA IN data/raw/*.json CAME FROM
  Pulled by fetch_london.py (real HTTP client, full monthly response) via a
  GitHub Actions run with normal outbound internet access — this sandbox's
  own network is restricted, so score_london.py only ever reads whatever
  fetch_london.py already wrote to data/raw/, it never fetches directly.

TONE THRESHOLD
  Each borough's day (and separately, night) rate is compared against the
  AVERAGE of that same rate across every borough currently on the automated
  pipeline — which, as of the 32-borough expansion, is effectively all of
  London except the City of London. >=1.3x that average is flagged red
  ("higher caution"), <=0.8x is green ("relatively safer"), everything
  between is yellow ("average"). This mirrors the interactive map's
  existing red/yellow/green legend so a covered borough's page and its
  polygon on the map always agree.
"""

import glob
import json
import os
import re
from collections import Counter

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scores")

# How many of the most recent months on disk to average per borough.
# fetch_london.py keeps this many months' raw files around per borough
# (its own MONTHS_TO_FETCH); this should be <= that, since averaging can
# only use what's actually been fetched.
MONTHS_TO_AVERAGE = 3

# 2021 UK Census resident population by borough (ONS). Every borough except
# the City of London (separate police force, out of scope for this
# dataset). Westminster/Camden/Islington/Kensington & Chelsea/Lambeth are
# from the original disclosure-controlled release used since the project's
# first London pass; the other 27 are from ONS's "Census 2021 area
# changes" comparison tool (ons.gov.uk/visualisations/censusareachanges),
# which rounds to the nearest 100 — differences against other ONS 2021
# rounding passes are under 0.15% and immaterial for a per-capita score.
BOROUGH_POPULATION = {
    "westminster": 204300,
    "camden": 210200,
    "islington": 215700,
    "kensington_chelsea": 143400,
    "lambeth": 317600,
    "barking_dagenham": 218900,
    "barnet": 389300,
    "bexley": 246500,
    "brent": 339800,
    "bromley": 330000,
    "croydon": 390700,
    "ealing": 367100,
    "enfield": 330000,
    "greenwich": 289100,
    "hackney": 259100,
    "hammersmith_fulham": 183200,
    "haringey": 264200,
    "harrow": 261200,
    "havering": 262100,
    "hillingdon": 305900,
    "hounslow": 288200,
    "kingston_upon_thames": 168100,
    "lewisham": 300600,
    "merton": 215200,
    "newham": 351000,
    "redbridge": 310300,
    "richmond_upon_thames": 195300,
    "southwark": 307600,
    "sutton": 209600,
    "tower_hamlets": 310300,
    "waltham_forest": 278400,
    "wandsworth": 327500,
}

BOROUGH_LABEL = {
    "westminster": "Westminster",
    "camden": "Camden",
    "islington": "Islington",
    "kensington_chelsea": "Kensington & Chelsea",
    "lambeth": "Lambeth",
    "barking_dagenham": "Barking and Dagenham",
    "barnet": "Barnet",
    "bexley": "Bexley",
    "brent": "Brent",
    "bromley": "Bromley",
    "croydon": "Croydon",
    "ealing": "Ealing",
    "enfield": "Enfield",
    "greenwich": "Greenwich",
    "hackney": "Hackney",
    "hammersmith_fulham": "Hammersmith and Fulham",
    "haringey": "Haringey",
    "harrow": "Harrow",
    "havering": "Havering",
    "hillingdon": "Hillingdon",
    "hounslow": "Hounslow",
    "kingston_upon_thames": "Kingston upon Thames",
    "lewisham": "Lewisham",
    "merton": "Merton",
    "newham": "Newham",
    "redbridge": "Redbridge",
    "richmond_upon_thames": "Richmond upon Thames",
    "southwark": "Southwark",
    "sutton": "Sutton",
    "tower_hamlets": "Tower Hamlets",
    "waltham_forest": "Waltham Forest",
    "wandsworth": "Wandsworth",
}

# ONS "The workday population of England and Wales" (2011 Census release,
# published 2013-10-31), ages 16-74. See the module docstring for what the
# three source tiers (measured_headcount / measured_density / no_data)
# mean. Headcount ratios (workday / resident):
#   Westminster            176,000 -> 644,000
#   Camden                 174,000 -> 337,000
#   Islington               165,000 -> 226,000
#   Kensington & Chelsea    126,000 -> 161,000
#   Croydon                 263,000 -> 210,000
#   Hillingdon              200,000 -> 235,000
#   Hammersmith & Fulham    146,000 -> 170,000
#   Southwark               225,000 -> 261,000
#   Tower Hamlets           197,000 -> 310,000
#   Lewisham                206,000 -> 149,000
#   Wandsworth              244,000 -> 183,000
#   Redbridge               200,000 -> 154,000
#   Harrow                  175,000 -> 135,000
#   Haringey                193,000 -> 150,000
#   Waltham Forest          191,000 -> 149,000
#   Bexley                  166,000 -> 130,000
#   Merton                  150,000 -> 120,000
# Density ratios (workday persons/hectare / resident persons/hectare) used
# as a proxy where the release only published density, not a headcount:
#   Lambeth      78 / 89
#   Hackney      90 / 98
#   Ealing       40 / 46
#   Brent        47 / 54
#   Newham       55 / 63
# The remaining boroughs (Barking & Dagenham, Barnet, Bromley, Enfield,
# Greenwich, Havering, Hounslow, Kingston upon Thames, Richmond upon
# Thames, Sutton) appear in neither table of the 2011 release — see
# WORKDAY_RATIO_SOURCE, ratio defaults to 1.0 (no correction) for these.
WORKDAY_POPULATION_RATIO = {
    "westminster": 644 / 176,
    "camden": 337 / 174,
    "islington": 226 / 165,
    "kensington_chelsea": 161 / 126,
    "lambeth": 78 / 89,
    "croydon": 210 / 263,
    "hillingdon": 235 / 200,
    "hammersmith_fulham": 170 / 146,
    "southwark": 261 / 225,
    "tower_hamlets": 310 / 197,
    "lewisham": 149 / 206,
    "wandsworth": 183 / 244,
    "redbridge": 154 / 200,
    "harrow": 135 / 175,
    "haringey": 150 / 193,
    "waltham_forest": 149 / 191,
    "bexley": 130 / 166,
    "merton": 120 / 150,
    "hackney": 90 / 98,
    "ealing": 40 / 46,
    "brent": 47 / 54,
    "newham": 55 / 63,
}
DEFAULT_WORKDAY_RATIO = 1.0  # applied when no 2011 release data exists at all

WORKDAY_RATIO_SOURCE = {
    "westminster": "measured_headcount",
    "camden": "measured_headcount",
    "islington": "measured_headcount",
    "kensington_chelsea": "measured_headcount",
    "croydon": "measured_headcount",
    "hillingdon": "measured_headcount",
    "hammersmith_fulham": "measured_headcount",
    "southwark": "measured_headcount",
    "tower_hamlets": "measured_headcount",
    "lewisham": "measured_headcount",
    "wandsworth": "measured_headcount",
    "redbridge": "measured_headcount",
    "harrow": "measured_headcount",
    "haringey": "measured_headcount",
    "waltham_forest": "measured_headcount",
    "bexley": "measured_headcount",
    "merton": "measured_headcount",
    "lambeth": "measured_density",
    "hackney": "measured_density",
    "ealing": "measured_density",
    "brent": "measured_density",
    "newham": "measured_density",
    "barking_dagenham": "no_data",
    "barnet": "no_data",
    "bromley": "no_data",
    "enfield": "no_data",
    "greenwich": "no_data",
    "havering": "no_data",
    "hounslow": "no_data",
    "kingston_upon_thames": "no_data",
    "richmond_upon_thames": "no_data",
    "sutton": "no_data",
}

WORKDAY_POPULATION = {
    name: round(BOROUGH_POPULATION[name] * WORKDAY_POPULATION_RATIO.get(name, DEFAULT_WORKDAY_RATIO))
    for name in BOROUGH_POPULATION
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


def latest_raw_files(name, n=MONTHS_TO_AVERAGE):
    """Pick the n most recent data/raw/{name}_{YYYY-MM}.json files on disk
    for this borough (most-recent-first), rather than hardcoded months —
    fetch_london.py always writes whatever months the API currently
    publishes, which drifts over time. Returns fewer than n pairs if fewer
    months have been fetched yet (e.g. a borough just added)."""
    pattern = os.path.join(RAW_DIR, f"{name}_*.json")
    candidates = []
    for path in glob.glob(pattern):
        m = re.search(r"_(\d{4}-\d{2})\.json$", os.path.basename(path))
        if m:
            candidates.append((m.group(1), path))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[:n]


def load_borough_window(name, n=MONTHS_TO_AVERAGE):
    """Returns (months, counts_per_month): months is a most-recent-first
    list of 'YYYY-MM' strings actually found on disk (up to n of them);
    counts_per_month is a parallel list of Counter(category -> incident
    count) for each of those months."""
    files = latest_raw_files(name, n)
    if not files:
        raise FileNotFoundError(f"no raw data files found for borough '{name}'")
    months = []
    counts_per_month = []
    for month, path in files:
        with open(path) as f:
            records = json.load(f)
        months.append(month)
        counts_per_month.append(Counter(r.get("category", "unknown") for r in records))
    return months, counts_per_month


def _weighted_rate(counts, category_set, workday_pop):
    weighted = sum(
        n * CATEGORY_WEIGHT.get(cat, DEFAULT_WEIGHT)
        for cat, n in counts.items()
        if cat in category_set
    )
    return round((weighted / workday_pop) * 1000, 4)


# Completeness tiers ranked worst-to-best so a multi-month window can
# report its WEAKEST tier honestly (e.g. if one of three months had to
# fall back to a point/radius circle, the whole window says so) rather
# than only reflecting the most recent month.
_COMPLETENESS_RANK = {"partial_sample_legacy": 0, "full_point_radius_fallback": 1, "full_polygon_boundary": 2}


def _month_completeness(manifest, name, month):
    fetched_via = manifest.get(name, {}).get(month, {}).get("source", "")
    if "polygon boundary" in fetched_via:
        return "full_polygon_boundary"
    elif fetched_via:
        return "full_point_radius_fallback"
    else:
        return "partial_sample_legacy"


def score_borough(name, months, counts_per_month, manifest):
    pop = BOROUGH_POPULATION[name]
    workday_pop = WORKDAY_POPULATION[name]
    n_months = len(months)

    total_counts = Counter()
    for c in counts_per_month:
        total_counts.update(c)
    total_records = sum(total_counts.values())
    avg_counts = {cat: n / n_months for cat, n in total_counts.items()}

    day_rate = _weighted_rate(avg_counts, DAY_CATEGORIES, workday_pop)
    night_rate = _weighted_rate(avg_counts, NIGHT_CATEGORIES, workday_pop)

    # Distinguish data pulled by fetch_london.py's full HTTP client from
    # the original v0.1 prototype files (truncated by a browser text
    # tool), and distinguish a real polygon boundary query from the old
    # point+radius circle fallback — taking the WEAKEST tier found across
    # the whole window, not just the latest month.
    completeness = min(
        (_month_completeness(manifest, name, m) for m in months),
        key=lambda t: _COMPLETENESS_RANK[t],
    )

    return {
        "borough": BOROUGH_LABEL[name],
        "slug": name,
        "population": pop,
        "workday_population": workday_pop,
        "workday_population_ratio": round(WORKDAY_POPULATION_RATIO.get(name, DEFAULT_WORKDAY_RATIO), 3),
        "workday_population_source": WORKDAY_RATIO_SOURCE.get(name, "no_data"),
        "sample_record_count": total_records,
        "sample_record_count_avg_per_month": round(total_records / n_months, 1),
        "category_breakdown": dict(total_counts),
        "day_rate_per_1000": day_rate,
        "night_rate_per_1000": night_rate,
        "months_included": months,
        "data_month": months[0],
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
    skipped = []
    for name in BOROUGH_POPULATION:
        try:
            months, counts_per_month = load_borough_window(name)
        except FileNotFoundError:
            skipped.append(name)
            continue
        results.append(score_borough(name, months, counts_per_month, manifest))

    if results:
        avg_day = sum(r["day_rate_per_1000"] for r in results) / len(results)
        avg_night = sum(r["night_rate_per_1000"] for r in results) / len(results)
        for r in results:
            r["day_tone"] = _tone(r["day_rate_per_1000"], avg_day)
            r["night_tone"] = _tone(r["night_rate_per_1000"], avg_night)
            r["day_vs_covered_average"] = round(r["day_rate_per_1000"] / avg_day, 2) if avg_day else None
            r["night_vs_covered_average"] = round(r["night_rate_per_1000"] / avg_night, 2) if avg_night else None
            r["covered_count"] = len(results)
            r["total_boroughs"] = len(BOROUGH_POPULATION)

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
    if skipped:
        print(f"  skipped (no raw data yet): {', '.join(skipped)}")
    for r in results:
        print(
            f"  #{r['relative_rank']} {r['borough']:<24} "
            f"sample={r['sample_record_count']:>4}  "
            f"day={r['day_rate_per_1000']}/1000 ({r['day_tone']})  "
            f"night={r['night_rate_per_1000']}/1000 ({r['night_tone']})"
        )


if __name__ == "__main__":
    main()
