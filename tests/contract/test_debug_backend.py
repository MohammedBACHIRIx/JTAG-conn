from __future__ import annotations

import threading
import time
from pathlib import Path
from threading import Event

import pytest

from jtagconn.backend.base import (
    ConnectionLost,
    CoreNotAvailable,
    DeviceSecured,
    EngineMissing,
    InvalidImage,
    MemoryAccessError,
    ProbeBusy,
    ProbeNotFound,
    TargetNotResponding,
    VerifyError,
)
from jtagconn.backend.ccs_scripting import CcsScriptingBackend
from jtagconn.backend.ccxml.generator import generate_ccxml
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.devices import DEVICE_CATALOG
from jtagconn.core.models import CoreState, Probe, ProbeKind, ValueStatus
from jtagconn.core.worker import EngineWorker
from tests.fixtures.make_fixtures import create_sample_elf_out


def configured_backend(sim_backend: SimulatedBackend, default_probe: Probe, device: str = "F28388D"):
    cores = sim_backend.configure(default_probe, device, None)
    return sim_backend, cores


class TestDebugBackendContract:
    def test_list_probes(self, sim_backend: SimulatedBackend) -> None:
        probes = sim_backend.list_probes()
        assert len(probes) >= 1
        assert probes[0].kind == ProbeKind.XDS110

    @pytest.mark.parametrize("device_id", list(DEVICE_CATALOG.keys()))
    def test_configure_returns_device_cores(
        self, sim_backend: SimulatedBackend, default_probe: Probe, device_id: str
    ) -> None:
        cores = sim_backend.configure(default_probe, device_id, None)
        expected = [c.name for c in DEVICE_CATALOG[device_id].cores]
        assert cores == expected

    def test_connect_disconnect_state_and_run_halt_reset(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        assert sim_backend.state(core) == CoreState.Disconnected
        sim_backend.connect(core)
        assert sim_backend.state(core) == CoreState.Halted
        sim_backend.run(core)
        assert sim_backend.state(core) == CoreState.Running
        pc = sim_backend.halt(core)
        assert isinstance(pc, int)
        assert sim_backend.state(core) == CoreState.Halted
        sim_backend.reset(core)
        assert sim_backend.state(core) == CoreState.Halted
        sim_backend.disconnect(core)
        assert sim_backend.state(core) == CoreState.Disconnected

    def test_run_all_halt_all(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        # connect masters/slaves respecting boot deps: CPU1 then CPU2/CLA/CM for F28388D
        for core in cores:
            sim_backend.connect(core)
        sim_backend.run_all(cores)
        assert all(sim_backend.state(c) == CoreState.Running for c in cores)
        sim_backend.halt_all(cores)
        assert all(sim_backend.state(c) == CoreState.Halted for c in cores)

    def test_load_program_and_progress(
        self, sim_backend: SimulatedBackend, default_probe: Probe, tmp_path: Path
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)
        img = create_sample_elf_out(tmp_path / "sample.out")
        progress: list[int] = []
        sim_backend.load_program(core, img, progress.append, Event())
        assert progress[0] == 0
        assert 100 in progress

    def test_load_program_cancel(
        self, sim_backend: SimulatedBackend, default_probe: Probe, tmp_path: Path
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)
        img = create_sample_elf_out(tmp_path / "sample.out")
        cancel = Event()
        cancel.set()
        progress: list[int] = []
        sim_backend.load_program(core, img, progress.append, cancel)
        # cancelled early; implementation may report initial progress or none
        assert 100 not in progress or progress == []

    def test_memory_read_write(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)
        sim_backend.write_memory(core, 0xC100, [1, 2, 3, 4], 16)
        data = sim_backend.read_memory(core, 0xC100, 4, 16)
        assert data == [1, 2, 3, 4]

    def test_multi_core_memory_isolation(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        assert len(cores) >= 2
        for core in cores[:2]:
            sim_backend.connect(core)
        c1, c2 = cores[0], cores[1]
        sim_backend.write_memory(c1, 0xD000, [0xAAAA], 16)
        sim_backend.write_memory(c2, 0xD000, [0x5555], 16)
        assert sim_backend.read_memory(c1, 0xD000, 1, 16) == [0xAAAA]
        assert sim_backend.read_memory(c2, 0xD000, 1, 16) == [0x5555]

    def test_evaluate_and_assign_symbols(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)

        node = sim_backend.evaluate(core, "g_counter")
        assert node.name == "g_counter"
        assert node.status == ValueStatus.current

        sim_backend.assign(core, "g_counter", "42")
        node2 = sim_backend.evaluate(core, "g_counter")
        assert node2.raw_value == 42

        # struct member
        gain = sim_backend.evaluate(core, "g_ctrl.gain")
        assert gain.status == ValueStatus.current
        sim_backend.assign(core, "g_ctrl.gain", "77")
        assert sim_backend.evaluate(core, "g_ctrl.gain").raw_value == 77

        # array element
        sim_backend.assign(core, "g_buffer[2]", "9")
        assert sim_backend.evaluate(core, "g_buffer[2]").raw_value == 9

        # not found
        missing = sim_backend.evaluate(core, "no_such_symbol")
        assert missing.status == ValueStatus.not_found

    def test_callstack_and_locals(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)
        sim_backend.halt(core)
        stack = sim_backend.callstack(core)
        assert len(stack) >= 2
        assert stack[0].function == "control_loop"
        assert stack[1].function == "main"
        local_names = [v.name for v in stack[0].locals]
        assert "err" in local_names
        assert "pwm_duty" in local_names
        opt = next(v for v in stack[0].locals if v.name == "optimized_var")
        assert opt.status == ValueStatus.unavailable

    def test_symbols_and_supports_realtime_and_ping(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend, cores = configured_backend(sim_backend, default_probe)
        core = cores[0]
        sim_backend.connect(core)
        syms = sim_backend.symbols(core)
        names = {s.name for s in syms}
        assert {"g_counter", "g_ctrl", "g_status", "g_buffer"}.issubset(names)
        assert sim_backend.supports_realtime(core) is True
        assert sim_backend.ping() is True


class TestFaultInjection:
    def test_probe_not_found(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.inject_probe_not_found(True)
        assert sim_backend.list_probes() == []
        sim_backend.configure(default_probe, "F28388D", None)
        with pytest.raises(ProbeNotFound):
            sim_backend.connect("C28xx_CPU1")

    def test_target_not_responding(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.inject_target_not_responding(True)
        with pytest.raises(TargetNotResponding):
            sim_backend.configure(default_probe, "F28388D", None)

    def test_probe_busy(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.inject_probe_busy(True)
        with pytest.raises(ProbeBusy):
            sim_backend.configure(default_probe, "F28388D", None)

    def test_device_secured(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.inject_secured_device(True)
        with pytest.raises(DeviceSecured):
            sim_backend.configure(default_probe, "F28388D", None)

    def test_core_not_available_without_boot_master(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        with pytest.raises(CoreNotAvailable):
            sim_backend.connect("C28xx_CPU2")  # boot master C28xx_CPU1 not connected

    def test_auto_release_slaves_allows_connect(
        self, logger, default_probe: Probe
    ) -> None:
        backend = SimulatedBackend(logger=logger, auto_release_slaves=True)
        backend.configure(default_probe, "F28388D", None)
        backend.connect("C28xx_CPU2")
        assert backend.state("C28xx_CPU2") == CoreState.Halted

    def test_verify_error(
        self, sim_backend: SimulatedBackend, default_probe: Probe, tmp_path: Path
    ) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        sim_backend.connect("C28xx_CPU1")
        sim_backend.inject_verify_error(0x080010)
        img = create_sample_elf_out(tmp_path / "v.out")
        with pytest.raises(VerifyError) as ei:
            sim_backend.load_program("C28xx_CPU1", img, lambda _: None, Event())
        assert ei.value.address == 0x080010

    def test_memory_access_error(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        sim_backend.connect("C28xx_CPU1")
        sim_backend.set_inaccessible_range(0xF000, 0xFFFF)
        with pytest.raises(MemoryAccessError):
            sim_backend.read_memory("C28xx_CPU1", 0xF010, 4, 16)
        with pytest.raises(MemoryAccessError):
            sim_backend.write_memory("C28xx_CPU1", 0xF010, [1, 2], 16)

    def test_connection_lost(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        sim_backend.connect("C28xx_CPU1")
        sim_backend.inject_connection_loss(True)
        assert sim_backend.ping() is False
        with pytest.raises(ConnectionLost):
            sim_backend.read_memory("C28xx_CPU1", 0xC000, 1, 16)
        with pytest.raises(ConnectionLost):
            sim_backend.state("C28xx_CPU1")

    def test_invalid_image_path(
        self, sim_backend: SimulatedBackend, default_probe: Probe, tmp_path: Path
    ) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        sim_backend.connect("C28xx_CPU1")
        with pytest.raises(InvalidImage):
            sim_backend.load_program(
                "C28xx_CPU1", tmp_path / "missing.out", lambda _: None, Event()
            )


class TestCcxmlGeneration:
    def test_generate_ccxml_creates_valid_xml(self, tmp_path: Path) -> None:
        probe = Probe(kind=ProbeKind.XDS110, serial="ABC123", description="XDS110")
        out = tmp_path / "target.ccxml"
        result = generate_ccxml(probe, "F28388D", out)
        assert result == out
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "TIXDS110_Connection" in content
        assert "configurations" in content
        assert "ABC123" in content

    @pytest.mark.parametrize("kind", list(ProbeKind))
    def test_generate_ccxml_for_all_probe_kinds(self, tmp_path: Path, kind: ProbeKind) -> None:
        probe = Probe(kind=kind, serial=None, description=str(kind.value))
        out = tmp_path / f"{kind.value}.ccxml"
        generate_ccxml(probe, "F28069M", out)
        assert out.exists()


class TestCcsScriptingBackend:
    def test_engine_missing_without_ccs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CCS_ROOT", raising=False)
        # force discovery to fail by making Path.exists return False? easier: patch candidates
        import jtagconn.backend.ccs_scripting as mod

        monkeypatch.setattr(mod, "_discover_ccs_root", lambda: None)
        backend = CcsScriptingBackend()
        with pytest.raises(EngineMissing):
            backend.list_probes()


class TestEngineWorker:
    def test_async_execution_and_callbacks(self, sim_backend: SimulatedBackend, default_probe: Probe) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        worker = EngineWorker(sim_backend)
        try:
            done = threading.Event()
            results: list[object] = []

            def on_done(res: object) -> None:
                results.append(res)
                done.set()

            fut = worker.submit_backend_call("connect", "C28xx_CPU1", callback=on_done)
            fut.result(timeout=5)
            assert done.wait(timeout=5)
            assert sim_backend.state("C28xx_CPU1") == CoreState.Halted
        finally:
            worker.shutdown(wait=True, timeout=5)

    def test_future_exception_propagation(
        self, sim_backend: SimulatedBackend, default_probe: Probe
    ) -> None:
        sim_backend.configure(default_probe, "F28388D", None)
        worker = EngineWorker(sim_backend)
        try:
            # connect slave without master -> CoreNotAvailable
            fut = worker.submit_backend_call("connect", "C28xx_CPU2")
            with pytest.raises(CoreNotAvailable):
                fut.result(timeout=5)
        finally:
            worker.shutdown(wait=True, timeout=5)

    def test_zero_busy_wait_idle(self, sim_backend: SimulatedBackend) -> None:
        worker = EngineWorker(sim_backend)
        try:
            # Give thread time to block on queue.get()
            time.sleep(0.05)
            assert worker.is_running
            # Internal queue should be empty while idle and thread should be waiting on blocking get
            q = worker._queue  # type: ignore[attr-defined]
            assert q.empty()
            # Submit a task to prove it's responsive after idle period
            fut = worker.submit(lambda: 123)
            assert fut.result(timeout=2) == 123
            time.sleep(0.02)
            assert q.empty()
        finally:
            worker.shutdown(wait=True, timeout=5)

    def test_shutdown(self, sim_backend: SimulatedBackend) -> None:
        worker = EngineWorker(sim_backend)
        worker.shutdown(wait=True, timeout=5)
        assert not worker._thread.is_alive()  # type: ignore[attr-defined]
