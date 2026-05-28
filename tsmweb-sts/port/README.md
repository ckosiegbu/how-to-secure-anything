# pysts — Python port of the TsmWeb-STS token engine

A clean-room Python re-implementation of the STS prepaid-token engine recovered
from the decompiled Tcl (`modules/sts/*`, `modules/crypto/misty1`,
`dbn-crypto`). This is the shared core for any re-implementation (a FastAPI
service or a Frappe v13 app) — see `../PORTING.md`.

## What it implements

| Area | Module | Notes |
|---|---|---|
| DKGA01 / DKGA02 (DES) | `pysts/dkga.py` | decoder-key derivation |
| DKGA04 (KDF108-HMAC-SHA256) | `pysts/dkga.py` | EA=11 / long keys |
| Key Check Values | `pysts/dkga.py` | `vk_kcv`, `dk_kcv` |
| STA cipher (EA=07) | `pysts/sta.py` | **DEMO tables only** (see below) |
| MISTY1 (EA=11) | `pysts/misty1.py` | public cipher — production-faithful |
| Token codec | `pysts/codec.py` | clear-token, CRC-16, transpose, encrypt/decrypt |
| Transfer amount (16-bit) + currency (20-bit) | `pysts/codec.py` | encode/decode |
| Key Change Tokens (KCT) | `pysts/codec.py` | EA=7 (2/3 tokens), EA=11 (4 tokens) |
| Tariff / unit scaling | `pysts/tariff.py` | `convert_units`, `scale_units` |
| High-level vending-key API | `pysts/engine.py` | `vk_create_token`, `vk_verify_token`, `vk_create_key_change_tokens` |

## NDA / DEMO boundary

The STA (EA=07) **production** S-box/permutation tables are withheld — the
source marks them *“DO NOT DISTRIBUTE; PROD table under NDA from STSA.”* This
port embeds only the **DEMO** tables, so EA=7 tokens are internally consistent
(encrypt↔decrypt) but are **not** accepted by production meters. A licensee can
populate `PROD_*` in `pysts/sta.py`. **MISTY1 (EA=11)** is a public cipher
(RFC 2994) and is fully functional here.

Issuing production tokens additionally requires real (secret) vending keys and
the appropriate STS Association licensing — an organisational gate, not a
technical one.

## Usage

```bash
pip install -r requirements.txt
python3 demo.py                 # worked examples
python3 tests/test_pysts.py     # 17 self-contained tests
# or: python3 -m pytest -q
```

```python
import pysts
vk  = bytes.fromhex("ABABABABABABABAB")
tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 1000*60)
res = pysts.vk_create_token(vk, sgc=123456, pan18="0"*18, krn=1, kt=2,
                            dkga_no=2, bdt=93, ti=1, ea=7,
                            cls=0, subclass=0, rnd=0, tid=tid,
                            amount=50, encode_amount=True, sta_mode=1)
print(res["token20d"])
info = pysts.vk_verify_token(vk, 123456, "0"*18, 1, 2, 2, 93, 1, 7,
                             res["token20d"], sta_mode=1)
```

## Validation
- **MISTY1** is checked byte-for-byte against the RFC 2994 test vector.
- STA (demo), DKGA, all token types, currency, KCT, and tariff conversion are
  covered by round-trip tests in `tests/test_pysts.py`.
- Production test vectors (CTSA/STSA) require the withheld production STA tables
  and are intentionally not reproduced.
