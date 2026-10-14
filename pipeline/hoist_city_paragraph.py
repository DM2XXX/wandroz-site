# -*- coding: utf-8 -*-
"""Hoists a city-level paragraph onto the hub — matching the paragraph, not its length.

The first version of this used "the tail is longer than 300 characters" as its
rule and destroyed Ghent's Gent: it replaced the shoplifting hotspots the police
actually localise — Veldstraat, Korenmarkt, Langemunt — with boilerplate, and
produced the sentence "The historic core ... It lies outside Ghent's historic
core." qa_full_site caught it, because the new wording declared an absence on a
page still tagged as documented.

So this version matches the exact shared paragraph and touches nothing else. An
area whose tail is one character different keeps everything it had.
"""
import collections
import io
import json
import os

SCOPE = {
    "vilnius": (
        "Lithuania publishes crime statistics at municipality level rather than by "
        "seniūnija, so there is no per-district figure to rate these areas on, and "
        "the ratings here come from an area-level review of Lithuanian reporting "
        "and the city's own district profiles rather than from a number. For the "
        "context that does exist: registered crime in the Vilnius area fell in "
        "2025 and the clearance rate rose to 52% from 49%, and the Lithuanian "
        "public broadcaster LRT describes the city as among Europe's safest "
        "capitals for visitors."),
    "warsaw": (
        "Poland publishes no open, geolocated neighbourhood crime dataset of the "
        "kind London runs on, so the ratings here come from an area-level review "
        "of police figures as the local press reports them and of coverage of the "
        "city's crime map, rather than from a per-district number. Where a dashed "
        "outline appears it says the ground was not examined, not that it was "
        "checked and found safe."),
    "ghent": (
        "Ghent publishes crime figures by wijk and by month as open data, and its "
        "police report two consecutive years of decline: 31,074 recorded offences "
        "in 2025, down 3,418 or 10% on 2024. Pickpocketing fell from 1,026 cases "
        "to 564, a drop of 45%, and burglaries, bicycle thefts and thefts from "
        "cars all fell sharply too; snatch thefts went from 168 to 122. The one "
        "thing the police do localise is shoplifting, and its hotspots are the "
        "shopping streets: Veldstraat, Korenmarkt and Langemunt."),
    "bratislava": (
        "Slovakia publishes no open neighbourhood-level crime dataset — the "
        "Interior Ministry's figures stop at district level and are not broken out "
        "publicly — so the ratings here come from an area-level review rather than "
        "from a number, and a dashed outline records an absence of findings rather "
        "than a checked all-clear. For city-wide context: the mayor has publicly "
        "asked central government for help with rising crime, and most offences in "
        "Bratislava go unsolved."),
}

TAIL = {
    "vilnius": ("The area-level review found nothing specific to this seniūnija in "
                "Lithuanian reporting or in the city's district profiles; the "
                "dashed outline records that absence."),
    "warsaw": ("It is outside the districts that appear in the police figures the "
               "local press reports on, and the area-level review found nothing "
               "specific to it."),
    "ghent": ("The area-level review found nothing specific to this deelgemeente, "
              "and the dashed outline records that absence."),
    "bratislava": ("It is one of the smaller mestské časti, outside the areas "
                   "Bratislava's police and city documents name, and the review "
                   "found nothing specific to it."),
}

for city, scope in SCOPE.items():
    path = os.path.join("pipeline", "data_zones", "%s.json" % city)
    doc = json.load(io.open(path, encoding="utf-8"))
    tails = collections.Counter()
    for z in doc["zones"]:
        _h, sep, rest = " ".join(z["text"].split()).partition(". ")
        if sep:
            tails[rest] += 1
    shared, count = tails.most_common(1)[0]
    doc["scopeNote"] = scope
    n = kept = 0
    for z in doc["zones"]:
        t = " ".join(z["text"].split())
        head, sep, rest = t.partition(". ")
        if sep and rest == shared:
            z["text"] = head + ". " + TAIL[city]
            n += 1
        else:
            kept += 1
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print("%-11s shared paragraph on %d areas -> hub; %d rewritten, %d left untouched"
          % (city, count, n, kept))
