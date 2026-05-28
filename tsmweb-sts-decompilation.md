# Decompilation: Prism TsmWeb-STS 4.70.2

A walkthrough of unpacking a commercial STS prepaid-electricity token-vending
application back to source, as a worked example of reverse-engineering a
packaged desktop/server program.

## Subject

| | |
|---|---|
| File | `TsmWeb-STS-4.70.2-Setup.exe` |
| Size | 23,450,375 bytes |
| SHA-256 | `65b15cba77f9ac6f7a107c9c2a64a58291e175c6fcfe49dbf74f8e8865d284af` |
| Type | PE32 GUI executable, 10 sections |
| Product | Prism TsmWeb-STS 4.70.2 |
| Publisher | Prism Payment Technologies (Pty) Ltd (Manqala) |
| Purpose | Web-based STS (Standard Transfer Specification, IEC 62055) prepaid-electricity token vending and key management |

## Unpacking chain

The path from a single 23 MB `.exe` to readable source is three layers deep.

### 1. Identify the installer

String/PE fingerprinting gave the definitive marker:

```
Inno Setup Setup Data (6.1.0) (u)      # (u) = Unicode build
Embarcadero Delphi for Win32 compiler  # the Inno Setup loader stub
```

So it is an **Inno Setup 6.1.0** installer, not NSIS (the handful of "NSIS"
string hits were substrings of `AnsiString`; the ~98 "Qt" hits were random
bytes inside the compressed payload — both false positives).

### 2. Extract the installer

`innoextract` unpacks Inno Setup archives. A prebuilt static Linux binary was
fetched from the project's GitHub releases (the only file host the environment's
network allowlist permitted), then:

```
innoextract -e -d out setup.exe        # 2,179 files, ~74 MB into app/
```

### 3. Recover the program from the Tcl VFS

The extracted `app/` does **not** contain a compiled application binary. The
launcher (`tsmweb.bat`) reveals the real architecture:

```tcl
@start "Tcl" "%~dp0rt\bin\wish86t.exe" -encoding utf-8 "%~f0" ...
package require -exact ptcl 8.6.2.7
set ::tap::PATHS(vfs)     [::ptcl::addLibraryOrVfs "./libs" "./libs.vfs"]
lappend ::tap::PATHS(vfs) [::ptcl::addLibraryOrVfs "./libshlsm" "./libshlsm.vfs"]
source [file join ... app_init.tcl]
package require stsWeb
```

It is a **Tcl/Tk "Starpack"**: the interpreter (`rt/bin/wish86t.exe`, Tcl 8.6
threaded) mounts two Virtual File Systems and `source`s the app from them. Both
`.vfs` files are ordinary **ZIP archives** (deflate). Unzipping them recovers
the entire application as source.

> Note: the VFS zips store some directory entries without a trailing slash,
> which collides with the same name as a real directory and breaks `unzip`. A
> small `zipfile`-based extractor (treat any name that is a prefix of another
> entry as a directory) resolves this cleanly.

Result: **1,019 source files** across `libs.vfs` (977) and `libshlsm.vfs` (42).

## Decompilation result: full source recovery

Nothing is obfuscated or byte-compiled — **0 `.tbc` files**. All 247 `.tcl` and
271 `.tm` (Tcl module) files are plaintext, retaining their original CVS
`$Header$` provenance comments dating from 2007 to 2021. This is complete
source recovery of the application layer, not a partial disassembly.

| Asset type | Count |
|---|---|
| Tcl scripts (`.tcl`) | 247 |
| Tcl modules (`.tm`) | 271 |
| Plugins (`.plugin`) | 44 |
| JavaScript (front-end) | 90 |

## Architecture

- **Language/runtime:** Tcl 8.6 (threaded) + Tk, packaged as a Starpack.
- **Web server:** the `wub` Tcl HTTP server (`libs/wub-1/`), serving a local
  admin/vending UI (`httpd.port=80` by default, bind `0.0.0.0`).
- **Web MVC:** custom framework under `modules/web/` — Bootstrap-4 views,
  `Csrf`, `Formbuilder`, `Pagebuilder`, `HtmlTemplate`, plus the `hlsmweb`
  controllers/views in `libshlsm` (Dashboard, TokenIssue, KeyManagement,
  VendingKeys, MeterMfr, Settings, Reporting).
- **Data:** SQLite via TDBC with a PostgreSQL adapter (`dbn-base/db_postgres.tcl`,
  `db_sqlite.tcl`).
- **Messaging:** ZeroMQ (`zmq4.0.1`), Thrift API (`prismtoken1`), `tdom` XML.
- **Front-end:** React + jQuery bundles under `app/resources/`.

### Source tree (top level)

```
libs/
  app_init.tcl            application bootstrap
  dbn-base/               app framework: datastore, db adapters, logging, navbar
  dbn-comms/              communications
  dbn-crypto/             cryptographic primitives (see below)
  dbn-tsm/                hardware-HSM drivers + STS demos
  dbn-utils/              utilities
  modules/                Tcl modules (sts, hsm, crypto, web, db, net, prism, ...)
  psws/                   stsWeb package (web entry point)
  tclcrypt-1/, twapi/, tdom0.8.3/, wub-1/   third-party libs
libshlsm/                 HLSM = software HSM + its web UI
```

## Security-relevant components

This is the interesting part: an STS vending system is essentially a key-management
and token-minting product, and the whole crypto stack is here in readable form.

- **`libs/dbn-crypto/`** — hand-rolled crypto in pure Tcl:
  - Symmetric: DES (`crypt-des.tcl`), AES (`crypt-aes.tcl`), XXTEA.
  - Public-key: RSA with ISO-9796 signing, PSS, and X9.31 key generation;
    ECC over F_p (`eccFp*`) and Curve25519.
  - Hashing/MAC: SipHash; Keccak (native `keccak.dll`).
  - RNG: an **ANSI X9.31 AES PRNG** (`prngX931aes.tcl`).
  - Thales HSM crypto helpers (`thales_crypto.tcl`, `thales-keyutil.tcl`).
- **`libs/modules/sts/`** — the STS engine:
  - `dkga-1.0.tm` — Decoder Key Generation Algorithm.
  - `sta-1.0.tm` — STS Association handling.
  - `softalg-1.0.tm` — software token algorithm.
  - `StsKm-1.0.tm`, `StsSoftwareKmcSm-1.0.tm` (313 KB) — key management /
    software KMC security module.
  - `Keystore`, `VsmKeystore`, `KmConfig`, `KmcImport`/`KmcExport`, `ParseKmf`
    (Key Management File parsing), `MeterRec`, `stsTariff`, `vendApi`.
- **`libshlsm/`** — **HLSM, a software HSM**: `KeyManagementService`,
  `TokenIssueDb`, `Sts6Record`, `BearerToken`, `SmManagementService`, plus the
  PrismToken Thrift `TokenApi`.
- **`libs/dbn-tsm/`** — drivers for hardware HSMs: Prism BL50/BL410, MCM,
  Thales, EDP, Prima.
- **Bundled documentation (PDF):** "Introduction to STS and PrismToken",
  "PrismToken User Guide", "PrismToken Thrift API", "PrismVend User Guide",
  "TsmWeb-STS Web Vending API", "TsmWeb-STS User Guide".

### Observations (factual, from the recovered config/source)

- Default HTTP listener binds `0.0.0.0:80` with no TLS configured in the
  shipped `tsmweb.prop`; transport security is left to deployment.
- Security-critical key material is handled by a *software* HSM (`libshlsm`)
  when no hardware HSM is present — the token-minting trust boundary collapses
  to the host when run that way.
- Crypto is largely hand-implemented in interpreted Tcl rather than delegated
  to a vetted library, which is a notable maintenance/assurance surface.

These are surface observations from configuration and module layout, not a
completed crypto audit.

## Residual native binaries (not recovered as source)

These are compiled libraries that would require separate native
reverse-engineering; they are runtime/driver code, not application logic:

- `libs/dbn-tsm/libDcmLinDrv.so`, `libDcmSolDrv.so` — Linux/Solaris HSM drivers.
- Windows runtime DLLs in `app/rt/bin/`: Tcl/Tk (`tcl86t.dll`, `tk86t.dll`),
  OpenSSL (`libeay32.dll`, `ssleay32.dll`), `tclcrypt1_*.dll`, `keccak.dll`,
  `_eccfp.dll`, `merkle_db_tcl.dll`, `libzmq.dll`, `twapi_*.dll`, `DcmNtDrv.dll`.

## Reproduce

```sh
# 1. identify
file setup.exe
strings -n 6 setup.exe | grep -i "inno setup"

# 2. extract installer (innoextract static build from its GitHub releases)
innoextract -e -d out setup.exe

# 3. recover Tcl source from the VFS zips
unzip out/app/libs.vfs     -d src/libs      # (use a zipfile-based extractor
unzip out/app/libshlsm.vfs -d src/libshlsm  #  to handle dir-marker collisions)
```
