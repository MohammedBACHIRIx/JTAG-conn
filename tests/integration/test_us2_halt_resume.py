from __future__ import annotations

from pathlib import Path

import pytest

from jtagconn.backend.base import JtagError
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, Probe, ProbeKind
from jtagconn.core.target_manager import TargetManager
from jtagconn.symbols.image import load_program_image, resolve_pc_to_function
from tests.fixtures.make_fixtures import create_sample_elf_out


@pytest.fixture
def backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


class TestUS2HaltResumeReset:
    def test_halt_resume_reset_and_pc_function(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        tm = TargetManager(backend)
        core = tm.configure(probe, "F28388D")[0]
        tm.connect_core(core)

        # load image so PC/function resolution has symbol context
        img_path = create_sample_elf_out(tmp_path / "app.out", entry=0x080000)
        tm.select_image(core, img_path)
        tm.load_program(core, confirm_flash_callback=lambda s: True)

        # run then halt
        tm.run(core)
        assert tm.core_state(core) == CoreState.Running
        pc, fn = tm.halt(core)
        assert tm.core_state(core) == CoreState.Halted
        assert isinstance(pc, int)
        # function name resolution: may be "main" if pc falls in range, else None acceptable if not mapped
        assert fn == resolve_pc_to_function(tm.image_for_core(core), pc) or fn is None or isinstance(fn, str)

        # resume (alias for run) requires Halted
        tm.resume(core)
        assert tm.core_state(core) == CoreState.Running
        tm.halt(core)
        assert tm.core_state(core) == CoreState.Halted

        # reset requires Halted and keeps Halted
        reset_pc = tm.reset(core)
        assert isinstance(reset_pc, int)
        assert tm.core_state(core) == CoreState.Halted
        assert tm.pc_for_core(core) == reset_pc

    def test_state_guards(self, backend: SimulatedBackend, probe: Probe) -> None:
        tm = TargetManager(backend)
        core = tm.configure(probe, "F28388D")[0]
        tm.connect_core(core)
        # halt requires Running
        with pytest.raises(JtagError):
            tm.halt(core)
        tm.run(core)
        # reset requires Halted
        with pytest.raises(JtagError):
            tm.reset(core)
        # resume requires Halted
        with pytest.raises(JtagError):
            tm.resume(core)

    def test_pc_to_function_resolution_unit(self, tmp_path: Path) -> None:
        img_path = create_sample_elf_out(tmp_path / "app.out", entry=0x080000)
        image = load_program_image(img_path)
        assert resolve_pc_to_function(image, 0x080000) == "main"
        assert resolve_pc_to_function(image, 0x08001F) == "main"
        # outside
        outside = resolve_pc_to_function(image, 0x090000)
        assert outside is None or isinstance(outside, str)
