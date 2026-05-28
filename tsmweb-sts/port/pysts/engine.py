"""High-level vending-key token operations -- ports the sts::vk* procs.

vk_create_token / vk_verify_token / vk_create_key_change_tokens derive the
decoder key from a vending key (via DKGA) and then build/encrypt or
decrypt/verify a token, exactly like modules/sts/softalg-1.0.tm.
"""

from __future__ import annotations

from . import codec, dkga


def _cipher_for(ea: int, sta_mode: int):
    """Resolve the cipher; sta_mode lets callers use demo STA (1) for EA=7."""
    if ea == 7 and sta_mode == 1:
        from .sta import Sta
        return Sta(1), 7
    return codec.get_cipher(ea)


def vk_create_token(vk, sgc, pan18, krn, kt, dkga_no, bdt, ti, ea,
                    cls, subclass, rnd, tid, amount, encode_amount=False,
                    sta_mode=1) -> dict:
    """Create an encrypted token from a vending key. Returns dict with token20d."""
    cipher, ea = _cipher_for(ea, sta_mode)
    dk = dkga.derive_dk(dkga_no, vk, sgc, pan18, kt, ti, krn, ea, bdt)
    content = codec.build_credit_mse_content(cls, subclass, rnd, tid, amount, encode_amount)
    token20d = codec.encrypt_token_int(cipher, dk, cls, subclass, content)
    return {
        "token20d": token20d,
        "dk": dk.hex(),
        "dkKcv": dkga.dk_kcv(ea, dk).hex(),
        "class": cls, "subclass": subclass, "tid": tid, "content": content,
    }


def vk_verify_token(vk, sgc, pan18, krn, kt, dkga_no, bdt, ti, ea,
                    token20d, sta_mode=1) -> dict:
    """Decrypt and verify a token using a vending key."""
    cipher, ea = _cipher_for(ea, sta_mode)
    dk = dkga.derive_dk(dkga_no, vk, sgc, pan18, kt, ti, krn, ea, bdt)
    base = codec.decrypt_token_int(cipher, dk, token20d)
    base.update(codec.parse_credit_mse_content(base["class"], base["subclass"], base["content"]))
    return base


def vk_create_key_change_tokens(vk, sgc, krn, kt, dkga_no, bdt, pan18, ti, ea,
                                new_vk, new_dkga, new_bdt, new_sgc, new_krn,
                                new_ti, new_ken, new_kt, three_kct=0,
                                sta_mode=1) -> list:
    """Create the encrypted Key Change Token set that moves a meter from the
    source vending key to new_vk (sts::vkCreateKeyChangeTokens)."""
    cipher, ea = _cipher_for(ea, sta_mode)
    ro = 1 if (codec.EPOCHS[new_bdt] - codec.EPOCHS[bdt]) > 0 else 0
    src_dk = dkga.derive_dk(dkga_no, vk, sgc, pan18, kt, ti, krn, ea, bdt)
    dst_dk = dkga.derive_dk(new_dkga, new_vk, new_sgc, pan18, new_kt, new_ti, new_krn, ea, new_bdt)
    clear = codec.build_key_change_tokens(ea, dst_dk, new_sgc, new_krn, new_ti,
                                          new_ken, new_kt, ro, three_kct)
    out = []
    for tok_int in clear:
        cls = (tok_int >> 64) & 3
        subclass = (tok_int >> 60) & 0xF
        content = (tok_int >> 16) & ((1 << 44) - 1)
        out.append(codec.encrypt_token_int(cipher, src_dk, cls, subclass, content))
    return out
