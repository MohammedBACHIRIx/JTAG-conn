from __future__ import annotations

from pathlib import Path
from threading import Event

import pytest

from jtagconn.backend.base import CoreNotAvailable
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, DisplayFormat, Probe, ProbeKind
from jtagconn.core.target_manager import TargetManager
from jtagconn.core.watch_service import WatchService
from tests.fixtures.make_fixtures import create_sample_elf_out


@pytest.fixture
def backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


class TestUS6MultiCore:
    def test_boot_dependency_error_and_independent_connect_load_watch(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D")
        assert "C28xx_CPU1" in cores and "C28xx_CPU2" in cores

        # boot dependency: CPU2 requires CPU1 connected first
        with pytest.raises(CoreNotAvailable):
            tm.connect_core("C28xx_CPU2")

        # connect masters/slaves independently in valid order
        tm.connect_core("C28xx_CPU1")
        tm.connect_core("C28xx_CPU2")
        assert tm.core_state("C28xx_CPU1") == CoreState.Halted
        assert tm.core_state("C28xx_CPU2") == CoreState.Halted

        # load independent images per core
        img1 = create_sample_elf_out(tmp_path / "cpu1.out", entry=0x080000)
        img2 = create_sample_elf_out(tmp_path / "cpu2.out", entry=0x080100)
        tm.select_image("C28xx_CPU1", img1)
        tm.select_image("C28xx_CPU2", img2)
        assert tm.load_program("C28xx_CPU1", confirm_flash_callback=lambda s: True, cancel_event=Event())
        assert tm.load_program("C28xx_CPU2", confirm_flash_callback=lambda s: True, cancel_event=Event())

        # independent watch per core
        ws = WatchService(backend, tm)
        ws.add_watch("C28xx_CPU1", "g_counter", DisplayFormat.dec)
        ws.add_watch("C28xx_CPU2", "g_counter", DisplayFormat.dec)
        backend.assign("C28xx_CPU1", "g_counter", "11")
        backend.assign("C28xx_CPU2", "g_counter", "22")
        ws.refresh("C28xx_CPU1", force_emit=True)
        ws.refresh("C28xx_CPU2", force_emit=True)
        v1 = ws.entries("C28xx_CPU1")[0].value
        v2 = ws.entries("C28xx_CPU2")[0].value
        assert v1 is not None and v2 is not None
        assert str(v1.raw_value) in ("11",) or "11" in str(v1.display_value)
        assert str(v2.raw_value) in ("22",) or "22" in str(v2.display_value)

    def test_run_all_halt_all_and_independent_halt(self, backend: SimulatedBackend, probe: Probe) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D")
        # connect in dependency-safe order
        for c in cores:
            tm.connect_core(c)
        assert all(tm.core_state(c) == CoreState.Halted for c in cores)

        # run all
        tm.run_all(cores)
        assert all(tm.core_state(c) == CoreState.Running for c in cores)

        # halt only CPU2, CPU1 remains running
        pc2, _fn2 = tm.halt("C28xx_CPU2")
        assert tm.core_state("C28xx_CPU2") == CoreState.Halted
        assert tm.core_state("C28xx_CPU1") == CoreState.Running
        assert isinstance(pc2, int)

        # halt all remaining running cores
        result = tm.halt_all()
        assert "C28xx_CPU1" in result or tm.core_state("C28xx_CPU1") == CoreState.Halted
        assert tm.core_state("C28xx_CPU1") == CoreState.Halted
        # CPU2 already halted; calling halt_all default targets running cores only in our impl
        assert tm.core_state("C28xx_CPU2") == CoreState.Halted
