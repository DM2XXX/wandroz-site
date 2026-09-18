"""
Tell Bing (and Yandex, Seznam, Naver) that these pages exist.

WHY THIS IS NEEDED AND GOOGLE IS NOT
    Google found the site on its own: a site: query returns the area pages, days
    after the canonical fix. Bing and DuckDuckGo return exactly one result, the
    homepage. Nothing technical explains it — robots.txt allows everything, the
    sitemap is declared in it, bingbot gets a 200 and no page carries a noindex.
    Bing has simply not crawled, and an entire search engine being closed to
    2,000 pages is worth one HTTP request to fix.

    Bing Webmaster Tools would do it too, but it needs an account only the owner
    can create. IndexNow needs a key hosted on the domain, which the build now
    publishes, so this can run unattended.

WHAT IT SUBMITS
    Only URLs already listed in the site's own public sitemap — the same list
    robots.txt has been pointing crawlers at since the site went up. This is the
    same request through a faster channel, not new exposure.

    python3 submit_indexnow.py            # dry run: prints what it would send
    python3 submit_indexnow.py --send
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "www.wandroz.com"
STATIC = os.path.join(HERE, "static")
ENDPOINT = "https://api.indexnow.org/IndexNow"
UA = "Mozilla/5.0 (compatible; wandroz-indexnow/1.0; +https://www.wandroz.com)"
BATCH = 10000          # IndexNow accepts up to 10,000 URLs per request


def find_key():
    """The key is the name of the key file the build publishes at the site root."""
    keys = [f[:-4] for f in os.listdir(STATIC)
            if re.fullmatch(r"[0-9a-f]{32}\.txt", f)]
    if len(keys) != 1:
        raise SystemExit("expected exactly one IndexNow key file in static/, found %d" % len(keys))
    return keys[0]


def sitemap_urls():
    path = os.path.join(HERE, "..", "dist", "sitemap.xml")
    with open(path) as f:
        return re.findall(r"<loc>([^<]+)</loc>", f.read())


def main(send):
    key = find_key()
    urls = sitemap_urls()
    print("host %s, key %s, %d URLs in the sitemap" % (HOST, key, len(urls)))
    # The key has to be reachable before the submission means anything: the
    # engine fetches it to prove we control the host. Submitting first and
    # publishing the key later looks, from the outside, exactly like someone
    # submitting a domain they do not own.
    probe = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "https://%s/%s.txt" % (HOST, key)], capture_output=True, text=True)
    print("key file at https://%s/%s.txt -> HTTP %s" % (HOST, key, probe.stdout))
    if probe.stdout.strip() != "200":
        raise SystemExit("the key is not live yet — release the build first, then submit")

    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        body = json.dumps({"host": HOST, "key": key,
                           "keyLocation": "https://%s/%s.txt" % (HOST, key),
                           "urlList": chunk})
        if not send:
            print("would POST %d URLs (%s ... %s)" % (len(chunk), chunk[0], chunk[-1]))
            continue
        # The User-Agent is not optional: without one the endpoint answers 403,
        # which reads like a rejected key and is not. With it, the same request
        # and the same key file are accepted.
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "-X", "POST", "-A", UA,
                            "-H", "Content-Type: application/json; charset=utf-8",
                            "--data-binary", "@-", ENDPOINT],
                           input=body, capture_output=True, text=True)
        # 200 accepted, 202 accepted-pending-key-validation. Anything else is
        # worth reading rather than retrying blind.
        print("POST %d URLs -> HTTP %s" % (len(chunk), r.stdout))


if __name__ == "__main__":
    main("--send" in sys.argv)
