"""pysts -- a clean-room Python port of the Prism TsmWeb-STS token engine.

Ported from decompiled Tcl (modules/sts/*, modules/crypto/misty1, dbn-crypto).
Implements DKGA01/02/04 key derivation, the STA (EA=07, DEMO tables) and MISTY1
(EA=11, production-faithful) ciphers, the class 0/1/2 token codec, transfer
amount + currency encodings, key-change tokens, and tariff conversion.

The STA *production* S-box tables are withheld (NDA from the STS Association);
EA=7 therefore runs on DEMO tables (use ea=107 or sta_mode=1). MISTY1 (EA=11)
is a public cipher and is fully functional.
"""

from .sta import Sta
from .misty1 import Misty1
from .dkga import (dkga01, dkga02, dkga04, derive_dk, vk_kcv, dk_kcv,
                   set_odd_parity)
from .codec import (
    get_cipher, crc16, EPOCHS, MAX_TID, token_id_from_time, date_from_token_id,
    is_reserved_tid, is_currency,
    encode_transfer_amount, decode_transfer_amount,
    encode_currency_transfer_amount, decode_currency_transfer_amount,
    make_clear_token_int, make_clear_token_fields,
    encrypt_token_int, decrypt_token_int,
    build_credit_mse_content, parse_credit_mse_content,
    build_key_change_tokens,
)
from .tariff import convert_units, scale_units, must_encode_transfer_amount
from .engine import (vk_create_token, vk_verify_token,
                     vk_create_key_change_tokens)

__all__ = [
    "Sta", "Misty1",
    "dkga01", "dkga02", "dkga04", "derive_dk", "vk_kcv", "dk_kcv", "set_odd_parity",
    "get_cipher", "crc16", "EPOCHS", "MAX_TID", "token_id_from_time",
    "date_from_token_id", "is_reserved_tid", "is_currency",
    "encode_transfer_amount", "decode_transfer_amount",
    "encode_currency_transfer_amount", "decode_currency_transfer_amount",
    "make_clear_token_int", "make_clear_token_fields",
    "encrypt_token_int", "decrypt_token_int",
    "build_credit_mse_content", "parse_credit_mse_content",
    "build_key_change_tokens",
    "convert_units", "scale_units", "must_encode_transfer_amount",
    "vk_create_token", "vk_verify_token", "vk_create_key_change_tokens",
]
