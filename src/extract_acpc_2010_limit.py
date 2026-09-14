#!/usr/bin/env python3
"""Extract only ACPC 2010 heads-up LIMIT logs from the remote Zenodo ZIP.

Uses two HTTP Range downloads for the contiguous 2P_LIMIT archive spans instead
of downloading the full 20.3 GB ZIP.
"""
from __future__ import annotations

import argparse
import binascii
import os
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED

import requests
from remotezip import RemoteZip

URL = "https://zenodo.org/records/17136841/files/poker-hand-histories.zip?download=1"
PREFIX = "data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT/"
OUT_DIR = Path("data/raw/acpc_2010_2p_limit")
LOCAL_HEADER = b"PK\x03\x04"
HEADER_STRUCT = "<4s5H3I2H"
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)


@dataclass(frozen=True)
class Member:
    name: str
    header_offset: int
    compress_size: int
    file_size: int
    compress_type: int
    crc: int


def is_candidate(name: str) -> bool:
    return name.startswith(PREFIX) and not name.endswith("/")


def load_members() -> list[Member]:
    with RemoteZip(URL) as zf:
        return sorted(
            [
                Member(i.filename, i.header_offset, i.compress_size, i.file_size, i.compress_type, i.CRC)
                for i in zf.infolist()
                if is_candidate(i.filename)
            ],
            key=lambda i: i.header_offset,
        )


def contiguous_blocks(members: list[Member]) -> list[tuple[int, int, list[Member]]]:
    blocks: list[tuple[int, int, list[Member]]] = []
    for member in members:
        # Local header + filename/extra is under 1 KB here; use 1 KB slack so each block contains it.
        end = member.header_offset + HEADER_SIZE + len(member.name.encode()) + 1024 + member.compress_size - 1
        if not blocks or member.header_offset > blocks[-1][1] + 1:
            blocks.append((member.header_offset, end, [member]))
            continue
        start, old_end, old_members = blocks[-1]
        blocks[-1] = (start, max(old_end, end), [*old_members, member])
    return blocks


def download_range(start: int, end: int, path: Path) -> None:
    headers = {"Range": f"bytes={start}-{end}"}
    with requests.get(URL, headers=headers, stream=True, timeout=60) as response:
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError(f"server did not honor Range request: HTTP {response.status_code}")
        with path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def member_payload(blob: bytes, member: Member, block_start: int) -> bytes:
    rel = member.header_offset - block_start
    header = blob[rel : rel + HEADER_SIZE]
    fields = struct.unpack(HEADER_STRUCT, header)
    if fields[0] != LOCAL_HEADER:
        raise RuntimeError(f"bad local header for {member.name}")
    name_len, extra_len = fields[-2], fields[-1]
    data_start = rel + HEADER_SIZE + name_len + extra_len
    return blob[data_start : data_start + member.compress_size]


def decompress_member(payload: bytes, member: Member) -> bytes:
    if member.compress_type == ZIP_STORED:
        data = payload
    elif member.compress_type == ZIP_DEFLATED:
        data = zlib.decompress(payload, -zlib.MAX_WBITS)
    else:
        raise RuntimeError(f"unsupported compression {member.compress_type} for {member.name}")
    if len(data) != member.file_size:
        raise RuntimeError(f"size mismatch for {member.name}")
    if binascii.crc32(data) & 0xFFFFFFFF != member.crc:
        raise RuntimeError(f"CRC mismatch for {member.name}")
    return data


def extract_block(block_start: int, part_path: Path, members: list[Member], out_dir: Path) -> None:
    blob = part_path.read_bytes()
    for index, member in enumerate(members, 1):
        rel_name = member.name.removeprefix(PREFIX)
        out_path = out_dir / rel_name
        if out_path.exists() and out_path.stat().st_size == member.file_size:
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = decompress_member(member_payload(blob, member, block_start), member)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out_path)
        if index % 1000 == 0:
            print(f"  extracted {index}/{len(members)} from current block", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--part", type=Path, help="existing downloaded range block")
    args = parser.parse_args()

    members = load_members()
    blocks = contiguous_blocks(members)
    print(f"files={len(members)}")
    print(f"compressed_bytes={sum(m.compress_size for m in members)}")
    print(f"uncompressed_bytes={sum(m.file_size for m in members)}")
    print(f"range_blocks={len(blocks)}")
    print(f"range_bytes={sum(end - start + 1 for start, end, _ in blocks)}")
    for start, end, block_members in blocks:
        print(f"range={start}-{end} files={len(block_members)} bytes={end - start + 1}")
    if args.dry_run:
        return

    args.out.mkdir(parents=True, exist_ok=True)
    if args.part:
        if len(blocks) != 1:
            raise RuntimeError("--part only supports a single planned range block")
        start, _end, block_members = blocks[0]
        print("extracting existing range block", flush=True)
        extract_block(start, args.part, block_members, args.out)
    else:
        with tempfile.TemporaryDirectory(prefix="acpc-2010-limit-") as tmpdir:
            for block_index, (start, end, block_members) in enumerate(blocks):
                part = Path(tmpdir) / f"block-{block_index}.bin"
                print(f"downloading block {block_index + 1}/{len(blocks)}", flush=True)
                download_range(start, end, part)
                print(f"extracting block {block_index + 1}/{len(blocks)}", flush=True)
                extract_block(start, part, block_members, args.out)
                part.unlink()
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
