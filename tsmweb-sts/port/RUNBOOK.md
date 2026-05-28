# PrismToken vending server — operations runbook

A high-throughput STS prepaid-token vending service: the `pysts` crypto engine,
a virtual (software) HSM or a serial-attached Prism module behind one `SmBase`
abstraction, and the PrismToken Thrift API. Target platform: macOS on Mac Minis.

## 1. Install

```bash
cd tsmweb-sts/port
python3 -m pip install -e '.[all]'          # engine + thriftpy2 + pyserial
# on Mac Minis, to seal keys with the Secure Enclave:
python3 -m pip install '.[macos-enclave]'
```

## 2. Provision (before first serve)

```bash
export PRISMTOKEN_KEYSTORE=/var/lib/prismtoken/keystore.json
export PRISMTOKEN_DB=/var/lib/prismtoken/prismtoken.db
export PRISMTOKEN_KEK=auto                   # Secure Enclave on Mac, else passphrase

prismtoken-admin add-user   --user op --password '****' --perm '*'
prismtoken-admin add-api-key --key-id vend1 --secret '****' --user op --perm IssueCreditToken --perm VerifyToken
prismtoken-admin load-vk    --sgc 123456 --krn 1 --vk-hex <32-or-40-hex> --ea 11 --dkga 4
prismtoken-admin set-license --count 1000000      # arms the transaction counter
prismtoken-admin status
```

Clients authenticate with either a bearer token (`signInWithPassword`) or an API
key passed as the `accessToken` in the form `key_id:secret`.

## 3. Run

`prismtoken-serve` (driven entirely by `PRISMTOKEN_*` env vars) or the launchd
unit in `deploy/co.prism.prismtoken.plist`. Always terminate TLS:
set `PRISMTOKEN_TLS_CERT` / `PRISMTOKEN_TLS_KEY`.

## 4. Scaling (hundreds/sec)

- **Virtual backend:** the pure-Python ciphers are CPU-bound (GIL), so set
  `PRISMTOKEN_WORKERS` to the core count. Workers prefork on one `SO_REUSEPORT`
  socket; the OS load-balances. Shared state (TID lists, result cache) is in the
  DB — use **Postgres** (not SQLite) once you run multiple writer workers.
- **Decoder-key cache:** DKGA derivation is memoised per (register, PAN, TI);
  watch `dkCache.hitRate` in `getStatus`. Size via `PRISMTOKEN_DK_CACHE`.
- **Serial backend:** a module is a single serial conversation — run **one
  worker per module** (`PRISMTOKEN_WORKERS=1`), or several modules each on its
  own port behind a TCP load balancer.

## 5. Hardware bring-up checklist (serial backend)

Before trusting the vend path against a real Prism module on `/dev/cu.*`:
1. `PRISMTOKEN_BACKEND=serial PRISMTOKEN_SERIAL_PORT=/dev/cu.usbserial-XXXX`.
2. Confirm a clean `SM?DI` (identification) and `SM?CQ` (transaction counter)
   exchange — these validate framing, the **CRC-16/ARC**, and PTVD parsing on
   real hardware. The wire layer is ported from the firmware spec but has only
   been validated here against the in-process emulator.
3. Vend one test token and verify it (`SM?VC` then `SM?VT`) before going live.

## 6. Keys, backup, security

- The keystore is AES-256-GCM; the data key is wrapped by the KEK provider. On
  Mac the KEK is a non-exportable Secure Enclave key — **back up the keystore
  file, but note it can only be unwrapped on the same machine.** For portable
  DR, provision with `PRISMTOKEN_KEK=passphrase` instead and escrow the passphrase.
- Back up the DB (meter TID-cancellation lists prevent token replay — losing
  them weakens that control).
- EA=11 (MISTY1) is production-faithful. **EA=7 (STA) runs on DEMO tables**;
  drop the licensed STSA production tables into `pysts/sta.py` (`PROD_*`) before
  issuing production EA=7 tokens. Issuing production tokens also requires real
  vending keys and STS Association licensing.

## 7. Monitoring

`getStatus` returns `txCounter`, `numRegisters`, per-process `metric.*`
(tokensIssued/verifies/errors) and `dkCache.*`. Alert on: txCounter approaching
zero (vending halts), rising `metric.errors`, and low `dkCache.hitRate`.
