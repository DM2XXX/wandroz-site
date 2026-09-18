# Wandroz — internal methodology (NOT PUBLISHED)

**This file is deliberately not published.** It holds the part of the
methodology that the public page used to carry and no longer does: exact
thresholds, weights, category allocations, denominator corrections and the
engineering history behind them.

The public page at `/methodology.html` answers *"why should I trust this
rating?"*. This file answers *"exactly how is this rating produced?"*. The
first is the product; the second is the thing a competitor with the same raw
CSV cannot get for free.

**Why it cannot leak into the build.** The generator only ever reads
`pipeline/templates/`, `pipeline/static/`, `pipeline/data_*/` and `data/`, and
writes to `dist/`. `docs/` is outside all of those, so no build path reaches
it. That is an argument, not a guarantee, so the QA gate also fails the build
if any published file contains the markers listed under "Publication guard"
below — see `check_recipe_not_published()` in `pipeline/qa_full_site.py`.

Anything added here that must stay private should get a marker in that check.

---

## 1. London and the English/Welsh cities — data.police.uk pipeline

Source of truth: `pipeline/score_london.py`, `pipeline/score_uk_city.py`.

### 1.1 Category weights

Applied to the recorded count for each crime category before any rate is
computed. Rationale: anti-social behaviour and shoplifting dominate the raw
counts and are the least relevant to a traveller's exposure, so leaving the
counts unweighted made every high-footfall retail area look like a violent one.

| Category | Weight |
|---|---|
| violent-crime | 3.0 |
| robbery | 3.0 |
| possession-of-weapons | 2.5 |
| burglary | 2.0 |
| theft-from-the-person | 2.0 |
| criminal-damage-arson | 1.5 |
| vehicle-crime | 1.2 |
| public-order | 1.2 |
| other-theft | 1.0 |
| drugs | 1.0 |
| other-crime | 1.0 |
| bicycle-theft | 0.8 |
| anti-social-behaviour | 0.5 |
| shoplifting | 0.3 |

`DEFAULT_WEIGHT = 1.0` for any category not listed.

### 1.2 Day / night category allocation

This is a **category-mix proxy, not measured time of day**. The UK Police API
publishes no per-incident timestamp. The public page must keep saying so; it no
longer says which categories go where.

- **Day score**: `bicycle-theft`, `burglary`, `drugs`, `shoplifting`,
  `vehicle-crime`
- **Night score**: `anti-social-behaviour`, `public-order`, `robbery`,
  `theft-from-the-person`, `violent-crime`
- **In neither score**: `criminal-damage-arson`, `possession-of-weapons`,
  `other-theft`, `other-crime`. They carry weights (used elsewhere) but are
  excluded from both scores rather than assigned to a half of the day on a
  guess.

### 1.3 Rate

    day_rate   = Σ(weight[c] × avg_monthly_count[c] for c in DAY_CATEGORIES)   / population × 1000
    night_rate = Σ(weight[c] × avg_monthly_count[c] for c in NIGHT_CATEGORIES) / population × 1000

`avg_monthly_count` is the mean over the most recent 3 published months, not the
latest month alone: one unusual month used to swing a borough's relative
position more than a real trend would.

### 1.4 Classification thresholds

Against the mean rate of the covered areas **of that city only**:

- `rate >= 1.3 × city_average` → **red**
- `rate <= 0.8 × city_average` → **green**
- otherwise → **yellow**

The same two cut-offs are used for every official-data city, London and the
snapshot cities alike. This is the single most reproducible thing on the site
and the main reason the public page no longer states it.

### 1.5 Denominator — London only

London divides by an estimated **workday/footfall population**, not resident
population. Three tiers, disclosed per borough page but no longer explained as
a mechanism on the methodology page:

1. **measured headcount** — the ONS 2011 Census workday-population release
   names the borough directly. 17 of 32 boroughs.
2. **density-based proxy** — not in the headcount tables but present in the
   release's density-per-hectare table, used as a stand-in. 5 boroughs.
3. **no correction** — in neither table; resident population is used as-is
   rather than inventing a figure. 10 boroughs.

The ratio comes from the 2011 release (Westminster's workday population was
267% of its resident population that year) and is applied to each borough's
2021 resident population. No official UK workday-population release has been
published since 2011.

**Consequence that must stay public:** for the 10 uncorrected boroughs the rate
is resident-normalised, so the resident-denominator caveat applies to them and
not to the other 22. `caution_note()` in `build_site.py` enforces this per
borough via `workday_population_ratio`.

The other 20 English/Welsh cities use **resident population only** — no workday
correction exists for wards.

### 1.6 Geography

Crime is queried against each area's real administrative polygon (ONS 2021 for
London), not a radius around a centroid. If boundary data fails to load for a
run, the borough page says so and falls back to the old ~1-mile circle rather
than silently using the wrong method.

---

## 2. Official-snapshot cities

Berlin, Amsterdam, Prague, Oslo, Munich, Stockholm, Brussels.

Each takes its own national or municipal published statistic, normalises on the
resident population that source publishes, and applies **the same 1.3× / 0.8×
thresholds against that city's own population-weighted average**. No day/night
split exists in any of these sources: both the day and night rating for a zone
come from the same annual figure.

Per-city inputs, reference periods and quirks live with each city's builder in
`pipeline/build_*_zones.py` and in `CITY_METHODOLOGY[...]["crime_source"]`.

### 2.1 Munich extraction note (engineering history)

Munich's figures were independently extracted twice before publication — once
via an automated summary of the source PDF, once from scratch by loading the
PDF's raw bytes and running pdf.js against them in the browser, because
Chrome's built-in PDF viewer failed to render that particular file. Both
extractions agreed. District populations were checked by confirming the 25
district figures sum exactly to the published city total.

This belongs here, not on the public page: it is a story about our QA, not
something that helps a reader interpret a Munich rating.

### 2.2 Oslo outlier note

Oslo's Sentrum has a very small resident population against heavy nightlife and
office use; its 2024 rate lands around 60× the citywide average. The number is
real and the denominator makes it unreadable as a traveller signal. This is the
canonical example of the resident-denominator artefact and the reason the
caveat exists.

---

## 3. Structured local-source assessment (class B)

The public page keeps the *principles* (multiple attributable sources, recency,
area-by-area review, cross-source consolidation, explicit uncertainty, absence
of reporting is inconclusive). What is not public is the operational detail of
how a city's review is batched, which source families are tried in which order,
and how a conflicting pair is resolved into a colour.

The `evidence` field per zone is `documented` or `no_findings`. `no_findings`
means the review reached no reporting specific to that area; it renders dashed
on the map and is stated in words on the area page. It is never silently
treated as a clean result.

---

## 4. Limited-data assessment (class C)

Turin and Zurich. No official neighbourhood dataset is published and the
area-level source review has not been completed. Zurich additionally carries
Kantonspolizei Zürich's district burglary rate as a separate, clearly-labelled
layer that does **not** drive its rating.

Terminology note: "manual first-pass", "illustrative first pass" and
"experimental first pass" are **retired**. The canonical public term is
**Limited-data assessment**. `MANUAL_EXPERIMENTAL` survives as an internal
constant name only.

---

## 5. Publication guard

`check_recipe_not_published()` in `pipeline/qa_full_site.py` fails the build if
any file under `dist/` contains one of these markers:

- `1.3×` / `1.3x` / `0.8×` / `0.8x` in a threshold context
- the phrase `workday population` together with a tier name
- the explicit day/night category lists
- the filename `internal-methodology`

Add a marker whenever something private is added to this file. A guard that is
not updated is a guard that stops guarding.

---

## 6. The per-city sections removed from the public page

Preserved verbatim (markup stripped) from the version of
`pipeline/templates/methodology.html` at commit 7f98400a, the last one that
carried them. They are here for two reasons: several contain genuine
negative findings that cost real work to establish — Milan's confirmation
that no geolocated municipal dataset exists, corroborated by a named quote
from Il Riformista, is not something to re-derive from scratch — and the
rest document what was actually checked in each city.

**These are not private by nature.** Most of it is category A, public
transparency, and it is off the public page only because the page could not
carry 24 hand-written city essays and stay consistent with 62 cities of
generated metadata. Moving the facts that matter into structured per-city
metadata, so the public table can carry them for all 62 rather than 24, is
the open item — see the report accompanying this change.


### How a structured local-source assessment is made

This is the method behind class B, in full, so it can be judged rather than taken on trust. It is deliberate, documented work per area — and it is not a police dataset, which is why it is labelled differently from one.

Source collection. Before anything else, we check whether the city or country publishes an open, geolocated crime dataset at neighbourhood level; where one exists, the city moves to class A and this method is not used. Where none does, the review draws on established local and national news outlets, municipal and government publications, police-published district figures where they exist, official reports, and credible survey or research data. Not every class is available in every city — each city's section below names what was actually used there, including where a source is a resident-perception survey or a market-data ranking rather than a crime figure.

Area-level review. Research is carried out per neighbourhood, not once per city. A city-wide reputation is never copied across its areas: … areas each have their own review and their own written reasoning.

Signal identification. What the review looks for is traveller-relevant: theft and pickpocketing, robbery, violent incidents, drug-related activity, persistent disorder, nightlife-related trouble, transport-hub problems, and other repeatedly documented concerns that would change how a visitor uses an area.

Cross-source consolidation. A single article or one isolated incident is not a rating. Signals are weighed together and in context — how often, how recently, how specific to that area, and whether independent sources agree. Where sources conflict, both findings are stated on the area's page rather than averaged into a number.

Recency. Recent evidence carries more weight; older material is used where it establishes a persistent local pattern rather than a one-off. Each area's page carries the dates of what was checked, and each city's section below states when its review was carried out.

Traveller relevance. What is being assessed is the context of a neighbourhood for a visitor. It is not an estimate of any individual's probability of becoming a victim of crime, and it should not be read as one.

No coverage is not a clean bill of health. This is the rule the method lives or dies on. Every area on a city map carries a rating — these are major cities and a map that shrugs at a third of its districts helps nobody — but a rating reached through an empty search is not the same claim as one built on named sources, and Wandroz will not let the two look identical. Areas where the review reached no reporting specific to them are marked no area-specific findings : dashed on the map, stated under the rating on the area's page, and spelled out in its answer to "is it safe?". The rating there rests on the absence together with the character of the area, and it says so. … of … areas currently carry that marker — most of them small administrative subdivisions with no press profile of their own, which is normal and is not a finding about the area.

Transparency. The reasoning is published on the area's own page, with the sources that produced it named there. Where the review reached nothing, the page states that too, instead of quietly rendering the area the same colour as a checked one.

Every figure here is counted from the published data at build time, including the ones that are unflattering. A high "no area-specific findings" count means the review reached fewer sources in that city — usually because its official geography is cut into small administrative units — not that the city is safe.

City Areas reviewed Backed by named sources No area-specific findings Review completed

What this method is not: it is not a crime count, it is not comparable between cities, and it does not become an official statistic by being carefully done. Where a country starts publishing neighbourhood-level crime data, that city moves to class A and its ratings are rebuilt on it.


### How a score is built

For each London borough, Wandroz downloads every recorded crime for each of the most recent 3 months available (averaged together, not just the latest month — see "What this method gets wrong today" below for why) inside that borough's real administrative boundary (the same ONS 2021 polygon outline the map draws — not a circle around its centre), then splits it into two scores. The day score uses crime categories that are overwhelmingly daytime in nature (shoplifting, burglary, vehicle/cycle theft, drugs); the night score uses categories with a well-documented evening/night skew (violence, robbery, street theft, public order, anti-social behaviour). This is a category-mix proxy , not literal time-stamped data — the UK Police API doesn't record a time of day per incident — so it will miss anything that doesn't fit that pattern; a few categories (criminal damage, weapons possession, "other theft"/ "other crime") are left out of both scores rather than guessed at. Each category is also weighted by how relevant it typically is to a traveller's sense of safety — violence and robbery count for more than shoplifting or anti-social behaviour, which are heavily over-represented in the raw data relative to serious crime.

Both scores are divided by an estimated workday/footfall population , not the borough's resident population — central, nightlife-heavy or highly-visited boroughs otherwise look "less safe per resident" simply because relatively few people are officially resident there compared to how many actually pass through. That workday population is approximated from the ONS's 2011 Census "workday population" release (the most recent official one published — Westminster's workday population was 267% of its resident population that year, for example), applied to each borough's up-to-date 2021 resident population. This release doesn't cover every borough the same way, so each borough page discloses which of three tiers its correction comes from: a measured headcount (the release names the borough directly — the most reliable tier), a density-based proxy (the borough isn't in the headcount tables but is in the release's density- per-hectare table, used as a stand-in), or no correction at all (the borough appears in neither table, so resident population is used as-is rather than inventing a number — this is disclosed explicitly on that borough's page, not hidden).

Boroughs are then rated against the average of the other London boroughs currently on the automated pipeline (… today) — not a fixed, borough-independent scale, and

effectively a full London average now that every borough except the City of London is covered.

not yet a full London average, since only … of … boroughs are covered so far.


### What this method gets wrong today

Extended 15 August 2026 — from 5 to … of … boroughs. The automated pipeline originally covered only 5 boroughs; it now covers …, using population and workday-correction data researched and added for the rest. The "average" every covered borough is rated against is the average of those … boroughs — it will keep shifting slightly as new monthly data comes in.

Workday population is a 2011-ratio approximation, and not every borough has one. No official UK workday-population release has been published since the 2011 Census, so today's footfall correction applies that release's resident-vs-workday ratio to each borough's 2021 resident population rather than a directly measured current figure — and for a subset of boroughs the 2011 release has no usable figure at all, so no correction is applied for them (see the tier explanation above; each borough page states plainly which tier it got).

Fixed 15 August 2026 — crime data now queried inside the real boundary, not a circle. Earlier versions of this page fetched crime counts from a point plus roughly a 1-mile radius around each borough's centre — a circle, not the exact administrative shape — so incidents right at a border could be attributed to the wrong side. Every borough now queries the UK Police API directly against its real ONS 2021 polygon outline (the same shape the map draws), so the count matches the shape you see. If a borough's boundary data can't be loaded for a given run, that borough's page will say so explicitly and fall back to the old circle rather than silently using the wrong method.

Fixed 15 August 2026 — averaged over 3 months, not just one. Scores used to reflect only the single most recent month the UK Police API had published, so one unusual month could swing a borough's relative position more than a longer-term trend would. Every score is now an average of the most recent 3 months on record for that borough (fewer right after a borough is first added, until 3 months have accumulated) — each borough page states the exact months included. Averaging further back than 3 months is possible as more history accumulates, but trades off responsiveness to genuinely recent changes.


### Turin and Zurich — limited-data assessment

Both cities were researched (16 August 2026) to see whether they could get their own automated pipeline like London's. The two turned out very different, and it's worth being specific about why rather than lumping them together as "not done yet."

Turin: no automated pipeline is currently possible, not just "not built yet." Unlike the UK, Italy does not publish an open, geolocated, neighbourhood-level crime dataset. The City of Turin's own open-data portal (aperTO) has no such dataset; Italy's national statistics office (ISTAT) publishes crime figures only at the provincia level (an area far larger than a single city), or a one-off Turin-specific study over 20 years out of date; and the Ministero dell'Interno's crime data is published at the whole-city or provincia level, not by neighbourhood. This matches independent reporting on Italian open data generally, not just a gap specific to Turin. Turin's ratings stay a manual, illustrative first pass for now — this page will be updated the moment that changes, but there's no pipeline to build against today.

Zurich: one real, narrow, official data layer added — burglaries, by district. The Kantonspolizei Zürich's comprehensive crime dataset (all offense types) turned out to not actually be current despite claiming an annual update — its data stops at 2022 and hasn't been refreshed since April 2023, so it wouldn't have been honest to build an automated pipeline on it. A separate, narrower dataset from the same source — burglaries only — is genuinely current (refreshed days before this was written, with data through 2025) and is now pulled automatically. It's published only at the level of Zurich's 12 Stadtkreise (city districts), not the 34 Statistische Quartiere the map shows, so every neighbourhood page inherits its district's figure rather than having its own — this is stated plainly on each Zurich neighbourhood page, and it sits alongside the existing manual day/night rating rather than replacing it. It's a real, official, current number — just a narrower and coarser one than London's pipeline provides.


### Milan — structured local-source assessment

Milan was researched (17 August 2026) the same way Turin was: checked the Comune di Milano's open-data portal, Regione Lombardia, and local police/prefettura sources for a geolocated neighbourhood-level crime dataset. None exists — confirmed independently, including by cross-checking against local journalism explicitly making the same point ("non esiste una rilevazione pubblica e periodica dei reati disaggregata per municipio" — Il Riformista). Rather than defaulting straight to Turin/Zurich's "general knowledge" first pass, Milan's ratings are built one tier up: real, current web research per area — recent local and national news coverage, official municipal "zona rossa" (red zone) public-order designations, and specific named incidents — with the reasoning disclosed on each neighbourhood's page rather than compressed into a single colour.

All 88 official zones covered, none skipped. Milan's NIL boundary dataset has 88 official zones, many of them fine-grained administrative subdivisions rather than names a traveller would recognise. The first pass (17 August 2026) covered the 20 most traveller-relevant zones plus every zone with a specific, named, sourced safety concern found during research; every remaining zone was then individually researched the same way (real web searches per zone, not a blanket assumption) and added the same day. For the majority of zones — ordinary residential streets with no notable news coverage — that honestly means a "no particular concern" rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the zone off the map. A handful of zones (Bicocca, Comasina, Bruzzano, Barona, Lorenteggio, Gratosoglio, Quarto Oggiaro, and others) carry real, sourced, recent local-press coverage of documented issues — drug dealing, organised-crime prosecutions, or recurring nightlife violence — and are flagged accordingly.

Milan's official "zone rosse" are a public-order tool, not a danger map — used carefully here. Milan currently has several areas under official "zona rossa" measures (allowing police to issue exclusion orders), extended through 30 March 2026. Some of these — like the historic centre and the Navigli nightlife strip — are covered because they're busy, high-footfall areas subject to public-order rules, not because they're dangerous; both are still rated green/safe by day on this map. Others — Stazione Centrale, Corvetto, Rogoredo, Via Padova — are flagged here because independent local reporting also documents specific, recurring incidents there (not just the zona rossa designation on its own), which is why those areas carry a caution rating and the others don't.


### Berlin: real official police data, annual not live

Berlin (23 August 2026) is the second city on the site, after London, whose ratings come from an official, geolocated police dataset rather than an assessment. Polizei Berlin publishes the Kriminalitätsatlas Berlin (https://www.kriminalitaetsatlas.berlin.de), a real crime map covering all 143 official "Bezirksregionen" (Berlin's finest routinely-published statistical subdivision), which was used both for the zone boundaries themselves and for each zone's Häufigkeitszahl (HZ) — total recorded offences per 100,000 registered residents, an annual, already population-normalized figure. Every zone is rated red/yellow/ green against the citywide average HZ, the same 1.3×/0.8× thresholds used for London.

Real data, but not a live pipeline, and no day/night split. Unlike London's monthly automated refresh, the Kriminalitätsatlas publishes one annual figure per zone, so Berlin's ratings here are a snapshot of the 2025 HZ table, not something re-pulled on a schedule yet. The source data also has no time-of-day breakdown, so — rather than inventing a day/night difference that isn't in the data — every Berlin zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

HZ counts residents, not footfall — read high numbers carefully. Häufigkeitszahl is defined against each zone's registered resident population. A zone with heavy tourist, shopping or transit traffic and relatively few residents (central Mitte's Alexanderplatz and Regierungsviertel, for instance) can show a high HZ from a normal volume of opportunistic offences spread over a small resident base — that is not the same claim as "unusually dangerous to visit." A quiet, heavily residential zone can likewise show a low HZ simply by having few recorded offences relative to its population. This caveat is repeated on every Berlin zone page, not just here.


### Amsterdam: real official CBS crime and population data

Amsterdam (23 August 2026) is the third city on the site whose ratings come from an official, geolocated government dataset rather than an assessment. The zone boundaries are the Gemeente Amsterdam's own official "wijk" boundaries (110 zones, via api.data.amsterdam.nl), and each zone's rating is computed from two real CBS (Statistics Netherlands) tables: registered crimes per wijk for 2025 (table 47018NED) and population per wijk for 2025 (table 86165NED), combined into a rate per 100,000 residents — the same style of already population-normalized figure Berlin's Häufigkeitszahl is, just computed here from CBS's own separate crime and population tables rather than published as a single ready-made statistic. Every zone is rated red/yellow/green against the citywide average rate, the same 1.3×/0.8× thresholds used for London and Berlin.

Real data, but not a live pipeline, and no day/night split. Like Berlin, this is a snapshot of CBS's 2025 tables, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Amsterdam zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall — read high numbers carefully. A wijk with heavy tourist, shopping or transit traffic and relatively few residents (the historic centre's Burgwallen and Grachtengordel wijken, or the Zuidas business district) can show a high rate from a normal volume of opportunistic offences spread over a small resident base — that is not the same claim as "unusually dangerous to visit." A handful of very sparsely populated wijken — harbour and industrial fringe areas like Sloterdijk-West or Coenhaven/Minervahaven, some under 1,000 or even under 100 registered residents — can also swing sharply from just a few recorded cases; those zones' own pages flag the small population explicitly. This caveat is repeated on every Amsterdam zone page, not just here.


### Prague: real official Policie ČR crime and CSU population data

Prague (24 August 2026) is the fourth city on the site whose ratings come from an official, geolocated government dataset rather than an assessment. The zone boundaries are Prague's own official "městské části" (57 city districts, the full set of Praha 1–22 plus the 35 smaller named "Praha-X" districts, none excluded), and each zone's rating is computed from two real official sources: Policie ČR's (Czech national police) total registered incidents per district for 2024, via the official kriminalita.policie.gov.cz portal, and CSU (Czech Statistical Office) population per district for 2024, from the DataStat open API. Both figures were pulled for the same year (2024) to keep the resulting rate from being skewed by a vintage mismatch. Every zone is rated red/yellow/green against the citywide average rate, the same 1.3×/0.8× thresholds used for London, Berlin and Amsterdam.

Real data, but not a live pipeline, and no day/night split. Like Berlin and Amsterdam, this is a snapshot of 2024 figures, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Prague zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall — read high numbers carefully. A district with heavy tourist, shopping or transit traffic and relatively few residents (Praha 1's historic centre, for instance) can show a high rate from a normal volume of opportunistic offences spread over a small resident base — that is not the same claim as "unusually dangerous to visit." A handful of very sparsely populated outer districts can also swing sharply from just a few recorded cases; those districts' own pages flag the small population explicitly. This caveat is repeated on every Prague zone page, not just here. Separately, mapakriminality.cz (an NGO-republished feed of the same underlying police data) was checked as a possible source and found stale since November 2020, so the official kriminalita.policie.gov.cz portal was used directly instead.


### Oslo: real official Oslo kommune Statistikkbanken data

Oslo (24 August 2026, updated same day) is the sixth city on the site whose ratings come from an official, geolocated government dataset rather than an assessment, and the first built on a Norwegian municipal source. The zone boundaries are Oslo's own official 15 "bydeler" (city boroughs, each with its own elected local bydelsutvalg) plus Sentrum , the city centre — 16 zones, none excluded. Sentrum is not one of the 15 administrative bydeler and carries no population figure in Oslo kommune's own bydel-level data, but it does have its own distinct entry in Oslo kommune's crime table and its own real population figure from Statistics Norway's separate "urban district" system, so it is mapped using those two sources rather than left as a gap in the middle of the city (see the caveat below). Each bydel's rating is computed from two tables in the same official source, Oslo kommune's own Statistikkbanken: table KRI002 for total reported offences by place of occurrence per bydel in 2024, and table BEF005 for population per bydel, also for 2024; Sentrum's rating uses KRI002's own separate "Sentrum" row for offences, and Statistics Norway (SSB) table 10826 for its 2024 population. All figures were pulled for the same year to keep the resulting rate from being skewed by a vintage mismatch (Statistikkbanken's population table already has live 2025/2026 figures, but its crime table currently stops at 2024). Every zone is rated red/yellow/green against the population-weighted citywide average rate, the same 1.3×/0.8× thresholds used for London, Berlin, Amsterdam and Prague.

Real data, but not a live pipeline, and no day/night split. Like Berlin, Amsterdam and Prague, this is a snapshot of 2024 figures, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Oslo zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall, and Sentrum's figure is an extreme case of this. A bydel with heavy nightlife, shopping or commuter traffic and a comparatively smaller resident base (Gamle Oslo and St. Hanshaugen, in particular) can show a high rate from a normal volume of offences spread over a smaller resident denominator — that is not the same claim as "unusually dangerous to visit." Sentrum takes this to an extreme: with only 1,528 registered residents against Oslo's densest concentration of hotels, shops, restaurants, nightlife and offices, its 2024 rate comes out around 60× the citywide average — a genuinely high absolute number of offences divided by a tiny denominator, not a literal 60-fold increase in walking-around risk. It is shown rather than hidden because leaving Oslo's own city centre off the map — exactly where many visitors book — would be a bigger gap than an inflated number with this caveat attached, and the caveat is repeated on Sentrum's own zone page. Separately, Oslo kommune's own published note on this data flags that many criminal-damage cases reported by the city's public transport operator (Sporveien) are registered with an offence address in Bydel Nordstrand regardless of where the incident actually happened, inflating that district's figure somewhat independent of on-the-ground risk — this is disclosed on Nordstrand's own zone page too.

Marka (forest) remains excluded. Unlike Sentrum, Oslo kommune's crime table has no distinct figure for Marka — it is folded into a mixed "uoppgitt gjerningsbydel" (unspecified place-of-offence) catch-all alongside genuinely unknown-location offences, so it cannot be honestly attributed to Marka specifically. Marka is also largely unpopulated forest with no visitor accommodation, so this does not affect the site's usefulness for travellers the way Sentrum's initial omission did.


### Munich: real official Polizeipräsidium München and Statistisches Amt München data

Munich (24 August 2026) is the seventh city on the site whose ratings come from an official, geolocated government dataset rather than an assessment. The zone boundaries are Munich's own official 25 "Stadtbezirke" (city districts), none excluded, sourced directly from GeodatenService München's own boundary WFS. Each district's rating is computed from two real official sources: Polizeipräsidium München and the Statistisches Amt München's own published "Straftaten in den Stadtbezirken 2025" table (total recorded offences per district) and the Statistisches Amt München's population-per-Stadtbezirk figures as of 31 December 2024. The crime figures were independently extracted twice before being used for a published rating — once via an automated summary of the source PDF, once from scratch by loading the PDF's raw bytes and running pdf.js against them directly in the browser (Chrome's built-in PDF viewer failed to render this particular file) — and both extractions agreed. The population figures were checked by confirming the 25 district populations sum exactly to the dataset's own published citywide total (1,603,776). Every zone is rated red/yellow/green against the population-weighted citywide average rate, the same 1.3×/0.8× thresholds used for London, Berlin, Amsterdam, Prague and Oslo.

Real data, but not a live pipeline, and no day/night split. Like Berlin, Amsterdam, Prague and Oslo, this is a snapshot of 2025 crime figures against a 2024 population figure, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Munich zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall — read high numbers carefully. Altstadt-Lehel (Munich's historic centre around Marienplatz) and Ludwigsvorstadt-Isarvorstadt (which includes the Hauptbahnhof/ Bahnhofsviertel area and the Gärtnerplatz/Glockenbach nightlife district) both show a rate several times the citywide average — a small resident base next to some of Munich's densest hotel, shopping, station and nightlife traffic, the same footfall effect already documented for London's West End, Prague, Amsterdam, Berlin and Oslo's Sentrum. That is not the same claim as "unusually dangerous to visit," and this caveat is repeated on both districts' own zone pages, not just here. Two districts' boundary polygons — Untergiesing-Harlaching and Thalkirchen-Obersendling-Forstenried-Fürstenried-Solln — were returned twice by the source WFS service with identical crime/population attribution but two different shapes (a small fragment and the full district body); the full body was kept and the tiny duplicate fragment dropped, since it is imperceptible at map scale and does not affect either district's crime or population figures.


### Stockholm: real official Brå and Stockholms stad data

Stockholm (25 August 2026) is the eighth city on the site whose ratings come from an official, geolocated government dataset rather than an assessment, and the first built on a Swedish national source. The zone boundaries are Stockholm's own official 11 "stadsdelsnämnder" (city district committees), none excluded, sourced directly from Stockholms stad's own "Stadskartans Stadsdelsnämnder 2023" boundary dataset. Each district's rating is computed from two real official sources: Brå (Brottsförebyggande rådet, Sweden's national crime-prevention council)'s own live statistics database, queried for total reported offences per district for 2025, and Stockholms stad's own "Befolkningsöversikt Årsrapport 2024" population-per-district figures as of 31 December 2024. Every zone is rated red/yellow/green against the population-weighted citywide average rate, the same 1.3×/0.8× thresholds used for London, Berlin, Amsterdam, Prague, Oslo and Munich.

Real data, but not a live pipeline, and no day/night split. Like Berlin, Amsterdam, Prague, Oslo and Munich, this is a snapshot of 2025 crime figures against a 2024 population figure, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Stockholm zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall — read high numbers carefully. Norra innerstaden (Stockholm's dense inner-city core, covering the former Norrmalm and Östermalm districts — Centralstationen, Sergels torg, and the main shopping streets around Drottninggatan and Hamngatan) shows a rate meaningfully above the citywide average, and Södermalm (a major nightlife and restaurant district) follows close behind — both a small resident base next to some of Stockholm's densest station, shopping and nightlife traffic, the same footfall effect already documented for London's West End, Prague, Amsterdam, Berlin, Oslo's Sentrum and Munich's Altstadt-Lehel. That is not the same claim as "unusually dangerous to visit," and this caveat is repeated on both districts' own zone pages, not just here.

Stockholm's 2024 reform means "11 districts" is genuinely current, not a mismatch between sources. Brå's own crime-statistics tool initially looked like it might use a different district scheme from Stockholm's real administrative boundaries — its region list shows several older, now-discontinued district names (marked "upphörde 2024-01-01") alongside the 11 currently-active ones. Checked directly against Stockholms stad's own website: the city genuinely reorganised down to these same 11 stadsdelsnämnder, so the crime, population and boundary sources used here all line up on the same real, current districts — not an approximation across mismatched schemes.


### Barcelona — structured local-source assessment

Barcelona (25 August 2026) was researched the same way Rome, Milan and Turin were: checked the Ajuntament de Barcelona's own open-data portal, Catalonia's regional statistics sources, and the Mossos d'Esquadra (Catalan police) for a geolocated barri-level crime dataset. None exists — the Ajuntament's portal was bot-gated for automated/browser-tool access at build time, and no other official source publishes reported crime broken down by barri. Barcelona's 73 official barris (grouped into 10 districts) were each individually researched — real, current local and national press coverage (La Vanguardia, El Periódico, ARA, El País, Betevé, Metrópoli Abierta and others), Mossos d'Esquadra statements, and specific named incidents where they exist — with the reasoning and sources disclosed on each barri's own page rather than compressed into a single colour.

All 73 official barris covered, none skipped. Every barri was researched the same way (real web searches per barri, not a blanket assumption based on district or income level), grouped into 10 batches by official district to keep the research tractable. For the majority of barris — ordinary residential streets with no notable news coverage — that honestly means a "no particular concern" (green) rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the barri off the map. A number of barris (El Raval, El Carmel, Ciutat Meridiana, La Verneda i la Pau, El Besòs i el Maresme, and others) carry real, sourced, recent local-press coverage of documented issues — drug-related activity, organised-crime prosecutions, or recurring violent incidents — and are flagged accordingly; a much larger number of barris, including several in lower-income districts, showed no such coverage and are rated green, since this project never infers a rating from a neighbourhood's income level or reputation alone.

Barcelona's real, well-documented issue is overwhelmingly tourist-targeted theft, not violent crime. Multiple independent sources (Barcelona's own Guàrdia Urbana Beach Unit, national press comparing Barcelona to other major cities on tourist-theft rates) confirm pickpocketing and bag-snatching — particularly around La Barceloneta beach, the Gòtic and Raval, Sants station, and the Sagrada Família — as a genuinely elevated, well-documented risk to property. This is kept distinct throughout from violent crime against persons, which is concentrated in specific, sourced incidents rather than a citywide pattern, and each barri's page states plainly which kind of concern (if any) the research actually found.


### Madrid — structured local-source assessment

Madrid (28 August 2026) was researched the same way Barcelona, Rome, Milan and Turin were: checked the Ayuntamiento de Madrid's own open-data portal and the Comunidad de Madrid's statistical offerings for a geolocated barrio-level crime dataset. None exists — Spain's Interior Ministry publishes crime balances at municipality level only, not by barrio. Madrid's 131 official barrios (grouped into 21 districts) were each individually researched — real, current local and national press coverage (El País, El Mundo, ABC, La Vanguardia, Telemadrid, ElDiario.es, 20minutos, Madridiario and others), Policía Nacional/Municipal statements, and specific named incidents where they exist — with the reasoning and sources disclosed on each barrio's own page rather than compressed into a single colour.

All 131 official barrios covered, none skipped. Every barrio was researched the same way (real web searches per barrio, not a blanket assumption based on district or income level), grouped into 21 batches by official district to keep the research tractable. For the majority of barrios — ordinary residential streets with no notable news coverage — that honestly means a "no particular concern" (green) rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the barrio off the map. A number of barrios (Embajadores/Lavapiés, San Cristóbal, Entrevías, San Diego, Orcasitas, Pradolongo, several barrios in San Blas-Canillejas around Parque Paraíso, Valdebernardo, El Cañaveral, and others) carry real, sourced, recent local-press coverage of documented issues — narcopisos, organised-crime activity, or recurring violent incidents — and are flagged accordingly; a much larger number of barrios, including several in lower-income districts, showed no such coverage and are rated green, since this project never infers a rating from a neighbourhood's income level or reputation alone.

Madrid's most consistently and severely documented pattern is narcopisos — drug-dealing flats — rather than street muggings. Multiple independent Spanish outlets, across many barrios and several years, document a recurring cycle in specific areas (parts of Puente de Vallecas, Usera, Villaverde, Latina, San Blas-Canillejas and Vicálvaro in particular): police raids dismantle a drug-selling flat, only for a new one to open nearby within weeks or months. This is kept distinct throughout from violent street crime against passers-by or tourists, which in Madrid is more concentrated around specific transit hubs, parks and a handful of named streets rather than a citywide pattern — and each barrio's page states plainly which kind of concern (if any) the research actually found.


### Vienna — structured local-source assessment

Vienna (30 August 2026) was researched the same way Barcelona and Madrid were: checked Statistik Austria and the Bundeskriminalamt's own published crime statistics (PKS/Kriminalitätsbericht) for a geolocated district-level crime dataset. None exists publicly — Austria's official crime reporting bottoms out at Bundesland (state) level, and the police's own internal spatial-crime-analysis tool ("Kriminalitätsatlas") is explicitly restricted to internal Interior Ministry use. Vienna's 23 official Bezirke were each individually researched — real, current local and national press coverage (meinbezirk.at, vienna.at, Heute.at, oe24.at, ORF Wien, Falter and others), city and police statements, and specific named incidents where they exist — with the reasoning and sources disclosed on each district's own page rather than compressed into a single colour.

All 23 official Bezirke covered, none skipped. Unlike Barcelona/Madrid, Vienna has no further officially bounded neighbourhood layer below the Bezirk — "Zählbezirke" are statistical sub-areas used for census purposes, not administrative neighbourhoods, and "Grätzel" are informal, not officially delineated — so the 23 Bezirke are themselves the complete, correct unit and all 23 are mapped. For several districts — ordinary residential areas with no notable news coverage — that honestly means a "no particular concern" (green) rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the district off the map. A number of districts (Favoriten around Reumannplatz/Keplerplatz, Leopoldstadt's Praterstern, Ottakring's Yppenplatz/Brunnenmarkt, Rudolfsheim-Fünfhaus's Westbahnhof, Meidling's Bahnhof Meidling, Brigittenau's Handelskai, Floridsdorf's station/Wasserpark area) carry real, sourced, recent local-press coverage of documented issues — open drug dealing, weapon-ban/protection zones, or recurring violent incidents — and are flagged accordingly, almost always concentrated around a specific square, station or street rather than the whole district.

Vienna's most consistently documented pattern is drug dealing concentrated at specific transit hubs and squares, not a citywide crime wave. Multiple independent Austrian outlets document recurring open-drug and knife-crime concerns tied to named locations — Praterstern (Leopoldstadt), Reumannplatz/Keplerplatz (Favoriten), Yppenplatz (Ottakring), Westbahnhof (Rudolfsheim-Fünfhaus/Gürtel) — several of which have prompted the city to impose formal weapon-ban or protection zones. This is kept distinct throughout from the ordinary property-crime trends (car break-ins, bicycle theft, online fraud) that Vienna's own district-level police statistics show rising broadly across nearly every district regardless of reputation — and each Bezirk's page states plainly which kind of concern (if any) the research actually found.


### Lisbon — structured local-source assessment

Lisbon (30 August 2026) was researched the same way Barcelona, Madrid and Vienna were: checked the Sistema de Segurança Interna's own published annual security report (RASI, "Relatório Anual de Segurança Interna") for a geolocated freguesia-level crime dataset. None exists publicly — the RASI is a PDF-only report and reports crime figures only at municipality/national level, with no structured, downloadable, neighbourhood-level dataset. Lisbon's 24 official freguesias were each individually researched — real, current local and national press coverage (Público, Jornal de Notícias, Correio da Manhã, Observador, SIC Notícias, RTP, Diário de Notícias, CNN Portugal, TVI, Notícias ao Minuto and others), police and city statements, and specific named incidents where they exist — with the reasoning and sources disclosed on each freguesia's own page rather than compressed into a single colour.

All 24 official freguesias covered, none skipped. Lisbon's 24 freguesias (civil parishes, since the 2012 administrative reform that merged the prior 53 into 24) are the city's complete, non-overlapping official neighbourhood unit, so all 24 are mapped. For several freguesias — ordinary residential areas with no notable news coverage on one or both of day/night — that honestly means a "no particular concern" (green) rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the freguesia off the map. A number of freguesias carry real, sourced, recent local-press coverage of documented issues and are flagged accordingly, almost always concentrated around a specific neighbourhood, housing estate or street rather than the whole freguesia.

Lisbon's most consistently documented pattern is drug dealing and gang violence concentrated in a handful of named social-housing areas, not a citywide crime wave. Multiple independent Portuguese outlets document a long-running open-air drug market in Alcântara's Vale de Alcântara/Casal Ventoso area, recurring shootings and gang conflict tied to Carnide's Bairro Padre Cruz, and a large-scale drug-trafficking police operation ("Samir, rei do crack") centred on Marvila/Chelas — all three freguesias carry a red rating both day and night on that basis. Separately, tourist-focused pickpocketing and bag-snatching is a recurring theme in the historic, tram-heavy central freguesias (Santa Maria Maior, Misericórdia, Belém) and in packed nightlife areas (Bairro Alto in Misericórdia, Cais do Sodré), which is kept distinct throughout from the organised drug-related violence found elsewhere — each freguesia's page states plainly which kind of concern (if any) the research actually found.


### Paris — structured local-source assessment

Paris (31 August 2026) was researched the same way Barcelona, Madrid, Vienna and Lisbon were: checked France's official crime dataset (published by the SSMSI, Interstats, via data.gouv.fr) for a geolocated arrondissement- or quartier-level breakdown. None exists — SSMSI's own methodology publishes crime figures only at commune level, and Paris is a single commune, so there is no official finer-grained crime dataset to automate against. Paris's 80 official "quartiers administratifs" were each individually researched — real, current local and national press coverage (Le Parisien, Le Figaro, BFM Paris Île-de-France, France Bleu/ici Paris, franceinfo, 20 Minutes, RTL, CNews, Europe1, and others), prefecture de police communiqués and official city-council/mairie documents where relevant, with the reasoning and sources disclosed on each quartier's own page rather than compressed into a single colour.

All 80 official quartiers administratifs covered, none skipped. Paris's 80 quartiers (4 per arrondissement, across all 20 arrondissements) are the city's finest-grain official, non-overlapping neighbourhood unit, so all 80 are mapped. For many quartiers — especially in the historic, affluent central and western arrondissements — that honestly means a "no particular concern" (green) rating with a note that nothing specific was found, rather than either fabricating a concern or silently leaving the quartier off the map. A number of quartiers carry real, sourced, recent local-press coverage of documented issues and are flagged accordingly, almost always concentrated around a specific station, square or street rather than the whole quartier.

Paris's most consistently documented pattern is open-air drug dealing concentrated around a handful of named transport hubs and boulevards, not a citywide crime wave. Multiple independent French outlets document long-running open-air drug markets and street disorder around Gare du Nord (an official police "zone de sécurité prioritaire", quartier Saint-Vincent-de-Paul), the Barbès/Château Rouge area (quartier Goutte-d'Or), Porte de la Chapelle (quartier La Chapelle) and the Stalingrad/canal corridor (quartiers Pont-de-Flandre and Villette) — these quartiers carry red night ratings on that basis, each with the specific documented pattern named on its own page. Separately, tourist-focused pickpocketing is a recurring, well- documented theme around major landmarks (Montmartre/Sacré-Cœur, the Eiffel Tower/Champ de Mars), which is kept distinct throughout from the organised drug-related disorder found elsewhere, and a small number of quartiers (e.g. the Champs-Élysées, the Bois de Boulogne-adjacent quartiers) carry their own specific, separately sourced concerns — each quartier's page states plainly which kind of concern (if any) the research actually found.


### Brussels: real official BISA/Federale Politie and Statbel data

Brussels (3 September 2026) is the ninth city on the site whose ratings come from an official, geolocated government dataset rather than an assessment, and the first built on a Belgian source. The zone boundaries are the Brussels-Capital Region's own official 19 communes, none excluded, sourced directly from opendata.brussels.be's own boundary dataset. Each commune's rating is computed from two real official sources: BISA (Brussels Institute for Statistics and Analysis)'s own published workbook of total registered crimes and misdemeanours per commune for 2025, citing Federale Politie (federal police) figures, and Statbel (Belgium's national statistics office)'s own population-per-commune figures, also for 2025. Every zone is rated red/yellow/green against the population-weighted citywide average rate, the same 1.3×/0.8× thresholds used for London, Berlin, Amsterdam, Prague, Oslo, Munich and Stockholm.

Real data, but not a live pipeline, and no day/night split. Like Berlin, Amsterdam, Prague, Oslo, Munich and Stockholm, this is a snapshot of 2025 crime figures against a 2025 population figure, not something re-pulled on a schedule yet, and the source data has no time-of-day breakdown — so every Brussels zone shows one single level rather than a day/night pair, disclosed plainly on each zone's page.

The rate counts residents, not footfall — read high numbers carefully. The City of Brussels (the commune containing the historic Pentagon centre, Gare Centrale and Gare du Nord) shows a rate roughly double the citywide average, and Saint-Gilles (home to Gare du Midi, Brussels' Eurostar/international rail hub, plus the Barrière/Parvis nightlife area) follows close behind — both a comparatively modest resident base next to some of the region's densest station, tourism and nightlife traffic, the same footfall effect already documented for London's West End, Prague, Amsterdam, Berlin, Oslo's Sentrum, Munich's Altstadt-Lehel and Stockholm's Norra innerstaden. That is not the same claim as "unusually dangerous to visit," and this caveat is repeated on both communes' own zone pages, not just here.

Two communes' boundary shapes are simplified to their largest polygon part. Saint-Gilles and Ixelles came back from the boundary source as a GeoJSON MultiPolygon with a second, smaller polygon part — Saint-Gilles' second part is a roughly 440x-smaller sliver entirely inside the main polygon's bounding box (very likely a simplification artifact); Ixelles' second part overlaps the main polygon's bounding box rather than being a genuinely separate landmass. For both, only the larger polygon part is kept for the map shape shown here — the same "keep the larger part, drop the tiny/duplicate fragment" handling already used for two of Munich's Stadtbezirke. This affects only the drawn boundary shape, not which communes are included (all 19 are mapped) or their real crime/population figures, which cover the whole commune either way.


### Athens — structured local-source assessment

Athens was researched the same way Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon and Paris were: checked for an open, geolocated neighbourhood-level crime dataset first. None exists — the Hellenic Police publish crime figures only as national and regional aggregates, with no structured, geolocated, district-level dataset published. The zone boundaries are real, though: Athens' 7 official "Δημοτικές Κοινότητες" (Municipal Districts, a holdover administrative unit from the 2011 "Kallikratis" local-government reform), sourced directly from the City of Athens' own official GIS portal (gis.cityofathens.gr, a GeoNode instance, via its underlying GeoServer WFS endpoint), CC BY v3.0 Greece licensed. Each district was individually researched — real, current local and national press coverage (To Vima, Ta Nea, Ethnos, Skai, iefimerida.gr, ProtoThema, GreekCityTimes, and others), Hellenic Police statements and Human Rights Watch documentation where relevant, with the reasoning and sources disclosed on each district's own page rather than compressed into a single colour.

All 7 official Municipal Districts covered, none skipped. The 7 Δημοτικές Κοινότητες are the finest official government neighbourhood-equivalent unit for the Municipality of Athens (they subdivide further into 48 unofficial συνοικίες and 129 γειτονιές, but only the 7 Municipal Districts carry real, government- published boundaries), so all 7 are mapped. This is coarser than most other class B cities on the site, which means a single district's rating can span both a genuinely calm, upscale area and a specific pocket with a real documented problem — each district's page names the specific streets, squares or neighbourhoods the research actually found evidence for, rather than implying the whole district shares one uniform risk.

Athens' most consistently documented pattern is open-air drug dealing concentrated around a handful of named squares and metro stations, not a citywide crime wave. Multiple independent Greek outlets document long-running open drug dealing and related arrests around Omonoia Square (1st Municipal District), Attiki and Victoria Squares plus Agios Panteleimonas (6th Municipal District), and Kolonos/Sepolia near Attika metro station (4th Municipal District) — these districts carry red night ratings on that basis. Separately, Patisia (5th Municipal District) has its own multi-year, independently documented pattern going back to 2016, and Ampelokipoi (7th Municipal District) has a specific, real record of recurring gun violence rather than drug dealing. Tourist-focused pickpocketing around the historic centre and metro system (1st Municipal District) is kept distinct throughout from these organised drug- and gun-related patterns, and genuinely calm, affluent or gentrified areas — Kolonaki, Plaka, Thiseio, Petralona, central Kypseli — are rated accordingly rather than tarred by the same district-level colour as a documented problem a few kilometres away.


### Venice — structured local-source assessment

Venice was researched the same way Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris and Athens were: checked for an open, geolocated neighbourhood-level crime dataset first. None exists for Italy at this level. The zone boundaries used are the Comune di Venezia's 6 official "Municipalità" (the decentralized administrative districts established in 2005), which cover the whole city — the historic lagoon islands (Venezia-Murano-Burano, Lido-Pellestrina) as well as the mainland districts (Mestre-Carpenedo, Marghera, Favaro Veneto, Chirignago-Zelarino). The Comune's own GIS portal was checked directly for a downloadable Municipalità boundary layer; it publishes only a historic-centre civic-addressing layer (the "sestieri") at a reachable endpoint, so the boundaries used here are OpenStreetMap's administrative relations for the 6 Municipalità — themselves originally imported from the Comune's own official open data during earlier community mapping efforts, rather than a crowd-sourced guess. Each Municipalità was individually researched — real, current local and national press coverage (Il Gazzettino, La Nuova Venezia, VeneziaToday, ANSA Veneto, and others) — with the reasoning and sources disclosed on each district's own page rather than compressed into a single colour.

All 6 official Municipalità covered, none skipped — mainland included. The 6 Municipalità are the finest official government-published neighbourhood-equivalent unit for the whole Comune di Venezia, so all 6 are mapped, not just the postcard historic centre. This is coarser than most other class B cities on the site, which means a single district's rating can span both a genuinely calm area and a specific pocket with a real documented problem — each district's page names the specific streets, squares or areas the research actually found evidence for, rather than implying the whole district shares one uniform risk. One geometric simplification is disclosed here too: Favaro Veneto's official territory has a small (~5% of its area), genuinely disjoint outlying part that isn't separately drawn on the map for the same technical reason already used for Brussels and Munich — Favaro Veneto itself is still fully mapped and rated.

Venice's most consistently documented pattern is tourist-targeted pickpocketing in the historic centre, plus a separate, more serious pattern around the Mestre train station corridor — not a citywide crime wave. Piazza San Marco, the Rialto area and the station-to-Cannaregio corridor have well-documented, recurring pickpocketing and scam problems (Venezia-Murano-Burano's rating reflects this), while violent crime in the historic islands themselves remains rare and Murano/Burano show no documented pattern at all. On the mainland, the Mestre train station area (Piazzale Cialdini, Via Piave) and the pedestrian underpass to Marghera carry a separate, more serious documented pattern — open-air drug dealing plus specific reported armed robberies and stabbings — which is why Mestre-Carpenedo carries a red night rating while its residential streets (Carpenedo, Bissuola) show no comparable pattern. Marghera's own documented concerns (drug dealing, a 2025 mall brawl) are real but more localized than Mestre's. Chirignago-Zelarino and Favaro Veneto are quiet residential/suburban areas with only isolated drug- or property-related incidents found, rated accordingly rather than tarred by association with the busier districts nearby.


### Dublin — structured local-source assessment

Dublin was researched the same way Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens and Venice were: checked for an open, geolocated neighbourhood-level crime dataset first. Ireland's only near-candidate — a historical AIRO/data.gov.ie dataset of crimes recorded at each Garda station — was checked directly: it covers only 2003-2015, its own documentation describes the underlying project as "effectively completed," and no current download or live update exists, so it was not usable. The zone boundaries used are Dublin City Council's 11 official Local Electoral Areas (LEAs) — the government electoral geography used for Dublin City Council elections, most recently in 2024 — sourced from Ordnance Survey Ireland (OSi)'s official boundary dataset. Each LEA was individually researched — real, current local and national press coverage (The Irish Times, RTE, TheJournal.ie, the Irish Examiner, Dublin People, BreakingNews.ie, and others) — with the reasoning and sources disclosed on each district's own page rather than compressed into a single colour.

All 11 official Local Electoral Areas covered, none skipped. The 11 LEAs are Dublin City Council's finest official government-published electoral geography, so all 11 are mapped, not just the tourist core. Each district's page names the specific streets, stations or areas the research actually found evidence for, rather than implying the whole district shares one uniform risk.

Dublin's documented pattern is a genuine split between a handful of LEAs with serious, repeated, well-sourced problems and a majority with only isolated incidents. North Inner City (O'Connell Street, Smithfield, docklands) combines open drug dealing and gang intimidation with a fatal 2024 unprovoked assault on a tourist on O'Connell Street itself. South East Inner City (Temple Bar, Grafton Street, Trinity College, St Stephen's Green) pairs a long-running daytime pickpocketing problem with two separate fatal or near-fatal nighttime attacks in 2026. South West Inner City (the Liberties, Kilmainham, Rialto) has an academically documented crime rate more than double the national average alongside long-running open drug-dealing hotspots, even though its marquee tourist sites (Guinness Storehouse, Kilmainham Gaol) show no particular daytime concern. Ballymun-Finglas has an active, ongoing gang and drugs feud with multiple shootings and a 2026 incident in which a child discharged a dropped firearm, and Ballyfermot-Drimnagh has a well-documented pattern of gun and gang crime including a fatal 2024 shooting. By contrast, Clontarf, Pembroke (Ballsbridge, Donnybrook, Ranelagh, Sandymount), Cabra-Glasnevin, Donaghmede, Kimmage-Rathmines and Artane-Whitehall show no pattern of muggings, gang activity or no-go streets — only isolated, dated incidents — and are rated accordingly rather than tarred by association with the more serious districts nearby.


### Kraków — structured local-source assessment

Kraków was researched the same way Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens, Venice, Dublin, Naples and Budapest were: checked for an open, geolocated neighbourhood-level crime dataset first. Poland's national Krajowa Mapa Zagrożeń Bezpieczeństwa (National Security Threat Map) was checked directly — it turned out to be a crowd-sourced map of individual citizen-reported nuisances (speeding, public drinking, stray animals), not aggregated crime statistics, with no per-district breakdown or export, so it was not usable. The zone boundaries used are Kraków's 18 official dzielnice — the city's own government-defined administrative districts, each with its own local council (rada dzielnicy) — sourced from OpenStreetMap's tagged administrative-boundary relations, each cross-checked against its own Polish Wikipedia "Dzielnica N" article. Each dzielnica was individually researched using local press (Kraków Nasze Miasto, Portal Samorządowy, Gazeta Krakowska) and, notably, the City of Kraków's own official resident-safety survey (conducted end of 2022, published January 2023 on krakow.pl) — a genuine official government source, even though it measures resident perception rather than recorded crime counts.

All 18 official dzielnice covered, none skipped. Two of the local-press sources used report figures only in police-defined groupings spanning two or three dzielnice at once, rather than one figure per district — this is disclosed on the affected districts' own pages rather than presented as a precise single-district statistic.

Kraków's most consistent finding is that its historic centre, not its outer estates, carries the city's highest recorded crime. Stare Miasto (the Old Town) recorded the highest theft, robbery and assault counts of any district in both the most recent (2024) and an earlier (2022) police breakdown, which a police spokesperson attributed directly to its concentration of nightlife venues — while Grzegórzki, Kraków's administrative and business district, was the single safest district in both years running. Three district pairs produced genuinely conflicting evidence between the City of Kraków's own official survey or a private 120,000-respondent resident survey on one hand and raw police theft counts on the other — Bronowice, Bieńczyce and Wzgórza Krzesławickie — and rather than pick a side, both findings are disclosed on each district's own page. Bieżanów-Prokocim stands out as the one district where an official government survey and an independent private survey agree: both rate it the city's least safe by resident perception, even though its raw theft figures are only moderate.


### {{ uk_cities|length }} English and Welsh cities: the same official feed as London

… are built on London's own pipeline rather than beside it. … all publish street-level crime records to data.police.uk (https://data.police.uk) — the same national feed London runs on — so every official ward is queried against its real ONS boundary polygon, not a circle around a centroid, and scored with the same category weights and the same day/night split described above. Ratings compare a ward against the average of its own city's wards, never against London's or each other's.

One deliberate difference from London: no footfall correction. London's scores are divided by an estimated workday population, because the ONS published a workday-population release at borough level. No equivalent exists for wards, so these cities' rates are per resident (2021 census). The effect is predictable and worth knowing when reading the map: a central ward carrying a city's shops, stations and nightlife — Ladywood, which includes the Bullring and New Street — serves far more people than live there, so its rate per resident reads high. It is the highest in the city at 46 recorded crimes per 1,000 residents over the three months to July 2026; that number describes a city centre, not a warning to stay away from one.

Why Liverpool and Brighton are not here. Both re-drew their wards after the 2021 census, so their current wards have no census population: the national statistics service returns nothing for those codes. A rate needs a denominator measured over the same geography as its numerator, and the alternative is crime counts divided by an estimate nobody published. They wait for 2021-vintage boundaries or a newer official ward figure.

Why Manchester is not here. Manchester was the intended first city. Greater Manchester Police does not supply street-level crime to data.police.uk, and the API does not say so — it answers normally and returns almost nothing. A mile around Manchester city centre returned 6 recorded crimes for June 2026, against 1,774 in Birmingham, 1,691 in Bristol, 1,464 in Liverpool and 1,452 in Leeds for the same month and the same radius. Published as-is, that would have made Manchester by far the safest city on this site, purely because a police force is absent from a feed. The build now refuses any city whose recorded rate falls below a plausibility floor, and says it is a data-supply problem rather than a finding.


### Rome — structured local-source assessment

Rome (reviewed 20 August 2026) uses Roma Capitale's own 155 official Zone Urbanistiche, taken from the Comune's Geoportale. Italy publishes no open geolocated crime dataset at neighbourhood level, so each zona was reviewed individually against Italian local and national reporting — RomaToday, Il Messaggero, Corriere della Sera, Il Fatto and local outlets — plus municipal material where an area was subject to a public-order measure. The reasoning and the dates are on each zona's page. Rome is also the clearest illustration of the no-coverage rule: many Zone Urbanistiche are administrative slivers with no press profile of their own, and 34 of the 155 returned nothing at all. Those are shown as reviewed with no findings rather than as calm — the earlier version of this map rated them green, which is exactly the inference this page says it does not make.


### Florence — structured local-source assessment

Florence (reviewed to 13 September 2026) is mapped on the Comune di Firenze's 74 official aree elementari — a deliberately fine-grained statistical grid, much smaller than a neighbourhood a visitor would name. Sources are Tuscan local press: La Nazione, FirenzeToday, Controradio, 055firenze and Firenze Post/ANSA. That grid is why Florence's coverage table looks the way it does: 43 of the 74 cells have no press profile of their own, and are published as reviewed with no findings. The 31 that carry a rating include the areas a visitor actually walks — the historic centre, Santa Croce, San Frediano, the station district and the Cascine.


### Naples — structured local-source assessment

Naples (reviewed 11 September 2026) is mapped on the city's 10 official Municipalità. Alongside local reporting (Fanpage.it, Napolitan.it, Il Mattino), the review uses a genuinely official document: the Naples Court of Appeal's annual report on organised crime, which describes activity by area. Municipalità are large — each covers several districts — so ratings are coarser here than in cities mapped at neighbourhood level, and each page says which specific district within the Municipalità the evidence refers to.


### Budapest — structured local-source assessment

Budapest (reviewed 11 September 2026) is mapped on its 23 official districts. Hungary publishes no open neighbourhood crime dataset, but the police statistics service (PRE-STAT) and a rolling 30-day crime-hotspot map are public, and both are used here alongside Hungarian press (Index.hu, Metropol.hu, BPhírek). Where a figure comes from the hotspot map rather than from an annual statistic, the district's page says so — a 30-day window is a snapshot, not a trend.


### Edinburgh — structured local-source assessment

Edinburgh (reviewed 10 September 2026) is the one city in this class whose evidence is not press at all. Its 17 wards are rated from a numeric crimes-per-1,000-population analysis of Scottish Government and Police Scotland figures, independently corroborated by a second published analysis. That is stronger than a source review and weaker than a first-party official feed: it is a secondary analysis of official statistics, published by third parties, not a dataset Police Scotland releases at ward level itself. It is deliberately not labelled 🟢 Official crime data for that reason — the conservative label is worth more than another green city.


### How this scales beyond London

Wandroz is meant to eventually cover neighbourhoods across Europe, not just London. Getting there honestly means being upfront about which of three tiers a city's data currently sits at:

Tier What it means 1 — Official, automated A government or police API/dataset exists and is pulled automatically on a schedule, with no manual editing. London is here today. 2 — Local press signal No clean official feed exists yet, so coverage is built (semi-automatically) from local news and public safety reporting instead. 3 — Community-verified Residents confirm or correct scores directly, with multiple independent confirmations required before a correction is applied — to avoid the kind of single-person bias that has undermined similar crowdsourced safety apps in the past.

Every city page will eventually say plainly which tier its data comes from, rather than presenting every score as equally rigorous.


### Updates

London's scores are recomputed from data.police.uk by pipeline, not by hand, and every borough page names the exact months behind its score — currently …. That refresh is currently run on review rather than on an unattended schedule: the job rebuilds and republishes the whole site, so it goes through the same build, QA and release gate as any other change. The published window on this page is read from the data itself, so it cannot promise a freshness the site does not have.

14 September 2026 — evidence classes named, and an empty search stopped counting as a clean street. Every city page now carries one compact provenance line instead of a disclaimer panel, naming its evidence class and what sits behind it. … areas whose review had reached no source were rated "calm — no particular concern"; they are now shown as reviewed with no findings, which is what the evidence supports. Class B cities' area reviews are unchanged — what changed is that the site no longer converts silence into reassurance.


### Feedback

Wandroz doesn't have a public feedback form yet. If something here looks wrong, that's useful to know — this page will get a proper reporting mechanism as the site matures.
