# JTAG-conn — Lightweight TI C2000 JTAG Debugger & Live Watch Tool

`JTAG-conn` is a low-CPU, standalone Windows 10/11 desktop utility for connecting to Texas Instruments C2000 microcontrollers over JTAG, loading `.out` (COFF/ELF) firmware, watching and modifying global symbols live while the target runs, inspecting memory, and debugging multi-core targets without launching the full Code Composer Studio (CCS) IDE.

---

## Features

- **All TI JTAG Probes Supported**: `XDS100v2`, `XDS100v3`, `XDS110`, `XDS200`, `XDS560v2`, and `ThirdParty` probes.
- **Built-in C2000 Device Catalog & `.ccxml` Generator**:
  - `TMS320F28388D` (`CPU1`, `CPU2`, `CLA1`, `CM`)
  - `TMS320F28069M` (`CPU1`, `CLA1`)
  - `F28M35x` & `F28M36x` Concerto (`C28x`, `Cortex-M3`)
  - `TMS320F28P65x` (`CPU1`, `CPU2`, `CLA1`)
  - Or import any custom `.ccxml` target configuration file.
- **One-Click Connect + Load + Run**: Connect to target, validate `.out` image architecture, guard against unintended Flash programming, load symbols/program, and run.
- **Non-Intrusive Live Watch**: Real-time background polling (`100 ms` – `5000 ms`, default `500 ms`) with diff-only UI updates and inline symbol writes while the MCU runs. Automatically pauses polling when minimized or when the Watch tab is hidden (`0%` idle CPU).
- **Multi-Core Control**: Inspect per-core state (`Disconnected`, `Halted`, `Running`, `Faulted`) and Program Counter (`PC`), switch active core, or execute `Run All`, `Halt All`, and `Reset Core`.
- **Memory Inspector**: Read target memory by hex address, word count, and word size (`16-bit` C28x word or `32-bit`) with formatted table and hex/ASCII dump.
- **Call Stack & Local Variables**: Inspect DWARF stack frames and frame-relative local variables when the active core is halted.
- **Built-in Simulator Mode**: Test workflows, symbol parsing, live watch, and UI without physical hardware using `--simulate`.

---

## Quick Start (Windows Standalone `.exe`)

### 1. Build `JTAG-conn.exe` from Source

On Windows 10/11 with Python 3.12+ installed:

```powershell
git clone https://github.com/MohammedBACHIRIx/JTAG-conn.git
cd JTAG-conn
powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
```

Output artifacts:
- Standalone single-file executable: `dist\JTAG-conn.exe`
- Optional Windows Setup installer (if Inno Setup `ISCC.exe` is installed): `dist\JTAG-conn-Setup.exe`

*(If rebuilding while `JTAG-conn.exe` is open, close the app first or run `Stop-Process -Name "JTAG-conn" -Force -ErrorAction SilentlyContinue`.)*

### 2. Run the Application

**Hardware Mode** (uses TI CCS Scripting / DSS or `--dss-path`):
```powershell
.\dist\JTAG-conn.exe
```

**Simulated Target Mode** (no JTAG probe or MCU required):
```powershell
.\dist\JTAG-conn.exe --simulate
```

**Headless Self-Check** (CI / smoke verification):
```powershell
.\dist\JTAG-conn.exe --simulate --headless-check
```

---

## CLI Options

```text
usage: jtagconn [-h] [--simulate] [--headless-check] [--ccxml CCXML]
                [--out OUT] [--device DEVICE] [--probe PROBE]
                [--dss-path DSS_PATH] [--log-dir LOG_DIR]

options:
  --simulate           Use deterministic simulated C2000 backend
  --headless-check     Run non-interactive self-check and exit 0
  --ccxml CCXML        Pre-populate path to .ccxml target configuration
  --out OUT            Pre-populate path to .out firmware image
  --device DEVICE      Pre-select device (F28388D, F28069M, F28M35x, F28M36x, F28P65x)
  --probe PROBE        Pre-select JTAG probe (XDS100v2, XDS100v3, XDS110, XDS200, XDS560v2, ThirdParty)
  --dss-path DSS_PATH  Explicit path to TI CCS Debug Server Scripting (dss.bat)
  --log-dir LOG_DIR    Custom directory for rotating diagnostic logs
```

---

## Development & Testing

Using [`uv`](https://docs.astral.sh/uv/) or standard `pip`:

```bash
# Install dependencies + dev tools
uv sync --extra dev

# Run full unit, contract, integration, and UI test suite
uv run pytest -q

# Run linter
uv run ruff check src/ tests/
```

---

## Project Structure

```text
JTAG-conn/
├── src/jtagconn/
│   ├── app.py                 # Application bootstrap & CLI parser
│   ├── __main__.py            # Entry point (python -m jtagconn)
│   ├── backend/               # DebugBackend protocol, SimulatedBackend, CcsScriptingBackend, CCXML generator
│   ├── core/                  # Models, Device catalog, TargetManager, WatchService, MemoryService, StackService, Worker
│   ├── symbols/               # ELF/DWARF & TI COFF (.out) parser and fast symbol index
│   ├── persistence/           # JSON session persistence & presets
│   └── ui/                    # PySide6 desktop GUI (MainWindow, Connection, Cores, Watch, Memory, Locals, Logs)
├── packaging/
│   ├── jtagconn.spec          # PyInstaller single-file Windows spec
│   ├── installer.iss          # Inno Setup installer script
│   └── build_windows.ps1      # One-command Windows build script
└── tests/                     # Contract, unit, integration, and UI tests
```
