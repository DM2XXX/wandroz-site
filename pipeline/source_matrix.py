"""
What every published city's rating actually rests on, in one table.

WHY THIS EXISTS
    The site shows the same three colours everywhere. Behind them sit five
    different things, from a monthly police feed queried by polygon to one
    person's first-pass judgement, and until now the only way to know which
    was to read the generator. That is how the homepage came to describe the
    whole site in the language of official data, and how "relatively safer
    than most other neighbourhoods" came to be printed for cities where the
    green means nothing was found.

    This writes the classification out as data, so a check can compare what a
    page claims against what its city is actually built on.

THE CATEGORIES
    A  official quantitative crime data      a public per-area crime dataset,
                                             used as published
    B  official data + normalisation         the same, divided by an estimated
                                             exposure rather than as published
    C  mixed official and qualitative        an official figure that covers
                                             only part of the picture, plus
                                             sourced research for the rest
    D  local-source research                 no per-area dataset exists; each
                                             area reviewed against named local
                                             sources
    E  manual first-pass                     neither, and the site says so

    No numeric confidence score. A number would imply the five are points on
    one scale, and they are not: B is not "better than" D by some ratio, it is
    a different kind of claim.

USAGE
    python3 pipeline/source_matrix.py             # human-readable table
    python3 pipeline/source_matrix.py --json      # machine-readable
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as BS
import published

OUT = os.path.join(os.path.dirname(HERE), "qa_output", "source_matrix.json")

# Everything below is a statement about a city's pipeline, not about the city.
# Where a field is unknown it says so; it is never guessed.
OVERRIDES = {
    "london": dict(
        category="B", source="data.police.uk street-level crime, Met and City of London Police",
        period="rolling 3 months, refreshed monthly",
        method="weighted category mix, normalised by estimated workday population",
        daynight="category-mix proxy: property crime = day, violence/robbery/ASB = night; the feed has no timestamps",
        unit="32 boroughs + the City of London",
        denominator="2021 residents x a 2011 workday/resident ratio (3 tiers: 18 measured headcount, 5 density-derived, 10 uncorrected)",
        limitation="day/night is inferred from offence type, not recorded time. The workday correction is an approximation and 10 boroughs have none."),
    "berlin": dict(
        category="A", source="Polizei Berlin Kriminalitätsatlas (Häufigkeitszahl)",
        period="2025", method="official frequency figure, used as published",
        daynight="none in the source; the same figure is shown for both",
        unit="143 Bezirksregionen", denominator="registered residents (the provider's own)",
        limitation="no day/night split exists. Central districts with few residents and heavy footfall read high."),
    "amsterdam": dict(
        category="A", source="CBS registered crime",
        period="latest CBS release", method="official registered-crime rate, used as published",
        daynight="none in the source", unit="110 wijken",
        denominator="registered residents",
        limitation="seven port and industrial wijken have 30–1,830 residents; a resident-normalised rate there is not a statement about risk to a person."),
    "praha": dict(
        category="A", source="Policie ČR (kriminalita.policie.gov.cz)",
        period="latest published", method="official figures, used as published",
        daynight="none in the source", unit="57 městské části",
        denominator="registered residents",
        limitation="four areas flagged for very small resident denominators."),
    "oslo": dict(
        category="A", source="Oslo kommune Statistikkbanken",
        period="latest published", method="official figures, used as published",
        daynight="none in the source", unit="15 bydeler + Sentrum",
        denominator="registered residents",
        limitation="Sentrum has almost no residents and very high footfall."),
    "zurigo": dict(
        category="C", source="Kantonspolizei Zürich burglary figures + area-level research",
        period="burglaries 2023–2025; research Sept 2026",
        method="day/night from area research; a separate burglary layer computed per district",
        daynight="research-based, not measured",
        unit="34 Quartiere, burglary inherited from 12 Kreise",
        denominator="burglary layer: residents + workplaces (STATENT 2024). Day/night ratings: none",
        limitation="the official figure covers burglary only and is district-level, not neighbourhood-level. The day/night colours are not derived from it."),
    "basel": dict(
        category="C", source="data.bs.ch municipal crime (Riehen, Bettingen only) + area-level research",
        period="2025 figures; research Sept 2026",
        method="area research; official figures exist for 2 of 21 areas",
        daynight="research-based", unit="19 Wohnviertel + 2 Landgemeinden",
        denominator="residents, for the two municipal figures only",
        limitation="checked twice: no crime data is published below municipality. 19 of 21 areas have no figure."),
    "bern": dict(
        category="D", source="area-level research; Kantonspolizei Bern PKS for canton context",
        period="research Sept 2026; PKS 2025",
        method="area research", daynight="research-based",
        unit="27 statistical districts + Innere Stadt",
        denominator="none",
        limitation="PKS stops at municipality, so the city has one figure and its districts none."),
    "geneva": dict(
        category="D", source="area-level research; Police cantonale + Diagnostic local de sécurité for context",
        period="research Sept 2026; DLS 2023; police figures 2025",
        method="area research", daynight="research-based",
        unit="8 city quarters + 44 communes", denominator="none",
        limitation="the canton publishes crime per commune but only as a PDF whose columns cannot be read back reliably. The DLS ranks perceived safety, which is not recorded crime."),
    "torino": dict(
        category="E", source="general knowledge and public reputation",
        period="unknown", method="manual first-pass", daynight="manual",
        unit="23 quartieri", denominator="none",
        limitation="the site labels this a limited-data assessment. No source review has been completed."),
}

UK_FORCES = {c["key"]: c["force"] for c in BS.UK_CITIES}


def classify(city_key):
    if city_key in OVERRIDES:
        return dict(OVERRIDES[city_key])
    if city_key in UK_FORCES:
        return dict(
            category="B", source="data.police.uk street-level crime, %s" % UK_FORCES[city_key],
            period="rolling 3 months, refreshed monthly",
            method="weighted category mix, normalised by estimated workday population",
            daynight="category-mix proxy; the feed has no timestamps",
            unit="local-authority wards", denominator="residents x workday ratio",
            limitation="the ward set is the local authority's, which for some cities is larger than the city.")
    meta = BS.CITY_METHODOLOGY.get(city_key) or {}
    tier = meta.get("tier", BS.MANUAL_EXPERIMENTAL)
    if tier == BS.OFFICIAL_SNAPSHOT:
        return dict(category="A", source=meta.get("crime_source", "official statistics"),
                    period="latest published", method="official figures, used as published",
                    daynight="unverified", unit="official areas",
                    denominator="residents", limitation="not individually reviewed by this script")
    if tier == BS.RESEARCH_BASED:
        return dict(category="D", source="area-level review of named local sources",
                    period="see each area", method="area research", daynight="research-based",
                    unit="official areas", denominator="none",
                    limitation="no per-area crime dataset exists for this city")
    return dict(category="E", source="manual first-pass", period="unknown",
                method="manual", daynight="manual", unit="official areas",
                denominator="none", limitation="limited-data assessment")


def main(as_json):
    slug_to_key = {c[1]: c[0] for c in BS.mapped_cities()}
    rows = []
    for slug, zones in published.published_cities():
        key = slug_to_key.get(slug, slug)
        r = classify(key)
        r.update(city=slug, key=key, areas=len(zones))
        rows.append(r)
    rows.sort(key=lambda r: (r["category"], r["city"]))

    if as_json:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        io.open(OUT, "w", encoding="utf-8").write(
            json.dumps({"cities": rows}, ensure_ascii=False, indent=1) + "\n")
        print("wrote %s — %d cities" % (OUT, len(rows)))
        return 0

    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    print("%d published cities: %s\n" % (len(rows), ", ".join(
        "%s=%d" % (k, counts[k]) for k in sorted(counts))))
    print("%-2s %-14s %5s  %s" % ("", "city", "areas", "source"))
    for r in rows:
        print("%-2s %-14s %5d  %s" % (r["category"], r["city"], r["areas"], r["source"][:78]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.json))
