# Contract: UI Commands & Panels (Layer 4 ↔ Layer 2)

UI issues commands to `core` services; results arrive via Qt signals. UI never calls the backend.

## Commands

| Command | Enabled when | Result signal | Safety |
|---------|--------------|---------------|--------|
| Open .out (per core) | always | `imageLoaded(core, ProgramImage)` | read-only |
| Connect | Disconnected/ConnectionLost | `coreStateChanged` | — |
| Disconnect | connected | `coreStateChanged` | — |
| Load | Halted + image selected | `loadProgress(%)`, `loadFinished(ok, err)` | flash confirm dialog if image has FLASH sections |
| Run / Resume | Halted | `coreStateChanged(Running)` | — |
| Halt | Running | `coreStateChanged(Halted, pc, func)` | — |
| Reset | Halted | `coreStateChanged(Halted)` | confirm |
| Run All / Halt All | ≥2 cores connected | `coreStateChanged` × n | — |
| Add watch | image loaded | `watchUpdated(entry)` | read-only |
| Edit watch value | Halted, or Running + realtime | `watchUpdated` (re-read) | validated before write |
| Read memory | connected | `memoryUpdated(view)` | read-only |
| Select stack frame | Halted | `localsUpdated(frame)` | read-only |
| Edit local | Halted | `localsUpdated` | validated before write |
| Set refresh interval | always | — | min 100 ms |

## Main window layout

- Toolbar: probe/device selector, Connect, Load, Run, Halt, Reset, Run All, Halt All
- Left dock: Cores panel (core, state, PC/function, image)
- Center tabs: Watch, Memory
- Right dock: Call Stack + Locals
- Bottom dock: Log
- Status bar: app version | probe | device | active core | image path | state
