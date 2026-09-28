import json, re, sys

sys.path.insert(0, ".")
from fetch import get


def txt(b):
    s = b.decode("latin1")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


out = []
d = json.load(open("cdx/football-data_co_uk_notes_txt.json"))[1:]
for r in d:
    b = get(r[1], r[0])
    if not b:
        continue
    s = txt(b)
    hits = set(
        m.group(0)
        for m in re.finditer(r"[^.]{0,200}(collected|Friday|Tuesday|kick-?off)[^.]{0,200}", s, re.I)
    )
    print("NOTES", r[1], "|".join(sorted(hits))[:900])
d = json.load(open("cdx/football-data_co_uk_matches_php.json"))[1:]
seen = set()
for r in d:
    k = r[1][:4] + ("a" if r[1][4:6] < "07" else "b")
    if k in seen:
        continue
    seen.add(k)
    b = get(r[1], r[0])
    if not b:
        continue
    s = txt(b)
    hits = set(
        m.group(0)
        for m in re.finditer(r"[^.]{0,250}(collected|Fridays?|Tuesdays?)[^.]{0,250}", s, re.I)
    )
    print("MATCHES", r[1], "|".join(sorted(hits))[:900])
