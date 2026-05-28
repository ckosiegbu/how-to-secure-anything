"""Transport for STS6 frames. The CR line-ending lives here (per _raw_rpc).

SerialTransport drives a real Prism module over a macOS serial device via
pyserial. LoopbackTransport routes frames to an in-process SoftSm6Emulator so
the whole serial path is integration-testable without hardware.
"""

from __future__ import annotations
import threading
from abc import ABC, abstractmethod


class Transport(ABC):
    @abstractmethod
    def exchange(self, request: str) -> str:
        """Send a framed request (no CR) and return the framed response (no CR)."""


class LoopbackTransport(Transport):
    def __init__(self, emulator):
        self.emulator = emulator

    def exchange(self, request: str) -> str:
        return self.emulator.handle(request)


class SerialTransport(Transport):
    """pyserial transport. Adds CR to the request, reads/strips CR from response."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0,
                 bytesize: int = 8, parity: str = "N", stopbits: int = 1):
        import serial                       # pyserial (deploy-time dependency)
        self._serial = serial
        self.ser = serial.Serial(
            port=port, baudrate=baudrate, timeout=timeout, bytesize=bytesize,
            parity=parity, stopbits=stopbits)
        self._lock = threading.Lock()       # a serial module is single-conversation

    def exchange(self, request: str) -> str:
        with self._lock:
            self.ser.reset_input_buffer()
            self.ser.write((request + "\r").encode("ascii"))
            self.ser.flush()
            line = self.ser.read_until(b"\r")
            if not line.endswith(b"\r"):
                raise TimeoutError("serial read timed out waiting for CR")
            return line.rstrip(b"\r").decode("ascii")

    def close(self):
        self.ser.close()
