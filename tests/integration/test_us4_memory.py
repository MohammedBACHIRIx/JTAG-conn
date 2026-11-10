from __future__ import annotations

import pytest

from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.memory_service import MemoryService
from jtagconn.core.models import CoreState, MemoryFormat, Probe, ProbeKind, ValueStatus
from jtagconn.core.target_manager import TargetManager


@pytest.fixture
def backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


@pytest.fixture
def env(backend: SimulatedBackend, probe: Probe):
    tm = TargetManager(backend)
    core = tm.configure(probe, "F28388D")[0]
    tm.connect_core(core)
    ms = MemoryService(backend, tm)
    return backend, tm, ms, core


class TestUS4Memory:
    def test_address_and_symbol_resolution_and_read(self, env) -> None:
        backend, _tm, ms, core = env
        # seed memory
        backend.write_memory(core, 0xC100, [0x1234, 0xABCD, 0x0001], 16)
        view = ms.read_view(core, "0xC100", 3, MemoryFormat.hex16)
        assert view.status == ValueStatus.current
        assert view.start_address == 0xC100
        assert view.data[:3] == [0x1234, 0xABCD, 0x0001]

        # symbol resolution (g_counter is at 0xC000 in SimulatedBackend)
        backend.write_memory(core, 0xC000, [0x0042], 16)
        v2 = ms.read_view(core, "g_counter", 1, MemoryFormat.uint16)
        assert v2.start_address == 0xC000
        assert v2.data == [0x0042]

    def test_formatting_hex32_int_uint_float(self, env) -> None:
        backend, _tm, ms, core = env
        backend.write_memory(core, 0xD000, [0x0000FFFF, 0xFFFFFFFF], 16)
        v16 = ms.read_view(core, "0xD000", 2, MemoryFormat.hex16)
        cells = ms.format_memory_cells(v16)
        assert cells[0].lower().startswith("0x") and "ffff" in cells[0].lower()

        backend.write_memory(core, 0xD010, [0x12345678], 32)
        v32 = ms.read_view(core, "0xD010", 1, MemoryFormat.hex32)
        assert ms.format_memory_cells(v32)[0].lower() == "0x12345678"

        backend.write_memory(core, 0xD020, [0xFFFF], 16)
        vs = ms.read_view(core, "0xD020", 1, MemoryFormat.int16)
        assert ms.format_memory_cells(vs)[0] == "-1"
        vu = ms.read_view(core, "0xD020", 1, MemoryFormat.uint16)
        assert ms.format_memory_cells(vu)[0] == "65535"

    def test_inaccessible_range_returns_error_without_disconnect(self, env) -> None:
        backend, tm, ms, core = env
        backend.set_inaccessible_range(0xF000, 0xFFFF)
        view = ms.read_view(core, "0xF010", 4, MemoryFormat.hex16)
        assert view.status == ValueStatus.error
        # core should remain connected/halted (not disconnected)
        assert tm.core_state(core) == CoreState.Halted
        # accessible reads still work
        backend.write_memory(core, 0xC200, [7], 16)
        ok_view = ms.read_view(core, "0xC200", 1, MemoryFormat.uint16)
        assert ok_view.status == ValueStatus.current
        assert ok_view.data == [7]
