# Quickstart & Validation Guide

## Prerequisites
- Windows 10/11 x64, Python 3.12
- TI Code Composer Studio 20.x installed (provides probe drivers and the Scripting API)
- For hardware validation: a supported probe + one of F28388D, F28069M, F28M35x/F28M36x, F28P65x
  (e.g., a LaunchPad or controlCARD)

## Setup
```powershell
git clone <repo> JTAG-conn; cd JTAG-conn
py -3.12 -m venv .venv; .venv\Scripts\activate
pip install -e .[dev]
$env:CCS_ROOT = "C:\ti\ccs2000\ccs"   # if not auto-detected
```

## Run without hardware
```powershell
pytest                       # contract, unit, integration, ui (SimulatedBackend)
python -m jtagconn --simulate  # demo UI against simulated dual-core F28388D
```
Expected: all tests pass; UI connects to "SIM F28388D" with cores CPU1, CPU2, CLA1, CM.

## Validation scenarios (hardware)
Run with `pytest -m hw --device F28P65x --probe XDS110` or manually:

| # | Story | Steps | Expected |
|---|-------|-------|----------|
| 1 | US1 | Select `tests/fixtures/blinky_<device>.out`, Connect, Load, Run | progress → verified; LED blinks; state Running |
| 2 | US1 | Unplug board power, Connect | "Target not responding…" error, state Disconnected |
| 3 | US2 | Halt, Resume, Reset | Halted shows PC + function; Running; Halted at reset vector |
| 4 | US3 | Add `g_counter`, `g_ctrl` (struct) while running | values update ~every 500 ms; struct expandable |
| 5 | US3 | Set `g_ctrl.gain = 2.5` while running; enter `abc` | value applied and read back; `abc` rejected, memory unchanged |
| 6 | US4 | Memory at `&g_buffer`, 64 words, hex16 | matches known pattern |
| 7 | US5 | Halt inside `control_loop()` | call stack shows `main → control_loop`; locals shown/editable |
| 8 | US6 | F28388D: load CPU1 & CPU2 images, Run All, halt CPU2 only | CPU1 keeps running; CPU2 locals visible |
| 9 | Edge | Pull USB cable while running | "Connection lost" within 3 s; values marked stale |

See [contracts/ui-commands.md](./contracts/ui-commands.md) and [data-model.md](./data-model.md).
