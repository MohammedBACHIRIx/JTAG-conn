from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jtagconn.backend.base import DebugBackend
from jtagconn.backend.ccs_scripting import CcsScriptingBackend
from jtagconn.backend.simulated import SimulatedBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.models import Probe, ProbeKind
from jtagconn.persistence.session import SessionStore
from jtagconn.ui._qt import HAS_QT_WIDGETS, QApplication
from jtagconn.ui.main_window import MainWindow


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jtagconn", description="JTAG-conn C2000 JTAG Debug Desktop App")
    parser.add_argument("--simulate", action="store_true", help="Run with SimulatedBackend")
    parser.add_argument("--device", dest="device", help="Target device ID (e.g. F28388D)")
    parser.add_argument("--image", dest="image", help="Path to .out image to preselect")
    parser.add_argument(
        "--headless-check",
        action="store_true",
        help="Initialize MainWindow in simulated mode, verify startup, and exit 0",
    )
    return parser


def create_backend(args: argparse.Namespace, logger: OperationLogger) -> DebugBackend:
    if args.simulate or args.headless_check:
        return SimulatedBackend(logger=logger)
    return CcsScriptingBackend(logger=logger)


def _ensure_qapp() -> QApplication | None:
    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logger = OperationLogger()
    backend = create_backend(args, logger)
    session_store = SessionStore()

    # Headless/startup verification path
    if args.headless_check:
        try:
            if not isinstance(backend, SimulatedBackend):
                backend = SimulatedBackend(logger=logger)
            window = MainWindow(backend=backend, session_store=session_store, logger=logger)
            # basic startup verification in simulated mode
            device = args.device or "F28388D"
            probe = Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")
            cores = window.target_manager.configure(probe, device, None)
            window.cores_panel.set_cores(cores)
            if cores:
                window.set_active_core(cores[0])
            if args.image:
                window.connection_panel.set_image_path(str(Path(args.image)))
            # exercise a simple state update path
            window._update_status_bar()
            window._update_connection_actions()
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Headless check failed: {exc}", file=sys.stderr)
            return 1

    # GUI/simulated interactive launch path
    _ensure_qapp()
    window = MainWindow(backend=backend, session_store=session_store, logger=logger)

    # Optional preconfiguration
    try:
        if args.device:
            try:
                window.connection_panel.device_selector.setCurrentText(args.device)
            except Exception:  # noqa: BLE001, S110
                pass
        if args.image:
            window.connection_panel.set_image_path(str(Path(args.image)))
        if args.simulate:
            # Auto-configure for convenience in simulated mode
            probe = Probe(kind=ProbeKind.XDS110, serial="SIM0001", description="Simulated XDS110")
            device = args.device or window.connection_panel.selected_device() or "F28388D"
            cores = window.target_manager.configure(probe, device, None)
            window.cores_panel.set_cores(cores)
            if cores:
                window.set_active_core(cores[0])
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        window.show()
    except Exception:  # noqa: BLE001, S110
        pass

    if HAS_QT_WIDGETS:
        try:
            app = QApplication.instance()
            if app is not None:
                return int(app.exec())
        except Exception:  # noqa: BLE001, S110
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
