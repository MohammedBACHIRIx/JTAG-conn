from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from jtagconn import __version__
from jtagconn.backend.base import DebugBackend
from jtagconn.core.logging_service import OperationLogger
from jtagconn.core.memory_service import MemoryService
from jtagconn.core.models import (
    CoreSessionConfig,
    CoreState,
    DisplayFormat,
    Probe,
    ProbeKind,
    Section,
    Session,
)
from jtagconn.core.stack_service import StackService
from jtagconn.core.target_manager import TargetManager
from jtagconn.core.watch_service import WatchService
from jtagconn.persistence.session import SessionStore

from ._qt import (
    HAS_QT_WIDGETS,
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    Qt,
    QTabWidget,
    QTimer,
)
from .connection_panel import ConnectionPanel
from .cores_panel import CoresPanel
from .locals_view import LocalsView
from .log_view import LogView
from .memory_view import MemoryViewWidget
from .watch_view import WatchView


class MainWindow(QMainWindow):
    """Main application window assembling panels, services, and session persistence."""

    def __init__(
        self,
        backend: DebugBackend,
        session_store: SessionStore | None = None,
        logger: OperationLogger | None = None,
        confirm_flash_handler: Callable[[list[Section]], bool] | None = None,
        parent: Any = None,
    ) -> None:
        if HAS_QT_WIDGETS:
            from ._qt import QApplication

            if QApplication.instance() is None:
                QApplication([])
        super().__init__(parent)
        self.backend = backend
        self.logger = logger or getattr(backend, "logger", None) or OperationLogger()
        self.session_store = session_store or SessionStore()
        self.confirm_flash_handler = confirm_flash_handler or self._default_confirm_flash_handler

        # Services
        self.target_manager = TargetManager(self.backend, logger=self.logger)
        self.watch_service = WatchService(self.backend, self.target_manager)
        self.memory_service = MemoryService(self.backend, self.target_manager)
        self.stack_service = StackService(self.backend, self.target_manager)

        # Panels / views
        self.connection_panel = ConnectionPanel(self)
        self.cores_panel = CoresPanel(self)
        self.watch_view = WatchView(self)
        self.memory_view = MemoryViewWidget(self)
        self.locals_view = LocalsView(self)
        self.log_view = LogView(self.logger, self)

        self.center_tabs = QTabWidget(self)
        try:
            self.center_tabs.addTab(self.watch_view, "Watch")
            self.center_tabs.addTab(self.memory_view, "Memory")
        except Exception:  # noqa: BLE001, S110
            pass

        self._status_bar = QStatusBar(self)
        try:
            self.setStatusBar(self._status_bar)
        except Exception:  # noqa: BLE001, S110
            pass

        self._assemble_layout()

        # State
        self.session: Session = Session()
        self._active_core: str | None = None
        self._selected_image_path: str | None = None
        self._connected_core_names: list[str] = []
        self._window_minimized = False

        # Polling timer for watch refresh
        self.watch_timer = QTimer(self)
        try:
            self.watch_timer.setInterval(500)
            self.watch_timer.timeout.connect(self._on_watch_timer)
        except Exception:  # noqa: BLE001, S110
            pass

        self._wire_signals()
        self._apply_session(self.session_store.load())
        self._update_status_bar()
        self._update_connection_actions()
        self._update_watch_polling_state()

    # --- layout ---
    def _assemble_layout(self) -> None:
        try:
            self.setWindowTitle("JTAG-conn")
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.setCentralWidget(self.center_tabs)
        except Exception:  # noqa: BLE001, S110
            pass

        # Left dock: connection + cores
        self.left_dock = QDockWidget("Connection / Cores", self)
        try:
            self.left_dock.setWidget(self.cores_panel)
        except Exception:  # noqa: BLE001, S110
            pass
        # In fallback/headless we can't easily nest both; expose connection panel too
        self.connection_dock = QDockWidget("Connection", self)
        try:
            self.connection_dock.setWidget(self.connection_panel)
        except Exception:  # noqa: BLE001, S110
            pass

        self.right_dock = QDockWidget("Call Stack + Locals", self)
        try:
            self.right_dock.setWidget(self.locals_view)
        except Exception:  # noqa: BLE001, S110
            pass

        self.bottom_dock = QDockWidget("Log", self)
        try:
            self.bottom_dock.setWidget(self.log_view)
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            left = getattr(Qt, "LeftDockWidgetArea", 0x1)
            right = getattr(Qt, "RightDockWidgetArea", 0x2)
            bottom = getattr(Qt, "BottomDockWidgetArea", 0x8)
            self.addDockWidget(left, self.connection_dock)
            self.addDockWidget(left, self.left_dock)
            self.addDockWidget(right, self.right_dock)
            self.addDockWidget(bottom, self.bottom_dock)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- wiring ---
    def _wire_signals(self) -> None:
        cp = self.connection_panel
        self._connect_signal(cp.connect_button, "clicked", self.on_connect_clicked)
        self._connect_signal(cp.disconnect_button, "clicked", self.on_disconnect_clicked)
        self._connect_signal(cp.load_button, "clicked", self.on_load_clicked)
        self._connect_signal(cp.run_button, "clicked", self.on_run_clicked)
        self._connect_signal(cp.halt_button, "clicked", self.on_halt_clicked)
        self._connect_signal(cp.reset_button, "clicked", self.on_reset_clicked)
        self._connect_signal(cp.run_all_button, "clicked", self.on_run_all_clicked)
        self._connect_signal(cp.halt_all_button, "clicked", self.on_halt_all_clicked)
        self._connect_signal(cp.image_path_input, "textChanged", self._on_image_path_changed)
        self._connect_signal(cp.refresh_interval_spinbox, "valueChanged", self._on_refresh_interval_changed)

        # Cores panel
        try:
            self.cores_panel.coreSelected.connect(self.set_active_core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._connect_signal(self.cores_panel.connect_core_button, "clicked", self.on_connect_core_clicked)
        self._connect_signal(self.cores_panel.disconnect_core_button, "clicked", self.on_disconnect_core_clicked)

        # Watch view
        self._connect_signal(self.watch_view.add_button, "clicked", self.on_add_watch_clicked)
        self._connect_signal(self.watch_view.remove_button, "clicked", self.on_remove_watch_clicked)
        self._connect_signal(self.watch_view.apply_edit_button, "clicked", self.on_apply_watch_edit_clicked)
        self._connect_signal(self.watch_view.format_selector, "currentTextChanged", self._on_watch_format_changed)

        # Memory view
        self._connect_signal(self.memory_view.refresh_button, "clicked", self.on_memory_refresh_clicked)

        # Locals view
        self._connect_signal(self.locals_view.apply_button, "clicked", self.on_apply_local_edit_clicked)

        # Center tab visibility changes (pause polling when Watch tab hidden)
        self._connect_signal(self.center_tabs, "currentChanged", lambda *_: self._update_watch_polling_state())

        # Target manager signals
        self._connect_signal(self.target_manager, "coreStateChanged", self._on_core_state_changed)
        self._connect_signal(self.target_manager, "coreHaltedInfo", self._on_core_halted_info)
        self._connect_signal(self.target_manager, "imageLoaded", self._on_image_loaded)
        self._connect_signal(self.target_manager, "loadProgress", self._on_load_progress)
        self._connect_signal(self.target_manager, "loadFinished", self._on_load_finished)
        self._connect_signal(self.target_manager, "errorOccurred", self._on_tm_error)
        self._connect_signal(self.target_manager, "connectionLost", self._on_connection_lost)

        # Watch updates
        self._connect_signal(self.watch_service, "watchUpdated", self._on_watch_updated)

    @staticmethod
    def _connect_signal(obj: Any, signal_name: str, slot: Callable[..., Any]) -> None:
        try:
            sig = getattr(obj, signal_name)
            if hasattr(sig, "connect"):
                sig.connect(slot)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- session ---
    def _apply_session(self, session: Session) -> None:
        self.session = session
        try:
            self.connection_panel.set_recent_files(list(session.recent_files))
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.connection_panel.set_refresh_interval_ms(int(session.refresh_interval_ms))
            self.watch_timer.setInterval(max(100, int(session.refresh_interval_ms)))
        except Exception:  # noqa: BLE001, S110
            pass
        if session.device:
            try:
                self.connection_panel.device_selector.setCurrentText(session.device)
            except Exception:  # noqa: BLE001, S110
                pass

    def persist_session(self) -> Path | None:
        try:
            # update session fields
            self.session.device = self.connection_panel.selected_device()
            self.session.refresh_interval_ms = self.connection_panel.refresh_interval_ms()
            self.session.recent_files = list(getattr(self.session, "recent_files", []))
            # cores config
            for core in self.target_manager.cores() or self._connected_core_names:
                cfg = self.session.cores.get(core) or CoreSessionConfig()
                img = self.target_manager.image_for_core(core)
                if img is not None:
                    cfg.image_path = img.path
                elif self._active_core == core and self._selected_image_path:
                    cfg.image_path = self._selected_image_path
                # persist watch expressions for core
                try:
                    entries = self.watch_service.entries(core)
                    cfg.watch_expressions = [(e.expression, e.format) for e in entries]
                except Exception:  # noqa: BLE001, S110
                    pass
                self.session.cores[core] = cfg
            return self.session_store.save(self.session)
        except Exception:  # noqa: BLE001
            return None

    # --- flash confirmation ---
    def _default_confirm_flash_handler(self, sections: list[Section]) -> bool:
        if HAS_QT_WIDGETS:
            try:
                names = ", ".join(s.name for s in sections[:5])
                msg = f"Program contains flash sections ({names}). Proceed with flash programming?"
                ans = QMessageBox.question(self, "Confirm Flash Programming", msg)
                yes = getattr(QMessageBox, "Yes", 0x4000)
                return ans == yes
            except Exception:  # noqa: BLE001
                return False
        # Headless fallback default: refuse unless explicitly provided
        return False

    # --- actions / handlers ---
    def _current_probe(self) -> Probe:
        # Prefer session probe if present; otherwise default to simulated XDS110
        if self.session.probe is not None:
            return self.session.probe
        # try to map selector text to ProbeKind
        txt = self.connection_panel.selected_probe_text()
        kind = ProbeKind.XDS110
        for k in ProbeKind:
            if k.value == txt or txt == k.name:
                kind = k
                break
        return Probe(kind=kind, serial="SIM0001", description=f"Simulated {kind.value}")

    def _ensure_configured(self) -> list[str]:
        device_id = self.connection_panel.selected_device()
        probe = self._current_probe()
        cores = self.target_manager.configure(probe, device_id, None)
        self._connected_core_names = list(cores)
        self.cores_panel.set_cores(cores)
        if not self._active_core and cores or self._active_core not in cores and cores:
            self.set_active_core(cores[0])
        self._update_connection_actions()
        self._update_status_bar()
        return cores

    def on_connect_clicked(self) -> None:
        try:
            cores = self.target_manager.cores() or self._ensure_configured()
            core = self.active_core() or (cores[0] if cores else None)
            if core:
                self.target_manager.connect_core(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()
        self._update_watch_polling_state()

    def on_connect_core_clicked(self) -> None:
        try:
            core = self.cores_panel.active_core() or self.active_core()
            if not self.target_manager.cores():
                self._ensure_configured()
            if core:
                self.target_manager.connect_core(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()

    def on_disconnect_clicked(self) -> None:
        try:
            core = self.active_core()
            if core:
                self.target_manager.disconnect_core(core)
            else:
                self.target_manager.disconnect_all()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()
        self._refresh_stack_and_locals()

    def on_disconnect_core_clicked(self) -> None:
        try:
            core = self.cores_panel.active_core() or self.active_core()
            if core:
                self.target_manager.disconnect_core(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()

    def on_load_clicked(self) -> None:
        try:
            core = self.active_core()
            if not core:
                return
            path = self.connection_panel.image_path()
            if path:
                self.target_manager.select_image(core, Path(path))
                self.session_store.add_recent_file(self.session, path)
                self.connection_panel.set_recent_files(list(self.session.recent_files))
            ok = self.target_manager.load_program(core, confirm_flash_callback=self.confirm_flash_handler)
            if ok:
                self._update_symbol_index_for_active_core()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()

    def on_run_clicked(self) -> None:
        try:
            core = self.active_core()
            if core:
                self.target_manager.run(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._refresh_stack_and_locals()
        self.refresh_watch_now()

    def on_halt_clicked(self) -> None:
        try:
            core = self.active_core()
            if core:
                self.target_manager.halt(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._refresh_stack_and_locals()
        self.refresh_watch_now()

    def on_reset_clicked(self) -> None:
        try:
            core = self.active_core()
            if core:
                self.target_manager.reset(core)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._refresh_stack_and_locals()
        self.refresh_watch_now()

    def on_run_all_clicked(self) -> None:
        try:
            self.target_manager.run_all()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._refresh_stack_and_locals()
        self.refresh_watch_now()

    def on_halt_all_clicked(self) -> None:
        try:
            self.target_manager.halt_all()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._refresh_stack_and_locals()
        self.refresh_watch_now()

    # --- image/active core ---
    def _on_image_path_changed(self, text: str) -> None:
        self._selected_image_path = str(text) if text else None
        self._update_connection_actions()

    def set_active_core(self, core: str | None) -> None:
        if not core:
            return
        self._active_core = core
        try:
            self.cores_panel.set_active_core(core)
        except Exception:  # noqa: BLE001, S110
            pass
        # restore core session config if present
        cfg = self.session.cores.get(core)
        if cfg:
            if cfg.image_path:
                try:
                    self.connection_panel.set_image_path(cfg.image_path)
                except Exception:  # noqa: BLE001, S110
                    pass
                self._selected_image_path = cfg.image_path
            # restore watches
            for expr, fmt in list(getattr(cfg, "watch_expressions", []) or []):
                try:
                    self.watch_service.add_watch(core, expr, fmt)
                except Exception:  # noqa: BLE001, S110
                    pass
        self._update_symbol_index_for_active_core()
        self._update_connection_actions()
        self._update_status_bar()
        self.refresh_watch_now(force_emit=True)
        self._refresh_stack_and_locals()
        self.on_memory_refresh_clicked()

    def active_core(self) -> str | None:
        if self._active_core:
            return self._active_core
        try:
            c = self.cores_panel.active_core()
            if c:
                self._active_core = c
                return c
        except Exception:  # noqa: BLE001, S110
            pass
        cores = self.target_manager.cores()
        return cores[0] if cores else None

    def _update_symbol_index_for_active_core(self) -> None:
        core = self.active_core()
        if not core:
            return
        symbols: list[Any] = []
        img = self.target_manager.image_for_core(core)
        if img is not None:
            symbols = list(getattr(img, "symbols", []) or [])
        else:
            try:
                symbols = list(self.backend.symbols(core))
            except Exception:  # noqa: BLE001
                symbols = []
        try:
            self.watch_view.set_symbol_index(symbols)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- watch actions/polling ---
    def on_add_watch_clicked(self) -> None:
        core = self.active_core()
        if not core:
            return
        expr = ""
        try:
            expr = self.watch_view.search_input.text().strip()
        except Exception:  # noqa: BLE001
            expr = ""
        if not expr:
            return
        fmt = DisplayFormat.natural
        try:
            fmt = DisplayFormat(self.watch_view.format_selector.currentText())
        except Exception:  # noqa: BLE001
            fmt = DisplayFormat.natural
        try:
            self.watch_service.add_watch(core, expr, fmt)
            self.refresh_watch_now(force_emit=True)
            self.watch_view.clear_edit_error()
        except Exception as exc:  # noqa: BLE001
            try:
                self.watch_view.set_edit_error(str(exc))
            except Exception:  # noqa: BLE001, S110
                pass

    def on_remove_watch_clicked(self) -> None:
        core = self.active_core()
        if not core:
            return
        expr = ""
        try:
            expr = self.watch_view.search_input.text().strip()
        except Exception:  # noqa: BLE001
            expr = ""
        if not expr:
            return
        try:
            self.watch_service.remove_watch(core, expr)
            self.watch_view.remove_expression(expr)
        except Exception:  # noqa: BLE001, S110
            pass

    def on_apply_watch_edit_clicked(self) -> None:
        core = self.active_core()
        if not core:
            return
        try:
            expr = self.watch_view.search_input.text().strip()
            new_value = self.watch_view.edit_value_input.text()
        except Exception:  # noqa: BLE001
            return
        if not expr:
            return
        try:
            self.watch_service.modify_value(core, expr, new_value)
            self.watch_view.clear_edit_error()
            self.refresh_watch_now(force_emit=True)
        except Exception as exc:  # noqa: BLE001
            try:
                self.watch_view.set_edit_error(str(exc))
            except Exception:  # noqa: BLE001, S110
                pass

    def _on_watch_format_changed(self, *args: Any) -> None:
        core = self.active_core()
        if not core:
            return
        expr = ""
        try:
            expr = self.watch_view.search_input.text().strip()
            fmt = DisplayFormat(self.watch_view.format_selector.currentText())
        except Exception:  # noqa: BLE001
            return
        if not expr:
            return
        try:
            self.watch_service.set_format(core, expr, fmt)
            self.refresh_watch_now(force_emit=True)
        except Exception:  # noqa: BLE001, S110
            pass

    def _on_watch_updated(self, core: str, changed_entries: list[Any]) -> None:
        if core != self.active_core():
            return
        try:
            self.watch_view.upsert_entries(list(changed_entries))
        except Exception:  # noqa: BLE001, S110
            pass

    def refresh_watch_now(self, force_emit: bool = False) -> list[Any]:
        core = self.active_core()
        if not core:
            return []
        try:
            return self.watch_service.refresh(core, force_emit=force_emit)
        except Exception:  # noqa: BLE001
            return []

    def _on_watch_timer(self) -> None:
        # Guard: 0 work when not allowed (paused, hidden, minimized)
        if not self._watch_polling_allowed():
            return
        self.refresh_watch_now(force_emit=False)

    def _is_watch_tab_active(self) -> bool:
        try:
            idx = self.center_tabs.currentIndex()
            w = self.center_tabs.widget(idx)
            return w is self.watch_view
        except Exception:  # noqa: BLE001
            return True

    def _is_window_minimized(self) -> bool:
        try:
            if hasattr(self, "isMinimized"):
                return bool(self.isMinimized())
        except Exception:  # noqa: BLE001, S110
            pass
        return bool(self._window_minimized)

    def _watch_polling_allowed(self) -> bool:
        if self._is_window_minimized():
            return False
        if not self._is_watch_tab_active():
            return False
        core = self.active_core()
        # if paused in service, respect it
        return bool(core)

    def _update_watch_polling_state(self) -> None:
        allowed = self._watch_polling_allowed()
        try:
            self.watch_service.set_polling_paused(not allowed)
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            if allowed:
                if not self.watch_timer.isActive():
                    self.watch_timer.start(max(100, self.connection_panel.refresh_interval_ms()))
            else:
                if self.watch_timer.isActive():
                    self.watch_timer.stop()
        except Exception:  # noqa: BLE001, S110
            pass

    def showMinimized(self) -> None:
        self._window_minimized = True
        try:
            super().showMinimized()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_watch_polling_state()

    def showNormal(self) -> None:
        self._window_minimized = False
        try:
            fn = getattr(super(), "showNormal", None)
            if callable(fn):
                fn()
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_watch_polling_state()

    def set_watch_tab_visible(self, visible: bool) -> None:
        """Helper for tests/headless to simulate tab visibility changes."""
        try:
            if visible:
                # set to watch tab index
                for i in range(self.center_tabs.count()):
                    if self.center_tabs.widget(i) is self.watch_view:
                        self.center_tabs.setCurrentIndex(i)
                        break
            else:
                # switch to memory tab if available
                for i in range(self.center_tabs.count()):
                    if self.center_tabs.widget(i) is self.memory_view:
                        self.center_tabs.setCurrentIndex(i)
                        break
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_watch_polling_state()

    # --- memory ---
    def on_memory_refresh_clicked(self) -> None:
        core = self.active_core()
        if not core:
            return
        try:
            start_expr = self.memory_view.start_expr_input.text()
            length = int(self.memory_view.length_input.value())
            fmt = self.memory_view.selected_format()
        except Exception:  # noqa: BLE001
            return
        try:
            view = self.memory_service.read_view(core, start_expr, length, fmt)
            cells = self.memory_service.format_memory_cells(view)
            self.memory_view.set_view(view, cells)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- locals/stack ---
    def _refresh_stack_and_locals(self) -> None:
        core = self.active_core()
        if not core:
            try:
                self.locals_view.clear()
            except Exception:  # noqa: BLE001, S110
                pass
            return
        try:
            frames = self.stack_service.refresh_stack(core)
            self.locals_view.set_callstack(frames)
        except Exception:  # noqa: BLE001
            try:
                self.locals_view.clear()
            except Exception:  # noqa: BLE001, S110
                pass

    def on_apply_local_edit_clicked(self) -> None:
        core = self.active_core()
        if not core:
            return
        try:
            frame_idx = self.locals_view.selected_frame_index() or 0
            name = self.locals_view.edit_name_input.text().strip()
            new_val = self.locals_view.edit_value_input.text()
            if not name:
                return
            self.stack_service.modify_local(core, int(frame_idx), name, new_val)
            self.locals_view.set_error("")
            self._refresh_stack_and_locals()
        except Exception as exc:  # noqa: BLE001
            try:
                self.locals_view.set_error(str(exc))
            except Exception:  # noqa: BLE001, S110
                pass

    # --- target manager event handlers ---
    def _on_core_state_changed(self, core: str, state: CoreState) -> None:
        try:
            self.cores_panel.update_core_state(core, state)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()
        self._update_watch_polling_state()
        self._refresh_stack_and_locals()
        if core == self.active_core():
            self.refresh_watch_now(force_emit=True)

    def _on_core_halted_info(self, core: str, pc: int, function_name: str | None) -> None:
        try:
            self.cores_panel.update_core_halted_info(core, pc, function_name)
        except Exception:  # noqa: BLE001, S110
            pass
        if core == self.active_core():
            try:
                self.connection_panel.set_state(CoreState.Halted, pc, function_name)
            except Exception:  # noqa: BLE001, S110
                pass
        self._update_status_bar()
        self._refresh_stack_and_locals()

    def _on_image_loaded(self, core: str, image: Any) -> None:
        try:
            self.cores_panel.update_core_image(core, getattr(image, "path", None))
        except Exception:  # noqa: BLE001, S110
            pass
        if core == self.active_core():
            self._update_symbol_index_for_active_core()
        self._update_connection_actions()
        self._update_status_bar()

    def _on_load_progress(self, core: str, percent: int) -> None:
        # could update status bar/progress widget if present
        try:
            self._status_bar.showMessage(f"Loading... {int(percent)}%")
        except Exception:  # noqa: BLE001, S110
            pass

    def _on_load_finished(self, core: str, success: bool, message: str) -> None:
        try:
            self._status_bar.showMessage(str(message))
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_status_bar()

    def _on_tm_error(self, operation: str, message: str) -> None:
        try:
            self._status_bar.showMessage(str(message))
        except Exception:  # noqa: BLE001, S110
            pass

    def _on_connection_lost(self) -> None:
        try:
            self.connection_panel.set_state(CoreState.ConnectionLost)
        except Exception:  # noqa: BLE001, S110
            pass
        self._update_connection_actions()
        self._update_status_bar()
        self._update_watch_polling_state()
        self.refresh_watch_now(force_emit=True)

    # --- UI state helpers ---
    def _update_connection_actions(self) -> None:
        core = self.active_core()
        state = self.target_manager.core_state(core) if core else CoreState.Disconnected
        has_image = bool(self.connection_panel.image_path() or (core and self.target_manager.image_for_core(core)))
        connected_count = 0
        try:
            connected_count = self.cores_panel.connected_cores_count()
        except Exception:  # noqa: BLE001
            # fallback count
            for c in self.target_manager.cores():
                if self.target_manager.core_state(c) in (CoreState.Halted, CoreState.Running):
                    connected_count += 1
        try:
            pc = self.target_manager.pc_for_core(core) if core else None
            fn = self.target_manager.function_for_core(core) if core else None
            self.connection_panel.update_actions_for_state(state, has_image, connected_count)
            self.connection_panel.set_state(state, pc, fn)
        except Exception:  # noqa: BLE001
            try:
                self.connection_panel.update_actions_for_state(state, has_image, connected_count)
            except Exception:  # noqa: BLE001, S110
                pass

    def _update_status_bar(self) -> None:
        core = self.active_core() or "-"
        state = self.target_manager.core_state(core) if core != "-" else CoreState.Disconnected
        state_text = state.value if hasattr(state, "value") else str(state)
        probe_desc = "-"
        try:
            if self.session.probe:
                probe_desc = self.session.probe.description
            else:
                probe_desc = self.connection_panel.selected_probe_text() or "-"
        except Exception:  # noqa: BLE001, S110
            pass
        device = self.connection_panel.selected_device() or "-"
        image_path = "-"
        try:
            img = self.target_manager.image_for_core(core) if core != "-" else None
            if img is not None:
                image_path = Path(img.path).name
            elif self.connection_panel.image_path():
                image_path = Path(self.connection_panel.image_path()).name
        except Exception:  # noqa: BLE001, S110
            pass
        msg = f"{__version__} | {probe_desc} | {device} | {core} | {image_path} | {state_text}"
        try:
            self._status_bar.showMessage(msg)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- refresh interval ---
    def _on_refresh_interval_changed(self, value: Any) -> None:
        try:
            ms = max(100, int(value))
        except Exception:  # noqa: BLE001
            ms = 500
        self.session.refresh_interval_ms = ms
        try:
            self.watch_timer.setInterval(ms)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- convenience for tests / CLI ---
    def tick_watch_poll(self) -> None:
        """Manually fire watch timer tick (useful in fallback/headless tests)."""
        # simulate timer firing if allowed
        if self._watch_polling_allowed():
            self.refresh_watch_now(force_emit=False)

    def closeEvent(self, event: Any = None) -> None:
        try:
            self.persist_session()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.watch_timer.stop()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            if event is not None and hasattr(event, "accept"):
                event.accept()
        except Exception:  # noqa: BLE001, S110
            pass
