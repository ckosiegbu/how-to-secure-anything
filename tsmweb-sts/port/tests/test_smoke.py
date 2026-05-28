"""Runs the in-process smoke client end-to-end (no socket / no thriftpy2).
Run: python3 tests/test_smoke.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service import smoke
from service import meter


def _mc(ea):
    drn = meter.pan_to_drn(meter.make_meter_pan(7 if ea != 11 else 11, 1))
    return {"drn": drn, "ea": ea, "tct": 0, "sgc": 123456, "krn": 1, "ti": 1, "ken": 0}


def test_smoke_inproc_ea7():
    client = smoke._build_inproc(7)
    out = smoke.run_smoke(client, _mc(7), amount=50.0, log=lambda *_: None)
    assert out["validationResult"] == "EVerify.Ok" and len(out["tokenDec"]) == 20


def test_smoke_inproc_ea11():
    client = smoke._build_inproc(11)
    out = smoke.run_smoke(client, _mc(11), amount=250.0, log=lambda *_: None)
    assert out["validationResult"] == "EVerify.Ok"


def test_smoke_main_inproc():
    smoke.main(["--inproc", "--ea", "7"])     # should not raise / exit non-zero


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(funcs)}/{len(funcs)} smoke tests passed")
