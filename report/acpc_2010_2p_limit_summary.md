# ACPC 2010 heads-up LIMIT remote ZIP pull

Source ZIP: https://zenodo.org/records/17136841/files/poker-hand-histories.zip?download=1

## Range support

`curl -I -L` reported `Content-Length: 20289230983`.

A 1 KiB test range returned `HTTP/1.1 206 PARTIAL_CONTENT` with:

- `accept-ranges: bytes`
- `content-range: bytes 0-1023/20289230983`

## Relevant 2010 directories

```text
data/annual-computer-poker-competition/competitions/2010/logs/3P_LIMIT
data/annual-computer-poker-competition/competitions/2010/logs/3P_LIMIT/post_aaai
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT/post_aaai
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PNOLIMIT
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PNOLIMIT/2P_NOLIMIT
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PNOLIMIT/2P_NOLIMIT/post_aaai
```

## Selected files

Selected prefix:

```text
data/annual-computer-poker-competition/competitions/2010/logs/acpc_2010_2PLIMIT/2P_LIMIT/
```

Full candidate listing with per-file compressed/uncompressed sizes:

- `report/acpc_2010_remote_zip_listing.txt`

Totals from central directory:

- files: 29,000 `.phhs`
- compressed bytes: 2,479,427,507
- uncompressed bytes: 32,168,970,209
- contiguous remote range used: `8516639143-11001579782`
- range bytes downloaded: 2,484,940,640

Extracted split:

- main `2P_LIMIT`: 20,620 files / 22,791,369,888 bytes
- `2P_LIMIT/post_aaai`: 8,380 files / 9,377,600,321 bytes

## Local extraction

Extracted to:

```text
data/raw/acpc_2010_2p_limit/
```

Verification:

```text
files 29000
bytes 32168970209
```

The full 20.3 GB archive was not downloaded.
