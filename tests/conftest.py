from __future__ import annotations

import pytest

from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import Probe, ProbeKind


@pytest.fixture
def logger() -> OperationLogger:
    return OperationLogger()


@pytest.fixture
def sim_backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def default_probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")
