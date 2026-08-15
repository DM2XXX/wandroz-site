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
import shutil
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data", "scores")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUT_DIR = os.path.join(BASE_DIR, "..", "dist")

# Canonical public URL — apex wandroz.com 308-redirects to this host on
# Vercel, so this is what canonical/OG tags and the sitemap should use.
SITE_URL = "https://www.wandroz.com"

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)


def score_label(rank, total):
    frac = (rank - 1) / max(total - 1, 1)
    if frac <= 0.2:
        return "Relatively safer", "good"
    if frac <= 0.6:
        return "Average", "mid"
    return "Higher caution advised", "caution"


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cities = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            city_data = json.load(f)
        cities.append(city_data)

    index_tpl = env.get_template("index.html")
    borough_tpl = env.get_template("borough.html")
    methodology_tpl = env.get_template("methodology.html")

    sitemap_urls = [SITE_URL + "/", SITE_URL + "/methodology.html"]

    # Home page
    with open(os.path.join(OUT_DIR, "index.html"), "w") as f:
        f.write(index_tpl.render(cities=cities, canonical_url=SITE_URL + "/"))

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
            label, tone = score_label(b["relative_rank"], total)
            page_url = f"{SITE_URL}/{city_slug}/{b['slug']}.html"
            page = borough_tpl.render(
                city=city, b=b, label=label, tone=tone, canonical_url=page_url
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

    write_robots_and_sitemap(sitemap_urls)


if __name__ == "__main__":
    main()
