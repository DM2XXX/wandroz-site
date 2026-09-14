"""
Street-level crime for any English or Welsh city, from data.police.uk.

This is fetch_london.py with the city taken out of it. The API covers every
police force in England and Wales, and the ONS publishes every ward boundary,
so a new city needs a boundary file and nothing else. Each zone's real polygon
is POSTed (not a radius around a centroid, which mis-assigns incidents at the
edges), for the most recent months the API publishes.

    python3 fetch_uk_city.py manchester
"""
import json, os, subprocess, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
API = "https://data.police.uk/api/crimes-street/all-crime"
DATES = "https://data.police.uk/api/crimes-street-dates"
UA = "WandrozCrimeFetch/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"
MONTHS = 3


# Transport is curl, not urllib or requests. data.police.uk refuses the TLS
# handshake offered by the LibreSSL that macOS's system Python links against,
# and a fetch script that only runs on one machine is a fetch script that stops
# working the day it matters. curl is present on the runner and on the laptop.
def http(url, data=None, timeout=180):
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-A", UA]
    if data is not None:
        cmd += ["--data", urllib.parse.urlencode(data)]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("curl failed (%s): %s" % (res.returncode, res.stderr.strip()[:200]))
    return json.loads(res.stdout)


def available_months(n=MONTHS):
    return [d["date"] for d in http(DATES, timeout=60)][:n]


def poly_of(zone):
    ring = zone["coords"][0]
    # The API caps polygon complexity; a ward outline stays well inside it, but
    # thin it evenly rather than truncating, so the shape stays the shape.
    step = max(1, len(ring) // 240)
    pts = ring[::step]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return ":".join("%s,%s" % (lat, lon) for lat, lon in pts)


def fetch(zone, month):
    payload = {"poly": poly_of(zone), "date": month}
    for attempt in range(3):
        try:
            return http(API, data=payload)
        except Exception:
            if attempt < 2:
                time.sleep(15 * (attempt + 1)); continue
            raise


def main(key):
    src = os.path.join(HERE, "data_zones", "%s_boundaries.json" % key)
    doc = json.load(open(src))
    out_dir = os.path.join(REPO, "data", "raw_%s" % key)
    os.makedirs(out_dir, exist_ok=True)
    months = available_months()
    print("%s: %d zone x %d mesi (%s)" % (key, len(doc["zones"]), len(months), ", ".join(months)))
    manifest = {}
    for z in doc["zones"]:
        for month in months:
            path = os.path.join(out_dir, "%s_%s.json" % (z["slug"], month))
            if os.path.exists(path):
                continue
            crimes = fetch(z, month)
            json.dump(crimes, open(path, "w"))
            manifest.setdefault(z["slug"], {})[month] = len(crimes)
            print("  %-26s %s  %5d reati" % (z["name"], month, len(crimes)))
            time.sleep(1.0)
    json.dump({"city": key, "months": months, "counts": manifest},
              open(os.path.join(out_dir, "manifest.json"), "w"), indent=1)
    check_plausible(key, doc, out_dir, months)
    print("fatto")


# Greater Manchester Police does not supply street-level crime to
# data.police.uk. The API answers cheerfully anyway: six recorded crimes for a
# city of 552,000, which would have published Manchester as far and away the
# safest place in Europe — a claim produced entirely by a force's absence from
# a feed. A city whose rate is implausibly low is a data-supply problem, not a
# finding, and the fetch says so instead of handing the number downstream.
MIN_CRIMES_PER_1000_PER_MONTH = 2.0


def check_plausible(key, doc, out_dir, months):
    import glob
    total = 0
    for path in glob.glob(os.path.join(out_dir, "*_*.json")):
        if path.endswith("manifest.json"):
            continue
        total += len(json.load(open(path)))
    pop = sum(z.get("population") or 0 for z in doc["zones"])
    if not pop or not months:
        return
    rate = total / (pop / 1000.0) / len(months)
    print("plausibilita': %s reati su %s abitanti in %d mesi = %.2f per 1.000 al mese"
          % ("{:,}".format(total), "{:,}".format(pop), len(months), rate))
    if rate < MIN_CRIMES_PER_1000_PER_MONTH:
        raise SystemExit(
            "\nSTOP: %s registra %.2f reati per 1.000 abitanti al mese, sotto la soglia di "
            "plausibilita' (%.1f). Quasi certamente la forza di polizia competente non "
            "pubblica su data.police.uk — verifica prima di costruire la citta'."
            % (key, rate, MIN_CRIMES_PER_1000_PER_MONTH))


main(sys.argv[1] if len(sys.argv) > 1 else "manchester")
