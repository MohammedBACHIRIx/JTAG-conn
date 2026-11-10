from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from jtagconn.backend.base import (
    ConnectionLost,
    CoreNotAvailable,
    DeviceSecured,
    EngineMissing,
    InvalidImage,
    MemoryAccessError,
    ProbeBusy,
    ProbeNotFound,
    TargetNotResponding,
    VerifyError,
)


@dataclass
class LogEntry:
    timestamp: float
    level: str
    core: str | None
    operation: str
    message: str
    duration_ms: float | None = None


class OperationLogger:
    """Thread-safe structured operation logger with ring buffer and listeners."""

    def __init__(self, max_entries: int = 2000) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._listeners: list[Callable[[LogEntry], None]] = []
        self._lock = threading.RLock()

    def log(
        self,
        level: str,
        operation: str,
        message: str,
        core: str | None = None,
        duration_ms: float | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            timestamp=time.time(),
            level=level,
            core=core,
            operation=operation,
            message=message,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._entries.append(entry)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(entry)
            except Exception:  # noqa: BLE001, S110
                # Listeners must not break logging.
                pass
        return entry

    def add_listener(self, callback: Callable[[LogEntry], None]) -> None:
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[LogEntry], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    def entries(self) -> list[LogEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def format_user_error(exc: Exception) -> str:
    """Convert backend exceptions into clear plain-language diagnostic messages."""
    if isinstance(exc, ProbeNotFound):
        return (
            "No debug probe was found. Check that the probe is connected, powered, "
            "and that the correct drivers are installed."
        )
    if isinstance(exc, TargetNotResponding):
        return (
            "The target is not responding. Check power, JTAG cable connections, "
            "and that the selected device matches the hardware."
        )
    if isinstance(exc, ProbeBusy):
        return (
            "The debug probe is busy. Another debugger session may already be using it. "
            "Close other debug sessions and try again."
        )
    if isinstance(exc, DeviceSecured):
        return (
            "The device is secured (CSM/DCSM locked). JTAG access is restricted and "
            "this application does not bypass device security."
        )
    if isinstance(exc, CoreNotAvailable):
        return (
            f"The selected core is not available: {exc.reason}. "
            "Its boot master core must be connected and released first."
        )
    if isinstance(exc, InvalidImage):
        return f"The program image is invalid: {exc.reason}"
    if isinstance(exc, VerifyError):
        return (
            f"Program load verification failed at address 0x{exc.address:X}. "
            "The target memory may not match the image."
        )
    if isinstance(exc, MemoryAccessError):
        return f"Memory access failed for range {exc.range_info}. The range may be inaccessible."
    if isinstance(exc, ConnectionLost):
        return (
            "The connection to the target was lost. Check the probe, cable, and target power, "
            "then reconnect."
        )
    if isinstance(exc, EngineMissing):
        return (
            "The CCS debug engine could not be found. Install TI Code Composer Studio 20.x "
            "or set CCS_ROOT to its installation path."
        )
    return f"An unexpected error occurred: {exc}"
