#!/usr/bin/env python3
"""Download the external poker datasets used by this repo.

Raw files go under data/raw/ (gitignored). Zenodo sometimes blocks automated
requests; when that happens this prints the exact record URL to download by hand.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

DATASETS = {
    "pluribus": "17136841",
    "acpc": "10796886",
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "poker-player-comparison/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def download(url: str, out: Path) -> None:
    if out.exists() and out.stat().st_size:
        print(f"skip existing {out}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "poker-player-comparison/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, out.open("wb") as file:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            file.write(chunk)
    print(f"downloaded {out}")


def download_record(name: str, out_dir: Path) -> None:
    record_id = DATASETS[name]
    record_url = f"https://zenodo.org/records/{record_id}"
    try:
        record = fetch_json(f"https://zenodo.org/api/records/{record_id}")
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"could not read Zenodo metadata for {name}: {exc}")
        print(f"download manually: {record_url}")
        return

    files = record.get("files", [])
    if not files:
        print(f"no files listed for {name}; check {record_url}")
        return
    for item in files:
        key = item["key"]
        url = item.get("links", {}).get("self") or item.get("links", {}).get("download")
        if not url:
            print(f"no download URL for {name}/{key}; check {record_url}")
            continue
        try:
            download(url, out_dir / name / key)
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"could not download {name}/{key}: {exc}")
            print(f"download manually: {record_url}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default="all", choices=[*DATASETS, "all"])
    parser.add_argument("--out-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert DATASETS["pluribus"] == "17136841"
        assert DATASETS["acpc"] == "10796886"
        print("ok")
        return
    names = DATASETS if args.dataset == "all" else [args.dataset]
    for name in names:
        download_record(name, args.out_dir)


if __name__ == "__main__":
    main()
