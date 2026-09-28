# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Download martj42/international_results (CC0) into data/raw/international-results/.

The four CSVs come from raw.githubusercontent.com at one pinned commit, so a
rerun fetches the same bytes. Files are stored as UTF-8 with Unix line endings.
Each run appends one line per file to _manifest.jsonl (sha256 of the bytes as
downloaded, and the commit) and rewrites dbt/seeds/international_results_files.csv,
the committed record of the stored files. To move to a newer commit, pass
--commit and commit the changed seed.

    uv run scripts/download_international_results.py [--commit <sha>]
"""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

COMMIT = "394fe81893b062fbc2cf6257e988ac7cc4c039a1"  # master on 2026-09-28
URL = "https://raw.githubusercontent.com/martj42/international_results/{commit}/{file}"
FILES = ["results.csv", "goalscorers.csv", "shootouts.csv", "former_names.csv"]
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "international-results"
RECORD = ROOT / "dbt" / "seeds" / "international_results_files.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commit", default=COMMIT, help="martj42 commit sha")
    args = parser.parse_args()

    manifest = OUT / "_manifest.jsonl"
    lines = ["file,sha256,bytes"]
    OUT.mkdir(parents=True, exist_ok=True)
    for file in FILES:
        url = URL.format(commit=args.commit, file=file)
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read()
        text = body.decode("utf-8-sig").replace("\r\n", "\n")
        path = OUT / file
        path.write_text(text, encoding="utf-8", newline="\n")
        stored = text.encode("utf-8")
        lines.append(f"{file},{hashlib.sha256(stored).hexdigest()},{len(stored)}")
        entry = {
            "file": file,
            "commit": args.commit,
            "url": url,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "ingested_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with manifest.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"{file}: {len(body):,} bytes")
        time.sleep(1)

    RECORD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
