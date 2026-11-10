from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from jtagconn.core.models import CoreSessionConfig, DisplayFormat, Probe, Session


def default_config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "JTAG-conn"
        return Path.home() / "AppData" / "Roaming" / "JTAG-conn"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "jtagconn"
    return Path.home() / ".config" / "jtagconn"


class SessionStore:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.path = self.config_dir / "session.jtagc.json"

    def load(self) -> Session:
        if not self.path.exists():
            return Session()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return Session()
        try:
            # Normalize core watch_expressions tuples stored as JSON lists
            cores_in = data.get("cores") or {}
            cores_out: dict[str, CoreSessionConfig] = {}
            for core, cfg in cores_in.items():
                watches = []
                for item in (cfg or {}).get("watch_expressions", []):
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        expr, fmt = item[0], item[1]
                        try:
                            fmt_enum = fmt if isinstance(fmt, DisplayFormat) else DisplayFormat(fmt)
                        except Exception:  # noqa: BLE001
                            fmt_enum = DisplayFormat.natural
                        watches.append((str(expr), fmt_enum))
                cores_out[core] = CoreSessionConfig(
                    image_path=(cfg or {}).get("image_path"),
                    watch_expressions=watches,
                )
            probe_data = data.get("probe")
            probe = Probe.model_validate(probe_data) if probe_data else None
            refresh = int(data.get("refresh_interval_ms", 500))
            refresh = max(refresh, 100)
            return Session(
                probe=probe,
                device=str(data.get("device", "F28388D")),
                ccxml_path=data.get("ccxml_path"),
                cores=cores_out,
                refresh_interval_ms=refresh,
                recent_files=list(data.get("recent_files") or []),
            )
        except Exception:  # noqa: BLE001
            return Session()

    def save(self, session: Session) -> Path:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Enforce minimum refresh interval
        session.refresh_interval_ms = max(session.refresh_interval_ms, 100)
        data = session.model_dump(mode="json")
        # Ensure watch_expressions serialized as [expr, fmt]
        cores_ser: dict[str, dict] = {}
        for core, cfg in session.cores.items():
            cores_ser[core] = {
                "image_path": cfg.image_path,
                "watch_expressions": [
                    [expr, fmt.value if isinstance(fmt, DisplayFormat) else str(fmt)]
                    for expr, fmt in cfg.watch_expressions
                ],
            }
        data["cores"] = cores_ser
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return self.path

    def add_recent_file(self, session: Session, path: str, max_items: int = 10) -> Session:
        p = str(path)
        recent = [r for r in session.recent_files if r != p]
        recent.insert(0, p)
        session.recent_files = recent[: max(1, int(max_items))]
        return session
