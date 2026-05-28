"""sts_sm -- Security Module layer for the PrismToken port.

SmBase is the backend contract; VirtualHsm is the in-process software HSM;
Keystore + KEK providers protect vending-key material at rest. The serial
hardware backend (DcmSerialSm) is added in a later phase behind the same SmBase.
"""

from .sm_base import SmBase, SmStatus, KeyRegister, IssuedToken, SmError
from .keystore import (Keystore, KekProvider, PlaintextKek, PassphraseKek,
                       MacSecureEnclaveKek, make_kek)
from .virtual_hsm import VirtualHsm
from .transport import Transport, LoopbackTransport, SerialTransport
from .emulator import SoftSm6Emulator
from .dcm_serial import DcmSerialSm

__all__ = [
    "SmBase", "SmStatus", "KeyRegister", "IssuedToken", "SmError",
    "Keystore", "KekProvider", "PlaintextKek", "PassphraseKek",
    "MacSecureEnclaveKek", "make_kek", "VirtualHsm",
    "Transport", "LoopbackTransport", "SerialTransport",
    "SoftSm6Emulator", "DcmSerialSm",
]
