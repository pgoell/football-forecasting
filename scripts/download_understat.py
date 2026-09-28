# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Download Understat league data (EPL, Bundesliga) into data/raw/understat/.

Understat's robots.txt disallows all scripts; the project downloads anyway, by
the owner's decision, once per season at one request a second
(docs/data-sources.md). Each file is the JSON of
https://understat.com/getLeagueData/<league>/<start year>, stored unzipped.
Each run appends one line per file to _manifest.jsonl and rewrites
dbt/seeds/understat_files.csv, the committed record of the stored files, so
`git diff dbt/seeds/understat_files.csv` shows which files changed.

    uv run scripts/download_understat.py [--first 2014] [--last 2026]
"""

import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

LEAGUES = ["EPL", "Bundesliga"]
URL = "https://understat.com/getLeagueData/{league}/{year}"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "understat"
RECORD = ROOT / "dbt" / "seeds" / "understat_files.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first", type=int, default=2014, help="first season start year")
    parser.add_argument("--last", type=int, default=2026, help="last season start year")
    args = parser.parse_args()

    manifest = OUT / "_manifest.jsonl"
    record = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for league in LEAGUES:
        for year in range(args.first, args.last + 1):
            url = URL.format(league=league, year=year)
            # the endpoint answers 404 without this header
            request = urllib.request.Request(url, headers={"X-Requested-With": "XMLHttpRequest"})
            with urllib.request.urlopen(request, timeout=30) as resp:
                raw = resp.read()
            # gzipped even when not asked for
            body = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            json.loads(body)  # fail on anything but JSON
            path = OUT / league / f"{year}.json"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(body)
            sha256 = hashlib.sha256(body).hexdigest()
            record[(league, str(year))] = (sha256, len(body))
            entry = {
                "league": league,
                "season": year,
                "url": url,
                "path": str(path.relative_to(OUT)),
                "bytes": len(raw),
                "sha256_received": hashlib.sha256(raw).hexdigest(),
                "sha256": sha256,
                "ingested_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            with manifest.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            print(f"{league} {year}: {len(body):,} bytes")
            time.sleep(1)

    write_record(record)


def write_record(new: dict[tuple[str, str], tuple[str, int]]) -> None:
    """Merge this run's files into the committed record, sorted by league and season."""
    rows = {}
    if RECORD.exists():
        for line in RECORD.read_text().splitlines()[1:]:
            league, season, sha256, size = line.split(",")
            rows[(league, season)] = (sha256, int(size))
    rows |= new
    lines = ["league,season,sha256,bytes"]
    lines += [f"{lg},{ss},{h},{n}" for (lg, ss), (h, n) in sorted(rows.items())]
    RECORD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
