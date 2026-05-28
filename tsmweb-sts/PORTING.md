# Re-implementing TsmWeb-STS: Python equivalent / Frappe v13 app

Feasibility, scope, and a concrete plan for rebuilding the decompiled app — as
either a standalone Python service or a Frappe v13 application.

## Short answer

- **A Python equivalent: yes — feasible, and the hard part is already proven.**
  The crypto token engine (the irreplaceable core) ports cleanly to ~350 lines
  of Python; see `port/sts_engine.py`, which round-trips real token math.
- **A Frappe v13 app "with all capabilities": yes for the application layer
  (data model, web UI, RBAC, audit, REST/Thrift API, workflow), but "all
  capabilities" is a months-long re-engineering effort, not a one-shot
  generation** — and two pieces cannot be fully reproduced in software (below).

## What ports cleanly

| Original | Target | Notes |
|---|---|---|
| STS token engine (DKGA, STA EA=07, codec) | pure Python | done — `port/sts_engine.py` |
| EA=11 (MISTY1) | Python (RFC 2994 / lib) | published cipher |
| DKGA04 (HMAC-SHA256 KDF108) | `hmac`/`hashlib` | standard |
| DES/RSA/ECC primitives | `pycryptodome` / `cryptography` | replace hand-rolled Tcl |
| Data model (15+ tables) | SQLAlchemy models / Frappe DocTypes | 1:1 mapping |
| Web MVC + controllers | FastAPI/Django, or Frappe | routes enumerated in DEEP-DIVE §4 |
| PrismToken Thrift API | Python `thrift` (IDL exists) | drop-in IDL |
| Bearer-token auth, CSRF, RBAC | framework-native | Frappe gives these free |
| Append-only audit + SIEM queue | framework + a queue | tombstone pattern is portable |

## What does NOT fully port (be realistic)

1. **Hardware-HSM drivers** (`libDcm*.so`, `DcmNtDrv.dll`, the BL50/MCM/Thales
   wire protocols). These talk to physical tamper-resistant modules. You can
   re-implement the RPC framing in Python, but you still need the hardware; the
   native blobs themselves are not portable. The **software HSM (HLSM)** path
   *is* portable and is what `sts_engine.py` demonstrates.
2. **Production STS algorithm tables.** The STA production S-boxes are under NDA
   from the STS Association, and STS algorithms/keys are governed by STSA
   licensing. The port ships DEMO tables only; a licensee drops in their own.
   → Any reimplementation that issues *production* tokens needs the appropriate
   STSA licence and the production tables/keys; this is an organisational, not a
   technical, gate.

## Recommended architecture (either target)

Two layers, so the crypto core is reusable regardless of the web framework:

```
  pysts  (library)                 app  (Frappe v13  OR  FastAPI service)
  ├─ engine   DKGA + STA/MISTY1    ├─ DocTypes/models   meters, KMC, VK,
  │           + token codec        │                    wrapped keys, tokens,
  ├─ kdf      DKGA04 / KDF108      │                    audit, prefs
  ├─ keymgmt  KLF/KMF parse,       ├─ controllers       token issue, key mgmt,
  │           wrap/unwrap          │                    vending keys, meter mfr
  ├─ sm       SmFacade:            ├─ api               PrismToken Thrift + REST
  │           software | hardware  ├─ auth/roles        admin/operator/auditor
  └─ codec    transfer-amount,     └─ audit             append-only + SIEM
              TID, tariff
```

### Why Frappe v13 is a good fit
The original hand-rolls exactly what Frappe provides out of the box, so a Frappe
port replaces a lot of bespoke code with framework features:

| TsmWeb-STS hand-rolled | Frappe v13 equivalent |
|---|---|
| `t_users`/`t_alias` + `acm` RBAC | Users, Roles, Role Permissions, Permission Levels |
| `Csrf` module | built-in CSRF |
| `AuditLogEntry` tombstones | Version / Activity log + a custom immutable DocType |
| `t_prefs` | Single DocTypes / Site Config |
| Wub controllers + HtmlTemplate | DocType controllers + Jinja Web Pages / Portal |
| `db_sqlite`/`db_postgres` | Frappe ORM (MariaDB/Postgres) |
| Thrift `ApiService` | `@frappe.whitelist()` REST + a Thrift shim |

**Suggested Frappe DocTypes:** `STS Meter`, `KMC`, `KMC Public Key`,
`VK Load Request`, `Key Load File`, `Vending Key`, `Token Issue` (immutable),
`Audit Entry` (immutable), `SM Status`, plus Settings singles. Server scripts
call `pysts`; the SM backend is selectable (software HLSM vs hardware bridge).

### Phased plan (suggested)
1. **`pysts` library** — engine core. **DONE** (see Status below): DKGA01/02/04,
   STA (demo), MISTY1, 16-bit + currency amounts, KCT, tariff, tests.
2. **Data model** — DocTypes/models from DEEP-DIVE §5, with migrations. *(small)*
3. **Token-issue + verify** workflow end-to-end (software SM). *(medium)*
4. **Key management** — KMC pubkeys, VK load req/KLF, load/delete VK. *(medium)*
5. **API** — PrismToken (REST first; Thrift shim from the existing IDL). *(medium)*
6. **AuthZ/audit/SIEM** parity. *(small–medium)*
7. **Hardware-HSM bridge** (only if hardware is in scope). *(large, needs HW)*
8. **Meter-manufacturing / DITK / production ceremonies.** *(large, gated)*

Steps 1–6 are a realistic first milestone (a working software-only vending
server). 7–8 depend on hardware access and STSA licensing.

## Status in this repo — step 1 complete
The `pysts` package (`port/pysts/`) implements the full token engine with a
17-test suite (all passing), including the MISTY1 RFC 2994 vector:

- `pysts/dkga.py` — DKGA01/02/04 + KCVs
- `pysts/sta.py` — STA cipher EA=07 (DEMO tables; production withheld, NDA)
- `pysts/misty1.py` — MISTY1 EA=11 (public, production-faithful)
- `pysts/codec.py` — token codec, CRC, transfer-amount + currency, KCT
- `pysts/tariff.py` — `convert_units` / `scale_units`
- `pysts/engine.py` — `vk_create_token` / `vk_verify_token` / `vk_create_key_change_tokens`

Run: `pip install -r port/requirements.txt && python3 port/demo.py` and
`python3 port/tests/test_pysts.py`. See `port/README.md`.

### High-traffic Thrift service + virtual HSM (in progress)
Target: a high-throughput Python service exposing the **PrismToken Thrift API**
and driving a **Prism module over macOS serial** (pure-Python STS6/DCM protocol,
no native `libDcm`), plus an **in-process virtual HSM** as a drop-in SM backend.
Architecture: the service depends only on `SmBase`; the backend is `VirtualHsm`
or `DcmSerialSm` by config. Auth = TLS + per-client API key. Keys on Mac Minis
are protected by the **Secure Enclave** (KEK wraps the keystore data key).

**Phase 1 — SM layer: DONE** (`port/sts_sm/`, 11 tests passing):
- `sm_base.py` — `SmBase` contract (ports the SmFacade method set: status,
  list/fetch key registers, issue credit/MSE/key-change tokens, verify) +
  `KeyRegister`/`SmStatus`/`IssuedToken`/`SmError` (STS6 status codes).
- `keystore.py` — AES-256-GCM keystore; pluggable KEK providers:
  `MacSecureEnclaveKek` (SE-wrapped, needs on-device validation),
  `PassphraseKek` (scrypt, tested default), `PlaintextKek` (dev).
- `virtual_hsm.py` — `VirtualHsm(SmBase)` over `pysts` + keystore, with a
  transaction-counter (license) gate. EA=11 production-faithful; EA=7 on demo
  tables (`sta_mode`).

**Phase 2 — Thrift service: DONE** (`port/service/`, 16 tests passing). The
`TokenApi` surface from the recovered IDL, implemented over `SmBase`:
- `meter.py` — DRN/PAN (dual Luhn), IDRecord (35-digit) + Record2 parse/build,
  expiry. `tid.py` — TID from `tokenTime`+flags (EXTERNAL_CLOCK / TID_ADJUST_BDT
  / SPECIAL_RESERVED), `bdtAdjustTid`, and the per-meter TokenCancellation list
  (monotonic TIDs, skips the 00:01 reserved minute).
- `store.py` — sqlite3 DAL (users, API keys, TID lists, `fetchTokenResult`
  result cache). `auth.py` — password sign-in -> bearer token, API keys,
  per-call permission checks.
- `handler.py` — transport-agnostic `TokenApiHandler` (ping, signIn, getStatus,
  parseIdRecord, issueCredit/Mse/KeyChange, verify, fetch, ctsReset; auto-KCT on
  `newConfig`). Class-1 meter-test and DITK methods are explicitly disabled
  (engineering/manufacturing scope, not yet ported).
- `thrift_server.py` — `thriftpy2` runtime IDL load + struct adapter (optional
  dep; handler/tests run stdlib-only). `app.py` — wiring + server entrypoint.

Total suite: 44 tests (17 pysts + 11 SM + 16 service), all passing.

**Phase 3 — serial hardware backend: DONE** (`port/sts_sm/`, 13 tests passing).
A pure-Python STS6 serial path (no native `libDcm`), ported byte-for-byte from
`hsm-sts.tcl` / `sts6v-1.0.tm` / `Ptvd-1.0.tm`:
- `ptvd.py` — PTVD field codec (`<T>value~`, types N/P/H/D).
- `sts6_frame.py` — hook-bang framing (`XX?YY`+params+CRC, `XX!YYRR`+payload+CRC)
  with **CRC-16/ARC** (poly 0x8005, distinct from the token's CCITT CRC; verified
  against the 0xBB3D vector) and the STS6 status-code table.
- `transport.py` — `SerialTransport` (pyserial, CR line-ending) + `LoopbackTransport`.
- `emulator.py` — `SoftSm6Emulator`, an in-process module that speaks the wire
  protocol via pysts, so the path is integration-testable without hardware.
- `dcm_serial.py` — `DcmSerialSm(SmBase)` issuing SM?VC/VM/VK/VT/DI/CQ; host-side
  amount encoding and (sgc,krn)->register map, exactly as the original ApiService.

A token issued through the full serial path verifies under an independent
`VirtualHsm` holding the same key (cross-check test) — proving the wire encoding.
The service swaps `VirtualHsm`<->`DcmSerialSm` by config with zero handler changes.

Total suite: 57 tests (17 pysts + 11 SM + 16 service + 13 serial), all passing.

**Phase 4 — scale & ops: DONE** (`port/`, 7 tests passing):
- `sts_sm/cache.py` + `virtual_hsm.py` — DKGA derivation memoised in a bounded
  LRU (the main throughput lever); per-process metrics surfaced via `getStatus`.
- `service/pool.py` — `SO_REUSEPORT` prefork (`serve_forked`) so the CPU-bound
  ciphers scale across cores; per-connection TLS. Serial backend runs 1 worker
  per module; virtual backend scales freely.
- `service/config.py` — env-driven typed `Config`. `service/adminctl.py` —
  provisioning CLI (users, API keys, vending keys, transaction license).
- `pyproject.toml` (console scripts `prismtoken-serve`/`prismtoken-admin`),
  `deploy/co.prism.prismtoken.plist` (launchd), and `RUNBOOK.md` (install,
  provision, scale, hardware bring-up, backup, monitoring).

- `service/smoke.py` — dual-mode smoke client (`prismtoken-smoke`): `--inproc`
  drives the handler directly (self-provisions a demo key); `--host ...` connects
  to a running server via thriftpy2 (TLS + API-key/password). Runs the full
  ping -> signin -> issueCreditToken -> verifyToken -> fetch flow in one command.

**Build complete (software-only milestone).** Total suite: 67 tests
(17 pysts + 11 SM + 16 service + 13 serial + 7 ops + 3 smoke), all passing. Remaining work
is deployment-gated, not code: validate the serial wire path against a real
Prism module (SM?DI/CQ first), supply the licensed STSA production STA tables for
EA=7, load real vending keys, and (if ever in scope) manufacturing/DITK firmware.
