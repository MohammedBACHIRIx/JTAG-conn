from __future__ import annotations

from pathlib import Path
from threading import Event

import pytest

from jtagconn.backend.base import ConnectionLost
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, Probe, ProbeKind
from jtagconn.core.target_manager import TargetManager
from tests.fixtures.make_fixtures import create_sample_elf_out


@pytest.fixture
def backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


class TestUS1Flow:
    def test_connect_flash_confirm_load_progress_run(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D")
        assert "C28xx_CPU1" in cores
        core = "C28xx_CPU1"

        # connect
        tm.connect_core(core)
        assert tm.core_state(core) == CoreState.Halted

        # select/load with flash confirmation and progress
        img_path = create_sample_elf_out(tmp_path / "app.out", entry=0x080000)
        image = tm.select_image(core, img_path)
        assert image.path == str(img_path)

        progress: list[int] = []
        finished: list[tuple[bool, str]] = []
        tm.loadProgress.connect(lambda c, p: progress.append(p) if c == core else None)
        tm.loadFinished.connect(lambda c, ok, msg: finished.append((ok, msg)) if c == core else None)

        ok = tm.load_program(core, confirm_flash_callback=lambda secs: True, cancel_event=Event())
        assert ok is True
        assert progress and progress[0] == 0
        assert 100 in progress
        assert finished and finished[-1][0] is True

        # run
        tm.run(core)
        assert tm.core_state(core) == CoreState.Running

    def test_connection_error_handling_and_health(self, backend: SimulatedBackend, probe: Probe) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D")
        core = cores[0]
        tm.connect_core(core)
        tm.run(core)
        assert tm.core_state(core) == CoreState.Running

        # simulate connection loss and detect via watchdog health check
        backend.inject_connection_loss(True)
        lost_events: list[bool] = []
        tm.connectionLost.connect(lambda: lost_events.append(True))
        ok = tm.check_connection_health()
        assert ok is False
        assert tm.core_state(core) == CoreState.ConnectionLost
        assert lost_events, "connectionLost signal should be emitted"

        # operations should now reflect lost connection
        with pytest.raises(ConnectionLost):
            backend.read_memory(core, 0xC000, 1, 16)

    def test_load_verify_failure_surfaces(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        from jtagconn.backend.base import VerifyError

        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D")
        core = cores[0]
        tm.connect_core(core)
        img_path = create_sample_elf_out(tmp_path / "app.out")
        tm.select_image(core, img_path)
        backend.inject_verify_error(0x080010)
        with pytest.raises(VerifyError):
            tm.load_program(core, confirm_flash_callback=lambda s: True, cancel_event=Event())
