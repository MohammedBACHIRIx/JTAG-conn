# Feature Specification: C2000 JTAG Debug Desktop App

**Feature Branch**: `001-c2000-jtag-debugger`

**Created**: 2026-11-10

**Status**: Draft

## Clarifications

### Session 2026-11-10

- Q: Which probes? → A: All probes supported by TI's C2000 debug software (incl. third-party).
- Q: Which devices? → A: F28388D, F28069M, F28M35x, F28M36x, F28P65x.
- Q: Watch while running? → A: Live refresh without halting (real-time access).
- Scope change: local variables and multi-core debugging (CPU2/CLA, plus Arm cores) are in v1.

**Input**: User description: "build a desktop windows app that connect to C2000 MCU using JTAG probe, the app load .out file, connect, load and run, halt and resume, read memory, and watch and modify symboles"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect, Load and Run Firmware (Priority: P1)

An embedded engineer plugs a JTAG probe into the PC and a C2000 board, opens the app, selects
a `.out` firmware file, connects to the target, downloads the program, and starts it running.

**Why this priority**: Getting firmware onto the target and running is the foundation every
other capability depends on; on its own it already replaces a heavy IDE for quick flashing.

**Independent Test**: With a board attached, select a known `.out`, press Connect, Load, Run,
and observe the board behaving as expected (e.g., LED blinking).

**Acceptance Scenarios**:

1. **Given** a probe and powered C2000 target are attached, **When** the user clicks Connect,
   **Then** the app reports the probe and target identified and shows state "Connected – Halted".
2. **Given** a valid `.out` file is selected and the target is connected, **When** the user
   clicks Load, **Then** the program is downloaded with visible progress, verified, and the
   program counter is set to the entry point.
3. **Given** a program is loaded, **When** the user clicks Run, **Then** the target executes and
   the state shows "Running".
4. **Given** no probe is attached or the target is unpowered, **When** the user clicks Connect,
   **Then** a clear error explains the likely cause and the app stays in "Disconnected".

---

### User Story 2 - Halt and Resume Execution (Priority: P2)

While the firmware runs, the engineer halts the CPU to inspect it, then resumes execution.

**Why this priority**: Halting is required to inspect target state reliably; it is the next
most valuable debug action after running.

**Independent Test**: Run a loaded program, press Halt, confirm state "Halted" with the current
program counter/function shown; press Resume and confirm execution continues.

**Acceptance Scenarios**:

1. **Given** the target is running, **When** the user clicks Halt, **Then** the CPU stops, state
   shows "Halted", and the current program location (address and function name if known) is shown.
2. **Given** the target is halted, **When** the user clicks Resume, **Then** execution continues
   from where it stopped and state shows "Running".
3. **Given** the target is halted, **When** the user clicks Reset, **Then** the CPU is reset and
   remains halted at the reset location.

---

### User Story 3 - Watch and Modify Symbols (Priority: P2)

The engineer adds global variables from the loaded program (by name, with search/autocomplete)
to a watch list, sees their current values with correct types, and edits a value to change
firmware behavior (e.g., a setpoint or gain).

**Why this priority**: Observing and tuning variables is the primary day-to-day use once
firmware runs; it is the main reason to use this tool over a pure flasher.

**Independent Test**: Load a program, add a known global variable to the watch list, verify the
displayed value matches expectations, edit it, and verify the change takes effect on the target.

**Acceptance Scenarios**:

1. **Given** a `.out` file is loaded, **When** the user types part of a symbol name, **Then**
   matching global symbols are suggested with their type and address.
2. **Given** a symbol is in the watch list and the target is halted, **When** the view refreshes,
   **Then** the value is displayed according to its type (integer, float, enum, pointer, and
   expandable struct/array members).
3. **Given** a watched symbol, **When** the user enters a new valid value, **Then** it is written
   to the target and the re-read value matches.
4. **Given** the user enters an invalid value (wrong format or out of range for the type),
   **Then** the write is rejected with an explanation and target memory is unchanged.
5. **Given** the target is running, **Then** watch values behave per FR-014.

---

### User Story 4 - Read Memory (Priority: P3)

The engineer opens a memory view, enters an address or symbol name, and views a range of target
memory in selectable formats.

**Why this priority**: Useful for low-level inspection (peripheral registers, buffers) but used
less often than symbol watching.

**Independent Test**: Enter the address of a known variable or peripheral register and confirm
the displayed contents match the expected values.

**Acceptance Scenarios**:

1. **Given** the target is connected, **When** the user enters a start address (or symbol) and
   length, **Then** memory is displayed in rows with address, values, and selected format
   (hex 16-bit, hex 32-bit, signed/unsigned decimal, float).
2. **Given** a memory view is open, **When** the user clicks Refresh, **Then** contents are re-read.
3. **Given** the user requests an invalid or inaccessible address range, **Then** the app shows an
   error for that range without disconnecting.

---

### User Story 5 - Inspect Local Variables and Call Stack (Priority: P3)

When the target is halted, the engineer sees the call stack and the local variables and
parameters of the selected function frame, and can modify them.

**Why this priority**: Gives function-level insight when a halt lands inside code of interest.

**Independent Test**: Halt inside a known function and verify its locals and the call chain match
the source.

**Acceptance Scenarios**:

1. **Given** a core is halted inside a function with debug info, **Then** the call stack lists
   the active functions and the locals/parameters of the top frame are shown with values.
2. **Given** the user selects another stack frame, **Then** that frame's locals are shown.
3. **Given** the user edits a local variable, **Then** the new value is written and re-read.
4. **Given** the core resumes, **Then** locals are cleared or marked unavailable until the next halt.

---

### User Story 6 - Multi-Core Debugging (Priority: P3)

On multi-core devices (e.g., F28388D, F28P65x, F28M35x/F28M36x) the engineer selects which
cores to connect to (C28x CPU1/CPU2, CLA, Arm Cortex-M), loads an image per core, and controls
and inspects each core independently or all together.

**Why this priority**: Required for the dual-core and Concerto devices in scope, but builds on
the single-core capabilities.

**Independent Test**: On a dual-core device, load different images to CPU1 and CPU2, run both,
halt only CPU2, and confirm CPU1 keeps running while CPU2 variables are inspected.

**Acceptance Scenarios**:

1. **Given** a multi-core device is connected, **Then** the app lists all debuggable cores with
   each core's state.
2. **Given** a core is selected, **When** the user loads, runs, halts, or watches, **Then** the
   action applies only to that core.
3. **Given** several cores are connected, **When** the user clicks Halt All or Run All, **Then**
   all connected cores change state together.
4. **Given** a core that must be released by another (e.g., CPU2 booted by CPU1, CM on Concerto),
   **Then** the app explains the dependency if that core cannot be connected yet.

---

### Edge Cases

- Probe unplugged or target power lost mid-session: app detects within a few seconds, shows
  "Connection lost", stops refreshing values, and allows reconnect.
- Selected file is not a valid `.out` or was built for a different device: load is refused with
  an explanation before anything is written.
- `.out` has no debug information: load and run still work; symbol watch is limited to symbol
  names/addresses with raw values, and the user is informed.
- Program targets flash memory: the user is warned and must confirm before flash is programmed.
- Target is code-security (CSM/DCSM) locked: app reports the target is secured and does not attempt
  to bypass it.
- File changed on disk after loading: app indicates symbols may be out of date and offers reload.
- Watch list contains a symbol absent from a newly loaded program: entry is marked "not found".
- Another debugger (e.g., an IDE) is already using the probe: app reports the probe is busy.
- Variable optimized away or not in a register/stack location at the current PC: shown as
  "unavailable" rather than a wrong value.
- Live (real-time) refresh not possible for a memory region or core: values marked stale and
  the user is told why.
- Shared memory between cores (e.g., IPC message RAM): addresses resolved per core's memory map.
- Device is Concerto/F2838x with an Arm core: Arm-core images and symbols are handled with that
  core's byte-addressed memory model.
- C2000 16-bit addressable memory: sizes and addresses are shown consistently in target words,
  with byte/word units clearly labeled.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run as a desktop application on Windows 10/11 64-bit.
- **FR-002**: System MUST let users select a TI `.out` executable via file dialog and remember
  recently used files.
- **FR-003**: System MUST detect attached supported JTAG probes and let the user choose one.
  Supported probes: all JTAG probes supported by TI's standard debug software for C2000, including
  TI XDS100v2/v3, XDS110, XDS200, XDS560v2 and compatible third-party probes (e.g., Spectrum
  Digital, Blackhawk).
- **FR-004**: System MUST connect to and identify the target device. Supported devices in v1:
  F28388D (F2838xD), F28069M (F2806x), F28M35x and F28M36x (Concerto), and F28P65x.
- **FR-005**: System MUST download the program image to the target, show progress, verify the
  written contents, and report success or the first failing address.
- **FR-006**: System MUST require explicit user confirmation before programming flash memory.
- **FR-007**: System MUST provide Run, Halt, Resume, and Reset controls, enabled only when valid
  for the current state.
- **FR-008**: System MUST always display current target state: Disconnected, Connected–Halted,
  Running, or Connection lost.
- **FR-009**: When halted, the system MUST show the current program counter and the containing
  function name when available.
- **FR-010**: System MUST list and search global/static symbols from the loaded `.out`, showing
  name, address, size, and type.
- **FR-011**: System MUST display watched symbol values decoded per their type, including nested
  struct, union, array, enum, and pointer types, with selectable number format (hex/decimal).
- **FR-012**: Users MUST be able to modify watched symbol values (scalar fields, struct members,
  array elements), with type and range validation before writing.
- **FR-013**: System MUST provide a memory view by address or symbol, length, and display format,
  with manual refresh and optional auto-refresh when halted.
- **FR-014**: While the target is running, global/static watch values and memory views MUST refresh
  live without halting the CPU (non-intrusive real-time access) at a user-selectable interval
  (default 500 ms); writes to globals MUST also be possible while running. Local variables are
  only available while the selected core is halted.
- **FR-015**: System MUST persist the watch list, last file, and probe selection per project/session
  and restore them on restart.
- **FR-016**: System MUST log all probe operations with timestamps and expose the log to the user;
  errors MUST be reported in plain language with the cause.
- **FR-017**: System MUST detect connection loss and stop presenting values as current.
- **FR-018**: System MUST keep the user interface responsive during all target operations, and
  long operations (load) MUST be cancellable where safe.
- **FR-019**: System MUST NOT attempt to bypass device code security or probe licensing.
- **FR-020**: When a core is halted, the system MUST show its call stack and the local variables
  and parameters of the selected stack frame, decoded by type, and allow modifying them.
- **FR-021**: System MUST list all debuggable cores on multi-core devices (e.g., C28x CPU1, CPU2,
  CLA, and Arm Cortex-M cores on F28M35x/F28M36x/F28388D) and allow connecting to each one.
- **FR-022**: System MUST let the user load a separate `.out` image per core and perform run, halt,
  resume, reset, memory, and watch operations per core, with each core's state shown independently.
- **FR-023**: System MUST offer "run all / halt all" actions for multi-core devices.
- **FR-024**: System MUST maintain near-zero CPU usage (<1% on modern multi-core desktop) when idle or halted with auto-refresh off, and <5% average CPU usage during 500 ms live-watch polling of 50 symbols; UI rendering MUST ONLY occur for changed values (delta updates).

### Key Entities

- **Probe**: An attached JTAG debug adapter; identity (model, serial), connection status.
- **Target**: The connected C2000 device; device name, CPU core, execution state, program counter.
- **Program Image**: The loaded `.out` file; path, timestamp, entry point, memory sections (load
  address, size, RAM/flash), debug info availability.
- **Symbol**: A named program variable from the image; name, address, size, type description.
- **Core**: One debuggable CPU of the device (C28x CPU1/CPU2, CLA, Arm Cortex-M); has its own
  state, program image, and watch list.
- **Stack Frame**: One active function call on a halted core; function, location, locals.
- **Watch Entry**: A user-selected symbol or expression in the watch list; display format,
  last value, value status (current/stale/error).
- **Memory View**: A user-selected address range and display format with last read contents.
- **Session**: The saved set of last image, probe choice, and watch entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can connect, load, and run a sample program in under 2 minutes
  without documentation.
- **SC-002**: Connecting to an attached target completes in under 5 seconds in 95% of attempts.
- **SC-003**: Halt and resume take effect within 0.5 seconds of the user action.
- **SC-004**: A watch list of 50 symbols refreshes in under 1 second while halted.
- **SC-005**: Values written through the app match the value read back in 100% of valid writes.
- **SC-006**: Loss of the probe or target power is reported to the user within 3 seconds.
- **SC-007**: 100% of rejected operations (invalid file, invalid value, secured device) leave target
  memory unchanged.
- **SC-008**: Application consumes <1% CPU when idle/halted (auto-refresh off), <5% CPU during 500 ms live-watch polling of 50 symbols, and starts up to interactive main window in under 1.5 seconds.

## Assumptions

- Users are embedded engineers familiar with C2000 and JTAG debugging concepts.
- `.out` files are produced by the TI C2000 code generation tools with standard debug info.
- The required TI probe drivers/emulation software are installed on the PC (or bundled where the
  license permits).
- "f29388d" in the request is interpreted as the TI F28388D (F2838xD family).
- Breakpoints, single-stepping, source-level views, and disassembly are out of scope for v1.
- Local variables are inspected only at halt points (user Halt); there are no breakpoints to
  stop at a chosen line in v1.
- One target connection per application instance.
