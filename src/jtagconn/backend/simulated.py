from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from jtagconn.backend.base import (
    ConnectionLost,
    CoreNotAvailable,
    DebugBackend,
    DeviceSecured,
    InvalidImage,
    JtagError,
    MemoryAccessError,
    ProbeBusy,
    ProbeNotFound,
    TargetNotResponding,
    VerifyError,
)
from jtagconn.core.devices import DEVICE_CATALOG, get_device_profile
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import (
    CoreArch,
    CoreState,
    Probe,
    ProbeKind,
    StackFrame,
    Symbol,
    SymbolScope,
    TypeInfo,
    TypeKind,
    ValueNode,
    ValueStatus,
)


def _base_type(name: str, bit_size: int, signed: bool = False, float_type: bool = False) -> TypeInfo:
    return TypeInfo(
        name=name,
        kind=TypeKind.base,
        bit_size=bit_size,
        signed=signed,
        float_type=float_type,
    )


class SimulatedBackend(DebugBackend):
    """In-memory simulated backend for tests and --simulate demo mode."""

    def __init__(
        self,
        logger: OperationLogger | None = None,
        auto_release_slaves: bool = False,
    ) -> None:
        self.logger = logger or OperationLogger()
        self.auto_release_slaves = auto_release_slaves

        self._probes: list[Probe] = [
            Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")
        ]
        self._configured: tuple[Probe, str, Path | None] | None = None
        self._core_states: dict[str, CoreState] = {}
        self._core_arch: dict[str, CoreArch] = {}
        self._core_boot_master: dict[str, str | None] = {}
        self._pc: dict[str, int] = {}
        self._memory: dict[str, dict[int, int]] = {}
        self._symbols: dict[str, dict[str, Symbol]] = {}
        self._values: dict[str, dict[str, object]] = {}
        self._loaded_images: dict[str, Path] = {}

        # Fault injection state
        self._inject_probe_not_found = False
        self._inject_target_not_responding = False
        self._inject_probe_busy = False
        self._inject_secured_device = False
        self._inject_connection_lost = False
        self._verify_error_addr: int | None = None
        self._inaccessible_range: tuple[int, int] | None = None

    # --- fault injection hooks ---
    def inject_connection_loss(self, enabled: bool = True) -> None:
        self._inject_connection_lost = enabled
        if enabled:
            for core in list(self._core_states.keys()):
                if self._core_states[core] in (CoreState.Running, CoreState.Halted):
                    self._core_states[core] = CoreState.ConnectionLost

    def inject_secured_device(self, enabled: bool = True) -> None:
        self._inject_secured_device = enabled

    def inject_probe_busy(self, enabled: bool = True) -> None:
        self._inject_probe_busy = enabled

    def inject_probe_not_found(self, enabled: bool = True) -> None:
        self._inject_probe_not_found = enabled

    def inject_target_not_responding(self, enabled: bool = True) -> None:
        self._inject_target_not_responding = enabled

    def inject_verify_error(self, addr: int | None) -> None:
        self._verify_error_addr = addr

    def set_inaccessible_range(self, start: int | None, end: int | None) -> None:
        self._inaccessible_range = (start, end) if start is not None and end is not None else None

    # --- helpers ---
    def _log(self, operation: str, message: str, core: str | None = None, level: str = "info") -> None:
        self.logger.log(level, operation, message, core=core)

    def _check_connection(self, core: str | None = None) -> None:
        if self._inject_connection_lost:
            raise ConnectionLost("Simulated connection loss")
        if core is not None:
            st = self._core_states.get(core, CoreState.Disconnected)
            if st == CoreState.ConnectionLost:
                raise ConnectionLost(f"Core {core} lost connection")

    def _ensure_core(self, core: str) -> None:
        if core not in self._core_states:
            raise JtagError(f"Unknown core: {core}")

    def _ensure_configured(self) -> None:
        if self._configured is None:
            raise JtagError("Backend not configured")

    def _mask(self, width_bits: int) -> int:
        return (1 << width_bits) - 1 if width_bits < 64 else (1 << 64) - 1

    def _init_default_symbols(self, core: str) -> None:
        uint16 = _base_type("uint16", 16, signed=False)
        _base_type("int16", 16, signed=True)
        _base_type("uint32", 32, signed=False)
        ctrl_type = TypeInfo(
            name="ctrl_t",
            kind=TypeKind.struct,
            bit_size=32,
            fields={
                "gain": (0, uint16),
                "enable": (16, uint16),
            },
        )
        status_type = TypeInfo(
            name="status_t",
            kind=TypeKind.enum,
            bit_size=16,
            enum_values={"IDLE": 0, "RUN": 1, "FAULT": 2},
        )
        buffer_type = TypeInfo(
            name="uint16[4]",
            kind=TypeKind.array,
            bit_size=64,
            element_type=uint16,
            length=4,
        )
        symbols = {
            "g_counter": Symbol(
                name="g_counter",
                address=0xC000,
                size=1,
                type_info=uint16,
                scope=SymbolScope.global_,
            ),
            "g_ctrl": Symbol(
                name="g_ctrl",
                address=0xC010,
                size=2,
                type_info=ctrl_type,
                scope=SymbolScope.global_,
            ),
            "g_status": Symbol(
                name="g_status",
                address=0xC020,
                size=1,
                type_info=status_type,
                scope=SymbolScope.global_,
            ),
            "g_buffer": Symbol(
                name="g_buffer",
                address=0xC030,
                size=4,
                type_info=buffer_type,
                scope=SymbolScope.global_,
            ),
        }
        self._symbols[core] = symbols
        prev_locals = None
        if core in self._values:
            prev_locals = self._values[core].get("__frame_locals__")
        self._values[core] = {
            "g_counter": 0,
            "g_ctrl.gain": 100,
            "g_ctrl.enable": 1,
            "g_status": 0,
            "g_buffer": [0, 0, 0, 0],
        }
        if prev_locals is not None:
            self._values[core]["__frame_locals__"] = prev_locals
        self._init_frame_locals(core)

    # --- DebugBackend implementation ---
    def list_probes(self) -> list[Probe]:
        self._log("list_probes", "Listing probes")
        if self._inject_probe_not_found:
            return []
        return list(self._probes)

    def configure(self, probe: Probe, device: str, ccxml: Path | None) -> list[str]:
        self._log("configure", f"Configuring probe={probe.kind.value} device={device}")
        if self._inject_probe_busy:
            raise ProbeBusy("Simulated probe busy")
        if self._inject_secured_device:
            raise DeviceSecured("Simulated secured device")
        if self._inject_target_not_responding:
            raise TargetNotResponding("Simulated target not responding")
        if device not in DEVICE_CATALOG:
            raise JtagError(f"Unsupported device: {device}")
        profile = get_device_profile(device)
        self._configured = (probe, device, ccxml)
        self._core_states.clear()
        self._core_arch.clear()
        self._core_boot_master.clear()
        self._pc.clear()
        self._memory.clear()
        self._symbols.clear()
        self._values.clear()
        self._loaded_images.clear()
        core_names: list[str] = []
        for core in profile.cores:
            core_names.append(core.name)
            self._core_states[core.name] = CoreState.Disconnected
            self._core_arch[core.name] = core.arch
            self._core_boot_master[core.name] = core.boot_master
            self._pc[core.name] = 0
            self._memory[core.name] = {}
            self._init_default_symbols(core.name)
        self._log("configure", f"Configured cores: {core_names}")
        return core_names

    def connect(self, core: str) -> None:
        self._ensure_configured()
        self._ensure_core(core)
        self._log("connect", f"Connecting core {core}", core=core)
        if self._inject_probe_not_found:
            raise ProbeNotFound("No simulated probe")
        if self._inject_target_not_responding:
            raise TargetNotResponding("Target not responding")
        if self._inject_secured_device:
            raise DeviceSecured("Device secured")
        if self._inject_probe_busy:
            raise ProbeBusy("Probe busy")
        boot_master = self._core_boot_master.get(core)
        if boot_master and not self.auto_release_slaves:
            master_state = self._core_states.get(boot_master, CoreState.Disconnected)
            if master_state == CoreState.Disconnected:
                raise CoreNotAvailable(
                    f"Core '{core}' requires boot master '{boot_master}' to be connected first"
                )
        self._core_states[core] = CoreState.Halted
        self._init_frame_locals(core)
        if self._pc.get(core, 0) == 0:
            self._pc[core] = 0x080000

    def disconnect(self, core: str) -> None:
        self._ensure_configured()
        self._ensure_core(core)
        self._core_states[core] = CoreState.Disconnected
        self._log("disconnect", f"Disconnected core {core}", core=core)

    def load_program(
        self, core: str, image: Path, progress: Callable[[int], None], cancel: Event
    ) -> None:
        self._ensure_configured()
        self._ensure_core(core)
        self._check_connection(core)
        self._log("load_program", f"Loading {image} on {core}", core=core)
        if not image.exists():
            raise InvalidImage(f"Image not found: {image}")
        if image.suffix.lower() not in (".out", ".elf", ""):
            raise InvalidImage(f"Unsupported image type: {image.suffix}")
        for i in (0, 25, 50, 75, 100):
            if cancel.is_set():
                self._log("load_program", f"Load cancelled for {core}", core=core)
                return
            progress(i)
            time.sleep(0.001)
        if self._verify_error_addr is not None:
            raise VerifyError(self._verify_error_addr)
        self._loaded_images[core] = image

    def run(self, core: str) -> None:
        self._ensure_core(core)
        self._check_connection(core)
        self._core_states[core] = CoreState.Running
        self._log("run", f"Run core {core}", core=core)

    def halt(self, core: str) -> int:
        self._ensure_core(core)
        self._check_connection(core)
        self._core_states[core] = CoreState.Halted
        pc = int(self._pc.get(core, 0))
        self._log("halt", f"Halted core {core} at 0x{pc:X}", core=core)
        return pc

    def reset(self, core: str) -> None:
        self._ensure_core(core)
        self._check_connection(core)
        self._core_states[core] = CoreState.Halted
        self._pc[core] = 0x080000
        self._log("reset", f"Reset core {core}", core=core)

    def run_all(self, cores: list[str]) -> None:
        for core in cores:
            self.run(core)
        self._log("run_all", f"Run cores {cores}")

    def halt_all(self, cores: list[str]) -> None:
        for core in cores:
            self.halt(core)
        self._log("halt_all", f"Halted cores {cores}")

    def state(self, core: str) -> CoreState:
        self._check_connection(core)
        return self._core_states.get(core, CoreState.Disconnected)

    def read_memory(self, core: str, address: int, count: int, width_bits: int) -> list[int]:
        self._ensure_core(core)
        self._check_connection(core)
        if self._inaccessible_range is not None:
            start, end = self._inaccessible_range
            # count is in native address units; check overlap conservatively
            if not (address + count - 1 < start or address > end):
                raise MemoryAccessError((max(address, start), min(address + count - 1, end)))
        mem = self._memory[core]
        mask = self._mask(width_bits)
        values = [int(mem.get(address + i, 0)) & mask for i in range(count)]
        self._log("read_memory", f"Read {count}x{width_bits} @ 0x{address:X}", core=core)
        return values

    def write_memory(self, core: str, address: int, values: list[int], width_bits: int) -> None:
        self._ensure_core(core)
        self._check_connection(core)
        if self._inaccessible_range is not None:
            start, end = self._inaccessible_range
            if not (address + len(values) - 1 < start or address > end):
                raise MemoryAccessError((max(address, start), min(address + len(values) - 1, end)))
        mem = self._memory[core]
        mask = self._mask(width_bits)
        for i, val in enumerate(values):
            mem[address + i] = int(val) & mask
        self._log(
            "write_memory",
            f"Wrote {len(values)}x{width_bits} @ 0x{address:X}",
            core=core,
        )

    def supports_realtime(self, core: str) -> bool:
        self._ensure_core(core)
        return True

    def _eval_symbol_value(self, core: str, expression: str) -> tuple[object | None, str, str, ValueStatus]:
        vals = self._values.get(core, {})
        syms = self._symbols.get(core, {})
        expr = expression.strip()
        # direct (symbol/global values)
        if expr in vals and expr != "__frame_locals__":
            v = vals[expr]
            sym = syms.get(expr)
            tname = sym.type_info.name if sym else "unknown"
            return v, tname, str(v), ValueStatus.current
        # struct member: g_ctrl.gain
        if "." in expr:
            base, member = expr.split(".", 1)
            key = f"{base}.{member}"
            if key in vals:
                v = vals[key]
                tname = "uint16"
                if base in syms:
                    field = syms[base].type_info.fields.get(member)
                    if field:
                        tname = field[1].name
                return v, tname, str(v), ValueStatus.current
        # array element: g_buffer[3]
        m = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+)\]", expr)
        if m:
            name, idx_s = m.group(1), int(m.group(2))
            if name in vals and isinstance(vals[name], list):
                arr = vals[name]  # type: ignore[assignment]
                if 0 <= idx_s < len(arr):
                    v = arr[idx_s]
                    elem = syms[name].type_info.element_type if name in syms else None
                    tname = elem.name if elem else "uint16"
                    return v, tname, str(v), ValueStatus.current
                return None, "unknown", "index out of range", ValueStatus.error
        # frame locals (recognize by name; prefer current frame 0 state)
        self._init_frame_locals(core)
        fl_all = vals.get("__frame_locals__", {})
        for fr in sorted(fl_all.keys()):
            info = fl_all[fr].get(expr)
            if info is not None:
                v = info.get("value")
                tname = str(info.get("type", "unknown"))
                status = info.get("status", ValueStatus.current)
                disp = info.get("display", str(v) if v is not None else "")
                return v, tname, str(disp), status
        return None, "unknown", "not found", ValueStatus.not_found

    def evaluate(self, core: str, expression: str, frame: int | None = None) -> ValueNode:
        self._ensure_core(core)
        self._check_connection(core)
        self._log("evaluate", f"Evaluating '{expression}'", core=core)
        raw, tname, disp, status = self._eval_symbol_value(core, expression)
        children: list[ValueNode] = []
        # expand structs/arrays for direct symbol names
        vals = self._values.get(core, {})
        syms = self._symbols.get(core, {})
        if expression in syms and status == ValueStatus.current:
            sym = syms[expression]
            if sym.type_info.kind == TypeKind.struct:
                for member in sym.type_info.fields:
                    child_expr = f"{expression}.{member}"
                    c_raw, c_t, c_disp, c_st = self._eval_symbol_value(core, child_expr)
                    children.append(
                        ValueNode(
                            name=member,
                            expression=child_expr,
                            type_name=c_t,
                            raw_value=c_raw if isinstance(c_raw, (int, float, str)) else None,
                            display_value=c_disp,
                            status=c_st,
                        )
                    )
            elif sym.type_info.kind == TypeKind.array and isinstance(vals.get(expression), list):
                arr = vals[expression]  # type: ignore[assignment]
                for i, _ in enumerate(arr):
                    child_expr = f"{expression}[{i}]"
                    c_raw, c_t, c_disp, c_st = self._eval_symbol_value(core, child_expr)
                    children.append(
                        ValueNode(
                            name=f"[{i}]",
                            expression=child_expr,
                            type_name=c_t,
                            raw_value=c_raw if isinstance(c_raw, (int, float, str)) else None,
                            display_value=c_disp,
                            status=c_st,
                        )
                    )
        raw_out: int | float | str | None
        if isinstance(raw, (int, float, str)):
            raw_out = raw
        elif raw is None:
            raw_out = None
        else:
            raw_out = str(raw)
        return ValueNode(
            name=expression,
            expression=expression,
            type_name=tname,
            raw_value=raw_out,
            display_value=disp,
            status=status,
            children=children,
        )

    def assign(self, core: str, expression: str, value: str, frame: int | None = None) -> None:
        self._ensure_core(core)
        self._check_connection(core)
        vals = self._values.get(core, {})
        expr = expression.strip()
        # parse value
        v_str = value.strip()
        try:
            if v_str.lower().startswith("0x"):
                parsed: object = int(v_str, 16)
            elif v_str.lower().startswith("0b"):
                parsed = int(v_str, 2)
            else:
                parsed = int(v_str, 10)
        except ValueError:
            try:
                parsed = float(v_str)
            except ValueError:
                parsed = v_str
        # frame locals (respect frame if provided)
        self._init_frame_locals(core)
        fl_all = vals.get("__frame_locals__", {})
        if frame is not None:
            finfo = fl_all.get(frame, {}).get(expr)
            if finfo is not None and finfo.get("status") != ValueStatus.unavailable:
                finfo["value"] = parsed
                finfo["display"] = str(parsed)
                self._log("assign", f"Assigned {expr} = {value} (frame {frame})", core=core)
                return
        # search any frame local by name
        for fr, fl in fl_all.items():
            if expr in fl and fl[expr].get("status") != ValueStatus.unavailable:
                fl[expr]["value"] = parsed
                fl[expr]["display"] = str(parsed)
                self._log("assign", f"Assigned {expr} = {value} (frame {fr})", core=core)
                return
        if expr in vals and not isinstance(vals[expr], list) and expr != "__frame_locals__":
            vals[expr] = parsed
            self._log("assign", f"Assigned {expr} = {value}", core=core)
            return
        if "." in expr:
            base, member = expr.split(".", 1)
            key = f"{base}.{member}"
            if key in vals:
                vals[key] = parsed
                self._log("assign", f"Assigned {expr} = {value}", core=core)
                return
        m = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+)\]", expr)
        if m:
            name, idx_s = m.group(1), int(m.group(2))
            if name in vals and isinstance(vals[name], list):
                arr = vals[name]  # type: ignore[assignment]
                if 0 <= idx_s < len(arr):
                    arr[idx_s] = int(parsed) if isinstance(parsed, (int, float)) else parsed
                    self._log("assign", f"Assigned {expr} = {value}", core=core)
                    return
        raise JtagError(f"Cannot assign to expression: {expression}")

    def callstack(self, core: str) -> list[StackFrame]:
        self._ensure_core(core)
        self._check_connection(core)
        st = self._core_states.get(core, CoreState.Disconnected)
        if st == CoreState.Running:
            return []
        pc = int(self._pc.get(core, 0))
        frames = [
            StackFrame(index=0, function="control_loop", pc=pc, locals=self.locals(core, 0)),
            StackFrame(index=1, function="main", pc=max(pc - 0x10, 0), locals=self.locals(core, 1)),
        ]
        self._log("callstack", f"Call stack depth {len(frames)}", core=core)
        return frames

    def _init_frame_locals(self, core: str) -> None:
        # Mutable frame-local storage so assign/evaluate/locals stay consistent.
        self._values.setdefault(core, {})
        self._values[core].setdefault("__frame_locals__", {})
        fl = self._values[core]["__frame_locals__"]
        fl.setdefault(
            0,
            {
                "err": {"type": "int16", "value": 0, "status": ValueStatus.current},
                "pwm_duty": {"type": "uint16", "value": 50, "status": ValueStatus.current},
                "optimized_var": {
                    "type": "unknown",
                    "value": None,
                    "status": ValueStatus.unavailable,
                    "display": "<optimized out>",
                },
            },
        )
        fl.setdefault(
            1,
            {"status": {"type": "int16", "value": 0, "status": ValueStatus.current}},
        )

    def locals(self, core: str, frame: int) -> list[ValueNode]:
        self._ensure_core(core)
        self._check_connection(core)
        self._init_frame_locals(core)
        fl = self._values[core]["__frame_locals__"].get(frame, {})
        nodes: list[ValueNode] = []
        for name, info in fl.items():
            val = info.get("value")
            status = info.get("status", ValueStatus.current)
            display = info.get("display", str(val) if val is not None else "")
            raw_out: int | float | str | None
            if isinstance(val, (int, float, str)):
                raw_out = val
            elif val is None:
                raw_out = None
            else:
                raw_out = str(val)
            nodes.append(
                ValueNode(
                    name=name,
                    expression=name,
                    type_name=str(info.get("type", "unknown")),
                    raw_value=raw_out,
                    display_value=str(display),
                    status=status,
                )
            )
        return nodes

    def symbols(self, core: str) -> list[Symbol]:
        self._ensure_core(core)
        self._check_connection(core)
        return list(self._symbols.get(core, {}).values())

    def ping(self) -> bool:
        if self._inject_connection_lost:
            return False
        # ping indicates probe/link health in general
        return self._configured is not None and not self._inject_target_not_responding
