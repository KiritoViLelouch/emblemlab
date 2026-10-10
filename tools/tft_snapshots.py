"""Re-fetch pinned public static snapshots, or verify icon references; never scrape websites."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def fetch_snapshot(entry, directory):
    url = entry["url"]
    if (
        urlparse(url).netloc
        not in {"raw.communitydragon.org", "ddragon.leagueoflegends.com"}
        or "/latest/" in url
    ):
        raise ValueError("Only pinned public static hosts allowed")
    with urlopen(url, timeout=90) as response:
        content = response.read(60 * 1024 * 1024)
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError(
            "Remote content changed: use the committed snapshot, do not overwrite the manifest"
        )
    target = directory / entry["filename"]
    if target.parent != directory or not target.name.endswith(".json"):
        raise ValueError("Unsafe snapshot path")
    target.write_bytes(content)
    return dict(filename=target.name, sha256=entry["sha256"])


def verify_icon(url):
    try:
        with urlopen(Request(url, method="HEAD"), timeout=25) as response:
            return dict(
                url=url,
                status=response.status,
                content_type=response.headers.get("Content-Type"),
            )
    except Exception as exc:
        return dict(url=url, error=str(exc))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download", "icons"])
    parser.add_argument("--manifest", default="data/manifests/tft_set18_18_4.json")
    parser.add_argument("--catalog", default="data/catalogs/tft/set18_18_4.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / args.manifest).read_text())
    if args.action == "download":
        directory = ROOT / manifest["snapshot_directory"]
        directory.mkdir(parents=True, exist_ok=True)
        # versions.json is a discovery record, not an immutable resource. Keep its cached copy.
        entries = [e for e in manifest["snapshots"] if e["filename"] != "versions.json"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda e: fetch_snapshot(e, directory), entries))
    else:
        catalog = json.loads((ROOT / args.catalog).read_text())
        urls = sorted(
            {
                e["icon_path"]
                for kind in ["champions", "traits", "emblems"]
                for e in catalog[kind]
            }
        )
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(verify_icon, urls))
        report = dict(
            verified_at=datetime.now(timezone.utc).isoformat(), results=results
        )
        (ROOT / "data/manifests/tft_set18_icons.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    print(
        json.dumps(
            dict(total=len(results), failures=[r for r in results if "error" in r]),
            indent=2,
        )
    )
