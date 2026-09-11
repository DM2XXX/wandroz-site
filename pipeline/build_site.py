"""
Wandroz — static site generator (v0.1 prototype)

Renders one HTML page per city + one page per neighbourhood/borough from
the structured JSON produced by the scoring scripts (e.g. score_london.py),
using a single Jinja2 template. This is a plain-Python/Jinja2 generator
rather than a JS framework (Astro/Next) because this sandbox's network
policy blocks the npm registry, so a Node toolchain can't be installed or
tested here. The output is plain static HTML/CSS with no build step
required at deploy time — it can be hosted for free on literally any
static host (Vercel, Netlify, Cloudflare Pages, GitHub Pages) and is a
reasonable permanent choice, not just a workaround: no JS framework is
actually needed for content pages like these.

Re-running this script after score_london.py (or an equivalent script for
another city) regenerates every page from the current JSON — this is the
"templated, database-driven" architecture the project needs to scale to
many cities, proven out end-to-end here with one real city.
"""

import json
import os
import re
import shutil
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data", "scores")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ZONES_DIR = os.path.join(BASE_DIR, "data_zones")
OUT_DIR = os.path.join(BASE_DIR, "..", "dist")

# Canonical public URL — apex wandroz.com 308-redirects to this host on
# Vercel, so this is what canonical/OG tags and the sitemap should use.
SITE_URL = "https://www.wandroz.com"

# "Report a correction" mailto target, shown on every neighbourhood/borough
# detail page. Update this if the project ever gets a dedicated address
# (e.g. corrections@wandroz.com) instead of a personal inbox.
CORRECTION_EMAIL = "hellowandroz@gmail.com"

# Every city with a map page, used to populate the "City" switcher shown on
# every map page (top-right, next to the Day/Night toggle) so a visitor can
# jump straight from one city's map to another's without going back home.
CITY_LINKS = [
    {"label": "London", "url": f"{SITE_URL}/london/"},
    {"label": "Berlin", "url": f"{SITE_URL}/berlin/"},
    {"label": "Amsterdam", "url": f"{SITE_URL}/amsterdam/"},
    {"label": "Turin", "url": f"{SITE_URL}/torino/"},
    {"label": "Zurich", "url": f"{SITE_URL}/zurigo/"},
    {"label": "Milan", "url": f"{SITE_URL}/milano/"},
    {"label": "Rome", "url": f"{SITE_URL}/roma/"},
    {"label": "Prague", "url": f"{SITE_URL}/praha/"},
    {"label": "Oslo", "url": f"{SITE_URL}/oslo/"},
    {"label": "Munich", "url": f"{SITE_URL}/monaco-di-baviera/"},
    {"label": "Stockholm", "url": f"{SITE_URL}/stockholm/"},
    {"label": "Barcelona", "url": f"{SITE_URL}/barcelona/"},
    {"label": "Madrid", "url": f"{SITE_URL}/madrid/"},
    {"label": "Vienna", "url": f"{SITE_URL}/vienna/"},
    {"label": "Lisbon", "url": f"{SITE_URL}/lisbon/"},
    {"label": "Paris", "url": f"{SITE_URL}/paris/"},
    {"label": "Brussels", "url": f"{SITE_URL}/brussels/"},
    {"label": "Athens", "url": f"{SITE_URL}/athens/"},
    {"label": "Venice", "url": f"{SITE_URL}/venezia/"},
    {"label": "Dublin", "url": f"{SITE_URL}/dublin/"},
    {"label": "Florence", "url": f"{SITE_URL}/firenze/"},
    {"label": "Edinburgh", "url": f"{SITE_URL}/edinburgh/"},
    {"label": "Naples", "url": f"{SITE_URL}/napoli/"},
    {"label": "Budapest", "url": f"{SITE_URL}/budapest/"},
    {"label": "Kraków", "url": f"{SITE_URL}/krakow/"},
]

# --- Central methodology classification -----------------------------------
#
# Every "illustrative" city (everything render_illustrative_city renders —
# i.e. every city except London, which has its own real automated
# data.police.uk pipeline) actually falls into one of three genuinely
# different evidence tiers, even though a single FAQ generator used to talk
# about all of them the same way ("qualitative first-pass... general local
# knowledge and public reputation") regardless of which tier applied. That
# mismatch is exactly the contradiction flagged in the September 2026 deep
# QA review: e.g. Berlin/Amsterdam/Prague/Oslo/Munich/Stockholm/Brussels/
# Edinburgh are driven by a real official police/government statistic (see
# each city's own *_BANNER text below, which already discloses this
# correctly) yet their FAQ implied a guess. This dict is the single source
# of truth for that classification — build_faq_illustrative(), the legend
# text and the homepage's per-city evidence tag all read from it, so a
# newly added city only needs one correct entry here instead of getting
# fixed in three separate places later.
#
# Tiers:
#   OFFICIAL_SNAPSHOT   — a real official government/police crime statistic
#                         (usually one annual figure, no time-of-day split)
#                         actually drives the zone ratings.
#   RESEARCH_BASED      — Wandroz's "Level 2" approach: genuine, current,
#                         dated local/national press and/or official-survey
#                         research per area, honestly disclosed as such
#                         (not an official crime feed).
#   MANUAL_EXPERIMENTAL — a first manual pass based on general local
#                         knowledge/public reputation, not a geolocated
#                         crime dataset and not sourced research per area.
#
# crime_source, where given, is a short human-readable citation used in FAQ
# copy for OFFICIAL_SNAPSHOT cities — kept short deliberately; the full
# citation with dataset names/years lives in each city's *_BANNER text.
OFFICIAL_SNAPSHOT = "OFFICIAL_SNAPSHOT"
RESEARCH_BASED = "RESEARCH_BASED"
MANUAL_EXPERIMENTAL = "MANUAL_EXPERIMENTAL"

CITY_METHODOLOGY = {
    "berlin": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Polizei Berlin's official Häufigkeitszahl crime statistic (Kriminalitätsatlas Berlin)"},
    "amsterdam": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "CBS (Statistics Netherlands)'s official registered-crime statistics"},
    "praha": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Policie ČR's official crime statistics (kriminalita.policie.gov.cz)"},
    "oslo": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Oslo kommune's official Statistikkbanken crime statistics"},
    "munich": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Polizeipräsidium München's official recorded-offence statistics"},
    "stockholm": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Brå (Brottsförebyggande rådet)'s official crime statistics"},
    "brussels": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "BISA / Federale Politie's official crime statistics"},
    # Edinburgh is deliberately NOT OFFICIAL_SNAPSHOT. Its figures are a secondary
    # analysis of Scottish Government/Police Scotland data (Churchill Support
    # Services, corroborated by datamap-scotland), not a first-party official
    # neighbourhood crime feed like Berlin's or Amsterdam's. crime_source is kept
    # for provenance even though the RESEARCH_BASED branch does not cite it: the
    # conservative user-facing claim is worth more than another green city.
    "edinburgh": {"tier": RESEARCH_BASED, "crime_source": "a numeric crimes-per-1,000-population analysis of Scottish Government/Police Scotland data, independently corroborated by a second analysis"},
    "milano": {"tier": RESEARCH_BASED},
    "roma": {"tier": RESEARCH_BASED},
    "barcelona": {"tier": RESEARCH_BASED},
    "madrid": {"tier": RESEARCH_BASED},
    "vienna": {"tier": RESEARCH_BASED},
    "lisbon": {"tier": RESEARCH_BASED},
    "paris": {"tier": RESEARCH_BASED},
    "athens": {"tier": RESEARCH_BASED},
    "venezia": {"tier": RESEARCH_BASED},
    "dublin": {"tier": RESEARCH_BASED},
    "napoli": {"tier": RESEARCH_BASED},
    "budapest": {"tier": RESEARCH_BASED},
    "krakow": {"tier": RESEARCH_BASED},
    "firenze": {"tier": RESEARCH_BASED},
    "torino": {"tier": MANUAL_EXPERIMENTAL},
    "zurigo": {"tier": MANUAL_EXPERIMENTAL},
}


# The per-page evidence tag shown at the top of every neighbourhood/borough
# page. Derived from CITY_METHODOLOGY so a city's label can never drift from
# its declared tier — which is exactly how this element went missing from
# source in the first place: it was hand-patched into dist/ for 19 of 25
# cities and never existed in the generator, so a clean rebuild silently
# dropped it from 1,053 live pages.
#
# Wording is deliberately conservative. MANUAL_EXPERIMENTAL gets a neutral
# label rather than anything implying a data source, because Turin and Zurich
# have none: their ratings are a qualitative first pass.
EVIDENCE_TAG = {
    OFFICIAL_SNAPSHOT: "🟢 Official crime data",
    RESEARCH_BASED: "🟡 Local source research",
    MANUAL_EXPERIMENTAL: "⚪ Manual first-pass rating",
}

# London is not in CITY_METHODOLOGY — it has its own automated pipeline built
# directly on data.police.uk, which is the strongest source on the site, so it
# carries the official-data label on its own terms rather than by inheritance.
LONDON_EVIDENCE_TAG = "🟢 Official crime data"

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)


def _canon(name):
    """Normalise a borough/neighbourhood name for matching across two
    slightly different naming conventions (e.g. 'Kensington & Chelsea' vs
    'Kensington and Chelsea')."""
    name = name.lower().replace("&", " and ")
    tokens = [t for t in re.split(r"[\s\-_]+", name) if t and t != "and"]
    return "".join(tokens)


def load_london_boundaries():
    """Real London borough boundary polygons (ONS 2021 LSOA boundaries,
    dissolved per borough), sourced from the earlier map prototype. Used to
    replace the ~1-mile-radius circle shown on borough pages with the
    borough's actual administrative outline."""
    path = os.path.join(ZONES_DIR, "london_boundaries.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return {_canon(z["name"]): z for z in data["zones"]}


def attach_boundaries(cities):
    """Attach a real boundary polygon to each London borough dict (in
    place) where a match exists, so borough.html can render an accurate
    outline instead of the point+radius circle."""
    boundaries = load_london_boundaries()
    if not boundaries:
        return
    for city in cities:
        if city["city"].lower() != "london":
            continue
        for b in city["boroughs"]:
            match = boundaries.get(_canon(b["borough"]))
            if match:
                b["coords"] = match["coords"]


EN_TONE_BADGE = {"green": "Relatively safer", "yellow": "Average", "red": "Higher caution advised", "grey": "Not yet covered automatically"}

# Short, plain-language descriptor for each tone, used inside FAQ answer
# sentences below (EN_TONE_BADGE is a label for a UI badge, not a sentence
# fragment — this is worded to read naturally in a sentence instead).
#
# Deliberately city-scoped ("other West-Endname areas in London", not
# "other areas covered on Wandroz"): tones are assigned independently per
# city (a "green" in Turin and a "green" in Zurich come from two unrelated
# datasets/judgment calls, not one shared scale), so wording that read as a
# cross-city ranking overstated what the data actually supports. See the
# methodology page's comparability note for the same caveat spelled out in
# full.
def tone_descriptor(tone, city_label):
    phrase = {
        "green": "relatively safer than most other neighbourhoods in {city}",
        "yellow": "roughly average compared to other neighbourhoods in {city}",
        "red": "an area where the data suggests extra caution relative to other neighbourhoods in {city}",
        "grey": "not yet covered by a comparative rating",
    }.get(tone, tone)
    return phrase.format(city=city_label) if "{city}" in phrase else phrase


def _faq_jsonld(items):
    """Build a schema.org FAQPage JSON-LD dict from a list of {"q","a"}
    items, for the <script type="application/ld+json"> block on each
    neighbourhood/borough page. Google's rich-result eligibility for FAQ
    snippets isn't guaranteed just by adding this markup, but it's a
    prerequisite, and the plain-language Q&A text underneath also directly
    targets the long-tail "is X safe" search phrasing this project is
    aiming for — useful on its own even before/without a rich snippet."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in items
        ],
    }


def build_faq_illustrative(zone, city_label, burglary=None, tier=MANUAL_EXPERIMENTAL,
                            crime_source=None, has_time_of_day=True):
    """FAQ content for a non-London, non-automated neighbourhood page.

    tier is one of the CITY_METHODOLOGY constants (OFFICIAL_SNAPSHOT /
    RESEARCH_BASED / MANUAL_EXPERIMENTAL) and controls the actual claim
    made about where the rating comes from — this used to be one fixed
    "qualitative first-pass... general local knowledge and public
    reputation" text for every non-London city, which was accurate for
    Turin/Zurich but false for the 8 cities whose ratings are actually
    driven by a real official police/government statistic, and understated
    the 13 press/survey-research cities (which do have genuine, dated,
    per-area sourcing, just not an official crime feed). See
    CITY_METHODOLOGY's docstring above for the full tier definitions.

    has_time_of_day should be False when the underlying source has no
    day/night split at all (every zone's day and night tone identical by
    construction, e.g. Berlin's HZ or Amsterdam's CBS rate) — this drops
    the separate "is X safe at night?" question, which otherwise implies a
    distinct night-specific data point that doesn't exist, and answers the
    "safe at night" framing honestly instead.

    If burglary is given (Zurich only), a data-availability question
    surfaces that one real, narrowly-scoped official data point instead of
    just saying "no data exists"."""
    name = zone["name"]
    day_desc = tone_descriptor(zone["day"], city_label)
    night_desc = tone_descriptor(zone["night"], city_label)

    if tier == OFFICIAL_SNAPSHOT:
        source_phrase = crime_source or "a real official crime statistic"
        basis_sentence = (
            f"This rating is based on {source_phrase}, not a qualitative guess. High-footfall tourist, "
            f"transit or shopping areas can read higher on this kind of measure without that meaning "
            f"elevated risk per visit, since these statistics are normalised against registered residents "
            f"rather than footfall — see the note on this page and the methodology page for the full "
            f"caveats."
        )
    elif tier == RESEARCH_BASED:
        basis_sentence = (
            f"This is Wandroz's Level 2 approach: genuine, current local and national press (and, where "
            f"available, official survey) research for this specific area, honestly disclosed as "
            f"press/survey-based rather than an official government crime statistic — see the note on "
            f"this page and the methodology page for what was checked and how this differs from cities "
            f"with a real official crime feed."
        )
    else:
        basis_sentence = (
            f"This is a qualitative first-pass assessment based on general local knowledge and public "
            f"reputation, not an official geolocated crime dataset and not individually sourced research "
            f"per area — see the note on data limitations below before treating it as more precise than "
            f"it is."
        )

    if has_time_of_day:
        rating_sentence = (
            f"Wandroz currently rates {name} in {city_label} as {day_desc} during the day and "
            f"{night_desc} at night. {basis_sentence}"
        )
        night_faq = {
            "q": f"Is {name} safe at night?",
            "a": (
                f"At night, {name} is rated as {night_desc}. If you're unsure, it's worth checking recent "
                f"local reviews for your specific street or block, since a neighbourhood-wide rating can't "
                f"capture block-by-block variation."
            ),
        }
    else:
        rating_sentence = (
            f"Wandroz currently rates {name} in {city_label} as {day_desc}. {basis_sentence} The source "
            f"data has no day/night breakdown, so this single rating applies at any time of day rather "
            f"than being a distinct night-specific figure."
        )
        night_faq = {
            "q": f"Does {name}'s rating differ between day and night?",
            "a": (
                f"No — {name}'s source data has no time-of-day breakdown, so the same rating ({day_desc}) "
                f"is shown for both day and night rather than Wandroz inventing a separate night figure "
                f"it doesn't actually have."
            ),
        }

    faqs = [
        {"q": f"Is {name} safe?", "a": rating_sentence},
        night_faq,
        {
            "q": f"Is {name} a good area to stay in as a tourist?",
            "a": (
                f"{name}'s day rating ({day_desc}) is the more relevant one for typical daytime tourist "
                f"activity; check the night rating too if you'll be out late. You can search accommodation "
                f"already filtered to this specific area using the Booking.com link on this page."
            ),
        },
    ]
    if burglary:
        faqs.append({
            "q": f"Is there any official crime data for {name}?",
            "a": (
                f"Partially. {name} sits in {burglary['kreis_label']}, one of Zurich's 12 police districts. "
                f"Kantonspolizei Zürich publishes a real, current burglary rate for that district — "
                f"{burglary['rate_avg_per_1000']} per 1,000 residents"
                + (
                    f", {round(burglary['vs_city_average'] * 100)}% of the 12-district average"
                    if burglary.get("city_average_rate_per_1000") else ""
                )
                + f". This covers burglaries only, not all crime types, and is reported at district level, "
                  f"not specifically for {name} — see the box below for the full figure and caveats. The "
                  f"neighbourhood-wide rating above is still the qualitative first-pass described above, "
                  f"not derived from this burglary figure."
            ),
        })
    elif tier == OFFICIAL_SNAPSHOT:
        faqs.append({
            "q": f"Is there official crime data for {name}?",
            "a": (
                f"Yes. {name}'s rating is derived from {crime_source or 'a real official crime statistic'}, "
                f"not a qualitative guess or press research — see the note on this page for the exact "
                f"figure and the methodology page for full sourcing."
            ),
        })
    elif tier == RESEARCH_BASED:
        faqs.append({
            "q": f"Is there official crime data for {name}?",
            "a": (
                f"Not an official government crime feed — {name}'s rating comes from Wandroz's own current "
                f"local/national press and survey research for this specific area instead (see the note on "
                f"this page for what was checked and the sources used). An absence of recent negative "
                f"coverage is treated as inconclusive, not as proof the area is safe. If you live in or "
                f"know {name} well, you can suggest a correction using the link below."
            ),
        })
    else:
        faqs.append({
            "q": f"Is there official crime data for {name}?",
            "a": (
                f"Not yet at neighbourhood level. Unlike London, this city does not currently publish an "
                f"open, geolocated crime dataset at this level of detail (checked against the relevant local "
                f"and national open-data portals — see the methodology page for what was checked). If you "
                f"live in or know {name} well, you can suggest a correction to its rating using the link "
                f"below."
            ),
        })
    return faqs


def build_faq_london(b, city_label="London"):
    """FAQ content for a London borough page — grounded in the real,
    automated UK Police data this page is built from (incident counts,
    category mix, workday-population normalisation), unlike the
    illustrative Turin/Zurich version above."""
    name = b["borough"]
    day_desc = tone_descriptor(b.get("day_tone"), city_label)
    night_desc = tone_descriptor(b.get("night_tone"), city_label)
    window = (
        f"{len(b['months_included'])} months ({b['months_included'][-1]} to {b['months_included'][0]})"
        if b.get("months_included") and len(b["months_included"]) > 1
        else f"the month of {b.get('data_month')}"
    )
    faqs = [
        {
            "q": f"Is {name} safe?",
            "a": (
                f"Based on real, current UK Police data, Wandroz rates {name} as {day_desc} during the day "
                f"and {night_desc} at night, relative to the other London boroughs currently on the "
                f"automated pipeline. The rating comes from {b.get('sample_record_count')} recorded "
                f"incidents over {window}, split into a day-weighted score (property crime) and a "
                f"night-weighted score (violence, robbery, antisocial behaviour)."
            ),
        },
        {
            "q": f"Is {name} safe at night?",
            "a": (
                f"{name}'s night score is {night_desc}, based on the categories most relevant after dark "
                f"(violence, robbery, street theft, public order, antisocial behaviour), normalised by an "
                f"estimated workday/footfall population rather than plain residents where that data exists, "
                f"so busy central boroughs aren't overstated as riskier just for having fewer official "
                f"residents."
            ),
        },
        {
            "q": f"What official data is {name}'s rating based on?",
            "a": (
                f"{b.get('sample_record_count')} recorded incidents from data.police.uk (the UK Police's "
                f"official open crime API), queried against {name}'s real administrative boundary and "
                f"covering {window} — refreshed automatically every month, not a one-off snapshot. Full "
                f"category breakdown is shown further down this page."
            ),
        },
    ]
    return faqs

# Zurich's 34 Statistische Quartiere grouped by their parent Kreis (city
# district) — sourced from the German Wikipedia "Kreis (Zürich)" article
# and cross-checked name-for-name against data_zones/zurigo.json's 34
# zones (exact match). Kantonspolizei Zürich's real burglary dataset (see
# fetch_zurich.py / score_zurich.py) is only published at Kreis level, not
# per-Quartier, so this mapping is how a real Kreis-level figure gets
# attached to each Quartier page — every Quartier in a Kreis shows that
# Kreis's number, so this is an inherited/coarser figure, not a
# Quartier-specific one, and is disclosed as such in neighbourhood.html.
KREIS_TO_QUARTIERE = {
    1: ["Rathaus", "Hochschulen", "Lindenhof", "City"],
    2: ["Wollishofen", "Leimbach", "Enge"],
    3: ["Alt-Wiedikon", "Friesenberg", "Sihlfeld"],
    4: ["Werd", "Langstrasse", "Hard"],
    5: ["Gewerbeschule", "Escher Wyss"],
    6: ["Unterstrass", "Oberstrass"],
    7: ["Fluntern", "Hottingen", "Hirslanden", "Witikon"],
    8: ["Seefeld", "Mühlebach", "Weinegg"],
    9: ["Albisrieden", "Altstetten"],
    10: ["Höngg", "Wipkingen"],
    11: ["Affoltern", "Oerlikon", "Seebach"],
    12: ["Saatlen", "Schwamendingen-Mitte", "Hirzenbach"],
}
QUARTIER_TO_KREIS = {name: k for k, names in KREIS_TO_QUARTIERE.items() for name in names}


def load_zurich_burglary():
    """Loads score_zurich.py's output (data/scores/zurich_burglary.json)
    if it exists. Returns {} if the file is missing or has no scored
    Kreise yet (e.g. this sandbox, or before the first real GitHub Actions
    run) — callers treat that the same as "no real data available yet"."""
    path = os.path.join(DATA_DIR, "zurich_burglary.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def build_zurich_zone_burglary():
    """Maps each of Zurich's 34 Quartier names to a burglary disclosure
    dict inherited from its parent Kreis, via QUARTIER_TO_KREIS. Returns {}
    if no Kreis has scored data yet, so render_illustrative_city's
    zurich call simply renders with no burglary note (identical to
    Turin) rather than breaking."""
    burglary = load_zurich_burglary()
    kreise = burglary.get("kreise") or {}
    if not kreise:
        return {}
    city_avg = burglary.get("city_average_rate_per_1000")
    zone_data = {}
    for quartier, kreis_n in QUARTIER_TO_KREIS.items():
        rec = kreise.get(f"kreis_{kreis_n}")
        if not rec:
            continue
        merged = dict(rec)
        merged["city_average_rate_per_1000"] = city_avg
        zone_data[quartier] = merged
    return zone_data


def render_illustrative_city(city_key, url_slug, ui, tone_badge, data_note_banner, neigh_note, extra_zone_data=None, flat=False):
    """Render a full-city interactive map (day/night toggle, click-a-zone
    detail sidebar) plus one detail sub-page per neighbourhood, for a city
    whose ratings are an illustrative first pass rather than an automated
    pipeline (Turin, Zurich today). Mirrors the original map prototype's
    UX exactly, instead of the flat card-grid list this replaces.

    extra_zone_data, if given, is a dict keyed by zone name (e.g. from
    build_zurich_zone_burglary()) merged into each zone's neighbourhood-
    page context as zone_ctx["burglary"], and into the interactive map's
    per-zone JS data too — used to attach a real, narrowly-scoped official
    data point on top of the illustrative day/night rating, without
    changing that rating itself or affecting cities that don't pass this
    in (Turin). When present, the map also gets an optional "real burglary
    data" toggle (show_burglary_toggle) that recolours zones by their
    Kreis's burglary tone instead of the manual day/night tone, so the one
    real data layer Zurich has is visible on the map itself, not just
    buried in each zone's detail page.

    flat=True writes each neighbourhood page as {url_slug}/{slug}.html
    instead of {url_slug}/{slug}/index.html — same convention already used
    for London's borough pages (render_london_map/borough.html below).
    This exists for Roma specifically: with 155 zones, deploying via
    GitHub's browser-based web-upload UI (the only permitted deployment
    mechanism for this project — no git CLI, no stored credentials) can't
    recreate 155 nested per-zone subdirectories, since that upload UI's
    file input has no webkitdirectory/folder support reachable through
    browser automation — only a flat multi-file selection, which can be
    batched into a handful of commits instead of ~155 individual ones."""
    path = os.path.join(ZONES_DIR, f"{city_key}.json")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        data = json.load(f)
    zones = data["zones"]
    urls = []

    # Some cities' underlying data has no time-of-day split at all (Berlin's
    # HZ, Amsterdam's CBS rate — every zone's day and night tone are
    # identical by construction, disclosed in each zone's text). Showing a
    # day/night switch that visibly does nothing when clicked reads as
    # broken (reported for both cities), so the switch itself is only
    # rendered when at least one zone actually varies between day and
    # night — detected here from the real data rather than hardcoded per
    # city, so it stays correct automatically if a city's data changes.
    show_toggle = any(z["day"] != z["night"] for z in zones)

    methodology = CITY_METHODOLOGY.get(city_key, {"tier": MANUAL_EXPERIMENTAL})
    tier = methodology["tier"]
    crime_source = methodology.get("crime_source")

    # The shared legend's yellow line ("Caution — fine by day, be more
    # careful in the evening/night", inherited from TORINO_UI by every
    # city) implies a real day/night distinction. That's true for cities
    # where show_toggle is on, but false-precision for the ones where every
    # zone's day and night tone is identical by construction (no
    # time-of-day data in the source at all) — so this swaps in wording
    # that doesn't claim a day/night split that isn't there, driven by the
    # same real show_toggle signal the map's own toggle switch already
    # uses, rather than a second hardcoded flag that could drift out of
    # sync with it.
    legend_yellow = ui["legend_yellow"] if show_toggle else "Caution — some risk factors reported, no particular time-of-day pattern in the data"

    city_dir = os.path.join(OUT_DIR, url_slug)
    os.makedirs(city_dir, exist_ok=True)

    js_zones = []
    for z in zones:
        z_url = f"/{url_slug}/{z['slug']}.html" if flat else f"/{url_slug}/{z['slug']}/"
        zone_js = {
            "name": z["name"], "slug": z["slug"],
            "day": z["day"], "night": z["night"],
            "day_label": tone_badge.get(z["day"], z["day"]),
            "night_label": tone_badge.get(z["night"], z["night"]),
            "text": z["text"], "query": z["query"],
            "coords": z["coords"], "url": z_url,
        }
        if extra_zone_data:
            zone_js["burglary"] = extra_zone_data.get(z["name"])
        js_zones.append(zone_js)

    map_tpl = env.get_template("city_map.html")
    canonical = f"{SITE_URL}/{url_slug}/"
    html = map_tpl.render(
        lang="en", city_label=data["label"], tagline=ui["tagline"],
        nav_home=ui["nav_home"], nav_methodology=ui["nav_methodology"],
        page_title=ui["page_title"], page_description=ui["page_description"],
        canonical_url=canonical, city_links=CITY_LINKS,
        page_h1=ui["page_h1"], page_lead=ui["page_lead"],
        data_note=data_note_banner, show_toggle=show_toggle,
        label_day=ui["label_day"], label_night=ui["label_night"],
        legend_green=ui["legend_green"], legend_yellow=legend_yellow,
        legend_red=ui["legend_red"], legend_grey=ui["legend_grey"],
        label_zone_detail=ui["label_zone_detail"], label_click_hint=ui["label_click_hint"],
        label_all_zones=ui["label_all_zones"], label_booking=ui["label_booking"],
        label_more=ui["label_more"], label_not_covered="",
        footer_note=ui["footer_note"],
        zones=js_zones, center=data["center"], zoom=data["zoom"],
        show_burglary_toggle=bool(extra_zone_data),
    )
    with open(os.path.join(city_dir, "index.html"), "w") as f:
        f.write(html)
    urls.append(canonical)
    print(f"Wrote {os.path.join(city_dir, 'index.html')} ({len(zones)} zones)")

    neigh_tpl = env.get_template("neighbourhood.html")
    for z in zones:
        if flat:
            out_path = os.path.join(city_dir, f"{z['slug']}.html")
            z_canonical = f"{SITE_URL}/{url_slug}/{z['slug']}.html"
        else:
            zdir = os.path.join(city_dir, z["slug"])
            os.makedirs(zdir, exist_ok=True)
            out_path = os.path.join(zdir, "index.html")
            z_canonical = f"{SITE_URL}/{url_slug}/{z['slug']}/"
        zone_ctx = dict(z)
        zone_ctx["day_label"] = tone_badge.get(z["day"], z["day"])
        zone_ctx["night_label"] = tone_badge.get(z["night"], z["night"])
        if extra_zone_data:
            zone_ctx["burglary"] = extra_zone_data.get(z["name"])
        faq_items = build_faq_illustrative(
            zone_ctx, data["label"], burglary=zone_ctx.get("burglary"),
            tier=tier, crime_source=crime_source, has_time_of_day=show_toggle,
        )
        page = neigh_tpl.render(
            lang="en", city_label=data["label"], tagline=ui["tagline"],
            nav_home=ui["nav_home"], canonical_url=z_canonical,
            page_title=ui["neigh_title"].format(name=z["name"], city=data["label"]),
            page_description=z["text"][:160],
            zone=zone_ctx, show_toggle=show_toggle,
            label_day=ui["label_day"], label_night=ui["label_night"],
            label_detail=ui["label_detail"], label_booking=ui["label_booking"],
            label_booking_note=ui["label_booking_note"], data_note=neigh_note,
            footer_note=ui["footer_note"], correction_email=CORRECTION_EMAIL,
            evidence_tag=EVIDENCE_TAG.get(tier),
            faq_items=faq_items, faq_schema=_faq_jsonld(faq_items),
        )
        with open(out_path, "w") as f:
            f.write(page)
        urls.append(z_canonical)

    print(f"Wrote {len(zones)} neighbourhood pages under {city_dir}/")
    return urls


def render_london_map(cities):
    """Render the London city-wide map hub (/london/) with every one of the
    33 real ONS borough boundaries fully populated — day/night toggle,
    description and Booking.com link on click, same as Turin/Zurich — using
    the real Met Police data this map was originally built from. The 5
    boroughs the automated pipeline currently refreshes every month
    (Westminster, Camden, Islington, Kensington & Chelsea, Lambeth) get
    their polygon colour AND their sidebar text replaced with the real,
    live-computed day/night rating from score_london.py (category-mix day/
    night split, workday-population corrected — see that module's
    docstring) plus a link through to the auto-updating page; the rest show
    the same baked-in real dataset the map was originally built from, just
    not on the automatic monthly refresh yet — never blank/grey
    placeholders."""
    boundaries = load_london_boundaries()
    if not boundaries:
        return []
    london = next((c for c in cities if c["city"].lower() == "london"), None)
    live = {}
    if london:
        for b in london["boroughs"]:
            live[_canon(b["borough"])] = {
                "slug": b["slug"], "rank": b["relative_rank"],
                "count": b["sample_record_count"], "month": b["data_month"],
                "day_tone": b["day_tone"], "night_tone": b["night_tone"],
                "day_label": EN_TONE_BADGE.get(b["day_tone"], b["day_tone"]),
                "night_label": EN_TONE_BADGE.get(b["night_tone"], b["night_tone"]),
                "day_vs_avg": b.get("day_vs_covered_average"),
                "night_vs_avg": b.get("night_vs_covered_average"),
            }

    js_zones = []
    live_count = 0
    for name_key, z in boundaries.items():
        entry = {
            "name": z["name"], "day": z["day"], "night": z["night"],
            "day_label": EN_TONE_BADGE.get(z["day"], z["day"]),
            "night_label": EN_TONE_BADGE.get(z["night"], z["night"]),
            "text": z["text"], "query": z["query"], "coords": z["coords"], "url": "",
        }
        match = live.get(_canon(z["name"]))
        if match:
            live_count += 1
            entry["url"] = f"/london/{match['slug']}.html"
            # Live boroughs get their colour AND label replaced by the real
            # computed rating — the baked tester value is only a fallback
            # for boroughs not yet on the automated pipeline.
            entry["day"] = match["day_tone"]
            entry["night"] = match["night_tone"]
            entry["day_label"] = match["day_label"]
            entry["night_label"] = match["night_label"]
            entry["text"] = (
                entry["text"] + f" Automatically kept current from official Metropolitan Police data: day "
                f"{match['day_label'].lower()}, night {match['night_label'].lower()} "
                f"({match['count']} recorded incidents, {match['month']})."
            )
        js_zones.append(entry)

    london_dir = os.path.join(OUT_DIR, "london")
    os.makedirs(london_dir, exist_ok=True)
    map_tpl = env.get_template("city_map.html")
    canonical = f"{SITE_URL}/london/"
    total_zones = len(js_zones)
    not_covered = total_zones - live_count
    if live_count >= total_zones - 1:
        # The only realistic gap left is the City of London (structurally
        # excluded — separate police force), so say so plainly instead of
        # a vague "the rest" once coverage is effectively complete.
        coverage_sentence = (
            f"{live_count} of {total_zones} boroughs — every London borough except the City of London, which is "
            "policed separately and isn't covered by this dataset — are refreshed automatically every month."
        )
    else:
        coverage_sentence = (
            f"{live_count} of {total_zones} boroughs are refreshed automatically every month; the other "
            f"{not_covered} reflect the same real dataset from when this map was built and aren't on the automatic "
            "refresh yet."
        )
    data_note = (
        f"Boundaries and ratings are based on real Metropolitan Police crime data (data.police.uk). {coverage_sentence} "
        "Each covered borough's day score (property crime) and night score (violence, robbery, street theft, public "
        "order, anti-social behaviour — a category-mix proxy, not literal time-stamped data) are normalised by an "
        f"estimated workday/footfall population rather than resident population, then rated against the AVERAGE of "
        f"the {live_count} boroughs currently covered (not yet a fixed, borough-independent scale). Click one and "
        "follow the link for the live current numbers and full methodology."
    )
    html = map_tpl.render(
        lang="en", city_label="London", tagline="Neighbourhood safety for travellers",
        nav_home="Home", nav_methodology="Methodology", canonical_url=canonical, city_links=CITY_LINKS,
        page_title="Is my London borough safe? — Wandroz",
        page_description="Interactive map of all 33 London boroughs, day/night ratings from real Metropolitan Police data, 5 refreshed automatically every month.",
        page_h1="London boroughs", page_lead="Click a borough on the map to see its level, the reasoning, and a Booking.com link for that area.",
        data_note=data_note, show_toggle=True,
        label_day="day", label_night="night",
        legend_green=EN_TONE_BADGE["green"], legend_yellow=EN_TONE_BADGE["yellow"],
        legend_red=EN_TONE_BADGE["red"], legend_grey=EN_TONE_BADGE["grey"],
        label_zone_detail="Borough detail", label_click_hint="Click a borough on the map to see its level, the reasoning, and a Booking.com link for that area.",
        label_all_zones="All boroughs", label_booking="Search accommodation here on Booking.com →",
        label_more="See the auto-updating live data →",
        label_not_covered="",
        footer_note="public official data, not just reviews. In beta — coverage is expanding.",
        zones=js_zones, center=[51.509, -0.118], zoom=10,
    )
    with open(os.path.join(london_dir, "index.html"), "w") as f:
        f.write(html)
    print(f"Wrote {os.path.join(london_dir, 'index.html')} ({len(js_zones)} boroughs, {live_count} auto-refreshed)")
    return [canonical]


def build_search_index(cities, city_cards):
    """Build the homepage search bar's data source, purely from real content
    that already exists elsewhere in the pipeline — no invented names, no
    placeholder entries. Covers: the top-level city cards (same 5 shown on
    the homepage map); every London borough that actually has its own live
    page (the automated-pipeline set in `cities`, not all 33 — the other
    boroughs have no individual URL to send someone to); and every zone in
    each illustrative city's data_zones JSON (Torino/Zurigo/Milano nested
    URLs, Roma flat URLs — mirrors the exact scheme render_illustrative_city
    uses, so a search result always resolves to a real page)."""
    entries = []
    for c in city_cards:
        entries.append({"type": "city", "name": c["name"], "flag": c["flag"], "url": "/" + c["url"]})

    for city in cities:
        city_slug = city["city"].lower().replace(" ", "-")
        for b in city["boroughs"]:
            entries.append({
                "type": "zone", "name": b["borough"], "city": city["city"],
                "url": f"/{city_slug}/{b['slug']}.html",
            })

    illustrative = [
        ("torino", "torino", "Turin", False),
        ("zurigo", "zurigo", "Zurich", False),
        ("milano", "milano", "Milan", False),
        ("roma", "roma", "Rome", True),
        ("berlin", "berlin", "Berlin", True),
        ("amsterdam", "amsterdam", "Amsterdam", True),
        ("praha", "praha", "Prague", True),
        ("oslo", "oslo", "Oslo", True),
        ("munich", "monaco-di-baviera", "Munich", True),
        ("stockholm", "stockholm", "Stockholm", True),
        ("barcelona", "barcelona", "Barcelona", True),
        ("madrid", "madrid", "Madrid", True),
        ("vienna", "vienna", "Vienna", True),
        ("lisbon", "lisbon", "Lisbon", True),
        ("paris", "paris", "Paris", True),
        ("brussels", "brussels", "Brussels", True),
        ("athens", "athens", "Athens", True),
        ("venezia", "venezia", "Venice", True),
        ("dublin", "dublin", "Dublin", True),
        ("edinburgh", "edinburgh", "Edinburgh", True),
        ("napoli", "napoli", "Naples", True),
        ("budapest", "budapest", "Budapest", True),
        ("krakow", "krakow", "Kraków", True),
        ("firenze", "firenze", "Florence", True),
    ]
    for city_key, url_slug, label, flat in illustrative:
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for z in data["zones"]:
            z_url = f"/{url_slug}/{z['slug']}.html" if flat else f"/{url_slug}/{z['slug']}/"
            entries.append({"type": "zone", "name": z["name"], "city": label, "url": z_url})

    return entries


def build_zone_boundaries(cities, city_cards):
    """Real per-zone polygon boundaries, exported for the homepage's
    address search (see templates/index.html) to do a client-side
    point-in-polygon match against a geocoded address — the exact same
    polygons the interactive maps already draw (render_illustrative_city /
    render_london_map), never an approximated or fabricated shape.

    Also emits a padded bounding box per city (from the real union of that
    city's own zone coordinates, not a hand-picked radius) so an address
    that geocodes just outside the outermost mapped zone but still clearly
    inside the city can fall back to that city's hub page instead of being
    reported as uncovered."""
    zones = []
    city_bbox = {}

    def _extend_bbox(label, coords):
        if not coords or not coords[0]:
            return
        for lat, lon in coords[0]:
            b = city_bbox.setdefault(label, [lat, lon, lat, lon])
            b[0] = min(b[0], lat)
            b[1] = min(b[1], lon)
            b[2] = max(b[2], lat)
            b[3] = max(b[3], lon)

    for city in cities:
        city_slug = city["city"].lower().replace(" ", "-")
        for b in city["boroughs"]:
            if b.get("coords"):
                zones.append({
                    "name": b["borough"], "city": city["city"],
                    "url": f"/{city_slug}/{b['slug']}.html",
                    "coords": b["coords"],
                })
                _extend_bbox(city["city"], b["coords"])

    illustrative = [
        ("torino", "torino", "Turin", False),
        ("zurigo", "zurigo", "Zurich", False),
        ("milano", "milano", "Milan", False),
        ("roma", "roma", "Rome", True),
        ("berlin", "berlin", "Berlin", True),
        ("amsterdam", "amsterdam", "Amsterdam", True),
        ("praha", "praha", "Prague", True),
        ("oslo", "oslo", "Oslo", True),
        ("munich", "monaco-di-baviera", "Munich", True),
        ("stockholm", "stockholm", "Stockholm", True),
        ("barcelona", "barcelona", "Barcelona", True),
        ("madrid", "madrid", "Madrid", True),
        ("vienna", "vienna", "Vienna", True),
        ("lisbon", "lisbon", "Lisbon", True),
        ("paris", "paris", "Paris", True),
        ("brussels", "brussels", "Brussels", True),
        ("athens", "athens", "Athens", True),
        ("venezia", "venezia", "Venice", True),
        ("dublin", "dublin", "Dublin", True),
        ("edinburgh", "edinburgh", "Edinburgh", True),
        ("napoli", "napoli", "Naples", True),
        ("budapest", "budapest", "Budapest", True),
        ("krakow", "krakow", "Kraków", True),
        ("firenze", "firenze", "Florence", True),
    ]
    for city_key, url_slug, label, flat in illustrative:
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for z in data["zones"]:
            z_url = f"/{url_slug}/{z['slug']}.html" if flat else f"/{url_slug}/{z['slug']}/"
            zones.append({"name": z["name"], "city": label, "url": z_url, "coords": z["coords"]})
            _extend_bbox(label, z["coords"])

    city_url_by_label = {c["name"]: "/" + c["url"] for c in city_cards}
    cities_out = []
    for label, bbox in city_bbox.items():
        pad_lat = (bbox[2] - bbox[0]) * 0.08 + 0.01
        pad_lon = (bbox[3] - bbox[1]) * 0.08 + 0.01
        cities_out.append({
            "name": label,
            "url": city_url_by_label.get(label, "/"),
            "bbox": [bbox[0] - pad_lat, bbox[1] - pad_lon, bbox[2] + pad_lat, bbox[3] + pad_lon],
        })

    return {"zones": zones, "cities": cities_out}


def copy_static():
    """Copy favicon/manifest assets into dist/ on every build, so they're
    reproducible from source (pipeline/static/) instead of relying on
    leftover files surviving in dist/ between runs."""
    if not os.path.isdir(STATIC_DIR):
        return []
    copied = []
    for fname in os.listdir(STATIC_DIR):
        src = os.path.join(STATIC_DIR, fname)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(OUT_DIR, fname)
        shutil.copyfile(src, dst)
        copied.append(dst)
    return copied


def write_robots_and_sitemap(urls):
    robots_path = os.path.join(OUT_DIR, "robots.txt")
    with open(robots_path, "w") as f:
        f.write("User-agent: *\nAllow: /\n\nSitemap: {}/sitemap.xml\n".format(SITE_URL))
    print(f"Wrote {robots_path}")

    sitemap_path = os.path.join(OUT_DIR, "sitemap.xml")
    entries = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )
    with open(sitemap_path, "w") as f:
        f.write(xml)
    print(f"Wrote {sitemap_path} ({len(urls)} URLs)")


TORINO_UI = {
    "tagline": "Neighbourhood safety for travellers",
    "nav_home": "Home", "nav_methodology": "Methodology",
    "page_title": "Is my Turin neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Turin's neighbourhoods with the council's real official boundaries, day/night safety levels.",
    "page_h1": "Turin neighbourhoods", "page_lead": "Click a neighbourhood on the map to see its level, the reasoning, and a Booking.com link for that area.",
    "label_day": "day", "label_night": "night",
    "legend_green": "Calm — no particular concern",
    "legend_yellow": "Caution — fine by day, be more careful in the evening/night",
    "legend_red": "Not recommended for a tourist — known, recurring issues",
    "legend_grey": "Not rated — data not comparable for this zone",
    "label_zone_detail": "Zone detail", "label_click_hint": "Click a zone on the map to see its level, the reasoning, and a Booking.com link for that area.",
    "label_all_zones": "All neighbourhoods", "label_booking": "Search accommodation here on Booking.com →",
    "label_more": "See the full page →",
    "footer_note": "in beta — coverage is expanding",
    "neigh_title": "Is {name} in Turin safe? | Wandroz",
    "label_detail": "In detail", "label_booking_note": "This link is already scoped to this area (not the whole city), using the neighbourhood's real coordinates.",
}

ZURIGO_UI = dict(TORINO_UI)
ZURIGO_UI.update({
    "page_title": "Is my Zurich neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Zurich's neighbourhoods with the city's real official boundaries, day/night safety levels.",
    "page_h1": "Zurich neighbourhoods",
    "neigh_title": "Is {name} in Zurich safe? | Wandroz",
})

MILANO_UI = dict(TORINO_UI)
MILANO_UI.update({
    "page_title": "Is my Milan neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Milan's neighbourhoods (real official NIL boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Milan neighbourhoods",
    "neigh_title": "Is {name} in Milan safe? | Wandroz",
})

ROMA_UI = dict(TORINO_UI)
ROMA_UI.update({
    "page_title": "Is my Rome neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Rome's neighbourhoods (real official Zone Urbanistiche boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Rome neighbourhoods",
    "neigh_title": "Is {name} in Rome safe? | Wandroz",
})

BARCELONA_UI = dict(TORINO_UI)
BARCELONA_UI.update({
    "page_title": "Is my Barcelona neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Barcelona's 73 official barris (real official Ajuntament boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Barcelona neighbourhoods",
    "neigh_title": "Is {name} in Barcelona safe? | Wandroz",
})

TORINO_BANNER = (
    "Neighbourhood shapes are the City of Turin's real official boundaries (the \"Quartieri\" dataset). Safety "
    "levels, on the other hand, are a first manual pass — general knowledge, not a geolocated crime dataset — "
    "unlike London. See the methodology page for details."
)
TORINO_NEIGH_NOTE = (
    "Risk levels for Turin are a qualitative judgment call based on general knowledge and public reputation of "
    "each neighbourhood, not an official geolocated crime dataset — unlike London, no open municipal dataset at "
    "this level of detail exists yet for Turin."
)
ZURIGO_BANNER = (
    "Neighbourhood shapes are the City of Zurich's real official boundaries (the \"Statistische Quartiere\" "
    "dataset). Safety levels are a first manual pass — general knowledge, not a geolocated crime dataset — unlike "
    "London. Where available, each neighbourhood page below also shows one real, official data point: the "
    "Kantonspolizei Zürich's burglary rate for its wider city district (Kreis) — narrower and coarser than "
    "London's pipeline, but genuine and current. See the methodology page for details."
)
ZURIGO_NEIGH_NOTE = (
    "Risk levels for Zurich are a qualitative judgment call based on general knowledge and public reputation of "
    "each neighbourhood, not an official geolocated crime dataset — unlike London, no open municipal dataset at "
    "this level of detail exists yet for Zurich."
)

MILANO_BANNER = (
    "Neighbourhood shapes are the Comune di Milano's real official boundaries (the \"Nuclei d'Identità Locale\" "
    "dataset), covering all 88 official zones. Unlike Turin/Zurich's general-knowledge first pass, Milan's safety "
    "levels are Wandroz's Level 2 approach: genuine current local/national press research per area, honestly "
    "disclosed as press-based rather than official crime statistics — no open geolocated crime dataset exists for "
    "Milan (checked against the Comune, Regione Lombardia and local police). Where no specific news coverage was "
    "found for a zone, that is stated plainly rather than assumed either way. See the methodology page for "
    "details and sources."
)
MILANO_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Milan: genuine current local/national press research for this "
    "specific area (not blind guessing, not fabricated crime statistics), honestly disclosed as press-based "
    "rather than official data — no open geolocated crime dataset exists for Milan at neighbourhood level. See "
    "the methodology page for what was checked and how this differs from London's automated official-data pipeline."
)

ROMA_BANNER = (
    "Neighbourhood shapes are Roma Capitale's real official boundaries (the \"Zone Urbanistiche\" dataset, via the "
    "Comune's Geoportale), covering all 155 official zones. Like Milan, Rome's safety levels are Wandroz's Level 2 "
    "approach: genuine current local/national press research per area, honestly disclosed as press-based rather "
    "than official crime statistics — no open geolocated crime dataset exists for Rome (Italy does not publish one "
    "at neighbourhood level). Where no specific news coverage was found for a zone, that is stated plainly rather "
    "than assumed either way. See the methodology page for details and sources."
)
ROMA_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Rome: genuine current local/national press research for this "
    "specific area (not blind guessing, not fabricated crime statistics), honestly disclosed as press-based "
    "rather than official data — no open geolocated crime dataset exists for Rome at neighbourhood level. See "
    "the methodology page for what was checked and how this differs from London's automated official-data pipeline."
)

BARCELONA_BANNER = (
    "Neighbourhood shapes are the Ajuntament de Barcelona's real official administrative boundaries (73 official "
    "\"barris\", grouped into 10 districts), reached via a direct GeoJSON conversion of the Ajuntament's own "
    "shapefile dataset (the portal's own raw endpoint was bot-gated for automated access at build time, so a "
    "mirror that republishes the same official geometry unmodified was used instead). Like Milan, Rome and Turin, "
    "Barcelona's safety levels are Wandroz's Level 2 approach: genuine current local/national press research per "
    "barri, honestly disclosed as press-based rather than official crime statistics — no open geolocated crime "
    "dataset exists for Barcelona at neighbourhood level (checked against the Ajuntament's own open-data portal). "
    "Where no specific news coverage was found for a barri, that is stated plainly rather than assumed either "
    "way. See the methodology page for details and sources."
)
BARCELONA_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Barcelona: genuine current local/national press research for "
    "this specific barri (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — no open geolocated crime dataset exists for Barcelona at "
    "neighbourhood level. See the methodology page for what was checked and how this differs from London's "
    "automated official-data pipeline."
)

MADRID_UI = dict(TORINO_UI)
MADRID_UI.update({
    "page_title": "Is my Madrid neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Madrid's 131 official barrios (real official Ayuntamiento boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Madrid neighbourhoods",
    "neigh_title": "Is {name} in Madrid safe? | Wandroz",
})

MADRID_BANNER = (
    "Neighbourhood shapes are the Ayuntamiento de Madrid's real official administrative boundaries (131 official "
    "\"barrios\", grouped into 21 districts), sourced directly from the city's own Geoportal (geoportal.madrid.es) "
    "TopoJSON dataset. Like Milan, Rome, Turin and Barcelona, Madrid's safety levels are Wandroz's Level 2 "
    "approach: genuine current local/national press research per barrio, honestly disclosed as press-based "
    "rather than official crime statistics — no open geolocated crime dataset exists for Madrid at neighbourhood "
    "level (checked against both the Ayuntamiento's own open-data portal and the Comunidad de Madrid's "
    "statistical offerings). Where no specific news coverage was found for a barrio, that is stated plainly "
    "rather than assumed either way. See the methodology page for details and sources."
)
MADRID_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Madrid: genuine current local/national press research for "
    "this specific barrio (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — no open geolocated crime dataset exists for Madrid at neighbourhood "
    "level. See the methodology page for what was checked and how this differs from London's automated "
    "official-data pipeline."
)

VIENNA_UI = dict(TORINO_UI)
VIENNA_UI.update({
    "page_title": "Is my Vienna neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Vienna's 23 official Bezirke (real official Statistik Austria boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Vienna neighbourhoods",
    "neigh_title": "Is {name} in Vienna safe? | Wandroz",
})

VIENNA_BANNER = (
    "District shapes are Vienna's real official administrative boundaries (the 23 \"Bezirke\"), sourced from "
    "Statistik Austria's own official boundary dataset. Like Milan, Rome, Turin, Barcelona and Madrid, Vienna's "
    "safety levels are Wandroz's Level 2 approach: genuine current local/national press research per district, "
    "honestly disclosed as press-based rather than official crime statistics — Austria has no open, geolocated "
    "Bezirk-level crime dataset (Statistik Austria and the Bundeskriminalamt's PKS only publish at Bundesland/"
    "state level; an internal police spatial-crime-analysis tool exists but is not public). Where no specific "
    "news coverage was found for a district, that is stated plainly rather than assumed either way. See the "
    "methodology page for details and sources."
)
VIENNA_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Vienna: genuine current local/national press research for "
    "this specific district (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — Austria has no open, geolocated Bezirk-level crime dataset. See "
    "the methodology page for what was checked and how this differs from London's automated official-data "
    "pipeline."
)

LISBON_UI = dict(TORINO_UI)
LISBON_UI.update({
    "page_title": "Is my Lisbon neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Lisbon's 24 official freguesias (real official Câmara Municipal de Lisboa boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Lisbon neighbourhoods",
    "neigh_title": "Is {name} in Lisbon safe? | Wandroz",
})

LISBON_BANNER = (
    "Neighbourhood shapes are Lisbon's real official administrative boundaries (the 24 \"freguesias\", civil "
    "parishes since the 2012 reform), sourced directly from the Câmara Municipal de Lisboa's own Lisboa Aberta "
    "open-data portal. Like Milan, Rome, Turin, Barcelona, Madrid and Vienna, Lisbon's safety levels are "
    "Wandroz's Level 2 approach: genuine current local/national press research per freguesia, honestly "
    "disclosed as press-based rather than official crime statistics — Portugal has no open, geolocated "
    "freguesia-level crime dataset (the Sistema de Segurança Interna's annual RASI report is PDF-only and "
    "reports only at municipality/national level). Where no specific news coverage was found for a freguesia, "
    "that is stated plainly rather than assumed either way. See the methodology page for details and sources."
)
LISBON_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Lisbon: genuine current local/national press research for "
    "this specific freguesia (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — Portugal has no open, geolocated freguesia-level crime dataset. "
    "See the methodology page for what was checked and how this differs from London's automated official-data "
    "pipeline."
)

PARIS_UI = dict(TORINO_UI)
PARIS_UI.update({
    "page_title": "Is my Paris neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Paris's 80 official quartiers administratifs (real official City of Paris boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Paris neighbourhoods",
    "neigh_title": "Is {name} in Paris safe? | Wandroz",
})

PARIS_BANNER = (
    "Neighbourhood shapes are Paris's real official administrative boundaries (the 80 \"quartiers "
    "administratifs\", 4 per arrondissement across all 20 arrondissements), sourced directly from the City of "
    "Paris's own opendata.paris.fr open-data portal. Like Milan, Rome, Turin, Barcelona, Madrid, Vienna and "
    "Lisbon, Paris's safety levels are Wandroz's Level 2 approach: genuine current local/national press "
    "research per quartier, honestly disclosed as press-based rather than official crime statistics — France's "
    "SSMSI crime dataset is published only at commune level, and Paris is a single commune, so no official "
    "arrondissement- or quartier-level crime breakdown exists. Where no specific news coverage was found for a "
    "quartier, that is stated plainly rather than assumed either way. See the methodology page for details and "
    "sources."
)
PARIS_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Paris: genuine current local/national press research for "
    "this specific quartier (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — France's SSMSI crime dataset is commune-level only, and Paris is "
    "a single commune. See the methodology page for what was checked and how this differs from London's "
    "automated official-data pipeline."
)

BERLIN_UI = dict(TORINO_UI)
BERLIN_UI.update({
    "page_title": "Is my Berlin neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Berlin's 143 official Bezirksregionen with real official Polizei Berlin crime-rate data (Häufigkeitszahl) per zone.",
    "page_h1": "Berlin neighbourhoods",
    "neigh_title": "Is {name} in Berlin safe? | Wandroz",
})

BERLIN_BANNER = (
    "Neighbourhood shapes are Polizei Berlin's real official \"Bezirksregion\" boundaries (143 zones, via the "
    "Kriminalitätsatlas Berlin / LKA St 14). Unlike Milan and Rome's press-research approach, Berlin's safety "
    "levels come from a real official police statistic — the 2025 Häufigkeitszahl (total recorded offences per "
    "100,000 registered residents) per zone — the same kind of open geolocated data London's pipeline uses, "
    "though here as one annual figure rather than a live day/night feed, so the source data has no time-of-day "
    "breakdown and this map shows one consistent level per zone rather than a day/night toggle. HZ counts "
    "against registered residents, not footfall, so busy tourist, shopping or transit areas can read higher "
    "without that meaning elevated risk per visit — see the methodology page for details."
)
BERLIN_NEIGH_NOTE = (
    "This rating for Berlin is a real official police statistic — Polizei Berlin's 2025 Häufigkeitszahl (total "
    "recorded offences per 100,000 registered residents) for this Bezirksregion — not a qualitative or "
    "press-based judgment. It has no day/night split in the source data, so this single rating applies at any time of day rather than there being a separate night figure. HZ "
    "counts against registered residents, not footfall, so a busy tourist, shopping or transit area can read "
    "higher without that meaning elevated risk per visit. See the methodology page for full sourcing."
)

AMSTERDAM_UI = dict(TORINO_UI)
AMSTERDAM_UI.update({
    "page_title": "Is my Amsterdam neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Amsterdam's 110 official wijken with real official CBS crime-rate data per zone.",
    "page_h1": "Amsterdam neighbourhoods",
    "neigh_title": "Is {name} in Amsterdam safe? | Wandroz",
})

AMSTERDAM_BANNER = (
    "Neighbourhood shapes are the Gemeente Amsterdam's real official \"wijk\" boundaries (110 zones, via "
    "api.data.amsterdam.nl). Like Berlin, Amsterdam's safety levels come from a real official statistic — CBS "
    "(Statistics Netherlands) registered crimes per wijk for 2025, converted to a rate per 100,000 residents "
    "using CBS's own 2025 population figures per wijk — rather than Milan/Rome's press-research approach. This "
    "rate is calculated against registered residents, not footfall, so high-traffic tourist/shopping/transit "
    "areas (like the city centre) can read higher without that meaning elevated risk per visit, and a few very "
    "sparsely populated wijken (harbour/industrial fringe areas) can swing sharply from a handful of cases. The "
    "source data has no time-of-day breakdown, so — like Berlin — this map shows one consistent level per wijk "
    "rather than a day/night toggle; see the methodology page for details."
)
AMSTERDAM_NEIGH_NOTE = (
    "This rating for Amsterdam is a real official statistic — CBS's 2025 registered crimes for this wijk, "
    "converted to a rate per 100,000 residents using CBS's own 2025 population figures — not a qualitative or "
    "press-based judgment. It has no day/night split in the source data, so this single rating applies at any time of day rather than there being a separate night figure. The "
    "rate counts against registered residents, not footfall, so a busy tourist, shopping or transit area can "
    "read higher without that meaning elevated risk per visit, and a very sparsely populated wijk can swing "
    "sharply from a handful of cases. See the methodology page for full sourcing."
)

PRAHA_UI = dict(TORINO_UI)
PRAHA_UI.update({
    "page_title": "Is my Prague neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Prague's 57 official mestske casti (city districts) with real official Policie CR crime-rate data per district.",
    "page_h1": "Prague neighbourhoods",
    "neigh_title": "Is {name} in Prague safe? | Wandroz",
})

PRAHA_BANNER = (
    "Neighbourhood shapes are Prague's real official 57 \"mestske casti\" (city districts, boundaries via "
    "OpenStreetMap's administrative-boundary data). Like Berlin and Amsterdam, Prague's safety levels come from a "
    "real official statistic — Policie CR's (Czech Police) total registered incidents per district for 2024, via "
    "the official kriminalita.policie.gov.cz portal, converted to a rate per 100,000 residents using CSU (Czech "
    "Statistical Office) 2024 population figures per district — rather than Milan/Rome's press-research approach. "
    "This rate is calculated against registered residents, not footfall, so high-traffic tourist/shopping/transit "
    "areas (like Praha 1's historic centre) can read higher without that meaning elevated risk per visit, and a "
    "few very sparsely populated outer districts can swing sharply from a handful of cases. The source data has "
    "no time-of-day breakdown, so — like Berlin and Amsterdam — this map shows one consistent level per district "
    "rather than a day/night toggle; see the methodology page for details."
)
PRAHA_NEIGH_NOTE = (
    "This rating for Prague is a real official statistic — Policie CR's total registered incidents for this "
    "district in 2024 (via kriminalita.policie.gov.cz), converted to a rate per 100,000 residents using CSU's "
    "2024 population figures for the district — not a qualitative or press-based judgment. It has no day/night "
    "split in the source data, so this single rating applies at any time of day rather than there being a separate night figure. The rate counts against registered residents, "
    "not footfall, so a busy tourist, shopping or transit area can read higher without that meaning elevated risk "
    "per visit, and a very sparsely populated district can swing sharply from a handful of cases. See the "
    "methodology page for full sourcing."
)

OSLO_UI = dict(TORINO_UI)
OSLO_UI.update({
    "page_title": "Is my Oslo neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Oslo's 15 official bydeler (city boroughs) plus Sentrum (the city centre) with real official Oslo kommune crime-rate data per zone.",
    "page_h1": "Oslo neighbourhoods",
    "neigh_title": "Is {name} in Oslo safe? | Wandroz",
})

OSLO_BANNER = (
    "Neighbourhood shapes are Oslo's real official 15 bydeler (city boroughs, boundaries via OpenStreetMap's "
    "administrative-boundary data) plus Sentrum, the city centre — 16 zones, none excluded. Like Berlin, Amsterdam "
    "and Prague, Oslo's safety levels come from a real official statistic — Oslo kommune's own Statistikkbanken "
    "figures on reported offences by place of occurrence per bydel for 2024, converted to a rate per 100,000 "
    "residents using the same Statistikkbanken's 2024 population figures per bydel — rather than Milan/Rome's "
    "press-research approach. Sentrum is not one of the 15 administrative bydeler and has no bydel-level population "
    "figure, so its rating instead combines Oslo kommune's own crime figure for Sentrum with a population figure "
    "for the same area from Statistics Norway (SSB); the resulting rate is roughly 60x the citywide average, a "
    "statistical artefact of Sentrum's tiny resident base against its huge footfall — see the methodology page and "
    "Sentrum's own zone page for the full explanation. This rate is calculated against registered residents, not "
    "footfall, so high-traffic central/nightlife/shopping bydeler (like Gamle Oslo or Frogner) can read higher "
    "without that meaning elevated risk per visit. The source data has no time-of-day breakdown, so — like Berlin, "
    "Amsterdam and Prague — this map shows one consistent level per bydel rather than a day/night toggle; see the "
    "methodology page for details."
)
OSLO_NEIGH_NOTE = (
    "This rating for Oslo is a real official statistic — Oslo kommune's own Statistikkbanken figure for reported "
    "offences by place of occurrence in this bydel in 2024, converted to a rate per 100,000 residents using the "
    "same source's 2024 population figure for the bydel — not a qualitative or press-based judgment. It has no "
    "day/night split in the source data, so this single rating applies at any time of day rather than there being a separate night figure. The rate counts against registered "
    "residents, not footfall, so a busy central, nightlife or shopping bydel can read higher without that meaning "
    "elevated risk per visit. See the methodology page for full sourcing."
)

MUNICH_UI = dict(TORINO_UI)
MUNICH_UI.update({
    "page_title": "Is my Munich neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Munich's 25 official Stadtbezirke (city districts) with real official Polizeipraesidium Muenchen crime-rate data per zone.",
    "page_h1": "Munich neighbourhoods",
    "neigh_title": "Is {name} in Munich safe? | Wandroz",
})

MUNICH_BANNER = (
    "Neighbourhood shapes are Munich's real official 25 Stadtbezirke (city districts, boundaries via "
    "GeodatenService München's own boundary data). Like Berlin, Amsterdam, Prague and Oslo, Munich's safety levels "
    "come from a real official statistic — Polizeipräsidium München and the Statistisches Amt München's own "
    "published 2025 total recorded-offence counts per Stadtbezirk, converted to a rate per 100,000 residents using "
    "each district's 31 December 2024 population — rather than Milan/Rome's press-research approach. This rate is "
    "calculated against registered residents, not footfall, so high-traffic central/station/nightlife districts — "
    "especially Altstadt-Lehel (the historic centre around Marienplatz) and Ludwigsvorstadt-Isarvorstadt "
    "(Hauptbahnhof and the Glockenbach nightlife district) — can read higher without that meaning elevated risk "
    "per visit. The source data has no time-of-day breakdown, so — like Berlin, Amsterdam, Prague and Oslo — this "
    "map shows one consistent level per Stadtbezirk rather than a day/night toggle; see the methodology page for "
    "details."
)
MUNICH_NEIGH_NOTE = (
    "This rating for Munich is a real official statistic — Polizeipräsidium München and the Statistisches Amt "
    "München's own published 2025 total recorded-offence count for this Stadtbezirk, converted to a rate per "
    "100,000 residents using the same source's 31 December 2024 population figure for the district — not a "
    "qualitative or press-based judgment. It has no day/night split in the source data, so this single rating "
    "applies at any time of day rather than there being a separate night figure. The rate counts against registered residents, not footfall, so a busy central, station or "
    "nightlife district can read higher without that meaning elevated risk per visit. See the methodology page "
    "for full sourcing."
)

STOCKHOLM_UI = dict(TORINO_UI)
STOCKHOLM_UI.update({
    "page_title": "Is my Stockholm neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Stockholm's 11 official stadsdelsnämnder (city district committees) with real official Brå crime-rate data per district.",
    "page_h1": "Stockholm neighbourhoods",
    "neigh_title": "Is {name} in Stockholm safe? | Wandroz",
})

STOCKHOLM_BANNER = (
    "Neighbourhood shapes are Stockholm's real official 11 stadsdelsnämnder (city district committees, boundaries "
    "via Stockholms stad's own 'Stadskartans Stadsdelsnämnder 2023' dataset). Like Berlin, Amsterdam, Prague, Oslo "
    "and Munich, Stockholm's safety levels come from a real official statistic — Brå (Brottsförebyggande rådet)'s "
    "own 2025 total reported-offence counts per district, converted to a rate per 100,000 residents using each "
    "district's 31 December 2024 population (Stockholms stad) — rather than Milan/Rome's press-research approach. "
    "This rate is calculated against registered residents, not footfall, so high-traffic central/station/nightlife "
    "districts — especially Norra innerstaden (the inner-city core around Centralstationen) and Södermalm "
    "(nightlife and restaurants) — can read higher without that meaning elevated risk per visit. The source data "
    "has no time-of-day breakdown, so — like Berlin, Amsterdam, Prague, Oslo and Munich — this map shows one "
    "consistent level per district rather than a day/night toggle; see the methodology page for details."
)
STOCKHOLM_NEIGH_NOTE = (
    "This rating for Stockholm is a real official statistic — Brå (Brottsförebyggande rådet)'s own published 2025 "
    "total reported-offence count for this district, converted to a rate per 100,000 residents using Stockholms "
    "stad's 31 December 2024 population figure for the district — not a qualitative or press-based judgment. It "
    "has no day/night split in the source data, so this single rating applies at any time of day rather than there being a separate night figure. The rate counts against "
    "registered residents, not footfall, so a busy central, station or nightlife district can read higher without "
    "that meaning elevated risk per visit. See the methodology page for full sourcing."
)

BRUSSELS_UI = dict(TORINO_UI)
BRUSSELS_UI.update({
    "page_title": "Is my Brussels neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Brussels' 19 official communes with real official BISA/Federale Politie crime-rate data per commune.",
    "page_h1": "Brussels neighbourhoods",
    "neigh_title": "Is {name} in Brussels safe? | Wandroz",
})

BRUSSELS_BANNER = (
    "Neighbourhood shapes are the Brussels-Capital Region's real official 19 communes (boundaries via "
    "opendata.brussels.be). Like Berlin, Amsterdam, Prague, Oslo, Munich and Stockholm, Brussels' safety levels "
    "come from a real official statistic — BISA (Brussels Institute for Statistics and Analysis), citing Federale "
    "Politie figures, and their own published 2025 total registered crime counts per commune, converted to a rate "
    "per 100,000 residents using Statbel's own 2025 population figures per commune — rather than a press-research "
    "approach. This rate is calculated against registered residents, not footfall, so high-traffic central/"
    "station/nightlife communes — especially the City of Brussels (the historic Pentagon centre, Gare Centrale, "
    "Gare du Nord) and Saint-Gilles (Gare du Midi, Brussels' Eurostar/international rail hub) — can read higher "
    "without that meaning elevated risk per visit. The source data has no time-of-day breakdown, so — like "
    "Berlin, Amsterdam, Prague, Oslo, Munich and Stockholm — this map shows one consistent level per commune "
    "rather than a day/night toggle; see the methodology page for details."
)
BRUSSELS_NEIGH_NOTE = (
    "This rating for Brussels is a real official statistic — BISA (Brussels Institute for Statistics and "
    "Analysis), citing Federale Politie figures, and their own published 2025 total registered crime count for "
    "this commune, converted to a rate per 100,000 residents using Statbel's 2025 population figure for the "
    "commune — not a qualitative or press-based judgment. It has no day/night split in the source data, so this single "
    "rating applies at any time of day rather than there being a separate night figure. The rate counts against registered residents, not footfall, so a busy central, "
    "station or nightlife commune can read higher without that meaning elevated risk per visit. See the "
    "methodology page for full sourcing."
)

ATHENS_UI = dict(TORINO_UI)
ATHENS_UI.update({
    "page_title": "Is my Athens neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Athens' 7 official Δημοτικές Κοινότητες (Municipal Districts, real official City of Athens boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Athens neighbourhoods",
    "neigh_title": "Is {name} in Athens safe? | Wandroz",
})

ATHENS_BANNER = (
    "District shapes are Athens' real official administrative boundaries (the 7 \"Δημοτικές Κοινότητες\", "
    "Municipal Districts, a holdover unit from the 2011 \"Kallikratis\" local-government reform), sourced "
    "directly from the City of Athens' own official GIS portal (gis.cityofathens.gr). Like Milan, Rome, Turin, "
    "Barcelona, Madrid, Vienna, Lisbon and Paris, Athens' safety levels are Wandroz's Level 2 approach: genuine "
    "current local/national press research per district, honestly disclosed as press-based rather than official "
    "crime statistics — Greece has no open, geolocated neighbourhood-level crime dataset (the Hellenic Police "
    "publish only national and regional aggregate statistics). Where no specific news coverage was found for "
    "part of a district, that is stated plainly rather than assumed either way. All 7 official Municipal "
    "Districts are mapped, none excluded. See the methodology page for details and sources."
)
ATHENS_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Athens: genuine current local/national press research for "
    "this specific Municipal District (not blind guessing, not fabricated crime statistics), honestly disclosed "
    "as press-based rather than official data — Greece has no open, geolocated neighbourhood-level crime "
    "dataset. See the methodology page for what was checked and how this differs from London's automated "
    "official-data pipeline."
)

VENEZIA_UI = dict(TORINO_UI)
VENEZIA_UI.update({
    "page_title": "Is my Venice neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Venice's 6 official Municipalità (real official Comune di Venezia administrative districts, mainland included) with day/night safety levels based on current local press research.",
    "page_h1": "Venice neighbourhoods",
    "neigh_title": "Is {name} in Venice safe? | Wandroz",
})

VENEZIA_BANNER = (
    "District shapes are Venice's real official administrative boundaries (the 6 \"Municipalità\" established in "
    "2005), covering the whole Comune di Venezia — the historic lagoon islands (Venezia-Murano-Burano, "
    "Lido-Pellestrina) as well as the mainland districts (Mestre-Carpenedo, Marghera, Favaro Veneto, "
    "Chirignago-Zelarino). Like Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris and Athens, Venice's "
    "safety levels are Wandroz's Level 2 approach: genuine current local/national press research per district, "
    "honestly disclosed as press-based rather than official crime statistics — Italy has no open, geolocated "
    "neighbourhood-level crime dataset. Where no specific news coverage was found for part of a district, that "
    "is stated plainly rather than assumed either way. All 6 official Municipalità are mapped, none excluded. "
    "See the methodology page for details and sources."
)
VENEZIA_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Venice: genuine current local/national press research for "
    "this specific Municipalità (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — Italy has no open, geolocated neighbourhood-level crime dataset. "
    "See the methodology page for what was checked and how this differs from London's automated official-data "
    "pipeline."
)


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

# Carried over verbatim from the hand-built dist/firenze/index.html that this
# city was recovered from — it is Florence's honesty disclosure, so migrating
# it must not paraphrase it. Same text as firenze.json's dataNote.
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
DUBLIN_UI = dict(TORINO_UI)
DUBLIN_UI.update({
    "page_title": "Is my Dublin neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Dublin City's 11 official Local Electoral Areas (real Dublin City Council electoral geography) with day/night safety levels based on current local press research.",
    "page_h1": "Dublin neighbourhoods",
    "neigh_title": "Is {name} in Dublin safe? | Wandroz",
})

DUBLIN_BANNER = (
    "District shapes are Dublin City Council's real official Local Electoral Areas (LEAs) — the government "
    "electoral geography used for Dublin City Council elections. Like Milan, Rome, Turin, Barcelona, Madrid, "
    "Vienna, Lisbon, Paris, Athens and Venice, Dublin's safety levels are Wandroz's Level 2 approach: genuine "
    "current local/national press research per district, honestly disclosed as press-based rather than "
    "official crime statistics — Ireland has no current, live, geolocated neighbourhood-level crime dataset "
    "(the only near-candidate, a historical Garda-station dataset, is confirmed to cover only 2003-2015 with "
    "no live update). Where no specific news coverage was found for part of a district, that is stated "
    "plainly rather than assumed either way. All 11 official Local Electoral Areas are mapped, none excluded. "
    "See the methodology page for details and sources."
)
DUBLIN_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Dublin: genuine current local/national press research for "
    "this specific Local Electoral Area (not blind guessing, not fabricated crime statistics), honestly "
    "disclosed as press-based rather than official data — Ireland has no current, live, geolocated "
    "neighbourhood-level crime dataset. See the methodology page for what was checked and how this differs "
    "from London's automated official-data pipeline."
)

EDINBURGH_UI = dict(TORINO_UI)
EDINBURGH_UI.update({
    "page_title": "Is my Edinburgh neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Edinburgh's 17 official City of Edinburgh Council wards with day/night safety levels anchored to real crimes-per-1,000-population figures per ward.",
    "page_h1": "Edinburgh neighbourhoods",
    "neigh_title": "Is {name} in Edinburgh safe? | Wandroz",
})

EDINBURGH_BANNER = (
    "Ward shapes are the real official administrative boundaries of the City of Edinburgh Council's 17 wards, "
    "sourced directly from the Council's own ArcGIS map service (edinburghcouncilmaps.info, Open Government "
    "Licence v3.0). Unlike most other Level 2 cities on Wandroz, Edinburgh's safety levels here are anchored "
    "to genuine, real, numeric crimes-per-1,000-population figures per ward for 2023/24 (Churchill Support "
    "Services' analysis of Scottish Government data, published via the Scottish Daily Express), independently "
    "corroborated by a second analysis of Police Scotland's own published crime data through end of 2025 "
    "(datamap-scotland.co.uk) — both agree on the same highest- and lowest-crime wards. Neither official "
    "source splits crime by time of day, so day and night ratings are the same for every ward unless specific, "
    "dated local press coverage documented a night-specific pattern (as for City Centre's Cowgate/Grassmarket "
    "nightlife area). Where no such specific incident was found, that is stated plainly rather than assumed "
    "either way. All 17 official wards are mapped, none excluded. See the methodology page for details and "
    "sources."
)
EDINBURGH_NEIGH_NOTE = (
    "This rating for Edinburgh is anchored to a genuine, real, numeric crimes-per-1,000-population figure for "
    "this specific ward (not blind guessing, not fabricated crime statistics), cross-checked against a second "
    "independent analysis of Police Scotland's own published data. Day and night show the same tone unless "
    "specific, dated local press coverage documented a night-specific pattern. See the methodology page for "
    "what was checked and how this differs from London's automated official-data pipeline."
)

NAPOLI_UI = dict(TORINO_UI)
NAPOLI_UI.update({
    "page_title": "Is my Naples neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Naples's 10 official Municipalità (real official administrative boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Naples neighbourhoods",
    "neigh_title": "Is {name} in Naples safe? | Wandroz",
})

NAPOLI_BANNER = (
    "Zone shapes are the real official administrative boundaries of Naples's 10 \"Municipalità\" (established "
    "2005, each grouping several traditional quartieri) — the finest official government-defined neighbourhood "
    "unit for the city. The Comune di Napoli's own GIS portal (sit.comune.napoli.it) has a broken server-side "
    "SSL certificate that makes it unreachable, so these boundaries were instead sourced from OpenStreetMap's "
    "own tagged administrative-boundary relations for each Municipalità (admin_level 10, cross-checked against "
    "Wikidata/Wikipedia references) — the same genuine, officially-modelled geometry, reached through a working "
    "channel. Like Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens, Venice and Dublin, "
    "Naples's safety levels are Wandroz's Level 2 approach: genuine current local/national press research per "
    "Municipalità, honestly disclosed as press-based rather than official crime statistics — Italy does not "
    "publish an open, geolocated crime dataset at this level of detail. Where no specific news coverage was "
    "found for a Municipalità, that is stated plainly rather than assumed either way. All 10 official "
    "Municipalità are mapped, none excluded. See the methodology page for details and sources."
)
NAPOLI_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Naples: genuine current local/national press research for "
    "this specific Municipalità (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — Italy does not publish an open, geolocated crime dataset at "
    "Municipalità level. See the methodology page for what was checked and how this differs from London's "
    "automated official-data pipeline."
)

BUDAPEST_UI = dict(TORINO_UI)
BUDAPEST_UI.update({
    "page_title": "Is my Budapest neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Budapest's 23 official kerületek (real official administrative boundaries) with day/night safety levels based on current local press research.",
    "page_h1": "Budapest neighbourhoods",
    "neigh_title": "Is {name} in Budapest safe? | Wandroz",
})

BUDAPEST_BANNER = (
    "Zone shapes are the real official administrative boundaries of Budapest's 23 \"kerületek\" (districts) — "
    "each with its own local government — the finest official government-defined neighbourhood unit for the "
    "city. Hungary's own PRE-STAT crime-statistics portal was checked first as a possible official per-district "
    "data source, but it turned out not to be usable: citizen access requires an authenticated Hungarian "
    "government-portal (Ügyfélkapu) login this build could not obtain, and its own documentation says it does "
    "not break data down to kerület level in any case. No other official open, geolocated crime dataset at "
    "kerület level could be found (Hungary's national statistics office only publishes county- and national-"
    "level figures), so boundaries were instead sourced from OpenStreetMap's own tagged administrative-boundary "
    "relations for each kerület (admin_level 9) — the same genuine, officially-modelled geometry, reached "
    "through a working channel. Like Milan, Rome, Turin, Barcelona, Madrid, Vienna, Lisbon, Paris, Athens, "
    "Venice, Dublin and Naples, Budapest's safety levels are Wandroz's Level 2 approach: genuine current local/"
    "national press research per kerület, honestly disclosed as press-based rather than official crime "
    "statistics. Where no specific news coverage was found for a kerület, or where sources genuinely "
    "disagreed, that is stated plainly rather than assumed either way. All 23 official kerületek are mapped, "
    "none excluded. See the methodology page for details and sources."
)
BUDAPEST_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Budapest: genuine current local/national press research for "
    "this specific kerület (not blind guessing, not fabricated crime statistics), honestly disclosed as "
    "press-based rather than official data — Hungary's own PRE-STAT crime portal does not break data down to "
    "kerület level and requires an authenticated government login in any case. See the methodology page for "
    "what was checked and how this differs from London's automated official-data pipeline."
)

KRAKOW_UI = dict(TORINO_UI)
KRAKOW_UI.update({
    "page_title": "Is my Kraków neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Kraków's 18 official dzielnice (real official administrative boundaries) with day/night safety levels based on current local press and official survey research.",
    "page_h1": "Kraków neighbourhoods",
    "neigh_title": "Is {name} in Kraków safe? | Wandroz",
})

KRAKOW_BANNER = (
    "Zone shapes are the real official administrative boundaries of Kraków's 18 \"dzielnice\" (districts) — "
    "each with its own local government — the finest official government-defined neighbourhood unit for the "
    "city. Poland's national Krajowa Mapa Zagrożeń Bezpieczeństwa (National Security Threat Map) was checked "
    "first as a possible official per-district data source, but it turned out not to be usable: it is a "
    "crowd-sourced map of individual citizen-reported nuisances (speeding, public drinking, stray animals), "
    "not aggregated crime statistics, with no per-district breakdown or export. No other official open, "
    "geolocated crime dataset at dzielnica level could be found, so boundaries were instead sourced from "
    "OpenStreetMap's own tagged administrative-boundary relations for each dzielnica (admin_level 9), each "
    "cross-checked against its own Polish Wikipedia \"Dzielnica N\" article — the same genuine, "
    "officially-modelled geometry used for every other city here. Like Milan, Rome, Turin, Barcelona, Madrid, "
    "Vienna, Lisbon, Paris, Athens, Venice, Dublin, Naples and Budapest, Kraków's safety levels are Wandroz's "
    "Level 2 approach: genuine current local press reporting and the City of Kraków's own official "
    "resident-safety survey, honestly disclosed as press- and survey-based rather than an official crime feed. "
    "Two of the sources used report figures only in police-defined groupings spanning two or three dzielnice "
    "at once, disclosed per zone rather than presented as a precise single-district figure. Where sources "
    "genuinely disagreed, that is stated plainly rather than assumed either way. All 18 official dzielnice are "
    "mapped, none excluded. See the methodology page for details and sources."
)
KRAKOW_NEIGH_NOTE = (
    "This rating is Wandroz's Level 2 approach for Kraków: genuine current local press reporting and the City "
    "of Kraków's own official resident-safety survey for this specific dzielnica (not blind guessing, not "
    "fabricated crime statistics), honestly disclosed as press- and survey-based rather than an official crime "
    "feed — Poland's national threat-report map does not break data down to dzielnica level and is a "
    "citizen-nuisance pin map, not a crime dataset, in any case. See the methodology page for what was checked "
    "and how this differs from London's automated official-data pipeline."
)


# NOTE: the homepage used to carry a large static SVG landmass path here for
# a hand-tuned decorative "flight map" hero. That hero (fixed equirectangular
# pin positions + a duplicate city-card list below it) has been replaced by
# a real, zoomable Leaflet map (see templates/index.html and the city_cards
# lat/lon below), so this constant is no longer needed and was removed.


def build_homepage_preview():
    """Real example neighbourhood shown in the homepage's "See what Wandroz
    tells you" section — pulled straight from Rome's real zone dataset at
    build time (never hand-typed on the page), so it can't drift out of
    sync with the actual live zone page. Trastevere is used because its
    real day/night tones (green by day, yellow by night, from genuine
    press research — see methodology.html) demonstrate exactly the thing a
    single overall score couldn't: the same place reads differently
    depending on when you're there. No score/stat is invented here — this
    only ever surfaces fields that already exist in roma.json."""
    path = os.path.join(ZONES_DIR, "roma.json")
    with open(path) as f:
        data = json.load(f)
    zone = next(z for z in data["zones"] if z["slug"] == "trastevere")

    # Trim the real body text to a clean sentence boundary for a compact
    # card, rather than a hard mid-sentence cut.
    text = zone["text"]
    snippet = text[:260]
    cut = snippet.rfind(". ")
    snippet = snippet[:cut + 1] if cut > 120 else snippet.rstrip() + "…"

    return {
        "name": zone["name"], "city": "Rome", "flag": "🇮🇹",
        "day": zone["day"], "night": zone["night"],
        "day_label": EN_TONE_BADGE.get(zone["day"], zone["day"]),
        "night_label": EN_TONE_BADGE.get(zone["night"], zone["night"]),
        "text": snippet,
        "url": "roma/trastevere.html",
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cities = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            city_data = json.load(f)
        if "boroughs" not in city_data:
            # Not a per-city ranking file — e.g. zurich_burglary.json, a
            # narrower supplementary dataset (see load_zurich_burglary() /
            # build_zurich_zone_burglary()) that's loaded separately and
            # attached to Zurich's illustrative pages rather than treated
            # as its own ranked city.
            continue
        cities.append(city_data)

    attach_boundaries(cities)

    index_tpl = env.get_template("index.html")
    borough_tpl = env.get_template("borough.html")
    methodology_tpl = env.get_template("methodology.html")

    sitemap_urls = [SITE_URL + "/", SITE_URL + "/methodology.html"]

    # Home page — a plain city chooser, no ranking here; the map itself
    # (click a zone) is where safety levels and reasoning live.
    london = next((c for c in cities if c["city"].lower() == "london"), None)
    london_live_count = len(london["boroughs"]) if london else 0
    # lat/lon are each city's real coordinates — the homepage map is a real,
    # zoomable Leaflet map (see templates/index.html), not a hand-tuned
    # decorative projection, so there is no bounding box to keep in sync and
    # no manual collision-avoidance needed: nearby cities (e.g. Zurich and
    # Turin, ~200km apart) simply cluster together at low zoom and separate
    # cleanly once you zoom in, which is also what keeps this scaling to
    # dozens of cities instead of needing a per-city "label_side" hack.
    # color is a distinct accent per city purely for visual variety on that
    # map — unrelated to the day/night safety tone colors used elsewhere.
    # zone_count/data_tag feed the homepage map's per-city popup card (see
    # templates/index.html). zone_count is read straight from each city's
    # real zone dataset (never hand-typed, so it can't drift out of sync
    # with the actual number of pages). data_tag is a short, deliberately
    # honest label: "Official boundaries" is true for every city here (all
    # five use real official council/city boundary datasets), but only
    # London's *ratings* come from an official crime feed (data.police.uk)
    # and only Zurich has one additional real official crime layer
    # (burglary-by-district) on top of its illustrative ratings — Turin,
    # Milan and Rome's day/night ratings are Level 2 (genuine press
    # research, see methodology.html), not official crime statistics, so
    # their tag does not claim "official data" beyond the boundaries.
    def _zone_count(city_key):
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        with open(path) as f:
            return len(json.load(f)["zones"])

    city_cards = [
        {"name": "London", "url": "london/index.html", "flag": "🇬🇧",
         "blurb": f"33 boroughs on the map, {london_live_count} refreshed automatically every month from real Metropolitan Police data.",
         "lat": 51.5074, "lon": -0.1278, "color": "#2f6fed",
         "zone_count": 33, "data_tag": "Official police data"},
        {"name": "Berlin", "url": "berlin/index.html", "flag": "🇩🇪",
         "blurb": "All 143 official Bezirksregionen mapped, safety levels from Polizei Berlin's real official 2025 crime-rate statistics.",
         "lat": 52.5200, "lon": 13.4050, "color": "#1f9e89",
         "zone_count": _zone_count("berlin"), "data_tag": "Official police data"},
        {"name": "Amsterdam", "url": "amsterdam/index.html", "flag": "🇳🇱",
         "blurb": "All 110 official wijken mapped, safety levels from CBS's real official 2025 crime and population statistics.",
         "lat": 52.3676, "lon": 4.9041, "color": "#f2994a",
         "zone_count": _zone_count("amsterdam"), "data_tag": "Official police data"},
        {"name": "Turin", "url": "torino/index.html", "flag": "🇮🇹",
         "blurb": "23 neighbourhoods, real official council boundaries, illustrative safety ratings.",
         "lat": 45.0703, "lon": 7.6869, "color": "#e2a33d",
         "zone_count": _zone_count("torino"), "data_tag": "Official boundaries"},
        {"name": "Zurich", "url": "zurigo/index.html", "flag": "🇨🇭",
         "blurb": "34 neighbourhoods, real official city boundaries, illustrative safety ratings — plus a real official burglary-rate layer by district.",
         "lat": 47.3769, "lon": 8.5417, "color": "#d1483f",
         "zone_count": _zone_count("zurigo"), "data_tag": "Official boundaries + burglary data"},
        {"name": "Milan", "url": "milano/index.html", "flag": "🇮🇹",
         "blurb": "All 88 official zones mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 45.4642, "lon": 9.1900, "color": "#3fae6b",
         "zone_count": _zone_count("milano"), "data_tag": "Official boundaries"},
        {"name": "Rome", "url": "roma/index.html", "flag": "🇮🇹",
         "blurb": "All 155 official zones mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 41.9028, "lon": 12.4964, "color": "#8e44ad",
         "zone_count": _zone_count("roma"), "data_tag": "Official boundaries"},
        {"name": "Prague", "url": "praha/index.html", "flag": "🇨🇿",
         "blurb": "All 57 official mestske casti mapped, safety levels from Policie CR's real official 2024 crime and population statistics.",
         "lat": 50.0755, "lon": 14.4378, "color": "#b5651d",
         "zone_count": _zone_count("praha"), "data_tag": "Official police data"},
        {"name": "Oslo", "url": "oslo/index.html", "flag": "🇳🇴",
         "blurb": "All 15 official bydeler mapped, safety levels from Oslo kommune's real official 2024 crime and population statistics.",
         "lat": 59.9139, "lon": 10.7522, "color": "#2678b6",
         "zone_count": _zone_count("oslo"), "data_tag": "Official police data"},
        {"name": "Munich", "url": "monaco-di-baviera/index.html", "flag": "🇩🇪",
         "blurb": "All 25 official Stadtbezirke mapped, safety levels from Polizeipräsidium München's real official 2025 crime and population statistics.",
         "lat": 48.1372, "lon": 11.5755, "color": "#4a7c59",
         "zone_count": _zone_count("munich"), "data_tag": "Official police data"},
        {"name": "Stockholm", "url": "stockholm/index.html", "flag": "🇸🇪",
         "blurb": "All 11 official stadsdelsnämnder mapped, safety levels from Brå's real official 2025 crime and population statistics.",
         "lat": 59.3293, "lon": 18.0686, "color": "#4472ca",
         "zone_count": _zone_count("stockholm"), "data_tag": "Official police data"},
        {"name": "Barcelona", "url": "barcelona/index.html", "flag": "🇪🇸",
         "blurb": "All 73 official barris mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 41.3874, "lon": 2.1686, "color": "#c94f7c",
         "zone_count": _zone_count("barcelona"), "data_tag": "Official boundaries"},
        {"name": "Madrid", "url": "madrid/index.html", "flag": "🇪🇸",
         "blurb": "All 131 official barrios mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 40.4168, "lon": -3.7038, "color": "#d98e04",
         "zone_count": _zone_count("madrid"), "data_tag": "Official boundaries"},
        {"name": "Vienna", "url": "vienna/index.html", "flag": "🇦🇹",
         "blurb": "All 23 official Bezirke mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 48.2082, "lon": 16.3738, "color": "#5b8c5a",
         "zone_count": _zone_count("vienna"), "data_tag": "Official boundaries"},
        {"name": "Lisbon", "url": "lisbon/index.html", "flag": "🇵🇹",
         "blurb": "All 24 official freguesias mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 38.7223, "lon": -9.1393, "color": "#c9483f",
         "zone_count": _zone_count("lisbon"), "data_tag": "Official boundaries"},
        {"name": "Paris", "url": "paris/index.html", "flag": "🇫🇷",
         "blurb": "All 80 official quartiers administratifs mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 48.8566, "lon": 2.3522, "color": "#3468c0",
         "zone_count": _zone_count("paris"), "data_tag": "Official boundaries"},
        {"name": "Brussels", "url": "brussels/index.html", "flag": "🇧🇪",
         "blurb": "All 19 official communes mapped, safety levels from BISA/Federale Politie's real official 2025 crime and Statbel population statistics.",
         "lat": 50.8503, "lon": 4.3517, "color": "#34495e",
         "zone_count": _zone_count("brussels"), "data_tag": "Official police data"},
        {"name": "Athens", "url": "athens/index.html", "flag": "🇬🇷",
         "blurb": "All 7 official Municipal Districts mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 37.9838, "lon": 23.7275, "color": "#1477a6",
         "zone_count": _zone_count("athens"), "data_tag": "Official boundaries"},
        {"name": "Venice", "url": "venezia/index.html", "flag": "🇮🇹",
         "blurb": "All 6 official Municipalità mapped, mainland included, safety ratings from genuine current local press research.",
         "lat": 45.4408, "lon": 12.3155, "color": "#7a2048",
         "zone_count": _zone_count("venezia"), "data_tag": "Official boundaries"},
        {"name": "Dublin", "url": "dublin/index.html", "flag": "🇮🇪",
         "blurb": "All 11 official Local Electoral Areas mapped, real council electoral boundaries, safety ratings from genuine current local press research.",
         "lat": 53.3498, "lon": -6.2603, "color": "#4b0082",
         "zone_count": _zone_count("dublin"), "data_tag": "Official boundaries"},
        {"name": "Florence", "url": "firenze/index.html", "flag": "🇮🇹",
         "blurb": "All 74 official quartieri/zone mapped, real Comune di Firenze boundaries, safety ratings from genuine current local press research.",
         "lat": 43.7696, "lon": 11.2558, "color": "#9c6b3e",
         "zone_count": 74, "data_tag": "Official boundaries"},
        {"name": "Edinburgh", "url": "edinburgh/index.html", "flag": "🇬🇧",
         "blurb": "All 17 official City of Edinburgh Council wards mapped, safety ratings anchored to real crimes-per-1,000-population figures per ward.",
         "lat": 55.9533, "lon": -3.1883, "color": "#0f4c81",
         "zone_count": _zone_count("edinburgh"), "data_tag": "Official boundaries"},
        {"name": "Naples", "url": "napoli/index.html", "flag": "🇮🇹",
         "blurb": "All 10 official Municipalità mapped, real OpenStreetMap administrative boundaries, safety ratings from genuine current local press research.",
         "lat": 40.8518, "lon": 14.2681, "color": "#c0392b",
         "zone_count": _zone_count("napoli"), "data_tag": "Official boundaries"},
        {"name": "Budapest", "url": "budapest/index.html", "flag": "🇭🇺",
         "blurb": "All 23 official kerületek mapped, real OpenStreetMap administrative boundaries, safety ratings from genuine current local press research.",
         "lat": 47.4979, "lon": 19.0402, "color": "#477050",
         "zone_count": _zone_count("budapest"), "data_tag": "Official boundaries"},
        {"name": "Kraków", "url": "krakow/index.html", "flag": "🇵🇱",
         "blurb": "All 18 official dzielnice mapped, real OpenStreetMap administrative boundaries, safety ratings from genuine current local press and official survey research.",
         "lat": 50.0619, "lon": 19.9368, "color": "#a23b72",
         "zone_count": _zone_count("krakow"), "data_tag": "Official boundaries"},
    ]
    # Homepage city-card "evidence" tag: this used to be a hand-typed
    # "Official boundaries" string on every non-London card, which only
    # ever spoke to the shapes being real, never to how the safety RATING
    # itself was actually produced — so a real official-police-statistic
    # city (Berlin) and a first-manual-pass city (Turin) showed the same
    # kind of claim. This derives the tag from CITY_METHODOLOGY instead —
    # the same single source of truth the FAQ/legend fixes above use — so
    # it can't drift out of sync and a newly added city gets a correct tag
    # automatically as soon as it has one CITY_METHODOLOGY entry.
    _CITY_CARD_TO_METHOD_KEY = {
        "Berlin": "berlin", "Amsterdam": "amsterdam", "Turin": "torino", "Zurich": "zurigo",
        "Milan": "milano", "Rome": "roma", "Prague": "praha", "Oslo": "oslo", "Munich": "munich",
        "Stockholm": "stockholm", "Barcelona": "barcelona", "Madrid": "madrid", "Vienna": "vienna",
        "Lisbon": "lisbon", "Paris": "paris", "Brussels": "brussels", "Athens": "athens",
        "Venice": "venezia", "Dublin": "dublin", "Edinburgh": "edinburgh", "Naples": "napoli",
        "Budapest": "budapest", "Kraków": "krakow",
        # London already has its own correct "Official police data" tag above (a real
        # automated data.police.uk pipeline, not this dict's illustrative-city tiers).
        # Florence has no CITY_METHODOLOGY entry because it isn't rendered by this
        # pipeline at all (dist/firenze/ is a hand-built page, not generated from
        # data_zones/) — flagged separately as an architectural gap, not silently
        # covered up with a borrowed tag here.
    }
    _EVIDENCE_TAG_BY_TIER = {
        OFFICIAL_SNAPSHOT: "Official police/crime data",
        RESEARCH_BASED: "Press & survey research",
        MANUAL_EXPERIMENTAL: "Manual first-pass rating",
    }
    for _card in city_cards:
        _mkey = _CITY_CARD_TO_METHOD_KEY.get(_card["name"])
        _method = CITY_METHODOLOGY.get(_mkey) if _mkey else None
        if _method:
            _tag = _EVIDENCE_TAG_BY_TIER[_method["tier"]]
            if _mkey == "zurigo":
                _tag += " + official burglary data"
            _card["data_tag"] = _tag

    preview_zone = build_homepage_preview()
    with open(os.path.join(OUT_DIR, "index.html"), "w") as f:
        f.write(index_tpl.render(city_cards=city_cards, preview_zone=preview_zone, canonical_url=SITE_URL + "/"))

    # Homepage search bar's data — built fresh from real content on every
    # run (see build_search_index docstring), never hand-maintained.
    search_entries = build_search_index(cities, city_cards)
    with open(os.path.join(OUT_DIR, "search-index.json"), "w") as f:
        json.dump(search_entries, f, ensure_ascii=False)
    print(f"Wrote {os.path.join(OUT_DIR, 'search-index.json')} ({len(search_entries)} entries)")

    # Homepage address search's boundary data — real zone polygons + real
    # per-city bounding boxes, used for a client-side point-in-polygon
    # match against a geocoded address (see build_zone_boundaries
    # docstring and templates/index.html).
    zone_boundaries = build_zone_boundaries(cities, city_cards)
    with open(os.path.join(OUT_DIR, "zone-boundaries.json"), "w") as f:
        json.dump(zone_boundaries, f, ensure_ascii=False)
    print(f"Wrote {os.path.join(OUT_DIR, 'zone-boundaries.json')} ({len(zone_boundaries['zones'])} zones, {len(zone_boundaries['cities'])} city boxes)")

    # Methodology page
    with open(os.path.join(OUT_DIR, "methodology.html"), "w") as f:
        f.write(methodology_tpl.render(
            canonical_url=SITE_URL + "/methodology.html",
            london_covered_count=london_live_count,
            london_total_boroughs=33,
        ))
    print(f"Wrote {os.path.join(OUT_DIR, 'methodology.html')}")

    # One page per borough/neighbourhood
    for city in cities:
        city_slug = city["city"].lower().replace(" ", "-")
        city_dir = os.path.join(OUT_DIR, city_slug)
        os.makedirs(city_dir, exist_ok=True)
        total = len(city["boroughs"])
        for b in city["boroughs"]:
            day_label = EN_TONE_BADGE.get(b.get("day_tone"), b.get("day_tone"))
            night_label = EN_TONE_BADGE.get(b.get("night_tone"), b.get("night_tone"))
            page_url = f"{SITE_URL}/{city_slug}/{b['slug']}.html"
            faq_items = build_faq_london(b, city["city"])
            page = borough_tpl.render(
                city=city, b=b, day_label=day_label, night_label=night_label,
                canonical_url=page_url, correction_email=CORRECTION_EMAIL,
                evidence_tag=LONDON_EVIDENCE_TAG,
                faq_items=faq_items, faq_schema=_faq_jsonld(faq_items),
            )
            out_path = os.path.join(city_dir, f"{b['slug']}.html")
            with open(out_path, "w") as f:
                f.write(page)
            print(f"Wrote {out_path}")
            sitemap_urls.append(page_url)

    print(f"Wrote {os.path.join(OUT_DIR, 'index.html')}")

    copied = copy_static()
    for path in copied:
        print(f"Copied {path}")

    torino_urls = render_illustrative_city("torino", "torino", TORINO_UI, EN_TONE_BADGE, TORINO_BANNER, TORINO_NEIGH_NOTE)
    sitemap_urls.extend(torino_urls)
    zurich_zone_burglary = build_zurich_zone_burglary()
    zurigo_urls = render_illustrative_city(
        "zurigo", "zurigo", ZURIGO_UI, EN_TONE_BADGE, ZURIGO_BANNER, ZURIGO_NEIGH_NOTE,
        extra_zone_data=zurich_zone_burglary,
    )
    sitemap_urls.extend(zurigo_urls)
    london_map_urls = render_london_map(cities)
    sitemap_urls.extend(london_map_urls)
    milano_urls = render_illustrative_city("milano", "milano", MILANO_UI, EN_TONE_BADGE, MILANO_BANNER, MILANO_NEIGH_NOTE)
    sitemap_urls.extend(milano_urls)
    roma_urls = render_illustrative_city("roma", "roma", ROMA_UI, EN_TONE_BADGE, ROMA_BANNER, ROMA_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(roma_urls)
    berlin_urls = render_illustrative_city("berlin", "berlin", BERLIN_UI, EN_TONE_BADGE, BERLIN_BANNER, BERLIN_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(berlin_urls)
    amsterdam_urls = render_illustrative_city("amsterdam", "amsterdam", AMSTERDAM_UI, EN_TONE_BADGE, AMSTERDAM_BANNER, AMSTERDAM_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(amsterdam_urls)
    praha_urls = render_illustrative_city("praha", "praha", PRAHA_UI, EN_TONE_BADGE, PRAHA_BANNER, PRAHA_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(praha_urls)
    oslo_urls = render_illustrative_city("oslo", "oslo", OSLO_UI, EN_TONE_BADGE, OSLO_BANNER, OSLO_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(oslo_urls)
    munich_urls = render_illustrative_city("munich", "monaco-di-baviera", MUNICH_UI, EN_TONE_BADGE, MUNICH_BANNER, MUNICH_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(munich_urls)
    stockholm_urls = render_illustrative_city("stockholm", "stockholm", STOCKHOLM_UI, EN_TONE_BADGE, STOCKHOLM_BANNER, STOCKHOLM_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(stockholm_urls)
    barcelona_urls = render_illustrative_city("barcelona", "barcelona", BARCELONA_UI, EN_TONE_BADGE, BARCELONA_BANNER, BARCELONA_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(barcelona_urls)
    madrid_urls = render_illustrative_city("madrid", "madrid", MADRID_UI, EN_TONE_BADGE, MADRID_BANNER, MADRID_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(madrid_urls)
    vienna_urls = render_illustrative_city("vienna", "vienna", VIENNA_UI, EN_TONE_BADGE, VIENNA_BANNER, VIENNA_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(vienna_urls)
    lisbon_urls = render_illustrative_city("lisbon", "lisbon", LISBON_UI, EN_TONE_BADGE, LISBON_BANNER, LISBON_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(lisbon_urls)
    paris_urls = render_illustrative_city("paris", "paris", PARIS_UI, EN_TONE_BADGE, PARIS_BANNER, PARIS_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(paris_urls)
    brussels_urls = render_illustrative_city("brussels", "brussels", BRUSSELS_UI, EN_TONE_BADGE, BRUSSELS_BANNER, BRUSSELS_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(brussels_urls)
    athens_urls = render_illustrative_city("athens", "athens", ATHENS_UI, EN_TONE_BADGE, ATHENS_BANNER, ATHENS_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(athens_urls)
    venezia_urls = render_illustrative_city("venezia", "venezia", VENEZIA_UI, EN_TONE_BADGE, VENEZIA_BANNER, VENEZIA_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(venezia_urls)
    dublin_urls = render_illustrative_city("dublin", "dublin", DUBLIN_UI, EN_TONE_BADGE, DUBLIN_BANNER, DUBLIN_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(dublin_urls)
    edinburgh_urls = render_illustrative_city("edinburgh", "edinburgh", EDINBURGH_UI, EN_TONE_BADGE, EDINBURGH_BANNER, EDINBURGH_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(edinburgh_urls)
    napoli_urls = render_illustrative_city("napoli", "napoli", NAPOLI_UI, EN_TONE_BADGE, NAPOLI_BANNER, NAPOLI_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(napoli_urls)
    budapest_urls = render_illustrative_city("budapest", "budapest", BUDAPEST_UI, EN_TONE_BADGE, BUDAPEST_BANNER, BUDAPEST_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(budapest_urls)
    krakow_urls = render_illustrative_city("krakow", "krakow", KRAKOW_UI, EN_TONE_BADGE, KRAKOW_BANNER, KRAKOW_NEIGH_NOTE, flat=True)
    sitemap_urls.extend(krakow_urls)
    firenze_urls = render_illustrative_city(
        "firenze", "firenze", FIRENZE_UI, EN_TONE_BADGE,
        FIRENZE_BANNER, FIRENZE_NEIGH_NOTE, flat=True,
    )
    sitemap_urls.extend(firenze_urls)
    print(f"Rendered interactive map hubs: Torino ({len(torino_urls)}), Zurigo ({len(zurigo_urls)}), London ({len(london_map_urls)}), Milano ({len(milano_urls)}), Roma ({len(roma_urls)}), Berlin ({len(berlin_urls)}), Amsterdam ({len(amsterdam_urls)}), Prague ({len(praha_urls)}), Oslo ({len(oslo_urls)}), Munich ({len(munich_urls)}), Stockholm ({len(stockholm_urls)}), Barcelona ({len(barcelona_urls)}), Madrid ({len(madrid_urls)}), Vienna ({len(vienna_urls)}), Lisbon ({len(lisbon_urls)}), Paris ({len(paris_urls)}), Brussels ({len(brussels_urls)}), Athens ({len(athens_urls)}), Venice ({len(venezia_urls)}), Dublin ({len(dublin_urls)}), Edinburgh ({len(edinburgh_urls)}), Naples ({len(napoli_urls)}), Budapest ({len(budapest_urls)}), Kraków ({len(krakow_urls)}), Firenze ({len(firenze_urls)})")

    write_robots_and_sitemap(sitemap_urls)


if __name__ == "__main__":
    main()
