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

# Every city with a map page, used to populate the "City" switcher shown on
# every map page (top-right, next to the Day/Night toggle) so a visitor can
# jump straight from one city's map to another's without going back home.
CITY_LINKS = [
    {"label": "London", "url": f"{SITE_URL}/london/"},
    {"label": "Turin", "url": f"{SITE_URL}/torino/"},
    {"label": "Zurich", "url": f"{SITE_URL}/zurigo/"},
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


def render_illustrative_city(city_key, url_slug, ui, tone_badge, data_note_banner, neigh_note):
    """Render a full-city interactive map (day/night toggle, click-a-zone
    detail sidebar) plus one detail sub-page per neighbourhood, for a city
    whose ratings are an illustrative first pass rather than an automated
    pipeline (Turin, Zurich today). Mirrors the original map prototype's
    UX exactly, instead of the flat card-grid list this replaces."""
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
        js_zones.append({
            "name": z["name"], "slug": z["slug"],
            "day": z["day"], "night": z["night"],
            "day_label": tone_badge.get(z["day"], z["day"]),
            "night_label": tone_badge.get(z["night"], z["night"]),
            "text": z["text"], "query": z["query"],
            "coords": z["coords"], "url": z_url,
        })

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
        page = neigh_tpl.render(
            lang="en", city_label=data["label"], tagline=ui["tagline"],
            nav_home=ui["nav_home"], canonical_url=z_canonical,
            page_title=ui["neigh_title"].format(name=z["name"], city=data["label"]),
            page_description=z["text"][:160],
            zone=zone_ctx, label_day=ui["label_day"], label_night=ui["label_night"],
            label_detail=ui["label_detail"], label_booking=ui["label_booking"],
            label_booking_note=ui["label_booking_note"], data_note=neigh_note,
            footer_note=ui["footer_note"],
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
    data_note = (
        "Boundaries and ratings are based on real Metropolitan Police crime data (data.police.uk). Five boroughs — "
        "Westminster, Camden, Islington, Kensington & Chelsea, Lambeth — are refreshed automatically every month: "
        "their day score (property crime) and night score (violence, robbery, street theft, public order, "
        "anti-social behaviour — a category-mix proxy, not literal time-stamped data) are each normalised by an "
        "estimated workday/footfall population rather than resident population, then rated against the AVERAGE of "
        "those same 5 boroughs (not yet a full London average, since only 5 of 33 are covered so far). Click one and "
        "follow the link for the live current numbers and full methodology. The other 28 boroughs reflect the same "
        "real dataset from when this map was built and aren't on the automatic refresh yet. City of London is "
        "unrated (policed by a separate force, not covered by this dataset)."
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
    "dataset). Safety levels, on the other hand, are a first manual pass — general knowledge, not a geolocated "
    "crime dataset — unlike London. See the methodology page for details."
)
ZURIGO_NEIGH_NOTE = (
    "Risk levels for Zurich are a qualitative judgment call based on general knowledge and public reputation of "
    "each neighbourhood, not an official geolocated crime dataset — unlike London, no open municipal dataset at "
    "this level of detail exists yet for Zurich."
)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cities = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            city_data = json.load(f)
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
    city_cards = [
        {"name": "London", "url": "london/index.html",
         "blurb": f"33 boroughs on the map, {london_live_count} refreshed automatically every month from real Metropolitan Police data."},
        {"name": "Turin", "url": "torino/index.html",
         "blurb": "23 neighbourhoods, real official council boundaries, illustrative safety ratings."},
        {"name": "Zurich", "url": "zurigo/index.html",
         "blurb": "34 neighbourhoods, real official city boundaries, illustrative safety ratings."},
    ]
    with open(os.path.join(OUT_DIR, "index.html"), "w") as f:
        f.write(index_tpl.render(city_cards=city_cards, canonical_url=SITE_URL + "/"))

    # Methodology page
    with open(os.path.join(OUT_DIR, "methodology.html"), "w") as f:
        f.write(methodology_tpl.render(canonical_url=SITE_URL + "/methodology.html"))
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
            page = borough_tpl.render(
                city=city, b=b, day_label=day_label, night_label=night_label,
                canonical_url=page_url,
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
    zurigo_urls = render_illustrative_city("zurigo", "zurigo", ZURIGO_UI, EN_TONE_BADGE, ZURIGO_BANNER, ZURIGO_NEIGH_NOTE)
    sitemap_urls.extend(zurigo_urls)
    london_map_urls = render_london_map(cities)
    sitemap_urls.extend(london_map_urls)
    print(f"Rendered interactive map hubs: Torino ({len(torino_urls)}), Zurigo ({len(zurigo_urls)}), London ({len(london_map_urls)})")

    write_robots_and_sitemap(sitemap_urls)


if __name__ == "__main__":
    main()
