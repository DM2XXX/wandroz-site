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
import published

# The reassuring word and the time of day have to sit in the SAME clause. The
# first version allowed 40 characters of anything between them, and it happily
# read "calm; the large, unlit forest interior after dark" as a claim that the
# place is calm after dark. So the gap may not contain a full stop, a comma, a
# semicolon, or a contrast word — the exact places where the sentence turns
# around and starts saying the opposite.
GAP = r"(?:[^.,;:!?]|\b(?:and|with)\b)"
# "best avoided" turns a sentence around as firmly as "but" does. Paris's
# Pont-de-Flandre reads "The Bassin de la Villette waterfront itself is popular
# and generally fine by day; the Riquet-Stalingrad blocks are best avoided,
# especially after dark" — a page being more precise than its own colour, not
# a page arguing with itself, and it was reported three times before this.
NOT_CONTRAST = (r"(?!.*\b(?:but|though|however|except|although|unless"
                r"|best avoided|steer clear)\b)")
# A calm claim narrowed to one part of the area is not a claim about the area.
# "The waterfront ITSELF is fine by day" says the opposite of "the quartier is
# fine by day", and only the second contradicts an amber quartier. Scoped to
# the clause before the calm word, so an "itself" elsewhere in a long text
# cannot silence a real contradiction.
SCOPED = re.compile(r"\bitself\b[^.;!?]{0,40}$", re.I)
CALM_DAY = re.compile(
    r"\b(calm|safe|quiet|fine|relaxed|unremarkable)\b" + NOT_CONTRAST + GAP + r"{0,40}?"
    # "through the day" was missing until a test case written from Zurich's own
    # Hard text failed to fire. It is the phrasing several of these texts
    # actually use, so the check had a hole exactly where it was aimed.
    r"\b(by day|during the day|through the day|in the day|in the daytime"
    r"|in daylight|daytime)\b", re.I)
CALM_NIGHT = re.compile(
    r"\b(calm|safe|quiet|fine|relaxed)\b" + NOT_CONTRAST + GAP + r"{0,40}?"
    r"\b(at night|after dark|in the evening)\b", re.I)
# Used only to suppress a calm-at-night match when the same text also warns
# about the night; never on its own (see WHY NOT THE OTHER DIRECTION).
TROUBLE = re.compile(
    r"\b(avoid after dark|tense at night|worse at night|quieter and less)\b", re.I)


def scoped_to_a_part(text, m):
    """True when the calm word's own clause narrows the claim to one part of
    the area, e.g. "the waterfront itself is fine by day"."""
    start = max(text.rfind(".", 0, m.start()) + 1,
                text.rfind(";", 0, m.start()) + 1, 0)
    return bool(SCOPED.search(text[start:m.start()]))


def context(text, m):
    """The whole sentence the match sits in — judging a contradiction needs the
    clause that follows it, not the four matched words. Nobody knows every
    neighbourhood in the world; the output has to carry its own evidence."""
    start = max(text.rfind(".", 0, m.start()) + 1, 0)
    end = text.find(".", m.end())
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())


def main(only):
    findings = []
    checked = 0
    cities = 0
    # Read the built pages, not the city registry. The registry does not
    # contain London — it is rendered by its own pipeline — so a check that
    # iterates it skips 33 boroughs and still reports a clean run.
    for city_key, zones in published.published_cities():
        if only and city_key != only:
            continue
        cities += 1
        for z in zones:
            text = (z.get("text") or "").strip()
            if not text:
                continue
            checked += 1
            day, night = z.get("day"), z.get("night")
            # Only look at the sentence that talks about that time of day,
            # so "calm by day, tense at night" does not fire on the night half.
            md = CALM_DAY.search(text)
            if md and day in ("yellow", "red") and not scoped_to_a_part(text, md):
                findings.append((city_key, z["name"], "says calm BY DAY, rated %s by day" % day,
                                 context(text, md)))
            mn = CALM_NIGHT.search(text)
            if (mn and night in ("yellow", "red") and not TROUBLE.search(text)
                    and not scoped_to_a_part(text, mn)):
                findings.append((city_key, z["name"], "says calm AT NIGHT, rated %s at night" % night,
                                 context(text, mn)))

    print("Read %d area texts in %d published cities against their own ratings.\n"
          % (checked, cities))
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


# Cases this check has actually got wrong, kept as a test because every hole in
# it so far was found by accident rather than on purpose: a regex tuned to stop
# crying wolf can go silent instead, and a silent check is worse than none.
SELFTEST = [
    ("Part of district 4, west of Langstrasse. Residential and calm through the day.",
     True, "blanket calm claim — the shape this check was written for"),
    ("A mixed residential quarter, quiet by day and busier after dark.",
     True, "blanket calm claim with a neutral second clause"),
    ("The Bassin de la Villette waterfront itself is popular and generally fine by day; "
     "the Riquet-Stalingrad blocks are best avoided, especially after dark.",
     False, "Paris Pont-de-Flandre: scoped to one part, then reversed"),
    ("The market square itself is calm by day, though the station end is not.",
     False, "scoped and contrasted"),
    ("The area is calm by day, but the station end is not.",
     False, "explicit contrast"),
    ("The park is calm by day. The estate itself has a documented problem.",
     True, "'itself' in a later sentence must not silence this one"),
    ("Streets here are quiet by day; the underpass is best avoided.",
     False, "reversal without the word 'but'"),
]


def selftest():
    bad = 0
    for text, want, why in SELFTEST:
        m = CALM_DAY.search(text)
        got = bool(m) and not scoped_to_a_part(text, m)
        if got != want:
            bad += 1
        print("%s  fires=%-5s want=%-5s  %s"
              % ("FAIL" if got != want else "ok  ", got, want, why))
    print("\n%d failing case(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="check the detector against cases it has got wrong before")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else main(a.city))
