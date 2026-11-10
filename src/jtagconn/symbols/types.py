from __future__ import annotations

import math
import re

from jtagconn.core.models import DisplayFormat, TypeInfo, TypeKind

_INT_BOUNDS: dict[tuple[int, bool], tuple[int, int]] = {
    # (bit_size, signed): (min, max)
    (8, True): (-128, 127),
    (8, False): (0, 255),
    (16, True): (-32768, 32767),
    (16, False): (0, 65535),
    (32, True): (-2147483648, 2147483647),
    (32, False): (0, 4294967295),
    (64, True): (-9223372036854775808, 9223372036854775807),
    (64, False): (0, 18446744073709551615),
}


def _effective_type(type_info: TypeInfo) -> TypeInfo:
    t = type_info
    while t.kind == TypeKind.typedef and t.element_type is not None:
        t = t.element_type
    return t


def format_value(
    raw_value: float | str | None,
    type_info: TypeInfo,
    fmt: DisplayFormat = DisplayFormat.natural,
) -> str:
    """Format a raw value according to type information and display format."""
    if raw_value is None:
        return ""

    t = _effective_type(type_info)

    # Enum formatting
    if t.kind == TypeKind.enum:
        try:
            ival = int(raw_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            ival = None
        name_for_val = None
        if ival is not None:
            for k, v in t.enum_values.items():
                if int(v) == ival:
                    name_for_val = k
                    break
        if fmt == DisplayFormat.natural:
            if name_for_val is not None and ival is not None:
                return f"{name_for_val} ({ival})"
            return str(raw_value)
        if ival is None:
            return str(raw_value)
        return _format_int(ival, fmt, signed=t.signed, bit_size=t.bit_size)

    # Pointer formatting
    if t.kind == TypeKind.pointer:
        try:
            ival = int(raw_value)  # type: ignore[arg-type]
            if ival < 0:
                ival = ival & ((1 << max(t.bit_size, 1)) - 1)
            return f"0x{ival:X}"
        except (TypeError, ValueError):
            return str(raw_value)

    # Float formatting
    if t.kind == TypeKind.base and t.float_type:
        try:
            fval = float(raw_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(raw_value)
        if fmt == DisplayFormat.hex:
            # show raw IEEE-ish representation via cast if integer-sized container known
            return str(fval)
        # natural/dec: compact representation
        if fval.is_integer() and abs(fval) < 2**53:
            return str(int(fval))
        return f"{fval:.9g}"

    # Integer / base / bitfield
    try:
        ival = int(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(raw_value)

    if fmt == DisplayFormat.natural:
        # natural defaults to decimal for integers
        return str(ival)
    return _format_int(ival, fmt, signed=t.signed, bit_size=t.bit_size)


def _format_int(value: int, fmt: DisplayFormat, signed: bool = False, bit_size: int = 32) -> str:
    if fmt == DisplayFormat.hex:
        width = max(1, (bit_size + 3) // 4)
        v = value
        if v < 0:
            v = v & ((1 << bit_size) - 1) if bit_size > 0 else v
        return f"0x{v:0{width}X}"
    if fmt == DisplayFormat.bin:
        width = max(0, bit_size)
        v = value
        if v < 0 and bit_size > 0:
            v = v & ((1 << bit_size) - 1)
        s = format(v, "b")
        if width:
            s = s.zfill(width)
        return f"0b{s}"
    # dec or fallback
    return str(value)


def parse_and_validate_value(input_str: str, type_info: TypeInfo) -> int | float:
    """Parse and validate a user input string against type_info.

    Supports decimal, 0x hex, 0b binary, float, enum constant names or values.
    Enforces signed/unsigned bit-width bounds. Raises ValueError with a descriptive
    reason if invalid or out of range.
    """
    s = input_str.strip()
    if s == "":
        raise ValueError("Value cannot be empty")

    t = _effective_type(type_info)

    # Enum: accept name or numeric value
    if t.kind == TypeKind.enum:
        if s in t.enum_values:
            val = int(t.enum_values[s])
            _validate_int_bounds(val, t)
            return val
        # try numeric
        try:
            val = _parse_int_literal(s)
        except ValueError as exc:
            allowed = ", ".join(list(t.enum_values.keys())[:8])
            raise ValueError(
                f"Invalid enum value '{s}' for {t.name}; expected one of [{allowed}] or a numeric value"
            ) from exc
        # allow numeric even if not a named constant, but enforce bounds
        _validate_int_bounds(val, t)
        return val

    # Float base types
    if t.kind == TypeKind.base and t.float_type:
        try:
            fval = float(s)
        except ValueError as exc:
            raise ValueError(f"Invalid float value '{s}' for {t.name}") from exc
        if not math.isfinite(fval):
            raise ValueError(f"Float value '{s}' is not finite")
        return fval

    # Pointer/base integer/bitfield
    if t.kind in (TypeKind.base, TypeKind.bitfield, TypeKind.pointer):
        try:
            ival = _parse_int_literal(s)
        except ValueError as exc:
            raise ValueError(f"Invalid integer value '{s}' for {t.name}") from exc
        _validate_int_bounds(ival, t)
        return ival

    # Fallback: try int then float
    try:
        ival = _parse_int_literal(s)
        _validate_int_bounds(ival, t)
        return ival
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError as exc:
        raise ValueError(f"Invalid value '{s}' for type {t.name}") from exc


def _parse_int_literal(s: str) -> int:
    sl = s.lower().replace("_", "")
    if sl.startswith(("+0x", "-0x")):
        return int(sl, 16)
    if sl.startswith("0x"):
        return int(sl, 16)
    if sl.startswith(("+0b", "-0b")):
        return int(sl, 2)
    if sl.startswith("0b"):
        return int(sl, 2)
    # decimal (allow leading +/-)
    if re.fullmatch(r"[+-]?\d+", sl):
        return int(sl, 10)
    raise ValueError(f"Not an integer literal: {s}")


def _validate_int_bounds(value: int, type_info: TypeInfo) -> None:
    bit_size = int(type_info.bit_size)
    signed = bool(type_info.signed)
    if type_info.kind == TypeKind.pointer:
        signed = False
        if bit_size <= 0:
            bit_size = 32
    bounds = _INT_BOUNDS.get((bit_size, signed))
    if bounds is None and bit_size > 0:
        if signed:
            lo = -(1 << (bit_size - 1))
            hi = (1 << (bit_size - 1)) - 1
        else:
            lo = 0
            hi = (1 << bit_size) - 1
        bounds = (lo, hi)
    if bounds is None:
        return
    lo, hi = bounds
    if value < lo or value > hi:
        sign_label = "signed" if signed else "unsigned"
        raise ValueError(
            f"Value {value} is out of range for {sign_label} {bit_size}-bit type {type_info.name} "
            f"(valid range: {lo}..{hi})"
        )


def coalesce_read_ranges(
    addresses_and_sizes: list[tuple[int, int]],
    max_gap: int = 8,
    max_block: int = 128,
) -> list[tuple[int, int]]:
    """Coalesce adjacent or nearby symbol (address, size) requests into contiguous blocks.

    Returns list of (start_address, total_length) blocks to minimize JTAG read round-trips.
    Sizes/lengths are in the core's native address units.
    """
    if not addresses_and_sizes:
        return []

    # Normalize and sort by start address
    ranges: list[tuple[int, int]] = []
    for addr, size in addresses_and_sizes:
        a = int(addr)
        s = max(0, int(size))
        if s <= 0:
            continue
        ranges.append((a, a + s))  # [start, end)
    if not ranges:
        return []
    ranges.sort()

    merged: list[list[int]] = [[ranges[0][0], ranges[0][1]]]
    for start, end in ranges[1:]:
        cur_start, cur_end = merged[-1][0], merged[-1][1]
        gap = start - cur_end
        new_len = end - cur_start
        if gap <= max_gap and new_len <= max_block:
            # merge (including overlap or nearby gap)
            if end > cur_end:
                merged[-1][1] = end
            # if start already inside current, nothing else to do
        else:
            merged.append([start, end])

    return [(s, e - s) for s, e in merged]
