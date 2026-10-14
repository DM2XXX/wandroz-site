"""
Puts Bern's and Basel's official population figures onto their area pages.

Bern and Basel have official geography and, until now, no official number
behind any area: neither canton publishes crime below the municipality. Both
cities do publish, per area and current, how many people live there.

That figure is not a crime statistic and this does not make it one. The rating
is untouched. What it changes is that a page saying "nothing was reported here"
now also says how many people that covers — four hundred or twenty thousand is
the difference between a quiet street and a finding worth doubting.

Density is derived rather than quoted: the population is the city's, the area
is this site's own simplified polygon, so the sentence says "of the area drawn
here" instead of implying an official density.

USAGE
    python3 pipeline/fetch_swiss_population.py     # first
    python3 pipeline/apply_swiss_population.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_site as BS

RAW = os.path.join(REPO, "data", "raw_swiss")
ZONES = os.path.join(HERE, "data_zones")

CITED = {
    "bern": ("Statistik Stadt Bern", "district"),
    "basel": ("Kanton Basel-Stadt's own statistics", "Wohnviertel"),
}


def sentence(office, unit, people, year, km2):
    per = people / km2 if km2 else 0
    if per >= 1000:
        density = "roughly %s per square kilometre of the area drawn here" % (
            "{:,}".format(int(round(per, -2))))
    elif per >= 100:
        density = "roughly %d per square kilometre of the area drawn here" % int(
            round(per, -1))
    else:
        density = "fewer than a hundred per square kilometre of the area drawn here"
    return "%s counted %s residents in the %s at the end of %s, %s." % (
        office, "{:,}".format(people), unit, year, density)


def short_form(office, people, year, km2):
    per = people / km2 if km2 else 0
    amount = ("{:,}".format(int(round(per, -2))) if per >= 1000
              else str(int(round(per, -1))))
    return ("That is the figure %s publishes for the end of %s, and roughly %s "
            "per square kilometre of the area drawn here." % (office, year, amount))


def main():
    changed = 0
    for city, (office, unit) in CITED.items():
        raw = json.load(io.open(os.path.join(RAW, "%s_population.json" % city),
                                encoding="utf-8"))
        pop, year = raw["areas"], raw["year"]
        path = os.path.join(ZONES, "%s.json" % city)
        doc = json.load(io.open(path, encoding="utf-8"))
        missing = [z["name"] for z in doc["zones"] if z["name"] not in pop]
        if missing:
            raise SystemExit("no population figure for %s in %s: %s"
                             % (", ".join(missing), city, raw["source"]))
        n = 0
        for z in doc["zones"]:
            km2 = sum(BS.ring_area_m2(r) for r in BS.simplify_rings(z["coords"])) / 1e6
            people = pop[z["name"]]
            # After the geography, before whatever the review did or did not
            # find: where it is, how many live there, then what is known.
            head, sep, rest = z["text"].partition(". ")
            # Four Basel texts were written with the resident count already in
            # them — Altstadt Grossbasel's "with only 2,692 residents". Saying
            # it twice in consecutive sentences reads as a machine talking over
            # a person, so there only the density and the attribution are added.
            # It has to be the sentence BEFORE: Gotthelf mentions its 7,256 two
            # sentences later, and "That is the figure..." then pointed at
            # nothing at all.
            if "{:,}".format(people) in head:
                s = short_form(office, people, year, km2)
            else:
                s = sentence(office, unit, people, year, km2)
            if s in z["text"]:
                continue
            z["text"] = (head + ". " + s + " " + rest) if sep else (z["text"] + " " + s)
            n += 1
        io.open(path, "w", encoding="utf-8").write(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        changed += n
        print("%-6s %2d areas given an official population (%s, end %s)"
              % (city, n, raw["source"], year))
    print("\n%d pages now carry a figure their city publishes" % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
