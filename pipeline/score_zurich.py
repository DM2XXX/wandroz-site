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
    """Reads the saved raw rows for one Kreis/year and returns the official
    Häufigkeitszahl for the 'Einbrüche insgesamt' row, or None if that row
    isn't present (schema drift, missing data for that year, etc.)."""
    path = os.path.join(RAW_DIR, f"kreis_{kreis_n}_{year}.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        rows = json.load(f)
    for row in rows:
        if row.get("Tatbestand", "").strip() == TOTAL_TATBESTAND:
            return _parse_rate(row.get("Häufigkeitszahl"))
    return None


def score_kreis(kreis_n, years_available):
    years_used = years_available[:YEARS_TO_AVERAGE]
    rates = []
    years_with_data = []
    for year in years_used:
        rate = load_kreis_year_rate(kreis_n, year)
        if rate is not None:
            rates.append(rate)
            years_with_data.append(year)
    if not rates:
        return None
    avg_rate = sum(rates) / len(rates)
    return {
        "kreis_number": kreis_n,
        "kreis_label": KREIS_LABEL[kreis_n],
        "years_included": years_with_data,
        "years_with_data": len(rates),
        "rate_avg_per_1000": round(avg_rate, 2),
    }


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

    city_avg = sum(v["rate_avg_per_1000"] for v in scored.values()) / len(scored)
    for v in scored.values():
        ratio = (v["rate_avg_per_1000"] / city_avg) if city_avg else 1.0
        v["vs_city_average"] = round(ratio, 3)
        if ratio >= RED_THRESHOLD:
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
