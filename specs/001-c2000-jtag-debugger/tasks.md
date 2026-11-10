# Tasks: C2000 JTAG Debug Desktop App

**Input**: Design documents from `/specs/001-c2000-jtag-debugger/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Automated tests against `SimulatedBackend` and ELF fixtures are REQUIRED per Constitution Principle III (Test-First with Simulated Targets).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, packaging metadata, and directory layout

- [ ] T001 Create project directory structure (`src/jtagconn/{backend,core,symbols,persistence,ui}`, `tests/{contract,unit,integration,ui,fixtures}`, `packaging/`) per [plan.md](./plan.md)
- [ ] T002 Create `pyproject.toml` with Python 3.12+, `PySide6`, `pyelftools`, `pydantic`, and dev dependencies (`pytest`, `pytest-qt`, `ruff`)
- [ ] T003 [P] Configure linting/formatting and pytest markers (`hw`) in `pyproject.toml` and `tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, Layer 1 `DebugBackend` protocol + `SimulatedBackend`, single worker thread, diagnostics logger, and sample fixture generator

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 [P] Implement domain models and enums (`Probe`, `DeviceProfile`, `CoreProfile`, `Core`, `CoreState`, `ProgramImage`, `Section`, `Symbol`, `TypeInfo`, `WatchEntry`, `StackFrame`, `MemoryView`, `Session`) in `src/jtagconn/core/models.py`
- [ ] T005 [P] Implement device catalog for `F28388D`, `F28069M`, `F28M35x`, `F28M36x`, `F28P65x` (core maps, address units, flash ranges, boot dependencies) in `src/jtagconn/core/devices.py`
- [ ] T006 [P] Define `DebugBackend` protocol and typed exceptions (`ProbeNotFound`, `TargetNotResponding`, `ProbeBusy`, `DeviceSecured`, `CoreNotAvailable`, `InvalidImage`, `VerifyError`, `MemoryAccessError`, `ConnectionLost`, `EngineMissing`) in `src/jtagconn/backend/base.py`
- [ ] T007 [P] Implement structured timestamped operation logger and plain-language error formatter in `src/jtagconn/core/logging_service.py`
- [ ] T008 Implement `SimulatedBackend` (multi-core 16-bit word & byte-addressed memory spaces, simulated symbols, callstack, locals, flash verify, and fault injection) in `src/jtagconn/backend/simulated.py`
- [ ] T009Implement `CcsScriptingBackend` wrapping TI CCS 20.x `scripting.initScripting` and `.ccxml` template generator in `src/jtagconn/backend/ccs_scripting.py` and `src/jtagconn/backend/ccxml/generator.py`
- [ ] T010 Implement zero-busy-wait event-driven worker thread (`EngineWorker`) with blocking command queue, cancellation tokens, and Qt signals in `src/jtagconn/core/worker.py`
- [ ] T011 [P] Create synthetic minimal ELF `.out` fixture generator and contract test suite for `DebugBackend` in `tests/fixtures/make_fixtures.py` and `tests/contract/test_debug_backend.py`

**Checkpoint**: Foundation ready — `DebugBackend` contract tests pass against `SimulatedBackend`

---

## Phase 3: User Story 1 - Connect, Load and Run Firmware (Priority: P1) 🎯 MVP

**Goal**: Select a `.out` file, detect/choose a JTAG probe and C2000 device, connect, verify & load firmware (with flash confirmation), and start execution.

**Independent Test**: Connect to simulated or hardware target, load sample `.out`, verify progress & flash confirmation, click Run, and verify state transitions to `Running`.

### Tests for User Story 1 ⚠️

- [ ] T012 [P] [US1] Unit tests for `ProgramImage` loader, `FlashGuard`, and `TargetManager` connect/load/run state machine in `tests/unit/test_us1_connect_load_run.py`
- [ ] T013 [P] [US1] Integration test for connect, flash-confirm, load with progress/verify, run, and connection error handling in `tests/integration/test_us1_flow.py`

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement `ProgramImage` parser (ELF sections/entry/symbols via `pyelftools`, COFF fallback metadata, mtime tracking, device compatibility check) in `src/jtagconn/symbols/image.py`
- [ ] T015 [P] [US1] Implement `FlashGuard` (detects sections overlapping device `flash_regions` and requires confirmation before load) in `src/jtagconn/core/flash_guard.py`
- [ ] T016 [US1] Implement `TargetManager` (probe discovery, configure, connect/disconnect, cancellable `load_program`, `run`, and connection watchdog) in `src/jtagconn/core/target_manager.py`
- [ ] T017 [P] [US1] Implement session & recent-files persistence (`%APPDATA%/JTAG-conn` / `~/.config/jtagconn`) in `src/jtagconn/persistence/session.py`
- [ ] T018 [US1] Implement connection toolbar, `.out` file picker, flash confirmation dialog, log panel, and status bar in `src/jtagconn/ui/connection_panel.py`, `src/jtagconn/ui/log_view.py`, and `src/jtagconn/ui/main_window.py`

**Checkpoint**: User Story 1 is functional and independently testable.

---

## Phase 4: User Story 2 - Halt and Resume Execution (Priority: P2)

**Goal**: Halt a running CPU (displaying PC and containing function name), resume execution, or reset the CPU to its reset vector while halted.

**Independent Test**: Run a loaded program, click Halt (confirm state `Halted` + PC + function name), click Resume (confirm `Running`), click Halt then Reset (confirm reset PC).

### Tests for User Story 2 ⚠️

- [ ] T019 [P] [US2] Unit & integration tests for `halt`, `resume`, `reset`, and PC-to-function symbol resolution in `tests/integration/test_us2_halt_resume.py`

### Implementation for User Story 2

- [ ] T020 [US2] Extend `TargetManager` and `ProgramImage` with PC-to-function lookup and strict state-guarded `halt()`, `resume()`, and `reset()` in `src/jtagconn/core/target_manager.py` and `src/jtagconn/symbols/image.py`
- [ ] T021 [US2] Wire Halt, Resume, and Reset actions with state-based enablement and PC/function readout in `src/jtagconn/ui/connection_panel.py` and `src/jtagconn/ui/main_window.py`

**Checkpoint**: User Stories 1 and 2 work independently.

---

## Phase 5: User Story 3 - Watch and Modify Symbols Live (Priority: P2)

**Goal**: Search/autocomplete global and static symbols from `.out`, watch decoded values (scalars, enums, pointers, nested structs/arrays), refresh live while running with minimal CPU usage, and validate/write modified values.

**Independent Test**: Load `.out`, search and add symbols to Watch, verify live updates while running at 500 ms interval with diff-only UI emission, modify a scalar/struct member, and verify invalid inputs are rejected without target writes.

### Tests for User Story 3 ⚠️

- [ ] T022 [P] [US3] Unit tests for `SymbolIndex` autocomplete, `TypeInfo` encode/decode/validation, and contiguous memory read coalescing in `tests/unit/test_us3_watch_types.py`
- [ ] T023 [P] [US3] Integration test for live watch polling, diff-only updates, stale fallback, and validated symbol writes in `tests/integration/test_us3_watch_flow.py`

### Implementation for User Story 3

- [ ] T024 [P] [US3] Implement `TypeInfo` codec and range/format validator (int/uint 16/32/64, float32/64, enum, pointer, struct, array) in `src/jtagconn/symbols/types.py`
- [ ] T025 [P] [US3] Implement fast prefix/substring `SymbolIndex` over `ProgramImage` symbols in `src/jtagconn/symbols/index.py`
- [ ] T026 [US3] Implement high-efficiency `WatchService` (contiguous address coalescing, adaptive timer that pauses when hidden/disconnected, value hash diffing to emit only changed nodes, validated writes) in `src/jtagconn/core/watch_service.py`
- [ ] T027 [US3] Implement `WatchView` (`QAbstractItemModel` tree with autocomplete adder, format selector, inline editing, and status badges) in `src/jtagconn/ui/watch_view.py`

**Checkpoint**: User Stories 1, 2, and 3 work independently.

---

## Phase 6: User Story 4 - Read Memory (Priority: P3)

**Goal**: Inspect arbitrary target memory ranges by hex address or symbol name in selectable formats (hex16, hex32, int16, uint16, int32, uint32, float32) with manual and live refresh.

**Independent Test**: Open Memory view, enter symbol name or address + length, verify formatted words match target memory, and verify out-of-range addresses report an error without disconnecting.

### Tests for User Story 4 ⚠️

- [ ] T028 [P] [US4] Unit & integration tests for `MemoryService` address/symbol resolution, word/byte formatting, and inaccessible range handling in `tests/integration/test_us4_memory.py`

### Implementation for User Story 4

- [ ] T029 [US4] Implement `MemoryService` (symbol-to-address resolution, chunked reads, diff detection, format conversion) in `src/jtagconn/core/memory_service.py`
- [ ] T030 [US4] Implement virtualized table `MemoryView` (`QAbstractTableModel`) with address/symbol input, format selector, and refresh controls in `src/jtagconn/ui/memory_view.py`

---

## Phase 7: User Story 5 - Inspect Local Variables and Call Stack (Priority: P3)

**Goal**: When a core is halted, display its call stack frames and the decoded local variables/parameters for the selected frame, allowing edits to available locals.

**Independent Test**: Halt inside a function, verify call stack frames and top-frame locals, switch frames, edit a local variable, and verify locals clear/mark unavailable upon Resume.

### Tests for User Story 5 ⚠️

- [ ] T031 [P] [US5] Integration test for call stack retrieval, frame selection, local editing, and resume clearing in `tests/integration/test_us5_stack_locals.py`

### Implementation for User Story 5

- [ ] T032 [US5] Implement `StackService` (call stack fetch on halt, per-frame locals evaluation, `unavailable` handling for optimized-out locals, validated local assignment, auto-clear on run) in `src/jtagconn/core/stack_service.py`
- [ ] T033 [US5] Implement `LocalsView` dock (call stack list + frame locals tree view with inline editing) in `src/jtagconn/ui/locals_view.py`

---

## Phase 8: User Story 6 - Multi-Core Debugging (Priority: P3)

**Goal**: Discover and connect to multiple cores (C28x CPU1/CPU2, CLA, Cortex-M), load independent `.out` images per core, switch active core context in UI panels, and execute synchronous Run All / Halt All.

**Independent Test**: Connect to simulated F28388D, load separate `.out` files on `C28xx_CPU1` and `C28xx_CPU2`, click Run All, halt only `C28xx_CPU2`, and verify `C28xx_CPU1` remains running while `C28xx_CPU2` locals/watch are inspected.

### Tests for User Story 6 ⚠️

- [ ] T034 [P] [US6] Integration test for multi-core independent connect/load/watch, boot-dependency error reporting, and `run_all` / `halt_all` in `tests/integration/test_us6_multicore.py`

### Implementation for User Story 6

- [ ] T035 [US6] Extend `TargetManager`, `WatchService`, `MemoryService`, and `StackService` for multi-core session isolation, boot-dependency diagnostics (`CoreNotAvailable`), and `run_all`/`halt_all` in `src/jtagconn/core/target_manager.py`
- [ ] T036 [US6] Implement `CoresPanel` dock and Run All / Halt All toolbar controls in `src/jtagconn/ui/cores_panel.py` and `src/jtagconn/ui/main_window.py`

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end UI tests, CPU/latency efficiency verification, CLI entry point (`--simulate`), and Windows PyInstaller packaging

- [ ] T037 [P] Implement CLI entry point (`python -m jtagconn [--simulate]`) and application bootstrap in `src/jtagconn/app.py` and `src/jtagconn/__main__.py`
- [ ] T038 [P] Implement `pytest-qt` end-to-end UI test suite and performance/efficiency benchmark test (verifying SC-004 <1s 50-symbol refresh and SC-008 zero idle polling) in `tests/ui/test_main_window.py`
- [ ] T039 [P] Create PyInstaller spec and Windows build script in `packaging/jtagconn.spec`
- [ ] T040 Run full test & lint suite (`pytest` and `ruff check`) and validate against [quickstart.md](./quickstart.md)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational)** → blocks all User Stories.
- **US1 (P1)** → MVP foundation for target connection and program loading.
- **US2 (P2)**, **US3 (P2)**, **US4 (P3)**, **US5 (P3)**, **US6 (P3)** build cleanly on Phase 2 + US1.
- Tasks marked `[P]` touch independent files and can be executed in parallel.
