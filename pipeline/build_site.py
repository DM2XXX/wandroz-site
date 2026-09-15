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
from markupsafe import Markup

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data", "scores")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ZONES_DIR = os.path.join(BASE_DIR, "data_zones")
POI_DIR = os.path.join(BASE_DIR, "data_poi")
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
# Cities on the data.police.uk pipeline. They differ by name, force and where
# they are; everything else — the ward vocabulary, the copy, the scoring — is
# shared, so they are described once here rather than copied four times.
UK_CITIES = [
    {"key": "birmingham", "city": "Birmingham", "force": "West Midlands Police",
     "lat": 52.4862, "lon": -1.8904, "color": "#7a4fbf"},
    {"key": "leeds", "city": "Leeds", "force": "West Yorkshire Police",
     "lat": 53.8008, "lon": -1.5491, "color": "#c0567a"},
    # Liverpool is not here yet, and the reason is worth writing down: the city
    # re-warded after the 2021 census, so its current 64 wards have no census
    # population — NOMIS returns nothing for their codes. A rate needs a
    # denominator from the same geography as its numerator, so Liverpool waits
    # for either 2021-vintage boundaries or a newer official ward estimate,
    # rather than shipping crime counts divided by a guess.
    {"key": "bristol", "city": "Bristol", "force": "Avon and Somerset Constabulary",
     "lat": 51.4545, "lon": -2.5879, "color": "#2f9e8f"},
    {"key": "sheffield", "city": "Sheffield", "force": "South Yorkshire Police",
     "lat": 53.3811, "lon": -1.4701, "color": "#4a7fb5"},
    {"key": "newcastle", "city": "Newcastle upon Tyne", "force": "Northumbria Police",
     "lat": 54.9783, "lon": -1.6178, "color": "#b5564a"},
    {"key": "nottingham", "city": "Nottingham", "force": "Nottinghamshire Police",
     "lat": 52.9548, "lon": -1.1581, "color": "#8a6d3b"},
    {"key": "cardiff", "city": "Cardiff", "force": "South Wales Police",
     "lat": 51.4816, "lon": -3.1791, "color": "#3f8f5c"},
    {"key": "leicester", "city": "Leicester", "force": "Leicestershire Police",
     "lat": 52.6369, "lon": -1.1398, "color": "#9c5fb0"},
    {"key": "liverpool", "city": "Liverpool", "force": "Merseyside Police",
     "lat": 53.4084, "lon": -2.9916, "color": "#e07a3f"},
    {"key": "brighton", "city": "Brighton and Hove", "force": "Sussex Police",
     "lat": 50.8225, "lon": -0.1372, "color": "#5aa9d6"},
    {"key": "york", "city": "York", "force": "North Yorkshire Police",
     "lat": 53.9600, "lon": -1.0873, "color": "#b08a3f"},
    {"key": "oxford", "city": "Oxford", "force": "Thames Valley Police",
     "lat": 51.7520, "lon": -1.2577, "color": "#6b6fd1"},
    {"key": "cambridge", "city": "Cambridge", "force": "Cambridgeshire Constabulary",
     "lat": 52.2053, "lon": 0.1218, "color": "#4fa36b"},
    {"key": "bath", "city": "Bath", "force": "Avon and Somerset Constabulary",
     "lat": 51.3811, "lon": -2.3590, "color": "#c2704f"},
    {"key": "coventry", "city": "Coventry", "force": "West Midlands Police",
     "lat": 52.4068, "lon": -1.5090, "color": "#7f8f3f"},
    {"key": "southampton", "city": "Southampton", "force": "Hampshire Constabulary",
     "lat": 50.9097, "lon": -1.4044, "color": "#3f7f8f"},
    {"key": "portsmouth", "city": "Portsmouth", "force": "Hampshire Constabulary",
     "lat": 50.8198, "lon": -1.0880, "color": "#8f3f6b"},
    {"key": "plymouth", "city": "Plymouth", "force": "Devon & Cornwall Police",
     "lat": 50.3755, "lon": -4.1427, "color": "#4f6bb0"},
    {"key": "derby", "city": "Derby", "force": "Derbyshire Constabulary",
     "lat": 52.9228, "lon": -1.4746, "color": "#b06b4f"},
    {"key": "norwich", "city": "Norwich", "force": "Norfolk Constabulary",
     "lat": 52.6309, "lon": 1.2974, "color": "#6b8f5a"},
]




def uk_city_ui(city):
    ui = dict(TORINO_UI)
    ui.update({
        "page_title": "Is my %s neighbourhood safe? — Wandroz" % city,
        "page_description": ("Interactive map of %s's official wards with real "
                             "street-level police crime data, day and night." % city),
        "page_h1": "%s wards" % city,
        "page_lead": ("Click a ward on the map to see its level, the recorded figures "
                      "behind it, and a Booking.com link for that area."),
        "label_all_zones": "All wards",
        "neigh_title": "Is {name} in %s safe? | Wandroz" % city,
        "label_zone_detail": "Ward detail",
        "label_click_hint": ("Click a ward on the map to see its level, the reasoning, "
                             "and a Booking.com link for that area."),
    })
    return ui


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
    {"label": "Bologna", "url": f"{SITE_URL}/bologna/"},
    {"label": "Verona", "url": f"{SITE_URL}/verona/"},
    {"label": "Genoa", "url": f"{SITE_URL}/genova/"},
    {"label": "Budapest", "url": f"{SITE_URL}/budapest/"},
    {"label": "Kraków", "url": f"{SITE_URL}/krakow/"},
]

# --- Country grouping (homepage "Explore destinations" + city switcher) ---
#
# Single source of truth for which country each city belongs to and which
# flag represents that country — both the homepage's grouped city grid and
# the per-city-page <select> switcher derive their grouping from this one
# dict via group_cities_by_country() below, so neither view can drift out
# of sync with the other and a newly added city only needs one line here.
COUNTRY_FLAGS = {
    "Italy": "🇮🇹", "Germany": "🇩🇪", "United Kingdom": "🇬🇧", "Spain": "🇪🇸",
    "Netherlands": "🇳🇱", "Switzerland": "🇨🇭", "Czechia": "🇨🇿", "Norway": "🇳🇴",
    "Sweden": "🇸🇪", "Austria": "🇦🇹", "Portugal": "🇵🇹", "France": "🇫🇷",
    "Belgium": "🇧🇪", "Greece": "🇬🇷", "Ireland": "🇮🇪", "Hungary": "🇭🇺",
    "Poland": "🇵🇱",
}
CITY_COUNTRY = {
    "London": "United Kingdom", "Berlin": "Germany", "Amsterdam": "Netherlands",
    "Turin": "Italy", "Zurich": "Switzerland", "Milan": "Italy", "Rome": "Italy",
    "Prague": "Czechia", "Oslo": "Norway", "Munich": "Germany", "Stockholm": "Sweden",
    "Barcelona": "Spain", "Madrid": "Spain", "Vienna": "Austria", "Lisbon": "Portugal",
    "Paris": "France", "Brussels": "Belgium", "Athens": "Greece", "Venice": "Italy",
    "Dublin": "Ireland", "Florence": "Italy", "Edinburgh": "United Kingdom",
    "Naples": "Italy", "Budapest": "Hungary", "Kraków": "Poland",
    "Bologna": "Italy", "Verona": "Italy", "Genoa": "Italy",
}

# Curated "Popular destinations" shortcut shown near the homepage search box
# — major traveller destinations rather than whichever cities happened to
# launch first. Deliberately a short, explicit, single list (not derived
# from zone count or launch order, which don't track traveller popularity)
# so it's obvious where to edit it; group_cities_by_country() below still
# pulls the actual card data (url, flag, counts) from city_cards/CITY_LINKS
# rather than this list duplicating it.
POPULAR_CITY_NAMES = ["London", "Paris", "Rome", "Barcelona", "Amsterdam", "Berlin"]


def group_cities_by_country(items, name_key="name"):
    """Group a list of city dicts (city_cards or CITY_LINKS) into country
    buckets, using CITY_COUNTRY/COUNTRY_FLAGS as the single source of truth.

    Ordering: countries with more cities first (Italy's 6 cities lead the
    homepage rather than a single-city country), ties broken by the
    position of that country's first city in `items` — so the grouping
    stays deterministic and reflects the existing rollout order rather
    than an arbitrary alphabetical list. Raises if any item's name has no
    CITY_COUNTRY entry, so a newly added city can't silently vanish from
    the grouped view instead of erroring loudly at build time.
    """
    buckets = {}
    first_index = {}
    for i, item in enumerate(items):
        name = item[name_key]
        country = CITY_COUNTRY.get(name)
        if country is None:
            raise ValueError(
                f"'{name}' has no CITY_COUNTRY entry — add one or it will "
                f"silently disappear from the country-grouped homepage/city "
                f"switcher instead of just showing ungrouped."
            )
        buckets.setdefault(country, []).append(item)
        first_index.setdefault(country, i)

    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), first_index[kv[0]]))
    groups = [
        {"name": country, "flag": COUNTRY_FLAGS[country], "count": len(cities), "cities": cities}
        for country, cities in ordered
    ]
    total = sum(g["count"] for g in groups)
    assert total == len(items), (
        f"group_cities_by_country lost or duplicated cities: {total} grouped vs {len(items)} input"
    )
    return groups


# Country-grouped version of CITY_LINKS for the per-city-page <select>
# switcher (rendered as <optgroup>s — see city_map.html). Computed once at
# import time since CITY_LINKS is static.
# Every UK pipeline city is in the United Kingdom; saying so here keeps the
# country grouping honest without four more literals to forget.
for _c in UK_CITIES:
    CITY_COUNTRY[_c["city"]] = "United Kingdom"

CITY_LINKS += [{"label": c["city"], "url": f"{SITE_URL}/{c['key']}/"} for c in UK_CITIES]
CITY_LINKS_BY_COUNTRY = group_cities_by_country(CITY_LINKS, name_key="label")

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
# Edinburgh are driven by a real official police/government statistic yet
# their FAQ implied a guess. This dict is the single source
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
# citation with dataset names and years lives on the methodology page.
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
    # The English cities added on London's own pipeline rather than beside it
    # are filled in from UK_CITIES below, so a new one needs a single entry.
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
    "bologna": {"tier": RESEARCH_BASED},
    "verona": {"tier": RESEARCH_BASED},
    "genova": {"tier": RESEARCH_BASED},
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
# The yellow box on a city map used to run five lines and explain London to
# someone reading about Zurich. It now says what the shapes are and how the
# levels were made, in one line, and sends the rest to the methodology page
# where a reader who wants the sources will go looking anyway.
# The note under a neighbourhood's description. Derived from the tier for the
# same reason the map line is: twenty-five hand-written variants drifted, and
# several still described sourced area-level work as "general local knowledge
# and public reputation", which undersold what was actually done.
# The methodology page states numbers — how many cities are on each kind of
# evidence, how many areas were reviewed one by one, how many came back with
# nothing. Counting them here means the page cannot claim a coverage it does
# not have: the figures move when the data moves.
# When each city's reviewed dataset entered the repository. Not a marketing
# date: it is the commit that added the file, so anyone can check it against
# the history. The research for a city was completed on or before it.
REVIEW_DATE = {
    "milano": "17 August 2026", "roma": "20 August 2026", "barcelona": "27 August 2026",
    "madrid": "30 August 2026", "vienna": "30 August 2026", "lisbon": "30 August 2026",
    "paris": "31 August 2026", "athens": "5 September 2026", "venezia": "5 September 2026",
    "dublin": "5 September 2026", "edinburgh": "10 September 2026", "napoli": "11 September 2026", "bologna": "14 September 2026", "verona": "15 September 2026", "genova": "15 September 2026",
    "budapest": "11 September 2026", "krakow": "11 September 2026", "firenze": "13 September 2026",
}

CITY_LABEL_FOR_KEY = {
    "milano": "Milan", "roma": "Rome", "barcelona": "Barcelona", "madrid": "Madrid",
    "vienna": "Vienna", "lisbon": "Lisbon", "paris": "Paris", "athens": "Athens",
    "venezia": "Venice", "dublin": "Dublin", "napoli": "Naples", "bologna": "Bologna", "verona": "Verona", "genova": "Genoa", "budapest": "Budapest",
    "krakow": "Kraków", "firenze": "Florence", "edinburgh": "Edinburgh",
}


def evidence_stats():
    per_tier = {OFFICIAL_SNAPSHOT: [], RESEARCH_BASED: [], MANUAL_EXPERIMENTAL: []}
    for key, meta in CITY_METHODOLOGY.items():
        per_tier[meta["tier"]].append(key)
    areas = no_findings = 0
    for key in per_tier[RESEARCH_BASED]:
        path = os.path.join(ZONES_DIR, f"{key}.json")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            zones = json.load(f)["zones"]
        areas += len(zones)
        no_findings += sum(1 for z in zones if z.get("evidence") == "no_findings")
    rows = []
    for key in per_tier[RESEARCH_BASED]:
        path = os.path.join(ZONES_DIR, f"{key}.json")
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            zones = json.load(f)["zones"]
        nf = sum(1 for z in zones if z.get("evidence") == "no_findings")
        rows.append({"city": CITY_LABEL_FOR_KEY.get(key, key.title()),
                     "areas": len(zones), "rated": len(zones) - nf, "no_findings": nf,
                     "reviewed": REVIEW_DATE.get(key, "—")})
    rows.sort(key=lambda r: -r["areas"])
    return {
        "rows": rows,
        "official_cities": len(per_tier[OFFICIAL_SNAPSHOT]),
        "assessment_cities": len(per_tier[RESEARCH_BASED]),
        "limited_cities": len(per_tier[MANUAL_EXPERIMENTAL]),
        "assessment_areas": areas,
        "no_findings_areas": no_findings,
        "rated_areas": areas - no_findings,
    }


def city_only(label):
    """"Paris, France" is the page's breadcrumb label; inside a sentence the
    country is noise ("Paris, France publishes no dataset")."""
    return label.split(",")[0].strip()


def method_note(city_key, city_label, no_findings=False):
    tier = CITY_METHODOLOGY[city_key]["tier"]
    city_label = city_only(city_label)
    if tier == OFFICIAL_SNAPSHOT:
        src = CITY_METHODOLOGY[city_key].get("crime_source") or "an official crime statistic"
        return (
            "This rating is derived from %s — an official statistic covering this area, not an "
            "assessment of it. It is a periodic snapshot rather than a live feed, and it is normalised "
            "against residents rather than footfall; the methodology page sets out the year, the "
            "normalisation and what that means for busy central areas." % src
        )
    if tier == RESEARCH_BASED:
        if no_findings:
            return (
                "This area was reviewed as part of a structured local-source assessment — the same "
                "area-level review applied to every neighbourhood in %s, drawing on local and national "
                "news, municipal and police-published material and official surveys where they exist. "
                "It returned nothing traveller-relevant specific to this area. The rating above "
                "therefore rests on that absence together with the character of the area, and is "
                "marked \u201cno area-specific findings\u201d: it carries less weight than the ratings "
                "on this map that are built on named sources, and it is not a positive finding of "
                "safety." % city_label
            )
        return (
            "This rating comes from a structured local-source assessment. This specific area was "
            "reviewed against credible local sources — local and national news, municipal and "
            "police-published material, and official surveys where they exist — and the signals were "
            "consolidated across sources rather than taken from any single report, with the reasoning "
            "and the sources shown above. %s publishes no comparable neighbourhood-level crime "
            "dataset; where a city does publish one, Wandroz uses it instead of an assessment. Where a "
            "review finds nothing documented, that is recorded as no findings rather than as a safety "
            "rating." % city_label
        )
    return (
        "This is a limited-data assessment. %s publishes no neighbourhood-level crime dataset, and this "
        "area has not yet had a full source review, so the rating is indicative and is labelled as such "
        "rather than presented as evidenced." % city_label
    )


def evidence_line(city_key, zone_count):
    """The provenance line on a city map: what the ratings rest on, in one row.

    It replaced a five-line yellow disclaimer that explained London's
    methodology to someone reading about Zurich. Everything it drops is a
    click away on the methodology page; what stays is the part a visitor
    needs to weigh the map — the evidence class, and the dataset or the
    number of areas actually reviewed behind it.
    """
    tier = CITY_METHODOLOGY[city_key]["tier"]
    bits = [EVIDENCE_TAG[tier]]
    src = EVIDENCE_SOURCE.get(city_key)
    if tier == OFFICIAL_SNAPSHOT and src:
        bits.append(src)
    elif tier == RESEARCH_BASED:
        bits.append("%d areas reviewed individually" % zone_count)
        if src:
            bits.append(src)
    elif src:
        bits.append(src)
    return " · ".join(bits)


EVIDENCE_TAG = {
    OFFICIAL_SNAPSHOT: "🟢 Official crime data",
    RESEARCH_BASED: "🟡 Local-source safety assessment",
    MANUAL_EXPERIMENTAL: "⚪ Limited-data assessment",
}

# The short attribution that sits beside the label on a city map. Naming the
# dataset is the strongest thing the page can say, so it says it.
EVIDENCE_SOURCE = {
    "berlin": "Polizei Berlin, Kriminalitätsatlas",
    "amsterdam": "CBS registered crime",
    "praha": "Policie ČR",
    "oslo": "Oslo kommune Statistikkbanken",
    "munich": "Polizeipräsidium München",
    "stockholm": "Brå",
    "brussels": "BISA / Federale Politie",
    "edinburgh": "analysis of Police Scotland figures",
    "zurigo": "district burglary data shown alongside",
}

# Each city on the data.police.uk pipeline is official-data tier by
# construction: the rating is computed from the force's own records.
for _c in UK_CITIES:
    CITY_METHODOLOGY[_c["key"]] = {
        "tier": OFFICIAL_SNAPSHOT,
        "crime_source": "%s street-level crime records published at data.police.uk" % _c["force"],
    }
    EVIDENCE_SOURCE[_c["key"]] = "%s, data.police.uk" % _c["force"]

# London is not in CITY_METHODOLOGY — it has its own automated pipeline built
# directly on data.police.uk, which is the strongest source on the site, so it
# carries the official-data label on its own terms rather than by inheritance.
LONDON_EVIDENCE_TAG = "🟢 Official crime data"


def london_window():
    """The months actually behind today's London scores, read from the data.

    Written after finding the site promising a monthly automatic refresh while
    the schedule had been switched off and the newest published month was
    three months old. A window taken from the file cannot make that promise
    and be wrong at the same time.
    """
    path = os.path.join(DATA_DIR, "london.json")
    try:
        with open(path) as f:
            months = sorted({m for b in json.load(f)["boroughs"]
                             for m in b.get("months_included", [])})
    except Exception:
        return "latest published Met Police months"
    if not months:
        return "latest published Met Police months"
    def pretty(m):
        y, mo = m.split("-")
        return "%s %s" % (["January", "February", "March", "April", "May", "June", "July",
                           "August", "September", "October", "November", "December"][int(mo) - 1], y)
    if len(months) == 1:
        return pretty(months[0])
    return "%s–%s" % (pretty(months[0]).split()[0], pretty(months[-1]))

# Shown instead of the usual "this link is already scoped to this area" note on
# zones whose booking_scope is "city". Booking has no district-level listing
# area for a handful of neighbourhoods — verified case by case against live
# searches on 13 Sep 2026 — and for those the link genuinely searches the whole
# city. Claiming a neighbourhood filter there would be exactly the kind of
# unverified assertion this project has spent its time removing, so the page
# says what the link actually does.
BOOKING_CITY_SCOPE_NOTE = (
    "Booking.com has no separate search area for this neighbourhood, so this link "
    "searches the whole city rather than just this area."
)

# And a third case, between the two: Booking has no area for the neighbourhood
# but does index the district it sits in. Paris is the clean example — every
# quartier name carries its arrondissement, "Halles, Paris, France" resolved to
# a single hotel while "1st arr., Paris, France" returns the arrondissement's
# 474 properties. The same held for Berlin's Bezirke, Madrid's distritos and
# Barcelona's districtes: better than the whole city, and the note says which
# of the three scopes a link is using.
BOOKING_PARENT_SCOPE_NOTE = (
    "Booking.com has no search area for this neighbourhood, so this link searches "
    "the district it sits in — narrower than the whole city, wider than this "
    "neighbourhood alone."
)


def booking_note(ui, scope):
    if scope == "city":
        return BOOKING_CITY_SCOPE_NOTE
    if scope == "parent":
        return BOOKING_PARENT_SCOPE_NOTE
    return ui["label_booking_note"]

# Categories a visitor filters by (why you would go) and the icon each pin
# takes (what the place is) are kept apart on purpose: they diverge on areas —
# Kazimierz, Navigli and Bairro Alto are all AREA, but people look for them
# under nightlife.
POI_CATEGORY_LABEL = {
    "art": "Art & history", "view": "Views", "green": "Green space",
    "square": "Squares & walks", "food": "Food markets", "night": "Nightlife",
}
# The filter chips are grouped by interest, so their icon has to come from the
# category. Taking it from poi_type gave the "Views" chip a temple, because
# Superga is a view you go to but a landmark by form.
POI_CATEGORY_ICON = {
    "art": "\U0001F3DB", "view": "\U0001F3D4", "green": "\U0001F333",
    "square": "\U0001F6B6", "food": "\U0001F37D", "night": "\U0001F309",
}
POI_TYPE_ICON = {
    "LANDMARK": "\U0001F3DB", "MUSEUM": "\U0001F5BC", "AREA": "\U0001F6B6",
    "VIEWPOINT": "\U0001F3D4", "PARK": "\U0001F333", "MARKET": "\U0001F37D",
}


# Munich renders under the city key "munich" while every file about it — its
# zones, its sights — is named after the Italian "monaco-di-baviera". The two
# were left to line up by luck, and for the sights they did not: load_pois()
# looked for munich.json, found nothing, and Munich shipped an empty map
# without a word. The mapping is written down here, and a sights file that no
# page asks for now fails the build instead of disappearing quietly.
POI_FILE_FOR_KEY = {"munich": "monaco-di-baviera"}
_POI_FILES_ASKED = set()


def assert_every_poi_file_is_used():
    on_disk = {f[:-5] for f in os.listdir(POI_DIR) if f.endswith(".json")}
    orphan = sorted(on_disk - _POI_FILES_ASKED)
    if orphan:
        raise SystemExit(
            "sights files that no page loaded: %s — a city renders under a key, "
            "and the file has to be that key or listed in POI_FILE_FOR_KEY."
            % ", ".join(orphan))


def load_pois(city_key):
    """Sights for a city, or nothing if it has none yet.

    Only what the page needs reaches the template. The Wikidata id and the
    notability score that decided which places made the cut are editorial
    tools; a visitor has no use for them, so they stay out of the HTML.
    """
    stem = POI_FILE_FOR_KEY.get(city_key, city_key)
    _POI_FILES_ASKED.add(stem)
    path = os.path.join(POI_DIR, f"{stem}.json")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        raw = json.load(f).get("pois", [])
    out = []
    for p in sorted(raw, key=lambda x: x["rank"]):
        if p.get("status") == "TEMPORARILY_CLOSED":
            continue          # not somewhere to send a visitor today
        out.append({
            "name": p["name"], "lat": p["lat"], "lon": p["lon"],
            "cat": p["category"], "cat_label": POI_CATEGORY_LABEL[p["category"]],
            "icon": POI_TYPE_ICON[p["poi_type"]],
            "cat_icon": POI_CATEGORY_ICON[p["category"]], "rank": p["rank"],
        })
    return out


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


EN_TONE_BADGE = {"green": "Relatively safer", "yellow": "Average", "red": "Higher caution advised", "grey": "Not covered"}

# Every area carries a rating. What differs is what stands behind it, and that
# is a separate field rather than a fourth colour: a map of a major city that
# shrugs at a third of its districts is not useful, but a green earned by an
# empty search is not the same claim as a green earned by sources, and the
# site has to be able to say which is which.
EVIDENCE_LABEL = {
    "documented": "",
    "no_findings": "No area-specific findings",
}
EVIDENCE_NOTE = (
    "Sources were reviewed for this area and returned nothing traveller-relevant. "
    "The rating reflects that absence together with the character of the area — "
    "it is not a positive finding of safety, and it carries less weight than a "
    "rating built on documented sources."
)

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
        "grey": "not covered by this dataset",
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
    limited-data text for every non-London city, which was accurate for
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
    city_label = city_only(city_label)
    day_desc = tone_descriptor(zone["day"], city_label)
    night_desc = tone_descriptor(zone["night"], city_label)

    if tier == OFFICIAL_SNAPSHOT:
        source_phrase = crime_source or "a real official crime statistic"
        basis_sentence = (
            f"This rating is derived from {source_phrase} — an official statistic, not an assessment. "
            f"High-footfall tourist, "
            f"transit or shopping areas can read higher on this kind of measure without that meaning "
            f"elevated risk per visit, since these statistics are normalised against registered residents "
            f"rather than footfall — see the note on this page and the methodology page for the full "
            f"caveats."
        )
    elif tier == RESEARCH_BASED:
        basis_sentence = (
            f"This comes from a structured local-source assessment: an area-level review of credible "
            f"local sources — local and national news, municipal and police-published material, and "
            f"official surveys where they exist — consolidated across sources rather than taken from a "
            f"single report. {city_label} publishes no comparable neighbourhood-level crime dataset; "
            f"where a city does, Wandroz uses it instead."
        )
    else:
        basis_sentence = (
            f"This is a limited-data assessment: {city_label} publishes no neighbourhood-level crime "
            f"dataset and this area has not yet had a full source review, so the rating is indicative "
            f"and labelled as such rather than presented as evidenced."
        )

    # Where the area-level review reached nothing specific, the rating still
    # stands — every area on a city map carries one — but the answer says what
    # it rests on. A green earned by an empty search is not the same claim as a
    # green earned by sources, and a visitor is entitled to know which they are
    # reading.
    if zone.get("evidence") == "no_findings":
        faqs = [
            {"q": f"Is {name} safe?",
             "a": (f"Wandroz rates {name} in {city_label} as {day_desc}. That rating rests on an "
                   f"area-level review that reached no traveller-relevant reporting specific to "
                   f"{name} — no incidents, no recurring problems, nothing documented either way — "
                   f"read together with the character of the area. It is not a positive finding of "
                   f"safety: an absence of reporting is weaker evidence than the sourced ratings "
                   f"elsewhere on this map, and it is marked as such wherever it appears.")},
            {"q": f"What was checked for {name}?",
             "a": (f"The same area-level review every other neighbourhood on the {city_label} map "
                   f"gets: local and national news, municipal and police-published material, and "
                   f"official surveys where they exist, searched for this specific area. {name} "
                   f"returned nothing traveller-relevant, which is common for smaller administrative "
                   f"areas without a press profile of their own. Where a review does return "
                   f"something, the sources are named on the area's page.")},
            {"q": f"Is {name} a good area to stay in as a tourist?",
             "a": (f"Nothing documented argues against it. For a stay, weigh that against the areas "
                   f"on the {city_label} map whose ratings are backed by named sources, and check "
                   f"recent reviews for the specific street. You can search accommodation already "
                   f"scoped to this area using the Booking.com link on this page.")},
        ]
        return faqs

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
                  f"neighbourhood-wide rating above is still the limited-data assessment described above, "
                  f"not derived from this burglary figure."
            ),
        })
    elif tier == OFFICIAL_SNAPSHOT:
        faqs.append({
            "q": f"Is there official crime data for {name}?",
            "a": (
                f"Yes. {name}'s rating is derived from {crime_source or 'a real official crime statistic'}, "
                f"not an assessment — see the note on this page for the exact "
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
                f"covering {window} — recomputed from the source data whenever the Met publishes new months, "
                f"not a one-off snapshot. Full "
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



# ---------------------------------------------------------------------------
# The pages every site needs and this one did not have: what the site is, who
# to write to, what it does with a visitor's data, and how its outbound links
# work. Their absence is also the most common reason an affiliate application
# sits in "pending" — compliance pauses any site with no privacy policy and no
# disclosure — so they are written to be true first and to satisfy a reviewer
# second.
# ---------------------------------------------------------------------------
STATIC_PAGES = [
    {
        "slug": "about",
        "title": "About Wandroz — what it is and how it is built",
        "h1": "About Wandroz",
        "description": "Wandroz maps neighbourhood safety for travellers in 25 European cities, "
                       "using official boundaries and, where it exists, official crime data.",
        "lede": "A traveller booking a room can find out what a hotel is like in thirty seconds, "
                "and almost nothing about the four streets around it. Wandroz exists for that gap.",
        "body": """
<h2>What it does</h2>
<p>Wandroz maps every official neighbourhood of 25 European cities and says, per neighbourhood,
what the evidence supports about safety for a visitor — by day and after dark — with the reasoning
and the sources on the page rather than behind a score.</p>

<h2>What it is built on</h2>
<p>Boundaries are always the city's own official administrative geometry. Ratings come from one of
three classes of evidence, and every page says which one it is on: official police or government
crime data; a structured local-source assessment where no such dataset is published; or a
limited-data assessment where neither is available yet. The
<a href="/methodology.html">methodology page</a> sets out all three, the process behind the second,
and the coverage figures city by city, including the unflattering ones.</p>

<h2>What it is not</h2>
<p>It is not a crime-prediction tool, it does not estimate anyone's personal risk, and its ratings
are never comparable between cities. Where the evidence is thin, the page says so instead of
rounding up to a colour.</p>

<h2>Who is behind it</h2>
<p>Wandroz is an independent project, not a company with a newsroom. It is built and maintained by
one person, which is the reason for the emphasis on published sources and checkable claims: the
work has to stand on what it can show, not on who is saying it.</p>

<h2>Credits</h2>
<p>Map data © OpenStreetMap contributors. Crime data for London from
<a href="https://data.police.uk" target="_blank" rel="noopener">data.police.uk</a> under the Open
Government Licence. Neighbourhood boundaries from each city's own open-data portal. Sights resolved
against <a href="https://www.wikidata.org" target="_blank" rel="noopener">Wikidata</a> and
OpenStreetMap. Local sources used for a specific neighbourhood are named on that neighbourhood's
page.</p>
""",
    },
    {
        "slug": "contact",
        "title": "Contact Wandroz",
        "h1": "Contact",
        "description": "How to reach Wandroz: corrections, questions, partnerships and press.",
        "lede": "One address, read by a person.",
        "body": """
<p style="font-size:18px;"><a href="mailto:{email}">{email}</a></p>

<h2>Corrections</h2>
<p>If something on a neighbourhood page is wrong or out of date, that is the most useful thing you
can send. Include the page and, where you can, a source — a local news report, an official figure,
a municipal notice. Every neighbourhood page carries a direct correction link that fills in the
area for you.</p>

<h2>Everything else</h2>
<p>Questions about the method, partnership and licensing enquiries, and press requests go to the
same address.</p>

<h2>What happens to what you send</h2>
<p>Correction emails are read and kept only as long as it takes to act on them. They are not added
to any mailing list, and there is no mailing list. See the
<a href="/privacy.html">privacy policy</a>.</p>
""",
    },
    {
        "slug": "privacy",
        "title": "Privacy policy — Wandroz",
        "h1": "Privacy policy",
        "description": "What Wandroz collects, what it does not, the cookies in use, and how to opt out.",
        "lede": "Last updated 14 September 2026.",
        "body": """
<h2>The short version</h2>
<p>Wandroz has no accounts, no logins, no forms and no newsletter. It does not ask you for personal
data and has nothing to sell. What follows is the complete list of what is nevertheless collected,
by whom, and how to stop it.</p>

<h2>What Wandroz itself collects</h2>
<p>Nothing. There is no database of visitors, no profile, no identifier set by this site.</p>

<h2>Analytics</h2>
<p>The site uses Google Analytics 4 to count visits and see which pages are read. Google sets
cookies in your browser and receives your IP address, which it uses to derive an approximate
location and then discards at full precision. This is used only in aggregate — how many people
read the Rome map, not who read it. The legal basis is legitimate interest in understanding whether
the site is useful; you can object by any of the means below, and nothing on the site stops working
if you do.</p>
<ul>
  <li>Block cookies for this site in your browser's settings.</li>
  <li>Install Google's own
    <a href="https://tools.google.com/dlpage/gaoptout" target="_blank" rel="noopener">opt-out
    browser add-on</a>.</li>
  <li>Use any tracker-blocking extension or a browser that blocks analytics by default.</li>
</ul>

<h2>Hosting</h2>
<p>The site is served as static files by Vercel, which keeps standard server logs (IP address,
request time, page requested, user agent) for security and abuse prevention. Wandroz does not read
these logs to identify anyone.</p>

<h2>Maps and outbound links</h2>
<p>Maps are drawn with Leaflet using tiles from OpenStreetMap; loading a map sends a request to
OpenStreetMap's tile servers, which see your IP address as any image request would. Accommodation
links go to Booking.com, which applies its own privacy policy once you arrive there. See the
<a href="/affiliate-disclosure.html">affiliate disclosure</a> for what those links are and are not.</p>

<h2>What is never done</h2>
<p>No data is sold, rented or shared with advertisers. There are no advertising cookies, no
retargeting pixels, no social-network trackers, and no fingerprinting. Wandroz does not attempt to
identify individual visitors, and nothing on this site is directed at children.</p>

<h2>Your rights</h2>
<p>If you are in the EU, the UK or another jurisdiction with equivalent law, you have the right to
access, correct, delete or object to the processing of personal data relating to you. Since Wandroz
holds no personal data of its own, most requests concern Google Analytics, and the opt-outs above
are the fastest route. If you have written to Wandroz and want that correspondence deleted, say so
and it will be.</p>

<h2>Changes</h2>
<p>Material changes to this page will be dated here. Questions:
<a href="mailto:{email}">{email}</a>.</p>
""",
    },
    {
        "slug": "affiliate-disclosure",
        "title": "Affiliate disclosure — Wandroz",
        "h1": "Affiliate disclosure",
        "description": "How Wandroz's accommodation links work, and what it does and does not earn from them.",
        "lede": "Last updated 14 September 2026.",
        "body": """
<h2>The links</h2>
<p>Every neighbourhood page carries one accommodation link, pointing to a Booking.com search already
scoped to that area. Where Booking.com has no search area for a neighbourhood, the link searches the
surrounding district or the city instead, and the note under the button says which of the three it
is — verified against Booking, not assumed.</p>

<h2>What Wandroz earns from them today</h2>
<p><strong>Nothing.</strong> The links carry no affiliate or tracking parameters and are not
commissioned. An application to Booking.com's affiliate programme is in progress. If and when those
links start earning a commission, this page will be updated with the date, every commissioned link
will be disclosed as such, and this notice will change from "nothing" to the actual arrangement.</p>

<h2>What a commission would and would not change</h2>
<p>It would not change a rating. Safety levels come from the evidence classes set out on the
<a href="/methodology.html">methodology page</a> and are written before any link is generated; a
neighbourhood's rating has never depended on how many rooms are bookable in it, and a commercial
arrangement would not make it depend on that. The link is downstream of the rating and always will
be.</p>
<p>Nor would it cost you anything: an affiliate commission is paid by the booking platform out of
its own margin, at no additional cost to the traveller.</p>

<h2>Other relationships</h2>
<p>Wandroz takes no payment for coverage, placement or a rating, from cities, hotels, tourist boards
or anyone else. There is no advertising on the site. If that ever changes it will be disclosed here
before it appears anywhere else.</p>

<h2>Questions</h2>
<p><a href="mailto:{email}">{email}</a></p>
""",
    },
]


def render_static_pages():
    """The about / contact / privacy / disclosure set."""
    tpl = env.get_template("page.html")
    urls = []
    for page in STATIC_PAGES:
        url = f"{SITE_URL}/{page['slug']}.html"
        html = tpl.render(
            lang="en", canonical_url=url,
            page_title=page["title"], page_description=page["description"],
            page_h1=page["h1"], lede=page["lede"],
            body=Markup(page["body"].replace("{email}", CORRECTION_EMAIL)),
        )
        with open(os.path.join(OUT_DIR, f"{page['slug']}.html"), "w") as f:
            f.write(html)
        print(f"Wrote {os.path.join(OUT_DIR, page['slug'] + '.html')}")
        urls.append(url)
    return urls


def group_zones(zones, js_zones):
    """Zones gathered under their own city's district, when the data says so.

    A city map ends with a list of every neighbourhood on it. At 155 names that
    list is a wall: nobody scans Rome looking for "Tor San Giovanni", they look
    for the part of town their hotel is in. Where a zone carries a `group` —
    its arrondissement, its Bezirk, its municipio — the list is built under
    those headings, each showing how its own areas split across the levels.
    Cities without groups keep the flat list; nothing is invented to fill one.
    """
    if not any(z.get("group") for z in zones):
        return []
    url_of = {z["slug"]: z.get("url") for z in js_zones}
    order, buckets = [], {}
    for z in zones:
        g = z.get("group") or "Other areas"
        if g not in buckets:
            buckets[g] = []
            order.append(g)
        buckets[g].append(z)
    ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
             "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
             "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20}

    def natural(name):
        # "10th arrondissement" must not sort before "1st", and Rome's
        # Municipio IX must not sort before Municipio V — which is exactly what
        # alphabetical order does to Roman numerals.
        m = re.match(r"^(\d+)", name)
        if m:
            return (0, int(m.group(1)), "")
        m = re.search(r"\b([IVXL]+)$", name)
        if m and m.group(1) in ROMAN:
            return (0, ROMAN[m.group(1)], "")
        return (1, 0, name.lower())

    out = []
    for name in sorted(order, key=natural):
        rows = sorted(buckets[name], key=lambda z: z["name"])
        tones = {}
        for z in rows:
            t = z.get("day") or "grey"
            tones[t] = tones.get(t, 0) + 1
        out.append({
            "name": name,
            "zones": [{"name": z["name"], "url": url_of.get(z["slug"], "")} for z in rows],
            "tones": [(t, tones[t]) for t in ("red", "yellow", "green", "grey") if tones.get(t)],
        })
    return out


def render_illustrative_city(city_key, url_slug, ui, tone_badge, extra_zone_data=None, flat=False):
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
            "evidence": z.get("evidence", "documented"),
            "evidence_label": EVIDENCE_LABEL.get(z.get("evidence", "documented"), ""),
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
        canonical_url=canonical, city_links=CITY_LINKS, city_country_links=CITY_LINKS_BY_COUNTRY,
        page_h1=ui["page_h1"], page_lead=ui["page_lead"],
        data_note=evidence_line(city_key, len(zones)), show_toggle=show_toggle,
        label_day=ui["label_day"], label_night=ui["label_night"],
        legend_green=ui["legend_green"], legend_yellow=legend_yellow,
        legend_red=ui["legend_red"], legend_grey=ui["legend_grey"],
        has_grey=any(z["day"] == "grey" or z["night"] == "grey" for z in zones),
        has_no_findings=any(z.get("evidence") == "no_findings" for z in zones),
        label_zone_detail=ui["label_zone_detail"], label_click_hint=ui["label_click_hint"],
        label_all_zones=ui["label_all_zones"], label_booking=ui["label_booking"],
        label_more=ui["label_more"], label_not_covered="",
        pois=load_pois(city_key), poi_filter_all="All",
        footer_note=ui["footer_note"],
        zones=js_zones, zone_groups=group_zones(zones, js_zones),
        center=data["center"], zoom=data["zoom"],
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
        zone_ctx["evidence_label"] = EVIDENCE_LABEL.get(z.get("evidence", "documented"), "")
        zone_ctx["evidence_note"] = EVIDENCE_NOTE if z.get("evidence") == "no_findings" else ""
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
            label_booking_note=booking_note(ui, z.get("booking_scope", "area")),
            data_note=method_note(city_key, data["label"],
                                  no_findings=(z.get("evidence") == "no_findings")),
            footer_note=ui["footer_note"], correction_email=CORRECTION_EMAIL,
            evidence_tag=evidence_line(city_key, len(zones)),
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
    # One line, like every other city, and it names the window rather than
    # promising a cadence: the monthly refresh is a manual, gated run today,
    # so "refreshed automatically every month" was a claim the site could not
    # keep. Each borough page still carries the exact months behind its score.
    data_note = (
        f"{LONDON_EVIDENCE_TAG} · Metropolitan Police recorded crime (data.police.uk) · "
        f"{live_count} of {total_zones} boroughs scored, {london_window()}"
    )
    html = map_tpl.render(
        lang="en", city_label="London", tagline="Neighbourhood safety for travellers",
        nav_home="Home", nav_methodology="Methodology", canonical_url=canonical, city_links=CITY_LINKS, city_country_links=CITY_LINKS_BY_COUNTRY,
        page_title="Is my London borough safe? — Wandroz",
        page_description="Interactive map of all 33 London boroughs, day/night ratings computed from real Metropolitan Police open crime data.",
        page_h1="London boroughs", page_lead="Click a borough on the map to see its level, the reasoning, and a Booking.com link for that area.",
        data_note=data_note, show_toggle=True,
        label_day="day", label_night="night",
        legend_green=EN_TONE_BADGE["green"], legend_yellow=EN_TONE_BADGE["yellow"],
        legend_red=EN_TONE_BADGE["red"], legend_grey=EN_TONE_BADGE["grey"],
        has_grey=any(z["day"] == "grey" or z["night"] == "grey" for z in js_zones),
        has_no_findings=False,
        label_zone_detail="Borough detail", label_click_hint="Click a borough on the map to see its level, the reasoning, and a Booking.com link for that area.",
        label_all_zones="All boroughs", label_booking="Search accommodation here on Booking.com →",
        label_more="See the auto-updating live data →",
        label_not_covered="",
        pois=load_pois("london"), poi_filter_all="All",
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
        ("bologna", "bologna", "Bologna", True),
        ("verona", "verona", "Verona", True),
        ("genova", "genova", "Genoa", True),
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
        ("bologna", "bologna", "Bologna", True),
        ("verona", "verona", "Verona", True),
        ("genova", "genova", "Genoa", True),
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
    "legend_grey": "Not covered by this dataset",
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
    "page_description": "Interactive map of Milan's neighbourhoods (real official NIL boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Milan neighbourhoods",
    "neigh_title": "Is {name} in Milan safe? | Wandroz",
})

ROMA_UI = dict(TORINO_UI)
ROMA_UI.update({
    "page_title": "Is my Rome neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Rome's neighbourhoods (real official Zone Urbanistiche boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Rome neighbourhoods",
    "neigh_title": "Is {name} in Rome safe? | Wandroz",
})

BARCELONA_UI = dict(TORINO_UI)
BARCELONA_UI.update({
    "page_title": "Is my Barcelona neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Barcelona's 73 official barris (real official Ajuntament boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Barcelona neighbourhoods",
    "neigh_title": "Is {name} in Barcelona safe? | Wandroz",
})


MADRID_UI = dict(TORINO_UI)
MADRID_UI.update({
    "page_title": "Is my Madrid neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Madrid's 131 official barrios (real official Ayuntamiento boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Madrid neighbourhoods",
    "neigh_title": "Is {name} in Madrid safe? | Wandroz",
})


VIENNA_UI = dict(TORINO_UI)
VIENNA_UI.update({
    "page_title": "Is my Vienna neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Vienna's 23 official Bezirke (real official Statistik Austria boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Vienna neighbourhoods",
    "neigh_title": "Is {name} in Vienna safe? | Wandroz",
})


LISBON_UI = dict(TORINO_UI)
LISBON_UI.update({
    "page_title": "Is my Lisbon neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Lisbon's 24 official freguesias (real official Câmara Municipal de Lisboa boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Lisbon neighbourhoods",
    "neigh_title": "Is {name} in Lisbon safe? | Wandroz",
})


PARIS_UI = dict(TORINO_UI)
PARIS_UI.update({
    "page_title": "Is my Paris neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Paris's 80 official quartiers administratifs (real official City of Paris boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Paris neighbourhoods",
    "neigh_title": "Is {name} in Paris safe? | Wandroz",
})


BERLIN_UI = dict(TORINO_UI)
BERLIN_UI.update({
    "page_title": "Is my Berlin neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Berlin's 143 official Bezirksregionen with real official Polizei Berlin crime-rate data (Häufigkeitszahl) per zone.",
    "page_h1": "Berlin neighbourhoods",
    "neigh_title": "Is {name} in Berlin safe? | Wandroz",
})


AMSTERDAM_UI = dict(TORINO_UI)
AMSTERDAM_UI.update({
    "page_title": "Is my Amsterdam neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Amsterdam's 110 official wijken with real official CBS crime-rate data per zone.",
    "page_h1": "Amsterdam neighbourhoods",
    "neigh_title": "Is {name} in Amsterdam safe? | Wandroz",
})


PRAHA_UI = dict(TORINO_UI)
PRAHA_UI.update({
    "page_title": "Is my Prague neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Prague's 57 official mestske casti (city districts) with real official Policie CR crime-rate data per district.",
    "page_h1": "Prague neighbourhoods",
    "neigh_title": "Is {name} in Prague safe? | Wandroz",
})


OSLO_UI = dict(TORINO_UI)
OSLO_UI.update({
    "page_title": "Is my Oslo neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Oslo's 15 official bydeler (city boroughs) plus Sentrum (the city centre) with real official Oslo kommune crime-rate data per zone.",
    "page_h1": "Oslo neighbourhoods",
    "neigh_title": "Is {name} in Oslo safe? | Wandroz",
})


MUNICH_UI = dict(TORINO_UI)
MUNICH_UI.update({
    "page_title": "Is my Munich neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Munich's 25 official Stadtbezirke (city districts) with real official Polizeipraesidium Muenchen crime-rate data per zone.",
    "page_h1": "Munich neighbourhoods",
    "neigh_title": "Is {name} in Munich safe? | Wandroz",
})


STOCKHOLM_UI = dict(TORINO_UI)
STOCKHOLM_UI.update({
    "page_title": "Is my Stockholm neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Stockholm's 11 official stadsdelsnämnder (city district committees) with real official Brå crime-rate data per district.",
    "page_h1": "Stockholm neighbourhoods",
    "neigh_title": "Is {name} in Stockholm safe? | Wandroz",
})


BRUSSELS_UI = dict(TORINO_UI)
BRUSSELS_UI.update({
    "page_title": "Is my Brussels neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Brussels' 19 official communes with real official BISA/Federale Politie crime-rate data per commune.",
    "page_h1": "Brussels neighbourhoods",
    "neigh_title": "Is {name} in Brussels safe? | Wandroz",
})


ATHENS_UI = dict(TORINO_UI)
ATHENS_UI.update({
    "page_title": "Is my Athens neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Athens' 7 official Δημοτικές Κοινότητες (Municipal Districts, real official City of Athens boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Athens neighbourhoods",
    "neigh_title": "Is {name} in Athens safe? | Wandroz",
})


VENEZIA_UI = dict(TORINO_UI)
VENEZIA_UI.update({
    "page_title": "Is my Venice neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Venice's 6 official Municipalità (real official Comune di Venezia administrative districts, mainland included) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Venice neighbourhoods",
    "neigh_title": "Is {name} in Venice safe? | Wandroz",
})


FIRENZE_UI = dict(TORINO_UI)
FIRENZE_UI.update({
    "page_title": "Is my Florence neighbourhood safe? — Wandroz",
    "page_description": (
        "Interactive map of Florence's 74 official Aree elementari (real Comune di "
        "Firenze statistical zones) with day/night safety levels from a structured "
        "local-source assessment."
    ),
    "page_h1": "Florence neighbourhoods",
    "neigh_title": "Is {name} in Florence safe? | Wandroz",
})

# Carried over verbatim from the hand-built dist/firenze/index.html that this
# city was recovered from — it is Florence's honesty disclosure, so migrating
# it must not paraphrase it. Same text as firenze.json's dataNote.

DUBLIN_UI = dict(TORINO_UI)
DUBLIN_UI.update({
    "page_title": "Is my Dublin neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Dublin City's 11 official Local Electoral Areas (real Dublin City Council electoral geography) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Dublin neighbourhoods",
    "neigh_title": "Is {name} in Dublin safe? | Wandroz",
})


EDINBURGH_UI = dict(TORINO_UI)
EDINBURGH_UI.update({
    "page_title": "Is my Edinburgh neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Edinburgh's 17 official City of Edinburgh Council wards with day/night safety levels anchored to real crimes-per-1,000-population figures per ward.",
    "page_h1": "Edinburgh neighbourhoods",
    "neigh_title": "Is {name} in Edinburgh safe? | Wandroz",
})


NAPOLI_UI = dict(TORINO_UI)
NAPOLI_UI.update({
    "page_title": "Is my Naples neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Naples's 10 official Municipalità (real official administrative boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Naples neighbourhoods",
    "neigh_title": "Is {name} in Naples safe? | Wandroz",
})


GENOVA_UI = dict(TORINO_UI)
GENOVA_UI.update({
    "page_title": "Is my Genoa neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Genoa's 9 official municipi (real official administrative boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Genoa neighbourhoods",
    "neigh_title": "Is {name} in Genoa safe? | Wandroz",
})


VERONA_UI = dict(TORINO_UI)
VERONA_UI.update({
    "page_title": "Is my Verona neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Verona's 8 official circoscrizioni (real official administrative boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Verona neighbourhoods",
    "neigh_title": "Is {name} in Verona safe? | Wandroz",
})


BOLOGNA_UI = dict(TORINO_UI)
BOLOGNA_UI.update({
    "page_title": "Is my Bologna neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Bologna's 6 official quartieri (real official administrative boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Bologna neighbourhoods",
    "neigh_title": "Is {name} in Bologna safe? | Wandroz",
})


BUDAPEST_UI = dict(TORINO_UI)
BUDAPEST_UI.update({
    "page_title": "Is my Budapest neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Budapest's 23 official kerületek (real official administrative boundaries) with day/night safety levels from a structured local-source assessment.",
    "page_h1": "Budapest neighbourhoods",
    "neigh_title": "Is {name} in Budapest safe? | Wandroz",
})


KRAKOW_UI = dict(TORINO_UI)
KRAKOW_UI.update({
    "page_title": "Is my Kraków neighbourhood safe? — Wandroz",
    "page_description": "Interactive map of Kraków's 18 official dzielnice (real official administrative boundaries) with day/night safety levels based on current local press and official survey research.",
    "page_h1": "Kraków neighbourhoods",
    "neigh_title": "Is {name} in Kraków safe? | Wandroz",
})


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
    real day/night tones (green by day, yellow by night, from its
    area-level source review — see methodology.html) demonstrate exactly the thing a
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
    sitemap_urls.extend(render_static_pages())

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
    # Milan and Rome's day/night ratings come from a structured local-source
    # assessment (see methodology.html), not official crime statistics, so
    # their tag does not claim "official data" beyond the boundaries.
    def _zone_count(city_key):
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        with open(path) as f:
            return len(json.load(f)["zones"])

    city_cards = [
        {"name": "London", "url": "london/index.html", "flag": "🇬🇧",
         "blurb": f"33 boroughs on the map, {london_live_count} scored from real Metropolitan Police open crime data ({london_window()}).",
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
         "blurb": "All 88 official zones mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 45.4642, "lon": 9.1900, "color": "#3fae6b",
         "zone_count": _zone_count("milano"), "data_tag": "Official boundaries"},
        {"name": "Rome", "url": "roma/index.html", "flag": "🇮🇹",
         "blurb": "All 155 official zones mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
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
         "blurb": "All 73 official barris mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 41.3874, "lon": 2.1686, "color": "#c94f7c",
         "zone_count": _zone_count("barcelona"), "data_tag": "Official boundaries"},
        {"name": "Madrid", "url": "madrid/index.html", "flag": "🇪🇸",
         "blurb": "All 131 official barrios mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 40.4168, "lon": -3.7038, "color": "#d98e04",
         "zone_count": _zone_count("madrid"), "data_tag": "Official boundaries"},
        {"name": "Vienna", "url": "vienna/index.html", "flag": "🇦🇹",
         "blurb": "All 23 official Bezirke mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 48.2082, "lon": 16.3738, "color": "#5b8c5a",
         "zone_count": _zone_count("vienna"), "data_tag": "Official boundaries"},
        {"name": "Lisbon", "url": "lisbon/index.html", "flag": "🇵🇹",
         "blurb": "All 24 official freguesias mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 38.7223, "lon": -9.1393, "color": "#c9483f",
         "zone_count": _zone_count("lisbon"), "data_tag": "Official boundaries"},
        {"name": "Paris", "url": "paris/index.html", "flag": "🇫🇷",
         "blurb": "All 80 official quartiers administratifs mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 48.8566, "lon": 2.3522, "color": "#3468c0",
         "zone_count": _zone_count("paris"), "data_tag": "Official boundaries"},
        {"name": "Brussels", "url": "brussels/index.html", "flag": "🇧🇪",
         "blurb": "All 19 official communes mapped, safety levels from BISA/Federale Politie's real official 2025 crime and Statbel population statistics.",
         "lat": 50.8503, "lon": 4.3517, "color": "#34495e",
         "zone_count": _zone_count("brussels"), "data_tag": "Official police data"},
        {"name": "Athens", "url": "athens/index.html", "flag": "🇬🇷",
         "blurb": "All 7 official Municipal Districts mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 37.9838, "lon": 23.7275, "color": "#1477a6",
         "zone_count": _zone_count("athens"), "data_tag": "Official boundaries"},
        {"name": "Venice", "url": "venezia/index.html", "flag": "🇮🇹",
         "blurb": "All 6 official Municipalità mapped, mainland included, safety ratings from a structured local-source assessment, area by area.",
         "lat": 45.4408, "lon": 12.3155, "color": "#7a2048",
         "zone_count": _zone_count("venezia"), "data_tag": "Official boundaries"},
        {"name": "Dublin", "url": "dublin/index.html", "flag": "🇮🇪",
         "blurb": "All 11 official Local Electoral Areas mapped, real council electoral boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 53.3498, "lon": -6.2603, "color": "#4b0082",
         "zone_count": _zone_count("dublin"), "data_tag": "Official boundaries"},
        {"name": "Genoa", "url": "genova/index.html", "flag": "🇮🇹",
         "blurb": "All 9 official municipi mapped, real administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 44.4072, "lon": 8.9340, "color": "#1f6f8b",
         "zone_count": _zone_count("genova"), "data_tag": "Official boundaries"},
        {"name": "Verona", "url": "verona/index.html", "flag": "🇮🇹",
         "blurb": "All 8 official circoscrizioni mapped, real administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 45.4384, "lon": 10.9916, "color": "#6b4f9e",
         "zone_count": _zone_count("verona"), "data_tag": "Official boundaries"},
        {"name": "Bologna", "url": "bologna/index.html", "flag": "🇮🇹",
         "blurb": "All 6 official quartieri mapped, real administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 44.4938, "lon": 11.3426, "color": "#a33b20",
         "zone_count": _zone_count("bologna"), "data_tag": "Official boundaries"},
        {"name": "Florence", "url": "firenze/index.html", "flag": "🇮🇹",
         "blurb": "All 74 official quartieri/zone mapped, real Comune di Firenze boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 43.7696, "lon": 11.2558, "color": "#9c6b3e",
         "zone_count": 74, "data_tag": "Official boundaries"},
        {"name": "Edinburgh", "url": "edinburgh/index.html", "flag": "🇬🇧",
         "blurb": "All 17 official City of Edinburgh Council wards mapped, safety ratings anchored to real crimes-per-1,000-population figures per ward.",
         "lat": 55.9533, "lon": -3.1883, "color": "#0f4c81",
         "zone_count": _zone_count("edinburgh"), "data_tag": "Official boundaries"},
        {"name": "Naples", "url": "napoli/index.html", "flag": "🇮🇹",
         "blurb": "All 10 official Municipalità mapped, real OpenStreetMap administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 40.8518, "lon": 14.2681, "color": "#c0392b",
         "zone_count": _zone_count("napoli"), "data_tag": "Official boundaries"},
        {"name": "Budapest", "url": "budapest/index.html", "flag": "🇭🇺",
         "blurb": "All 23 official kerületek mapped, real OpenStreetMap administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
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
        "Venice": "venezia", "Dublin": "dublin", "Edinburgh": "edinburgh", "Naples": "napoli", "Bologna": "bologna", "Verona": "verona", "Genoa": "genova",
        "Budapest": "budapest", "Kraków": "krakow", "Florence": "firenze",
        # London already has its own correct "Official police data" tag above (a real
        # automated data.police.uk pipeline, not this dict's illustrative-city tiers).
        # Florence IS in CITY_METHODOLOGY now (RESEARCH_BASED, recovered from
        # dist/firenze/ into data_zones/firenze.json), so its card tag derives from
        # the tier like every other city instead of the stale hardcoded "Official
        # boundaries" — which described the boundary provenance, not the evidence
        # behind the rating.
    }
    for _c in UK_CITIES:
        _CITY_CARD_TO_METHOD_KEY[_c["city"]] = _c["key"]
    _EVIDENCE_TAG_BY_TIER = {
        OFFICIAL_SNAPSHOT: "Official crime data",
        RESEARCH_BASED: "Local-source assessment",
        MANUAL_EXPERIMENTAL: "Limited-data assessment",
    }
    for _card in city_cards:
        _mkey = _CITY_CARD_TO_METHOD_KEY.get(_card["name"])
        _method = CITY_METHODOLOGY.get(_mkey) if _mkey else None
        if _method:
            _tag = _EVIDENCE_TAG_BY_TIER[_method["tier"]]
            if _mkey == "zurigo":
                _tag += " + district burglary data"
            _card["data_tag"] = _tag
    city_cards += [
        {"name": c["city"], "url": "%s/index.html" % c["key"], "flag": "🇬🇧",
         "blurb": ("All %d official wards mapped, day and night levels computed from real "
                   "%s street-level crime records." % (_zone_count(c["key"]), c["force"])),
         "lat": c["lat"], "lon": c["lon"], "color": c["color"],
         "zone_count": _zone_count(c["key"]), "data_tag": "Official police data"}
        for c in UK_CITIES
    ]

    # Florence has no CITY_METHODOLOGY entry (it's a hand-built page, not
    # rendered by this pipeline — see the comment above), so it falls
    # through the loop above and would otherwise keep the old, boundary-only
    # "Official boundaries" tag. Its own blurb already says the ratings come
    # from an area-by-area local-source assessment, i.e. the same evidence
    # tier as the other RESEARCH_BASED cities — set the homepage tag to
    # match honestly instead of leaving a stale provenance-only label. This
    # is a homepage-presentation fix only; it does not add Florence to
    # CITY_METHODOLOGY or touch its generation.
    for _card in city_cards:
        if _card["name"] == "Florence":
            _card["data_tag"] = _EVIDENCE_TAG_BY_TIER[RESEARCH_BASED]

    preview_zone = build_homepage_preview()
    # Country-grouped view of the same city_cards data (no separate
    # hand-maintained destination list — see group_cities_by_country()) plus
    # a small curated "Popular destinations" shortcut, ordered to match
    # POPULAR_CITY_NAMES rather than city_cards' launch order.
    countries = group_cities_by_country(city_cards)
    _popular_by_name = {c["name"]: c for c in city_cards}
    popular_cities = [_popular_by_name[n] for n in POPULAR_CITY_NAMES if n in _popular_by_name]
    with open(os.path.join(OUT_DIR, "index.html"), "w") as f:
        f.write(index_tpl.render(
            city_cards=city_cards, countries=countries, popular_cities=popular_cities,
            preview_zone=preview_zone, canonical_url=SITE_URL + "/",
        ))

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
            london_window=london_window(),
            uk_cities=[c["city"] for c in UK_CITIES],
            uk_forces=sorted({c["force"] for c in UK_CITIES}),
            ev=evidence_stats(),
        ))
    print(f"Wrote {os.path.join(OUT_DIR, 'methodology.html')}")

    # London's borough pages were the only zone pages on the site with no
    # accommodation link at all: 32 pages that answer "is this area safe?" and
    # then leave the reader with nowhere to go. The destination string is the
    # one the London map already uses for that borough, so the two cannot
    # disagree about where a click lands.
    london_queries = {}
    try:
        with open(os.path.join(ZONES_DIR, "london_boundaries.json")) as f:
            for z in json.load(f)["zones"]:
                if z.get("query"):
                    london_queries[_canon(z["name"])] = z["query"]
    except Exception:
        pass

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
                evidence_tag="%s · Metropolitan Police recorded crime · %s"
                              % (LONDON_EVIDENCE_TAG, london_window()),
                booking_query=london_queries.get(_canon(b["borough"])),
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

    torino_urls = render_illustrative_city("torino", "torino", TORINO_UI, EN_TONE_BADGE)
    sitemap_urls.extend(torino_urls)
    zurich_zone_burglary = build_zurich_zone_burglary()
    zurigo_urls = render_illustrative_city(
        "zurigo", "zurigo", ZURIGO_UI, EN_TONE_BADGE, extra_zone_data=zurich_zone_burglary,
    )
    sitemap_urls.extend(zurigo_urls)
    london_map_urls = render_london_map(cities)
    sitemap_urls.extend(london_map_urls)
    milano_urls = render_illustrative_city("milano", "milano", MILANO_UI, EN_TONE_BADGE)
    sitemap_urls.extend(milano_urls)
    roma_urls = render_illustrative_city("roma", "roma", ROMA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(roma_urls)
    berlin_urls = render_illustrative_city("berlin", "berlin", BERLIN_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(berlin_urls)
    amsterdam_urls = render_illustrative_city("amsterdam", "amsterdam", AMSTERDAM_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(amsterdam_urls)
    praha_urls = render_illustrative_city("praha", "praha", PRAHA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(praha_urls)
    oslo_urls = render_illustrative_city("oslo", "oslo", OSLO_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(oslo_urls)
    munich_urls = render_illustrative_city("munich", "monaco-di-baviera", MUNICH_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(munich_urls)
    stockholm_urls = render_illustrative_city("stockholm", "stockholm", STOCKHOLM_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(stockholm_urls)
    barcelona_urls = render_illustrative_city("barcelona", "barcelona", BARCELONA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(barcelona_urls)
    madrid_urls = render_illustrative_city("madrid", "madrid", MADRID_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(madrid_urls)
    vienna_urls = render_illustrative_city("vienna", "vienna", VIENNA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(vienna_urls)
    lisbon_urls = render_illustrative_city("lisbon", "lisbon", LISBON_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(lisbon_urls)
    paris_urls = render_illustrative_city("paris", "paris", PARIS_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(paris_urls)
    brussels_urls = render_illustrative_city("brussels", "brussels", BRUSSELS_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(brussels_urls)
    athens_urls = render_illustrative_city("athens", "athens", ATHENS_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(athens_urls)
    venezia_urls = render_illustrative_city("venezia", "venezia", VENEZIA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(venezia_urls)
    dublin_urls = render_illustrative_city("dublin", "dublin", DUBLIN_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(dublin_urls)
    edinburgh_urls = render_illustrative_city("edinburgh", "edinburgh", EDINBURGH_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(edinburgh_urls)
    napoli_urls = render_illustrative_city("napoli", "napoli", NAPOLI_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(napoli_urls)
    bologna_urls = render_illustrative_city("bologna", "bologna", BOLOGNA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(bologna_urls)
    verona_urls = render_illustrative_city("verona", "verona", VERONA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(verona_urls)
    genova_urls = render_illustrative_city("genova", "genova", GENOVA_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(genova_urls)
    budapest_urls = render_illustrative_city("budapest", "budapest", BUDAPEST_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(budapest_urls)
    krakow_urls = render_illustrative_city("krakow", "krakow", KRAKOW_UI, EN_TONE_BADGE, flat=True)
    sitemap_urls.extend(krakow_urls)
    for _c in UK_CITIES:
        sitemap_urls.extend(render_illustrative_city(
            _c["key"], _c["key"], uk_city_ui(_c["city"]), EN_TONE_BADGE, flat=True))
    firenze_urls = render_illustrative_city(
        "firenze", "firenze", FIRENZE_UI, EN_TONE_BADGE,
        flat=True,
    )
    sitemap_urls.extend(firenze_urls)
    print(f"Rendered interactive map hubs: Torino ({len(torino_urls)}), Zurigo ({len(zurigo_urls)}), London ({len(london_map_urls)}), Milano ({len(milano_urls)}), Roma ({len(roma_urls)}), Berlin ({len(berlin_urls)}), Amsterdam ({len(amsterdam_urls)}), Prague ({len(praha_urls)}), Oslo ({len(oslo_urls)}), Munich ({len(munich_urls)}), Stockholm ({len(stockholm_urls)}), Barcelona ({len(barcelona_urls)}), Madrid ({len(madrid_urls)}), Vienna ({len(vienna_urls)}), Lisbon ({len(lisbon_urls)}), Paris ({len(paris_urls)}), Brussels ({len(brussels_urls)}), Athens ({len(athens_urls)}), Venice ({len(venezia_urls)}), Dublin ({len(dublin_urls)}), Edinburgh ({len(edinburgh_urls)}), Naples ({len(napoli_urls)}), Bologna ({len(bologna_urls)}), Verona ({len(verona_urls)}), Genoa ({len(genova_urls)}), Budapest ({len(budapest_urls)}), Kraków ({len(krakow_urls)}), Firenze ({len(firenze_urls)})")

    assert_every_poi_file_is_used()
    write_robots_and_sitemap(sitemap_urls)


if __name__ == "__main__":
    main()
