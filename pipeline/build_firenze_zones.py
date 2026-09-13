"""
Wandroz — Florence zone-source recovery (one-shot, kept for provenance)

WHY THIS EXISTS
  Florence was the only city on Wandroz with no generator source. Its 75
  pages (1 hub + 74 zone pages) existed solely as hand-committed HTML in
  dist/firenze/, which meant every systemic fix to the generator silently
  skipped Florence, and a clean rebuild from source would have deleted the
  city entirely.

  The zone data was not lost, though — dist/firenze/index.html embeds the
  complete dataset as a `var ZONES = [...]` literal for the interactive
  map, carrying exactly the fields data_zones/*.json needs. This script
  lifts that literal back out into pipeline/data_zones/firenze.json so
  Florence becomes an ordinary first-class pipeline city.

  It is committed rather than thrown away so the provenance of
  firenze.json is auditable: anyone can re-run it against the same input
  and get the same file. It is NOT part of the normal build — run it once,
  commit the JSON, and it should never need to run again.

USAGE
    python3 pipeline/build_firenze_zones.py                 # write the file
    python3 pipeline/build_firenze_zones.py --check         # verify only

WHAT IS AND ISN'T RECOVERED
  Recovered from the HTML: label, center, zoom, dataNote (the hub's own
  sourcing notice) and all 74 zones with name / slug / day / night /
  coords / text / query.

  Deliberately dropped: day_label, night_label and url. Those three are
  render-time derivations (tone label lookup and slug-to-path), not
  inputs — keeping them in source would create a second place for the
  same fact to live, which is the exact class of bug this whole recovery
  is undoing.
"""

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
SRC_HTML = os.path.join(REPO_DIR, "dist", "firenze", "index.html")
OUT_JSON = os.path.join(BASE_DIR, "data_zones", "firenze.json")

# Recovered from the same page: `var CENTER = [...]` and `var ZOOM = ...`.
# Hardcoded here rather than re-parsed because they are two scalars and
# parsing them adds failure modes for no benefit.
LABEL = "Florence, Italy"
CENTER = [43.7696, 11.2558]
ZOOM = 12

SOURCE_FIELDS = ("name", "slug", "day", "night", "coords", "text", "query")
VALID_TONES = {"green", "yellow", "red", "grey"}
EXPECTED_ZONES = 74


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_zones(html):
    """Pull the `var ZONES = [...]` literal out of the hub page.

    The literal is emitted by the generator as a single json.dumps() call
    on one line, so it is already valid JSON — no JS-to-JSON translation
    is needed, and none is attempted (a regex that tried to would be the
    fragile part of this script).
    """
    m = re.search(r"var ZONES\s*=\s*(\[.*?\]);\s*$", html, re.MULTILINE | re.DOTALL)
    if not m:
        raise SystemExit(
            "FATAL: no `var ZONES = [...];` literal found in %s — the hub page "
            "format has changed, or this is not the hand-built Florence page." % SRC_HTML
        )
    return json.loads(m.group(1))


def extract_data_note(html):
    """Recover the hub's sourcing notice, which becomes `dataNote`.

    This is the text that states Florence's boundaries are the Comune's
    official Aree elementari 2021 and that its ratings are Level 2 press
    research. It is the city's honesty disclosure, so it has to survive
    the migration verbatim rather than being paraphrased.
    """
    m = re.search(r'<div class="notice">(.*?)</div>', html, re.DOTALL)
    if not m:
        raise SystemExit("FATAL: no <div class=\"notice\"> block found in %s" % SRC_HTML)
    text = re.sub(r"<[^>]+>", "", m.group(1))
    for entity, char in (
        ("&#39;", "'"), ("&#34;", '"'), ("&quot;", '"'),
        ("&mdash;", "—"), ("&ndash;", "–"),
        ("&nbsp;", " "), ("&amp;", "&"),
    ):
        text = text.replace(entity, char)
    return "Firenze: " + " ".join(text.split())


def build():
    html = _read(SRC_HTML)
    raw_zones = extract_zones(html)
    zones = [{k: z[k] for k in SOURCE_FIELDS} for z in raw_zones]
    return {
        "label": LABEL,
        "center": CENTER,
        "zoom": ZOOM,
        "dataNote": extract_data_note(html),
        "zones": zones,
    }


def validate(doc):
    """Fail loudly rather than commit a subtly wrong source file."""
    problems = []
    zones = doc["zones"]

    if len(zones) != EXPECTED_ZONES:
        problems.append("expected %d zones, got %d" % (EXPECTED_ZONES, len(zones)))

    names = [z["name"] for z in zones]
    slugs = [z["slug"] for z in zones]
    if len(set(names)) != len(names):
        problems.append("duplicate zone names")
    if len(set(slugs)) != len(slugs):
        problems.append("duplicate zone slugs")

    for z in zones:
        where = z.get("slug") or "<no slug>"
        for field in SOURCE_FIELDS:
            if field not in z:
                problems.append("%s: missing field %r" % (where, field))
        if not z.get("coords"):
            problems.append("%s: empty coords" % where)
        if not (z.get("text") or "").strip():
            problems.append("%s: empty text" % where)
        if not (z.get("query") or "").strip():
            problems.append("%s: empty query" % where)
        for tone_field in ("day", "night"):
            if z.get(tone_field) not in VALID_TONES:
                problems.append("%s: %s=%r not a valid tone" % (where, tone_field, z.get(tone_field)))

    # Cross-check against what is actually committed in dist/, so the source
    # provably describes the same 74 pages that are live today.
    dist_dir = os.path.join(REPO_DIR, "dist", "firenze")
    if os.path.isdir(dist_dir):
        on_disk = {
            f[:-5] for f in os.listdir(dist_dir)
            if f.endswith(".html") and f != "index.html"
        }
        missing = on_disk - set(slugs)
        extra = set(slugs) - on_disk
        if missing:
            problems.append("slugs in dist/ but not in source: %s" % ", ".join(sorted(missing)))
        if extra:
            problems.append("slugs in source but not in dist/: %s" % ", ".join(sorted(extra)))
    return problems


def main():
    check_only = "--check" in sys.argv
    doc = build()
    problems = validate(doc)

    if problems:
        print("FAIL — Florence source recovery did not validate:")
        for p in problems:
            print("  - %s" % p)
        return 1

    day_night_split = sum(1 for z in doc["zones"] if z["day"] != z["night"])
    print("Florence source recovered and validated:")
    print("  zones                 %d" % len(doc["zones"]))
    print("  zones with day!=night %d  (so SHOW_TOGGLE will be True, as it is live)" % day_night_split)
    print("  dataNote              %d chars" % len(doc["dataNote"]))

    if check_only:
        print("  --check given, nothing written")
        return 0

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("  wrote                 %s" % os.path.relpath(OUT_JSON, REPO_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
