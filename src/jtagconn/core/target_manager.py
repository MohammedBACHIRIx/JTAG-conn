from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

try:
    from PySide6.QtCore import QObject, Signal
except Exception:  # noqa: BLE001
    class QObject:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _SignalDescriptor:
        def __init__(self) -> None:
            self._name = ""

        def __set_name__(self, owner: type, name: str) -> None:
            self._name = name

        def __get__(self, obj: Any, objtype: type | None = None) -> Any:
            if obj is None:
                return _SignalInstance(None, self._name)
            signals = obj.__dict__.setdefault("_signals", {})
            inst = signals.get(self._name)
            if inst is None:
                inst = _SignalInstance(obj, self._name)
                signals[self._name] = inst
            return inst

    class _SignalInstance:
        def __init__(self, obj: Any, name: str) -> None:
            self._obj = obj
            self._name = name
            self._slots: list[Callable[..., Any]] = []

        def connect(self, slot: Callable[..., Any]) -> None:
            if self._obj is None:
                return
            self._obj.__dict__.setdefault("_slots", {}).setdefault(self._name, []).append(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            if self._obj is None:
                return
            for slot in self._obj.__dict__.get("_slots", {}).get(self._name, []):
                try:
                    slot(*args, **kwargs)
                except Exception:  # noqa: BLE001, S110
                    pass

    class Signal:  # type: ignore[no-redef]
        def __init__(self, *args: Any) -> None:
            self._desc = _SignalDescriptor()

        def __set_name__(self, owner: type, name: str) -> None:
            self._desc.__set_name__(owner, name)

        def __get__(self, obj: Any, objtype: type | None = None) -> Any:
            return self._desc.__get__(obj, objtype)

from jtagconn.backend.base import DebugBackend, JtagError
from jtagconn.backend.ccxml.generator import generate_ccxml
from jtagconn.core.devices import get_device_profile
from jtagconn.core.flash_guard import FlashGuard
from jtagconn.core.logging_service import OperationLogger, format_user_error
from jtagconn.core.models import CoreState, DeviceProfile, Probe, ProgramImage, Section
from jtagconn.symbols.image import load_program_image, resolve_pc_to_function


class TargetManager(QObject):
    """Manages probe configuration, core states, per-core images, and debug control."""

    coreStateChanged = Signal(str, object)  # (core, CoreState)
    coreHaltedInfo = Signal(str, int, object)  # (core, pc, function_name)
    imageLoaded = Signal(str, object)  # (core, ProgramImage)
    loadProgress = Signal(str, int)  # (core, percent)
    loadFinished = Signal(str, bool, str)  # (core, success, message)
    errorOccurred = Signal(str, str)  # (operation, user_message)
    connectionLost = Signal()

    def __init__(self, backend: DebugBackend, logger: OperationLogger | None = None) -> None:
        super().__init__()
        self.backend = backend
        self.logger = logger or getattr(backend, "logger", None) or OperationLogger()
        self.flash_guard = FlashGuard()

        self._probe: Probe | None = None
        self._device_id: str | None = None
        self._device_profile: DeviceProfile | None = None
        self._ccxml_path: Path | None = None
        self._cores: list[str] = []
        self._core_states: dict[str, CoreState] = {}
        self._images: dict[str, ProgramImage] = {}
        self._pcs: dict[str, int | None] = {}
        self._functions: dict[str, str | None] = {}

    # --- accessors ---
    def cores(self) -> list[str]:
        return list(self._cores)

    def device_profile(self) -> DeviceProfile | None:
        return self._device_profile

    def core_state(self, core: str) -> CoreState:
        return self._core_states.get(core, CoreState.Disconnected)

    def image_for_core(self, core: str) -> ProgramImage | None:
        return self._images.get(core)

    def pc_for_core(self, core: str) -> int | None:
        return self._pcs.get(core)

    def function_for_core(self, core: str) -> str | None:
        return self._functions.get(core)

    # --- probe/config ---
    def list_probes(self) -> list[Probe]:
        try:
            return self.backend.list_probes()
        except Exception as exc:  # noqa: BLE001
            self._emit_error("list_probes", exc)
            return []

    def configure(self, probe: Probe, device_id: str, ccxml: Path | None = None) -> list[str]:
        try:
            self._device_profile = get_device_profile(device_id)
        except Exception as exc:
            raise JtagError(f"Unknown device: {device_id}") from exc

        ccxml_path = ccxml
        if ccxml_path is None:
            # generate ccxml when needed (best-effort default location)
            tmp_dir = Path(tempfile.gettempdir()) / "jtagconn"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            ccxml_path = tmp_dir / f"{device_id}_{probe.kind.value}.ccxml"
            try:
                generate_ccxml(probe, device_id, ccxml_path)
            except Exception:  # noqa: BLE001, S110
                # backend may still configure without ccxml in simulated mode
                pass

        try:
            cores = self.backend.configure(probe, device_id, ccxml_path)
        except Exception as exc:
            self._emit_error("configure", exc)
            raise

        self._probe = probe
        self._device_id = device_id
        self._ccxml_path = ccxml_path
        self._cores = list(cores)
        self._core_states = {c: CoreState.Disconnected for c in self._cores}
        self._images = {}
        self._pcs = {c: None for c in self._cores}
        self._functions = {c: None for c in self._cores}
        self.logger.log("info", "configure", f"Configured device {device_id} cores={cores}")
        return list(cores)

    # --- connection/control ---
    def connect_core(self, core: str) -> None:
        self._ensure_known_core(core)
        try:
            self.backend.connect(core)
            self._set_core_state(core, CoreState.Halted)
            # sync halted info
            try:
                pc = self.backend.halt(core)
                self._update_halted_info(core, pc)
            except Exception:  # noqa: BLE001, S110
                pass
            self.logger.log("info", "connect", f"Connected core {core}", core=core)
        except Exception as exc:
            self._emit_error("connect", exc, core=core)
            raise

    def disconnect_core(self, core: str) -> None:
        self._ensure_known_core(core)
        try:
            self.backend.disconnect(core)
        except Exception as exc:  # noqa: BLE001
            self._emit_error("disconnect", exc, core=core)
        self._pcs[core] = None
        self._functions[core] = None
        self._set_core_state(core, CoreState.Disconnected)
        self.logger.log("info", "disconnect", f"Disconnected core {core}", core=core)

    def disconnect_all(self) -> None:
        for core in list(self._cores):
            try:
                self.disconnect_core(core)
            except Exception:  # noqa: BLE001, S110
                pass

    def select_image(self, core: str, path: Path) -> ProgramImage:
        self._ensure_known_core(core)
        try:
            image = load_program_image(Path(path), device_id=self._device_id)
        except Exception as exc:
            self._emit_error("select_image", exc, core=core)
            raise
        self._images[core] = image
        self.logger.log("info", "select_image", f"Selected image {path} for {core}", core=core)
        self.imageLoaded.emit(core, image)
        return image

    def load_program(
        self,
        core: str,
        confirm_flash_callback: Callable[[list[Section]], bool] | None = None,
        cancel_event: Event | None = None,
    ) -> bool:
        self._ensure_known_core(core)
        image = self._images.get(core)
        if image is None:
            exc = JtagError(f"No image selected for core {core}")
            self.loadFinished.emit(core, False, format_user_error(exc))
            self._emit_error("load_program", exc, core=core)
            raise exc

        # Flash confirmation (FR-006): refuse without touching target if not confirmed
        flash_sections: list[Section] = []
        if self._device_profile is not None:
            flash_sections = self.flash_guard.requires_confirmation(image, self._device_profile)
        if flash_sections and (
            confirm_flash_callback is None or not confirm_flash_callback(flash_sections)
        ):
                msg = "Load cancelled: flash programming was not confirmed"
                self.logger.log("warning", "load_program", msg, core=core)
                self.loadFinished.emit(core, False, msg)
                return False

        cancel = cancel_event or Event()

        def _progress(p: int) -> None:
            try:
                self.loadProgress.emit(core, int(p))
            except Exception:  # noqa: BLE001, S110
                pass

        try:
            self.backend.load_program(core, Path(image.path), _progress, cancel)
            if cancel.is_set():
                msg = "Load cancelled"
                self.loadFinished.emit(core, False, msg)
                return False
            # set PC to image entry point (per spec)
            if getattr(image, "entry_point", 0):
                self._pcs[core] = int(image.entry_point)
                self._functions[core] = resolve_pc_to_function(image, int(image.entry_point))
            self.loadFinished.emit(core, True, "Program loaded successfully")
            self.logger.log("info", "load_program", f"Loaded program on {core}", core=core)
            return True
        except Exception as exc:
            msg = format_user_error(exc) if isinstance(exc, Exception) else str(exc)
            self.loadFinished.emit(core, False, msg)
            self._emit_error("load_program", exc, core=core)
            raise

    def run(self, core: str) -> None:
        self._require_state(core, {CoreState.Halted}, "run")
        try:
            self.backend.run(core)
            self._set_core_state(core, CoreState.Running)
            self.logger.log("info", "run", f"Running core {core}", core=core)
        except Exception as exc:
            self._emit_error("run", exc, core=core)
            raise

    def resume(self, core: str) -> None:
        self.run(core)

    def halt(self, core: str) -> tuple[int, str | None]:
        self._require_state(core, {CoreState.Running}, "halt")
        try:
            pc = int(self.backend.halt(core))
            self._set_core_state(core, CoreState.Halted)
            fn = self._update_halted_info(core, pc)
            self.logger.log("info", "halt", f"Halted core {core} at 0x{pc:X}", core=core)
            return pc, fn
        except Exception as exc:
            self._emit_error("halt", exc, core=core)
            raise

    def reset(self, core: str) -> int:
        self._require_state(core, {CoreState.Halted}, "reset")
        try:
            self.backend.reset(core)
            self._set_core_state(core, CoreState.Halted)
            # try to read pc from backend state/halt context; fallback to entry or 0
            pc = None
            try:
                # reset leaves halted; backend.halt would be invalid, so use state/pc tracking if backend exposes via evaluate? not specified
                # prefer image entry point as reset vector approximation
                img = self._images.get(core)
                if img is not None:
                    pc = int(img.entry_point)
            except Exception:  # noqa: BLE001
                pc = None
            if pc is None:
                pc = int(self._pcs.get(core) or 0)
            self._update_halted_info(core, pc)
            self.logger.log("info", "reset", f"Reset core {core}", core=core)
            return pc
        except Exception as exc:
            self._emit_error("reset", exc, core=core)
            raise

    def run_all(self, cores: list[str] | None = None) -> None:
        target = list(cores) if cores is not None else list(self._cores)
        # validate states before issuing
        for core in target:
            self._require_state(core, {CoreState.Halted}, "run")
        try:
            self.backend.run_all(target)
        except Exception as exc:
            self._emit_error("run_all", exc)
            raise
        for core in target:
            self._set_core_state(core, CoreState.Running)

    def halt_all(self, cores: list[str] | None = None) -> dict[str, tuple[int, str | None]]:
        target = list(cores) if cores is not None else [
            c for c in self._cores if self.core_state(c) == CoreState.Running
        ]
        result: dict[str, tuple[int, str | None]] = {}
        try:
            self.backend.halt_all(target)
        except Exception as exc:
            self._emit_error("halt_all", exc)
            raise
        for core in target:
            self._set_core_state(core, CoreState.Halted)
            # best-effort PC retrieval: if backend supports halt returning pc only per-core,
            # try calling halt again is invalid; so query via internal state not available.
            # Use tracked pc or 0 and resolve function.
            pc = int(self._pcs.get(core) or 0)
            try:
                # some implementations may update pc; attempt a lightweight ping-like state sync not available.
                # fallback: keep previous/unknown
                pass
            except Exception:  # noqa: BLE001, S110
                pass
            fn = self._update_halted_info(core, pc)
            result[core] = (pc, fn)
        return result

    def check_connection_health(self) -> bool:
        try:
            ok = bool(self.backend.ping())
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            for core in list(self._cores):
                st = self._core_states.get(core, CoreState.Disconnected)
                if st in (CoreState.Running, CoreState.Halted):
                    self._set_core_state(core, CoreState.ConnectionLost)
            self.logger.log("error", "health_check", "Connection to target lost")
            self.connectionLost.emit()
        return ok

    # --- helpers ---
    def _ensure_known_core(self, core: str) -> None:
        if core not in self._core_states and self._cores and core not in self._cores:
            raise JtagError(f"Unknown core: {core}")
        if core not in self._core_states:
            # allow lazy registration
            self._core_states[core] = CoreState.Disconnected
            self._pcs[core] = None
            self._functions[core] = None

    def _set_core_state(self, core: str, state: CoreState) -> None:
        self._core_states[core] = state
        self.coreStateChanged.emit(core, state)

    def _require_state(self, core: str, allowed: set[CoreState], action: str) -> None:
        self._ensure_known_core(core)
        st = self.core_state(core)
        if st not in allowed:
            allowed_s = ", ".join(s.value for s in allowed)
            raise JtagError(
                f"Cannot {action} core {core} in state {st.value}; requires one of: {allowed_s}"
            )

    def _update_halted_info(self, core: str, pc: int) -> str | None:
        self._pcs[core] = int(pc)
        fn = resolve_pc_to_function(self._images.get(core), int(pc))
        self._functions[core] = fn
        self.coreHaltedInfo.emit(core, int(pc), fn)
        return fn

    def _emit_error(self, operation: str, exc: Exception, core: str | None = None) -> None:
        msg = format_user_error(exc) if isinstance(exc, Exception) else str(exc)
        try:
            self.logger.log("error", operation, msg, core=core)
        except Exception:  # noqa: BLE001, S110
            pass
        self.errorOccurred.emit(operation, msg)
