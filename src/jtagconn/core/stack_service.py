from __future__ import annotations

from typing import Any

try:
    from PySide6.QtCore import QObject
except Exception:  # noqa: BLE001
    class QObject:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

from jtagconn.backend.base import DebugBackend, JtagError
from jtagconn.core.models import CoreState, StackFrame, TypeInfo, TypeKind, ValueNode, ValueStatus
from jtagconn.core.target_manager import TargetManager
from jtagconn.symbols.types import parse_and_validate_value


def _typeinfo_for_local(name: str, type_name: str) -> TypeInfo | None:
    t = (type_name or "").lower()
    if t in ("int16", "short", "int"):
        return TypeInfo(name="int16", kind=TypeKind.base, bit_size=16, signed=True)
    if t in ("uint16", "unsigned int", "unsigned short"):
        return TypeInfo(name="uint16", kind=TypeKind.base, bit_size=16, signed=False)
    if t in ("int32", "long"):
        return TypeInfo(name="int32", kind=TypeKind.base, bit_size=32, signed=True)
    if t in ("uint32", "unsigned long"):
        return TypeInfo(name="uint32", kind=TypeKind.base, bit_size=32, signed=False)
    if t in ("float", "float32"):
        return TypeInfo(name="float32", kind=TypeKind.base, bit_size=32, float_type=True)
    return None


class StackService(QObject):
    def __init__(self, backend: DebugBackend, target_manager: TargetManager | None = None) -> None:
        super().__init__()
        self.backend = backend
        self.target_manager = target_manager

    def _core_state(self, core: str) -> CoreState:
        if self.target_manager is not None:
            return self.target_manager.core_state(core)
        try:
            return self.backend.state(core)
        except Exception:  # noqa: BLE001
            return CoreState.Disconnected

    def refresh_stack(self, core: str) -> list[StackFrame]:
        st = self._core_state(core)
        if st == CoreState.Halted:
            try:
                frames = self.backend.callstack(core)
                return list(frames)
            except Exception:  # noqa: BLE001
                return []
        # Running or Disconnected (and other non-halted): clear frames
        return []

    def get_frame_locals(self, core: str, frame_index: int = 0) -> list[ValueNode]:
        st = self._core_state(core)
        if st == CoreState.Halted:
            try:
                return list(self.backend.locals(core, int(frame_index)))
            except Exception:  # noqa: BLE001
                return []
        # when running/disconnected, mark locals unavailable
        try:
            locals_now = self.backend.locals(core, int(frame_index))
        except Exception:  # noqa: BLE001
            locals_now = []
        out: list[ValueNode] = []
        for v in locals_now:
            nv = v.model_copy(deep=True)
            nv.status = ValueStatus.unavailable
            nv.display_value = nv.display_value or "unavailable"
            out.append(nv)
        # If backend returns none while running, return empty list (cleared/unavailable context)
        return out

    def modify_local(self, core: str, frame_index: int, name: str, new_value_str: str) -> ValueNode:
        st = self._core_state(core)
        if st != CoreState.Halted:
            raise JtagError("Cannot modify local variables unless the core is halted")

        # find local and its type
        try:
            locals_list = self.backend.locals(core, int(frame_index))
        except Exception:  # noqa: BLE001
            locals_list = []
        target: ValueNode | None = None
        for v in locals_list:
            if v.name == name or v.expression == name:
                target = v
                break
        if target is None:
            raise JtagError(f"Local variable not found: {name}")

        # validate against local's type if known (int16, uint16 etc.)
        tinfo = _typeinfo_for_local(target.name, target.type_name)
        if tinfo is not None:
            parse_and_validate_value(new_value_str, tinfo)

        # assign in backend (supports frame-aware update in SimulatedBackend)
        self.backend.assign(core, target.expression or target.name, new_value_str, frame=int(frame_index))

        # return updated ValueNode
        updated_locals = self.backend.locals(core, int(frame_index))
        for v in updated_locals:
            if v.name == name or v.expression == name:
                return v
        # fallback: re-evaluate expression
        try:
            return self.backend.evaluate(core, target.expression or name, frame=int(frame_index))
        except Exception:  # noqa: BLE001
            nv = target.model_copy(deep=True)
            nv.raw_value = new_value_str
            nv.display_value = new_value_str
            return nv
