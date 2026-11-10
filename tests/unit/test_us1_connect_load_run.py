from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event

import pytest

from jtagconn.backend.base import InvalidImage, JtagError
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.devices import get_device_profile
from jtagconn.core.flash_guard import FlashGuard
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import CoreState, MemoryRegionKind, Probe, ProbeKind, Section
from jtagconn.core.target_manager import TargetManager
from jtagconn.symbols.image import is_image_out_of_date, load_program_image, resolve_pc_to_function
from tests.fixtures.make_fixtures import create_sample_elf_out


@pytest.fixture
def backend(logger: OperationLogger) -> SimulatedBackend:
    return SimulatedBackend(logger=logger)


@pytest.fixture
def probe() -> Probe:
    return Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")


class TestProgramImageLoader:
    def test_load_valid_elf(self, tmp_path: Path) -> None:
        img_path = create_sample_elf_out(tmp_path / "sample.out", entry=0x080000)
        image = load_program_image(img_path, device_id="F28388D")
        assert image.path == str(img_path)
        assert image.format.name in ("ELF", "COFF")
        assert image.entry_point == 0x080000
        assert len(image.sections) >= 1
        names = {s.name for s in image.symbols}
        assert "main" in names or "g_counter" in names

    def test_invalid_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidImage):
            load_program_image(tmp_path / "missing.out", device_id="F28388D")

    def test_invalid_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.out"
        p.write_bytes(b"")
        with pytest.raises(InvalidImage):
            load_program_image(p, device_id="F28388D")

    def test_invalid_not_elf_or_coff(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.bin"
        p.write_bytes(b"NOT_AN_IMAGE_FORMAT\x00\x01\x02")
        with pytest.raises(InvalidImage):
            load_program_image(p, device_id="F28388D")

    def test_is_image_out_of_date(self, tmp_path: Path) -> None:
        img_path = create_sample_elf_out(tmp_path / "sample.out")
        image = load_program_image(img_path)
        assert is_image_out_of_date(image) is False
        time.sleep(0.01)
        # modify file to change mtime
        os.utime(img_path, (time.time() + 5, time.time() + 5))
        assert is_image_out_of_date(image) is True

    def test_resolve_pc_to_function(self, tmp_path: Path) -> None:
        img_path = create_sample_elf_out(tmp_path / "sample.out", entry=0x080000)
        image = load_program_image(img_path)
        # main symbol created at entry with size 0x20 in fixture
        assert resolve_pc_to_function(image, 0x080000) == "main"
        assert resolve_pc_to_function(image, 0x080010) == "main"
        assert resolve_pc_to_function(None, 0x080000) is None


class TestFlashGuard:
    def test_requires_confirmation_for_flash_sections(self, tmp_path: Path) -> None:
        dev = get_device_profile("F28388D")
        # create image with section in flash range
        img_path = create_sample_elf_out(tmp_path / "flash.out", entry=0x080000)
        image = load_program_image(img_path, device_id="F28388D")
        guard = FlashGuard()
        flagged = guard.requires_confirmation(image, dev)
        # .text at 0x080000 is in F28388D flash range
        assert isinstance(flagged, list)
        assert any(s.address == 0x080000 or s.region == MemoryRegionKind.FLASH for s in flagged)

    def test_no_confirmation_for_ram_only(self) -> None:
        from jtagconn.core.models import ImageFormat, ProgramImage

        dev = get_device_profile("F28388D")
        ram_img = ProgramImage(
            path="ram.out",
            mtime=0.0,
            format=ImageFormat.ELF,
            entry_point=0xC000,
            sections=[Section(name=".data", address=0x00C000, size=16, region=MemoryRegionKind.RAM)],
            has_debug_info=False,
        )
        guard = FlashGuard()
        assert guard.requires_confirmation(ram_img, dev) == []


class TestTargetManagerStateMachine:
    def test_connect_load_run_state_transitions(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D", None)
        core = cores[0]
        assert tm.core_state(core) == CoreState.Disconnected

        tm.connect_core(core)
        assert tm.core_state(core) == CoreState.Halted

        img_path = create_sample_elf_out(tmp_path / "sample.out")
        tm.select_image(core, img_path)
        assert tm.image_for_core(core) is not None

        progress: list[int] = []
        tm.loadProgress.connect(lambda c, p: progress.append(p) if c == core else None)

        # flash confirmation required for flash image; accept
        ok = tm.load_program(core, confirm_flash_callback=lambda secs: True, cancel_event=Event())
        assert ok is True
        assert 100 in progress

        tm.run(core)
        assert tm.core_state(core) == CoreState.Running

        pc, _fn = tm.halt(core)
        assert isinstance(pc, int)
        assert tm.core_state(core) == CoreState.Halted

        reset_pc = tm.reset(core)
        assert isinstance(reset_pc, int)
        assert tm.core_state(core) == CoreState.Halted

    def test_invalid_state_transitions_raise(self, backend: SimulatedBackend, probe: Probe) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D", None)
        core = cores[0]
        tm.connect_core(core)
        # halted: cannot halt again
        with pytest.raises(JtagError):
            tm.halt(core)
        tm.run(core)
        # running: cannot run/reset
        with pytest.raises(JtagError):
            tm.run(core)
        with pytest.raises(JtagError):
            tm.reset(core)
        tm.halt(core)
        # halted: cannot halt
        with pytest.raises(JtagError):
            tm.halt(core)

    def test_flash_confirmation_refusal_does_not_load(self, backend: SimulatedBackend, probe: Probe, tmp_path: Path) -> None:
        tm = TargetManager(backend)
        cores = tm.configure(probe, "F28388D", None)
        core = cores[0]
        tm.connect_core(core)
        img_path = create_sample_elf_out(tmp_path / "flash.out")
        tm.select_image(core, img_path)
        # refuse confirmation
        ok = tm.load_program(core, confirm_flash_callback=lambda secs: len(secs) == 0, cancel_event=Event())
        # if there are flash sections, callback returns False -> should refuse
        # ensure no crash and load not marked successful
        assert ok is False
