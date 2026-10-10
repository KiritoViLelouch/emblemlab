"""Operator-only CSV/JSON ingestion; outputs reproducible, permission-bound artifacts."""

import argparse
import json
from pathlib import Path

from app.meta.providers import CsvProvider, JsonProvider, MAX_BYTES
from app.meta.repository import import_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--metadata", type=Path, help="CSV batch metadata JSON; no compositions field")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.file.stat().st_size > MAX_BYTES:
        parser.error("Export exceeds 2 MiB")
    if args.file.suffix.lower() not in (".csv", ".json"):
        parser.error("Only CSV/JSON authorized exports supported")
    content = args.file.read_bytes()
    metadata = json.loads(args.metadata.read_text()) if args.metadata else None
    provider = CsvProvider() if args.file.suffix.lower() == ".csv" else JsonProvider()
    export = provider.normalize(content, metadata)
    try:
        path = import_export(export, content, args.file.name, args.output_dir)
    except (ValueError, PermissionError, FileExistsError, RuntimeError) as exc:
        parser.error(str(exc))
    print(path)


if __name__ == "__main__":
    main()
