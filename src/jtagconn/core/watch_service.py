from __future__ import annotations

import time
from typing import Any

try:
    from PySide6.QtCore import QObject, Signal
except Exception:  # noqa: BLE001
    class QObject:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _SignalDescriptor:
        def __init__(self) -> None:
            self._name = ""

        def __set_name__(self, owner: type, name: str) -> None:
            self._name = name

        def __get__(self, obj: Any, objtype: type | None = None) -> Any:
            if obj is None:
                return _SignalInstance(None, self._name)
            signals = obj.__dict__.setdefault("_signals", {})
            inst = signals.get(self._name)
            if inst is None:
                inst = _SignalInstance(obj, self._name)
                signals[self._name] = inst
            return inst

    class _SignalInstance:
        def __init__(self, obj: Any, name: str) -> None:
            self._obj = obj
            self._name = name

        def connect(self, slot: Any) -> None:
            if self._obj is None:
                return
            self._obj.__dict__.setdefault("_slots", {}).setdefault(self._name, []).append(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            if self._obj is None:
                return
            for slot in self._obj.__dict__.get("_slots", {}).get(self._name, []):
                try:
                    slot(*args, **kwargs)
                except Exception:  # noqa: BLE001, S110
                    pass

    class Signal:  # type: ignore[no-redef]
        def __init__(self, *args: Any) -> None:
            self._desc = _SignalDescriptor()

        def __set_name__(self, owner: type, name: str) -> None:
            self._desc.__set_name__(owner, name)

        def __get__(self, obj: Any, objtype: type | None = None) -> Any:
            return self._desc.__get__(obj, objtype)

from jtagconn.backend.base import DebugBackend, JtagError
from jtagconn.core.models import (
    CoreState,
    DisplayFormat,
    ProgramImage,
    TypeInfo,
    ValueNode,
    ValueStatus,
    WatchEntry,
)
from jtagconn.core.target_manager import TargetManager
from jtagconn.symbols.types import format_value, parse_and_validate_value


def _node_signature(node: ValueNode | None) -> tuple:
    if node is None:
        return ("none",)
    return (
        node.display_value,
        node.status.value if hasattr(node.status, "value") else str(node.status),
        tuple(_node_signature(ch) for ch in (node.children or [])),
    )


def _apply_format_to_node(node: ValueNode, type_info: TypeInfo | None, fmt: DisplayFormat) -> ValueNode:
    # Reformat display values recursively when type info is known
    new = node.model_copy(deep=True)
    if type_info is not None and new.status == ValueStatus.current:
        try:
            new.display_value = format_value(new.raw_value, type_info, fmt)
        except Exception:  # noqa: BLE001, S110
            pass
    # children: without per-child type info map we keep backend-provided display but preserve structure
    return new


class WatchService(QObject):
    watchUpdated = Signal(str, list)  # (core, changed_entries)

    def __init__(
        self,
        backend: DebugBackend,
        target_manager: TargetManager | None = None,
    ) -> None:
        super().__init__()
        self.backend = backend
        self.target_manager = target_manager
        self._entries: dict[str, dict[str, WatchEntry]] = {}  # core -> expr -> entry
        self._signatures: dict[str, dict[str, tuple]] = {}
        self._paused = False

    # --- management ---
    def add_watch(self, core: str, expression: str, fmt: DisplayFormat = DisplayFormat.natural) -> WatchEntry:
        expr = expression.strip()
        core_entries = self._entries.setdefault(core, {})
        if expr in core_entries:
            entry = core_entries[expr]
            entry.format = fmt
            return entry
        entry = WatchEntry(
            expression=expr,
            core=core,
            format=fmt,
            value=None,
            status=ValueStatus.current,
            updated_at=time.time(),
        )
        core_entries[expr] = entry
        self._signatures.setdefault(core, {}).pop(expr, None)
        # eager refresh for this entry
        self.refresh(core, force_emit=True)
        return core_entries[expr]

    def remove_watch(self, core: str, expression: str) -> None:
        expr = expression.strip()
        core_entries = self._entries.get(core, {})
        core_entries.pop(expr, None)
        self._signatures.get(core, {}).pop(expr, None)

    def set_format(self, core: str, expression: str, fmt: DisplayFormat) -> WatchEntry:
        expr = expression.strip()
        entry = self._entries.get(core, {}).get(expr)
        if entry is None:
            raise JtagError(f"Watch entry not found: {expr}")
        entry.format = fmt
        self._signatures.get(core, {}).pop(expr, None)
        self.refresh(core, force_emit=True)
        return entry

    def entries(self, core: str) -> list[WatchEntry]:
        return list(self._entries.get(core, {}).values())

    def set_polling_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    # --- refresh/eval ---
    def refresh(self, core: str, force_emit: bool = False) -> list[WatchEntry]:
        if self._paused and not force_emit:
            return []

        core_entries = self._entries.setdefault(core, {})
        if not core_entries and not force_emit:
            return []

        # Determine core state
        state = CoreState.Disconnected
        if self.target_manager is not None:
            state = self.target_manager.core_state(core)
        else:
            try:
                state = self.backend.state(core)
            except Exception:  # noqa: BLE001
                state = CoreState.Disconnected

        changed: list[WatchEntry] = []
        sigs = self._signatures.setdefault(core, {})

        for expr, entry in core_entries.items():
            if state in (CoreState.Disconnected, CoreState.ConnectionLost):
                new_status = ValueStatus.stale
                val_node = entry.value
                if val_node is None:
                    val_node = ValueNode(
                        name=expr,
                        expression=expr,
                        type_name="unknown",
                        raw_value=None,
                        display_value="",
                        status=new_status,
                    )
                else:
                    val_node = val_node.model_copy(deep=True)
                    val_node.status = new_status
                entry.value = val_node
                entry.status = new_status
                entry.updated_at = time.time()
            elif state == CoreState.Running:
                try:
                    rt = self.backend.supports_realtime(core)
                except Exception:  # noqa: BLE001
                    rt = False
                if not rt:
                    new_status = ValueStatus.stale
                    val_node = entry.value
                    if val_node is None:
                        val_node = ValueNode(
                            name=expr,
                            expression=expr,
                            type_name="unknown",
                            raw_value=None,
                            display_value="",
                            status=new_status,
                        )
                    else:
                        val_node = val_node.model_copy(deep=True)
                        val_node.status = new_status
                    entry.value = val_node
                    entry.status = new_status
                    entry.updated_at = time.time()
                else:
                    self._evaluate_into_entry(core, entry)
            else:
                # Halted or other readable state
                self._evaluate_into_entry(core, entry)

            sig = (entry.status.value if hasattr(entry.status, "value") else str(entry.status), _node_signature(entry.value))
            prev = sigs.get(expr)
            if force_emit or prev != sig:
                changed.append(entry.model_copy(deep=True))
                sigs[expr] = sig

        if changed:
            self.watchUpdated.emit(core, changed)
        return changed

    def _evaluate_into_entry(self, core: str, entry: WatchEntry) -> None:
        try:
            node = self.backend.evaluate(core, entry.expression)
            # apply formatting if we know symbol type
            tinfo = self._resolve_type(core, entry.expression)
            if tinfo is not None and node.status == ValueStatus.current:
                try:
                    node = _apply_format_to_node(node, tinfo, entry.format)
                    if node.type_name in ("unknown", "", None):
                        node.type_name = tinfo.name
                except Exception:  # noqa: BLE001, S110
                    pass
            entry.value = node
            entry.status = node.status
            entry.updated_at = time.time()
        except Exception:  # noqa: BLE001
            node = ValueNode(
                name=entry.expression,
                expression=entry.expression,
                type_name="unknown",
                raw_value=None,
                display_value="error",
                status=ValueStatus.error,
            )
            entry.value = node
            entry.status = ValueStatus.error
            entry.updated_at = time.time()

    def modify_value(self, core: str, expression: str, new_value_str: str) -> WatchEntry:
        expr = expression.strip()
        # Resolve type info if known and validate BEFORE backend.assign (SC-007)
        type_info = self._resolve_type(core, expr)
        if type_info is not None:
            # raises ValueError if invalid/out of range; must not touch target
            parse_and_validate_value(new_value_str, type_info)

        # perform write
        self.backend.assign(core, expr, new_value_str)
        # re-evaluate to verify read-back (SC-005)
        node = self.backend.evaluate(core, expr)
        if type_info is not None and node.status == ValueStatus.current:
            try:
                node.display_value = format_value(node.raw_value, type_info, self._entry_format(core, expr))
            except Exception:  # noqa: BLE001, S110
                pass

        entry = self._entries.setdefault(core, {}).get(expr)
        if entry is None:
            entry = WatchEntry(expression=expr, core=core, value=node, status=node.status, updated_at=time.time())
            self._entries.setdefault(core, {})[expr] = entry
        else:
            entry.value = node
            entry.status = node.status
            entry.updated_at = time.time()

        # force signature update and emit change
        self._signatures.setdefault(core, {})[expr] = (entry.status.value, _node_signature(entry.value))
        self.watchUpdated.emit(core, [entry.model_copy(deep=True)])
        return entry

    def _entry_format(self, core: str, expr: str) -> DisplayFormat:
        entry = self._entries.get(core, {}).get(expr)
        return entry.format if entry else DisplayFormat.natural

    def _resolve_type(self, core: str, expression: str) -> TypeInfo | None:
        # Try backend symbols first
        try:
            for sym in self.backend.symbols(core):
                if sym.name == expression:
                    return sym.type_info
        except Exception:  # noqa: BLE001, S110
            pass
        # Try selected image symbols
        img: ProgramImage | None = None
        if self.target_manager is not None:
            img = self.target_manager.image_for_core(core)
        if img is not None:
            for sym in getattr(img, "symbols", []) or []:
                if sym.name == expression:
                    return sym.type_info
                # simple member lookup: base.member
                if "." in expression:
                    base, member = expression.split(".", 1)
                    if sym.name == base:
                        fld = sym.type_info.fields.get(member)
                        if fld:
                            return fld[1]
                # array element: base[idx]
                if expression.startswith(sym.name + "[") and sym.type_info.element_type is not None:
                    return sym.type_info.element_type
        return None
