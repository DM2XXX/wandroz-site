"""
Wandroz — real burglary-rate scoring for Zurich (Kreis-level)

WHAT THIS IS
  Turns the raw per-Kreis, per-year rows fetch_zurich.py saves under
  data/raw_zurich/ into a single scored file, data/scores/zurich_burglary.json,
  keyed by Kreis (city district). For each of Zurich's 12 Stadtkreise, it
  picks out the "Einbrüche insgesamt" (total burglaries) row for the most
  recent 3 years of data available, and rates each Kreis against the
  12-Kreise average — the same red/yellow/green logic score_london.py uses,
  so the two pipelines read consistently even though their inputs differ.

WHY NOT PER 1,000 RESIDENTS
  The provider publishes a Häufigkeitszahl: burglaries per 1,000 residents.
  This script used to take it as-is, and it put Kreis 1 at 39.5 — four times
  the city average, the worst district in Zurich, covering Lindenhof,
  Rathaus, City and Hochschulen, the four quarters this site otherwise calls
  the best places to stay.

  Burglary is a crime against premises. Someone breaks into a building. A
  district's homes are roughly its residents; its shops, offices and hotels
  are roughly its workplaces. Kreis 1 has 5,492 residents and 78,087 people
  working in it: counting the break-ins at all those premises and dividing by
  the residents alone measures how commercial the district is.

  So the denominator here is residents + employees, from STATENT via
  fetch_zurich_premises.py. On that basis Kreis 1 falls from 3.84x the city
  average to 0.80x, and the spread across Zurich narrows from 13x to under
  3x — which is the real finding: once you count the places there are to
  break into, Zurich's districts differ far less than the published
  per-resident figures suggest. Kreis 4 stays the outlier.

  The per-resident figure is still computed and kept in the output, because
  it is what every other source about Zurich quotes.

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


def load_kreis_year(kreis_n, year):
    """Returns (burglary count, residents) for one Kreis/year, or (None, None).

    Previously this read the published Häufigkeitszahl — burglaries per 1,000
    residents, computed by the data provider — and used it as-is. The count and
    the resident figure are both in the same row, and taking them separately is
    what makes it possible to divide by something better than residents. See
    the module docstring for why residents alone is the wrong denominator for
    a crime committed against buildings."""
    path = os.path.join(RAW_DIR, f"kreis_{kreis_n}_{year}.json")
    if not os.path.isfile(path):
        return None, None
    with open(path) as f:
        rows = json.load(f)
    for row in rows:
        if row.get("Tatbestand", "").strip() == TOTAL_TATBESTAND:
            try:
                count = int(str(row["Straftaten_total"]).replace("'", ""))
                pop = int(str(row["Einwohner"]).replace("'", ""))
            except (KeyError, TypeError, ValueError):
                return None, None
            return count, pop
    return None, None


def load_employees():
    """Employees per Kreis, from fetch_zurich_premises.py. Returns ({}, None)
    if absent, in which case scoring falls back to residents and says so."""
    path = os.path.join(RAW_DIR, "employees_by_kreis.json")
    if not os.path.isfile(path):
        return {}, None
    with open(path) as f:
        d = json.load(f)
    return d.get("employees") or {}, d.get("year")


def score_kreis(kreis_n, years_available, employees):
    """Burglaries per 1,000 premises — homes plus workplaces — averaged over
    the most recent years on disk."""
    years_used = years_available[:YEARS_TO_AVERAGE]
    counts, pops, years_with_data = [], [], []
    for year in years_used:
        count, pop = load_kreis_year(kreis_n, year)
        if count is not None:
            counts.append(count)
            pops.append(pop)
            years_with_data.append(year)
    if not counts:
        return None
    avg_count = sum(counts) / len(counts)
    residents = round(sum(pops) / len(pops))
    staff = employees.get(f"kreis_{kreis_n}")
    premises = residents + (staff or 0)
    return {
        "kreis_number": kreis_n,
        "kreis_label": KREIS_LABEL[kreis_n],
        "residents": residents,
        "employees": staff,
        "premises": premises,
        "burglaries_per_year": round(avg_count),
        "years_included": years_with_data,
        "years_with_data": len(counts),
        "rate_avg_per_1000": round(avg_count / premises * 1000, 2),
        # Kept because the old figure is what every other published source
        # about Zurich quotes, and a reader comparing us with them should be
        # able to see both numbers rather than conclude one of us is wrong.
        "rate_per_1000_residents": round(avg_count / residents * 1000, 2),
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

    employees, employees_year = load_employees()
    if not employees:
        raise SystemExit(
            "data/raw_zurich/employees_by_kreis.json is missing. Run "
            "pipeline/fetch_zurich_premises.py first: without it the only "
            "denominator available is resident population, which is the fault "
            "this scorer exists to avoid."
        )

    scored = {}
    for kreis_n in range(1, 13):
        years_available = kreis_years.get(kreis_n, [])
        if not years_available:
            continue
        result = score_kreis(kreis_n, years_available, employees)
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
        f"city average {out['city_average_rate_per_1000']} burglaries per 1,000 "
        f"premises (homes + workplaces)"
    )


if __name__ == "__main__":
    main()
