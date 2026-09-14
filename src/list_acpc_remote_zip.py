#!/usr/bin/env python3
"""List candidate ACPC files from the remote PHH archive without full download."""
from __future__ import annotations

from pathlib import PurePosixPath

from remotezip import RemoteZip

URL = "https://zenodo.org/records/17136841/files/poker-hand-histories.zip?download=1"


def is_candidate(name: str) -> bool:
    lower = name.lower()
    return "/2010/logs/acpc_2010_2plimit/2p_limit/" in lower and not lower.endswith("/")


def main() -> None:
    with RemoteZip(URL) as zf:
        infos = zf.infolist()

    names = [info.filename for info in infos]
    dirs_2010 = sorted({
        str(PurePosixPath(name).parent)
        for name in names
        if "/2010/" in name.lower()
    })
    candidates = [info for info in infos if is_candidate(info.filename)]
    total_compressed = sum(info.compress_size for info in candidates)
    total_uncompressed = sum(info.file_size for info in candidates)

    print("2010 directories:")
    for dirname in dirs_2010:
        print(dirname)

    print("\nCandidate 2010 HU-limit files:")
    for info in candidates:
        print(f"{info.filename}\tcompressed={info.compress_size}\tuncompressed={info.file_size}")

    print("\nTotals:")
    print(f"candidate_files={len(candidates)}")
    print(f"compressed_bytes={total_compressed}")
    print(f"uncompressed_bytes={total_uncompressed}")


if __name__ == "__main__":
    main()
