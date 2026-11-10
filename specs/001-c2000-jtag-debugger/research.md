# Phase 0 Research: C2000 JTAG Debug Desktop App

## R1. How to access the probe/target

- **Decision**: Use TI's **CCS Scripting API (Python)** from Code Composer Studio 20.x
  (`from scripting import initScripting`) as the debug engine, wrapped behind our own
  `DebugBackend` interface.
- **Rationale**: The spec requires *all* TI-supported probes (XDS100/110/200/560, third-party),
  five device families incl. Concerto Arm cores, multi-core, real-time memory access, COFF and ELF
  `.out` files, flash programming, call stacks and locals. TI's debug server already supports all
  of this through the official, licensed path (constitution V, FR-019). Implementing JTAG/flash
  algorithms ourselves for 5 families × N probes is infeasible and would bypass vendor drivers.
- **Alternatives considered**:
  - Legacy DSS (Jython/Rhino, CCS ≤ 12): deprecated; kept as optional fallback adapter only.
  - OpenOCD: no/limited C28x support, no XDS100/560 flash algorithms for these devices.
  - Direct XDS110 CMSIS-DAP/JTAG: XDS110 only; no flash algorithms; fails "all probes".
  - TI UniFlash CLI: flashing only; no run control, watch, or locals.

## R2. Language & UI framework

- **Decision**: **Python 3.12 + PySide6 (Qt 6)**, packaged as a Windows installer with PyInstaller.
- **Rationale**: Same language as the CCS Scripting API → no inter-process bridge; Qt gives a
  native-looking docking desktop UI (tree views for watch/locals, table for memory), threads/
  signals for a non-blocking UI (constitution, FR-018).
- **Alternatives considered**: C#/WPF (best Windows look, but needs a Python/Node sidecar for CCS
  Scripting → two runtimes, IPC); Electron + Node scripting API (heavier, larger footprint).

## R3. Target configuration (.ccxml)

- **Decision**: Generate `.ccxml` target configs from bundled templates per (probe, device) pair;
  also allow the user to pick an existing `.ccxml`.
- **Rationale**: CCS Scripting connects via `ds.configure(ccxml)`; templates avoid requiring users
  to create configs in CCS. Probe detection uses TI's `xdsdfu`/`xds110reset` and the emulation
  package's connection enumeration where available; otherwise user selects the probe type.

## R4. Symbols, types, locals, call stack

- **Decision**: Use the debug engine's **expression/symbol/callstack services** for value decoding,
  locals and call stack (works for both COFF and ELF/DWARF). Use **pyelftools** to parse ELF `.out`
  files offline for the symbol browser (works before connecting); for COFF images, the symbol list
  is populated from the engine after load.
- **Rationale**: F28069M/F28M35 legacy projects are often COFF; the engine handles both. Offline
  ELF parsing gives fast autocomplete (SC-004) without the target.

## R5. Live (real-time) watch while running

- **Decision**: Poll globals while running through the engine's non-intrusive memory access at a
  configurable interval (default 500 ms), batched per contiguous region; on cores/regions where
  the engine reports access is unavailable, mark values *stale* (spec edge case).
- **Rationale**: C28x and Cortex-M debug logic allow memory access without halting. Batching keeps
  50 symbols < 1 s (SC-004).

## R6. Multi-core

- **Decision**: One engine session per core (`ds.openSession("<probe>/<core>")`), managed by a
  `TargetManager`. Run All/Halt All use the engine's synchronous group run/halt where supported;
  otherwise sequential with timing reported.
- **Core map**: F28388D: C28xx_CPU1, C28xx_CPU2, CLA1 (×2), CM (Cortex-M4); F28P65x: CPU1, CPU2,
  CLA1; F28M35x/F28M36x: Cortex_M3_0, C28xx_0; F28069M: C28xx, CLA_0.

## R7. Threading model

- **Decision**: All engine calls run on a single dedicated worker thread per probe connection
  (engine sessions are not thread-safe); UI communicates via a command queue + Qt signals.

## R8. Testing without hardware (constitution III)

- **Decision**: `SimulatedBackend` implementing `DebugBackend` with an in-memory, 16-bit-word
  addressed memory model, multiple cores, and scripted run/halt; plus sample ELF `.out` fixtures
  built with TI C2000 CGT and checked in. pytest + pytest-qt. HIL suite marked `@pytest.mark.hw`.

## R9. Prerequisite licensing / install

- **Decision**: Require CCS 20.x (free) installed; the app locates it via registry/env/`CCS_ROOT`
  setting and reports a clear error if missing. No TI binaries are redistributed.
