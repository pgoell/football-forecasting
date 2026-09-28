# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Download eloratings.net results files into data/raw/eloratings/.

eloratings.net states no terms; the project uses the files for private research
only, at one request a second (docs/tournament-spec.md, docs/data-sources.md).
Files: <year>_results.tsv for each year (every match, with ratings), and the
lookups the site's scripts/ratings.js loads: en.teams.tsv (code to name),
teams.tsv (old code to current code), en.tournaments.tsv (code to name).
Stored as UTF-8 with Unix line endings. Each run appends one line per file to
_manifest.jsonl (sha256 of the bytes as downloaded) and rewrites
dbt/seeds/eloratings_files.csv, the committed record of the stored files.

    uv run scripts/download_eloratings.py [--first 2004] [--last 2026]
"""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URL = "https://www.eloratings.net/{file}"
LOOKUPS = ["en.teams.tsv", "teams.tsv", "en.tournaments.tsv"]
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "eloratings"
RECORD = ROOT / "dbt" / "seeds" / "eloratings_files.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first", type=int, default=2004, help="first year")
    parser.add_argument("--last", type=int, default=2026, help="last year")
    args = parser.parse_args()

    files = LOOKUPS + [f"{y}_results.tsv" for y in range(args.first, args.last + 1)]
    manifest = OUT / "_manifest.jsonl"
    record = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for file in files:
        url = URL.format(file=file)
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read()
        text = body.decode("utf-8-sig").replace("\r\n", "\n")
        (OUT / file).write_text(text, encoding="utf-8", newline="\n")
        stored = text.encode("utf-8")
        record[file] = (hashlib.sha256(stored).hexdigest(), len(stored))
        entry = {
            "file": file,
            "url": url,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "ingested_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with manifest.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"{file}: {len(body):,} bytes")
        time.sleep(1)

    write_record(record)


def write_record(new: dict[str, tuple[str, int]]) -> None:
    """Merge this run's files into the committed record, sorted by file name."""
    rows = {}
    if RECORD.exists():
        for line in RECORD.read_text().splitlines()[1:]:
            file, sha256, size = line.split(",")
            rows[file] = (sha256, int(size))
    rows |= new
    lines = ["file,sha256,bytes"]
    lines += [f"{f},{h},{n}" for f, (h, n) in sorted(rows.items())]
    RECORD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
