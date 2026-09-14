#!/usr/bin/env python3
"""Plan byte-range extraction for ACPC 2010 2P LIMIT files."""
from __future__ import annotations

from remotezip import RemoteZip

URL = "https://zenodo.org/records/17136841/files/poker-hand-histories.zip?download=1"
PREFIX = "data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT/"


def is_candidate(name: str) -> bool:
    return name.startswith(PREFIX) and not name.endswith("/")


def main() -> None:
    with RemoteZip(URL) as zf:
        infos = zf.infolist()
    candidates = sorted([i for i in infos if is_candidate(i.filename)], key=lambda i: i.header_offset)
    all_infos = sorted(infos, key=lambda i: i.header_offset)
    next_offsets = {info.header_offset: (all_infos[n + 1].header_offset if n + 1 < len(all_infos) else None) for n, info in enumerate(all_infos)}

    # Span each member through the next local header. Includes local header + compressed payload + possible descriptor.
    spans = []
    for info in candidates:
        end = next_offsets[info.header_offset]
        if end is not None:
            spans.append((info.header_offset, end - 1, info.filename))
    blocks = []
    for start, end, name in spans:
        if not blocks or start != blocks[-1][1] + 1:
            blocks.append([start, end, 1])
        else:
            blocks[-1][1] = end
            blocks[-1][2] += 1

    print(f"candidate_files={len(candidates)}")
    print(f"compressed_bytes={sum(i.compress_size for i in candidates)}")
    print(f"uncompressed_bytes={sum(i.file_size for i in candidates)}")
    print(f"range_blocks={len(blocks)}")
    print(f"range_span_bytes={sum(end-start+1 for start,end,_ in blocks)}")
    print("first_candidate", candidates[0].filename, candidates[0].header_offset)
    print("last_candidate", candidates[-1].filename, candidates[-1].header_offset)
    print("blocks:")
    for start, end, count in blocks[:20]:
        print(f"{start}-{end} files={count} bytes={end-start+1}")
    if len(blocks) > 20:
        print(f"... {len(blocks)-20} more blocks")


if __name__ == "__main__":
    main()
