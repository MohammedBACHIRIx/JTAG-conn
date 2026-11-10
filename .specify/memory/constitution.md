<!--
Sync Impact Report
- Version change: 1.0.0 → 1.0.1 (PATCH: clarified target devices include Arm cores of C2000 MCUs)
- Principles defined: I. Target Safety First; II. Layered Debug Architecture;
  III. Test-First with Simulated Targets; IV. Transparent Diagnostics; V. Simplicity & Focus
- Added sections: Platform & Hardware Constraints; Development Workflow & Quality Gates
- Removed sections: none
- Follow-up TODOs: none
-->
# JTAG-conn Constitution

## Core Principles

### I. Target Safety First
The application controls real hardware. It MUST never write target memory, flash, or registers
without an explicit user action. Destructive operations (program/erase, reset, writes to
non-RAM regions) MUST be confirmed or clearly indicated. Connection loss MUST be detected and
surfaced; the app MUST NOT leave the UI showing stale values as if they were live.
Rationale: an unintended write to a motor-control MCU can damage equipment or people.

### II. Layered Debug Architecture
Code MUST be separated into independent layers: (1) probe/transport backend, (2) target debug
core (run control, memory, registers), (3) symbol/image handling (.out parsing, symbol and type
resolution), (4) user interface. The UI MUST NOT talk to the probe directly. Each lower layer
MUST be usable and testable without the UI. The probe backend MUST sit behind an interface so
alternative probes or a simulated target can be substituted.

### III. Test-First with Simulated Targets (NON-NEGOTIABLE)
Every debug-core and symbol-handling feature MUST have automated tests that run without
hardware, using a simulated target and recorded/sample .out files. Tests are written before or
alongside implementation and MUST pass in CI. Hardware-in-the-loop tests are maintained as a
documented manual or optional suite.

### IV. Transparent Diagnostics
All probe operations MUST be logged with timestamps to a user-accessible log. Errors MUST be
reported in plain language with the underlying cause (e.g., "Target not responding: check power
and JTAG cable"). The app MUST expose its version, the probe and target identified, and the
loaded image path at all times.

### V. Simplicity & Focus
Scope is a focused C2000 load/run/inspect tool, not a full IDE. Features beyond connect, load,
run control, memory view, and symbol watch/modify require a spec. Prefer existing, vendor-
supported debug interfaces over custom low-level JTAG implementations. YAGNI applies.

## Platform & Hardware Constraints

- Target OS: Windows 10/11 (64-bit) desktop.
- Target devices: TI C2000 MCU family, including the Arm Cortex-M cores of Concerto (F28M3x) and
  F2838x devices; images in TI `.out` format produced by TI toolchains.
- Probe access MUST go through a supported, documented driver/SDK path; no bypass of vendor
  driver or licensing mechanisms.
- The app MUST remain responsive (UI never blocked) during probe operations.

## Development Workflow & Quality Gates

- Every feature follows Spec Kit: specify → (clarify) → plan → tasks → implement.
- Every change MUST pass automated tests and static checks before merge.
- Plans MUST include a Constitution Check; deviations MUST be justified in the plan's
  Complexity Tracking section.

## Governance

This constitution supersedes other practices for this project. Amendments require a documented
rationale, a version bump (MAJOR: principle removal/redefinition; MINOR: new principle or section;
PATCH: clarifications), and review of dependent plans. Reviews MUST verify compliance with these
principles.

**Version**: 1.0.1 | **Ratified**: 2026-11-10 | **Last Amended**: 2026-11-10
