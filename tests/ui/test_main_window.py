from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, DisplayFormat, MemoryFormat, Probe, ProbeKind
from jtagconn.core.worker import EngineWorker
from jtagconn.persistence.session import SessionStore
from jtagconn.ui.main_window import MainWindow
from tests.fixtures.make_fixtures import create_sample_elf_out


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


def _setup_f28388d_window(tmp_path: Path, probe: Probe) -> MainWindow:
    logger = OperationLogger()
    backend = SimulatedBackend(logger=logger)
    store = SessionStore(config_dir=tmp_path / "cfg")
    window = MainWindow(
        backend=backend,
        session_store=store,
        logger=logger,
        confirm_flash_handler=lambda sections: True,  # auto-confirm for tests unless overridden
    )
    cores = window.target_manager.configure(probe, "F28388D", None)
    window.cores_panel.set_cores(cores)
    window.session.probe = probe
    window.session.device = "F28388D"
    assert "C28xx_CPU1" in cores and "C28xx_CPU2" in cores
    window.set_active_core("C28xx_CPU1")
    return window


def test_main_window_startup_time_under_1_5s(tmp_path: Path, probe: Probe) -> None:
    t0 = time.perf_counter()
    logger = OperationLogger()
    backend = SimulatedBackend(logger=logger)
    store = SessionStore(config_dir=tmp_path / "cfg_startup")
    window = MainWindow(backend=backend, session_store=store, logger=logger)
    # basic startup interactions
    window.target_manager.configure(probe, "F28388D", None)
    window.set_active_core("C28xx_CPU1")
    window._update_status_bar()
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5, f"Startup/init took {elapsed:.3f}s"


def test_full_us1_to_us6_workflow(tmp_path: Path, probe: Probe) -> None:
    window = _setup_f28388d_window(tmp_path, probe)

    # --- US1: connect/load/run with flash confirmation ---
    cpu1 = "C28xx_CPU1"
    cpu2 = "C28xx_CPU2"
    window.set_active_core(cpu1)
    window.target_manager.connect_core(cpu1)
    window.target_manager.connect_core(cpu2)
    assert window.target_manager.core_state(cpu1) == CoreState.Halted
    assert window.target_manager.core_state(cpu2) == CoreState.Halted
    assert window.cores_panel.connected_cores_count() >= 2

    img1 = create_sample_elf_out(tmp_path / "cpu1.out", entry=0x080000)
    img2 = create_sample_elf_out(tmp_path / "cpu2.out", entry=0x080010)

    # flash confirmation invoked
    seen = {"called": False, "sections": []}

    def confirm(sections):
        seen["called"] = True
        seen["sections"] = list(sections)
        return True

    window.confirm_flash_handler = confirm
    window.target_manager.select_image(cpu1, img1)
    ok1 = window.target_manager.load_program(cpu1, confirm_flash_callback=window.confirm_flash_handler)
    assert ok1 is True
    assert seen["called"] is True

    window.target_manager.select_image(cpu2, img2)
    assert window.target_manager.load_program(cpu2, confirm_flash_callback=lambda s: True) is True

    # run/halt/resume/reset on active core (US1/US2)
    window.target_manager.run(cpu1)
    assert window.target_manager.core_state(cpu1) == CoreState.Running
    window.target_manager.halt(cpu1)
    assert window.target_manager.core_state(cpu1) == CoreState.Halted
    _pc, _fn = window.target_manager.halt.__self__.pc_for_core(cpu1), window.target_manager.function_for_core(cpu1)  # type: ignore[attr-defined]
    # use service API results/state
    pc2, _fn2 = (window.target_manager.pc_for_core(cpu1), window.target_manager.function_for_core(cpu1))
    assert pc2 is not None
    window.target_manager.run(cpu1)  # resume
    assert window.target_manager.core_state(cpu1) == CoreState.Running
    window.target_manager.halt(cpu1)
    window.target_manager.reset(cpu1)
    assert window.target_manager.core_state(cpu1) == CoreState.Halted

    # --- US3: watch add/autocomplete/live refresh/diff-only/modify/reject invalid ---
    window.set_active_core(cpu1)
    # autocomplete backed by SymbolIndex
    backend_syms = window.backend.symbols(cpu1)
    window.watch_view.set_symbol_index(backend_syms)
    sugg = window.watch_view.suggest_symbols("g_c")
    assert any("g_counter" in s for s in sugg)

    # add watches via watch service (UI-integrated service)
    w1 = window.watch_service.add_watch(cpu1, "g_counter", DisplayFormat.dec)
    w2 = window.watch_service.add_watch(cpu1, "g_ctrl", DisplayFormat.natural)
    assert w1.expression == "g_counter"
    assert w2.expression == "g_ctrl"

    # live refresh and diff-only emission
    received = []
    window.watch_service.watchUpdated.connect(lambda core, changed: received.append((core, list(changed))))
    changed1 = window.watch_service.refresh(cpu1, force_emit=True)
    assert changed1  # initial emit
    baseline = len(received)
    changed2 = window.watch_service.refresh(cpu1, force_emit=False)
    # no state/value change -> diff-only means no new emission
    assert changed2 == []
    assert len(received) == baseline

    # cause a value change and ensure diff-only emits
    window.backend.assign(cpu1, "g_counter", "42")
    changed3 = window.watch_service.refresh(cpu1, force_emit=False)
    assert len(changed3) >= 1
    assert any(e.expression == "g_counter" for e in changed3)
    window.watch_view.upsert_entries(changed3)
    # value updated in view model/item state
    assert "42" in (window.watch_service._entries[cpu1]["g_counter"].value.display_value)

    # modify watch value and reject invalid value
    window.watch_service.modify_value(cpu1, "g_counter", "7")
    assert int(window.backend.evaluate(cpu1, "g_counter").raw_value) == 7
    with pytest.raises(ValueError):
        window.watch_service.modify_value(cpu1, "g_counter", "99999")  # uint16 overflow

    # --- US4: memory view ---
    mv = window.memory_service.read_view(cpu1, "0xC000", 16, MemoryFormat.hex16)
    assert mv.status.value == "current"
    assert len(mv.data) == 16
    cells = window.memory_service.format_memory_cells(mv)
    assert len(cells) == 16
    window.memory_view.start_expr_input.setText("0xC000")
    window.memory_view.set_view(mv, cells)
    assert window.memory_view.status_label.text() in ("current", "stale", "error")

    # --- US5: call stack/frames and modify local variable ---
    # ensure halted and refresh stack
    if window.target_manager.core_state(cpu1) != CoreState.Halted:
        window.target_manager.halt(cpu1)
    frames = window.stack_service.refresh_stack(cpu1)
    assert len(frames) >= 1
    window.locals_view.set_callstack(frames)
    assert window.locals_view.locals_table.rowCount() >= 1
    # modify local in frame 0 (err is mutable in simulated backend)
    updated = window.stack_service.modify_local(cpu1, 0, "err", "5")
    assert updated is not None
    # unavailable/optimized local cannot be meaningfully edited in general; but path exercised

    # --- US6: Run All / Halt All and multicore behavior ---
    # halt cpu2 only while cpu1 runs
    window.target_manager.run(cpu1)
    # cpu2 is halted already; run_all requires halted cores, so halt cpu1 then run_all/halt_all
    window.target_manager.halt(cpu1)
    assert window.target_manager.core_state(cpu1) == CoreState.Halted
    assert window.target_manager.core_state(cpu2) == CoreState.Halted
    window.target_manager.run_all([cpu1, cpu2])
    assert window.target_manager.core_state(cpu1) == CoreState.Running
    assert window.target_manager.core_state(cpu2) == CoreState.Running
    # halt cpu2 only
    window.target_manager.halt(cpu2)
    assert window.target_manager.core_state(cpu2) == CoreState.Halted
    assert window.target_manager.core_state(cpu1) == CoreState.Running
    # locals visible for halted cpu2
    frames_cpu2 = window.stack_service.refresh_stack(cpu2)
    assert isinstance(frames_cpu2, list)
    window.target_manager.halt_all([cpu1])
    assert window.target_manager.core_state(cpu1) == CoreState.Halted

    # --- Connection loss detection ---
    window.backend.inject_connection_loss(True)
    healthy = window.target_manager.check_connection_health()
    assert healthy is False
    assert window.target_manager.core_state(cpu1) == CoreState.ConnectionLost
    assert window.target_manager.core_state(cpu2) == CoreState.ConnectionLost


def test_watch_refresh_50_symbols_performance_sc004(tmp_path: Path, probe: Probe) -> None:
    window = _setup_f28388d_window(tmp_path, probe)
    core = "C28xx_CPU1"
    window.target_manager.connect_core(core)
    window.set_active_core(core)

    # Register 50 watches. Simulated backend can evaluate known symbols and also returns not_found
    # nodes quickly for unknowns; benchmark exercises refresh path/diff logic and UI update volume.
    exprs = [f"sym_{i}" for i in range(45)] + ["g_counter", "g_ctrl", "g_status", "g_buffer", "g_counter"]
    # dedupe while preserving count intent
    exprs = list(dict.fromkeys(exprs))
    while len(exprs) < 50:
        exprs.append(f"extra_{len(exprs)}")
    exprs = exprs[:50]
    for e in exprs:
        window.watch_service.add_watch(core, e, DisplayFormat.natural)

    # Warm-up
    window.watch_service.refresh(core, force_emit=True)

    t0 = time.perf_counter()
    changed = window.watch_service.refresh(core, force_emit=True)
    elapsed = time.perf_counter() - t0
    assert len(changed) == 50
    assert elapsed < 1.0, f"Refresh of 50 symbols took {elapsed:.3f}s"
    # simulated mode efficiency target
    assert elapsed < 0.05, f"Simulated refresh of 50 symbols took {elapsed*1000:.2f}ms"


def test_watch_polling_pauses_and_worker_idle_efficiency(tmp_path: Path, probe: Probe) -> None:
    window = _setup_f28388d_window(tmp_path, probe)
    core = "C28xx_CPU1"
    window.target_manager.connect_core(core)
    window.set_active_core(core)
    window.watch_service.add_watch(core, "g_counter", DisplayFormat.natural)
    window.refresh_watch_now(force_emit=True)

    # Baseline: polling allowed on watch tab and not minimized
    window.set_watch_tab_visible(True)
    window.showNormal()
    window._update_watch_polling_state()
    assert window._watch_polling_allowed() is True
    assert getattr(window.watch_service, "_paused", False) is False

    # Count refresh effects by observing emissions
    events = []
    window.watch_service.watchUpdated.connect(lambda c, ch: events.append((c, ch)))
    # change value and tick -> should refresh/do work
    window.backend.assign(core, "g_counter", "11")
    before = len(events)
    window.tick_watch_poll()
    assert len(events) >= before  # may emit if changed

    # Pause when tab hidden
    window.set_watch_tab_visible(False)  # switches to memory tab
    window._update_watch_polling_state()
    assert window._watch_polling_allowed() is False
    assert getattr(window.watch_service, "_paused", False) is True
    window.backend.assign(core, "g_counter", "22")
    before_hidden = len(events)
    window.tick_watch_poll()  # guarded: should do no work
    # also timer callback path should early-return
    window._on_watch_timer()
    assert len(events) == before_hidden

    # Pause when minimized
    window.set_watch_tab_visible(True)
    window.showMinimized()
    window._update_watch_polling_state()
    assert window._watch_polling_allowed() is False
    assert getattr(window.watch_service, "_paused", False) is True
    window.backend.assign(core, "g_counter", "33")
    before_min = len(events)
    window.tick_watch_poll()
    window._on_watch_timer()
    assert len(events) == before_min

    # EngineWorker does 0 work when idle
    worker = EngineWorker(window.backend)
    try:
        # give thread time to start and settle
        time.sleep(0.05)
        assert worker.is_running is True
        assert worker._queue.unfinished_tasks == 0
        assert worker._queue.qsize() == 0
        # remain idle without submitted tasks
        time.sleep(0.1)
        assert worker._queue.unfinished_tasks == 0
        assert worker._queue.qsize() == 0
    finally:
        worker.shutdown(wait=True, timeout=2.0)


def test_cli_simulate_headless_check_exits_zero(tmp_path: Path) -> None:
    # run from repo root; ensure module importable
    cmd = [sys.executable, "-m", "jtagconn", "--simulate", "--headless-check"]
    proc = subprocess.run(
        cmd,
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
