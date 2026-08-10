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
- `data/raw/*.json` — a REAL but PARTIAL sample of June 2026 London crime
  data for 5 boroughs (Westminster, Camden, Islington, Kensington &
  Chelsea, Lambeth), pulled live from the UK Police API
  (https://data.police.uk) on 2026-08-10.
- `.github/workflows/refresh-data.yml` — the intended automation: a
  monthly GitHub Actions run that re-fetches data, recomputes scores,
  rebuilds the site, and commits the result (which triggers an auto-deploy
  on Vercel/Netlify/Cloudflare Pages if the repo is connected to one).

## What's still a prototype, not production data

The sandbox this was built in has a restricted network policy and a
50,000-character cap on the browser-based page-text tool used to pull the
sample data, so each borough file holds only the first ~170 crime records
of June 2026, not the full month. Scores computed from this sample are
directionally illustrative only — do not publish them as real rankings.

`pipeline/fetch_london.py` (a proper, complete data-fetch script — either
via the bulk CSV export at https://data.police.uk/data/ or by paginating
the API per LSOA) still needs to be written. It should be built and tested
directly in GitHub Actions (or any environment with normal outbound
internet access), not in this sandbox.

The original project notes also mention a day/night split and a "workday
population" (footfall) adjustment for central boroughs from an earlier
analysis session. That method wasn't recoverable as code, and the UK
Police API doesn't include time-of-day — so this version normalises by
resident population only. Revisit if that refinement is worth rebuilding.

## How to actually deploy this (needs a decision from Davide)

1. Push this folder to a new GitHub repo (free).
2. Connect the repo to Vercel, Netlify, or Cloudflare Pages (free tier) —
   set the output directory to `dist/`.
3. Point `wandroz.com` at that host (custom domain + automatic free SSL —
   this also fixes the current `https://wandroz.com` SSL problem, since
   the current Carrd + Namecheap-redirect setup only works over `http://`).
4. GitHub Actions then keeps the data (and the site) refreshed monthly on
   its own, without needing Davide to do anything manually.

Account creation (GitHub, and whichever host) needs to be done by Davide
personally, the same way Carrd/Namecheap/Awin signups were handled.

## Running locally

```
pip install -r pipeline/requirements.txt
python pipeline/score_london.py
python pipeline/build_site.py
# open dist/index.html
```
