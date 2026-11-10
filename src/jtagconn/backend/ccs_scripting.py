from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from jtagconn.backend.base import (
    CoreNotAvailable,
    DebugBackend,
    EngineMissing,
    InvalidImage,
    JtagError,
    MemoryAccessError,
    VerifyError,
)
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, Probe, StackFrame, Symbol, ValueNode


def _discover_ccs_root() -> Path | None:
    env = os.environ.get("CCS_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p
    candidates = [
        Path(r"C:\ti\ccs2000"),
        Path(r"C:\ti\ccs2001"),
        Path(r"C:\ti\ccs2002"),
        Path(r"C:\ti\ccs2010"),
        Path(r"C:\ti\ccs2011"),
        Path(r"C:\ti\ccs2020"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


class CcsScriptingBackend(DebugBackend):
    """Debug backend implemented via TI CCS 20.x scripting API."""

    def __init__(self, logger: OperationLogger | None = None) -> None:
        self.logger = logger or OperationLogger()
        self._scripting: Any | None = None
        self._debug_server: Any | None = None
        self._sessions: dict[str, Any] = {}
        self._configured: tuple[Probe, str, Path | None] | None = None
        self._core_states: dict[str, CoreState] = {}

    def _ensure_engine(self) -> Any:
        if self._scripting is not None:
            return self._scripting
        root = _discover_ccs_root()
        if root is None:
            raise EngineMissing(
                "CCS 20.x installation not found. Set CCS_ROOT or install CCS."
            )
        scripting_path = root / "ccs_base" / "DebugServer" / "packages"
        if scripting_path.exists():
            sys.path.insert(0, str(scripting_path))
        try:
            self._scripting = importlib.import_module("scripting")
        except Exception as exc:  # pragma: no cover - requires CCS
            raise EngineMissing(f"Failed to import CCS scripting API: {exc}") from exc
        self.logger.log("info", "engine.init", f"CCS scripting loaded from {root}")
        return self._scripting

    def list_probes(self) -> list[Probe]:
        # CCS enumeration varies by environment; return empty list when not enumerable.
        self._ensure_engine()
        self.logger.log("info", "list_probes", "Probe enumeration requested")
        return []

    def configure(self, probe: Probe, device: str, ccxml: Path | None) -> list[str]:
        scripting = self._ensure_engine()
        if ccxml is None:
            raise JtagError("CCS scripting backend requires a ccxml path")
        try:
            server = scripting.initScripting()  # type: ignore[attr-defined]
            self._debug_server = server
            server.setConfig(str(ccxml))
            core_names = list(server.getListOfCPUs())
        except Exception as exc:  # pragma: no cover - requires CCS
            raise JtagError(f"Failed to configure CCS session: {exc}") from exc
        self._configured = (probe, device, ccxml)
        self._core_states = {name: CoreState.Disconnected for name in core_names}
        self.logger.log("info", "configure", f"Configured {device} cores={core_names}")
        return core_names

    def _session(self, core: str) -> Any:
        if core not in self._sessions:
            raise CoreNotAvailable(f"Core not connected: {core}")
        return self._sessions[core]

    def connect(self, core: str) -> None:
        if self._debug_server is None:
            raise JtagError("Backend not configured")
        try:
            session = self._debug_server.openSession(core)
            session.target.connect()
            self._sessions[core] = session
            self._core_states[core] = CoreState.Halted
        except Exception as exc:  # pragma: no cover - requires CCS
            raise JtagError(f"Failed to connect to {core}: {exc}") from exc
        self.logger.log("info", "connect", f"Connected to {core}", core=core)

    def disconnect(self, core: str) -> None:
        session = self._sessions.pop(core, None)
        if session is not None:
            try:
                session.target.disconnect()
            except Exception:  # noqa: BLE001, S110
                pass
        self._core_states[core] = CoreState.Disconnected
        self.logger.log("info", "disconnect", f"Disconnected from {core}", core=core)

    def load_program(
        self, core: str, image: Path, progress: Callable[[int], None], cancel: Event
    ) -> None:
        session = self._session(core)
        if cancel.is_set():
            return
        progress(0)
        try:
            session.memory.loadProgram(str(image))
        except Exception as exc:  # pragma: no cover - requires CCS
            msg = str(exc).lower()
            if "verify" in msg:
                raise VerifyError(0) from exc
            raise InvalidImage(str(exc)) from exc
        progress(100)
        self.logger.log("info", "load_program", f"Loaded {image}", core=core)

    def run(self, core: str) -> None:
        self._session(core).target.run()
        self._core_states[core] = CoreState.Running
        self.logger.log("info", "run", "Target running", core=core)

    def halt(self, core: str) -> int:
        session = self._session(core)
        session.target.halt()
        self._core_states[core] = CoreState.Halted
        try:
            pc = int(session.expression.evaluate("PC"))
        except Exception:  # noqa: BLE001
            pc = 0
        self.logger.log("info", "halt", f"Target halted at PC=0x{pc:X}", core=core)
        return pc

    def reset(self, core: str) -> None:
        self._session(core).target.reset()
        self._core_states[core] = CoreState.Halted
        self.logger.log("info", "reset", "Target reset", core=core)

    def run_all(self, cores: list[str]) -> None:
        for core in cores:
            self.run(core)

    def halt_all(self, cores: list[str]) -> None:
        for core in cores:
            self.halt(core)

    def state(self, core: str) -> CoreState:
        return self._core_states.get(core, CoreState.Disconnected)

    def read_memory(self, core: str, address: int, count: int, width_bits: int) -> list[int]:
        session = self._session(core)
        page = 0
        try:
            data = session.memory.readData(page, address, width_bits, count)
            return [int(v) for v in data]
        except Exception as exc:  # pragma: no cover - requires CCS
            raise MemoryAccessError((address, address + count)) from exc

    def write_memory(self, core: str, address: int, values: list[int], width_bits: int) -> None:
        session = self._session(core)
        page = 0
        try:
            session.memory.writeData(page, address, values, width_bits)
        except Exception as exc:  # pragma: no cover - requires CCS
            raise MemoryAccessError((address, address + len(values))) from exc

    def supports_realtime(self, core: str) -> bool:
        return True

    def evaluate(self, core: str, expression: str, frame: int | None = None) -> ValueNode:
        session = self._session(core)
        try:
            raw = session.expression.evaluate(expression)
        except Exception as exc:  # pragma: no cover - requires CCS
            raise JtagError(f"Failed to evaluate '{expression}': {exc}") from exc
        return ValueNode(
            name=expression,
            expression=expression,
            type_name="unknown",
            raw_value=raw if isinstance(raw, (int, float, str)) else str(raw),
            display_value=str(raw),
        )

    def assign(self, core: str, expression: str, value: str, frame: int | None = None) -> None:
        session = self._session(core)
        try:
            session.expression.evaluate(f"{expression} = {value}")
        except Exception as exc:  # pragma: no cover - requires CCS
            raise JtagError(f"Failed to assign '{expression}': {exc}") from exc

    def callstack(self, core: str) -> list[StackFrame]:
        # Simplified mapping; full stack integration depends on CCS debug model.
        session = self._session(core)
        frames: list[StackFrame] = []
        try:
            pc = int(session.expression.evaluate("PC"))
        except Exception:  # noqa: BLE001
            pc = 0
        frames.append(StackFrame(index=0, function="?", pc=pc, locals=[]))
        return frames

    def locals(self, core: str, frame: int) -> list[ValueNode]:
        return []

    def symbols(self, core: str) -> list[Symbol]:
        return []

    def ping(self) -> bool:
        return bool(self._sessions)
