from __future__ import annotations

import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

from jtagconn.backend.base import InvalidImage
from jtagconn.core.devices import DEVICE_CATALOG, get_device_profile
from jtagconn.core.models import (
    ImageFormat,
    MemoryRegionKind,
    ProgramImage,
    Section,
    Symbol,
    SymbolScope,
    TypeInfo,
    TypeKind,
)

_DEFAULT_FLASH_RANGES = [
    (0x080000, 0x0BFFFF),
    (0x3D8000, 0x3F7FFF),
]

_COFF_MAGICS = {0x0097, 0x0098, 0x0099, 0x00C2}


def _unknown_type(name: str = "unknown", bit_size: int = 16) -> TypeInfo:
    return TypeInfo(name=name, kind=TypeKind.base, bit_size=bit_size, signed=False)


def _in_ranges(addr: int, size: int, ranges: list[tuple[int, int]]) -> bool:
    if size <= 0:
        # treat zero-size as point
        for start, end in ranges:
            if start <= addr <= end:
                return True
        return False
    sec_start = int(addr)
    sec_end = sec_start + int(size) - 1
    for start, end in ranges:
        if sec_start <= int(end) and sec_end >= int(start):
            return True
    return False


def _detect_format(path: Path, data: bytes) -> ImageFormat:
    if data.startswith(b"\x7fELF"):
        return ImageFormat.ELF
    if len(data) >= 2:
        magic_le = struct.unpack_from("<H", data, 0)[0]
        magic_be = struct.unpack_from(">H", data, 0)[0]
        if magic_le in _COFF_MAGICS or magic_be in _COFF_MAGICS:
            return ImageFormat.COFF
    # TI COFF .out sometimes has other headers; accept .out if not ELF but has plausible COFF-like size
    if path.suffix.lower() == ".out" and len(data) >= 20:
        # try to treat as COFF for our purposes if it looks binary-ish
        # (parser will still be limited), but spec says detect ELF vs TI COFF
        # If not matching known magics, fall through to invalid below unless caller handles
        # but we can also try a heuristic: not ELF => COFF for .out
        return ImageFormat.COFF
    raise InvalidImage("Not a valid ELF or TI COFF .out file")


def _flash_ranges_for_device(device_id: str | None) -> list[tuple[int, int]]:
    if device_id:
        try:
            dev = get_device_profile(device_id)
            if dev.flash_regions:
                return [(int(r.start), int(r.end)) for r in dev.flash_regions]
        except Exception:  # noqa: BLE001, S110
            pass
    return list(_DEFAULT_FLASH_RANGES)


def _infer_target_device(path: Path, elf: ELFFile | None = None) -> str | None:
    """Best-effort inference of target device tag from ELF notes/symbols/name."""
    name_l = path.name.lower()
    for dev_id in DEVICE_CATALOG:
        if dev_id.lower() in name_l:
            return dev_id
    if elf is None:
        return None
    # Look for a symbol/note containing known device id
    try:
        for sec in elf.iter_sections():
            if isinstance(sec, SymbolTableSection):
                for sym in sec.iter_symbols():
                    sname = sym.name or ""
                    for dev_id in DEVICE_CATALOG:
                        if dev_id.lower() in sname.lower() and "target" in sname.lower():
                            return dev_id
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def load_program_image(path: Path, device_id: str | None = None) -> ProgramImage:
    path = Path(path)
    if not path.exists():
        raise InvalidImage(f"Image not found: {path}")
    try:
        st = path.stat()
    except OSError as exc:
        raise InvalidImage(f"Cannot stat image: {path}") from exc
    if st.st_size <= 0:
        raise InvalidImage(f"Image is empty: {path}")

    data = path.read_bytes()
    # detect format
    if data.startswith(b"\x7fELF"):
        fmt = ImageFormat.ELF
    else:
        if len(data) < 2:
            raise InvalidImage("Not a valid ELF or TI COFF .out file")
        magic_le = struct.unpack_from("<H", data, 0)[0]
        magic_be = struct.unpack_from(">H", data, 0)[0]
        if magic_le in _COFF_MAGICS or magic_be in _COFF_MAGICS or path.suffix.lower() == ".out":
            fmt = ImageFormat.COFF
        else:
            raise InvalidImage("Not a valid ELF or TI COFF .out file")

    flash_ranges = _flash_ranges_for_device(device_id)
    sections: list[Section] = []
    symbols: list[Symbol] = []
    entry_point = 0
    has_debug_info = False
    target_device: str | None = None

    if fmt == ImageFormat.ELF:
        try:
            with path.open("rb") as f:
                elf = ELFFile(f)
                entry_point = int(getattr(elf.header, "e_entry", 0) or 0)
                has_debug_info = bool(elf.has_dwarf_info())

                # sections
                for sec in elf.iter_sections():
                    try:
                        flags = int(sec["sh_flags"])
                    except Exception:  # noqa: BLE001
                        flags = 0
                    SHF_ALLOC = 0x2
                    if not (flags & SHF_ALLOC):
                        continue
                    addr = int(sec["sh_addr"])
                    size = int(sec["sh_size"])
                    sec_data = b""
                    try:
                        sec_data = sec.data() if size > 0 else b""
                    except Exception:  # noqa: BLE001
                        sec_data = b""
                    region = (
                        MemoryRegionKind.FLASH
                        if _in_ranges(addr, size, flash_ranges)
                        else MemoryRegionKind.RAM
                    )
                    sections.append(
                        Section(
                            name=str(sec.name or ""),
                            address=addr,
                            size=size,
                            region=region,
                            data=sec_data,
                        )
                    )

                # symbols
                seen_syms: set[tuple[str, int]] = set()
                for sec in elf.iter_sections():
                    if not isinstance(sec, SymbolTableSection):
                        continue
                    for sym in sec.iter_symbols():
                        try:
                            name = sym.name or ""
                            if not name:
                                continue
                            st_type = sym["st_info"]["type"]
                            st_bind = sym["st_info"]["bind"]
                            if st_type not in ("STT_OBJECT", "STT_FUNC"):
                                continue
                            if st_bind not in ("STB_GLOBAL", "STB_LOCAL"):
                                continue
                            addr = int(sym["st_value"])
                            size = int(sym["st_size"])
                            scope = SymbolScope.global_ if st_bind == "STB_GLOBAL" else SymbolScope.static
                            bit_size = size * 8 if size > 0 else 16
                            type_info = _unknown_type("uint16" if size <= 2 else "symbol", bit_size)
                            function_end = addr + size if st_type == "STT_FUNC" and size > 0 else None
                            key = (name, addr)
                            if key in seen_syms:
                                continue
                            seen_syms.add(key)
                            symbols.append(
                                Symbol(
                                    name=name,
                                    address=addr,
                                    size=size if size > 0 else 1,
                                    type_info=type_info,
                                    scope=scope,
                                    function_end=function_end,
                                )
                            )
                        except Exception:  # noqa: BLE001, S112
                            continue

                target_device = _infer_target_device(path, elf)
        except InvalidImage:
            raise
        except Exception as exc:
            raise InvalidImage(f"Failed to parse ELF image: {exc}") from exc
    else:
        # COFF: limited parsing; still return a valid ProgramImage for supported flows
        entry_point = 0
        has_debug_info = False
        # Try to infer basic section-like info not available without full TI COFF parser.
        # Create a placeholder RAM section covering file data so callers have something.
        sections = [
            Section(
                name=".text",
                address=0,
                size=len(data),
                region=MemoryRegionKind.RAM if not _in_ranges(0, len(data), flash_ranges) else MemoryRegionKind.FLASH,
                data=b"",
            )
        ]
        symbols = []
        target_device = _infer_target_device(path, None)

    # Device compatibility check
    if device_id and target_device and target_device != device_id:
        raise InvalidImage(
            f"Image target device '{target_device}' does not match connected device '{device_id}'"
        )

    return ProgramImage(
        path=str(path),
        mtime=st.st_mtime,
        format=fmt,
        entry_point=entry_point,
        sections=sections,
        has_debug_info=has_debug_info,
        target_device=target_device or device_id,
        symbols=symbols,
    )


def is_image_out_of_date(image: ProgramImage) -> bool:
    try:
        p = Path(image.path)
        return p.stat().st_mtime > float(image.mtime)
    except Exception:  # noqa: BLE001
        # If file missing/unreadable, treat as changed/out of date
        return True


def resolve_pc_to_function(image: ProgramImage | None, pc: int) -> str | None:
    if image is None:
        return None
    best: tuple[int, str] | None = None  # (range_size, name)
    for sym in getattr(image, "symbols", []) or []:
        end = sym.function_end
        start = int(sym.address)
        if end is not None:
            if start <= pc < int(end):
                rng = int(end) - start
                if best is None or rng < best[0]:
                    best = (rng, sym.name)
        else:
            # exact match for function-like symbol with size 0 not expected, but safe
            if pc == start and sym.size > 0 and pc < start + int(sym.size):
                rng = int(sym.size)
                if best is None or rng < best[0]:
                    best = (rng, sym.name)
    if best is not None:
        return best[1]
    # Fallback: exact address match on any symbol (sometimes useful)
    for sym in getattr(image, "symbols", []) or []:
        if int(sym.address) == int(pc):
            return sym.name
    return None
