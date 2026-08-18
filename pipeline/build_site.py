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
CORRECTION_EMAIL = "dadenuoto@gmail.com"

# Every city with a map page, used to populate the "City" switcher shown on
# every map page (top-right, next to the Day/Night toggle) so a visitor can
# jump straight from one city's map to another's without going back home.
CITY_LINKS = [
    {"label": "London", "url": f"{SITE_URL}/london/"},
    {"label": "Turin", "url": f"{SITE_URL}/torino/"},
    {"label": "Zurich", "url": f"{SITE_URL}/zurigo/"},
    {"label": "Milan", "url": f"{SITE_URL}/milano/"},
]

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
TONE_DESCRIPTOR = {
    "green": "relatively safer than most other areas covered on Wandroz",
    "yellow": "roughly average compared to other areas covered on Wandroz",
    "red": "an area where Wandroz's data suggests extra caution relative to other areas covered",
    "grey": "not yet covered by a comparative rating",
}


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


def build_faq_illustrative(zone, city_label, burglary=None):
    """FAQ content for a Turin/Zurich neighbourhood page — honest about the
    fact that the underlying rating is a qualitative first pass, not a
    geolocated crime dataset (unlike London). If burglary is given (Zurich
    only), a 4th question surfaces that one real, narrowly-scoped official
    data point instead of just saying "no data exists"."""
    name = zone["name"]
    day_desc = TONE_DESCRIPTOR.get(zone["day"], zone["day"])
    night_desc = TONE_DESCRIPTOR.get(zone["night"], zone["night"])
    faqs = [
        {
            "q": f"Is {name} safe?",
            "a": (
                f"Wandroz currently rates {name} in {city_label} as {day_desc} during the day and "
                f"{night_desc} at night. This is a qualitative first-pass assessment based on general "
                f"local knowledge and public reputation, not an official geolocated crime dataset — see "
                f"the note on data limitations below before treating it as more precise than it is."
            ),
        },
        {
            "q": f"Is {name} safe at night?",
            "a": (
                f"At night, {name} is rated as {night_desc}. If you're unsure, it's worth checking recent "
                f"local reviews for your specific street or block, since a neighbourhood-wide rating can't "
                f"capture block-by-block variation."
            ),
        },
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
                  f"not specifically for {name} — see the box below for the full figure and caveats."
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
    day_desc = TONE_DESCRIPTOR.get(b.get("day_tone"), b.get("day_tone"))
    night_desc = TONE_DESCRIPTOR.get(b.get("night_tone"), b.get("night_tone"))
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


def render_illustrative_city(city_key, url_slug, ui, tone_badge, data_note_banner, neigh_note, extra_zone_data=None):
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
    buried in each zone's detail page."""
    path = os.path.join(ZONES_DIR, f"{city_key}.json")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        data = json.load(f)
    zones = data["zones"]
    urls = []

    city_dir = os.path.join(OUT_DIR, url_slug)
    os.makedirs(city_dir, exist_ok=True)

    js_zones = []
    for z in zones:
        z_url = f"/{url_slug}/{z['slug']}/"
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
        data_note=data_note_banner, show_toggle=True,
        label_day=ui["label_day"], label_night=ui["label_night"],
        legend_green=ui["legend_green"], legend_yellow=ui["legend_yellow"],
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
        zdir = os.path.join(city_dir, z["slug"])
        os.makedirs(zdir, exist_ok=True)
        z_canonical = f"{SITE_URL}/{url_slug}/{z['slug']}/"
        zone_ctx = dict(z)
        zone_ctx["day_label"] = tone_badge.get(z["day"], z["day"])
        zone_ctx["night_label"] = tone_badge.get(z["night"], z["night"])
        if extra_zone_data:
            zone_ctx["burglary"] = extra_zone_data.get(z["name"])
        faq_items = build_faq_illustrative(zone_ctx, data["label"], burglary=zone_ctx.get("burglary"))
        page = neigh_tpl.render(
            lang="en", city_label=data["label"], tagline=ui["tagline"],
            nav_home=ui["nav_home"], canonical_url=z_canonical,
            page_title=ui["neigh_title"].format(name=z["name"], city=data["label"]),
            page_description=z["text"][:160],
            zone=zone_ctx, label_day=ui["label_day"], label_night=ui["label_night"],
            label_detail=ui["label_detail"], label_booking=ui["label_booking"],
            label_booking_note=ui["label_booking_note"], data_note=neigh_note,
            footer_note=ui["footer_note"], correction_email=CORRECTION_EMAIL,
            faq_items=faq_items, faq_schema=_faq_jsonld(faq_items),
        )
        with open(os.path.join(zdir, "index.html"), "w") as f:
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
        footer_note="public official data, not just reviews. Prototype build.",
        zones=js_zones, center=[51.509, -0.118], zoom=10,
    )
    with open(os.path.join(london_dir, "index.html"), "w") as f:
        f.write(html)
    print(f"Wrote {os.path.join(london_dir, 'index.html')} ({len(js_zones)} boroughs, {live_count} auto-refreshed)")
    return [canonical]


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
    "footer_note": "prototype build, not a finished product",
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


# NOTE: the homepage used to carry a large static SVG landmass path here for
# a hand-tuned decorative "flight map" hero. That hero (fixed equirectangular
# pin positions + a duplicate city-card list below it) has been replaced by
# a real, zoomable Leaflet map (see templates/index.html and the city_cards
# lat/lon below), so this constant is no longer needed and was removed.


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
    city_cards = [
        {"name": "London", "url": "london/index.html", "flag": "🇬🇧",
         "blurb": f"33 boroughs on the map, {london_live_count} refreshed automatically every month from real Metropolitan Police data.",
         "lat": 51.5074, "lon": -0.1278, "color": "#2f6fed"},
        {"name": "Turin", "url": "torino/index.html", "flag": "🇮🇹",
         "blurb": "23 neighbourhoods, real official council boundaries, illustrative safety ratings.",
         "lat": 45.0703, "lon": 7.6869, "color": "#e2a33d"},
        {"name": "Zurich", "url": "zurigo/index.html", "flag": "🇨🇭",
         "blurb": "34 neighbourhoods, real official city boundaries, illustrative safety ratings — plus a real official burglary-rate layer by district.",
         "lat": 47.3769, "lon": 8.5417, "color": "#d1483f"},
        {"name": "Milan", "url": "milano/index.html", "flag": "🇮🇹",
         "blurb": "All 88 official zones mapped, real council boundaries, safety ratings from genuine current local press research.",
         "lat": 45.4642, "lon": 9.1900, "color": "#3fae6b"},
    ]
    with open(os.path.join(OUT_DIR, "index.html"), "w") as f:
        f.write(index_tpl.render(city_cards=city_cards, canonical_url=SITE_URL + "/"))

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
    print(f"Rendered interactive map hubs: Torino ({len(torino_urls)}), Zurigo ({len(zurigo_urls)}), London ({len(london_map_urls)}), Milano ({len(milano_urls)})")

    write_robots_and_sitemap(sitemap_urls)


if __name__ == "__main__":
    main()
