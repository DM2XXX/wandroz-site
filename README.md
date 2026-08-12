# Wandroz — real-data site prototype (v0.1)

Static site + data pipeline prototype for the Wandroz neighbourhood-safety
project. Built to replace the Carrd placeholder with something that can
scale to many cities and update itself automatically.

## What's actually working right now

- `pipeline/score_london.py` — turns raw crime records into per-borough
  safety scores, normalised by resident population.
- `pipeline/build_site.py` + `pipeline/templates/` — renders those scores
  into a plain static HTML site (`dist/`), one page per borough, no JS
  framework or build step needed at deploy time.
- `pipeline/fetch_london.py` — pulls the FULL monthly crime response (via
  a real `requests` HTTP client, not a truncating browser tool) from the
  UK Police API for each borough centroid, and writes it to
  `data/raw/{borough}_{YYYY-MM}.json` + a `manifest.json` so re-runs don't
  re-fetch months already saved. Written 2026-08-12; not yet run for real
  (needs normal outbound network, which this sandbox doesn't have — see
  below), so its first live run should happen on GitHub Actions and be
  checked for sane record counts before trusting the output.
- `data/raw/*.json` — for the 5 pilot boroughs (Westminster, Camden,
  Islington, Kensington & Chelsea, Lambeth), currently still the original
  REAL but PARTIAL June 2026 sample (~170 records/borough, truncated by
  the browser tool used to pull it on 2026-08-10) until
  `fetch_london.py`'s first GitHub Actions run replaces it with the full
  month.
- `.github/workflows/refresh-data.yml` — the automation: a monthly GitHub
  Actions run that re-fetches data, recomputes scores, rebuilds the site,
  and commits the result (which triggers an auto-deploy on Vercel, since
  the repo is connected — see below).

## What's still a prototype, not production data

`fetch_london.py` queries a **point + ~1-mile-radius catchment** around
each borough's centre, not the exact administrative boundary polygon —
so incidents right at a borough's edges may be slightly over- or
under-counted relative to the true borough. The full month for that
catchment is real and complete (no truncation), just not a perfect
boundary match. Swapping in real borough polygons (ONS/GLA boundary data,
or the Police "neighbourhood boundary" API aggregated by borough) is
tracked as follow-up work on the project dashboard, not done yet — it
needs verifying against a live API response, which wasn't possible from
the sandbox this was authored in (see network note below).

Until `fetch_london.py` has actually run once on GitHub Actions and been
sanity-checked, `data/raw/*.json` is still the old truncated sample.
Scores computed from that old sample are directionally illustrative only
— don't publish them as real rankings.

The original project notes also mention a day/night split and a "workday
population" (footfall) adjustment for central boroughs from an earlier
analysis session. That method wasn't recoverable as code, and the UK
Police API doesn't include time-of-day — so this version normalises by
resident population only. Revisit if that refinement is worth rebuilding.

## Deployment status

Done, as of 2026-08-12:

1. Repo pushed to GitHub: github.com/DM2XXX/wandroz-site.
2. Connected to Vercel (Hobby/free plan), output directory `dist/`,
   auto-deploys on every push to `main`.
3. `wandroz.com` and `www.wandroz.com` point at Vercel via DNS on
   Namecheap, with a working auto-issued SSL certificate — the old
   `https://wandroz.com` cert problem (Carrd + Namecheap-redirect only
   worked over `http://`) is resolved and verified live.
4. `.github/workflows/refresh-data.yml` runs monthly (and can be
   triggered manually) to re-fetch data, recompute scores, rebuild the
   site, and push — which triggers the next Vercel auto-deploy — without
   Davide needing to do anything manually.

Still open: `fetch_london.py`'s first real run hasn't happened yet (see
above) — trigger the workflow manually on GitHub Actions and check the
log/commit before trusting the next scheduled run.

## Running locally

```
pip install -r pipeline/requirements.txt
python pipeline/fetch_london.py    # needs normal outbound network — will not work in a restricted sandbox
python pipeline/score_london.py
python pipeline/build_site.py
# open dist/index.html
```
