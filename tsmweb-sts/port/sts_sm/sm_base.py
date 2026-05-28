"""SmBase -- the Security Module abstraction.

This is the contract both backends implement (mirrors the Tcl SmFacade in
libshlsm/modules/hlsm/SmFacade-1.0.tm): an in-process software HSM (VirtualHsm)
and the serial hardware module (DcmSerialSm). The PrismToken service depends
only on this interface, so the backend is swappable by config.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class KeyRegister:
    """Metadata for a vending-key register (mirrors KeyRegisterDetail fields)."""
    reg_no: int
    sgc: int
    krn: int
    ea: int                 # encryption algorithm (7, 11)
    dkga: int               # decoder-key generation algorithm (1, 2, 4)
    bdt: int = 93           # base date (93/14/35)
    ti: int = 1             # tariff index
    kt: int = 2             # key type
    ken: int = 0            # key expiry number
    kcv: str = ""           # 6-hex-digit key check value
    act: Optional[int] = None  # activation (unixtime), informational

    def public(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class SmStatus:
    api_type: str                     # 'vending' | 'manufacturing'
    module_id: str
    firmware_id: str
    tx_counter: int                   # remaining authorised transactions
    num_registers: int
    info: dict = field(default_factory=dict)


@dataclass
class IssuedToken:
    token_dec: str                    # 20 ASCII decimal digits
    token_hex: str                    # 17 ASCII hex digits
    token_class: int
    subclass: int
    tid: int
    transfer_amount: float            # actual units after encode/decode round
    vk_kcv: str
    new_config: Optional[dict] = None # MeterConfigAdvice for first KCT


class SmError(Exception):
    """Carries an STS6-style status code (see sts6v error table) + message."""
    def __init__(self, code: int, message: str):
        super().__init__(f"SM error 0x{code:02x}: {message}")
        self.code = code
        self.message = message


class SmBase(ABC):
    # ----- status / identity --------------------------------------------
    @abstractmethod
    def status(self) -> SmStatus: ...

    def get_api_type(self) -> str:
        return self.status().api_type

    # ----- key register management --------------------------------------
    @abstractmethod
    def list_key_registers(self) -> list: ...

    @abstractmethod
    def fetch_vk_meta(self, sgc: int, krn: int) -> KeyRegister: ...

    # ----- token issuance (SM?VC / SM?VM / SM?VK) -----------------------
    @abstractmethod
    def issue_credit_token(self, sgc: int, krn: int, pan18: str, ti: int, ea: int,
                           tct: int, subclass: int, tid: int,
                           transfer_amount: float) -> IssuedToken: ...

    @abstractmethod
    def issue_mse_token(self, sgc: int, krn: int, pan18: str, ti: int, ea: int,
                        tct: int, subclass: int, tid: int,
                        transfer_amount: float) -> IssuedToken: ...

    @abstractmethod
    def issue_key_change_tokens(self, sgc: int, krn: int, pan18: str, ti: int,
                                ea: int, tct: int, to_sgc: int, to_krn: int,
                                to_ti: int, to_ken: int,
                                allow_3kct: bool = False) -> list: ...

    # ----- verification (SM?VT) -----------------------------------------
    @abstractmethod
    def verify_token(self, sgc: int, krn: int, pan18: str, ti: int, ea: int,
                     token_dec: str) -> dict: ...
