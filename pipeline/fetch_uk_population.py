"""
Ward population from the 2021 census, straight from NOMIS.

The crime rate is only as honest as its denominator. London's boroughs carry a
resident count plus a workday correction; a new city starts with the resident
count, which is the figure the census publishes per ward, and the pages say so
rather than implying a footfall correction that does not exist yet.
"""
import json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset/NM_2021_1.data.json"
UA = "WandrozPopulation/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"


def fetch(codes):
    out = {}
    for i in range(0, len(codes), 20):
        chunk = codes[i:i + 20]
        url = NOMIS + "?" + urllib.parse.urlencode({
            "geography": ",".join(chunk),
            "c2021_restype_3": 0,
            "measures": 20100,
            "select": "geography_code,obs_value",
        })
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            for obs in json.load(r).get("obs", []):
                out[obs["geography"]["geogcode"]] = int(obs["obs_value"]["value"])
        time.sleep(0.5)
    return out


def main(key):
    path = os.path.join(HERE, "data_zones", "%s_boundaries.json" % key)
    doc = json.load(open(path))
    codes = [z["code"] for z in doc["zones"] if z.get("code")]
    pops = fetch(codes)
    missing = []
    for z in doc["zones"]:
        p = pops.get(z.get("code"))
        if p:
            z["population"] = p
        else:
            missing.append(z["name"])
    json.dump(doc, open(path, "w"), ensure_ascii=False)
    total = sum(z.get("population", 0) for z in doc["zones"])
    print("%s: %d zone con popolazione, totale %s abitanti" % (key, len(pops), "{:,}".format(total)))
    if missing:
        print("senza popolazione:", ", ".join(missing))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "birmingham")
