"""TokenIdentifier (TID) computation from tokenTime + flags.

Ports ::sts::bdtAdjustTid / makeReservedTokenId / hlsmMakeTokenId (common-1.0.tm)
and the makeTokenId branching in ApiService-1.0.tm. TIDs are tracked per meter
in a "TokenCancellation" list (canonical 1993-minute space) to guarantee
monotonicity and to skip the SpecialReservedTokenIdentifier (time 00:01).
"""

from __future__ import annotations
import time

import pysts

# TokenIssueFlags (from the PrismToken IDL)
EXTERNAL_CLOCK = 1
TID_ADJUST_BDT = 2
SPECIAL_RESERVED = 4

EPOCH_1993 = pysts.EPOCHS[93]
MINUTES_PER_DAY = 24 * 60
MAX_TID = 16777215
CANCELLATION_LEN = 50


def _min_from_1993(unixtime: int) -> int:
    return (unixtime - EPOCH_1993) // 60


def bdt_adjust_tid(min_from_1993: int, bdt: int) -> int:
    """Re-base a minutes-from-1993 value to the meter's Base Date."""
    bdt_ofs = (pysts.EPOCHS[bdt % 100] - EPOCH_1993) // 60
    tid = min_from_1993 - bdt_ofs
    if not (0 < tid <= MAX_TID):
        raise ValueError(f"TID {tid} out of range for bdt={bdt}")
    return tid


def make_reserved_token_id(unixtime: int, bdt: int) -> int:
    """SpecialReservedTokenIdentifier: minute 1 (00:01) of the day of `unixtime`."""
    cand = _min_from_1993(unixtime)
    cand = cand - (cand % MINUTES_PER_DAY) + 1
    return bdt_adjust_tid(cand, bdt)


def hlsm_make_token_id(recent_tids: list, unixtime: int, bdt: int):
    """Returns (tid, new_recent_tids). recent_tids are canonical 1993-minute values."""
    cand = _min_from_1993(unixtime)
    tids = sorted(recent_tids)
    if tids:
        cand = max(cand, tids[0] + 1)
    while (cand in tids) or (cand % MINUTES_PER_DAY == 1):
        cand += 1
    tid = bdt_adjust_tid(cand, bdt)
    new_recent = sorted(set(tids) | {cand})[-CANCELLATION_LEN:]
    return tid, new_recent


def make_token_id(store, pan: str, token_time: int, bdt: int, flags: int) -> int:
    """Top-level TID resolver mirroring ApiService makeTokenId."""
    if flags & TID_ADJUST_BDT:
        return bdt_adjust_tid(token_time, bdt)          # no cancellation dedupe
    unixtime = token_time if (flags & EXTERNAL_CLOCK) else int(time.time())
    if flags & SPECIAL_RESERVED:
        return make_reserved_token_id(unixtime, bdt)
    recent = store.get_tid_list(pan) if (store and pan) else []
    tid, new_recent = hlsm_make_token_id(recent, unixtime, bdt)
    if store and pan:
        store.set_tid_list(pan, new_recent)
    return tid
