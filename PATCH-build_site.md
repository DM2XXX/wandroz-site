# `pipeline/build_site.py` — required edits

Line numbers are against `main` @ `ad139e4` (1,905 lines). If you apply the pending
country-grouping work first, they shift by ~99; the anchors are quoted so you can
find them either way.

Six edits. Two are one-liners, four wire Florence in as an ordinary city.

---

## 1 — Canonical correction email  *(one line)*

**Line 41:**
```python
CORRECTION_EMAIL = "dadenuoto@gmail.com"
```
**becomes**
```python
CORRECTION_EMAIL = "hellowandroz@gmail.com"
```

Nothing else changes. The architecture is already single-source: this constant is
passed as `correction_email=` at lines 607 and 1832, and both consuming templates
(`borough.html:79`, `neighbourhood.html:93`) render `{{ correction_email }}`. **No
template hardcodes an address** — audited across all six templates, zero literal
`@gmail.com` strings.

Effect of the change: 1,035 non-Florence live pages currently showing
`hellowandroz@` keep showing it after a rebuild instead of reverting, and the 101
pages currently leaking the personal address stop. `qa_full_site.py` enforces this
permanently — any address that is not `BS.CORRECTION_EMAIL` is a hard failure.

---

## 2 — Florence methodology tier

**Line 132**, after the `"krakow"` entry in `CITY_METHODOLOGY`:
```python
    "krakow": {"tier": RESEARCH_BASED},
    "firenze": {"tier": RESEARCH_BASED},
```

**Verified against content, not the homepage blurb**, as you asked:

| Evidence | Florence | Rome (already `RESEARCH_BASED`) |
|---|---|---|
| Zones with an explicit `Sources checked:` line | **74 / 74** | 0 (different convention) |
| Zones citing a named outlet | **21** | 0 |
| Zones declaring no coverage found, plainly | 43 | 39 |
| Boundaries | Official Comune di Firenze *Aree elementari 2021* | Official Roma Capitale *Zone Urbanistiche* |

Named sources found in Florence's zone texts: La Nazione, FirenzeToday, Corriere
Toscano, Controradio, Il Sole 24 Ore, GoNews, Comune di Firenze press releases, and
Fondazione Caponnetto's six-month microcrime reports. Its own hub banner already
states *"Wandroz's Level 2 approach: genuine current local/national press research
per zone, honestly disclosed as press-based rather than official crime statistics"*
— the same sentence pattern Rome's banner uses.

**Florence is at least as well sourced as cities already carrying this tier.** The
classification is justified by the content. Nothing here is fabricated.

---

## 3 — Florence UI, banner and neighbourhood note

Insert next to the other city blocks (e.g. after `VENEZIA_*`, ~line 1400). Follows
the existing pattern exactly.

```python
FIRENZE_UI = dict(TORINO_UI)
FIRENZE_UI.update({
    "page_title": "Is my Florence neighbourhood safe? — Wandroz",
    "page_description": (
        "Interactive map of Florence's 74 official Aree elementari (real Comune di "
        "Firenze statistical zones) with day/night safety levels based on current "
        "local press research."
    ),
    "page_h1": "Florence neighbourhoods",
    "neigh_title": "Is {name} in Florence safe? | Wandroz",
})

FIRENZE_BANNER = (
    "Neighbourhood shapes are the real official 'Aree elementari 2021' (elementary "
    "statistical zones) published by Comune di Firenze's own Planning/Control/Statistics "
    "Service — 74 zones covering the whole comune, the finest official government-published "
    "neighbourhood-equivalent unit for the city. Like Milan, Rome, Turin, Barcelona, Madrid, "
    "Vienna, Lisbon, Paris, Athens, Venice and Dublin, Florence's safety levels are Wandroz's "
    "Level 2 approach: genuine current local/national press research per zone, honestly "
    "disclosed as press-based rather than official crime statistics — Italy has no open, "
    "geolocated neighbourhood-level crime dataset. Where no specific news coverage was found "
    "for a zone, that is stated plainly rather than assumed either way — most of Florence's 74 "
    "zones are ordinary residential or suburban areas with nothing notable in local coverage. "
    "All 74 official Aree elementari are mapped, none excluded. See the methodology page for "
    "details and sources."
)

FIRENZE_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Florence: genuine current local/national "
    "press research for this specific Area elementare (not blind guessing, not fabricated "
    "crime statistics), honestly disclosed as press-based rather than official data — Italy "
    "has no open, geolocated neighbourhood-level crime dataset. See the methodology page for "
    "what was checked and how this differs from London's automated official-data pipeline."
)
```

`FIRENZE_BANNER` is the live hub's own notice text, carried over verbatim — the
same string `build_firenze_zones.py` writes into `firenze.json` as `dataNote`. It
is Florence's honesty disclosure, so it must not be paraphrased in migration.

---

## 4 — Render Florence in `main()`

**After line 1888** (`sitemap_urls.extend(venezia_urls)`):
```python
    firenze_urls = render_illustrative_city(
        "firenze", "firenze", FIRENZE_UI, EN_TONE_BADGE,
        FIRENZE_BANNER, FIRENZE_NEIGH_NOTE, flat=True,
    )
    sitemap_urls.extend(firenze_urls)
```

`flat=True` is required: Florence's live URLs are `/firenze/{slug}.html`. Rendering
it nested would move 74 indexed URLs and need redirects. **Verified** the recovered
slugs reproduce the current paths exactly — 74 source slugs vs 74 files in
`dist/firenze/`, zero difference either way.

Add `Firenze ({len(firenze_urls)})` to the summary `print` at line 1899 while you
are there.

---

## 5 — Add Florence to the two `illustrative` lists

**Line 749** (`build_search_index`) and **line 823** (`build_zone_boundaries`) —
append to both:
```python
        ("firenze", "firenze", "Florence", True),
```

This is what fixes the sitemap and site-search gap: 75 pages currently live but
undiscoverable.

> ⚠️ **These two lists are identical, duplicated, 25 lines apart.** That is the same
> two-copies-of-one-fact pattern that produced every bug in this project. Fixing it
> is edit 6.

---

## 6 — Hoist a canonical `CITY_REGISTRY`  *(recommended, not required today)*

Add near `CITY_METHODOLOGY`:

```python
# The single canonical registry: public URL slug -> where its data lives, which
# URL scheme it uses, and its display label. build_search_index(),
# build_zone_boundaries(), main() and the QA scripts all read this instead of
# keeping their own copies. Adding city 26 becomes one entry, not four edits in
# four places.
CITY_REGISTRY = {
    "torino":            {"data_key": "torino",     "label": "Turin",     "scheme": "nested"},
    "zurigo":            {"data_key": "zurigo",     "label": "Zurich",    "scheme": "nested"},
    "milano":            {"data_key": "milano",     "label": "Milan",     "scheme": "nested"},
    "roma":              {"data_key": "roma",       "label": "Rome",      "scheme": "flat"},
    "berlin":            {"data_key": "berlin",     "label": "Berlin",    "scheme": "flat"},
    "amsterdam":         {"data_key": "amsterdam",  "label": "Amsterdam", "scheme": "flat"},
    "praha":             {"data_key": "praha",      "label": "Prague",    "scheme": "flat"},
    "oslo":              {"data_key": "oslo",       "label": "Oslo",      "scheme": "flat"},
    "monaco-di-baviera": {"data_key": "munich",     "label": "Munich",    "scheme": "flat"},
    "stockholm":         {"data_key": "stockholm",  "label": "Stockholm", "scheme": "flat"},
    "barcelona":         {"data_key": "barcelona",  "label": "Barcelona", "scheme": "flat"},
    "madrid":            {"data_key": "madrid",     "label": "Madrid",    "scheme": "flat"},
    "vienna":            {"data_key": "vienna",     "label": "Vienna",    "scheme": "flat"},
    "lisbon":            {"data_key": "lisbon",     "label": "Lisbon",    "scheme": "flat"},
    "paris":             {"data_key": "paris",      "label": "Paris",     "scheme": "flat"},
    "brussels":          {"data_key": "brussels",   "label": "Brussels",  "scheme": "flat"},
    "athens":            {"data_key": "athens",     "label": "Athens",    "scheme": "flat"},
    "venezia":           {"data_key": "venezia",    "label": "Venice",    "scheme": "flat"},
    "dublin":            {"data_key": "dublin",     "label": "Dublin",    "scheme": "flat"},
    "edinburgh":         {"data_key": "edinburgh",  "label": "Edinburgh", "scheme": "flat"},
    "napoli":            {"data_key": "napoli",     "label": "Naples",    "scheme": "flat"},
    "budapest":          {"data_key": "budapest",   "label": "Budapest",  "scheme": "flat"},
    "krakow":            {"data_key": "krakow",     "label": "Kraków",    "scheme": "flat"},
    "firenze":           {"data_key": "firenze",    "label": "Florence",  "scheme": "flat"},
}
```

Then both `illustrative` lists become:
```python
    illustrative = [
        (v["data_key"], slug, v["label"], v["scheme"] == "flat")
        for slug, v in CITY_REGISTRY.items()
    ]
```

Note the registry is keyed by **URL slug**, and `data_key` differs from it for
exactly one city (`monaco-di-baviera` → `munich.json`). That mismatch is invisible
today and is the kind of thing that silently drops a city from a list.

`qa_full_site.py` looks for `BS.CITY_REGISTRY` and uses it when present; otherwise
it falls back to its own table **and emits a warning saying so**, so the warning
disappears the moment this edit lands. London stays outside the registry — it has
its own pipeline and underscored borough slugs — and is special-cased in both QA
scripts.

---

## Order of application

1. Edit 1 (email) — safe alone, no output-shape change.
2. `build_firenze_zones.py` → produces `pipeline/data_zones/firenze.json` (already
   generated and validated; committing the pre-built JSON is fine).
3. Edits 2–5 (Florence wiring).
4. Run the Phase-1 CI workflow. Read `candidate_diff.json`.
5. Edit 6 once the diff is clean and boring.

## What I could not do

None of this is tested by execution. This Mac has no working Python or git —
`/usr/bin/python3` and `/usr/bin/git` are Command Line Tools stubs. Per your
instruction not to install a local toolchain, **the Phase-1 CI workflow is the
first execution of any of this code**, and it is built to fail loudly and
non-destructively when it does.

Expect the first run to surface bugs in my three new scripts before it surfaces
anything about the site. That is the correct order: the harness has to earn trust
before its verdicts mean anything.
