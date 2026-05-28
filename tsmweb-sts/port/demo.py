"""Demonstration of the pysts engine. Run: python3 demo.py"""

from datetime import datetime, timezone
import pysts

VK8 = bytes.fromhex("ABABABABABABABAB")     # 8-byte vending key (EA=7 / DKGA02)
VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")  # 16-byte (EA=11)
PAN = "000000000000000000"
SGC, KRN, KT, TI = 123456, 1, 2, 1
when = int(datetime(2021, 4, 12, 9, 0, tzinfo=timezone.utc).timestamp())


def show(title, res, vk, dkga, ea, sta_mode=1):
    tid = res["tid"]
    info = pysts.vk_verify_token(vk, SGC, PAN, KRN, KT, dkga, 93, TI, ea,
                                 res["token20d"], sta_mode=sta_mode)
    print(f"\n== {title} ==")
    print(f"  token (20-digit) : {res['token20d']}")
    print(f"  decoder key/KCV  : {res['dk']} / {res['dkKcv']}")
    print(f"  verify           : class={info['class']} subclass={info['subclass']}"
          f" tid={info['tid']} rnd={info['rnd']}")
    return info


print("pysts demo -- STA(EA=7) uses DEMO tables; MISTY1(EA=11) is production-faithful")

tid = pysts.token_id_from_time(when, 93)

# 1) Electricity credit, EA=7 (demo STA), DKGA02
r = pysts.vk_create_token(VK8, SGC, PAN, KRN, KT, 2, 93, TI, 7, 0, 0, 7, tid, 50,
                          encode_amount=True, sta_mode=1)
info = show("Electricity credit 50 kWh (EA=7 demo STA, DKGA02)", r, VK8, 2, 7)
print(f"  decoded units    : {pysts.decode_transfer_amount(info['transferamount'])} kWh")

# 2) Electricity credit, EA=11 (real MISTY1), DKGA04
r = pysts.vk_create_token(VK16, SGC, PAN, KRN, KT, 4, 93, TI, 11, 0, 0, 9, tid, 250,
                          encode_amount=True)
info = show("Electricity credit 250 kWh (EA=11 MISTY1, DKGA04)", r, VK16, 4, 11)
print(f"  decoded units    : {pysts.decode_transfer_amount(info['transferamount'])} kWh")

# 3) Currency credit token (20-bit amount)
r = pysts.vk_create_token(VK8, SGC, PAN, KRN, KT, 2, 93, TI, 7, 0, 4, 0, tid, 123.45,
                          encode_amount=True, sta_mode=1)
info = show("Currency credit ZAR 123.45 (EA=7 demo, subclass 4)", r, VK8, 2, 7)
print(f"  decoded value    : {info['amount']:.2f}")

# 4) Tariff conversion
conv = pysts.convert_units(50.0, tariff=0.115, cls=0, subclass=0)
print(f"\n== Tariff: ZAR 50 @ 0.115/100Wh ==\n  -> {conv['unitsReq']} units (100Wh),"
      f" transferAmt={conv['transferAmt']}")

# 5) Key change tokens (EA=7, 2-token set)
toks = pysts.vk_create_key_change_tokens(
    VK8, SGC, KRN, KT, 2, 93, PAN, TI, 7,
    new_vk=bytes.fromhex("1122334455667788"), new_dkga=2, new_bdt=93,
    new_sgc=123457, new_krn=2, new_ti=1, new_ken=0, new_kt=2, sta_mode=1)
print(f"\n== Key Change Token set (EA=7) ==")
for i, t in enumerate(toks, 1):
    print(f"  KCT{i}: {t}")

print("\nDemo complete.")
