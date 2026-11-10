from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProbeKind(str, Enum):
    XDS100v2 = "XDS100v2"
    XDS100v3 = "XDS100v3"
    XDS110 = "XDS110"
    XDS200 = "XDS200"
    XDS560v2 = "XDS560v2"
    ThirdParty = "ThirdParty"


class Probe(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ProbeKind
    serial: str | None = None
    description: str


class CoreArch(str, Enum):
    C28x = "C28x"
    CLA = "CLA"
    CortexM3 = "CortexM3"
    CortexM4 = "CortexM4"


class AddressRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int
    end: int


class CoreProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    arch: CoreArch
    address_unit_bits: int
    boot_master: str | None = None
    supports_realtime: bool = True


class DeviceProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    cores: list[CoreProfile]
    flash_regions: list[AddressRange]


class CoreState(str, Enum):
    Disconnected = "Disconnected"
    Halted = "Halted"
    Running = "Running"
    ConnectionLost = "ConnectionLost"


class ImageFormat(str, Enum):
    ELF = "ELF"
    COFF = "COFF"


class MemoryRegionKind(str, Enum):
    RAM = "RAM"
    FLASH = "FLASH"


class Section(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    address: int
    size: int
    region: MemoryRegionKind
    data: bytes = b""


class TypeKind(str, Enum):
    base = "base"
    enum = "enum"
    pointer = "pointer"
    array = "array"
    struct = "struct"
    union = "union"
    bitfield = "bitfield"
    typedef = "typedef"


class TypeInfo(BaseModel):
    name: str
    kind: TypeKind
    bit_size: int
    signed: bool = False
    float_type: bool = False
    enum_values: dict[str, int] = Field(default_factory=dict)
    fields: dict[str, tuple[int, TypeInfo]] = Field(default_factory=dict)
    element_type: TypeInfo | None = None
    length: int = 0


class SymbolScope(str, Enum):
    global_ = "global_"
    static = "static"


class Symbol(BaseModel):
    name: str
    address: int
    size: int
    type_info: TypeInfo
    scope: SymbolScope = SymbolScope.global_
    function_end: int | None = None


class ProgramImage(BaseModel):
    path: str
    mtime: float
    format: ImageFormat
    entry_point: int
    sections: list[Section]
    has_debug_info: bool
    target_device: str | None = None
    symbols: list[Symbol] = Field(default_factory=list)


class DisplayFormat(str, Enum):
    natural = "natural"
    hex = "hex"
    dec = "dec"
    bin = "bin"


class ValueStatus(str, Enum):
    current = "current"
    stale = "stale"
    error = "error"
    not_found = "not_found"
    unavailable = "unavailable"


class ValueNode(BaseModel):
    name: str
    expression: str
    type_name: str
    raw_value: int | float | str | None
    display_value: str
    status: ValueStatus = ValueStatus.current
    children: list[ValueNode] = Field(default_factory=list)


class WatchEntry(BaseModel):
    expression: str
    core: str
    format: DisplayFormat = DisplayFormat.natural
    value: ValueNode | None = None
    status: ValueStatus = ValueStatus.current
    updated_at: float = 0.0


class StackFrame(BaseModel):
    index: int
    function: str
    pc: int
    locals: list[ValueNode] = Field(default_factory=list)


class MemoryFormat(str, Enum):
    hex16 = "hex16"
    hex32 = "hex32"
    int16 = "int16"
    uint16 = "uint16"
    int32 = "int32"
    uint32 = "uint32"
    float32 = "float32"


class MemoryView(BaseModel):
    core: str
    start_expr: str
    start_address: int
    length: int
    format: MemoryFormat = MemoryFormat.hex16
    data: list[int] = Field(default_factory=list)
    status: ValueStatus = ValueStatus.current


class CoreSessionConfig(BaseModel):
    image_path: str | None = None
    watch_expressions: list[tuple[str, DisplayFormat]] = Field(default_factory=list)


class Session(BaseModel):
    probe: Probe | None = None
    device: str = "F28388D"
    ccxml_path: str | None = None
    cores: dict[str, CoreSessionConfig] = Field(default_factory=dict)
    refresh_interval_ms: int = 500
    recent_files: list[str] = Field(default_factory=list)


# Resolve forward references for recursive models
TypeInfo.model_rebuild()
Symbol.model_rebuild()
ProgramImage.model_rebuild()
ValueNode.model_rebuild()
WatchEntry.model_rebuild()
StackFrame.model_rebuild()
MemoryView.model_rebuild()
CoreSessionConfig.model_rebuild()
Session.model_rebuild()
