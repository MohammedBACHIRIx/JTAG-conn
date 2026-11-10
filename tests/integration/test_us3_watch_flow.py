from __future__ import annotations

import pytest

from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import DisplayFormat, Probe, ProbeKind, ValueStatus
from jtagconn.core.target_manager import TargetManager
from jtagconn.core.watch_service import WatchService


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
    ws = WatchService(backend, tm)
    return tm, ws, core


class TestUS3WatchFlow:
    def test_live_watch_polling_and_diff_only_updates(self, env) -> None:
        tm, ws, core = env
        # add watch; initial refresh emits
        emitted: list[list] = []
        ws.watchUpdated.connect(lambda c, changed: emitted.append(changed) if c == core else None)
        ws.add_watch(core, "g_counter", DisplayFormat.dec)
        assert emitted, "initial add should emit"
        emitted.clear()

        # no change -> no emission
        ws.refresh(core)
        assert emitted == []

        # change value via backend -> next refresh should emit
        backend = tm.backend
        backend.assign(core, "g_counter", "5")
        ws.refresh(core)
        assert emitted, "changed value should emit diff update"
        entry = ws.entries(core)[0]
        assert entry.expression == "g_counter"
        assert entry.value is not None
        assert str(entry.value.display_value) in ("5", "0x0005") or entry.value.raw_value == 5

    def test_stale_fallback_when_not_realtime_or_disconnected(self, backend: SimulatedBackend, probe: Probe) -> None:
        tm = TargetManager(backend)
        core = tm.configure(probe, "F28388D")[0]
        tm.connect_core(core)
        ws = WatchService(backend, tm)
        ws.add_watch(core, "g_counter")

        # running but no realtime -> stale
        tm.run(core)
        # SimulatedBackend supports_realtime True; monkeypatch to force stale path
        orig = backend.supports_realtime

        def no_rt(c: str) -> bool:
            return False

        backend.supports_realtime = no_rt  # type: ignore[assignment]
        ws.refresh(core, force_emit=True)
        e = ws.entries(core)[0]
        assert e.status == ValueStatus.stale
        backend.supports_realtime = orig  # type: ignore[assignment]

        # disconnected/connection lost -> stale
        backend.inject_connection_loss(True)
        tm.check_connection_health()
        ws.refresh(core, force_emit=True)
        e2 = ws.entries(core)[0]
        assert e2.status == ValueStatus.stale

    def test_validated_symbol_writes_and_reject_invalid(self, env) -> None:
        _, ws, core = env
        ws.add_watch(core, "g_counter")
        # valid write (uint16) and read-back verification
        entry = ws.modify_value(core, "g_counter", "123")
        assert entry.value is not None
        assert entry.value.raw_value in (123, "123") or str(entry.value.display_value).endswith("123") or "123" in str(entry.value.display_value)

        # invalid: out of range for uint16 must raise ValueError and not touch target
        with pytest.raises(ValueError):
            ws.modify_value(core, "g_counter", "70000")
        # value should remain unchanged (123)
        node = ws.entries(core)[0].value
        assert node is not None
        assert node.raw_value in (123, "123") or "123" in str(node.display_value)

        # invalid format
        with pytest.raises(ValueError):
            ws.modify_value(core, "g_counter", "not_a_number")
        node2 = ws.entries(core)[0].value
        assert node2 is not None
        assert node2.raw_value in (123, "123") or "123" in str(node2.display_value)
