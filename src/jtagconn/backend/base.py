from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol, runtime_checkable

from jtagconn.core.models import CoreState, Probe, StackFrame, Symbol, ValueNode


class JtagError(Exception):
    """Base exception for JTAG backend errors."""


class ProbeNotFound(JtagError):
    """No probe or driver found."""


class TargetNotResponding(JtagError):
    """No power, cable issue, or wrong device."""


class ProbeBusy(JtagError):
    """Another debugger owns the probe."""


class DeviceSecured(JtagError):
    """CSM/DCSM locked (no bypass attempted)."""


class CoreNotAvailable(JtagError):
    """Core not released by boot core."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class InvalidImage(JtagError):
    """Not an .out or wrong device."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class VerifyError(JtagError):
    """Load verification failed."""

    def __init__(self, address: int) -> None:
        self.address = address
        super().__init__(f"Verify failed at address 0x{address:X}")


class MemoryAccessError(JtagError):
    """Inaccessible memory range."""

    def __init__(self, range_info: str | tuple[int, int]) -> None:
        self.range_info = range_info
        super().__init__(f"Memory access error: {range_info}")


class ConnectionLost(JtagError):
    """Link dropped."""


class EngineMissing(JtagError):
    """CCS 20.x not found."""


@runtime_checkable
class DebugBackend(Protocol):
    def list_probes(self) -> list[Probe]: ...

    def configure(self, probe: Probe, device: str, ccxml: Path | None) -> list[str]:
        """Returns debuggable core names."""

    def connect(self, core: str) -> None: ...

    def disconnect(self, core: str) -> None: ...

    def load_program(
        self,
        core: str,
        image: Path,
        progress: Callable[[int], None],
        cancel: Event,
    ) -> None:
        """Downloads and verifies; raises VerifyError(address)."""

    def run(self, core: str) -> None: ...

    def halt(self, core: str) -> int:
        """Returns PC."""

    def reset(self, core: str) -> None: ...

    def run_all(self, cores: list[str]) -> None: ...

    def halt_all(self, cores: list[str]) -> None: ...

    def state(self, core: str) -> CoreState: ...

    def read_memory(
        self, core: str, address: int, count: int, width_bits: int
    ) -> list[int]: ...

    def write_memory(
        self, core: str, address: int, values: list[int], width_bits: int
    ) -> None: ...

    def supports_realtime(self, core: str) -> bool: ...

    def evaluate(
        self, core: str, expression: str, frame: int | None = None
    ) -> ValueNode: ...

    def assign(
        self, core: str, expression: str, value: str, frame: int | None = None
    ) -> None: ...

    def callstack(self, core: str) -> list[StackFrame]: ...

    def locals(self, core: str, frame: int) -> list[ValueNode]: ...

    def symbols(self, core: str) -> list[Symbol]: ...

    def ping(self) -> bool:
        """Used by watchdog."""
