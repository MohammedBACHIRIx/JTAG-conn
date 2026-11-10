from __future__ import annotations

import struct
from pathlib import Path


def create_sample_elf_out(
    path: Path,
    entry: int = 0x080000,
    flash: bool = True,
    symbols: dict[str, tuple[int, int]] | None = None,
) -> Path:
    """Construct a valid minimal 32-bit little-endian ELF .out file.

    Includes .text/.data sections and .symtab/.strtab symbol table readable by pyelftools.
    """
    if symbols is None:
        symbols = {"main": (entry, 0x20), "g_counter": (0x00C000, 0x2)}

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Section layout:
    # [ELF hdr][shdrs...][.text][.data][.shstrtab][.strtab][.symtab]
    ehdr_size = 52
    shentsize = 40
    shnum = 7  # NULL, .text, .data, .shstrtab, .strtab, .symtab, (none extra) -> 7
    shoff = ehdr_size

    shstrtab_names = b"\x00.text\x00.data\x00.shstrtab\x00.strtab\x00.symtab\x00"
    # symbol string table: null, then symbol names
    strtab = b"\x00"
    sym_name_offsets: dict[str, int] = {}
    for name in symbols:
        sym_name_offsets[name] = len(strtab)
        strtab += name.encode("ascii") + b"\x00"

    # sections data
    text_data = b"\x00\x01\x02\x03" * 16  # 64 bytes
    data_addr = 0x00C000
    data_data = b"\x10\x00\x20\x00"

    # offsets
    off = shoff + shentsize * shnum
    text_off = off
    off += len(text_data)
    data_off = off
    off += len(data_data)
    shstrtab_off = off
    off += len(shstrtab_names)
    strtab_off = off
    off += len(strtab)

    # symtab must be aligned to 4
    if off % 4:
        pad = 4 - (off % 4)
        strtab += b"\x00" * pad
        off += pad
        # adjust not necessary except offset moves; simpler rebuild
    # rebuild to be safe
    off = shoff + shentsize * shnum
    text_off = off
    off += len(text_data)
    data_off = off
    off += len(data_data)
    shstrtab_off = off
    off += len(shstrtab_names)
    strtab_off = off
    off += len(strtab)
    if off % 4:
        strtab += b"\x00" * (4 - (off % 4))
        off = strtab_off + len(strtab)
    symtab_off = off

    # build symbols: undef + provided
    # Elf32_Sym: st_name(4), st_value(4), st_size(4), st_info(1), st_other(1), st_shndx(2)
    def pack_sym(name_off: int, value: int, size: int, info: int, shndx: int) -> bytes:
        return struct.pack("<IIIBBH", name_off, value & 0xFFFFFFFF, size & 0xFFFFFFFF, info, 0, shndx)

    symtab = b""
    symtab += pack_sym(0, 0, 0, 0, 0)  # STN_UNDEF
    for name, (addr, size) in symbols.items():
        # STB_GLOBAL(1)<<4 | STT_OBJECT(1) for data-like, STT_FUNC(2) for low addresses/text-ish
        stt = 2 if addr == entry or name == "main" else 1
        st_info = (1 << 4) | stt
        shndx = 1 if addr >= entry else 2
        symtab += pack_sym(sym_name_offsets[name], addr, size, st_info, shndx)

    off += len(symtab)

    # name offsets in shstrtab
    def shname(n: str) -> int:
        key = f".{n}\x00".encode("ascii") if not n.startswith(".") else f"{n}\x00".encode("ascii")
        # our table starts with \x00.text...
        full = b"\x00.text\x00.data\x00.shstrtab\x00.strtab\x00.symtab\x00"
        return full.index(key)

    # section headers
    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHF_WRITE = 0x1
    SHF_ALLOC = 0x2
    SHF_EXECINSTR = 0x4

    def pack_shdr(name, sh_type, flags, addr, offset, size, link, info, addralign, entsize):
        return struct.pack(
            "<IIIIIIIIII",
            name,
            sh_type,
            flags,
            addr & 0xFFFFFFFF,
            offset,
            size,
            link,
            info,
            addralign,
            entsize,
        )

    shdrs = b""
    # 0: NULL
    shdrs += pack_shdr(0, SHT_NULL, 0, 0, 0, 0, 0, 0, 0, 0)
    # 1: .text
    shdrs += pack_shdr(
        shname("text"), SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR, entry, text_off, len(text_data), 0, 0, 4, 0
    )
    # 2: .data
    shdrs += pack_shdr(
        shname("data"), SHT_PROGBITS, SHF_ALLOC | SHF_WRITE, data_addr, data_off, len(data_data), 0, 0, 2, 0
    )
    # 3: .shstrtab
    shdrs += pack_shdr(
        shname("shstrtab"), SHT_STRTAB, 0, 0, shstrtab_off, len(shstrtab_names), 0, 0, 1, 0
    )
    # 4: .strtab
    shdrs += pack_shdr(
        shname("strtab"), SHT_STRTAB, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0
    )
    # 5: .symtab
    shdrs += pack_shdr(
        shname("symtab"), SHT_SYMTAB, 0, 0, symtab_off, len(symtab), 4, 1, 4, 16
    )
    # pad to shnum
    while len(shdrs) < shentsize * shnum:
        shdrs += pack_shdr(0, SHT_NULL, 0, 0, 0, 0, 0, 0, 0, 0)

    # ELF header
    e_ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8  # 32-bit, little, v1
    e_type = 2  # ET_EXEC
    e_machine = 40  # EM_ARM (generic enough) / could vary; pyelftools reads fine
    e_version = 1
    e_entry = entry
    e_phoff = 0
    e_shoff = shoff
    e_flags = 0
    e_ehsize = ehdr_size
    e_phentsize = 0
    e_phnum = 0
    e_shentsize = shentsize
    e_shnum = shnum
    e_shstrndx = 3

    ehdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        e_ident,
        e_type,
        e_machine,
        e_version,
        e_entry & 0xFFFFFFFF,
        e_phoff,
        e_shoff,
        e_flags,
        e_ehsize,
        e_phentsize,
        e_phnum,
        e_shentsize,
        e_shnum,
        e_shstrndx,
    )

    blob = bytearray()
    blob += ehdr
    blob += shdrs
    blob += text_data
    blob += data_data
    blob += shstrtab_names
    blob += strtab
    blob += symtab

    path.write_bytes(bytes(blob))
    return path
