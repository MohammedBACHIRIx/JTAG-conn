from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from jtagconn.core.models import Probe, ProbeKind

_PROBE_CONNECTIONS: dict[ProbeKind, str] = {
    ProbeKind.XDS100v2: "TIXDS100v2_Connection",
    ProbeKind.XDS100v3: "TIXDS100v3_Connection",
    ProbeKind.XDS110: "TIXDS110_Connection",
    ProbeKind.XDS200: "TIXDS200_Connection",
    ProbeKind.XDS560v2: "TIXDS560v2u_Connection",
    ProbeKind.ThirdParty: "TIXDS110_Connection",
}

# Minimal device XML ids for supported families. These are best-effort templates;
# CCS may further specialize, but the structure is valid TI target configuration XML.
_DEVICE_XML: dict[str, tuple[str, str]] = {
    # device_id: (platform_xml_id, cpu_xml_id-ish label base)
    "F28388D": ("tms320f28388d", "TMS320F28388D"),
    "F28069M": ("tms320f28069m", "TMS320F28069M"),
    "F28M35x": ("f28m35h52c1", "F28M35H52C1"),
    "F28M36x": ("f28m36p63c2", "F28M36P63C2"),
    "F28P65x": ("tms320f28p650dk9", "TMS320F28P650DK9"),
}


def generate_ccxml(probe: Probe, device_id: str, out_path: Path) -> Path:
    """Generate a valid TI .ccxml XML configuration for the selected probe and device."""
    connection_xml = _PROBE_CONNECTIONS.get(probe.kind, "TIXDS110_Connection")
    platform_id, device_label = _DEVICE_XML.get(device_id, (device_id.lower(), device_id))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    config = ET.Element("configurations", {"XML_version": "1.2", "id": "configurations_0"})
    configuration = ET.SubElement(config, "configuration", {"id": "configuration_0"})
    instance = ET.SubElement(
        configuration,
        "instance",
        {
            "XML_version": "1.2",
            "desc": connection_xml,
            "href": f"connections/{connection_xml}.xml",
            "id": connection_xml,
            "xml": f"{connection_xml}.xml",
            "xmlpath": "connections",
        },
    )
    platform = ET.SubElement(
        instance,
        "platform",
        {
            "XML_version": "1.2",
            "id": "platform_0",
            "desc": device_label,
        },
    )
    device_instance = ET.SubElement(
        platform,
        "instance",
        {
            "XML_version": "1.2",
            "desc": device_label,
            "href": f"devices/{platform_id}.xml",
            "id": platform_id,
            "xml": f"{platform_id}.xml",
            "xmlpath": "devices",
        },
    )
    # Add a generic CPU property placeholder; CCS resolves full core trees from device XML.
    ET.SubElement(
        device_instance,
        "property",
        {"Type": "stringfield", "Value": "true", "id": "SupportDebug"},
    )

    if probe.serial:
        # Attach serial when available (common XDS110 property name)
        ET.SubElement(
            instance,
            "property",
            {"Type": "stringfield", "Value": probe.serial, "id": "Debug Probe Selection"},
        )

    tree = ET.ElementTree(config)
    ET.indent(tree, space="    ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path
