#!/usr/bin/env python3
"""Inspect downloaded Pluribus/ACPC files without unpacking everything."""

from __future__ import annotations

import argparse
import gzip
import tarfile
import zipfile
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".log", ".phh", ".phhs", ".csv", ".json", ".jsonl"}


def head_bytes(path: Path, limit: int) -> bytes:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as file:
        return file.read(limit)


def preview_bytes(data: bytes) -> str:
    return data.decode("utf-8", "replace").replace("\r", "")[:2000]


def inspect_zip(path: Path, limit: int) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        print(f"  zip entries: {len(names)}")
        for name in names[:limit]:
            info = archive.getinfo(name)
            print(f"  - {name} ({info.file_size} bytes)")
        sample = next((name for name in names if Path(name).suffix.lower() in TEXT_SUFFIXES), None)
        if sample:
            print(f"  sample: {sample}")
            print(preview_bytes(archive.read(sample)[:4096]))


def inspect_tar(path: Path, limit: int) -> None:
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        print(f"  tar entries: {len(members)}")
        for member in members[:limit]:
            print(f"  - {member.name} ({member.size} bytes)")
        sample = next((m for m in members if Path(m.name).suffix.lower() in TEXT_SUFFIXES and m.isfile()), None)
        if sample:
            extracted = archive.extractfile(sample)
            if extracted:
                print(f"  sample: {sample.name}")
                print(preview_bytes(extracted.read(4096)))


def inspect_file(path: Path, limit: int) -> None:
    print(f"\n{path} ({path.stat().st_size} bytes)")
    name = path.name.lower()
    if zipfile.is_zipfile(path):
        inspect_zip(path, limit)
    elif tarfile.is_tarfile(path):
        inspect_tar(path, limit)
    elif path.suffix.lower() in TEXT_SUFFIXES or name.endswith(".txt.gz") or name.endswith(".log.gz"):
        print(preview_bytes(head_bytes(path, 4096)))
    else:
        print("  binary/unknown; no preview")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("data/raw"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert preview_bytes(b"abc") == "abc"
        print("ok")
        return
    files = [p for p in args.root.rglob("*") if p.is_file()]
    if not files:
        print(f"no files under {args.root}")
        return
    for path in files:
        inspect_file(path, args.limit)


if __name__ == "__main__":
    main()
