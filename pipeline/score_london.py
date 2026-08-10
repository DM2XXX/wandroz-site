"""
Wandroz — London neighbourhood safety scoring (v0.1 prototype)

WHAT THIS DOES
  Reads raw street-level crime JSON (as returned by the UK Police API,
  https://data.police.uk/api/crimes-street/all-crime) for a set of London
  boroughs, aggregates crime counts by category, normalises by resident
  population, and produces a simple per-borough safety score.

WHERE THE RAW DATA IN data/raw/*.json CAME FROM (READ THIS)
  These files were pulled through a browser navigation to the Police API
  for June 2026, one file per borough centroid (~1 mile radius). The text
  extraction tool used to grab the page truncated each response at ~50k
  characters, so each file holds roughly the first ~170 crime records of
  that borough's actual monthly total (which is larger). This is a REAL
  sample, not fabricated, but it is NOT the complete month for any borough.
  Treat scores computed from it as a working demo of the pipeline logic,
  not as accurate published safety scores yet.

WHAT A PRODUCTION RUN NEEDS TO DO DIFFERENTLY
  This sandbox's network is restricted (it can only reach a handful of
  allow-listed domains directly), so a full, unrestricted monthly pull
  has to run somewhere with normal outbound internet access — e.g. a
  GitHub Actions workflow (see .github/workflows/refresh-data.yml) or the
  hosting platform's own serverless cron. There, this same scoring logic
  should be fed the FULL monthly dataset (either via the same all-crime
  API paginated by street/LSOA, or via the bulk CSV export at
  https://data.police.uk/data/) instead of the truncated browser sample.

METHODOLOGY NOTE
  A previous analysis session for this project reportedly split scores by
  day/night and used workday (footfall) population instead of resident
  population for some central boroughs. The UK Police API does not include
  time-of-day, and that refinement's exact method wasn't recoverable in
  this session (no reusable code was found). This v0.1 uses residential
  population normalisation only; day/night and footfall-based refinements
  are open follow-up work (tracked in the project dashboard).
"""

import json
import os
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

# Rough severity weights (higher = more relevant to a traveller's sense of
# safety). Anti-social-behaviour is intentionally down-weighted since it is
# heavily over-represented in the API relative to violent/serious crime.
CATEGORY_WEIGHT = {
    "violence-and-sexual-offences": 3.0,
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


def load_borough(name):
    path = os.path.join(RAW_DIR, f"{name}_2026-06.json")
    with open(path) as f:
        return json.load(f)


def score_borough(name, records):
    pop = BOROUGH_POPULATION[name]
    counts = Counter(r.get("category", "unknown") for r in records)
    total = sum(counts.values())

    weighted = sum(
        n * CATEGORY_WEIGHT.get(cat, DEFAULT_WEIGHT) for cat, n in counts.items()
    )
    # per-1000-residents rate, in this SAMPLE window (not a full month)
    rate_per_1000 = (total / pop) * 1000
    weighted_rate_per_1000 = (weighted / pop) * 1000

    return {
        "borough": BOROUGH_LABEL[name],
        "slug": name,
        "population": pop,
        "sample_record_count": total,
        "category_breakdown": dict(counts),
        "rate_per_1000_sample": round(rate_per_1000, 3),
        "weighted_rate_per_1000_sample": round(weighted_rate_per_1000, 3),
        "data_month": "2026-06",
        "data_completeness": "partial_sample",
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    for name in BOROUGH_POPULATION:
        try:
            records = load_borough(name)
        except FileNotFoundError:
            continue
        results.append(score_borough(name, records))

    # Rank: lower weighted rate = safer. This is purely relative across
    # the boroughs we have data for, not an absolute scale.
    results.sort(key=lambda r: r["weighted_rate_per_1000_sample"])
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
            f"weighted_rate/1000={r['weighted_rate_per_1000_sample']}"
        )


if __name__ == "__main__":
    main()
