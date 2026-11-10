from __future__ import annotations

from jtagconn.core.models import DeviceProfile, MemoryRegionKind, ProgramImage, Section


class FlashGuard:
    """Detects program sections that would program/erase flash and require confirmation."""

    def requires_confirmation(self, image: ProgramImage, device: DeviceProfile) -> list[Section]:
        """Return all non-empty sections in image overlapping device flash regions.

        A section is considered flash-targeting if it is non-empty and either marked as
        FLASH or its load address range overlaps any of the device's flash_regions.
        """
        flash_ranges = list(device.flash_regions)
        flagged: list[Section] = []
        for sec in image.sections:
            if getattr(sec, "size", 0) <= 0:
                continue
            is_flash = sec.region == MemoryRegionKind.FLASH
            if not is_flash and flash_ranges:
                sec_start = int(sec.address)
                sec_end = sec_start + int(sec.size) - 1
                for fr in flash_ranges:
                    if sec_start <= int(fr.end) and sec_end >= int(fr.start):
                        is_flash = True
                        break
            if is_flash:
                flagged.append(sec)
        return flagged
