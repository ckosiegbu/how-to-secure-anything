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
1. **`pysts` library** — finish engine (DKGA01/02/04 ✓, STA ✓; add MISTY1,
   currency tokens, KCT, transfer-amount/tariff) + unit tests. *(small)*
2. **Data model** — DocTypes/models from DEEP-DIVE §5, with migrations. *(small)*
3. **Token-issue + verify** workflow end-to-end (software SM). *(medium)*
4. **Key management** — KMC pubkeys, VK load req/KLF, load/delete VK. *(medium)*
5. **API** — PrismToken (REST first; Thrift shim from the existing IDL). *(medium)*
6. **AuthZ/audit/SIEM** parity. *(small–medium)*
7. **Hardware-HSM bridge** (only if hardware is in scope). *(large, needs HW)*
8. **Meter-manufacturing / DITK / production ceremonies.** *(large, gated)*

Steps 1–6 are a realistic first milestone (a working software-only vending
server). 7–8 depend on hardware access and STSA licensing.

## Status in this repo
- `port/sts_engine.py` — runnable engine (step 1 core), demo tables, passing
  round-trip self-test. `python3 port/sts_engine.py`.
- `port/requirements.txt` — `pycryptodome`.
