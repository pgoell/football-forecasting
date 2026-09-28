import pathlib
import json, csv, io, sys, datetime as dt, glob
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
from fetch import get

L = ZoneInfo("Europe/London")
U = dt.timezone.utc
R = str(pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "football-data")


def pdate(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s.strip(), f).date()
        except:
            pass


def season(d):
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


final = {}


def load(div, ss):
    k = (div, ss)
    if k not in final:
        m = {}
        try:
            for r in csv.DictReader(
                open(f"{R}/{div}/{ss}.csv", encoding="utf-8", errors="replace")
            ):
                if r.get("Date"):
                    m[(pdate(r["Date"]), r["HomeTeam"].strip(), r["AwayTeam"].strip())] = r
        except FileNotFoundError:
            pass
        final[k] = m
    return final[k]


def rule(d):
    wd = d.weekday()  # Mon0
    if wd in (4, 5, 6, 0):
        back = {4: 0, 5: 1, 6: 2, 0: 3}[wd]
        h = 17
    else:
        back = {1: 0, 2: 1, 3: 2}[wd]
        h = 13
    x = d - dt.timedelta(days=back)
    return dt.datetime(x.year, x.month, x.day, h, tzinfo=L)


ODDS = [
    "B365H",
    "B365D",
    "B365A",
    "BWH",
    "BWD",
    "BWA",
    "IWH",
    "IWD",
    "IWA",
    "WHH",
    "WHD",
    "WHA",
    "PSH",
    "PSD",
    "PSA",
    "VCH",
    "VCD",
    "VCA",
    "GBH",
    "GBD",
    "GBA",
    "LBH",
    "LBD",
    "LBA",
    "SBH",
    "SBD",
    "SBA",
    "SJH",
    "SJD",
    "SJA",
]


def eq(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-6
    except:
        return (a or "").strip() == (b or "").strip()


def analyse(ts, url, kind):
    b = get(ts, url)
    if not b:
        return []
    T = dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=U)
    txt = b.decode("utf-8-sig", errors="replace")
    if not txt.lstrip().startswith(("Div", "﻿Div")):
        return [dict(ts=ts, kind=kind, err="notcsv:" + txt[:40].replace("\n", " "))]
    out = []
    for r in csv.DictReader(io.StringIO(txt)):
        r = {(k or "").strip(): (v or "") for k, v in r.items()}
        div = r.get("Div", "").strip()
        if div not in ("E0", "D1"):
            continue
        d = pdate(r.get("Date", ""))
        if not d:
            continue
        ss = season(d)
        f = load(div, ss).get((d, r["HomeTeam"].strip(), r["AwayTeam"].strip()))
        cols = [c for c in ODDS if c in r and r[c].strip()]
        rec = dict(
            ts=ts,
            kind=kind,
            div=div,
            date=str(d),
            wd=d.strftime("%a"),
            home=r["HomeTeam"].strip(),
            away=r["AwayTeam"].strip(),
            ss=ss,
            T=T.isoformat(),
            rule=rule(d).astimezone(U).isoformat(),
            T_ge_rule=T >= rule(d),
            nodds=len(cols),
            kick_after_T=(d > T.date()),
        )
        if f is None:
            rec["final"] = "missing"
        else:
            common = [c for c in cols if c in f and f[c].strip()]
            diff = [(c, r[c], f[c]) for c in common if not eq(r[c], f[c])]
            rec.update(ncommon=len(common), diff=diff, Ttime=r.get("Time", ""))
        out.append(rec)
    return out


if __name__ == "__main__":
    res = []
    for r in json.load(open("cdx/fixtures.csv.json"))[1:]:
        res += analyse(r[0], "http://www.football-data.co.uk/fixtures.csv", "fix")
    json.dump(res, open("fix_res.json", "w"), default=str)
