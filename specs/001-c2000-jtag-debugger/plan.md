# Implementation Plan: C2000 JTAG Debug Desktop App

**Branch**: `001-c2000-jtag-debugger` | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-c2000-jtag-debugger/spec.md`

## Summary

A Windows desktop app to connect to TI C2000 MCUs (F28388D, F28069M, F28M35x, F28M36x, F28P65x)
through any TI-supported JTAG probe, load `.out` images per core, run/halt/resume/reset, view
memory, watch and modify globals live while running, and inspect call stack/locals when halted.
Technical approach: Python/PySide6 UI over a layered core whose probe backend wraps TI's official
CCS Scripting API; a simulated backend enables hardware-free testing (see [research.md](./research.md)).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: PySide6 (Qt 6), TI CCS 20.x Scripting API (`scripting`), pyelftools,
pydantic (settings/session models), PyInstaller (packaging)

**Storage**: JSON files — per-user settings in `%APPDATA%\JTAG-conn\`, session files (`*.jtagc.json`)

**Testing**: pytest, pytest-qt, SimulatedBackend; optional HIL tests (`-m hw`)

**Target Platform**: Windows 10/11 x64 with CCS 20.x installed

**Project Type**: desktop-app

**Performance Goals**: connect < 5 s (SC-002); halt/resume < 0.5 s (SC-003); 50-symbol watch
refresh < 1 s (SC-004); connection loss detected < 3 s (SC-006); < 1% CPU idle, < 5% CPU live
polling, startup < 1.5 s (SC-008)

**Constraints**: UI thread never blocks on probe I/O; zero busy-wait loops (blocking queue + event-driven timers); contiguous memory coalescing & diff-only UI updates (`dataChanged` emitted only when value changes); paused polling when tab hidden/minimized; no writes without user action; flash writes confirmed; no bypass of CSM/DCSM or licensing

**Scale/Scope**: 1 probe, up to 5 cores per instance; images up to ~2 MB; ~10 UI panels

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How the plan complies | Status |
|-----------|-----------------------|--------|
| I. Target Safety First | Writes only via explicit UI commands; `FlashGuard` confirmation; connection watchdog; values carry `status` (current/stale/error) | PASS |
| II. Layered Architecture | `backend` → `core` → `symbols` → `ui`; UI depends only on `core` services; `DebugBackend` protocol | PASS |
| III. Test-First w/ Simulation | `SimulatedBackend` + ELF fixtures; contract tests for every backend; HIL optional | PASS |
| IV. Transparent Diagnostics | Structured log of every backend op; log panel; status bar shows version/probe/device/image | PASS |
| V. Simplicity & Focus | Uses vendor engine instead of custom JTAG; no breakpoints/stepping/source views | PASS |
| Platform constraints | Windows 10/11, C2000 incl. Arm cores, official TI driver path | PASS |

Post-design re-check (after Phase 1): PASS — no new violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-c2000-jtag-debugger/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── debug-backend.md
│   └── ui-commands.md
└── tasks.md             # created by /speckit.tasks
```

### Source Code (repository root)

```text
src/jtagconn/
├── app.py                     # entry point, Qt application bootstrap
├── backend/                   # Layer 1: probe/engine access
│   ├── base.py                # DebugBackend protocol, errors
│   ├── ccs_scripting.py       # CCS 20.x Scripting implementation
│   ├── simulated.py           # SimulatedBackend for tests/demo
│   └── ccxml/                 # .ccxml templates per probe/device
├── core/                      # Layer 2: debug domain services
│   ├── devices.py             # device catalog + core maps
│   ├── target_manager.py      # connections, cores, state machine, Run/Halt All
│   ├── worker.py              # single engine thread + command queue
│   ├── memory_service.py
│   ├── watch_service.py       # live polling, batching, writes
│   ├── stack_service.py       # call stack + locals
│   ├── flash_guard.py
│   └── watchdog.py            # connection-loss detection
├── symbols/                   # Layer 3: image & symbol handling
│   ├── image.py               # ProgramImage (ELF via pyelftools, COFF via engine)
│   ├── types.py               # type model + value encode/decode/validation
│   └── index.py               # symbol search/autocomplete
├── persistence/
│   └── session.py             # settings, recent files, session save/restore
└── ui/                        # Layer 4: PySide6 views
    ├── main_window.py
    ├── connection_panel.py
    ├── cores_panel.py
    ├── watch_view.py
    ├── locals_view.py
    ├── memory_view.py
    └── log_view.py

tests/
├── contract/                  # DebugBackend contract tests (simulated; ccs with -m hw)
├── unit/                      # symbols, types, services
├── integration/               # end-to-end user stories against SimulatedBackend
├── ui/                        # pytest-qt
└── fixtures/                  # sample .out files (ELF + COFF)

packaging/
└── jtagconn.spec              # PyInstaller
```

**Structure Decision**: Single Python package with four layer subpackages mirroring constitution
principle II; tests organized by contract/unit/integration/ui.

## Complexity Tracking

No constitution violations; section intentionally empty.
