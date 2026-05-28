# Prism TsmWeb-STS 4.70.2 — Complete Deep Dive

A full architectural and security walkthrough of the decompiled application.
Companion to `../tsmweb-sts-decompilation.md` (which covers how the installer
was unpacked). All file paths below are within the recovered source tree
(`libs/` = `libs.vfs`, `libshlsm/` = `libshlsm.vfs`).

> Source recovery was complete: 1,019 plaintext Tcl files, zero byte-compiled
> or obfuscated. Everything here was read from source.

---

## 1. What the system is

TsmWeb-STS is an on-premise **STS prepaid-electricity vending and key-management
server**. An operator (utility / meter manufacturer) runs it next to a hardware
Security Module (HSM) to:

- hold **vending keys** received from a Key Management Centre (KMC),
- **issue STS tokens** (the 20-digit numbers a customer types into a prepaid
  meter) — credit, engineering/management, and key-change tokens,
- run **meter-manufacturing** key operations (DITK), and
- expose all of this via a local **web UI** and a **Thrift API** (PrismToken)
  for integration with vending front-ends.

It is the trust anchor of a prepaid-electricity deployment: whoever controls it
(and its keys) can mint tokens worth money.

---

## 2. Process & runtime model

- A single **Tcl 8.6 (threaded)** interpreter (`wish86t.exe`) launched by
  `tsmweb.bat`, packaged as a Starpack (code mounted from `libs.vfs` /
  `libshlsm.vfs`).
- Bootstrap: `libs/app_init.tcl` → `package require stsWeb`
  (`libs/psws/stsWeb.tcl`) → `ptcl::eventLoop`.
- Can run as a **Windows service** (`winserv`), managing its own NIC / `netsh`
  / LCD front-panel on appliance ("NSS") builds (`tsmweb.prop`).
- Two co-operating servers in one process:
  1. **Wub** HTTP server → the web UI (default `0.0.0.0:80`).
  2. **Thrift-over-TLS** server → the PrismToken API (default `:9443`).
- Talks out to: an **HSM** (serial/PCI/`DCM` driver or remote "Conductor"
  service on `:5100`), a **SQLite** or **PostgreSQL** database, and an optional
  **SIEM** event sink.

```
   Browser ──HTTP:80──┐
                      ▼
 Vending FE ─Thrift/TLS:9443─►  TsmWeb-STS (Tcl)  ──► HSM (serial/PCI/EDP:5100)
                      │            │   │
                      │            │   └──► SQLite / PostgreSQL
                      │            └──────► SIEM event queue
```

---

## 3. Subsystem map

| Layer | Location | Role |
|---|---|---|
| Bootstrap / framework | `libs/dbn-base`, `libs/modules/{app,util}` | app init, prefs, logging, ACM, upgrade manager |
| Web server | `libs/wub-1` | the `wub` Tcl HTTP server |
| Web MVC | `libs/modules/web`, `libshlsm/modules/hlsmweb` | router, controllers, views, CSRF, forms |
| Data / persistence | `libs/dbn-base/db_*.tcl`, `libshlsm/modules/hlsm/DbSchema` | SQLite/PostgreSQL, schema, audit |
| STS token engine | `libs/modules/sts`, `libs/dbn-crypto` | DKGA, STA/MISTY1, token codec, key mgmt |
| Software HSM (HLSM) | `libshlsm/modules/hlsm` | software security module + Thrift API |
| Hardware HSM | `libs/dbn-tsm`, `libs/modules/hsm` | BL50/BL410/MCM/Thales/EDP drivers, ceremonies |
| Crypto primitives | `libs/dbn-crypto`, `libs/tclcrypt-1` | DES/AES/RSA/ECC/MISTY1/SHA/PRNG |
| Native libs | `app/rt/bin/*.dll`, `dbn-tsm/*.so` | Tcl/Tk, OpenSSL, keccak, DCM drivers |

---

## 4. Web application layer

**Server.** Wub, multithreaded/event-driven (`libs/psws/nssWeb.tcl`). Cookie
session auth on the UI port; optional TLS (`nssSsl.tcl`). An access interceptor
(`nssUtils.tcl`, `afterCookieAuthInterceptor`) redirects anonymous users
(username prefixed `$`) to `/login/` except for a small whitelist
(`/favicon.ico`, `/monitor/`, `/login/*`, `/res/*`, `/docs/*`).

**MVC framework** (`libs/modules/web`):

- `WubRouter` — regex path → controller/method dispatch.
- `WubController` — base class; `invokeWubAction`, `hasPermissions`, validation.
- `Csrf` — HMAC-SHA256 token bound to (random instance key, sessionId,
  resourceName, expiry ~15 min); forms carry `_csrf`, `_utf8` (☃), `_charset_`.
- `HtmlTemplate`, `Pagebuilder`, `Formbuilder`, `Bootstrap-4`, `PageMessages`,
  `ErrorViews` — server-side rendering.
- `HttpCurlClient`, `StsHttpApiClient`, `TclApiClient` — outbound HTTP/API.

**Controllers** (`libshlsm/modules/hlsmweb`, all routes under `/hlsm/`):

| Controller | Route | Action |
|---|---|---|
| Dashboard | `GET /hlsm/` | SM status, notices, KMC/VK cache |
| | `POST /hlsm/loadsmlicense/` | upload SM transaction license |
| | `POST /hlsm/clearcache/` | clear PrismToken cache |
| KeyManagement | `GET /hlsm/key-management/` | KMC list, key-agreement state |
| | `POST /hlsm/genvkloadreq/` | generate vending-key load request |
| | `POST /hlsm/uploadklf/` | upload key load file (KLF) |
| | `POST /hlsm/loadvendingkeys/`, `loadallvks/` | load VKs |
| | `POST /hlsm/uploadkmcpubkey/`, `uploadstsaconfigfile/` | KMC pubkey / STSA config |
| | `POST /hlsm/deletekekslot/`, `endkeyagree/` | manage KEK slots / sessions |
| VendingKeys | `GET /hlsm/vending-keys/` | list VKs by SGC/KRN |
| | `POST /hlsm/loadvk/`, `deletevk/` | load / delete a VK |
| TokenIssue | `GET /hlsm/tokenissue/` | token-issue form |
| | `POST /hlsm/gentokens/`, `verifytokens/` | issue / verify tokens |
| | `POST /hlsm/issuekct/`, `issueditkct/` | key-change / DITK-change tokens |
| | `POST /hlsm/cleartidlist/` | clear transaction-ID list |
| MeterMfr | `GET /hlsm/metermfr/` | meter-manufacturing page (gated) |
| | `POST /hlsm/genanddisplay/`, `loadditk/` | generate / load DITK components |
| Settings / Reporting | `GET /hlsm/settings/`, `/reporting/` | (stubs) |

**Authorization.** Role-based via `::acm` (`db_acm.tcl`): roles **admin /
operator / auditor**, mapped to permissions (`manage-nss`, `view-nss`, and the
fine-grained `ptoken.*` set). Each endpoint asserts a permission.

**Front-end.** Hybrid: jQuery + jQuery-UI + DataTables for most pages; React +
Redux + React-Router on some; FontAwesome, Chosen, SimpleModal. Assets in
`app/resources/`.

---

## 5. Data model

**Engines:** SQLite (file `tsmweb.sqlite`, default) or PostgreSQL, behind a
`::db` ensemble (`db_sqlite.tcl` / `db_postgres.tcl`) using TDBC prepared
statements with named params and binary blobs. Schema versioning via
`upgrade_manager.tcl` + `t_schema`.

Key tables (from `libshlsm/modules/hlsm/DbSchema-1.0.tm`, `db_acm.tcl`,
`modules/db/keystore`, `programdata/siem-init-v1.sql`):

| Table | Purpose |
|---|---|
| `t_schema` | per-module schema revision |
| `t_prefs` | key/value config |
| `t_users`, `t_alias` | accounts, roles, password/lockout; smartcard/cert aliases |
| `t_keystore` | encrypted keys + KCV, keyed by (api, keyset, purpose, krn) |
| `HlsmMeters` | per-meter PAN + TID-cancellation list (optimistic locking) |
| `HlsmPubkeyKmc` | KMC public keys (STS600-4-2), approval flags |
| `HlsmVkLoadReq` / `HlsmVkLoadResp` | VK load requests / KLF responses |
| `HlsmWrappedKey` | wrapped VKs from a KLF (ACT/BDT/DKG/KEN/KRN/KTC/SGC/…) |
| `AuditLogEntry` / `AuditLogMessage` | append-only audit + message templates |
| `HsmAuditLog` | HSM-side audit-log sync |
| `t_siemApps` / `t_eventQueue` | SIEM event delivery queue |
| `NetworkServices` | service endpoint/port registry |

**Audit** is append-only with a *tombstone* pattern: a PENDING entry is
superseded by inserting a new row (`TombstoneFor = oldId`) and deleting the old,
so the autoincrement `Id` acts as a logical clock for SIEM ETL.

---

## 6. The STS token engine (security core)

This is the heart of the product and is implemented **in pure Tcl** (with an
optional native `sts.dll` fast-path). Files: `libs/modules/sts/{dkga,sta,
softalg,common}-1.0.tm`, `libs/dbn-crypto/crypt-des.tcl`.

### Inputs
Supply Group Code (SGC, 6 digits), Key Revision Number (KRN 1–9), Tariff Index
(TI 0–99), Key Type (KT 0–3), Encryption Algorithm (EA: 7=STA, 11=MISTY1),
Base Date (BDT: 93/14/35 → 1993/2014/2035), meter PAN (18 digits), Vending Key
(VK), token class/subclass, transfer amount, and a Token ID (TID = minutes
since the base-date epoch).

### Step 1 — Derive the Decoder Key (DKGA), `dkga-1.0.tm`
The VK never encrypts a token directly; a per-meter **Decoder Key (DK)** is
derived first.

- **DKGA01** (IEC 62055-41, legacy; only IIN 600727, KRN 1, EA 7, specific
  DRN/SGC ranges): `DK = DES(key=datablock, VKodd) XOR VKodd`, where
  `datablock = PAN[1..16] XOR (KT·SGC·TI·KRN·FFFFFF)`.
- **DKGA02** (the common default): `DK = DES(VK, datablock) XOR datablock XOR
  oddparity(VK)`.
- **DKGA04** (STS202-3, for EA 11 / long keys): KDF108-Feedback using
  `HMAC-SHA256(VK, Label ‖ 0x00 ‖ Context ‖ L)`, leftmost L bits — pure
  standard crypto.

`deriveDk` picks the algorithm per the IEC rules and forces the common PAN
`600727…` for KT=3.

### Step 2 — Build the clear token, `common-1.0.tm`
A 66-bit clear token: `class(2) | subclass(4) | content(44) | CRC(16)`. For
credit/management tokens `content = rnd(4) | tid(24) | transferAmount(16)`.
The 16-bit transfer amount uses a mantissa/exponent encoding
(`encodeTransferAmount`); currency tokens use a 20-bit variant. CRC is
CRC-16/CCITT (seed 0xFFFF) over the 56-bit field, stored byte-swapped;
currency tokens append `0x01` before CRC.

### Step 3 — Encrypt + transpose, `softalg-1.0.tm` (`encryptToken`)
The class bits are split off, the 64-bit datablock (`subclass|content|CRC`) is
encrypted with the DK, the class is reattached, and the *class-bit transpose*
(IEC s6.4.2) swaps bits {64,65}↔{27,28}. The 66-bit result is printed as **20
decimal digits**. Decryption (`decryptToken`/`vkVerifyToken`) reverses this and
validates the CRC.

### The STA cipher (EA=07), `sta-1.0.tm`
A 16-round Feistel-like block cipher (64-bit block/key): per round
`Substitute` (key-nibble-selected 4-bit S-boxes) → `Permute` (64-bit P-box) →
key `Rol 1`; encryption pre-step is 1's-complement of the key then `Ror 12`.
The S-box/P-box tables exist as **PRODUCTION** (marked *“DO NOT DISTRIBUTE; PROD
table under NDA from STSA”*) and **DEMO** sets. EA=11 (MISTY1, RFC 2994) is
delegated to a native `crypto::misty1`.

### Key hierarchy & KMC, `StsKm-1.0.tm`, `KmcImport/Export`, `ParseKmf`
`VK → (DKGA) → DK → (EA) → token`. VKs arrive wrapped from a KMC in a Key Load
File (KLF) and carry attributes ACT/BDT/DKG/KEN/KRN/KTC/SGC/ULM/CLM/KCV. The
`StsSoftwareKmcSm` module (313 KB) is a software KMC security module; `Keystore`
/ `VsmKeystore` store keys; `KeyAgreement` performs the SM↔KMC key-agreement.

> **A working Python port of this engine** (DKGA01/02/04 + STA *demo* tables +
> the full token codec) is in `port/sts_engine.py`, with a passing
> encrypt→verify round-trip. Production tables are deliberately omitted (NDA).

---

## 7. Software HSM (HLSM) + PrismToken Thrift API

`libshlsm/modules/hlsm` is a **software security module** that implements the
same STS6 SM interface the hardware exposes, so token issuing can run with or
without hardware (`SmFacade` abstracts the two).

**PrismToken Thrift API** (`prismtoken1/TokenApi-1.0.tm`, IDL
`docs/PrismToken/prismtoken1-TokenApi.thrift`), TBinaryProtocol over TLS
(`:9443`); every call carries a `messageId` + bearer `accessToken`:

| Method | Purpose |
|---|---|
| `ping` | connectivity |
| `signInWithPassword` | authenticate → bearer token (perms + expiry) |
| `getStatus` | SM/HLSM firmware, RTC, key slots, counters |
| `parseIdRecord` | parse a meter ID record → MeterConfig |
| `loadTransactionLicense` | install transaction-limit license |
| `issueCreditToken` | class-0 credit token(s), may auto-issue KCT |
| `issueMseToken` | class-2 management/engineering token(s) |
| `issueMeterTestToken` | class-1 init-meter-test token |
| `issueKeyChangeTokens` | manual key-change token set |
| `issueDitkChangeTokens` | DITK→VK change (manufacturing firmware) |
| `verifyToken` | decrypt/validate a token |
| `fetchTokenResult` | idempotent re-fetch of a prior issue (by messageId) |
| `ctsResetTidList` | test-mode TID-list reset |

**Auth (`BearerToken`).** Opaque base64 length-value blob → {realm, username,
culture, permissions, expiry}. Each method is gated by a permission spec that is
an OR-of-ANDs of `ptoken.*` permissions.

**Idempotency.** `ApiService` keeps a 100-entry FIFO result cache keyed by
messageId and scoped to (realm, username); `TokenIssueDb` stores predefined
tokens; per-meter TID-cancellation lists prevent duplicate/replayed TIDs.

---

## 8. Hardware HSM integration & key ceremonies

`libs/dbn-tsm` + `libs/modules/hsm`. A common interface (`hsm.tcl` / `Itsm.tcl`:
`rpc` / `status` / `detect`) abstracts every supported module:

- **Prism BL50 / BL410 / TSM2xx-5xx**, **MCM** (Module Crypto Manager),
  **Thales**, **EDP/Conductor** (remote, TCP `:5100`), **Prima** (legacy).
- Transport: native **DCM** driver (`libDcmLinDrv.so` / `DcmNtDrv.dll`),
  serial (`com://2/9600,n,8,1`), or EDP sockets. MCM RPC is CRC16-checked.

**Key-management ceremonies** (`mcmapi.tcl`, `mcmstskms.tcl`,
`hsm-bl50-key-mgmt.tcl`, `modules/hsm/mcmKeyWrap`):

- SMK (Secret Master Key) generation + KCV, KSI slot creation, split-knowledge
  custodian loading.
- Key import/export under wrap keys (TDES/AES/XOR SMK variants); token formats
  0x80/0x50/0x51.
- RSA keygen/sign/verify in-module; STS vending-key generate (cmd 0xCE), SM-KEK
  import under RSA (0xCC), export VK under KEK (0xCA).
- Production personalisation: DAK injection (0xB2), module signing / ECDSA token
  (0x33), `personalise_sm` (0xBE).

The software HLSM is a drop-in for the hardware SM via `SmFacade`, intended for
lower-assurance / test deployments.

---

## 9. Native binaries (not source)

Compiled, would need separate native RE; all are runtime/driver code, not app
logic: `dbn-tsm/libDcm{Lin,Sol}Drv.so` (HSM device comms) and the Windows
runtime DLLs (`tcl86t`, `tk86t`, OpenSSL `libeay32`/`ssleay32`, `tclcrypt1_*`,
`keccak`, `_eccfp`, `merkle_db_tcl`, `libzmq`, `twapi_*`, `DcmNtDrv`).

---

## 10. Security-posture observations

Factual notes from the source/config (not a completed audit):

1. **Hand-rolled crypto in interpreted Tcl** (DES, RSA, ECC, the STA cipher).
   Large assurance surface; constant-time properties are not a goal in Tcl.
2. **Software HSM mode** collapses the token-minting trust boundary to the host
   OS — keys live in process/DB rather than tamper-resistant hardware.
3. Shipped `tsmweb.prop` binds the **UI on `0.0.0.0:80` with no TLS** by
   default; transport security depends on deployment. The Thrift API does use
   TLS.
4. Strengths: append-only tombstoned **audit log** + SIEM queue; **CSRF** with
   per-resource HMAC tokens; **RBAC** on every endpoint; bearer-token scoping;
   per-meter **TID replay protection**; idempotent token issue.
5. The real-world security still rests on **secret vending keys + HSM custody**;
   the application code is the orchestration around that.

---

## 11. Where to look first (orientation)

| To understand… | Start at |
|---|---|
| App startup | `libs/app_init.tcl`, `libs/psws/stsWeb.tcl`, `nssWeb.tcl` |
| Token math | `libs/modules/sts/{dkga,sta,softalg,common}-1.0.tm` |
| API contract | `docs/PrismToken/prismtoken1-TokenApi.thrift`, `hlsm/ApiService` |
| Data model | `libshlsm/modules/hlsm/DbSchema-1.0.tm`, `dbn-base/db_acm.tcl` |
| Web routes | `libshlsm/modules/hlsmweb/Router-1.0.tm` + `*Controller` |
| HSM ops | `libs/dbn-tsm/hsm.tcl`, `mcmapi.tcl`, `mcmstskms.tcl` |
