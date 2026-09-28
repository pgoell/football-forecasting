# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Download Football-Data CSVs for E0 and D1 into data/raw/football-data/.

Files are stored as UTF-8 with Unix line endings: a few old seasons come in
Windows-1252, newer ones with a BOM. Each run overwrites the files and appends
one line per file to _manifest.jsonl (sha256 of the bytes as downloaded), so we
know what was fetched when.

It also rewrites dbt/seeds/football_data_files.csv, the committed record of the
stored files (sha256 of the UTF-8 text dbt reads). After a download,
`git diff dbt/seeds/football_data_files.csv` shows which files differ from the
data version the repo was built with.

    uv run scripts/download_football_data.py [--first 2000] [--last 2026]
"""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

LEAGUES = ["E0", "D1"]
URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "football-data"
RECORD = ROOT / "dbt" / "seeds" / "football_data_files.csv"


def season_code(start_year: int) -> str:
    """2000 -> '0001', 2026 -> '2627'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def to_utf8(body: bytes) -> str:
    """Decode UTF-8 (with or without BOM), falling back to Windows-1252."""
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    return text.replace("\r\n", "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first", type=int, default=2000, help="first season start year")
    parser.add_argument("--last", type=int, default=2026, help="last season start year")
    args = parser.parse_args()

    manifest = OUT / "_manifest.jsonl"
    record = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for league in LEAGUES:
        for year in range(args.first, args.last + 1):
            season = season_code(year)
            url = URL.format(season=season, league=league)
            with urllib.request.urlopen(url, timeout=30) as resp:
                body = resp.read()
            path = OUT / league / f"{season}.csv"
            path.parent.mkdir(exist_ok=True)
            text = to_utf8(body)
            path.write_text(text, encoding="utf-8", newline="\n")
            stored = text.encode("utf-8")
            record[(league, season)] = (hashlib.sha256(stored).hexdigest(), len(stored))
            entry = {
                "league": league,
                "season": season,
                "url": url,
                "path": str(path.relative_to(OUT)),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "ingested_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            with manifest.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            print(f"{league} {season}: {len(body):,} bytes")
            time.sleep(1)  # be polite to a free site

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
