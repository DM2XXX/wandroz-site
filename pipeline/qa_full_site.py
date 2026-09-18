"""
Wandroz — full-site deterministic QA gate

WHAT THIS ASKS
  "Is the generated website internally correct?"

  Its sibling, verify_reproducible.py, asks a different question — "can
  canonical source reproduce the intended site?" — and the two are kept
  apart deliberately. This one never looks at source coverage; it takes a
  built directory and audits it against the generator's own canonical
  constants.

WHY IT ASSERTS AGAINST build_site.py RATHER THAN ITS OWN COPY OF THE FACTS
  The class of bug this project keeps hitting is the same one every time:
  a fact (the city list, the evidence tier, the correction address) exists
  in two places and they drift. A QA script with its own hardcoded city
  list would be a third place. So the canonical values are imported from
  build_site and the script fails if they cannot be.

HARD FAILURES vs WARNINGS
  FAIL blocks deployment: broken links, missing pages, slug collisions,
  map/page mismatch, wrong canonical, malformed Booking URLs, stale
  navigation, methodology contradictions, a non-canonical contact address.
  WARN is reported and deployable: Booking destination ambiguity that
  needs a human eye, duplicate meta, cosmetic drift.

USAGE
    python3 pipeline/qa_full_site.py                      # audit dist/
    python3 pipeline/qa_full_site.py --dist build_candidate
    python3 pipeline/qa_full_site.py --report-dir qa_output
    python3 pipeline/qa_full_site.py --warnings-as-errors

EXIT CODES
    0  no hard failures
    1  at least one hard failure
    2  the audit itself could not run (bad path, unimportable generator)
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)

try:
    import build_site as BS
except Exception as exc:  # pragma: no cover - environment problem, not a site problem
    print("FATAL: cannot import pipeline/build_site.py (%s)." % exc)
    print("QA asserts against the generator's own constants and refuses to guess them.")
    sys.exit(2)


# --------------------------------------------------------------------------
# City registry
# --------------------------------------------------------------------------
# Maps the public URL slug to the data_zones key, the URL scheme, and where
# the zone data comes from. Three cities need it because the two names differ
# (monaco-di-baviera/munich) or the scheme does (torino, zurigo, milano are
# nested; every other illustrative city is flat).
#
# This belongs in build_site.py as the single canonical registry — see
# PATCH-build_site.md. Until it moves there, QA carries it and warns, rather
# than silently owning a second copy of the truth.
FALLBACK_REGISTRY = {
    #  url slug             data_zones key       scheme
    "amsterdam":            ("amsterdam",        "flat"),
    "athens":               ("athens",           "flat"),
    "barcelona":            ("barcelona",        "flat"),
    "berlin":               ("berlin",           "flat"),
    "birmingham":           ("birmingham",       "flat"),
    "bristol":              ("bristol",          "flat"),
    "brussels":             ("brussels",         "flat"),
    "budapest":             ("budapest",         "flat"),
    "dublin":               ("dublin",           "flat"),
    "edinburgh":            ("edinburgh",        "flat"),
    "firenze":              ("firenze",          "flat"),
    "krakow":               ("krakow",           "flat"),
    "leeds":                ("leeds",            "flat"),
    "lisbon":               ("lisbon",           "flat"),
    "madrid":               ("madrid",           "flat"),
    "milano":               ("milano",           "nested"),
    "monaco-di-baviera":    ("munich",           "flat"),
    "napoli":               ("napoli",           "flat"),
    "oslo":                 ("oslo",             "flat"),
    "paris":                ("paris",            "flat"),
    "praha":                ("praha",            "flat"),
    "roma":                 ("roma",             "flat"),
    "bologna":              ("bologna",          "flat"),
    "verona":               ("verona",           "flat"),
    "genova":               ("genova",           "flat"),
    "trieste":              ("trieste",          "flat"),
    "catania":              ("catania",          "flat"),
    "parma":                ("parma",            "flat"),
    "warsaw":               ("warsaw",           "flat"),
    "tallinn":              ("tallinn",          "flat"),
    "zagreb":               ("zagreb",           "flat"),
    "bucharest":            ("bucharest",        "flat"),
    "bratislava":           ("bratislava",       "flat"),
    "vilnius":              ("vilnius",          "flat"),
    "rotterdam":            ("rotterdam",        "flat"),
    "utrecht":              ("utrecht",          "flat"),
    "denhaag":              ("denhaag",          "flat"),
    "antwerp":              ("antwerp",          "flat"),
    "ghent":                ("ghent",            "flat"),
    "cardiff":               ("cardiff",             "flat"),
    "leicester":             ("leicester",           "flat"),
    "newcastle":             ("newcastle",           "flat"),
    "nottingham":            ("nottingham",          "flat"),
    "sheffield":             ("sheffield",           "flat"),
    "brighton":              ("brighton",            "flat"),
    "liverpool":             ("liverpool",           "flat"),
    "bath":                  ("bath",                "flat"),
    "cambridge":             ("cambridge",           "flat"),
    "oxford":                ("oxford",              "flat"),
    "york":                  ("york",                "flat"),
    "coventry":              ("coventry",            "flat"),
    "portsmouth":            ("portsmouth",          "flat"),
    "southampton":           ("southampton",         "flat"),
    "plymouth":              ("plymouth",            "flat"),
    "derby":                 ("derby",               "flat"),
    "norwich":               ("norwich",             "flat"),
    "stockholm":            ("stockholm",        "flat"),
    "torino":               ("torino",           "nested"),
    "venezia":              ("venezia",          "flat"),
    "vienna":               ("vienna",           "flat"),
    "zurigo":               ("zurigo",           "nested"),
}
# London is generated by its own pipeline from data/scores/london.json and
# uses underscored borough slugs, so it is handled separately throughout.
LONDON_SLUG = "london"

VALID_TONES = {"green", "yellow", "red", "grey"}

# Copy that was true once and is not any more. Any of these in output is a
# hard failure — this is the check that would have caught the four stale
# production vintages while they were still candidates.
FORBIDDEN_PHRASES = [
    ("prototype build", "superseded footer wording; the canonical footer says 'in beta'"),
    ("not a finished product", "superseded footer wording"),
    ("both figures shown are the same", "stale: contradicts the single-badge rendering"),
    ("areas covered on Wandroz", "superseded cross-city comparability wording"),
    ("only automated", "stale methodology claim from the 3-city era"),
    ("Overall safety level", "superseded badge label"),
]

# Retired vocabulary. These described the work as either more casual than it
# is ("general local knowledge", "public reputation") or as an internal tier
# number that means nothing to a reader ("Level 2"). They are now defects
# anywhere in public output, not just off-tier.
RETIRED_VOCABULARY = [
    ("Level 2", "internal tier number; the page says which evidence class a city is on"),
    ("Tier 2", "internal tier number"),
    ("press research", "understates an area-level source review; say 'local-source assessment'"),
    ("general local knowledge", "describes reviewed work as casual"),
    ("public reputation", "describes reviewed work as casual"),
    ("qualitative first-pass", "retired label; the class is 'limited-data assessment'"),
    ("manual first-pass", "retired label"),
    ("refreshed automatically every month", "the London refresh is gated and run on review, not unattended"),
    ("refreshes automatically once a month", "same claim, same problem"),
]

# Addresses retired from public use. This list does NOT define what is
# acceptable for the correction component — BS.CORRECTION_EMAIL alone does
# that. A retired address is a defect anywhere in public output, so this
# assertion is site-wide rather than scoped to the correction component.
LEGACY_EMAILS = {"dadenuoto@gmail.com"}

# Booking attribution parameters recognised by Booking.com / its affiliate
# networks. Presence is evidence of an attribution attempt; ABSENCE is
# conclusive, but presence alone never proves attribution actually works —
# see BOOKING_LAYERS below.

# CJ wraps an approved link as https://<tracking host>/click-<pid>-<link id>?url=<destination>.
# The gate has to see through it, and for the right reason: the wrapper is not
# the thing being checked. Layers A to C are about whether the traveller lands
# on the correct Booking search, so they must run on the destination inside.
# Treating the wrapper as opaque would have marked 129 correct links as broken
# — which is what it did on the first build after attribution was wired.
CJ_CLICK_RE = re.compile(r"^https://www\.(jdoqocy|tkqlhce|dpbolvw|anrdoezrs|kqzyfj)\.(com|net)"
                         r"/click-(\d+)-(\d+)$")


def unwrap_affiliate(url):
    """(destination, programme link id) — link id is None for an unwrapped URL."""
    parts = urllib.parse.urlsplit(url)
    m = CJ_CLICK_RE.match("%s://%s%s" % (parts.scheme, parts.netloc, parts.path))
    if not m:
        return url, None
    inner = (urllib.parse.parse_qs(parts.query).get("url") or [""])[0]
    # A wrapper with nothing inside is worse than no wrapper: it earns
    # commission on a click that lands the traveller on Booking's homepage.
    return (inner or url), m.group(4)


KNOWN_ATTRIBUTION_PARAMS = ("aid", "label", "sid", "utm_source", "utm_campaign")

# Booking correctness is four independent layers, and only the first two can
# be decided by reading HTML. Conflating them is how "the URL is valid" turns
# into "the link works", which is not the same claim.
#
#   A  URL_STRUCTURE_PASS            decidable here
#   B  WANDROZ_QUERY_MATCH           decidable here
#   C  BOOKING_DESTINATION_VERIFIED  needs a live Booking response — never
#                                    auto-passed by this script
#   D  AFFILIATE_ATTRIBUTION_VERIFIED needs the actual Booking/CJ account —
#                                    never auto-passed by this script
BOOKING_LAYERS = ("URL_STRUCTURE_PASS", "WANDROZ_QUERY_MATCH",
                  "BOOKING_DESTINATION_VERIFIED", "AFFILIATE_ATTRIBUTION_VERIFIED")

# Destination-mapping classes. Everything this script can see lands in
# UNVERIFIED at best; EXACT_AREA and TRAVELLER_ALIAS may only be set by a
# human or by a future live-checking layer, and are read from an optional
# reviewed ledger rather than inferred.
DEST_CLASSES = ("EXACT_AREA", "TRAVELLER_ALIAS", "CITY_FALLBACK", "UNVERIFIED", "FAIL")
DEST_LEDGER = os.path.join(BASE_DIR, "data_zones", "booking_destinations.json")

TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r'href="([^"]+)"')
CANON_RE = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
BADGE_RE = re.compile(r'class="badge (green|yellow|red|grey)"')
ZONES_RE = re.compile(r"var ZONES\s*=\s*(\[.*?\]);\s*$", re.M | re.S)
TOGGLE_RE = re.compile(r"var SHOW_TOGGLE\s*=\s*(true|false)")
BOOKING_RE = re.compile(r'href="(https?://[^"]*booking\.com[^"]*)"')
SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)
# A city claiming Level 2 press research about its own rating. Deliberately a
# positive-claim pattern: official pages mention press research only to deny it.
RESEARCH_CLAIM_RE = re.compile(
    r"(Level 2 approach|press research per (zone|area|Municipalit))", re.I)
# The correction component specifically: a mailto whose subject is a Wandroz
# correction. Both templates that emit it (borough.html:79,
# neighbourhood.html:93) build the subject as "Wandroz correction: <area>",
# so this matches the component rather than every address on the page.
CORRECTION_MAILTO_RE = re.compile(
    r'mailto:([\w.+-]+@[\w.-]+\.\w+)\?subject=Wandroz(?:%20|\+| )correction', re.I)


class Findings:
    def __init__(self):
        self.rows = []

    def add(self, severity, category, check, target, message):
        self.rows.append({
            "severity": severity, "category": category,
            "check": check, "target": target, "message": message,
        })

    def fail(self, *a):
        self.add("FAIL", *a)

    def warn(self, *a):
        self.add("WARN", *a)

    @property
    def failures(self):
        return [r for r in self.rows if r["severity"] == "FAIL"]

    @property
    def warnings(self):
        return [r for r in self.rows if r["severity"] == "WARN"]


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _fold(s):
    """Accent- and case-insensitive form, for comparing place names.

    Booking destinations are written ASCII ("Krakow, Poland") while the city
    label carries its diacritics ("Krak\u00f3w"). A raw substring test made 19
    Krak\u00f3w zones look ambiguous when nothing was wrong with them — a checker
    bug, not a site issue, and exactly the kind of noise that trains people to
    ignore warnings.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "")
        if not unicodedata.combining(c)
    ).casefold()


def load_zone_source(key):
    path = os.path.join(BASE_DIR, "data_zones", "%s.json" % key)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def registry(F):
    reg = getattr(BS, "CITY_REGISTRY", None)
    if reg:
        return {k: (v["data_key"], v["scheme"]) for k, v in reg.items()}
    F.warn("INVENTORY", "canonical-registry", "build_site.py",
           "no CITY_REGISTRY in build_site.py; QA is using its own fallback table. "
           "Move the registry into the generator so slug/scheme/data-key live in one place.")
    return dict(FALLBACK_REGISTRY)


def zone_page_path(dist, city, slug, scheme):
    if scheme == "nested":
        return os.path.join(dist, city, slug, "index.html")
    return os.path.join(dist, city, "%s.html" % slug)


def zone_page_url(city, slug, scheme):
    if scheme == "nested":
        return "/%s/%s/" % (city, slug)
    return "/%s/%s.html" % (city, slug)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_inventory(dist, reg, F):
    """Expected cities exist, and every source zone produced a page."""
    expected = {u.rstrip("/").rsplit("/", 1)[-1]
                for u in (c["url"] for c in BS.CITY_LINKS)}
    for slug in sorted(expected):
        hub = os.path.join(dist, slug, "index.html")
        if not os.path.isfile(hub):
            F.fail("INVENTORY", "city-hub-exists", slug,
                   "CITY_LINKS advertises /%s/ but %s does not exist" % (slug, hub))

    known = set(reg) | {LONDON_SLUG}
    for slug in sorted(expected - known):
        F.fail("INVENTORY", "city-registered", slug,
               "city is in CITY_LINKS but has no registry entry, so QA cannot audit its zones")
    for slug in sorted(known - expected):
        F.fail("INVENTORY", "city-registered", slug,
               "city is registered but absent from CITY_LINKS, so it is unreachable from the nav")

    counts = {}
    for city, (key, scheme) in sorted(reg.items()):
        src = load_zone_source(key)
        if src is None:
            F.fail("INVENTORY", "zone-source-exists", city,
                   "no pipeline/data_zones/%s.json — this city cannot be rebuilt from source" % key)
            continue
        zones = src.get("zones", [])
        counts[city] = len(zones)
        for z in zones:
            page = zone_page_path(dist, city, z["slug"], scheme)
            if not os.path.isfile(page):
                F.fail("INVENTORY", "zone-page-generated", "%s/%s" % (city, z["slug"]),
                       "zone is in source but no page was generated at %s"
                       % os.path.relpath(page, dist))

        generated = set()
        city_dir = os.path.join(dist, city)
        if os.path.isdir(city_dir):
            for entry in os.listdir(city_dir):
                full = os.path.join(city_dir, entry)
                if scheme == "flat" and entry.endswith(".html") and entry != "index.html":
                    generated.add(entry[:-5])
                elif scheme == "nested" and os.path.isdir(full):
                    generated.add(entry)
        for orphan in sorted(generated - {z["slug"] for z in zones}):
            F.fail("INVENTORY", "no-orphan-pages", "%s/%s" % (city, orphan),
                   "page exists in the build but has no zone in source")
    return counts


def check_slug_collisions(reg, F):
    for city, (key, _scheme) in sorted(reg.items()):
        src = load_zone_source(key)
        if not src:
            continue
        for slug, n in Counter(z["slug"] for z in src.get("zones", [])).items():
            if n > 1:
                F.fail("MAP", "slug-collision", "%s/%s" % (city, slug),
                       "%d zones share this slug; pages would overwrite each other" % n)
        for name, n in Counter(z["name"] for z in src.get("zones", [])).items():
            if n > 1:
                F.warn("MAP", "duplicate-zone-name", "%s/%s" % (city, name),
                       "%d zones share this display name" % n)


def check_map_integrity(dist, reg, F):
    """The hub's map polygons and the zone pages must describe one reality."""
    for city, (key, scheme) in sorted(reg.items()):
        hub = os.path.join(dist, city, "index.html")
        src = load_zone_source(key)
        if not os.path.isfile(hub) or not src:
            continue
        html = read(hub)
        m = ZONES_RE.search(html)
        if not m:
            F.fail("MAP", "hub-has-zones", city, "hub page has no `var ZONES` map data")
            continue
        try:
            map_zones = json.loads(m.group(1))
        except ValueError as exc:
            F.fail("MAP", "hub-zones-parse", city, "`var ZONES` is not valid JSON: %s" % exc)
            continue

        src_by_slug = {z["slug"]: z for z in src.get("zones", [])}
        map_by_slug = {z.get("slug"): z for z in map_zones}
        for slug in sorted(set(src_by_slug) - set(map_by_slug)):
            F.fail("MAP", "polygon-for-every-zone", "%s/%s" % (city, slug),
                   "zone has a page but no polygon on the city map")
        for slug in sorted(set(map_by_slug) - set(src_by_slug)):
            F.fail("MAP", "page-for-every-polygon", "%s/%s" % (city, slug),
                   "map shows a polygon with no corresponding zone in source")

        # Rating parity: the map and the detail page must agree.
        for slug, z in sorted(src_by_slug.items()):
            mz = map_by_slug.get(slug)
            if not mz:
                continue
            for field in ("day", "night"):
                if z.get(field) not in VALID_TONES:
                    F.fail("MAP", "valid-tone", "%s/%s" % (city, slug),
                           "%s=%r is not one of %s" % (field, z.get(field), sorted(VALID_TONES)))
                elif mz.get(field) != z.get(field):
                    F.fail("MAP", "rating-parity", "%s/%s" % (city, slug),
                           "map says %s=%s, source says %s=%s"
                           % (field, mz.get(field), field, z.get(field)))

        # Badge count is a CITY-level decision driven by SHOW_TOGGLE, never a
        # per-zone one. A city with any real day/night variation renders two
        # badges on EVERY zone page, uniform zones included.
        #
        # This distinction is not pedantic. Asserting the naive per-zone rule
        # (`day != night` → 2 badges) produces 55 false failures on Florence
        # alone — 55 uniform zones in a city whose SHOW_TOGGLE is true because
        # 19 other zones vary. Verified against the live site: Rome behaves
        # identically, Berlin (SHOW_TOGGLE=false) renders one badge everywhere.
        #
        # So the expected value is derived from the rendering rule the
        # generator actually uses, and the rule's own input is checked
        # separately below (SHOW_TOGGLE must agree with the source data).
        tm = TOGGLE_RE.search(html)
        if not tm:
            F.fail("MAP", "show-toggle-present", city, "hub page has no SHOW_TOGGLE flag")
            continue
        show_toggle = tm.group(1) == "true"
        expected_from_data = any(z["day"] != z["night"] for z in src.get("zones", []))
        if show_toggle != expected_from_data:
            F.fail("METHODOLOGY", "toggle-matches-data", city,
                   "SHOW_TOGGLE=%s but source data %s a real day/night split"
                   % (show_toggle, "has" if expected_from_data else "has no"))
        # One exception to the city-level rule: a zone the review found nothing
        # for carries a single "reviewed — no findings" badge, because there is
        # no day and night to split. Two identical badges there would dress an
        # absence of evidence up as a measurement.
        for slug in sorted(src_by_slug):
            page = zone_page_path(dist, city, slug, scheme)
            if not os.path.isfile(page):
                continue
            z = src_by_slug[slug]
            no_findings = z.get("day") == "grey" and z.get("night") == "grey"
            expected_badges = 1 if no_findings else (2 if show_toggle else 1)
            got = len(BADGE_RE.findall(read(page)))
            if got != expected_badges:
                F.fail("METHODOLOGY", "badge-count", "%s/%s" % (city, slug),
                       "expected %d badge(s) for SHOW_TOGGLE=%s, found %d"
                       % (expected_badges, show_toggle, got))


def check_navigation(dist, reg, F):
    """Every hub must offer the full canonical city list — no stale switchers."""
    expected = [(c["label"], c["url"].rstrip("/").rsplit("/", 1)[-1]) for c in BS.CITY_LINKS]
    for city in sorted(set(reg) | {LONDON_SLUG}):
        hub = os.path.join(dist, city, "index.html")
        if not os.path.isfile(hub):
            continue
        html = read(hub)
        missing = [label for label, slug in expected if "/%s/" % slug not in html]
        if missing:
            F.fail("NAVIGATION", "switcher-complete", city,
                   "city switcher is missing %d of %d cities: %s"
                   % (len(missing), len(expected), ", ".join(missing)))


def check_methodology(dist, reg, F):
    """Tier claims must match the tier, in both directions."""
    for city, (key, scheme) in sorted(reg.items()):
        meta = BS.CITY_METHODOLOGY.get(key) or BS.CITY_METHODOLOGY.get(city)
        if not meta:
            F.fail("METHODOLOGY", "tier-declared", city,
                   "no CITY_METHODOLOGY entry; FAQ, legend and homepage tag have nothing to derive from")
            continue
        tier = meta["tier"]
        src = load_zone_source(key)
        if not src:
            continue
        for z in src.get("zones", []):
            page = zone_page_path(dist, city, z["slug"], scheme)
            if not os.path.isfile(page):
                continue
            text = TAG_RE.sub(" ", read(page))
            target = "%s/%s" % (city, z["slug"])

            # The evidence tag must match the city's declared tier. Read the
            # expected label from the generator's own EVIDENCE_TAG map rather
            # than restating it here, so the label and the assertion cannot
            # drift apart — and fail if the tag is missing entirely, which is
            # how it silently vanished from 1,053 pages.
            expected_tag = getattr(BS, "EVIDENCE_TAG", {}).get(tier)
            if expected_tag:
                present = [lbl for lbl in getattr(BS, "EVIDENCE_TAG", {}).values()
                           if lbl in text]
                if not present:
                    F.fail("METHODOLOGY", "evidence-tag-present", target,
                           "no evidence tag on the page; expected %r for tier %s"
                           % (expected_tag, tier))
                elif expected_tag not in present:
                    F.fail("METHODOLOGY", "evidence-tag-matches-tier", target,
                           "evidence tag is %r but tier %s requires %r"
                           % (present[0], tier, expected_tag))

            if tier == BS.RESEARCH_BASED and re.search(
                    r"official (crime|police) statistics for this", text, re.I):
                F.fail("METHODOLOGY", "research-page-not-claiming-official", target,
                       "research-based page claims official crime statistics")

            # Polarity matters. Official-statistics pages legitimately mention
            # press research in order to DENY it — "not a qualitative guess or
            # press research". A bare substring test fired on all 398
            # OFFICIAL_SNAPSHOT pages on the first CI run, which is a defect in
            # the assertion, not in the site. So match the positive claim
            # instead: the Level 2 self-description that only a research-based
            # city should carry.
            if tier == BS.OFFICIAL_SNAPSHOT and RESEARCH_CLAIM_RE.search(text):
                F.fail("METHODOLOGY", "official-page-not-claiming-press", target,
                       "official-statistics page makes a Level 2 press-research claim "
                       "about its own rating")


# An area whose review reached no source may not carry a colour. This is the
# no-coverage rule, enforced rather than promised: the site said in writing
# that an absence of reporting is inconclusive while rating 175 such areas
# "calm — no particular concern".
NO_FINDINGS_RE = re.compile(
    r"no (specific|particular|notable|documented|dated|reported|significant|recent|quartier-specific|barri-specific)"
    r"|searches turned up no|turned up no|no coverage found|no news coverage"
    r"|nothing (specific|about crime)|no crime or safety reporting|little (or no )?(news|press) coverage", re.I)

# Did the review actually reach anything? Two ways to tell, in order of
# reliability: the "Sources checked" tail, when the text has one, and
# otherwise any sign of a real source in the prose — a domain, an outlet, an
# authority, a statistic, or a described report. The point of the check is to
# catch an area rated on nothing, not to police how the note is phrased, so
# anything that looks like a reached source counts.
SOURCES_TAIL_RE = re.compile(r"Sources? (?:checked|consulted)[:,]?\s*(.+)$", re.I | re.S)
EMPTY_TAIL_RE = re.compile(r"^\W*(no\b|none\b|not\b)", re.I)
SOURCE_REACHED_RE = re.compile(
    # The country list started western and the site did not stay there. Adding
    # Baltic, Balkan and Nordic cities without adding their adjectives made this
    # fire on texts that plainly name a source — Vilnius's Old Town cites LRT,
    # the national broadcaster, and was reported as having reached no source at
    # all. A check that cannot recognise a Lithuanian source is not stricter,
    # it is wrong in one direction.
    r"\b[a-z0-9][a-z0-9-]{2,}\.(com|it|es|cat|pt|fr|de|at|nl|be|cz|hu|pl|gr|ie|uk|eu|se|no|ch|dk|fi|"
    r"ee|lv|lt|hr|si|sk|ro|bg|rs|info|net|org)\b"
    r"|\b(local|national|italian|spanish|french|german|greek|dutch|portuguese|hungarian|polish|czech|scottish|"
    r"irish|austrian|catalan|lithuanian|latvian|estonian|croatian|slovenian|slovak|romanian|bulgarian|"
    r"serbian|finnish|danish|swedish|norwegian|belgian|swiss)\s+"
    r"(press|news|media|outlets?|reporting|coverage|journalism|broadcaster|newspapers?|daily)"
    r"|\b(press|news|media)\s+(coverage|reports?|reporting)\s+(found|located|describes|shows|documents)"
    r"|\b(reported|reports|coverage found|described|documented|recorded)\b.{0,40}\b(19|20)\d\d\b"
    r"|\b(19|20)\d\d\b.{0,60}\b(report|reported|data|figures|survey|statistics|cases|incidents|arrests|"
    r"operation|complaint|coverage)"
    r"|\bcrimes per 1,?000\b|\bper 1,?000 population\b"
    # A described, concrete event is a source reached, however it is worded.
    r"|\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19|20)\d\d\b"
    r"|\b(dismantled|investigated for|prosecut|convicted|arrested|arrests|raid|crackdown|seizure|"
    r"molotov|stabbing|shooting|brawl|altercation|mugging|snatching)\b"
    r"|\b(ayuntamiento|comune|municipio|city of|stadt|mairie|prefecture|prefettura|questura|police|polizia|"
    r"polizei|policie|mossos|garda|carabinieri|guardia civil|statistics|statistical|survey|census|"
    r"court of appeal|ministry|ministero|kantonspolizei|met police|police scotland|churchill support|datamap)\b",
    re.I)


def review_reached_a_source(text):
    m = SOURCES_TAIL_RE.search(text or "")
    if m:
        tail = m.group(1).strip()
        if not EMPTY_TAIL_RE.match(tail):
            return True
        # A tail that starts with "No ..." can still list something after it.
        rest = re.split(r"[;,]", tail)[1:]
        if any(part.strip() and not EMPTY_TAIL_RE.match(part.strip()) for part in rest):
            return True
        return False
    return bool(SOURCE_REACHED_RE.search(text or ""))


def check_no_coverage_rule(F):
    """An absence of reporting must be labelled as one, everywhere it is shown.

    The site promised in writing that an absence of negative coverage is
    inconclusive while rating 178 such areas "calm — no particular concern"
    with nothing to distinguish them from areas backed by named sources. The
    ratings stay; the distinction is now a field, and this is what keeps it
    honest — checked against the source data, so it holds for every city on a
    local-source assessment, present and future."""
    for key, meta in BS.CITY_METHODOLOGY.items():
        if meta["tier"] != BS.RESEARCH_BASED:
            continue
        src = load_zone_source(key)
        if not src:
            continue
        for z in src.get("zones", []):
            text = z.get("text") or ""
            if not NO_FINDINGS_RE.search(text):
                continue
            if review_reached_a_source(text):
                continue          # sources were reached and showed nothing adverse
            # Every area carries a colour — these are major cities and a map
            # that shrugs at a third of them is not useful. What the rule
            # enforces is that the colour never passes an empty search off as
            # a sourced finding: the area must be flagged no_findings, and
            # that flag is what the map, the badge and the FAQ disclose.
            if z.get("evidence") != "no_findings":
                F.fail("METHODOLOGY", "unflagged-absence", "%s/%s" % (key, z["slug"]),
                       "the review reached no source for this area, yet it is rated as if it had: "
                       "set evidence=no_findings so the rating discloses what it rests on")


def check_forbidden_copy(dist, F):
    for path, rel in walk_html(dist):
        text = TAG_RE.sub(" ", read(path))
        for phrase, why in FORBIDDEN_PHRASES + RETIRED_VOCABULARY:
            if phrase in text:
                F.fail("METHODOLOGY", "forbidden-copy", rel, "contains %r — %s" % (phrase, why))


def check_contact(dist, F):
    """Scoped to the correction-contact component, not to the whole page.

    Wandroz may legitimately grow other public addresses — support, privacy,
    partnerships — so "every address on the page must be the correction
    address" would be wrong the day one of those ships. The rule is narrower
    and survives that:

      1. the address in each *correction* mailto equals BS.CORRECTION_EMAIL.
         That constant remains the single source of truth for this function.
      2. no correction component carries an address we did not expect.
      3. separately and site-wide: a retired address must appear ZERO times
         anywhere in public output, in any context — not just in mailtos.
         This one is deliberately unscoped, because a leaked personal address
         is a defect wherever it appears.
    """
    canonical = BS.CORRECTION_EMAIL
    for path, rel in walk_html(dist):
        html = read(path)

        # (1) + (2) — the correction component only.
        for addr in sorted(set(CORRECTION_MAILTO_RE.findall(html))):
            if addr != canonical:
                F.fail("CONTACT", "correction-email-canonical", rel,
                       "correction link points at %r; BS.CORRECTION_EMAIL is %r"
                       % (addr, canonical))

        # (3) — retired addresses, anywhere on the page.
        for legacy in sorted(LEGACY_EMAILS):
            if legacy in html:
                F.fail("CONTACT", "no-legacy-email", rel,
                       "retired address %r appears in public output" % legacy)


def check_seo(dist, reg, F):
    titles = defaultdict(list)
    for path, rel in walk_html(dist):
        html = read(path)
        m = CANON_RE.search(html)
        expected = BS.SITE_URL + "/" + rel.replace(os.sep, "/").replace("index.html", "")
        expected = expected.rstrip("/") + ("/" if rel.endswith("index.html") else "")
        if not m:
            F.fail("SEO", "canonical-present", rel, "no rel=canonical link")
        elif m.group(1).rstrip("/") != expected.rstrip("/"):
            F.fail("SEO", "canonical-correct", rel,
                   "canonical is %r, expected %r" % (m.group(1), expected))
        t = TITLE_RE.search(html)
        if not t:
            F.fail("SEO", "title-present", rel, "no <title>")
        else:
            titles[t.group(1).strip()].append(rel)
    for title, pages in sorted(titles.items()):
        if len(pages) > 1:
            F.warn("SEO", "duplicate-title", pages[0],
                   "%d pages share the title %r" % (len(pages), title))

    sitemap = os.path.join(dist, "sitemap.xml")
    if not os.path.isfile(sitemap):
        F.fail("SEO", "sitemap-exists", "sitemap.xml", "no sitemap.xml in the build")
        return
    listed = {u.replace(BS.SITE_URL, "") or "/"
              for u in re.findall(r"<loc>([^<]+)</loc>", read(sitemap))}
    built = set()
    for _path, rel in walk_html(dist):
        url = "/" + rel.replace(os.sep, "/")
        built.add(url[:-len("index.html")] if url.endswith("index.html") else url)
    for url in sorted(built - listed):
        F.fail("SEO", "sitemap-complete", url, "page is built but missing from sitemap.xml")
    for url in sorted(listed - built):
        F.fail("SEO", "sitemap-no-phantoms", url, "sitemap lists a URL with no page behind it")


def check_links(dist, F):
    """Internal links must resolve to something the build actually produced.

    <script> blocks are stripped first. The city-map JS builds hrefs by string
    concatenation (`'<a href="' + z.url + '">'`), and a naive href scan reads
    `' + z.url + '` as a literal path and reports 27 broken links that do not
    exist. Those are template fragments, not links.
    """
    for path, rel in walk_html(dist):
        base = os.path.dirname(path)
        html = SCRIPT_RE.sub(" ", read(path))
        for href in set(HREF_RE.findall(html)):
            if "' +" in href or '" +' in href or "{{" in href:
                continue  # belt and braces: any templating that survived
            if href.startswith(("http://", "https://", "mailto:", "#", "tel:", "data:")):
                continue
            clean = href.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            if clean.startswith("/"):
                target = os.path.join(dist, clean.lstrip("/"))
            else:
                target = os.path.join(base, clean)
            if clean.endswith("/") or os.path.isdir(target):
                target = os.path.join(target, "index.html")
            if not os.path.exists(target):
                F.fail("LINKS", "internal-link-resolves", rel,
                       "link %r points at nothing (%s)" % (href, os.path.relpath(target, dist)))


def load_destination_ledger():
    """Human-reviewed destination verdicts, if any exist yet.

    Shape: {"<city>/<slug>": {"class": "EXACT_AREA", "checked": "2026-09-20",
                              "note": "Booking resolves this to the barrio"}}

    Nothing writes this file automatically. A class only appears here because
    a person opened the Booking search and looked, so the script can report
    verified coverage without ever inventing it.
    """
    if not os.path.isfile(DEST_LEDGER):
        return {}
    try:
        with open(DEST_LEDGER, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return {}


def check_booking(dist, reg, F, booking_rows):
    """Audit Booking CTAs across four independent layers.

    Layers A and B are decided here from the HTML. Layers C and D are NOT:
    a syntactically perfect URL whose `ss` matches our own source field still
    proves nothing about what Booking does with it, and the presence of an
    attribution parameter proves nothing about whether the account behind it
    is live. Both stay UNVERIFIED unless a reviewed ledger says otherwise.
    """
    ledger = load_destination_ledger()
    attribution_seen = Counter()
    checked_ctas = 0

    for city, (key, scheme) in sorted(reg.items()):
        src = load_zone_source(key)
        if not src:
            continue
        city_label = (src.get("label") or "").split(",")[0].strip()
        for z in src.get("zones", []):
            page = zone_page_path(dist, city, z["slug"], scheme)
            if not os.path.isfile(page):
                continue
            target = "%s/%s" % (city, z["slug"])
            urls = BOOKING_RE.findall(read(page))

            row = {
                "page": target,
                "url": urls[0] if urls else "",
                "ss": "",
                "scope": z.get("booking_scope", "area"),
                "source_query": z.get("query", ""),
                "URL_STRUCTURE_PASS": "FAIL",
                "WANDROZ_QUERY_MATCH": "FAIL",
                "BOOKING_DESTINATION_VERIFIED": "UNVERIFIED",
                "AFFILIATE_ATTRIBUTION_VERIFIED": "UNVERIFIED",
                "destination_class": "UNVERIFIED",
                "notes": "",
            }

            if not urls:
                row["notes"] = "no Booking CTA on the page"
                booking_rows.append(row)
                F.fail("BOOKING", "cta-present", target, "no Booking.com link on the zone page")
                continue
            if len(urls) > 1:
                F.warn("BOOKING", "single-cta", target, "%d Booking links on one page" % len(urls))

            url = urls[0]
            checked_ctas += 1
            url, cj_link_id = unwrap_affiliate(url)
            parts = urllib.parse.urlsplit(url)
            qs = urllib.parse.parse_qs(parts.query)
            ss = (qs.get("ss") or [""])[0]
            row["ss"] = ss

            # ---- Layer A: URL structure -------------------------------------
            structural = []
            if parts.scheme != "https":
                structural.append("not https")
            if not parts.path.endswith("searchresults.html"):
                structural.append("unexpected path %r" % parts.path)
            if not ss:
                structural.append("no `ss` destination")
            if " " in parts.query:
                structural.append("unencoded space in query string")
            if structural:
                row["notes"] = "; ".join(structural)
                F.fail("BOOKING", "url-structure", target, "%s: %s" % ("; ".join(structural), url))
            else:
                row["URL_STRUCTURE_PASS"] = "PASS"

            # ---- Layer B: does the URL carry OUR query verbatim? -------------
            # This is an internal-consistency check between the generated page
            # and data_zones. It says nothing about Booking.
            # The note under the button must match what the link really does.
            # A zone flagged booking_scope="city" searches the whole city —
            # Booking has no listing area for it — so a page promising "scoped
            # to this area (not the whole city)" would be stating something
            # verified to be false. Checked here so the copy and the flag
            # cannot drift apart later.
            page_html = read(page)
            scope = z.get("booking_scope", "area")
            claims_area = "not the whole city" in page_html
            says_city = "no separate search area for this neighbourhood" in page_html
            if scope == "city" and claims_area:
                F.fail("BOOKING", "scope-claim-matches-reality", target,
                       "booking_scope is 'city' but the page claims the link is scoped "
                       "to this area")
            if scope == "area" and says_city:
                F.fail("BOOKING", "scope-claim-matches-reality", target,
                       "booking_scope is 'area' but the page says Booking has no area "
                       "for this neighbourhood")

            if ss and ss == z.get("query"):
                row["WANDROZ_QUERY_MATCH"] = "PASS"
            elif ss:
                F.fail("BOOKING", "query-matches-source", target,
                       "Booking `ss`=%r but source query is %r" % (ss, z.get("query")))
                row["notes"] = (row["notes"] + "; " if row["notes"] else "") + "ss != source query"

            # ---- Layer C: destination — never auto-passed --------------------
            verdict = ledger.get(target, {})
            klass = verdict.get("class")
            if klass in DEST_CLASSES and klass not in ("UNVERIFIED",):
                row["destination_class"] = klass
                row["BOOKING_DESTINATION_VERIFIED"] = "PASS" if klass != "FAIL" else "FAIL"
                if klass == "FAIL":
                    F.fail("BOOKING", "destination-verified", target,
                           "reviewed and rejected: %s" % verdict.get("note", "no note"))
            else:
                row["BOOKING_DESTINATION_VERIFIED"] = "MANUAL_VERIFICATION_REQUIRED"
                if city_label and _fold(city_label) not in _fold(ss):
                    F.warn("BOOKING", "destination-ambiguity", target,
                           "`ss`=%r does not name %s — a generic or duplicated place name can "
                           "resolve to another city or country" % (ss, city_label))

            # ---- Layer D: attribution ---------------------------------------
            # A CJ click wrapper is attribution that has been confirmed on the
            # account side: the publisher id and the link id in it were issued
            # by an approved programme and cannot be invented. A bare parameter
            # still cannot be auto-passed, because anyone can add one.
            present = [p for p in KNOWN_ATTRIBUTION_PARAMS if p in qs]
            for p in present:
                attribution_seen[p] += 1
            if cj_link_id:
                attribution_seen["cj:" + cj_link_id] += 1
                row["AFFILIATE_ATTRIBUTION_VERIFIED"] = "PASS"
            else:
                row["AFFILIATE_ATTRIBUTION_VERIFIED"] = (
                    "NOT_ATTRIBUTED_BY_CURRENT_CODE" if not present
                    else "MANUAL_VERIFICATION_REQUIRED")
            if present:
                row["notes"] = (row["notes"] + "; " if row["notes"] else "") + \
                    "attribution params present: %s" % ",".join(present)

            booking_rows.append(row)

    # London's borough pages are generated by their own pipeline and were
    # outside this audit entirely — which is how 32 pages shipped with no
    # accommodation link at all and nothing said so. They are audited here on
    # the same layers, against the destination the London map uses.
    london_src = load_zone_source("london_boundaries") or {}
    london_q = {BS._canon(z["name"]): z.get("query", "")
                for z in london_src.get("zones", [])}
    scores_path = os.path.join(REPO_DIR, "data", "scores", "london.json")
    boroughs = []
    if os.path.isfile(scores_path):
        with open(scores_path) as f:
            boroughs = json.load(f).get("boroughs", [])
    for b in boroughs:
        page = os.path.join(dist, "london", "%s.html" % b["slug"])
        if not os.path.isfile(page):
            continue
        target = "london/%s" % b["slug"]
        urls = BOOKING_RE.findall(read(page))
        expected = london_q.get(BS._canon(b["borough"]), "")
        row = {"page": target, "url": urls[0] if urls else "", "ss": "",
               "scope": "area", "source_query": expected,
               "URL_STRUCTURE_PASS": "FAIL", "WANDROZ_QUERY_MATCH": "FAIL",
               "BOOKING_DESTINATION_VERIFIED": "MANUAL_VERIFICATION_REQUIRED",
               "AFFILIATE_ATTRIBUTION_VERIFIED": "UNVERIFIED",
               "destination_class": "UNVERIFIED", "notes": ""}
        if not urls:
            row["notes"] = "no Booking CTA on the page"
            booking_rows.append(row)
            F.fail("BOOKING", "cta-present", target, "no Booking.com link on the borough page")
            continue
        checked_ctas += 1
        # Same unwrapping as the main audit. London has no approved programme
        # today, so this changes nothing now — and stops the gate breaking the
        # day one covers the UK, instead of discovering it in a red release.
        london_url, london_cj = unwrap_affiliate(urls[0])
        parts = urllib.parse.urlsplit(london_url)
        qs = urllib.parse.parse_qs(parts.query)
        ss = (qs.get("ss") or [""])[0]
        row["ss"] = ss
        if parts.scheme == "https" and parts.path.endswith("searchresults.html") and ss:
            row["URL_STRUCTURE_PASS"] = "PASS"
        else:
            F.fail("BOOKING", "url-structure", target, urls[0])
        if ss and expected and ss == expected:
            row["WANDROZ_QUERY_MATCH"] = "PASS"
        elif ss:
            F.fail("BOOKING", "query-matches-source", target,
                   "borough page `ss`=%r but the London map uses %r" % (ss, expected))
        if "London" not in ss:
            F.warn("BOOKING", "destination-ambiguity", target,
                   "`ss`=%r does not name London" % ss)
        present = [p for p in KNOWN_ATTRIBUTION_PARAMS if p in qs]
        for p in present:
            attribution_seen[p] += 1
        if london_cj:
            attribution_seen["cj:" + london_cj] += 1
            row["AFFILIATE_ATTRIBUTION_VERIFIED"] = "PASS"
        else:
            row["AFFILIATE_ATTRIBUTION_VERIFIED"] = (
                "NOT_ATTRIBUTED_BY_CURRENT_CODE" if not present else "MANUAL_VERIFICATION_REQUIRED")
        booking_rows.append(row)

    # Duplicated destinations: distinct zones sending traffic to one search.
    by_ss = defaultdict(list)
    for row in booking_rows:
        if row["ss"]:
            by_ss[row["ss"]].append(row["page"])
    # Zones that deliberately share a parent district are not a defect: Paris's
    # four quartiers per arrondissement point at the arrondissement on purpose,
    # because Booking has no quartier. The warning is for accidental sharing.
    deliberate = {r["page"] for r in booking_rows if r.get("scope") in ("parent", "city")}
    for ss, pages in sorted(by_ss.items()):
        if len(pages) > 1 and all(p in deliberate for p in pages):
            continue
        if len(pages) > 1:
            for p in pages:
                for row in booking_rows:
                    if row["page"] == p and row["destination_class"] == "UNVERIFIED":
                        row["notes"] = (row["notes"] + "; " if row["notes"] else "") + \
                            "destination shared with %d other zone(s)" % (len(pages) - 1)
            F.warn("BOOKING", "shared-destination", pages[0],
                   "%d zones share destination %r: %s — check whether Booking can distinguish "
                   "them at all" % (len(pages), urllib.parse.unquote(ss), ", ".join(sorted(pages))))

    # Attribution is a site-wide fact, reported once.
    unattributed = sum(1 for r in booking_rows
                       if r["AFFILIATE_ATTRIBUTION_VERIFIED"] == "NOT_ATTRIBUTED_BY_CURRENT_CODE")
    if unattributed:
        F.warn("BOOKING", "affiliate-attribution", "site-wide",
               "%d of %d Booking CTAs carry no recognised attribution parameter (%s). "
               "Absence is conclusive; presence would still need account-side confirmation. "
               "Do not add parameters without the real account's authorised link format."
               % (unattributed, checked_ctas, ", ".join(KNOWN_ATTRIBUTION_PARAMS)))
    if attribution_seen:
        # Two different things end up in this counter and they do not deserve
        # the same sentence. A CJ click wrapper carries a publisher id and a
        # link id issued by an approved programme: that IS the account-side
        # confirmation, and it cannot be fabricated. A bare aid= or sid= can be
        # typed by anyone, so it stays unverified no matter how plausible.
        cj = {k: v for k, v in attribution_seen.items() if k.startswith("cj:")}
        bare = {k: v for k, v in attribution_seen.items() if not k.startswith("cj:")}
        if cj:
            F.warn("BOOKING", "affiliate-attribution", "site-wide",
                   "CJ click wrappers in use, issued by an approved programme: %s. "
                   "These pass layer D. Every other city keeps an unattributed "
                   "Booking link, which is correct until its region is approved."
                   % dict(cj))
        if bare:
            F.warn("BOOKING", "affiliate-attribution", "site-wide",
                   "bare attribution parameters found in use: %s — these stay "
                   "MANUAL_VERIFICATION_REQUIRED, since anyone can add one"
                   % dict(bare))


def walk_html(dist):
    for root, _dirs, files in os.walk(dist):
        for name in sorted(files):
            if name.endswith(".html"):
                path = os.path.join(root, name)
                yield path, os.path.relpath(path, dist)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def booking_layer_summary(booking_rows):
    """Roll the four layers up, keeping them strictly separate."""
    summary = {}
    for layer in BOOKING_LAYERS:
        summary[layer] = dict(Counter(r[layer] for r in booking_rows))
    summary["destination_class"] = dict(Counter(r["destination_class"] for r in booking_rows))
    summary["ctas_total"] = len(booking_rows)
    return summary


def write_reports(F, counts, dist, report_dir, booking_rows, reg):
    os.makedirs(report_dir, exist_ok=True)

    expected_cities = {u.rstrip("/").rsplit("/", 1)[-1] for u in (c["url"] for c in BS.CITY_LINKS)}
    built_cities = {slug for slug in expected_cities
                    if os.path.isfile(os.path.join(dist, slug, "index.html"))}
    nav_bad = sorted({r["target"] for r in F.rows if r["check"] == "switcher-complete"})

    payload = {
        "dist": os.path.abspath(dist),
        "pages_audited": sum(1 for _ in walk_html(dist)),
        "cities_expected": len(expected_cities),
        "cities_built": len(built_cities),
        "cities_missing": sorted(expected_cities - built_cities),
        "cities_audited": len(counts),
        "zone_counts": counts,
        "zones_in_source": sum(counts.values()),
        "florence": {
            "expected": 75,
            # Count pages that actually exist on disk. The first CI run
            # reported "generated 74" for a city the build had not produced at
            # all, because this read the SOURCE zone count. Counting source as
            # output is precisely the confusion this whole milestone exists to
            # remove, so it is counted from the filesystem now.
            "generated": sum(1 for _p, rel in walk_html(dist)
                             if rel.split(os.sep)[0] == "firenze"),
        },
        "navigation": {
            "expected_cities_per_hub": len(BS.CITY_LINKS),
            "hubs_with_incomplete_switcher": nav_bad,
        },
        "booking": booking_layer_summary(booking_rows),
        "correction_email": {
            "canonical": BS.CORRECTION_EMAIL,
            "legacy_addresses_checked": sorted(LEGACY_EMAILS),
        },
        "totals": {"failures": len(F.failures), "warnings": len(F.warnings)},
        "findings": F.rows,
    }

    with open(os.path.join(report_dir, "booking_audit.csv"), "w", encoding="utf-8", newline="") as f:
        cols = ["page", "url", "ss", "scope", "source_query"] + list(BOOKING_LAYERS) + \
               ["destination_class", "notes"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(booking_rows)
    with open(os.path.join(report_dir, "qa_report.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(os.path.join(report_dir, "qa_findings.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["severity", "category", "check", "target", "message"])
        w.writeheader()
        w.writerows(F.rows)

    with open(os.path.join(report_dir, "qa_inventory.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["city", "zones_in_source"])
        for city, n in sorted(counts.items()):
            w.writerow([city, n])
    return payload


def summarise(F, payload):
    print("=" * 72)
    print("WANDROZ FULL-SITE QA")
    print("=" * 72)
    print("pages audited        %d" % payload["pages_audited"])
    print("zones in source      %d" % payload["zones_in_source"])
    print("cities  expected %d / built %d%s"
          % (payload["cities_expected"], payload["cities_built"],
             "" if not payload["cities_missing"]
             else "   MISSING: " + ", ".join(payload["cities_missing"])))
    print("florence expected %d / generated %d"
          % (payload["florence"]["expected"], payload["florence"]["generated"]))
    nav = payload["navigation"]
    print("nav      expected %d cities per hub; hubs incomplete: %d%s"
          % (nav["expected_cities_per_hub"], len(nav["hubs_with_incomplete_switcher"]),
             "" if not nav["hubs_with_incomplete_switcher"]
             else "  (" + ", ".join(nav["hubs_with_incomplete_switcher"]) + ")"))
    print("email    canonical %s" % payload["correction_email"]["canonical"])
    print()
    print("BOOKING — four independent layers (C and D are never auto-passed)")
    for layer in BOOKING_LAYERS:
        states = payload["booking"][layer]
        print("  %-32s %s" % (layer, ", ".join("%s=%d" % kv for kv in sorted(states.items()))))
    print("  %-32s %s" % ("destination_class",
          ", ".join("%s=%d" % kv for kv in sorted(payload["booking"]["destination_class"].items()))))
    print()
    by_cat = Counter((r["severity"], r["category"]) for r in F.rows)
    if by_cat:
        print("%-10s %-14s %s" % ("SEVERITY", "CATEGORY", "COUNT"))
        for (sev, cat), n in sorted(by_cat.items()):
            print("%-10s %-14s %d" % (sev, cat, n))
        print()
    for row in F.failures[:60]:
        print("FAIL [%s/%s] %s — %s" % (row["category"], row["check"], row["target"], row["message"]))
    if len(F.failures) > 60:
        print("... and %d more failures (see qa_findings.csv)" % (len(F.failures) - 60))
    if F.failures and F.warnings:
        print()
    for row in F.warnings[:25]:
        print("WARN [%s/%s] %s — %s" % (row["category"], row["check"], row["target"], row["message"]))
    if len(F.warnings) > 25:
        print("... and %d more warnings (see qa_findings.csv)" % (len(F.warnings) - 25))
    print()
    print("RESULT: %d failure(s), %d warning(s)" % (len(F.failures), len(F.warnings)))


def main():
    ap = argparse.ArgumentParser(description="Wandroz full-site QA gate")
    ap.add_argument("--dist", default=os.path.join(REPO_DIR, "dist"),
                    help="directory to audit (default: dist/)")
    ap.add_argument("--report-dir", default=os.path.join(REPO_DIR, "qa_output"))
    ap.add_argument("--warnings-as-errors", action="store_true")
    args = ap.parse_args()

    dist = os.path.abspath(args.dist)
    if not os.path.isdir(dist):
        print("FATAL: %s is not a directory" % dist)
        return 2

    F = Findings()
    reg = registry(F)

    counts = check_inventory(dist, reg, F)
    check_slug_collisions(reg, F)
    check_map_integrity(dist, reg, F)
    check_navigation(dist, reg, F)
    check_methodology(dist, reg, F)
    check_forbidden_copy(dist, F)
    check_no_coverage_rule(F)
    check_contact(dist, F)
    check_seo(dist, reg, F)
    check_links(dist, F)
    booking_rows = []
    check_booking(dist, reg, F, booking_rows)

    payload = write_reports(F, counts, dist, args.report_dir, booking_rows, reg)
    summarise(F, payload)
    print("reports written to %s" % os.path.relpath(args.report_dir, REPO_DIR))

    if F.failures:
        return 1
    if args.warnings_as_errors and F.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
