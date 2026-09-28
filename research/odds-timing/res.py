# /// script
# dependencies = ["xlrd"]
# ///
import json, re, sys, io, csv, datetime as dt

sys.path.insert(0, ".")
import fix
from fetch import get

# name fallback
_orig = fix.load


def find(div, d, h, a):
    for ss in {fix.season(d), fix.season(d - dt.timedelta(days=45))}:
        m = fix.load(div, ss)
        r = m.get((d, h, a))
        if r:
            return r
        for (dd, hh, aa), v in m.items():
            if (
                abs((dd - d).days) <= 3
                and hh[:4].lower() == h[:4].lower()
                and aa[:4].lower() == a[:4].lower()
            ):
                return v


def rows_from(b, url):
    if url.endswith(".xls"):
        import xlrd

        try:
            wb = xlrd.open_workbook(file_contents=b)
        except Exception as e:
            return None
        out = []
        for sh in wb.sheets():
            if sh.nrows < 2:
                continue
            hdr = [str(c).strip() for c in sh.row_values(0)]
            for i in range(1, sh.nrows):
                v = sh.row_values(i)
                r = dict(zip(hdr, v))
                if isinstance(r.get("Date"), float):
                    r["Date"] = xlrd.xldate_as_datetime(r["Date"], wb.datemode).strftime("%d/%m/%Y")
                r = {k: ("" if x == "" else str(x)) for k, x in r.items()}
                out.append(r)
        return out
    t = b.decode("utf-8-sig", errors="replace")
    if not t.lstrip().startswith("Div"):
        return None
    return [
        {(k or "").strip(): (v or "") for k, v in r.items()} for r in csv.DictReader(io.StringIO(t))
    ]


def analyse(ts, url, kind):
    b = get(ts, url)
    if not b:
        return [dict(ts=ts, kind=kind, url=url, err="fetch")]
    rows = rows_from(b, url)
    if rows is None:
        return [dict(ts=ts, kind=kind, url=url, err="parse")]
    T = dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    out = []
    for r in rows:
        div = r.get("Div", "").strip()
        if div not in ("E0", "D1"):
            continue
        d = fix.pdate(r.get("Date", ""))
        if not d:
            continue
        f = find(div, d, r.get("HomeTeam", "").strip(), r.get("AwayTeam", "").strip())
        cols = [c for c in fix.ODDS if r.get(c, "").strip()]
        rec = dict(
            ts=ts,
            kind=kind,
            url=url,
            div=div,
            date=str(d),
            wd=d.strftime("%a"),
            home=r["HomeTeam"],
            away=r["AwayTeam"],
            ss=fix.season(d),
            T=T.isoformat(),
            rule=fix.rule(d).astimezone(dt.timezone.utc).isoformat(),
            T_ge_rule=T >= fix.rule(d),
            nodds=len(cols),
        )
        if f is None:
            rec["final"] = "missing"
        else:
            common = [c for c in cols if f.get(c, "").strip()]
            rec["ncommon"] = len(common)
            rec["diff"] = [(c, r[c], f[c]) for c in common if not fix.eq(r[c], f[c])]
            rec["final_has_more"] = [
                c for c in fix.ODDS if f.get(c, "").strip() and c in r and not r[c].strip()
            ]
        out.append(rec)
    return out


jobs = []
d = json.load(open("cdx/mmz.json"))[1:]
for o, t, s, g in d:
    m = re.search(r"mmz4281/(\d{4})/(E0|D1)\.csv", o)
    if m and m.group(1) < "9000":
        jobs.append(
            (t, f"http://www.football-data.co.uk/mmz4281/{m.group(1)}/{m.group(2)}.csv", "res")
        )
csvts = {r[0] for r in json.load(open("cdx/fixtures.csv.json"))[1:]}
for t in [
    "20050220085556",
    "20050504182817",
    "20050526065208",
    "20051210203105",
    "20051222191320",
    "20060210065320",
    "20060301050042",
    "20060624191608",
    "20061208155036",
    "20111027032719",
    "20120322173144",
    "20121023154239",
    "20140325073441",
    "20140708231959",
    "20151228042756",
    "20160316201120",
    "20160909073532",
    "20180508112351",
]:
    jobs.append((t, "http://www.football-data.co.uk/fixtures.xls", "fixxls"))
for r in json.load(open("cdx/fixtures.csv.json"))[1:]:
    jobs.append((r[0], "http://www.football-data.co.uk/fixtures.csv", "fix"))
jobs.append(("20210223124259", "http://www.football-data.co.uk/fixtures", "fix"))
res = []
for j in jobs:
    res += analyse(*j)
json.dump(res, open("res_res.json", "w"), default=str)
print("done", len(jobs))
