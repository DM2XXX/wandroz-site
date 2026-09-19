"""
Wandroz — rebuild pipeline/data_zones/zurigo.json from official Zurich data.

WHY ZURICH IS BEING REBUILT
    Zurich has been the site's weakest city: a limited-data assessment over 34
    statistical Quartiere, rated by a qualitative first pass, with the only
    real number — Kantonspolizei burglary counts by Kreis — shown alongside
    rather than driving anything. That was correct in August 2026, when the
    canton's full crime statistic by Stadtkreis was frozen at 2022 and could
    not honestly be called current.

    It is not frozen any more. KTZH_00001202_00003600 now runs 2009 to 2025,
    all twelve Stadtkreise, every offence group, with the resident population
    and the Häufigkeitszahl (offences per 1,000 residents) already computed by
    the Statistisches Amt. That is the same shape of evidence as Berlin's
    Kriminalitätsatlas, so Zurich moves from limited-data to official-data.

WHY TWELVE KREISE AND NOT THIRTY-FOUR QUARTIERE
    Because that is the level the official source publishes, and because it is
    what every other official-data city on this site already does: Munich's 25
    Stadtbezirke, Prague's 57 městské části, Stockholm's 11 stadsdelsnämnder,
    Brussels' 19 communes. None of those units was chosen for its count; each
    is the finest geography its own source publishes.

    Keeping 34 Quartiere and giving each the figure of its parent Kreis would
    be the one exception on the site to that rule: five neighbourhoods carrying
    an identical number, with an inheritance to disclose on every page. More
    pages, less truth.

    The twelve Kreise tile the city completely, so nothing is left unrated —
    and "Kreis 4", "Kreis 6" is how people in Zurich actually describe where
    they live. The 34 Quartier names are not lost: they become search aliases
    pointing at the Kreis that contains them, and the old URLs redirect.

SOURCES
  - Crime: Kanton Zürich / Kantonspolizei, Polizeiliche Kriminalstatistik,
    KTZH_00001202_00003600.csv, via the canton's OGD resource endpoint.
    Columns used: Ausgangsjahr, Gemeindename, Stadtkreis_Name, Haupttitel,
    Straftaten_total, Einwohner, Häufigkeitszahl.
  - Boundaries: maps.zh.ch WFS, layer ogd-0278_arv_basis_up_stadtkreise_f,
    the canton's own Stadtkreis polygons, requested in EPSG:4326.

    python3 pipeline/build_zurich_zones.py            # dry run, prints the table
    python3 pipeline/build_zurich_zones.py --write
"""
import io, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score_london import RED_THRESHOLD, GREEN_THRESHOLD

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
PKS = "https://www.web.statistik.zh.ch/ogd/daten/ressourcen/KTZH_00001202_00003600.csv"
WFS = ("https://maps.zh.ch/wfs/OGDZHWFS?service=WFS&version=2.0.0&request=GetFeature"
       "&typeNames=ms:ogd-0278_arv_basis_up_stadtkreise_f&outputFormat=geojson"
       "&srsName=EPSG:4326")
RAW = os.path.join(HERE, "data_zones", "zurigo_raw")

# WHICH LAW COUNTS, AND WHY NOT ALL OF THEM
#   The source splits offences across three laws: the Criminal Code (StGB), the
#   narcotics act (BetmG) and the foreign nationals act (AIG). It publishes no
#   single grand total, so one has to be chosen.
#
#   Only StGB is counted here — the five "Total ..." rows under it, which
#   together are its total. Theft, violence, robbery, damage: the things a
#   safety rating is about.
#
#   AIG is deliberately excluded, and this is the decision worth defending.
#   Those are immigration offences: illegal entry, illegal residence, illegal
#   employment. They measure where the police check people's papers, not where
#   a traveller is at risk, and counting them would push up exactly the
#   districts with more foreign residents and more policing. That is not a
#   safety signal, it is a policing signal wearing one.
#
#   BetmG is excluded for a weaker but similar reason: recorded drug offences
#   track enforcement activity more than street risk.
LAW = "StGB"

# The 34 statistical Quartiere, by the Kreis that contains them. Not used for
# rating — only so someone typing "Seefeld" finds the page that covers it.
# From the city's own Quartier/Kreis correspondence.
QUARTIERE = {
    1: ["Rathaus", "Hochschulen", "Lindenhof", "City"],
    2: ["Wollishofen", "Leimbach", "Enge"],
    3: ["Alt-Wiedikon", "Friesenberg", "Sihlfeld"],
    4: ["Werd", "Langstrasse", "Hard"],
    5: ["Gewerbeschule", "Escher Wyss"],
    6: ["Unterstrass", "Oberstrass"],
    7: ["Fluntern", "Hottingen", "Hirslanden", "Witikon"],
    8: ["Seefeld", "Mühlebach", "Weinegg"],
    9: ["Albisrieden", "Altstetten"],
    10: ["Höngg", "Wipkingen"],
    11: ["Affoltern", "Oerlikon", "Seebach"],
    12: ["Saatlen", "Schwamendingen-Mitte", "Hirzenbach"],
}


def fetch(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        return dest
    r = subprocess.run(["curl", "-sSL", "--max-time", "180", "-A", UA, "-o", dest, url],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(dest):
        raise SystemExit("download failed: %s" % url)
    return dest


def load_crime():
    """{kreis number: {"total": n, "pop": n, "hz": float, "year": "2025"}}"""
    import csv
    path = fetch(PKS, os.path.join(RAW, "pks_stadtkreise.csv"))
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig")))
    years = sorted({r["Ausgangsjahr"] for r in rows
                    if r.get("Gemeindename") == "Zürich" and r.get("Stadtkreis_Name")})
    year = years[-1]
    out = {}
    for r in rows:
        if r.get("Gemeindename") != "Zürich" or r.get("Ausgangsjahr") != year:
            continue
        name = (r.get("Stadtkreis_Name") or "").strip()
        m = re.fullmatch(r"Kreis (\d+)", name)
        if not m or (r.get("Gesetz_Abk") or "").strip() != LAW:
            continue
        k = int(m.group(1))
        e = out.setdefault(k, {"total": 0, "pop": 0, "year": year})
        e["total"] += int(r["Straftaten_total"] or 0)
        e["pop"] = int(r["Einwohner"] or 0)
    if len(out) != 12:
        raise SystemExit("expected 12 Kreise for %s, found %d" % (year, len(out)))
    return out, year


def load_boundaries():
    path = fetch(WFS, os.path.join(RAW, "stadtkreise.geojson"))
    gj = json.load(io.open(path, encoding="utf-8"))
    out = {}
    for f in gj["features"]:
        p = f["properties"]
        if p.get("gemeindename") != "Zürich":
            continue
        n = int(p["stadtkreisnummer"])
        g = f["geometry"]
        rings = g["coordinates"] if g["type"] == "Polygon" else [
            r for poly in g["coordinates"] for r in poly]
        # Wandroz stores [lat, lon]; GeoJSON is [lon, lat].
        out[n] = [[[pt[1], pt[0]] for pt in ring] for ring in rings]
    if len(out) != 12:
        raise SystemExit("expected 12 Kreis polygons, found %d" % len(out))
    return out


def main(write):
    crime, year = load_crime()
    bounds = load_boundaries()

    # Rated against Zurich's own average, weighted by population — the same
    # comparison every other official-data city on this site uses. A rate is
    # only ever meaningful next to the other areas of the same city.
    tot_off = sum(c["total"] for c in crime.values())
    tot_pop = sum(c["pop"] for c in crime.values())
    city_hz = tot_off / tot_pop * 1000.0

    zones = []
    print("Zurich, PKS %s — city average %.1f offences per 1,000 residents\n" % (year, city_hz))
    print("%-9s %8s %9s %8s %6s  %s" % ("Kreis", "offences", "residents", "per1000", "vs city", "quartiere"))
    for n in sorted(crime):
        c = crime[n]
        hz = c["total"] / c["pop"] * 1000.0
        ratio = hz / city_hz
        # Le stesse due soglie di ogni altra citta' a dato ufficiale, importate
        # da score_london invece che riscritte: una copia diverge.
        tone = "red" if ratio >= RED_THRESHOLD else ("green" if ratio <= GREEN_THRESHOLD else "yellow")
        qs = QUARTIERE[n]
        print("%-9s %8d %9d %8.1f %6.2f  %s"
              % ("Kreis %d" % n, c["total"], c["pop"], hz, ratio, ", ".join(qs)))
        zones.append({
            "name": "Kreis %d" % n,
            "slug": "kreis-%d" % n,
            "day": tone, "night": tone,
            "text": describe(n, c, hz, ratio, city_hz, year, qs),
            "query": "Kreis %d, Zurich, Switzerland" % n,
            "booking_scope": "area",
            "evidence": "documented",
            "aliases": qs,
            "coords": bounds[n],
        })

    doc = {"label": "Zurich, Switzerland",
           "center": [47.3769, 8.5417], "zoom": 12,
           "dataNote": "", "zones": zones}
    dest = os.path.join(HERE, "data_zones", "zurigo.json")
    if write:
        json.dump(doc, io.open(dest, "w", encoding="utf-8"), ensure_ascii=False)
        print("\nWrote %s (%d Kreise)" % (dest, len(zones)))
    else:
        print("\nDry run. Add --write to replace %s" % dest)
    return 0


def describe(n, c, hz, ratio, city_hz, year, quartiere):
    pct = int(round(ratio * 100))
    where = ", ".join(quartiere)
    return (
        "Kreis %d is one of the 12 official Stadtkreise the city of Zurich is divided into, "
        "covering %s. Kantonspolizei Zürich recorded %s offences under the Swiss Criminal Code "
        "here in %s across %s residents — %.1f per 1,000, %d%% of the citywide average of %.1f. "
        "The figure is the canton's own published Häufigkeitszahl, normalised against registered "
        "residents rather than the people who pass through, so a central Kreis with few residents "
        "and heavy daily footfall reads higher than the experience of being there would suggest. "
        "Zurich publishes no crime statistic below Stadtkreis level, and the same figure therefore "
        "applies to every Quartier inside this one. It is an annual snapshot, not a live feed, and "
        "it carries no time of day: the day and night levels shown here come from the same number."
        % (n, where, format(c["total"], ","), year, format(c["pop"], ","), hz, pct, city_hz)
    )


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
