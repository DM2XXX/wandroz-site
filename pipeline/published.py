"""
What the site actually publishes, read from the built pages.

WHY THIS EXISTS
    Two checks were written against mapped_cities(), the registry of cities
    build_site renders. Both reported clean runs across "61 cities, none
    missing". Neither had ever looked at London.

    London is not in mapped_cities(). It has its own pipeline built directly on
    data.police.uk, so it is rendered by a different path and registered in a
    different place — and every check that iterates the registry skips all 33
    boroughs without noticing. mapped_cities()' own docstring says it: "Two
    lists describing the same set, one of them incomplete, is the bug this
    project keeps rediscovering."

    Adding London to the registry would fix today's instance and leave the
    shape of the bug intact. Reading the built pages instead cannot drift: if a
    page is published, it is checked, whichever pipeline produced it. A check
    that reads the registry verifies what we meant to publish; this reads what
    we did.

WHAT IT RETURNS
    (slug, zones) for every published city hub, where each zone is the dict the
    page hands to Leaflet — the same object the reader's browser colours the
    map with, carrying name, day, night, text, evidence and any burglary
    disclosure.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(os.path.dirname(HERE), "dist")

ZONES_RE = re.compile(r"var ZONES = (\[.*?\]);\n", re.S)


def published_cities(dist=None, skip_translations=True):
    """Yields (slug, zones) per published city hub, newest build on disk.

    Translated hubs live under dist/<lang>/<city>/ and carry the same ratings
    as the English page, so by default they are skipped: reporting the same
    contradiction once per language turns one finding into seventeen."""
    root = dist or DIST
    if not os.path.isdir(root):
        raise SystemExit("no dist/ — run build_site.py first")
    langs = {d for d in os.listdir(root)
             if len(d) == 2 and os.path.isdir(os.path.join(root, d))}
    for entry in sorted(os.listdir(root)):
        if skip_translations and entry in langs:
            continue
        index = os.path.join(root, entry, "index.html")
        if not os.path.isfile(index):
            continue
        with open(index, encoding="utf-8") as f:
            html = f.read()
        m = ZONES_RE.search(html)
        if not m:
            continue
        try:
            zones = json.loads(m.group(1))
        except ValueError:
            continue
        if zones:
            yield entry, zones
