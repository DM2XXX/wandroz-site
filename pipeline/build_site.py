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

import hashlib
import json
import math
import os
import urllib.parse
import re
import shutil
import i18n
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

# ---------------------------------------------------------------------------
# GEOMETRY DELIVERED TO THE BROWSER
#
# WHY THIS EXISTS
#   A map needs its polygons in the browser, so the boundaries are public by
#   construction. That is not the problem. The problem was the FORM they were
#   published in: 14 decimal places — sub-millimetre — and every vertex the
#   source gave us, for 62 cities, in one 6 MB file at the site root. That is
#   not a map, it is a geodetic dataset, and the work that went into it (the
#   twenty fetchers, the boundary/name matching, the cleaning) was being handed
#   over complete with one curl.
#
# WHAT THIS DOES AND DOES NOT ACHIEVE
#   It does not make the data unobtainable and nothing here pretends to. It
#   removes the part of the value that was never needed to draw a map:
#   authoritative precision. After this, what we publish is a rendering-grade
#   outline — correct to a couple of metres, which is invisible at any zoom a
#   visitor uses and useless to anyone wanting to reuse our boundaries as
#   administrative geometry.
#
# THE TWO NUMBERS
#   GEOM_DECIMALS = 5 is about 1.1 m of quantisation. At zoom 13, where a city
#   map opens, one pixel is roughly 13 m.
#   GEOM_TOLERANCE_DEG = 2e-5 is about 2.2 m of Douglas-Peucker tolerance. It
#   halves the vertex count (539,380 -> 265,095 across the site) and stays
#   under two pixels even at zoom 16. Worst case the two together move a
#   boundary by ~3 m.
#   Both are deliberately conservative: the cheap win is the precision, and a
#   tolerance aggressive enough to be visible would be trading the product's
#   own quality for a protection that a determined copier defeats anyway.
GEOM_DECIMALS = 5
GEOM_TOLERANCE_DEG = 2e-5


def _simplify_ring(ring, tol):
    """Douglas-Peucker, iterative (a recursive one blows the stack on the
    longer coastal rings). Distances are measured with longitude scaled by
    cos(latitude), so the tolerance means the same number of metres on both
    axes instead of shrinking towards the poles."""
    if len(ring) < 5:
        return [list(p) for p in ring]
    klon = math.cos(math.radians(ring[0][0])) or 1.0
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ay, ax = ring[a][0], ring[a][1] * klon
        by, bx = ring[b][0], ring[b][1] * klon
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            py, px = ring[i][0], ring[i][1] * klon
            if den == 0.0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / den
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    out = [list(p) for p, k in zip(ring, keep) if k]
    # A ring that decimates to a line is not a polygon. It has not happened on
    # this data, but a silent sliver would be worse than a few extra vertices.
    return out if len(out) >= 4 else [list(p) for p in ring]


def simplify_rings(coords):
    """Rendering-grade version of one zone's coordinate rings: decimated, then
    rounded. Rounding last so the output is exactly what ships — rounding
    first and simplifying after would leave numbers the simplifier reasoned
    about but the file does not contain."""
    if not coords:
        return coords
    out = []
    for ring in coords:
        if not ring or not isinstance(ring[0], (list, tuple)):
            continue
        thin = _simplify_ring(ring, GEOM_TOLERANCE_DEG)
        out.append([[round(p[0], GEOM_DECIMALS), round(p[1], GEOM_DECIMALS)] for p in thin])
    return out


def load_zone_file(path):
    """The one door every zone file comes through, so no output path can
    accidentally keep full-precision geometry. Reads the source untouched on
    disk and hands back the rendering-grade version — the maps, the area
    pages and the published boundary files therefore all draw the same
    shapes, which the homepage's point-in-polygon search depends on."""
    with open(path) as f:
        data = json.load(f)
    for z in data.get("zones", []):
        if z.get("coords"):
            z["coords"] = simplify_rings(z["coords"])
    return data


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




ILLUSTRATIVE_CITIES = [

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

# ---------------------------------------------------------------------------
# Citta' di classe B aggiunte dopo il primo blocco. Prima ognuna voleva undici
# modifiche sparse in questo file — tier, data di revisione, etichetta, paese,
# link di navigazione, due liste "illustrative", la mappa dei data tag, la
# scheda in homepage, la chiamata di render e la riga di log — piu' una nel
# QA. Undici punti moltiplicati per le citta' che mancano sono trecento
# occasioni di dimenticarne uno, e dimenticarne uno non rompe la build: fa
# sparire la citta' da un menu e basta. Qui la riga e' una.
RESEARCH_CITIES = [
    {"key": "bologna", "label": "Bologna", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 44.4938, "lon": 11.3426, "color": "#a33b20",
     "areas": "6 official quartieri", "reviewed": "14 September 2026"},
    {"key": "verona", "label": "Verona", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 45.4384, "lon": 10.9916, "color": "#6b4f9e",
     "areas": "8 official circoscrizioni", "reviewed": "15 September 2026"},
    {"key": "genova", "label": "Genoa", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 44.4072, "lon": 8.9340, "color": "#1f6f8b",
     "areas": "9 official municipi", "reviewed": "15 September 2026"},
    {"key": "trieste", "label": "Trieste", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 45.6495, "lon": 13.7681, "color": "#2e7d6b",
     "areas": "7 official rioni", "reviewed": "16 September 2026"},
    {"key": "catania", "label": "Catania", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 37.5022, "lon": 15.0873, "color": "#b5453a",
     "areas": "6 official municipalità", "reviewed": "16 September 2026"},
    {"key": "parma", "label": "Parma", "country": "Italy", "flag": "\U0001F1EE\U0001F1F9",
     "lat": 44.8015, "lon": 10.3279, "color": "#4f8f5a",
     "areas": "13 official quartieri", "reviewed": "16 September 2026"},
    {"key": "warsaw", "label": "Warsaw", "country": "Poland", "flag": "\U0001F1F5\U0001F1F1",
     "lat": 52.2297, "lon": 21.0122, "color": "#a8323c",
     "areas": "18 official dzielnice", "reviewed": "16 September 2026"},
    {"key": "tallinn", "label": "Tallinn", "country": "Estonia", "flag": "\U0001F1EA\U0001F1EA",
     "lat": 59.4370, "lon": 24.7536, "color": "#3f6fa8",
     "areas": "8 official linnaosad", "reviewed": "17 September 2026"},
    {"key": "zagreb", "label": "Zagreb", "country": "Croatia", "flag": "\U0001F1ED\U0001F1F7",
     "lat": 45.8150, "lon": 15.9819, "color": "#2f7f8f",
     "areas": "16 of the 17 official gradske četvrti", "reviewed": "17 September 2026"},
    {"key": "bucharest", "label": "Bucharest", "country": "Romania", "flag": "\U0001F1F7\U0001F1F4",
     "lat": 44.4268, "lon": 26.1025, "color": "#9c4f2f",
     "areas": "6 official sectoare", "reviewed": "17 September 2026"},
    {"key": "bratislava", "label": "Bratislava", "country": "Slovakia", "flag": "\U0001F1F8\U0001F1F0",
     "lat": 48.1486, "lon": 17.1077, "color": "#7a5fa8",
     "areas": "17 official mestské časti", "reviewed": "17 September 2026"},
    {"key": "vilnius", "label": "Vilnius", "country": "Lithuania", "flag": "\U0001F1F1\U0001F1F9",
     "lat": 54.6872, "lon": 25.2797, "color": "#c08a2f",
     "areas": "21 official seniūnijos", "reviewed": "17 September 2026"},
    {"key": "rotterdam", "label": "Rotterdam", "country": "Netherlands", "flag": "\U0001F1F3\U0001F1F1",
     "lat": 51.9225, "lon": 4.4777, "color": "#2f6f8f",
     "areas": "21 official CBS wijken", "reviewed": "17 September 2026"},
    {"key": "utrecht", "label": "Utrecht", "country": "Netherlands", "flag": "\U0001F1F3\U0001F1F1",
     "lat": 52.0907, "lon": 5.1214, "color": "#a8453a",
     "areas": "10 official CBS wijken", "reviewed": "17 September 2026"},
    {"key": "denhaag", "label": "The Hague", "country": "Netherlands", "flag": "\U0001F1F3\U0001F1F1",
     "lat": 52.0705, "lon": 4.3007, "color": "#3f7f5c",
     "areas": "44 official CBS wijken", "reviewed": "17 September 2026"},
    {"key": "antwerp", "label": "Antwerp", "country": "Belgium", "flag": "\U0001F1E7\U0001F1EA",
     "lat": 51.2194, "lon": 4.4025, "color": "#8f3f5c",
     "areas": "10 official districten", "reviewed": "18 September 2026"},
    {"key": "ghent", "label": "Ghent", "country": "Belgium", "flag": "\U0001F1E7\U0001F1EA",
     "lat": 51.0543, "lon": 3.7250, "color": "#4f7f3f",
     "areas": "14 official deelgemeenten", "reviewed": "18 September 2026"},
]


# ---------------------------------------------------------------------------
# Affiliate attribution. One programme is approved — Booking.com BENELUX, CJ
# advertiser 4347407 — so exactly the cities inside that programme's territory
# get an attributed link and every other city keeps the plain Booking URL it
# has always had.
#
# This table is the whole permission model. Sending Rome's traffic through a
# BENELUX link would attribute it to a programme that does not cover Italy:
# wrong at best and a terms breach at worst, and it would not pay. The link
# ids are not guessable and are not guessed — the format below was generated
# by CJ's own link builder for a real Booking search URL, not inferred from
# the shape of other affiliate networks.
CJ_PID = "101862727"                      # the Wandroz site's publisher id
BOOKING_PROGRAMMES = {
    # programme -> the city keys its territory covers on this site
    "benelux": {"link_id": "15734897", "cities": ("amsterdam", "brussels", "rotterdam", "utrecht", "denhaag",
                                                "antwerp", "ghent")},
}
# CJ rotates equivalent tracking hosts; any of them is valid.
CJ_HOST = "https://www.jdoqocy.com"


def booking_affiliate_prefix(city_key):
    """The click-tracking prefix for this city, or None if no approved programme."""
    for prog in BOOKING_PROGRAMMES.values():
        if city_key in prog["cities"]:
            return "%s/click-%s-%s?url=" % (CJ_HOST, CJ_PID, prog["link_id"])
    return None


def booking_href(query, city_key):
    """The Booking link for one area: attributed where a programme covers it."""
    plain = "https://www.booking.com/searchresults.html?ss=%s" % urllib.parse.quote_plus(query)
    prefix = booking_affiliate_prefix(city_key)
    # The destination rides inside a query parameter, so its own separators are
    # encoded again — ss=A%2C+B becomes ss%3DA%252C%2BB. Encoding it once
    # produces a link CJ accepts and Booking then receives truncated at the
    # first &, which is the kind of thing that looks fine and silently loses
    # the search.
    return (prefix + urllib.parse.quote(plain, safe="")) if prefix else plain


# ---------------------------------------------------------------------------
# City hub: recommendations and a comparison table.
#
# The hub pages were titled "Is my <city> neighbourhood safe?", which is not a
# phrase anyone types. A SERP check found the area pages losing "is X safe" to
# Reddit and Tripadvisor — Google answers that question with people, not
# statistics — while "where to stay in <city>" is won by content sites. So the
# hub stops being a map with a list underneath and becomes an answer.
#
# Everything below is computed from data already in the repo. A sight is placed
# in an area by testing its coordinates against that area's polygon, which is
# the same ray-crossing test the boundary checker uses; nothing is hand-written
# per city, and no adjective appears that is not derived from a count.

def _in_rings(lat, lon, rings):
    n = 0
    for r in rings:
        for (y1, x1), (y2, x2) in zip(r, r[1:] + r[:1]):
            if (y1 > lat) != (y2 > lat):
                if x1 + (lat - y1) * (x2 - x1) / (y2 - y1) > lon:
                    n += 1
    return n % 2 == 1


TONE_ORDER = {"green": 0, "yellow": 1, "red": 2, "grey": 3}

# ---------------------------------------------------------------------------
# WHY A RECOMMENDED AREA CAN BE RATED RED
#
#   "For a first visit" picks the area holding the most of the city's sights.
#   In a European city that is the historic centre, and the historic centre is
#   also where recorded crime concentrates — so this site recommends, in 32 of
#   its 62 cities, an area it rates red. The owner's decision was to keep the
#   recommendation and explain the rating rather than hide either: "tenere il
#   centro e dire perche' e' rosso".
#
#   The line below the card is therefore computed, never written by hand, and
#   it explains what the rating is MADE OF. It must not argue that the area is
#   safe — the reader is given the composition and draws their own conclusion —
#   and it must not claim the denominator artefact where the data does not
#   support it.
#
# WHAT THE DATA ACTUALLY ALLOWS, checked city by city before writing a word
#   20 UK cities  data/counts_<key>.json holds per-ward, per-month counts by
#                 crime category, and <key>_boundaries.json holds the resident
#                 population the rate was divided by. Full sentence.
#   5 cities      Berlin, Brussels, Munich, Prague, Stockholm: no structured
#                 breakdown survives the build, but all five are official
#                 snapshots whose published rate is per registered resident
#                 (verified in each city's own text). Short sentence.
#   7 cities      Athens, Catania, Dublin, Edinburgh, Genoa, Kraków, Lisbon:
#                 research-based, no rate at all behind the rating. Nothing is
#                 printed. Silence is the honest output; a generic reassurance
#                 would be invented.
#   London        no borough carrying a card is rated red today, so no London
#                 case exists. If one appears, its rate is already corrected
#                 towards a workday population for 22 of 32 boroughs, and for
#                 those the resident-denominator half MUST NOT print — hence
#                 the workday_population_ratio check in uk_caution_note().
CRIME_CATEGORY_PLAIN = {
    "shoplifting": "shoplifting",
    "burglary": "burglary",
    "vehicle-crime": "vehicle crime",
    "bicycle-theft": "bicycle theft",
    "drugs": "drug offences",
    "violent-crime": "violence",
    "robbery": "robbery",
    "theft-from-the-person": "pickpocketing",
    "public-order": "public-order offences",
    "anti-social-behaviour": "anti-social behaviour",
}

# Imported rather than restated: if the scorer's idea of a daytime crime and
# this file's ever diverged, the sentence would name categories that did not
# drive the score it is explaining.
try:
    from score_london import DAY_CATEGORIES as _DAY_CATS, NIGHT_CATEGORIES as _NIGHT_CATS
except Exception:                                    # pragma: no cover
    _DAY_CATS, _NIGHT_CATS = set(), set()

# Official-snapshot cities whose published rate is per registered resident.
# Each one was read in its own zone text before being listed here.
RESIDENT_RATE_CITIES = {"berlin", "brussels", "munich", "praha", "stockholm"}

_uk_counts_cache = {}


def uk_ward_evidence(city_key):
    """{slug: {'day': [(category, n)...], 'night': [...], 'population': int}}
    for a data.police.uk city, or {} if this city is not one.

    Read from the counts file the fetcher already committed, so this needs no
    network and cannot drift from the numbers the pages were scored on."""
    if city_key in _uk_counts_cache:
        return _uk_counts_cache[city_key]
    out = {}
    counts_path = os.path.join(BASE_DIR, "..", "data", "counts_%s.json" % city_key)
    bounds_path = os.path.join(ZONES_DIR, "%s_boundaries.json" % city_key)
    if os.path.isfile(counts_path) and os.path.isfile(bounds_path):
        with open(counts_path) as f:
            counts = json.load(f).get("counts", {})
        with open(bounds_path) as f:
            pops = {z["slug"]: z.get("population") for z in json.load(f)["zones"]}
        for slug, months in counts.items():
            total = {}
            for per_month in months.values():
                for cat, n in per_month.items():
                    total[cat] = total.get(cat, 0) + n
            rank = sorted(total.items(), key=lambda kv: -kv[1])
            out[slug] = {
                "day": [(c, n) for c, n in rank if c in _DAY_CATS],
                "night": [(c, n) for c, n in rank if c in _NIGHT_CATS],
                "population": pops.get(slug),
            }
    _uk_counts_cache[city_key] = out
    return out


# Apertura della frase, in base a cosa la card sta consigliando. Il punto e'
# tenere separate le due dimensioni: l'etichetta dice a cosa serve la zona, il
# badge dice cosa dicono i dati, e questa riga spiega perche' possono coesistere.
# L'etichetta inglese della card e' la chiave interna: identifica QUALE card e'
# e non e' testo mostrato. Il testo mostrato arriva dal catalogo.
# Come sopra: l'etichetta inglese identifica la card, il testo viene dal catalogo.
CARD_LABEL_KEY = {
    "For a first visit": "card_first_visit",
    "With family": "card_family",
    "For going out": "card_going_out",
    "Best rated overall": "card_best",
}


_CAUTION_OPENER_KEY = {
    "For a first visit": "caution_open_first_visit",
    "With family": "caution_open_family",
    "For going out": "caution_open_going_out",
    "Best rated overall": "caution_open_best",
}


def caution_note(city_key, zone, labels=(), sights=0, resident_rate_ok=True, t=None):
    """Why a recommended area can carry a caution rating, for the cards.

    THE CONTRADICTION THIS EXISTS TO RESOLVE
        The cards pick an area for what it is useful for — most of the city's
        sights, a park and no nightlife, the evening venues. The rating comes
        from somewhere else entirely, and in a European city the two collide
        constantly: the historic centre holds the sights AND the recorded
        crime. 36 of the site's 156 recommendation cards carry a red rating.
        A reader saw "For a first visit" above "Higher caution advised" and
        nothing reconciling them.

    WHAT IT MUST NOT DO
        It must not argue the area is safe, and it must not blame tourist
        footfall unless the data we hold supports that reading. Three tiers,
        by what the evidence actually allows:

          UK cities      the crime-category split and the resident population
                         are both known, so the sentence can name them.
          snapshot       Berlin, Brussels, Munich, Prague, Stockholm publish a
                         rate per registered resident; that much can be said,
                         plus the sight count from our own map.
          everything     research-based cities have no rate at all behind the
          else           rating, so any denominator claim would be invented.
                         They get the neutral form: the recommendation stands
                         on location, the rating stands on the evidence, and
                         the reader is told to take care rather than reassured.
    """
    day_red = zone.get("day") == "red"
    night_red = zone.get("night") == "red"
    if not (day_red or night_red):
        return ""

    t = t or i18n.strings(i18n.DEFAULT_LANG)
    opener = t[_CAUTION_OPENER_KEY.get(labels[0] if labels else "", "caution_open_generic")]
    closer = t["caution_closer"]

    ev = uk_ward_evidence(city_key).get(zone.get("slug"))
    if ev:
        def top(kind):
            items = ev[kind]
            return t.get("cat_" + items[0][0], items[0][0]) if items else None
        d = top("day") if day_red else None
        n = top("night") if night_red else None
        if d and n:
            core = t["caution_core_both"] % {"day": d, "night": n}
        elif d:
            core = t["caution_core_day"] % {"day": d}
        elif n:
            core = t["caution_core_night"] % {"night": n}
        else:
            core = None
        if core:
            pop = ev.get("population")
            if pop and resident_rate_ok:
                core += t["caution_denominator"] % {"pop": f"{pop:,}"}
            return "%s: %s. %s" % (opener, core, closer)

    if city_key in RESIDENT_RATE_CITIES:
        where = (t["caution_sights_here"] % {"n": sights}) if sights >= 3 else ""
        return t["caution_snapshot"] % {"open": opener, "where": where, "closer": closer}

    # Nessun tasso dietro la valutazione: nessuna affermazione sul denominatore.
    return t["caution_neutral"] % {"open": opener}


SIGHT_CATS = ("art", "square", "view", "food")


def hub_data(city_key, zones, t=None):
    """Per-area sight counts, plus the recommendation cards.

    `t` is the string catalogue; omitted it means English, and the English
    output is unchanged byte for byte."""
    t = t or i18n.strings(i18n.DEFAULT_LANG)
    pois = load_pois(city_key) or []
    counts = {z["slug"]: {"sights": 0, "night": 0, "green": 0} for z in zones}
    for p in pois:
        # load_pois() normalises the raw file's "category" to "cat"; reading
        # the raw name here silently matched nothing and produced a hub with a
        # single card picked by alphabet.
        lat, lon, cat = p.get("lat"), p.get("lon"), p.get("cat")
        if lat is None or lon is None:
            continue
        for z in zones:
            if _in_rings(lat, lon, z["coords"]):
                c = counts[z["slug"]]
                if cat in SIGHT_CATS:
                    c["sights"] += 1
                elif cat == "night":
                    c["night"] += 1
                elif cat == "green":
                    c["green"] += 1
                break

    def rank(z):
        # Ties on tone are the normal case — most areas of a calm city are
        # green/green — so the tie-break is how much of the city's sightseeing
        # is inside. Without it "best rated overall" returns whichever green
        # area sorts first alphabetically, which in Amsterdam was a polder on
        # the eastern boundary.
        c = counts.get(z["slug"], {})
        return (TONE_ORDER.get(z["day"], 3) + TONE_ORDER.get(z["night"], 3),
                TONE_ORDER.get(z["night"], 3),
                -(c.get("sights", 0) + c.get("night", 0) + c.get("green", 0)),
                z["name"])

    cards, used = [], {}

    def add(label, zone, why):
        if zone is None:
            return
        if zone["slug"] in used:          # one area, both labels, not two cards
            used[zone["slug"]]["labels"].append(label)
            return
        c = {"labels": [label], "zone": zone, "why": why,
             "counts": counts[zone["slug"]]}
        used[zone["slug"]] = c
        cards.append(c)

    with_sights = [z for z in zones if counts[z["slug"]]["sights"] > 0]
    if with_sights:
        top = max(counts[z["slug"]]["sights"] for z in with_sights)
        pool = [z for z in with_sights if counts[z["slug"]]["sights"] >= max(1, top - 1)]
        best = sorted(pool, key=rank)[0]
        # LE FRASI DELLE CARD
        #   Dicevano come funziona il criterio di scelta ("N of the sights on
        #   this map are inside it", "no nightlife pin"): sembrava output di
        #   debug e, peggio, regalava a chiunque legga il modo in cui il sito
        #   decide. Il criterio resta identico e resta calcolato; la frase dice
        #   al viaggiatore perche' gli conviene stare li'. I due badge sulla
        #   card portano gia' le valutazioni, quindi non serve ripeterle.
        n = counts[best["slug"]]["sights"]
        add("For a first visit", best,
            (t["why_first_visit"] % {"n": n}) if n > 1 else t["why_first_visit_one"])

    family = [z for z in zones
              if counts[z["slug"]]["green"] > 0 and counts[z["slug"]]["night"] == 0]
    if family:
        best = sorted(family, key=rank)[0]
        g = counts[best["slug"]]["green"]
        add("With family", best,
            t["why_family_one"] if g == 1 else (t["why_family"] % {"n": g}))

    # Only offered where the night rating supports it. A city whose nightlife
    # sits in areas rated red gets no card at all, which is the honest output.
    night = [z for z in zones
             if counts[z["slug"]]["night"] > 0 and z["night"] in ("green", "yellow")]
    if night:
        best = max(night, key=lambda z: (counts[z["slug"]]["night"], -TONE_ORDER.get(z["night"], 3)))
        add("For going out", best, t["why_going_out"])

    if zones:
        add("Best rated overall", sorted(zones, key=rank)[0], t["why_best"])

    # ORDINE DELLA TABELLA: per contrasto, non per valutazione.
    #
    #   Ordinare per valutazione sembra ovvio e nasconde sistematicamente
    #   l'informazione. A Zurigo 27 aree su 34 sono verde/verde, ad Amsterdam
    #   92 su 110: in quasi ogni citta' la maggioranza condivide un giudizio,
    #   quindi l'ordine per valutazione produce una colonna di righe identiche
    #   e spinge in fondo l'unica area che si discosta — che e' esattamente
    #   quella per cui si guarda una tabella.
    #
    #   Qui la chiave primaria e' quanto e' rara la combinazione giorno/notte
    #   di quell'area nella citta': prima le rare, poi le comuni. A parita' di
    #   rarita' vengono prima le piu' severe, poi quelle con piu' cose intorno.
    #   Le intestazioni restano ordinabili, quindi chi vuole l'ordine per
    #   valutazione ce l'ha in un click: quello che cambia e' cosa si vede
    #   senza chiedere niente.
    #   Ordinare per sola rarita' non basta, e si vede su Amsterdam: le 7 aree
    #   giallo/giallo sono piu' rare delle 11 rosse e finivano sopra di esse.
    #   Fra due aree che si discostano entrambe dalla norma, quella che il
    #   lettore deve vedere prima e' la piu' severa. Quindi: prima tutto cio'
    #   che non e' il giudizio modale della citta', ordinato per severita'; poi
    #   il blocco modale. La rarita' resta come spareggio.
    #
    #   "grey" vale zero in questa scala e non due: grigio vuol dire non
    #   valutata, non pericolosa, e farla salire in cima sarebbe una sciocchezza
    #   travestita da prudenza.
    severity = {"green": 0, "yellow": 1, "red": 2, "grey": 0}
    pair_freq = {}
    for z in zones:
        pair_freq[(z["day"], z["night"])] = pair_freq.get((z["day"], z["night"]), 0) + 1
    modal_pair = max(pair_freq, key=lambda k: (pair_freq[k], -severity[k[0]] - severity[k[1]]))

    def contrast(z):
        c = counts.get(z["slug"], {})
        pair = (z["day"], z["night"])
        return (1 if pair == modal_pair else 0,
                -(severity[z["day"]] + severity[z["night"]]),
                pair_freq[pair],
                -(c.get("sights", 0) + c.get("night", 0) + c.get("green", 0)),
                z["name"])

    rows = []
    for z in sorted(zones, key=contrast):
        rows.append({"name": z["name"], "slug": z["slug"], "day": z["day"], "night": z["night"],
                     "evidence": z.get("evidence", "documented"),
                     "sights": counts[z["slug"]]["sights"] + counts[z["slug"]]["night"]
                               + counts[z["slug"]]["green"]})

    # Una colonna che dice la stessa cosa su ogni riga non e' una colonna, e'
    # rumore incolonnato: a Zurigo "Evidence" diceva "sourced" trentaquattro
    # volte. Si stampa solo dove distingue almeno due aree.
    #
    #   Su "Sights" mi fermo un passo prima di quanto chiesto, e lo dico:
    #   l'istruzione era di togliere anche le colonne quasi tutte a zero (a
    #   Zurigo 29 righe su 34). Ma quei 5 valori non nulli sono precisamente
    #   l'informazione che un viaggiatore cerca, e toglierli per far pulizia
    #   significherebbe nascondere il dato invece del rumore. Gli zeri diventano
    #   celle vuote — sparisce il muro di "0", restano i cinque numeri — e la
    #   colonna cade solo quando e' davvero tutta a zero.
    show_evidence = len({r["evidence"] for r in rows}) > 1
    show_sights = any(r["sights"] for r in rows)
    return {"cards": cards, "rows": rows,
            "show_evidence": show_evidence, "show_sights": show_sights}


LOCAL_TERM_RE = re.compile(
    r"\b(\d+\s+(?:of the \d+\s+)?official\s+)?"
    r"(boroughs?|wards?|quartieri|circoscrizioni|municipi|rioni|municipalit\u00e0|"
    r"gradske\s+\u010detvrti|dzielnice|linnaosad|seniu\u016bnijos|seni\u016bnijos|sectoare|"
    r"mestsk\u00e9\s+\u010dasti|wijken|districten|deelgemeenten|kerletek|ker\u00fcletek|"
    r"distritos|barris|arrondissements|bezirke|stadsdelen|quarters?|districts?|"
    r"neighbourhoods?)\b", re.I)


def hub_headline(label, areas_phrase, n):
    # "Bologna, Italy" is the dataset label; the query is "where to stay in
    # Bologna". The country belongs in the breadcrumb, not in a title someone
    # is meant to recognise as their search.
    label = label.split(",")[0].strip()
    """Title, H1 and one-line answer for a city hub.

    The old title was "Is my <city> neighbourhood safe?", which nobody types.
    The title has to carry the words people search — "where to stay", and
    "neighbourhoods" or "boroughs" rather than the local term — while the
    subtitle keeps the local word, because that is what the map is labelled in.
    """
    m = LOCAL_TERM_RE.search(areas_phrase or "")
    local = (m.group(2) if m else "neighbourhoods").lower()
    unit = "boroughs" if local in ("boroughs", "borough") else "neighbourhoods"
    return {
        "title": "Where to stay in %s: safest %s compared | Wandroz" % (label, unit),
        "h1": "Where to stay in %s" % label,
        "local": local,
        "unit": unit,
    }


def research_city_ui(label, areas):
    ui = dict(TORINO_UI)
    ui.update({
        "page_title": "Is my %s neighbourhood safe? — Wandroz" % label,
        "page_description": ("Interactive map of %s's %s (real official administrative "
                             "boundaries) with day/night safety levels from a structured "
                             "local-source assessment." % (label, areas)),
        "page_h1": "%s neighbourhoods" % label,
        "neigh_title": "Is {name} in %s safe? | Wandroz" % label,
    })
    return ui


def research_city_card(c, zone_count):
    # La barra e non index.html: sono lo stesso file ma due URL, e il canonical
    # della pagina e' la forma con la barra. Linkare l'altra fa scoprire a
    # Google un duplicato per ogni citta', che poi archivia come "pagina
    # alternativa con tag canonical appropriato" invece di indicizzarla.
    return {
        "name": c["label"], "url": "%s/" % c["key"], "flag": c["flag"],
        "blurb": ("All %s mapped, real administrative boundaries, safety ratings from a "
                  "structured local-source assessment, area by area." % c["areas"]),
        "lat": c["lat"], "lon": c["lon"], "color": c["color"],
        "zone_count": zone_count, "data_tag": "Official boundaries",
    }



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
    "Poland": "🇵🇱", "Estonia": "🇪🇪", "Finland": "🇫🇮",
    "Denmark": "🇩🇰", "Romania": "🇷🇴", "Bulgaria": "🇧🇬",
    "Croatia": "🇭🇷", "Slovenia": "🇸🇮", "Slovakia": "🇸🇰",
    "Latvia": "🇱🇻", "Lithuania": "🇱🇹", "Serbia": "🇷🇸",
}
CITY_COUNTRY = {
    "London": "United Kingdom", "Berlin": "Germany", "Amsterdam": "Netherlands",
    "Turin": "Italy", "Zurich": "Switzerland", "Milan": "Italy", "Rome": "Italy",
    "Prague": "Czechia", "Oslo": "Norway", "Munich": "Germany", "Stockholm": "Sweden",
    "Barcelona": "Spain", "Madrid": "Spain", "Vienna": "Austria", "Lisbon": "Portugal",
    "Paris": "France", "Brussels": "Belgium", "Athens": "Greece", "Venice": "Italy",
    "Dublin": "Ireland", "Florence": "Italy", "Edinburgh": "United Kingdom",
    "Naples": "Italy", "Budapest": "Hungary", "Kraków": "Poland",
}

# Curated "Popular destinations" shortcut shown near the homepage search box
# — major traveller destinations rather than whichever cities happened to
# launch first. Deliberately a short, explicit, single list (not derived
# from zone count or launch order, which don't track traveller popularity)
# so it's obvious where to edit it; group_cities_by_country() below still
# pulls the actual card data (url, flag, counts) from city_cards/CITY_LINKS
# rather than this list duplicating it.
POPULAR_CITY_NAMES = ["London", "Paris", "Rome", "Barcelona", "Amsterdam", "Berlin"]


def country_codes_covered():
    """The ISO 3166-1 alpha-2 codes of every country Wandroz covers, for the
    homepage's address geocoder.

    Derived from the flag emoji, which ARE those codes: a flag is two regional
    indicator symbols, and 🇳🇱 is literally 'n' + 'l'. So this needs no new
    table to maintain — the list widens by itself the moment a city in a new
    country is added, which is the whole point.

    It used to be the literal string "gb,ch,it,de", written when those were the
    only four countries on the site. It stayed there while the site grew to
    22, so an address in Amsterdam, Prague, Barcelona, Lisbon, Warsaw or Oslo
    was never even geocoded: the search answered "we don't cover that" for two
    thirds of the cities it does cover.
    """
    codes = set()
    for country in set(CITY_COUNTRY.values()):
        flag = COUNTRY_FLAGS.get(country)
        if not flag:
            raise ValueError(
                "%r has cities but no COUNTRY_FLAGS entry — the address search "
                "derives its country list from the flags, so a missing one "
                "silently makes that country unsearchable." % country
            )
        pts = [ord(c) for c in flag if 0x1F1E6 <= ord(c) <= 0x1F1FF]
        if len(pts) != 2:
            raise ValueError("COUNTRY_FLAGS[%r] is not a two-letter flag" % country)
        codes.add("".join(chr(c - 0x1F1E6 + ord("a")) for c in pts))
    return ",".join(sorted(codes))


_TRANSLATION_CACHE = {}


def translated_text(lang, city_key, text):
    """The Italian (or other) version of one area's reasoning, or "" if it was
    never translated.

    Read from data_i18n/<lang>/<city>.json, which translate.py wrote once and
    committed. Keyed by a hash of the English source, so an area whose
    reasoning was rewritten after the translation run comes back empty rather
    than returning a translation of text that no longer exists — which is the
    failure mode worth designing against: a stale translation of a safety
    claim looks exactly like a current one."""
    if lang == i18n.DEFAULT_LANG or not text:
        return ""
    key = (lang, city_key)
    if key not in _TRANSLATION_CACHE:
        path = os.path.join(BASE_DIR, "data_i18n", lang, "%s.json" % city_key)
        try:
            with open(path, encoding="utf-8") as f:
                _TRANSLATION_CACHE[key] = json.load(f)
        except Exception:
            _TRANSLATION_CACHE[key] = {}
    h = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]
    return _TRANSLATION_CACHE[key].get(h, "")


def city_country_code(city_label):
    """ISO 3166-1 alpha-2 for a city's country, from the flag emoji — the same
    derivation the address geocoder uses, for the same reason: the flag IS the
    code, so there is no second table to keep in step. Returns "" for a city
    with no country entry rather than raising, because a missing language is a
    page that does not exist, not a build that should die."""
    country = CITY_COUNTRY.get(city_only(city_label))
    flag = COUNTRY_FLAGS.get(country or "")
    if not flag:
        return ""
    pts = [ord(c) for c in flag if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    if len(pts) != 2:
        return ""
    return "".join(chr(c - 0x1F1E6 + ord("a")) for c in pts)


def countries_covered():
    """Counted from the same CITY_COUNTRY map the homepage groups by, so the
    methodology page cannot claim a country count the switcher disagrees with.

    A function and not a constant, and the difference is not cosmetic: the UK
    and research-city loops add to CITY_COUNTRY further down this file, so a
    module-level constant here captured 17 countries instead of 22. The same
    ordering bug once dropped four cities from the country switcher without a
    word."""
    return sorted(set(CITY_COUNTRY.values()))


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

# Ordering for the public source table: strongest evidence first, so a reader
# scanning it meets the official-data cities before the limited-data ones.
TIER_ORDER = {OFFICIAL_SNAPSHOT: 0, RESEARCH_BASED: 1, MANUAL_EXPERIMENTAL: 2}

CITY_METHODOLOGY = {
    "berlin": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Polizei Berlin's official Häufigkeitszahl crime statistic (Kriminalitätsatlas Berlin)", "source_url": "https://www.kriminalitaetsatlas.berlin.de/"},
    "amsterdam": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "CBS (Statistics Netherlands)'s official registered-crime statistics", "source_url": "https://dataderden.cbs.nl/ODataApi/odata/47018NED"},
    "praha": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Policie ČR's official crime statistics (kriminalita.policie.gov.cz)", "source_url": "https://kriminalita.policie.gov.cz/"},
    "oslo": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Oslo kommune's official Statistikkbanken crime statistics", "source_url": "https://statistikkbanken.oslo.kommune.no/"},
    "munich": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Polizeipräsidium München's official recorded-offence statistics", "source_url": "https://stadt.muenchen.de/dam/jcr:6291ac42-463d-4267-b436-c4b1a3313454/jt160904.pdf"},
    "stockholm": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "Brå (Brottsförebyggande rådet)'s official crime statistics", "source_url": "https://statistik.bra.se/solwebb/action/index"},
    "brussels": {"tier": OFFICIAL_SNAPSHOT, "crime_source": "BISA / Federale Politie's official crime statistics", "source_url": "https://bisa.brussels/"},
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
    "dublin": "5 September 2026", "edinburgh": "10 September 2026", "napoli": "11 September 2026",
    "budapest": "11 September 2026", "krakow": "11 September 2026", "firenze": "13 September 2026",
}

CITY_LABEL_FOR_KEY = {
    "milano": "Milan", "roma": "Rome", "barcelona": "Barcelona", "madrid": "Madrid",
    "vienna": "Vienna", "lisbon": "Lisbon", "paris": "Paris", "athens": "Athens",
    "venezia": "Venice", "dublin": "Dublin", "napoli": "Naples", "budapest": "Budapest",
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
        zones = load_zone_file(path)["zones"]
        areas += len(zones)
        no_findings += sum(1 for z in zones if z.get("evidence") == "no_findings")
    rows = []
    for key in per_tier[RESEARCH_BASED]:
        path = os.path.join(ZONES_DIR, f"{key}.json")
        if not os.path.isfile(path):
            continue
        zones = load_zone_file(path)["zones"]
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


# The geography unit and the reference period a city's own pages state. Read
# back out of the zone text the builders generate, with a fixed shape:
#   "X is one of Berlin's 143 official Bezirksregionen, part of ..."
#   "CBS ... recorded ... in 2025 ..."
# Reading our own generated sentence is not elegant, but the alternative is a
# second hand-maintained table of 62 rows, which is precisely the thing that
# drifts — and drift is what put three different city counts on three
# different pages. Where the shape does not match, the cell says so instead of
# guessing.
_GEO_RE = re.compile(r"one of (?:the )?[^.]{0,40}?(\d+)\s+official\s+([A-Za-zÀ-ž' ]+?)(?:\s*\(|,|\.)")
_YEAR_RE = re.compile(r"\b(20[12]\d)\b")


def city_source_facts(city_key, zones):
    """(geography, period) as the city's own area pages state them, or "—"."""
    blob = " ".join((z.get("text") or "") for z in zones[:4])
    geo = _GEO_RE.search(blob)
    years = sorted(set(_YEAR_RE.findall(blob)))
    return (geo.group(2).strip() if geo else "—",
            years[-1] if years else "—")


# Filled in as each city is rendered, then read by the methodology page, which
# is written afterwards. The point is that the methodology table cannot claim a
# coverage, a source or a count that the city pages do not actually have: it is
# a record of what was built, not a parallel description of it.
CITY_FACTS = []


def record_city_facts(url_slug, label, city_key, zones, source=None, period=None,
                      tier=None, geography=None, source_url=None):
    tier = tier or (CITY_METHODOLOGY.get(city_key) or {}).get("tier", RESEARCH_BASED)
    geo, derived_period = city_source_facts(city_key, zones)
    geo = geography or geo
    CITY_FACTS.append({
        "slug": url_slug,
        "label": city_only(label),
        "tier": tier,
        "areas": len(zones),
        "geography": geo,
        "period": period or derived_period,
        "source": source or EVIDENCE_SOURCE.get(city_key) or "",
        # Pubblicato solo se l'URL e' stato verificato: una fonte nominata e non
        # cliccabile e' un limite, una fonte cliccabile che porta a un 404 e'
        # una bugia sulla verificabilita', che e' il contrario del punto.
        "source_url": source_url or (CITY_METHODOLOGY.get(city_key) or {}).get("source_url", ""),
        "reviewed": REVIEW_DATE.get(city_key, ""),
        "no_findings": sum(1 for z in zones if z.get("evidence") == "no_findings"),
    })


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
        "source_url": "https://data.police.uk/",
    }
    EVIDENCE_SOURCE[_c["key"]] = "%s, data.police.uk" % _c["force"]

# London is not in CITY_METHODOLOGY — it has its own automated pipeline built
# directly on data.police.uk, which is the strongest source on the site, so it
# carries the official-data label on its own terms rather than by inheritance.
LONDON_EVIDENCE_TAG = "🟢 Official crime data"

# Stesso posto e stesso motivo del ciclo qui sopra: i dizionari che riempie
# esistono solo da qui in giu'.
for _c in RESEARCH_CITIES:
    CITY_METHODOLOGY.setdefault(_c["key"], {"tier": RESEARCH_BASED})
    REVIEW_DATE.setdefault(_c["key"], _c["reviewed"])
    CITY_LABEL_FOR_KEY.setdefault(_c["key"], _c["label"])
    CITY_COUNTRY.setdefault(_c["label"], _c["country"])
    if all(l["label"] != _c["label"] for l in CITY_LINKS):
        CITY_LINKS.append({"label": _c["label"], "url": f"{SITE_URL}/{_c['key']}/"})
    if all(e[0] != _c["key"] for e in ILLUSTRATIVE_CITIES):
        ILLUSTRATIVE_CITIES.append((_c["key"], _c["key"], _c["label"], True))

# CITY_LINKS_BY_COUNTRY viene derivato piu' in alto, prima che questo ciclo
# esista, quindi va rifatto: senza, le citta' aggiunte dalla tabella finiscono
# in CITY_LINKS ma non nel selettore raggruppato per paese — cioe' spariscono
# dal menu di ogni pagina senza rompere niente e senza dirlo.
CITY_LINKS_BY_COUNTRY = group_cities_by_country(CITY_LINKS, name_key="label")



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


# A fourth case, found by the QA gate rather than by reading the data: several
# zones can be marked scope "area" and still resolve to the SAME Booking search.
# Five Florence zones all point at "Rifredi, Florence, Italy"; Acilia nord and
# sud share one destination, as do Ostia nord and sud, and S. Ambrogio with
# S. Croce. Four of those five Florence pages were promising a link "already
# scoped to this area", which for them was not true.
#
# The destination itself is left alone: changing which string Booking resolves
# needs a live check against Booking, not a guess from here. What is corrected
# is the claim, which costs nothing to get right.
BOOKING_SHARED_SCOPE_NOTE = (
    "Booking.com indexes this neighbourhood together with its neighbours under a "
    "single search area, so this link covers that whole area rather than this "
    "neighbourhood alone."
)


def booking_note(ui, scope):
    if scope == "city":
        return BOOKING_CITY_SCOPE_NOTE
    if scope == "parent":
        return BOOKING_PARENT_SCOPE_NOTE
    if scope == "shared":
        return BOOKING_SHARED_SCOPE_NOTE
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


def load_pois(city_key, t=None):
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
            "cat": p["category"], "cat_label": (t or {}).get("poi_" + p["category"]) or POI_CATEGORY_LABEL[p["category"]],
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
    data = load_zone_file(path)
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
def tone_descriptor(tone, city_label, t=None):
    t = t or i18n.strings(i18n.DEFAULT_LANG)
    phrase = t.get("desc_" + tone)
    if not phrase:
        return tone
    return phrase % {"city": city_label} if "%(city)s" in phrase else phrase


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
                            crime_source=None, has_time_of_day=True, t=None):
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
    t = t or i18n.strings(i18n.DEFAULT_LANG)
    name = zone["name"]
    city_label = city_only(city_label)
    day_desc = tone_descriptor(zone["day"], city_label, t)
    night_desc = tone_descriptor(zone["night"], city_label, t)
    q = lambda key: t[key] % {"name": name}

    if tier == OFFICIAL_SNAPSHOT:
        basis = t["basis_official"] % {"source": crime_source or t["source_generic"]}
    elif tier == RESEARCH_BASED:
        basis = t["basis_research"] % {"city": city_label}
    else:
        basis = t["basis_limited"] % {"city": city_label}

    # Where the area-level review reached nothing specific, the rating still
    # stands — every area on a city map carries one — but the answer says what
    # it rests on. A green earned by an empty search is not the same claim as a
    # green earned by sources, and a visitor is entitled to know which they are
    # reading.
    if zone.get("evidence") == "no_findings":
        return [
            {"q": q("faq_q_safe"),
             "a": t["faq_a_nofind_safe"] % {"name": name, "city": city_label, "day": day_desc}},
            {"q": q("faq_q_checked"),
             "a": t["faq_a_nofind_checked"] % {"name": name, "city": city_label}},
            {"q": q("faq_q_tourist"),
             "a": t["faq_a_nofind_tourist"] % {"city": city_label}},
        ]

    if has_time_of_day:
        # Su 2.330 aree su 2.902 — l'ottanta per cento — giorno e notte hanno lo
        # stesso giudizio, e la frase ripeteva per intero la stessa perifrasi di
        # quattordici parole due volte. Quarantuno parole per dire una cosa
        # sola, ed e' la frase che Google mostra come risposta alla domanda
        # "is X safe?". Quando i due giudizi coincidono lo si dice una volta.
        key = "faq_a_rating_same" if day_desc == night_desc else "faq_a_rating_diff"
        rating_sentence = t[key] % {"name": name, "city": city_label,
                                    "day": day_desc, "night": night_desc, "basis": basis}
        night_faq = {"q": q("faq_q_night"),
                     "a": t["faq_a_night"] % {"name": name, "night": night_desc}}
    else:
        rating_sentence = t["faq_a_rating_notime"] % {"name": name, "city": city_label,
                                                      "day": day_desc, "basis": basis}
        night_faq = {"q": q("faq_q_daynight"),
                     "a": t["faq_a_daynight"] % {"name": name, "day": day_desc}}

    faqs = [
        {"q": q("faq_q_safe"), "a": rating_sentence},
        night_faq,
        {"q": q("faq_q_tourist"),
         "a": t["faq_a_tourist"] % {"name": name, "day": day_desc}},
    ]
    if burglary:
        # Zurigo soltanto, e Zurigo oggi esiste solo in inglese: questa
        # diramazione resta nella lingua di partenza finche' il tedesco non e'
        # una lingua dichiarata.
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
        faqs.append({"q": q("faq_q_official"),
                     "a": t["faq_a_official_yes"] % {"name": name,
                                                     "source": crime_source or t["source_generic"]}})
    elif tier == RESEARCH_BASED:
        faqs.append({"q": q("faq_q_official"),
                     "a": t["faq_a_official_research"] % {"name": name}})
    else:
        faqs.append({"q": q("faq_q_official"),
                     "a": t["faq_a_official_none"] % {"name": name}})
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
    data = load_zone_file(path)
    zones = data["zones"]

    # Quante zone puntano alla stessa ricerca Booking. Contato qui, dai dati
    # della citta', invece che dichiarato per zona: cosi' non puo' divergere da
    # cio' che i link fanno davvero, ed e' la stessa cosa che il gate QA misura
    # quando segnala "shared-destination".
    _dest_count = {}
    for _z in zones:
        q = _z.get("query")
        if q:
            _dest_count[q] = _dest_count.get(q, 0) + 1

    def _scope_of(z):
        scope = z.get("booking_scope", "area")
        if scope == "area" and _dest_count.get(z.get("query"), 0) > 1:
            return "shared"
        return scope
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
    # LA STESSA PAGINA, UNA VOLTA PER LINGUA
    #
    #   L'inglese resta dov'e' e com'e': /plymouth/, stessi byte di prima.
    #   Spostarlo sotto /en/ butterebbe via ogni URL che Google ha indicizzato
    #   in cambio di niente. Le altre lingue nascono accanto, sotto il loro
    #   prefisso, e hreflang dice a Google che sono la stessa pagina.
    #
    #   hub_data() viene ricalcolato per lingua perche' le frasi delle card e
    #   la spiegazione delle zone rosse sono costruite li' dentro. Costa un
    #   secondo passaggio sui POI per citta' per lingua; il build resta sotto i
    #   venti secondi e in cambio non esiste un solo pezzo di testo che sia
    #   inglese per sbaglio.
    _langs = [i18n.DEFAULT_LANG] + i18n.languages_for_country_code(
        city_country_code(data["label"]))
    _alts = [(lg, SITE_URL + i18n.url_for(lg, "%s/" % url_slug)) for lg in _langs]

    for _lang in _langs:
        _t = i18n.strings(_lang)
        _is_en = _lang == i18n.DEFAULT_LANG
        _city_only = i18n.place(_lang, city_only(data["label"]))
        _label = i18n.local_label(_lang, data["label"])
        _hubdata = hub_data(city_key, zones, _t)
        _tone = tone_badge if _is_en else {
            "green": _t["tone_green"], "yellow": _t["tone_yellow"],
            "red": _t["tone_red"], "grey": _t["tone_grey"],
        }
        # Le pagine delle singole aree non sono ancora tradotte — sono i 177.000
        # parole di ragionamento che aspettano il servizio di traduzione — quindi
        # da una hub tradotta i link puntano alla versione inglese, che esiste.
        # Mandare un lettore italiano su una pagina inglese e' un limite; mandarlo
        # su un 404 sarebbe un difetto.
        def _area_url(slug):
            return f"/{url_slug}/{slug}.html" if flat else f"/{url_slug}/{slug}/"

        for _r in _hubdata["rows"]:
            _r["url"] = _area_url(_r["slug"])
            _r["day_label"] = _tone.get(_r["day"], _r["day"])
            _r["night_label"] = _tone.get(_r["night"], _r["night"])
            _r["book"] = booking_href(next((z["query"] for z in zones
                                            if z["slug"] == _r["slug"]), ""), city_key)
        # Due card rosse sulla stessa pagina possono ricevere la stessa frase — la
        # forma breve, che non nomina l'area, e' identica per costruzione. Stamparla
        # due volte non aggiunge niente e sembra un modello incollato.
        _notes_seen = set()
        for _c in _hubdata["cards"]:
            _z = _c["zone"]
            _c["url"] = _area_url(_z["slug"])
            _c["day_label"] = _tone.get(_z["day"], _z["day"])
            _c["night_label"] = _tone.get(_z["night"], _z["night"])
            _c["book"] = booking_href(_z["query"], city_key)
            _c["label_text"] = " · ".join(_t.get(CARD_LABEL_KEY[l], l) for l in _c["labels"])
            _note = caution_note(city_key, _z, _c["labels"], _c["counts"]["sights"], t=_t)
            _c["caution"] = "" if _note in _notes_seen else _note
            if _note:
                _notes_seen.add(_note)
        _hub = hub_headline(data["label"], ui.get("page_description", ""), len(zones))
        _dir = city_dir if _is_en else os.path.join(OUT_DIR, _lang, url_slug)
        os.makedirs(_dir, exist_ok=True)
        _canonical = SITE_URL + i18n.url_for(_lang, "%s/" % url_slug)

        html = map_tpl.render(
            lang=_lang, alternates=_alts, languages=i18n.LANGUAGES,
            t=_t,
            city_label=_label, tagline=_t["tagline"],
            place=(lambda nm, _l=_lang: i18n.place(_l, nm)),
            current_city_url=SITE_URL + "/%s/" % url_slug,
            nav_home=_t["nav_home"], nav_methodology=_t["nav_methodology"],
            page_title=(_hub.get("title") or ui["page_title"]) if _is_en
                       else _t["hub_title"] % {"city": _city_only},
            page_description=ui["page_description"] if _is_en
                             else _t["hub_description"] % {"city": _city_only},
            canonical_url=_canonical,
            city_links=CITY_LINKS, city_country_links=CITY_LINKS_BY_COUNTRY,
            page_h1=(_hub.get("h1") or ui["page_h1"]) if _is_en
                    else _t["hub_h1"] % {"city": _city_only},
            # Deliberately "area" and not the local word: the singular of wijken,
            # quartieri or seniūnijos is not derivable by trimming an s, and
            # "Every wijken rated" is worse than the plain English. The local term
            # keeps the table heading, where the plural is the correct form anyway.
            page_lead=(_t["hub_lead"] if _hubdata["rows"] else ui["page_lead"]),
            hub=_hubdata, hub_unit=_hub.get("unit"),
            # Il termine locale — wijken, quartieri, seniunijos — resta com'e':
            # e' il nome che quella citta' da' alle sue aree, non una parola da
            # tradurre. Si traduce solo il generico "neighbourhoods", che e'
            # inglese perche' la descrizione da cui viene e' inglese.
            hub_local=(_t["unit_generic"] if _hub.get("local") == "neighbourhoods"
                       else _hub.get("local")),
            data_note=evidence_line(city_key, len(zones)) if _is_en else "",
            show_toggle=show_toggle,
            label_day=_t["label_day"], label_night=_t["label_night"],
            legend_green=_t["legend_green"],
            legend_yellow=legend_yellow if _is_en else _t["legend_yellow"],
            legend_red=_t["legend_red"], legend_grey=_t["legend_grey"],
            has_grey=any(z["day"] == "grey" or z["night"] == "grey" for z in zones),
            has_no_findings=any(z.get("evidence") == "no_findings" for z in zones),
            label_zone_detail=ui["label_zone_detail"], label_click_hint=_t["click_hint"],
            label_all_zones=_t["all_zones"], label_booking=_t["booking_cta"],
            booking_prefix=booking_affiliate_prefix(city_key),
            label_more=_t["see_full_page"], label_not_covered="",
            pois=load_pois(city_key, _t), poi_filter_all=_t["poi_all"],
            label_hide_sights=_t["hide_sights"], label_sights_hidden=_t["sights_hidden"],
            footer_note=_t["footer_note"],
            zones=js_zones, zone_groups=group_zones(zones, js_zones),
            center=data["center"], zoom=data["zoom"],
            show_burglary_toggle=bool(extra_zone_data),
        )
        with open(os.path.join(_dir, "index.html"), "w") as f:
            f.write(html)
        urls.append(_canonical)
    print(f"Wrote {os.path.join(city_dir, 'index.html')} ({len(zones)} zones"
          f"{', +' + ','.join(_langs[1:]) if len(_langs) > 1 else ''})")

    neigh_tpl = env.get_template("neighbourhood.html")
    # Le pagine delle aree, una volta per lingua. Stessa logica della hub:
    # l'inglese resta al suo URL, le altre lingue nascono sotto il prefisso, e
    # hreflang le lega. Il testo lungo arriva dalla cache di traduzione; dove
    # manca, la pagina mostra l'inglese e lo dice in una riga.
    for _lang in _langs:
        _t = i18n.strings(_lang)
        _is_en = _lang == i18n.DEFAULT_LANG
        _label = i18n.local_label(_lang, data["label"])
        _tone = tone_badge if _is_en else {
            "green": _t["tone_green"], "yellow": _t["tone_yellow"],
            "red": _t["tone_red"], "grey": _t["tone_grey"],
        }
        for z in zones:
            _rel = f"{url_slug}/{z['slug']}.html" if flat else f"{url_slug}/{z['slug']}/"
            _base = city_dir if _is_en else os.path.join(OUT_DIR, _lang, url_slug)
            if flat:
                os.makedirs(_base, exist_ok=True)
                out_path = os.path.join(_base, f"{z['slug']}.html")
            else:
                zdir = os.path.join(_base, z["slug"])
                os.makedirs(zdir, exist_ok=True)
                out_path = os.path.join(zdir, "index.html")
            z_canonical = SITE_URL + i18n.url_for(_lang, _rel)
            _z_alts = [(lg, SITE_URL + i18n.url_for(lg, _rel)) for lg in _langs]
            # Il ragionamento dell'area: tradotto se e' in cache, altrimenti resta
            # inglese e la pagina lo dichiara invece di far finta.
            _body_text = translated_text(_lang, city_key, z.get("text") or "") or (z.get("text") or "")
            _untranslated = (not _is_en) and not translated_text(_lang, city_key, z.get("text") or "")
            zone_ctx = dict(z)
            zone_ctx["text"] = _body_text
            zone_ctx["evidence_label"] = EVIDENCE_LABEL.get(z.get("evidence", "documented"), "")
            zone_ctx["evidence_note"] = EVIDENCE_NOTE if z.get("evidence") == "no_findings" else ""
            zone_ctx["day_label"] = _tone.get(z["day"], z["day"])
            zone_ctx["night_label"] = _tone.get(z["night"], z["night"])
            if extra_zone_data:
                zone_ctx["burglary"] = extra_zone_data.get(z["name"])
            faq_items = build_faq_illustrative(
                zone_ctx, data["label"], burglary=zone_ctx.get("burglary"),
                tier=tier, crime_source=crime_source, has_time_of_day=show_toggle, t=_t,
            )
            page = neigh_tpl.render(
                lang=_lang, t=_t, alternates=_z_alts, city_label=_label, tagline=_t["tagline"],
                nav_home=_t["nav_home"], canonical_url=z_canonical,
                # Era un "../" relativo. Da /bologna/x.html porta a /, che esiste;
                # da /it/bologna/x.html porta a /it/, che non esiste. Un link
                # relativo cambia significato quando la pagina cambia profondita'.
                city_hub_url=i18n.url_for(_lang, "%s/" % url_slug),
                page_title=(ui["neigh_title"].format(name=z["name"], city=data["label"])
                            if _is_en else _t["faq_q_safe"] % {"name": z["name"]} + " | Wandroz"),
                page_description=_body_text[:160],
                zone=zone_ctx, show_toggle=show_toggle,
                label_day=_t["label_day"], label_night=_t["label_night"],
                label_detail=ui["label_detail"], label_booking=_t["booking_cta"],
                booking_url=booking_href(z["query"], city_key),
                label_booking_note=booking_note(ui, _scope_of(z)),
                data_note=method_note(city_key, data["label"],
                                      no_findings=(z.get("evidence") == "no_findings")),
                footer_note=_t["footer_note"], correction_email=CORRECTION_EMAIL,
                evidence_tag=evidence_line(city_key, len(zones)),
                faq_items=faq_items, faq_schema=_faq_jsonld(faq_items),
                untranslated_notice=_t["untranslated_notice"] if _untranslated else "",
            )
            with open(out_path, "w") as f:
                f.write(page)
            urls.append(z_canonical)

    print(f"Wrote {len(zones)} neighbourhood pages under {city_dir}/")
    # La geografia la dice gia' la pagina della citta' ("All 34 neighbourhoods
    # compared"): la prendo da li' invece di dedurla dal testo delle zone, che
    # la nomina solo in 7 citta' su 62.
    record_city_facts(url_slug, data["label"], city_key, zones,
                      geography=_hub.get("local"))
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
    # hub_data works on zone dicts with a slug; London's map entries carry a
    # url instead, and the boroughs without one have no page to link to — the
    # City of London is policed separately and is not in the dataset. Only the
    # ones with a page go in the table.
    london_zones_for_hub = [
        dict(z, slug=z["url"].rsplit("/", 1)[-1].replace(".html", ""),
             evidence="documented")
        for z in js_zones if z.get("url")
    ]
    _london_hub = hub_data("london", london_zones_for_hub)
    for _r in _london_hub["rows"]:
        _r["url"] = "/london/%s.html" % _r["slug"]
        _r["day_label"] = EN_TONE_BADGE.get(_r["day"], _r["day"])
        _r["night_label"] = EN_TONE_BADGE.get(_r["night"], _r["night"])
        _r["book"] = booking_href(next((z["query"] for z in london_zones_for_hub
                                        if z["slug"] == _r["slug"]), ""), "london")
    for _c in _london_hub["cards"]:
        _z = _c["zone"]
        _c["url"] = "/london/%s.html" % _z["slug"]
        _c["day_label"] = EN_TONE_BADGE.get(_z["day"], _z["day"])
        _c["night_label"] = EN_TONE_BADGE.get(_z["night"], _z["night"])
        _c["book"] = booking_href(_z["query"], "london")
        # 22 of London's 32 boroughs have their rate corrected towards a workday
        # population, so for those the resident-denominator half of the sentence
        # would be false. It is suppressed per borough, not per city.
        _b = next((b for b in (london["boroughs"] if london else []) if b["slug"] == _z["slug"]), None)
        _c["caution"] = caution_note("london", _z, _c["labels"], _c["counts"]["sights"],
                                     resident_rate_ok=bool(_b) and
                                     (_b.get("workday_population_ratio") in (None, 1.0)))

    html = map_tpl.render(
        # Londra non ha ancora una seconda lingua: alternates vuoto significa
        # nessun hreflang e nessun selettore, che e' la cosa giusta per una
        # pagina che esiste in una versione sola.
        lang="en", t=i18n.strings("en"), alternates=[], current_city_url=None,
        place=(lambda nm: nm),
        city_label="London", tagline="Neighbourhood safety for travellers",
        nav_home="Home", nav_methodology="Methodology", canonical_url=canonical, city_links=CITY_LINKS, city_country_links=CITY_LINKS_BY_COUNTRY,
        page_title="Where to stay in London: safest boroughs compared | Wandroz",
        page_description="Compare all 33 London boroughs on Metropolitan Police recorded crime. Which rate safest, which suit a first visit, families or a night out, and where to book in each.",
        page_h1="Where to stay in London",
        page_lead="Every borough rated for day and night from Metropolitan Police recorded crime, with the figures behind each rating.",
        hub=_london_hub, hub_unit="boroughs", hub_local="boroughs",
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
        label_hide_sights="Hide sights", label_sights_hidden="Sights hidden",
        footer_note="public official data, not just reviews. In beta — coverage is expanding.",
        zones=js_zones, center=[51.509, -0.118], zoom=10,
    )
    with open(os.path.join(london_dir, "index.html"), "w") as f:
        f.write(html)
    print(f"Wrote {os.path.join(london_dir, 'index.html')} ({len(js_zones)} boroughs, {live_count} auto-refreshed)")
    # London is not in CITY_METHODOLOGY (see the comment where LONDON_EVIDENCE_TAG
    # is defined), so its row is recorded explicitly. Leaving it out is how the
    # site came to publish "27 official-data cities" on the methodology page and
    # 28 green badges on the homepage.
    record_city_facts("london", "London, United Kingdom", "london",
                      london_zones_for_hub,
                      source="Metropolitan Police street-level crime records, data.police.uk",
                      period=london_window(), tier=OFFICIAL_SNAPSHOT, geography="boroughs",
                      source_url="https://data.police.uk/")
    return [canonical]


def mapped_cities():
    """Every city rendered by render_illustrative_city, as
    (data key, url slug, label, flat) — ILLUSTRATIVE_CITIES plus the 20 English
    and Welsh cities on the data.police.uk pipeline.

    WHY THIS FUNCTION EXISTS
        Those 20 were rendered from UK_CITIES in main() but were absent from
        ILLUSTRATIVE_CITIES, and ILLUSTRATIVE_CITIES is what the homepage's
        search index and the published boundary files were built from. So the
        pages existed and nothing else knew about them: 438 neighbourhoods —
        Kingsmead, Compton, every ward of Bath, Plymouth, Leeds, Liverpool —
        could not be found by typing their name, and none of those 20 cities
        could be found by address either, because they had no boundaries.json
        for the point-in-polygon test to load.

        Two lists describing the same set, one of them incomplete, is the bug
        this project keeps rediscovering. There is one list now, and everything
        downstream reads it.
    """
    uk = [(c["key"], c["key"], c["city"], True) for c in UK_CITIES]
    return list(ILLUSTRATIVE_CITIES) + uk


# Separatori con cui un nome amministrativo elenca piu' luoghi in uno.
_ALIAS_SPLIT = re.compile(r"\s*[-/]\s+|\s+[-/]\s*|\s*·\s*")
# Pezzi che da soli non sono il nome di un posto: "Q.re" e' l'abbreviazione di
# quartiere, e cercare "Ovest" non deve portare da nessuna parte.
_ALIAS_STOP = {"q.re", "q", "e.o.", "eo", "nord", "sud", "est", "ovest", "centro",
               "north", "south", "east", "west", "zona", "quartiere"}


def search_aliases(name):
    """I nomi con cui si cerca un'area, quando il suo nome ufficiale ne contiene
    piu' di uno.

    Milano divide la citta' in NIL, e 29 dei suoi 88 si chiamano elencando i
    posti che contengono: "De Angeli - Monte Rosa", "Loreto - Casoretto - Nolo",
    "Gratosoglio - Q.re Missaglia - Q.re Terrazze". Il nome e' quello ufficiale
    e resta tale sulla pagina, perche' il nome deve corrispondere al confine che
    la pagina disegna. Ma nessuno digita "De Angeli - Monte Rosa": digita
    "De Angeli". Questi alias esistono solo nell'indice di ricerca, non sono
    mostrati da nessuna parte, e portano alla stessa pagina.

    Vale anche fuori Milano — Lambrate - Ortica, Gorla - Precotto — e in
    qualunque citta' usi la stessa convenzione.
    """
    out = []
    base = re.sub(r"\s*\([^)]*\)", "", name).strip()
    for part in _ALIAS_SPLIT.split(base):
        part = part.strip(" ,")
        if not part or part == name:
            continue
        if part.lower() in _ALIAS_STOP or len(part) < 3:
            continue
        # "Q.re Feltre" -> "Feltre": il prefisso non e' parte del nome parlato.
        part = re.sub(r"^(?:Q\.re|Quartiere)\s+", "", part).strip()
        if part and part.lower() not in _ALIAS_STOP and part != name:
            out.append(part)
    # Anche il contenuto delle parentesi: "Via Padova (Padova - Turro -
    # Crescenzago)" si cerca per Turro o per Crescenzago.
    for inner in re.findall(r"\(([^)]*)\)", name):
        for part in _ALIAS_SPLIT.split(inner):
            part = re.sub(r"^(?:Q\.re|Quartiere)\s+", "", part.strip(" ,")).strip()
            if part and part.lower() not in _ALIAS_STOP and len(part) >= 3:
                out.append(part)
    seen, uniq = set(), []
    for a in out:
        if a.lower() not in seen:
            seen.add(a.lower())
            uniq.append(a)
    return uniq


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
            for _alias in search_aliases(b["borough"]):
                entries.append({"type": "zone", "name": _alias, "city": city["city"],
                                "url": f"/{city_slug}/{b['slug']}.html", "alias_of": b["borough"]})
            entries.append({
                "type": "zone", "name": b["borough"], "city": city["city"],
                "url": f"/{city_slug}/{b['slug']}.html",
            })

    for city_key, url_slug, label, flat in mapped_cities():
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        if not os.path.isfile(path):
            continue
        data = load_zone_file(path)
        for z in data["zones"]:
            z_url = f"/{url_slug}/{z['slug']}.html" if flat else f"/{url_slug}/{z['slug']}/"
            entries.append({"type": "zone", "name": z["name"], "city": label, "url": z_url})
            for _alias in search_aliases(z["name"]):
                entries.append({"type": "zone", "name": _alias, "city": label,
                                "url": z_url, "alias_of": z["name"]})

    return entries


def build_city_boundaries(cities, city_cards):
    """Boundary data for the homepage's address search, published as one file
    per city plus a small index of city bounding boxes.

    WHY IT IS SPLIT AND NOT ONE FILE
        It used to be a single /zone-boundaries.json: 6 MB, every zone of
        every city, at full source precision. The search never needed all of
        it — a geocoded address is in at most one or two cities — so the
        visitor paid for 62 cities to be told about one, and anyone who wanted
        the whole dataset was handed it in a single request. Now the page
        fetches the index (a few kB of bounding boxes), works out which cities
        the address could be in, and fetches only those. Wanting everything
        means enumerating the cities one at a time, which is both slower and
        visible in the logs.

    The polygons are the rendering-grade ones every map draws (see
    load_zone_file / simplify_rings), never an approximation invented here:
    the point-in-polygon test and the map have to agree about where a boundary
    is, or a visitor lands on a page whose own map contradicts the match.

    Each city's padded bounding box comes from the real union of that city's
    own zone coordinates, not a hand-picked radius, so an address that
    geocodes just outside the outermost mapped zone but still clearly inside
    the city falls back to that city's hub instead of "not covered".

    Returns (per_city, boxes): {slug: [zone, ...]} and the index list.
    """
    per_city = {}
    label_for_slug = {}
    city_bbox = {}

    def _add(slug, label, name, url, coords):
        if not coords or not coords[0]:
            return
        # No "city" field on the zone: the file it is in already says which
        # city this is. One less piece of the taxonomy travelling with the
        # geometry, at no cost to the search.
        per_city.setdefault(slug, []).append({"name": name, "url": url, "coords": coords})
        label_for_slug[slug] = label
        for lat, lon in coords[0]:
            b = city_bbox.setdefault(slug, [lat, lon, lat, lon])
            b[0] = min(b[0], lat)
            b[1] = min(b[1], lon)
            b[2] = max(b[2], lat)
            b[3] = max(b[3], lon)

    for city in cities:
        city_slug = city["city"].lower().replace(" ", "-")
        for b in city["boroughs"]:
            if b.get("coords"):
                _add(city_slug, city["city"], b["borough"],
                     f"/{city_slug}/{b['slug']}.html", b["coords"])

    for city_key, url_slug, label, flat in mapped_cities():
        path = os.path.join(ZONES_DIR, f"{city_key}.json")
        if not os.path.isfile(path):
            continue
        for z in load_zone_file(path)["zones"]:
            z_url = f"/{url_slug}/{z['slug']}.html" if flat else f"/{url_slug}/{z['slug']}/"
            _add(url_slug, label, z["name"], z_url, z["coords"])

    city_url_by_label = {c["name"]: "/" + c["url"] for c in city_cards}
    boxes = []
    for slug, bbox in sorted(city_bbox.items()):
        pad_lat = (bbox[2] - bbox[0]) * 0.08 + 0.01
        pad_lon = (bbox[3] - bbox[1]) * 0.08 + 0.01
        label = label_for_slug[slug]
        boxes.append({
            "name": label,
            "slug": slug,
            "url": city_url_by_label.get(label, "/%s/" % slug),
            "bbox": [bbox[0] - pad_lat, bbox[1] - pad_lon, bbox[2] + pad_lat, bbox[3] + pad_lon],
        })

    return per_city, boxes


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


FINGERPRINT_FILE = "build-fingerprint.txt"


def write_build_fingerprint():
    """A hash of everything the build produced, published with it.

    WHY NOT COMPARE SITEMAPS
        The obvious check for "is production serving what main says?" is to
        compare the live sitemap with the committed one. It would not have
        caught the failure that prompted this: on 18 September a commit changed
        the wording on 1,944 pages and added no URL, Vercel skipped the
        deployment entirely because the account was over its storage quota, and
        the two sitemaps stayed identical for two hours while production served
        the previous build. Nobody noticed until a person opened the site.

        A hash over the CONTENT catches that, and catches it in one request.

    WHY IT DOES NOT BREAK REPRODUCIBILITY
        It is derived from the output, not from the commit: same bytes in, same
        hash out. Embedding the git SHA instead would have made every rebuild
        differ from the one before it and broken the reproducibility gate,
        which is the one thing that must not be traded away for convenience.
    """
    h = hashlib.sha256()
    for root, dirs, files in os.walk(OUT_DIR):
        dirs.sort()
        for name in sorted(files):
            if name == FINGERPRINT_FILE:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, OUT_DIR)
            h.update(rel.encode("utf-8") + b"\0")
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    digest = h.hexdigest()
    path = os.path.join(OUT_DIR, FINGERPRINT_FILE)
    with open(path, "w") as f:
        f.write(digest + "\n")
    print("Wrote %s (%s)" % (path, digest[:16]))
    return digest


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
    data = load_zone_file(path)
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
        {"name": "London", "url": "london/", "flag": "🇬🇧",
         "blurb": f"33 boroughs on the map, {london_live_count} scored from real Metropolitan Police open crime data ({london_window()}).",
         "lat": 51.5074, "lon": -0.1278, "color": "#2f6fed",
         "zone_count": 33, "data_tag": "Official police data"},
        {"name": "Berlin", "url": "berlin/", "flag": "🇩🇪",
         "blurb": "All 143 official Bezirksregionen mapped, safety levels from Polizei Berlin's real official 2025 crime-rate statistics.",
         "lat": 52.5200, "lon": 13.4050, "color": "#1f9e89",
         "zone_count": _zone_count("berlin"), "data_tag": "Official police data"},
        {"name": "Amsterdam", "url": "amsterdam/", "flag": "🇳🇱",
         "blurb": "All 110 official wijken mapped, safety levels from CBS's real official 2025 crime and population statistics.",
         "lat": 52.3676, "lon": 4.9041, "color": "#f2994a",
         "zone_count": _zone_count("amsterdam"), "data_tag": "Official police data"},
        {"name": "Turin", "url": "torino/", "flag": "🇮🇹",
         "blurb": "23 neighbourhoods, real official council boundaries, illustrative safety ratings.",
         "lat": 45.0703, "lon": 7.6869, "color": "#e2a33d",
         "zone_count": _zone_count("torino"), "data_tag": "Official boundaries"},
        {"name": "Zurich", "url": "zurigo/", "flag": "🇨🇭",
         "blurb": "34 neighbourhoods, real official city boundaries, illustrative safety ratings — plus a real official burglary-rate layer by district.",
         "lat": 47.3769, "lon": 8.5417, "color": "#d1483f",
         "zone_count": _zone_count("zurigo"), "data_tag": "Official boundaries + burglary data"},
        {"name": "Milan", "url": "milano/", "flag": "🇮🇹",
         "blurb": "All 88 official zones mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 45.4642, "lon": 9.1900, "color": "#3fae6b",
         "zone_count": _zone_count("milano"), "data_tag": "Official boundaries"},
        {"name": "Rome", "url": "roma/", "flag": "🇮🇹",
         "blurb": "All 155 official zones mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 41.9028, "lon": 12.4964, "color": "#8e44ad",
         "zone_count": _zone_count("roma"), "data_tag": "Official boundaries"},
        {"name": "Prague", "url": "praha/", "flag": "🇨🇿",
         "blurb": "All 57 official mestske casti mapped, safety levels from Policie CR's real official 2024 crime and population statistics.",
         "lat": 50.0755, "lon": 14.4378, "color": "#b5651d",
         "zone_count": _zone_count("praha"), "data_tag": "Official police data"},
        {"name": "Oslo", "url": "oslo/", "flag": "🇳🇴",
         "blurb": "All 15 official bydeler mapped, safety levels from Oslo kommune's real official 2024 crime and population statistics.",
         "lat": 59.9139, "lon": 10.7522, "color": "#2678b6",
         "zone_count": _zone_count("oslo"), "data_tag": "Official police data"},
        {"name": "Munich", "url": "monaco-di-baviera/", "flag": "🇩🇪",
         "blurb": "All 25 official Stadtbezirke mapped, safety levels from Polizeipräsidium München's real official 2025 crime and population statistics.",
         "lat": 48.1372, "lon": 11.5755, "color": "#4a7c59",
         "zone_count": _zone_count("munich"), "data_tag": "Official police data"},
        {"name": "Stockholm", "url": "stockholm/", "flag": "🇸🇪",
         "blurb": "All 11 official stadsdelsnämnder mapped, safety levels from Brå's real official 2025 crime and population statistics.",
         "lat": 59.3293, "lon": 18.0686, "color": "#4472ca",
         "zone_count": _zone_count("stockholm"), "data_tag": "Official police data"},
        {"name": "Barcelona", "url": "barcelona/", "flag": "🇪🇸",
         "blurb": "All 73 official barris mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 41.3874, "lon": 2.1686, "color": "#c94f7c",
         "zone_count": _zone_count("barcelona"), "data_tag": "Official boundaries"},
        {"name": "Madrid", "url": "madrid/", "flag": "🇪🇸",
         "blurb": "All 131 official barrios mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 40.4168, "lon": -3.7038, "color": "#d98e04",
         "zone_count": _zone_count("madrid"), "data_tag": "Official boundaries"},
        {"name": "Vienna", "url": "vienna/", "flag": "🇦🇹",
         "blurb": "All 23 official Bezirke mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 48.2082, "lon": 16.3738, "color": "#5b8c5a",
         "zone_count": _zone_count("vienna"), "data_tag": "Official boundaries"},
        {"name": "Lisbon", "url": "lisbon/", "flag": "🇵🇹",
         "blurb": "All 24 official freguesias mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 38.7223, "lon": -9.1393, "color": "#c9483f",
         "zone_count": _zone_count("lisbon"), "data_tag": "Official boundaries"},
        {"name": "Paris", "url": "paris/", "flag": "🇫🇷",
         "blurb": "All 80 official quartiers administratifs mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 48.8566, "lon": 2.3522, "color": "#3468c0",
         "zone_count": _zone_count("paris"), "data_tag": "Official boundaries"},
        {"name": "Brussels", "url": "brussels/", "flag": "🇧🇪",
         "blurb": "All 19 official communes mapped, safety levels from BISA/Federale Politie's real official 2025 crime and Statbel population statistics.",
         "lat": 50.8503, "lon": 4.3517, "color": "#34495e",
         "zone_count": _zone_count("brussels"), "data_tag": "Official police data"},
        {"name": "Athens", "url": "athens/", "flag": "🇬🇷",
         "blurb": "All 7 official Municipal Districts mapped, real council boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 37.9838, "lon": 23.7275, "color": "#1477a6",
         "zone_count": _zone_count("athens"), "data_tag": "Official boundaries"},
        {"name": "Venice", "url": "venezia/", "flag": "🇮🇹",
         "blurb": "All 6 official Municipalità mapped, mainland included, safety ratings from a structured local-source assessment, area by area.",
         "lat": 45.4408, "lon": 12.3155, "color": "#7a2048",
         "zone_count": _zone_count("venezia"), "data_tag": "Official boundaries"},
        {"name": "Dublin", "url": "dublin/", "flag": "🇮🇪",
         "blurb": "All 11 official Local Electoral Areas mapped, real council electoral boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 53.3498, "lon": -6.2603, "color": "#4b0082",
         "zone_count": _zone_count("dublin"), "data_tag": "Official boundaries"},
    ] + [research_city_card(c, _zone_count(c["key"])) for c in RESEARCH_CITIES] + [
        {"name": "Florence", "url": "firenze/", "flag": "🇮🇹",
         "blurb": "All 74 official quartieri/zone mapped, real Comune di Firenze boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 43.7696, "lon": 11.2558, "color": "#9c6b3e",
         "zone_count": 74, "data_tag": "Official boundaries"},
        {"name": "Edinburgh", "url": "edinburgh/", "flag": "🇬🇧",
         "blurb": "All 17 official City of Edinburgh Council wards mapped, safety ratings anchored to real crimes-per-1,000-population figures per ward.",
         "lat": 55.9533, "lon": -3.1883, "color": "#0f4c81",
         "zone_count": _zone_count("edinburgh"), "data_tag": "Official boundaries"},
        {"name": "Naples", "url": "napoli/", "flag": "🇮🇹",
         "blurb": "All 10 official Municipalità mapped, real OpenStreetMap administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 40.8518, "lon": 14.2681, "color": "#c0392b",
         "zone_count": _zone_count("napoli"), "data_tag": "Official boundaries"},
        {"name": "Budapest", "url": "budapest/", "flag": "🇭🇺",
         "blurb": "All 23 official kerületek mapped, real OpenStreetMap administrative boundaries, safety ratings from a structured local-source assessment, area by area.",
         "lat": 47.4979, "lon": 19.0402, "color": "#477050",
         "zone_count": _zone_count("budapest"), "data_tag": "Official boundaries"},
        {"name": "Kraków", "url": "krakow/", "flag": "🇵🇱",
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
    # E anche le citta' della tabella, altrimenti la loro scheda resta con
    # l'etichetta segnaposto che research_city_card scrive: "Official
    # boundaries" descrive la provenienza del confine, non l'evidenza dietro il
    # voto, ed e' esattamente la stringa che il gate di produzione conta per
    # assicurarsi che non ricompaia in homepage. Toglierla da questa mappa nel
    # refactor l'ha rimessa su cinque schede, e il gate l'ha fermata.
    for _c in RESEARCH_CITIES:
        _CITY_CARD_TO_METHOD_KEY[_c["label"]] = _c["key"]
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
        {"name": c["city"], "url": "%s/" % c["key"], "flag": "🇬🇧",
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
    # La home, una volta per lingua. Senza, un lettore italiano che clicca
    # "Home" da /it/milano/ esce dalla propria lingua al primo clic — ed e' la
    # pagina che raccoglie il traffico di marca.
    def _city_href(lang):
        """Il link a una citta' dalla home: resta nella lingua del lettore dove
        quella citta' esiste in quella lingua, altrimenti va all'inglese.

        Erano link relativi ("bristol/"), che dalla radice funzionano e da /it/
        puntano a /it/bristol/ — una pagina che non esiste, perche' Bristol e'
        inglese e non ha una versione italiana. Stesso difetto del "../" nelle
        briciole di pane: un link relativo cambia significato quando cambia la
        profondita' della pagina che lo contiene."""
        have = {c["slug"] for c in CITY_FACTS
                if lang in i18n.languages_for_country_code(
                    city_country_code(c["label"]))}
        def href(url):
            slug = url.strip("/")
            return i18n.url_for(lang, slug + "/") if slug in have else "/" + slug + "/"
        return href

    _home_langs = [i18n.DEFAULT_LANG] + i18n.extra_languages()
    _home_alts = [(lg, SITE_URL + i18n.url_for(lg, "")) for lg in _home_langs]
    for _lang in _home_langs:
        _t = i18n.strings(_lang)
        _out = OUT_DIR if _lang == i18n.DEFAULT_LANG else os.path.join(OUT_DIR, _lang)
        os.makedirs(_out, exist_ok=True)
        with open(os.path.join(_out, "index.html"), "w") as f:
            f.write(index_tpl.render(
                lang=_lang, t=_t, alternates=_home_alts,
                home_url=i18n.url_for(_lang, ""),
                    city_href=_city_href(_lang),
                # Solo i nomi che la lingua cambia davvero: "Rome" -> "Roma",
                # "Bologna" resta "Bologna". Vedi i18n.PLACE_NAMES.
                place=(lambda nm, _l=_lang: i18n.place(_l, nm)),
                city_cards=city_cards, countries=countries, popular_cities=popular_cities,
                preview_zone=preview_zone,
                canonical_url=SITE_URL + i18n.url_for(_lang, ""),
                geocode_countries=country_codes_covered(),
            ))
        if _lang != i18n.DEFAULT_LANG:
            sitemap_urls.append(SITE_URL + i18n.url_for(_lang, ""))

    # Homepage search bar's data — built fresh from real content on every
    # run (see build_search_index docstring), never hand-maintained.
    search_entries = build_search_index(cities, city_cards)
    with open(os.path.join(OUT_DIR, "search-index.json"), "w") as f:
        json.dump(search_entries, f, ensure_ascii=False)
    print(f"Wrote {os.path.join(OUT_DIR, 'search-index.json')} ({len(search_entries)} entries)")

    # Homepage address search's boundary data — real zone polygons + real
    # per-city bounding boxes, used for a client-side point-in-polygon
    # match against a geocoded address (see build_city_boundaries
    # docstring and templates/index.html). One file per city, next to that
    # city's own pages, plus a small index at the root.
    per_city_boundaries, city_boxes = build_city_boundaries(cities, city_cards)
    written = 0
    for slug, zones_out in sorted(per_city_boundaries.items()):
        city_dir = os.path.join(OUT_DIR, slug)
        os.makedirs(city_dir, exist_ok=True)
        with open(os.path.join(city_dir, "boundaries.json"), "w") as f:
            json.dump({"zones": zones_out}, f, ensure_ascii=False)
        written += 1
    with open(os.path.join(OUT_DIR, "city-boxes.json"), "w") as f:
        json.dump({"cities": city_boxes}, f, ensure_ascii=False)
    # The single global file this replaced is committed in dist/. A build that
    # merely stops writing it would leave it served forever, so the build
    # removes it — and keeps removing it, harmlessly, once it is gone.
    stale = os.path.join(OUT_DIR, "zone-boundaries.json")
    if os.path.isfile(stale):
        os.remove(stale)
        print(f"Removed {stale} (superseded by per-city boundaries.json)")
    print(f"Wrote {written} per-city boundaries.json + city-boxes.json ({len(city_boxes)} city boxes)")

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
                booking_url=booking_href(london_queries.get(_canon(b["borough"])) or "", "london"),
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
    research_counts = {}
    for c in RESEARCH_CITIES:
        urls = render_illustrative_city(c["key"], c["key"], research_city_ui(c["label"], c["areas"]),
                                        EN_TONE_BADGE, flat=True)
        sitemap_urls.extend(urls)
        research_counts[c["label"]] = len(urls)
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
    research_summary = ", ".join("%s (%d)" % kv for kv in research_counts.items())
    print(f"Rendered interactive map hubs: Torino ({len(torino_urls)}), Zurigo ({len(zurigo_urls)}), London ({len(london_map_urls)}), Milano ({len(milano_urls)}), Roma ({len(roma_urls)}), Berlin ({len(berlin_urls)}), Amsterdam ({len(amsterdam_urls)}), Prague ({len(praha_urls)}), Oslo ({len(oslo_urls)}), Munich ({len(munich_urls)}), Stockholm ({len(stockholm_urls)}), Barcelona ({len(barcelona_urls)}), Madrid ({len(madrid_urls)}), Vienna ({len(vienna_urls)}), Lisbon ({len(lisbon_urls)}), Paris ({len(paris_urls)}), Brussels ({len(brussels_urls)}), Athens ({len(athens_urls)}), Venice ({len(venezia_urls)}), Dublin ({len(dublin_urls)}), Edinburgh ({len(edinburgh_urls)}), Naples ({len(napoli_urls)}), {research_summary}, Budapest ({len(budapest_urls)}), Kraków ({len(krakow_urls)}), Firenze ({len(firenze_urls)})")

    # Methodology page. Written LAST, on purpose: its source table is built
    # from CITY_FACTS, which every city fills in as it is rendered. Written
    # before them, as it used to be, it could only describe the site from a
    # separate set of constants — which is how it came to say 27 official-data
    # cities while the homepage showed 28 badges.
    ev = evidence_stats()
    facts = sorted(CITY_FACTS, key=lambda c: (TIER_ORDER[c["tier"]], c["label"]))
    with open(os.path.join(OUT_DIR, "methodology.html"), "w") as f:
        f.write(methodology_tpl.render(
            canonical_url=SITE_URL + "/methodology.html",
            london_covered_count=london_live_count,
            london_total_boroughs=33,
            london_window=london_window(),
            uk_cities=[c["city"] for c in UK_CITIES],
            uk_forces=sorted({c["force"] for c in UK_CITIES}),
            ev=ev,
            facts=facts,
            tier_official=OFFICIAL_SNAPSHOT,
            tier_research=RESEARCH_BASED,
            tier_limited=MANUAL_EXPERIMENTAL,
            tag_for=EVIDENCE_TAG,
            n_cities=len(facts),
            n_countries=len(countries_covered()),
            n_areas=sum(c["areas"] for c in facts),
            n_official=sum(1 for c in facts if c["tier"] == OFFICIAL_SNAPSHOT),
            n_research=sum(1 for c in facts if c["tier"] == RESEARCH_BASED),
            n_limited=sum(1 for c in facts if c["tier"] == MANUAL_EXPERIMENTAL),
            correction_email=CORRECTION_EMAIL,
        ))
    print(f"Wrote {os.path.join(OUT_DIR, 'methodology.html')} "
          f"({len(facts)} cities in the source table)")

    assert_every_poi_file_is_used()
    write_robots_and_sitemap(sitemap_urls)
    # Ultimo di tutti: l'impronta deve coprire ogni file appena scritto.
    write_build_fingerprint()


if __name__ == "__main__":
    main()
