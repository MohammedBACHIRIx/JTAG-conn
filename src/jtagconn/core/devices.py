from __future__ import annotations

from .models import AddressRange, CoreArch, CoreProfile, DeviceProfile

DEVICE_CATALOG: dict[str, DeviceProfile] = {
    "F28388D": DeviceProfile(
        id="F28388D",
        name="F28388D",
        cores=[
            CoreProfile(
                name="C28xx_CPU1",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master=None,
                supports_realtime=True,
            ),
            CoreProfile(
                name="C28xx_CPU2",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master="C28xx_CPU1",
                supports_realtime=True,
            ),
            CoreProfile(
                name="CLA1_0",
                arch=CoreArch.CLA,
                address_unit_bits=16,
                boot_master="C28xx_CPU1",
                supports_realtime=True,
            ),
            CoreProfile(
                name="CM",
                arch=CoreArch.CortexM4,
                address_unit_bits=8,
                boot_master="C28xx_CPU1",
                supports_realtime=True,
            ),
        ],
        flash_regions=[AddressRange(start=0x080000, end=0x0BFFFF)],
    ),
    "F28069M": DeviceProfile(
        id="F28069M",
        name="F28069M",
        cores=[
            CoreProfile(
                name="C28xx",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master=None,
                supports_realtime=True,
            ),
            CoreProfile(
                name="CLA_0",
                arch=CoreArch.CLA,
                address_unit_bits=16,
                boot_master="C28xx",
                supports_realtime=True,
            ),
        ],
        flash_regions=[AddressRange(start=0x3D8000, end=0x3F7FFF)],
    ),
    "F28M35x": DeviceProfile(
        id="F28M35x",
        name="F28M35x",
        cores=[
            CoreProfile(
                name="Cortex_M3_0",
                arch=CoreArch.CortexM3,
                address_unit_bits=8,
                boot_master=None,
                supports_realtime=True,
            ),
            CoreProfile(
                name="C28xx_0",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master="Cortex_M3_0",
                supports_realtime=True,
            ),
        ],
        flash_regions=[AddressRange(start=0x080000, end=0x0BFFFF)],
    ),
    "F28M36x": DeviceProfile(
        id="F28M36x",
        name="F28M36x",
        cores=[
            CoreProfile(
                name="Cortex_M3_0",
                arch=CoreArch.CortexM3,
                address_unit_bits=8,
                boot_master=None,
                supports_realtime=True,
            ),
            CoreProfile(
                name="C28xx_0",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master="Cortex_M3_0",
                supports_realtime=True,
            ),
        ],
        flash_regions=[AddressRange(start=0x080000, end=0x0BFFFF)],
    ),
    "F28P65x": DeviceProfile(
        id="F28P65x",
        name="F28P65x",
        cores=[
            CoreProfile(
                name="C28xx_CPU1",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master=None,
                supports_realtime=True,
            ),
            CoreProfile(
                name="C28xx_CPU2",
                arch=CoreArch.C28x,
                address_unit_bits=16,
                boot_master="C28xx_CPU1",
                supports_realtime=True,
            ),
            CoreProfile(
                name="CLA1_0",
                arch=CoreArch.CLA,
                address_unit_bits=16,
                boot_master="C28xx_CPU1",
                supports_realtime=True,
            ),
        ],
        flash_regions=[AddressRange(start=0x080000, end=0x0BFFFF)],
    ),
}


def get_device_profile(device_id: str) -> DeviceProfile:
    try:
        return DEVICE_CATALOG[device_id]
    except KeyError as exc:
        raise KeyError(f"Unknown device profile: {device_id}") from exc
