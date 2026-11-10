# Data Model: C2000 JTAG Debug Desktop App

## Probe
| Field | Type | Notes |
|-------|------|-------|
| kind | enum | XDS100v2, XDS100v3, XDS110, XDS200, XDS560v2, ThirdParty |
| serial | str? | when enumerable |
| description | str | display name |

## DeviceProfile (catalog, read-only)
| Field | Type | Notes |
|-------|------|-------|
| id | str | `F28388D`, `F28069M`, `F28M35x`, `F28M36x`, `F28P65x` |
| cores | list[CoreProfile] | name, arch (`C28x`/`CLA`/`CortexM3`/`CortexM4`), address unit (16-bit word / byte), boot dependency |
| flash_regions | list[Range] | used by FlashGuard |

## Core
| Field | Type | Notes |
|-------|------|-------|
| name | str | e.g. `C28xx_CPU1`, `CM` |
| state | CoreState | see state machine |
| pc | int? | when halted |
| function | str? | function containing PC |
| image | ProgramImage? | per core |
| realtime_access | bool | live refresh possible |

**CoreState transitions**

```text
Disconnected --connect--> Halted
Halted --run/resume--> Running
Running --halt--> Halted
Halted --reset--> Halted
Halted|Running --link lost--> ConnectionLost
ConnectionLost --reconnect--> Halted
any --disconnect--> Disconnected
```
Actions are enabled only for valid source states (FR-007).

## ProgramImage
| Field | Type | Notes |
|-------|------|-------|
| path, mtime | str, datetime | change detection → "out of date" banner |
| format | enum | ELF, COFF |
| entry_point | int | |
| sections | list[Section] | name, load address, size, region (RAM/FLASH) |
| has_debug_info | bool | |
| target_device | str? | validated against connected device |

## Symbol
| Field | Type | Notes |
|-------|------|-------|
| name | str | |
| address | int | in core address units |
| size | int | in address units |
| type | TypeInfo | |
| scope | enum | global, static |

## TypeInfo
Kinds: `base` (int/uint 16/32/64, float32/64, bool, char), `enum`, `pointer`, `array`, `struct`,
`union`, `bitfield`, `typedef`. Validation: value must parse for kind and fit range; enum accepts
name or number.

## WatchEntry
| Field | Type | Notes |
|-------|------|-------|
| expression | str | symbol name or member path (`ctrl.gain`, `buf[3]`) |
| core | str | |
| format | enum | natural, hex, dec, bin |
| value | Value? | decoded tree |
| status | enum | current, stale, error, not_found, unavailable |
| updated_at | datetime | |

## StackFrame
| Field | Type | Notes |
|-------|------|-------|
| index | int | 0 = top |
| function | str | |
| pc | int | |
| locals | list[WatchEntry] | status `unavailable` when optimized out |

## MemoryView
| Field | Type | Notes |
|-------|------|-------|
| core | str | |
| start | int | address or resolved symbol |
| length | int | address units |
| format | enum | hex16, hex32, int16, uint16, int32, uint32, float32 |
| data | list[int]? | last read |
| status | enum | current, stale, error |

## Session (persisted JSON)
| Field | Type |
|-------|------|
| probe | Probe |
| device | str |
| ccxml_path | str? |
| cores | map core → {image_path, watch: list[WatchEntry(expr, format)]} |
| refresh_interval_ms | int (default 500, min 100) |
| recent_files | list[str] (max 10) |
