"""
Does an area's colour agree with the words printed underneath it?

WHY THIS EXISTS
    Zurich's Hard was rated amber by day while its own published text said
    "calm by day". Werd, Gewerbeschule, Saatlen and Hirzenbach said the same
    thing and carried the same amber. A reader sees a colour and a sentence
    that contradict each other, and there is no way to tell which one to
    believe.

    Nothing caught it. qa_full_site checks that a page is well-formed and
    honest about its sources; it never reads the prose against the colour.
    verify_reproducible checks that source and build agree. Both were green
    while five pages argued with themselves.

WHAT IT LOOKS FOR
    One contradiction, in one direction:

      SAYS CALM, RATED CAUTION   the text says the area is calm/safe/fine at a
                                 given time of day, and that half of the rating
                                 is amber or red.

    It reads the same sentence a visitor reads, so a match is a real
    contradiction on a real page, not a modelling opinion.

WHY NOT THE OTHER DIRECTION
    The first version of this also looked for the reverse — prose naming
    trouble under a green rating — and it was useless. It fired 60 times and
    every one was a negation: "no reports of no-go conditions", "listicles do
    not name it", "outside the areas named in reporting on drug violence".
    Our texts describe an absence of findings by naming the thing that was
    absent, so keyword-matching danger words finds our safest areas. Detecting
    it properly needs to read negation, which a regex cannot do; it is left to
    the human review instead of shipped as a check that cries wolf.

WHAT IT IS NOT
    It is not a judge of whether a rating is right. A rating can be wrong and
    perfectly consistent with its own prose, and this will say nothing. It
    only catches the page disagreeing with itself — which is the failure a
    reader can see without knowing anything about the city.

USAGE
    python3 pipeline/check_text_vs_rating.py
    python3 pipeline/check_text_vs_rating.py --city zurigo
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as BS

# The reassuring word and the time of day have to sit in the SAME clause. The
# first version allowed 40 characters of anything between them, and it happily
# read "calm; the large, unlit forest interior after dark" as a claim that the
# place is calm after dark. So the gap may not contain a full stop, a comma, a
# semicolon, or a contrast word — the exact places where the sentence turns
# around and starts saying the opposite.
GAP = r"(?:[^.,;:!?]|\b(?:and|with)\b)"
NOT_CONTRAST = r"(?!.*\b(?:but|though|however|except|although|unless)\b)"
CALM_DAY = re.compile(
    r"\b(calm|safe|quiet|fine|relaxed|unremarkable)\b" + NOT_CONTRAST + GAP + r"{0,40}?"
    r"\b(by day|during the day|in the daytime|in daylight|daytime)\b", re.I)
CALM_NIGHT = re.compile(
    r"\b(calm|safe|quiet|fine|relaxed)\b" + NOT_CONTRAST + GAP + r"{0,40}?"
    r"\b(at night|after dark|in the evening)\b", re.I)
# Used only to suppress a calm-at-night match when the same text also warns
# about the night; never on its own (see WHY NOT THE OTHER DIRECTION).
TROUBLE = re.compile(
    r"\b(avoid after dark|tense at night|worse at night|quieter and less)\b", re.I)


def context(text, m):
    """The whole sentence the match sits in — judging a contradiction needs the
    clause that follows it, not the four matched words. Nobody knows every
    neighbourhood in the world; the output has to carry its own evidence."""
    start = max(text.rfind(".", 0, m.start()) + 1, 0)
    end = text.find(".", m.end())
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())


def zones_of(city_key):
    p = os.path.join(BS.ZONES_DIR, "%s.json" % city_key)
    if not os.path.isfile(p):
        return []
    return json.load(io.open(p, encoding="utf-8")).get("zones", [])


def main(only):
    findings = []
    checked = 0
    for city_key, url_slug, label, flat in BS.mapped_cities():
        if only and city_key != only:
            continue
        for z in zones_of(city_key):
            text = (z.get("text") or "").strip()
            if not text:
                continue
            checked += 1
            day, night = z.get("day"), z.get("night")
            # Only look at the sentence that talks about that time of day,
            # so "calm by day, tense at night" does not fire on the night half.
            if CALM_DAY.search(text) and day in ("yellow", "red"):
                findings.append((city_key, z["name"], "says calm BY DAY, rated %s by day" % day,
                                 context(text, CALM_DAY.search(text))))
            if CALM_NIGHT.search(text) and night in ("yellow", "red") and not TROUBLE.search(text):
                findings.append((city_key, z["name"], "says calm AT NIGHT, rated %s at night" % night,
                                 context(text, CALM_NIGHT.search(text))))

    print("Read %d area texts against their own ratings.\n" % checked)
    if not findings:
        print("OK: no page contradicts itself.")
        return 0
    by_city = {}
    for c, n, why, quote in findings:
        by_city.setdefault(c, []).append((n, why, quote))
    print("%d contradiction(s) in %d cities:\n" % (len(findings), len(by_city)))
    for c in sorted(by_city):
        print("%s" % c)
        for n, why, quote in by_city[c]:
            print("   %-32s %s" % (n[:32], why))
            print("      the text says: “%s”" % " ".join(quote.split()))
    print("\nEach of these is a page arguing with itself. Either the colour is")
    print("wrong or the sentence is — a reader cannot tell which, and that is")
    print("the problem regardless of which one gets fixed.")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    a = ap.parse_args()
    sys.exit(main(a.city))
