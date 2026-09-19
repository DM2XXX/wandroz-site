"""
Wandroz — real burglary-rate scoring for Zurich (Kreis-level)

WHAT THIS IS
  Turns the raw per-Kreis, per-year rows fetch_zurich.py saves under
  data/raw_zurich/ into a single scored file, data/scores/zurich_burglary.json,
  keyed by Kreis (city district). For each of Zurich's 12 Stadtkreise, it
  picks out the "Einbrüche insgesamt" (total burglaries) row for the most
  recent 3 years of data available, averages the official
  Häufigkeitszahl (burglaries per 1,000 residents — computed by the data
  provider, used as-is), and rates each Kreis against the 12-Kreise
  average — the same red/yellow/green logic score_london.py uses, so the
  two pipelines read consistently even though their inputs differ.

WHAT THIS IS NOT
  This is NOT a day/night safety score like London's, and it does NOT
  replace Zurich's existing manual/illustrative day/night ratings for its
  34 Statistische Quartiere. It is one additional, narrow, real data
  point — burglaries only — attached at Kreis level (12 districts), which
  is coarser than the 34-Quartier map. build_site.py attaches each Kreis's
  score to every Quartier inside it (see QUARTIER_TO_KREIS there) and the
  neighbourhood template discloses both limits explicitly rather than
  presenting this as equivalent to London's per-borough pipeline.

  Averaging the most recent 3 years (rather than 3 months, like London)
  is a deliberate difference: this dataset is published annually, not
  monthly, so "3 months" has no meaning here — 3 years is the closest
  equivalent smoothing window for an annual series.

GRACEFUL DEGRADATION
  If data/raw_zurich/ doesn't exist yet or is empty (e.g. this script has
  never had fetch_zurich.py's output available, such as in this sandbox,
  which can't reach data.stadt-zuerich.ch — see fetch_zurich.py's
  docstring), this script writes an empty result
  ({"kreise": {}, "city_average_rate_per_1000": None}) rather than
  failing, and build_site.py treats an empty result as "no burglary data
  to show yet" rather than erroring.

USAGE
  python pipeline/score_zurich.py
"""

import json
import os
import re

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw_zurich")
OUT_DIR = os.path.join(BASE_DIR, "..", "data", "scores")
OUT_PATH = os.path.join(OUT_DIR, "zurich_burglary.json")

YEARS_TO_AVERAGE = 3
TOTAL_TATBESTAND = "Einbrüche insgesamt"

# Same relative thresholds as score_london.py, for consistency across the
# site rather than a Zurich-specific scale.
RED_THRESHOLD = 1.3
GREEN_THRESHOLD = 0.8

KREIS_LABEL = {n: f"Kreis {n}" for n in range(1, 13)}

FILE_PATTERN = re.compile(r"^kreis_(\d{1,2})_(\d{4})\.json$")


def discover_kreis_years():
    """Returns dict: kreis_number(int) -> years available on disk, sorted
    most-recent-first."""
    result = {}
    if not os.path.isdir(RAW_DIR):
        return result
    for fname in os.listdir(RAW_DIR):
        m = FILE_PATTERN.match(fname)
        if not m:
            continue
        kreis_n, year = int(m.group(1)), m.group(2)
        result.setdefault(kreis_n, []).append(year)
    for years in result.values():
        years.sort(reverse=True)
    return result


def _parse_rate(raw):
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "."))
    except ValueError:
        return None


def load_kreis_year_rate(kreis_n, year):
    """Reads the saved raw rows for one Kreis/year and returns
    (Häufigkeitszahl, Einwohner) for the 'Einbrüche insgesamt' row, or
    (None, None) if that row isn't present (schema drift, missing data for
    that year, etc.).

    The resident count was previously read and discarded. It matters: the
    Häufigkeitszahl is offences per 1,000 *residents*, and burglary counts
    include break-ins at shops, offices and hotels. Where residents are a
    small minority of the premises at risk, the ratio stops describing a
    person's risk and starts describing the district's commercial density."""
    path = os.path.join(RAW_DIR, f"kreis_{kreis_n}_{year}.json")
    if not os.path.isfile(path):
        return None, None
    with open(path) as f:
        rows = json.load(f)
    for row in rows:
        if row.get("Tatbestand", "").strip() == TOTAL_TATBESTAND:
            pop = row.get("Einwohner")
            try:
                pop = int(str(pop).replace("'", "").replace(" ", ""))
            except (TypeError, ValueError):
                pop = None
            return _parse_rate(row.get("Häufigkeitszahl")), pop
    return None, None


def score_kreis(kreis_n, years_available):
    years_used = years_available[:YEARS_TO_AVERAGE]
    rates = []
    pops = []
    years_with_data = []
    for year in years_used:
        rate, pop = load_kreis_year_rate(kreis_n, year)
        if rate is not None:
            rates.append(rate)
            years_with_data.append(year)
            if pop:
                pops.append(pop)
    if not rates:
        return None
    avg_rate = sum(rates) / len(rates)
    return {
        "kreis_number": kreis_n,
        "kreis_label": KREIS_LABEL[kreis_n],
        "residents": round(sum(pops) / len(pops)) if pops else None,
        "years_included": years_with_data,
        "years_with_data": len(rates),
        "rate_avg_per_1000": round(avg_rate, 2),
    }


def mark_incomparable(scored):
    """Flags districts where burglaries-per-1,000-residents is not a rate a
    reader can compare with other districts.

    Zurich's Kreis 1 is the old town and the central business district. It has
    about 5,500 residents and several thousand shops, offices and hotels, and
    the burglary count includes break-ins at all of them. Divided by a resident
    population that small, it produces 38.8 per 1,000 — 3.8 times the city
    average and by far the worst figure in Zurich — for the four quarters
    (Lindenhof, Rathaus, City, Hochschulen) that this site otherwise rates as
    the safest places in the city to stay. Both statements came from real data
    and they cannot both be read as risk to a person.

    The rule: a district whose resident population is under a third of the
    median district's is flagged. That threshold is not delicate. Zurich's
    districts run from 15,300 residents upward apart from Kreis 1 at 5,600, so
    anything between roughly 6,000 and 15,000 selects the same single district;
    a third of the median (about 11,900) sits in the middle of that gap. If a
    future boundary change puts another district in the same position, it gets
    the same treatment, which is why this is written as a rule.

    Flagged districts keep their published figure and lose only their colour.
    They stay in the city average: they are part of the city, the average is
    described to the reader as the average of the twelve districts, and
    quietly removing one to make the arithmetic prettier would be the same
    class of error in the other direction."""
    pops = [v["residents"] for v in scored.values() if v.get("residents")]
    if len(pops) < 3:
        return
    pops.sort()
    n = len(pops)
    median = pops[n // 2] if n % 2 else (pops[n // 2 - 1] + pops[n // 2]) / 2
    floor = median / 3.0
    for v in scored.values():
        pop = v.get("residents")
        if pop and pop < floor:
            v["rate_not_comparable"] = True
            # Written for a traveller, not for us. The first version explained
            # medians and denominators and told the reader nothing they wanted
            # to know. Three sentences: what the number is, why it looks bad,
            # why we are not using it.
            v["not_comparable_reason"] = (
                "This is Zurich's old town: only about %s people live here, but "
                "there are thousands of shops, offices and hotels. Break-ins at "
                "all of them are counted and then divided by those few "
                "residents, which is why the number looks alarming. It tracks "
                "how many businesses are packed in, not your risk — so we show "
                "it, but we don't rate the area on it." % f"{pop:,}"
            )


def write_empty(reason):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump({"kreise": {}, "city_average_rate_per_1000": None, "kreise_covered": 0, "kreise_total": 12}, f, indent=2)
    print(reason)


def main():
    kreis_years = discover_kreis_years()
    if not kreis_years:
        write_empty(
            "No Zurich raw data found on disk — nothing to score yet. (Expected in this sandbox, since "
            "fetch_zurich.py's output only exists after a real GitHub Actions run with real network access; "
            "wrote an empty result so build_site.py degrades gracefully.)"
        )
        return

    scored = {}
    for kreis_n in range(1, 13):
        years_available = kreis_years.get(kreis_n, [])
        if not years_available:
            continue
        result = score_kreis(kreis_n, years_available)
        if result:
            scored[f"kreis_{kreis_n}"] = result

    if not scored:
        write_empty("Found raw Zurich files, but none had a usable 'Einbrüche insgesamt' rate — wrote an empty result.")
        return

    mark_incomparable(scored)

    city_avg = sum(v["rate_avg_per_1000"] for v in scored.values()) / len(scored)
    for v in scored.values():
        ratio = (v["rate_avg_per_1000"] / city_avg) if city_avg else 1.0
        v["vs_city_average"] = round(ratio, 3)
        if v.get("rate_not_comparable"):
            # The figure is published and shown; only the ranking is withheld,
            # because a rank is a comparison and this one cannot be made.
            # Deliberately not "grey": grey means no data, and there is data.
            v["tone"] = "offscale"
        elif ratio >= RED_THRESHOLD:
            v["tone"] = "red"
        elif ratio <= GREEN_THRESHOLD:
            v["tone"] = "green"
        else:
            v["tone"] = "yellow"

    out = {
        "kreise": scored,
        "city_average_rate_per_1000": round(city_avg, 2),
        "kreise_covered": len(scored),
        "kreise_total": 12,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(
        f"Wrote {OUT_PATH} — {len(scored)}/12 Kreise scored, "
        f"city average {out['city_average_rate_per_1000']} burglaries/1,000 residents"
    )


if __name__ == "__main__":
    main()
