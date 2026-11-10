from __future__ import annotations

import pytest

from jtagconn.core.models import DisplayFormat, Symbol, SymbolScope, TypeInfo, TypeKind
from jtagconn.symbols.index import SymbolIndex
from jtagconn.symbols.types import coalesce_read_ranges, format_value, parse_and_validate_value


def make_symbol(name: str, addr: int = 0, size: int = 1) -> Symbol:
    return Symbol(
        name=name,
        address=addr,
        size=size,
        type_info=TypeInfo(name="uint16", kind=TypeKind.base, bit_size=16, signed=False),
        scope=SymbolScope.global_,
    )


class TestSymbolIndex:
    def test_prefix_and_substring_search(self) -> None:
        idx = SymbolIndex(
            [
                make_symbol("g_counter"),
                make_symbol("g_ctrl"),
                make_symbol("my_counter"),
                make_symbol("alpha"),
            ]
        )
        # prefix matches first
        res = idx.search("g_c")
        names = [s.name for s in res]
        assert names[0] == "g_counter"
        assert "g_ctrl" in names
        # substring matches included after prefix
        res2 = idx.search("counter")
        names2 = [s.name for s in res2]
        assert names2[0] == "g_counter" or names2[0] == "my_counter"
        assert "g_counter" in names2 and "my_counter" in names2

    def test_case_insensitive_and_get(self) -> None:
        idx = SymbolIndex([make_symbol("MotorSpeed"), make_symbol("g_status")])
        assert idx.get("motorspeed") is not None
        assert idx.get("MotorSpeed") is not None
        assert [s.name for s in idx.search("motor", limit=10)] == ["MotorSpeed"]

    def test_limit(self) -> None:
        idx = SymbolIndex([make_symbol(f"sym_{i}") for i in range(20)])
        assert len(idx.search("sym", limit=5)) == 5


class TestTypeFormattingAndValidation:
    def test_format_integer_hex_dec_bin_natural(self) -> None:
        t_u16 = TypeInfo(name="uint16", kind=TypeKind.base, bit_size=16, signed=False)
        assert format_value(255, t_u16, DisplayFormat.hex).lower().startswith("0x")
        assert format_value(255, t_u16, DisplayFormat.dec) == "255"
        assert format_value(5, t_u16, DisplayFormat.bin).startswith("0b")
        assert format_value(255, t_u16, DisplayFormat.natural) == "255"

    def test_format_enum_natural_and_other(self) -> None:
        t_enum = TypeInfo(
            name="status_t",
            kind=TypeKind.enum,
            bit_size=16,
            signed=False,
            enum_values={"IDLE": 0, "RUN": 1, "FAULT": 2},
        )
        assert format_value(0, t_enum, DisplayFormat.natural) == "IDLE (0)"
        assert format_value(2, t_enum, DisplayFormat.natural) == "FAULT (2)"
        assert "0x" in format_value(1, t_enum, DisplayFormat.hex).lower() or format_value(1, t_enum, DisplayFormat.hex) in ("0x0001", "0x1")

    def test_parse_and_validate_integers_bounds(self) -> None:
        t_i16 = TypeInfo(name="int16", kind=TypeKind.base, bit_size=16, signed=True)
        t_u16 = TypeInfo(name="uint16", kind=TypeKind.base, bit_size=16, signed=False)
        t_i32 = TypeInfo(name="int32", kind=TypeKind.base, bit_size=32, signed=True)
        t_u32 = TypeInfo(name="uint32", kind=TypeKind.base, bit_size=32, signed=False)

        assert parse_and_validate_value("-32768", t_i16) == -32768
        assert parse_and_validate_value("32767", t_i16) == 32767
        assert parse_and_validate_value("0x7FFF", t_i16) == 32767
        assert parse_and_validate_value("0b1111", t_u16) == 15
        with pytest.raises(ValueError):
            parse_and_validate_value("-32769", t_i16)
        with pytest.raises(ValueError):
            parse_and_validate_value("32768", t_i16)
        with pytest.raises(ValueError):
            parse_and_validate_value("-1", t_u16)
        assert parse_and_validate_value("65535", t_u16) == 65535
        with pytest.raises(ValueError):
            parse_and_validate_value("65536", t_u16)

        assert parse_and_validate_value("-2147483648", t_i32) == -2147483648
        assert parse_and_validate_value("4294967295", t_u32) == 4294967295
        with pytest.raises(ValueError):
            parse_and_validate_value("4294967296", t_u32)

    def test_parse_enum_name_or_value(self) -> None:
        t_enum = TypeInfo(
            name="status_t",
            kind=TypeKind.enum,
            bit_size=16,
            enum_values={"IDLE": 0, "RUN": 1},
        )
        assert parse_and_validate_value("RUN", t_enum) == 1
        assert parse_and_validate_value("0", t_enum) == 0
        with pytest.raises(ValueError):
            parse_and_validate_value("BAD", t_enum)

    def test_parse_float(self) -> None:
        t_f = TypeInfo(name="float32", kind=TypeKind.base, bit_size=32, float_type=True)
        v = parse_and_validate_value("3.14", t_f)
        assert abs(float(v) - 3.14) < 1e-6
        with pytest.raises(ValueError):
            parse_and_validate_value("not_a_float", t_f)


class TestCoalesceReadRanges:
    def test_coalesce_adjacent_and_nearby(self) -> None:
        # adjacent/nearby within gap
        blocks = coalesce_read_ranges([(0x100, 2), (0x102, 2), (0x110, 1)], max_gap=8, max_block=128)
        # 0x100-0x103 and 0x110 within gap 12? 0x104 to 0x110 is gap 12 > 8 so separate
        assert any(start == 0x100 and length >= 4 for start, length in blocks)
        assert any(start == 0x110 for start, length in blocks)

        blocks2 = coalesce_read_ranges([(0x100, 2), (0x103, 2)], max_gap=8, max_block=128)
        assert blocks2 == [(0x100, 5)] or (len(blocks2) == 1 and blocks2[0][0] == 0x100)

    def test_respects_max_block(self) -> None:
        blocks = coalesce_read_ranges([(0, 50), (60, 50), (120, 50)], max_gap=20, max_block=80)
        # should not merge into blocks larger than max_block
        assert all(length <= 80 for _, length in blocks)
        assert len(blocks) >= 2

    def test_empty_and_zero(self) -> None:
        assert coalesce_read_ranges([]) == []
        assert coalesce_read_ranges([(0, 0), (1, 0)]) == []
