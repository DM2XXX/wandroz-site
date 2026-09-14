"""
Sights for a city: the well-known ones found by ranking, the rest named by hand.

Two passes, because neither alone is right. Ranking Wikidata by sitelink count
finds the cathedral and the museum and misses every place a resident would send
you after dark — that is how twenty-five cities ended up with a "Nightlife"
filter containing nothing. Naming everything by hand finds those and misses the
obvious. So: a proximity query for what is notable, a curated list for what the
categories promise, and the same two guards on both — nothing beyond 12 km from
the centre, nothing within 60 m of a pin already placed.

    python3 build_city_pois.py birmingham
"""
import json, math, os, subprocess, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
POI_DIR = os.path.join(HERE, "data_poi")
UA = "WandrozPOI/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"
WDQS = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"

CAT_TYPE = {"art": "LANDMARK", "view": "VIEWPOINT", "green": "PARK",
            "square": "AREA", "food": "MARKET", "night": "AREA"}

CITIES = {
    "bologna": {
        "centre": (11.3426, 44.4938), "lang": "it",
        "min_sitelinks": 10,
        "curated": [
            ("Piazza Maggiore", "square", "AREA"),
            ("Basilica di San Petronio", "art", "LANDMARK"),
            ("Due Torri, Bologna", "view", "VIEWPOINT"),
            ("Torre degli Asinelli", "view", "VIEWPOINT"),
            ("Archiginnasio di Bologna", "art", "LANDMARK"),
            ("Santuario della Madonna di San Luca", "view", "LANDMARK"),
            ("Portico di San Luca", "square", "AREA"),
            ("Basilica di Santo Stefano (Bologna)", "art", "LANDMARK"),
            ("Quadrilatero, Bologna", "food", "MARKET"),
            ("Mercato delle Erbe", "food", "MARKET"),
            ("Mercato di Mezzo", "food", "MARKET"),
            ("Giardini Margherita", "green", "PARK"),
            ("Parco della Montagnola", "green", "PARK"),
            ("Pinacoteca Nazionale di Bologna", "art", "MUSEUM"),
            ("Museo Civico Archeologico di Bologna", "art", "MUSEUM"),
            ("MAMbo", "art", "MUSEUM"),
            ("Piazza Santo Stefano", "square", "AREA"),
            ("via del Pratello", "night", "AREA"),
            ("Piazza Giuseppe Verdi", "night", "AREA"),
            ("Via Zamboni", "night", "AREA"),
            ("Teatro Comunale di Bologna", "art", "LANDMARK"),
            ("Basilica di San Domenico", "art", "LANDMARK"),
            ("Parco di Villa Ghigi", "green", "PARK"),
        ],
    },
    "birmingham": {
        "centre": (-1.8904, 52.4862), "lang": "en",
        "min_sitelinks": 12,
        "curated": [
            ("Bullring, Birmingham", "square", "AREA"),
            ("Selfridges Building, Birmingham", "art", "LANDMARK"),
            ("St Philip's Cathedral, Birmingham", "art", "LANDMARK"),
            ("Symphony Hall, Birmingham", "art", "LANDMARK"),
            ("Thinktank, Birmingham Science Museum", "art", "MUSEUM"),
            ("Cadbury World", "art", "MUSEUM"),
            ("Ikon Gallery", "art", "MUSEUM"),
            ("Barber Institute of Fine Arts", "art", "MUSEUM"),
            ("Soho House, Birmingham", "art", "MUSEUM"),
            ("Sarehole Mill", "art", "MUSEUM"),
            ("Winterbourne House and Garden", "green", "PARK"),
            ("Lickey Hills", "view", "VIEWPOINT"),
            ("Chinese Quarter, Birmingham", "food", "AREA"),
            ("Villa Park", "art", "LANDMARK"),
            ("Jewellery Quarter", "square", "AREA"),
            ("Digbeth", "night", "AREA"),
            ("Broad Street, Birmingham", "night", "AREA"),
            ("Brindleyplace", "square", "AREA"),
            ("Moseley", "night", "AREA"),
            ("Birmingham Museum and Art Gallery", "art", "MUSEUM"),
            ("Library of Birmingham", "art", "LANDMARK"),
            ("Cannon Hill Park", "green", "PARK"),
            ("Sutton Park", "green", "PARK"),
            ("Birmingham Back to Backs", "art", "MUSEUM"),
            ("Aston Hall", "art", "LANDMARK"),
            ("Gas Street Basin", "square", "AREA"),
            ("Edgbaston Cricket Ground", "art", "LANDMARK"),
            ("Custard Factory", "night", "AREA"),
            ("Birmingham Botanical Gardens", "green", "PARK"),
        ],
    },
    "leeds": {
        "centre": (-1.5491, 53.8008), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Leeds Kirkgate Market", "food", "MARKET"),
            ("Leeds Corn Exchange", "square", "AREA"),
            ("Briggate", "square", "AREA"),
            ("Leeds Minster", "art", "LANDMARK"),
            ("Roundhay Park", "green", "PARK"),
            ("Kirkstall Abbey", "art", "LANDMARK"),
            ("Leeds Art Gallery", "art", "MUSEUM"),
            ("Royal Armouries Museum", "art", "MUSEUM"),
            ("Call Lane", "night", "AREA"),
            
            ("Headingley", "night", "AREA"),
            ("Leeds Town Hall", "art", "LANDMARK"),
            ("Victoria Quarter", "square", "AREA"),
            ("Temple Newsam", "green", "PARK"),
            ("Leeds Dock", "square", "AREA"),
        ],
    },
    "newcastle": {
        "centre": (-1.6178, 54.9783), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Tyne Bridge", "view", "VIEWPOINT"),
            ("Gateshead Millennium Bridge", "view", "VIEWPOINT"),
            ("Grey's Monument", "square", "AREA"),
            ("Grainger Town", "square", "AREA"),
            ("Quayside, Newcastle upon Tyne", "night", "AREA"),
            ("Bigg Market", "night", "AREA"),
            ("Ouseburn Valley", "night", "AREA"),
            ("Jesmond Dene", "green", "PARK"),
            ("Leazes Park", "green", "PARK"),
            ("Great North Museum: Hancock", "art", "MUSEUM"),
            ("Laing Art Gallery", "art", "MUSEUM"),
            ("Baltic Centre for Contemporary Art", "art", "MUSEUM"),
            ("St James' Park", "art", "LANDMARK"),
            ("Newcastle Castle", "art", "LANDMARK"),
            ("Grainger Market", "food", "MARKET"),
        ],
    },
    "sheffield": {
        "centre": (-1.4701, 53.3811), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Sheffield Winter Garden", "green", "PARK"),
            ("Peace Gardens", "square", "AREA"),
            ("Sheffield Botanical Gardens", "green", "PARK"),
            ("Endcliffe Park", "green", "PARK"),
            ("Kelham Island Museum", "art", "MUSEUM"),
            ("Millennium Gallery", "art", "MUSEUM"),
            ("Graves Gallery", "art", "MUSEUM"),
            ("Sheffield Cathedral", "art", "LANDMARK"),
            ("Devonshire Green", "night", "AREA"),
            ("West Street, Sheffield", "night", "AREA"),
            ("Kelham Island", "night", "AREA"),
            ("Ecclesall Road", "square", "AREA"),
            ("Moor Market", "food", "MARKET"),
            ("Bramall Lane", "art", "LANDMARK"),
        ],
    },
    "nottingham": {
        "centre": (-1.1581, 52.9548), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Nottingham Castle", "art", "LANDMARK"),
            ("Old Market Square", "square", "AREA"),
            ("City of Caves", "art", "MUSEUM"),
            ("Nottingham Contemporary", "art", "MUSEUM"),
            ("Wollaton Hall", "art", "MUSEUM"),
            ("Highfields Park, Nottingham", "green", "PARK"),
            ("The Arboretum, Nottingham", "green", "PARK"),
            ("Hockley, Nottingham", "night", "AREA"),
            ("Lace Market", "night", "AREA"),
            ("Ye Olde Trip to Jerusalem", "night", "AREA"),
            ("Victoria Centre", "square", "AREA"),
            ("Nottingham Council House", "art", "LANDMARK"),
            ("Sneinton Market", "food", "MARKET"),
        ],
    },
    "cardiff": {
        "centre": (-3.1791, 51.4816), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Cardiff Castle", "art", "LANDMARK"),
            ("Principality Stadium", "art", "LANDMARK"),
            ("Cardiff Bay", "square", "AREA"),
            ("Wales Millennium Centre", "art", "LANDMARK"),
            ("National Museum Cardiff", "art", "MUSEUM"),
            ("Bute Park", "green", "PARK"),
            ("Roath Park", "green", "PARK"),
            ("Cardiff Market", "food", "MARKET"),
            ("Castle Quarter, Cardiff", "square", "AREA"),
            ("St Mary Street, Cardiff", "night", "AREA"),
            ("Mermaid Quay", "night", "AREA"),
            ("Llandaff Cathedral", "art", "LANDMARK"),
            ("Techniquest", "art", "MUSEUM"),
        ],
    },
    "liverpool": {
        "centre": (-2.9916, 53.4084), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Royal Albert Dock", "square", "AREA"),
            ("Liverpool Cathedral", "art", "LANDMARK"),
            ("Liverpool Metropolitan Cathedral", "art", "LANDMARK"),
            ("Walker Art Gallery", "art", "MUSEUM"),
            ("World Museum", "art", "MUSEUM"),
            ("The Beatles Story", "art", "MUSEUM"),
            ("Cavern Club", "night", "AREA"),
            ("Concert Square", "night", "AREA"),
            ("Baltic Triangle", "night", "AREA"),
            ("Sefton Park", "green", "PARK"),
            ("Anfield", "art", "LANDMARK"),
            ("Bold Street", "square", "AREA"),
            ("Pier Head", "view", "VIEWPOINT"),
            ("St George's Hall, Liverpool", "art", "LANDMARK"),
        ],
    },
    "brighton": {
        "centre": (-0.1372, 50.8225), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Royal Pavilion", "art", "LANDMARK"),
            ("Brighton Palace Pier", "art", "LANDMARK"),
            ("The Lanes, Brighton", "square", "AREA"),
            ("North Laine", "square", "AREA"),
            ("Brighton Beach", "green", "PARK"),
            ("British Airways i360", "view", "VIEWPOINT"),
            ("Brighton Museum and Art Gallery", "art", "MUSEUM"),
            ("Kemptown", "night", "AREA"),
            ("West Street, Brighton", "night", "AREA"),
            ("Brighton Marina", "square", "AREA"),
            ("Preston Park, Brighton", "green", "PARK"),
            ("Devil's Dyke", "view", "VIEWPOINT"),
            ("Open Market, Brighton", "food", "MARKET"),
        ],
    },
    "york": {
        "centre": (-1.0873, 53.9600), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("York Minster", "art", "LANDMARK"),
            ("The Shambles", "square", "AREA"),
            ("Clifford's Tower", "art", "LANDMARK"),
            ("York City Walls", "view", "VIEWPOINT"),
            ("Jorvik Viking Centre", "art", "MUSEUM"),
            ("National Railway Museum", "art", "MUSEUM"),
            ("York Castle Museum", "art", "MUSEUM"),
            ("Museum Gardens, York", "green", "PARK"),
            ("Rowntree Park", "green", "PARK"),
            ("Micklegate", "night", "AREA"),
            ("Shambles Market", "food", "MARKET"),
            ("York Art Gallery", "art", "MUSEUM"),
        ],
    },
    "oxford": {
        "centre": (-1.2577, 51.7520), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Radcliffe Camera", "art", "LANDMARK"),
            ("Bodleian Library", "art", "LANDMARK"),
            ("Christ Church, Oxford", "art", "LANDMARK"),
            ("Ashmolean Museum", "art", "MUSEUM"),
            ("Oxford University Museum of Natural History", "art", "MUSEUM"),
            ("Pitt Rivers Museum", "art", "MUSEUM"),
            ("University Parks", "green", "PARK"),
            ("Christ Church Meadow", "green", "PARK"),
            ("Covered Market, Oxford", "food", "MARKET"),
            ("Cowley Road", "night", "AREA"),
            ("Jericho, Oxford", "night", "AREA"),
            ("Carfax Tower", "view", "VIEWPOINT"),
        ],
    },
    "cambridge": {
        "centre": (0.1218, 52.2053), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("King's College Chapel, Cambridge", "art", "LANDMARK"),
            ("Fitzwilliam Museum", "art", "MUSEUM"),
            ("Trinity College, Cambridge", "art", "LANDMARK"),
            ("The Backs", "green", "PARK"),
            ("Cambridge University Botanic Garden", "green", "PARK"),
            ("Parker's Piece", "green", "PARK"),
            ("Mill Road", "night", "AREA"),
            ("Cambridge Corn Exchange", "art", "LANDMARK"),
            ("Midsummer Common", "green", "PARK"),
            ("Jesus Green", "green", "PARK"),
        ],
    },
    "bath": {
        "centre": (-2.3590, 51.3811), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Roman Baths", "art", "MUSEUM"),
            ("Bath Abbey", "art", "LANDMARK"),
            ("Royal Crescent", "art", "LANDMARK"),
            ("The Circus, Bath", "square", "AREA"),
            ("Pulteney Bridge", "view", "VIEWPOINT"),
            ("Thermae Bath Spa", "art", "LANDMARK"),
            ("Royal Victoria Park", "green", "PARK"),
            ("Prior Park Landscape Garden", "green", "PARK"),
            ("Bath Assembly Rooms", "art", "MUSEUM"),
            ("Alexandra Park, Bath", "view", "VIEWPOINT"),
            ("Bath Guildhall Market", "food", "MARKET"),
            ("Milsom Street", "square", "AREA"),
        ],
    },
    "coventry": {
        "centre": (-1.5090, 52.4068), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Coventry Cathedral", "art", "LANDMARK"),
            ("Coventry Transport Museum", "art", "MUSEUM"),
            ("Herbert Art Gallery and Museum", "art", "MUSEUM"),
            ("Lady Godiva statue", "square", "AREA"),
            ("FarGo Village", "night", "AREA"),
            ("War Memorial Park, Coventry", "green", "PARK"),
            ("Coventry Market", "food", "MARKET"),
            ("Spon Street", "square", "AREA"),
            ("Coventry Building Society Arena", "art", "LANDMARK"),
        ],
    },
    "southampton": {
        "centre": (-1.4044, 50.9097), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("SeaCity Museum", "art", "MUSEUM"),
            ("Tudor House, Southampton", "art", "MUSEUM"),
            ("Southampton City Art Gallery", "art", "MUSEUM"),
            ("Southampton Old Town Walls", "art", "LANDMARK"),
            ("Ocean Village", "square", "AREA"),
            ("Oxford Street, Southampton", "night", "AREA"),
            ("Southampton Common", "green", "PARK"),
            ("Mayflower Park", "green", "PARK"),
            ("Bargate", "art", "LANDMARK"),
            ("St Mary's Stadium", "art", "LANDMARK"),
        ],
    },
    "portsmouth": {
        "centre": (-1.0880, 50.8198), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Spinnaker Tower", "view", "VIEWPOINT"),
            ("Portsmouth Historic Dockyard", "art", "MUSEUM"),
            ("HMS Victory", "art", "LANDMARK"),
            ("Mary Rose Museum", "art", "MUSEUM"),
            ("Gunwharf Quays", "square", "AREA"),
            ("Southsea Common", "green", "PARK"),
            ("Old Portsmouth", "square", "AREA"),
            ("Albert Road, Portsmouth", "night", "AREA"),
            ("Charles Dickens' Birthplace Museum", "art", "MUSEUM"),
            ("Southsea Castle", "art", "LANDMARK"),
        ],
    },
    "plymouth": {
        "centre": (-4.1427, 50.3755), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Plymouth Hoe", "view", "VIEWPOINT"),
            ("Smeaton's Tower", "view", "VIEWPOINT"),
            ("Barbican, Plymouth", "square", "AREA"),
            ("Royal William Yard", "square", "AREA"),
            ("The Box, Plymouth", "art", "MUSEUM"),
            ("National Marine Aquarium", "art", "MUSEUM"),
            ("Mayflower Steps", "art", "LANDMARK"),
            ("Central Park, Plymouth", "green", "PARK"),
            ("Union Street, Plymouth", "night", "AREA"),
            ("Plymouth Market", "food", "MARKET"),
        ],
    },
    "derby": {
        "centre": (-1.4746, 52.9228), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Derby Cathedral", "art", "LANDMARK"),
            ("Derby Museum and Art Gallery", "art", "MUSEUM"),
            ("Derby Silk Mill", "art", "MUSEUM"),
            ("Markeaton Park", "green", "PARK"),
            ("Darley Park", "green", "PARK"),
            ("Derby Market Hall", "food", "MARKET"),
            ("Cathedral Quarter, Derby", "square", "AREA"),
            ("Pride Park Stadium", "art", "LANDMARK"),
            ("Friar Gate", "night", "AREA"),
        ],
    },
    "norwich": {
        "centre": (1.2974, 52.6309), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Norwich Cathedral", "art", "LANDMARK"),
            ("Norwich Castle", "art", "MUSEUM"),
            ("Elm Hill", "square", "AREA"),
            ("Norwich Market", "food", "MARKET"),
            ("The Forum, Norwich", "square", "AREA"),
            ("Chapelfield Gardens", "green", "PARK"),
            ("Eaton Park", "green", "PARK"),
            ("Prince of Wales Road", "night", "AREA"),
            ("Sainsbury Centre for Visual Arts", "art", "MUSEUM"),
            ("Norwich Lanes", "square", "AREA"),
        ],
    },
    "leicester": {
        "centre": (-1.1398, 52.6369), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Leicester Cathedral", "art", "LANDMARK"),
            ("King Richard III Visitor Centre", "art", "MUSEUM"),
            ("New Walk Museum and Art Gallery", "art", "MUSEUM"),
            ("Leicester Guildhall", "art", "LANDMARK"),
            ("Jewry Wall", "art", "LANDMARK"),
            ("Golden Mile, Leicester", "square", "AREA"),
            ("Leicester Market", "food", "MARKET"),
            ("Abbey Park, Leicester", "green", "PARK"),
            ("Victoria Park, Leicester", "green", "PARK"),
            ("Cultural Quarter, Leicester", "night", "AREA"),
            ("Braunstone Gate", "night", "AREA"),
            ("King Power Stadium", "art", "LANDMARK"),
            ("National Space Centre", "art", "MUSEUM"),
        ],
    },
    "bristol": {
        "centre": (-2.5879, 51.4545), "lang": "en", "min_sitelinks": 10,
        "curated": [
            ("Clifton Suspension Bridge", "view", "VIEWPOINT"),
            ("SS Great Britain", "art", "MUSEUM"),
            ("Bristol Harbour", "square", "AREA"),
            ("St Nicholas Market", "food", "MARKET"),
            ("Clifton, Bristol", "square", "AREA"),
            ("Stokes Croft", "night", "AREA"),
            ("King Street, Bristol", "night", "AREA"),
            ("Ashton Court", "green", "PARK"),
            ("Brandon Hill", "view", "VIEWPOINT"),
            ("M Shed", "art", "MUSEUM"),
            ("Bristol Museum and Art Gallery", "art", "MUSEUM"),
            ("Bristol Cathedral", "art", "LANDMARK"),
            ("Gloucester Road, Bristol", "square", "AREA"),
            ("Queen Square, Bristol", "square", "AREA"),
        ],
    },
}


def http(url, timeout=120):
    res = subprocess.run(["curl", "-sS", "--max-time", str(timeout), "-A", UA, url],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200])
    return json.loads(res.stdout)


def km(a, b, c, d):
    dy = (a - c) * 111.32
    dx = (b - d) * 111.32 * math.cos(math.radians((a + c) / 2))
    return math.hypot(dx, dy)


def notable(lon, lat, min_sitelinks, radius=6):
    q = """
SELECT ?item ?itemLabel ?sitelinks ?lat ?lon WHERE {
  SERVICE wikibase:around {
    ?item wdt:P625 ?loc .
    bd:serviceParam wikibase:center "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "%d" .
  }
  ?item wikibase:sitelinks ?sitelinks . FILTER(?sitelinks >= %d)
  ?item p:P625/psv:P625 ?c . ?c wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q3957 }      # not a town
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q515 }       # not a city
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q548662 }    # not a civil parish
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q55488 }     # not a railway station
  FILTER NOT EXISTS { ?item wdt:P31/wdt:P279* wd:Q1248784 }   # not an airport
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} ORDER BY DESC(?sitelinks) LIMIT 60""" % (lon, lat, radius, min_sitelinks)
    url = WDQS + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    rows = http(url, timeout=180)["results"]["bindings"]
    out = []
    for b in rows:
        out.append({"qid": b["item"]["value"].rsplit("/", 1)[1],
                    "name": b["itemLabel"]["value"],
                    "sitelinks": int(b["sitelinks"]["value"]),
                    "lat": float(b["lat"]["value"]), "lon": float(b["lon"]["value"])})
    return out


def resolve(name, lang, lon0, lat0):
    u = API + "?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": name,
        "language": lang, "uselang": lang, "format": "json", "limit": 8, "type": "item"})
    ids = [h["id"] for h in http(u, timeout=60).get("search", [])]
    if not ids:
        return None
    u2 = API + "?" + urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids),
        "props": "labels|claims|sitelinks", "languages": "en", "format": "json"})
    ents = http(u2, timeout=60).get("entities", {})
    for qid in ids:
        e = ents.get(qid, {})
        cl = e.get("claims", {}).get("P625")
        if not cl:
            continue
        v = cl[0]["mainsnak"].get("datavalue", {}).get("value", {})
        lat, lon = v.get("latitude"), v.get("longitude")
        if lat is None or km(lat, lon, lat0, lon0) > 12:
            continue
        return {"qid": qid, "lat": lat, "lon": lon,
                "name": (e.get("labels", {}).get("en") or {}).get("value", name),
                "sitelinks": len(e.get("sitelinks", {}))}
    return None


def main(key):
    cfg = CITIES[key]
    lon0, lat0 = cfg["centre"]
    picked = []

    def add(entry, cat, ptype, why):
        d = km(entry["lat"], entry["lon"], lat0, lon0)
        if d > 12:
            print("  scarto %-38s %.1f km fuori" % (entry["name"][:38], d)); return
        for p in picked:
            if km(entry["lat"], entry["lon"], p["lat"], p["lon"]) * 1000 < 60:
                print("  scarto %-38s a 60 m da %s" % (entry["name"][:38], p["name"])); return
            if p["qid"] == entry["qid"]:
                return
        picked.append({"name": entry["name"], "category": cat, "qid": entry["qid"],
                       "lat": round(entry["lat"], 5), "lon": round(entry["lon"], 5),
                       "poi_type": ptype, "status": "OPEN", "map_priority": 3,
                       "sitelinks": entry.get("sitelinks", 0)})
        print("  %-6s %-38s %-11s sl=%-3d %.1f km" % (why, entry["name"][:38], entry["qid"],
                                                      entry.get("sitelinks", 0), d))

    print("== %s: curati" % key)
    for name, cat, ptype in cfg["curated"]:
        e = resolve(name, cfg["lang"], lon0, lat0)
        if not e:
            print("  MANCA  %s" % name); continue
        add(e, cat, ptype, "cur")
        time.sleep(0.3)

    # The proximity ranking stays, but only to suggest. Ranking English
    # Wikipedia by sitelinks around Birmingham returns the county, two
    # universities, a stadium in another borough and the 1998 Eurovision Song
    # Contest before it returns anything a visitor would walk to. It is a good
    # way to notice something missing and a bad way to choose pins, so what it
    # finds is printed for review and nothing is written from it.
    if "--suggest" in sys.argv:
        print("== %s: suggerimenti da Wikidata (non scritti)" % key)
        have = {p["qid"] for p in picked}
        for e in notable(lon0, lat0, cfg["min_sitelinks"]):
            if e["qid"] not in have:
                print("  ? %-40s %-11s sl=%d" % (e["name"][:40], e["qid"], e["sitelinks"]))

    picked.sort(key=lambda p: -p["sitelinks"])
    for i, p in enumerate(picked, 1):
        p["rank"] = i
        p.pop("sitelinks", None)
    dest = os.path.join(POI_DIR, "%s.json" % key)
    json.dump({"city": key, "pois": picked}, open(dest, "w"), ensure_ascii=False, indent=1)
    cats = {}
    for p in picked:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    print("\n%s: %d pin %s -> %s" % (key, len(picked), cats, dest))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "birmingham")
