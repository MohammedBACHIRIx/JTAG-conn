from __future__ import annotations

import pytest

from jtagconn.backend.base import JtagError
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, Probe, ProbeKind, ValueStatus
from jtagconn.core.stack_service import StackService
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
    ss = StackService(backend, tm)
    return tm, ss, core


class TestUS5StackLocals:
    def test_stack_retrieval_and_locals_when_halted(self, env) -> None:
        tm, ss, core = env
        # ensure halted
        assert tm.core_state(core) == CoreState.Halted
        frames = ss.refresh_stack(core)
        assert len(frames) >= 2
        assert frames[0].function == "control_loop"
        assert frames[1].function == "main"

        locals_f0 = ss.get_frame_locals(core, 0)
        names = {v.name for v in locals_f0}
        assert "err" in names and "pwm_duty" in names

    def test_frame_selection_locals(self, env) -> None:
        _tm, ss, core = env
        l1 = ss.get_frame_locals(core, 1)
        names = {v.name for v in l1}
        assert "status" in names

    def test_local_edit_and_validation(self, env) -> None:
        _tm, ss, core = env
        # edit err (int16)
        updated = ss.modify_local(core, 0, "err", "-123")
        assert updated.name == "err"
        assert updated.raw_value in (-123, "-123") or "-123" in str(updated.display_value)

        # verify persisted
        locals_after = {v.name: v for v in ss.get_frame_locals(core, 0)}
        assert locals_after["err"].raw_value in (-123, "-123") or "-123" in str(locals_after["err"].display_value)

        # invalid for int16
        with pytest.raises(ValueError):
            ss.modify_local(core, 0, "err", "40000")

    def test_resume_clears_stack_and_marks_locals_unavailable(self, env) -> None:
        tm, ss, core = env
        tm.run(core)
        assert tm.core_state(core) == CoreState.Running
        frames = ss.refresh_stack(core)
        assert frames == []
        # locals unavailable when running
        locs = ss.get_frame_locals(core, 0)
        # may be empty or marked unavailable depending on impl; spec says cleared/marks unavailable
        for v in locs:
            assert v.status == ValueStatus.unavailable

    def test_cannot_modify_local_while_running(self, env) -> None:
        tm, ss, core = env
        tm.run(core)
        with pytest.raises(JtagError):
            ss.modify_local(core, 0, "err", "1")
