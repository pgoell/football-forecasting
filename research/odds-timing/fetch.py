import sys, os, time, urllib.request, hashlib

S = os.path.dirname(os.path.abspath(__file__))


def get(ts, url):
    p = os.path.join(S, "cache", hashlib.md5((ts + url).encode()).hexdigest())
    if os.path.exists(p):
        return open(p, "rb").read()
    for i in range(4):
        try:
            time.sleep(1.2)
            r = urllib.request.urlopen(
                f"http://web.archive.org/web/{ts}id_/{url}", timeout=60
            ).read()
            open(p, "wb").write(r)
            return r
        except Exception as e:
            print("ERR", ts, url, e, file=sys.stderr)
            time.sleep(5)
    return None
