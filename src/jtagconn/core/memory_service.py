from __future__ import annotations

import re
import struct
from typing import Any

try:
    from PySide6.QtCore import QObject
except Exception:  # noqa: BLE001
    class QObject:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

from jtagconn.backend.base import DebugBackend, MemoryAccessError
from jtagconn.core.models import MemoryFormat, MemoryView, ProgramImage, ValueStatus
from jtagconn.core.target_manager import TargetManager


def _parse_address(expr: str) -> int | None:
    s = expr.strip().lower().replace("_", "")
    try:
        if s.startswith(("0x", "+0x", "-0x")):
            return int(s, 16)
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s, 10)
    except ValueError:
        return None
    return None


def _resolve_symbol_address(image: ProgramImage | None, backend: DebugBackend, core: str, name: str) -> int | None:
    if image is not None:
        for sym in getattr(image, "symbols", []) or []:
            if sym.name == name:
                return int(sym.address)
    try:
        for sym in backend.symbols(core):
            if sym.name == name:
                return int(sym.address)
    except Exception:  # noqa: BLE001, S110
        pass
    return None


class MemoryService(QObject):
    def __init__(self, backend: DebugBackend, target_manager: TargetManager | None = None) -> None:
        super().__init__()
        self.backend = backend
        self.target_manager = target_manager

    def _resolve_start(self, core: str, start_expr: str) -> int:
        addr = _parse_address(start_expr)
        if addr is not None:
            return addr
        img = self.target_manager.image_for_core(core) if self.target_manager else None
        saddr = _resolve_symbol_address(img, self.backend, core, start_expr.strip())
        if saddr is None:
            raise ValueError(f"Cannot resolve address or symbol: {start_expr}")
        return saddr

    def read_view(
        self,
        core: str,
        start_expr: str,
        length: int,
        fmt: MemoryFormat = MemoryFormat.hex16,
    ) -> MemoryView:
        """Read memory and return a MemoryView. Catches MemoryAccessError and returns
        status=error without disconnecting the core."""
        try:
            start_addr = self._resolve_start(core, start_expr)
        except Exception:  # noqa: BLE001
            return MemoryView(
                core=core,
                start_expr=start_expr,
                start_address=0,
                length=int(length),
                format=fmt,
                data=[],
                status=ValueStatus.error,
            )

        count = max(0, int(length))
        width_bits = self._width_bits_for_format(fmt)
        if count == 0:
            return MemoryView(
                core=core,
                start_expr=start_expr,
                start_address=start_addr,
                length=0,
                format=fmt,
                data=[],
                status=ValueStatus.current,
            )
        try:
            data = self.backend.read_memory(core, start_addr, count, width_bits)
            status = ValueStatus.current
        except MemoryAccessError:
            data = []
            status = ValueStatus.error
        except Exception:  # noqa: BLE001
            data = []
            status = ValueStatus.error

        return MemoryView(
            core=core,
            start_expr=start_expr,
            start_address=start_addr,
            length=count,
            format=fmt,
            data=[int(v) for v in data],
            status=status,
        )

    def format_memory_cells(self, view: MemoryView) -> list[str]:
        fmt = view.format
        cells: list[str] = []
        for v in view.data:
            cells.append(self._format_cell(int(v), fmt))
        return cells

    @staticmethod
    def _width_bits_for_format(fmt: MemoryFormat) -> int:
        if fmt in (MemoryFormat.hex16, MemoryFormat.int16, MemoryFormat.uint16):
            return 16
        if fmt in (MemoryFormat.hex32, MemoryFormat.int32, MemoryFormat.uint32, MemoryFormat.float32):
            return 32
        return 16

    @staticmethod
    def _to_signed(value: int, bits: int) -> int:
        mask = (1 << bits) - 1
        v = value & mask
        sign = 1 << (bits - 1)
        return v - (1 << bits) if (v & sign) else v

    @classmethod
    def _format_cell(cls, value: int, fmt: MemoryFormat) -> str:
        if fmt == MemoryFormat.hex16:
            return f"0x{(value & 0xFFFF):04X}"
        if fmt == MemoryFormat.hex32:
            return f"0x{(value & 0xFFFFFFFF):08X}"
        if fmt == MemoryFormat.uint16:
            return str(value & 0xFFFF)
        if fmt == MemoryFormat.int16:
            return str(cls._to_signed(value, 16))
        if fmt == MemoryFormat.uint32:
            return str(value & 0xFFFFFFFF)
        if fmt == MemoryFormat.int32:
            return str(cls._to_signed(value, 32))
        if fmt == MemoryFormat.float32:
            try:
                b = struct.pack(">I", value & 0xFFFFFFFF)
                f = struct.unpack(">f", b)[0]
                # compact display
                if f == 0.0:
                    return "0.0"
                return f"{f:.9g}"
            except Exception:  # noqa: BLE001
                return str(value)
        return str(value)
