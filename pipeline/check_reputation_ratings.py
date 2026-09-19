"""
Which areas are rated cautious on nothing but a reputation?

WHY THIS EXISTS
    Zurich's Saatlen and Hirzenbach were amber. The whole justification, in the
    published text, was "shares some of the district's reputation for occasional
    issues". No incident, no date, no source. Meanwhile the one hard figure that
    reaches those streets — Kantonspolizei Zürich's burglary rate — says their
    district records 2.9 per 1,000 residents, the lowest of Zurich's twelve.
    Schwamendingen-Mitte was worse: amber by day and RED at night, the strongest
    claim this site makes about anywhere, resting on "repeatedly described by
    Swiss media as one of Zurich's more troubled areas".

    A reputation is not evidence. It is often just an old reputation, and the
    places that carry them are usually the poorer end of a city. Printing one as
    a colour launders hearsay into something that looks measured.

WHAT IT LOOKS FOR
    An area rated amber or red where the published text offers no anchor a
    reader could check — no year, no named source, no counted thing, no named
    place — and instead leans on reputation words: reputation, known for,
    described as, considered, perceived, has a name for, said to be.

    An anchor is any of: a four-digit year, a percentage or a count, a named
    institution or publication, or a named street, square, park or station.
    Those are the things that let a reader go and look. Reputation words are the
    things that stop them.

WHAT IT IS NOT
    It does not say the rating is wrong. Plenty of these areas may deserve the
    colour; the objection is that the page gives the reader no way to tell. The
    fix is either a source or a different colour, and which one is a judgment
    call this script does not make.

USAGE
    python3 pipeline/check_reputation_ratings.py
    python3 pipeline/check_reputation_ratings.py --city zurigo
    python3 pipeline/check_reputation_ratings.py --quiet   # counts per city only
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import published

REPUTATION = re.compile(
    # "described as" is written as a gap, not a fixed phrase: the sentence that
    # got past the first version of this was "repeatedly described BY SWISS
    # MEDIA as one of Zurich's more troubled areas", and naming an unnamed
    # medium is not a source.
    r"\b(reputation|reputedly|notorious|known for|considered|perceived|perception|"
    r"said to be|has a name for|widely regarded|seen as|a name as|image as)\b"
    r"|\bdescribed\b[^.]{0,40}?\bas\b"
    r"|\bregarded\b[^.]{0,40}?\bas\b", re.I)

# Things a reader can go and check.
YEAR = re.compile(r"\b(19|20)\d{2}\b")
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|per\s+1,?000|per\s+100,?000|incidents?|"
                    r"offences?|crimes?|arrests?|reports?|cases?)\b", re.I)
# A named source: two capitalised words in a row, or a known-source keyword.
SOURCE = re.compile(
    r"\b(police|polizei|policía|polizia|politie|politi|prefettura|questura|"
    r"ministry|kommune|comune|ayuntamiento|statistics|statistik|istat|ine|insee|"
    r"cbs|bra|bfs|observatory|osservatorio|council|municipality|court|prosecutor)\b",
    re.I)
# A named place — the proper noun, not the bare noun. "the station area" tells
# a reader nothing; "Zürich HB" or "Piazza Garibaldi" tells them where to look.
# So the word has to sit next to a capitalised name, on either side, or be a
# compound name in its own right (Langstrasse, Klybeckstrasse).
PLACE = re.compile(
    r"\b[A-ZÄÖÜÀ-Þ][\w'’-]+\s+(?:Street|Road|Avenue|Square|Park|Station|Bridge|"
    r"Gardens?|Market|Quay|Hill|Lane|Beach)\b"
    # Romance-language place types are routinely lowercase in running prose
    # ("via Val Cannuta") and routinely carry a lowercase connector before the
    # name ("Parco di Trenno", "Campo de' Fiori"). Missing those made the first
    # run report six Rome and Milan areas as unsourced when every one of them
    # cited documented press coverage of a named place.
    r"|(?i:\b(?:via|piazza|piazzale|corso|largo|viale|campo|rue|place|boulevard|"
    r"avenue|calle|plaza|carrer|plaça|praça|plein|platz|bahnhof|stazione|gare|"
    r"parco|parc|park|ponte|puente|pont)\s+"
    r"(?:(?:di|del|della|dei|delle|de|du|des|la|le|el|van|der)['’ ]\s*)?)"
    r"[A-ZÄÖÜÀ-Þ][\w'’-]+"
    r"|\b[A-ZÄÖÜÀ-Þ][\wä öüß'’-]{2,}?(?:strasse|straße|platz|gasse|markt|brücke|"
    r"bahnhof|kade|gracht|plein|torg|gata|vej)\b")


def anchors(text):
    """What in this text could a reader actually go and verify?"""
    found = []
    if YEAR.search(text):
        found.append("a year")
    if NUMBER.search(text):
        found.append("a figure")
    if SOURCE.search(text):
        found.append("a named source")
    if PLACE.search(text):
        found.append("a named place")
    return found


def main(only, quiet):
    findings = []
    cautious = 0
    cities = 0
    # Built pages, not the city registry: the registry has no London, and a
    # check that cannot see 33 boroughs reporting "all clear" is worse than
    # no check at all.
    for city_key, zones in published.published_cities():
        if only and city_key != only:
            continue
        cities += 1
        for z in zones:
            if z.get("day") not in ("yellow", "red") and z.get("night") not in ("yellow", "red"):
                continue
            cautious += 1
            text = (z.get("text") or "").strip()
            m = REPUTATION.search(text)
            if not m:
                continue
            if anchors(text):
                continue
            findings.append((city_key, z["name"], z.get("day"), z.get("night"),
                             " ".join(text.split())))

    print("Read %d areas rated amber or red, across %d published cities.\n"
          % (cautious, cities))
    if not findings:
        print("OK: every cautious rating offers the reader something to check.")
        return 0

    by_city = {}
    for f in findings:
        by_city.setdefault(f[0], []).append(f)

    print("%d rated on reputation alone, in %d cities:\n" % (len(findings), len(by_city)))
    for c in sorted(by_city, key=lambda k: -len(by_city[k])):
        rows = by_city[c]
        print("%s  (%d)" % (c, len(rows)))
        if quiet:
            continue
        for _c, name, day, night, text in rows:
            print("   %-28s %s/%s" % (name[:28], day, night))
            print("      %s" % (text[:220] + ("…" if len(text) > 220 else "")))
        print()

    print("Each of these asks a reader to accept a caution on trust. The fix is a")
    print("source or a different colour — not both left as they are.")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.city, a.quiet))
