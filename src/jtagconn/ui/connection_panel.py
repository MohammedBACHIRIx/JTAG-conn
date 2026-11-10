from __future__ import annotations

from typing import Any

from jtagconn.core.models import CoreState, ProbeKind

from ._qt import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ConnectionPanel(QWidget):
    """Connection/control panel for probe, device, image selection and debug actions."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)

        # Selectors / inputs
        self.probe_selector = QComboBox(self)
        self.device_selector = QComboBox(self)
        self.image_path_input = QLineEdit(self)
        try:
            self.image_path_input.setPlaceholderText("Select TI .out firmware file...")
        except Exception:  # noqa: BLE001, S110
            pass
        self.browse_button = QPushButton("Browse...", self)
        self.recent_files_dropdown = QComboBox(self)
        self.refresh_interval_spinbox = QSpinBox(self)
        try:
            self.refresh_interval_spinbox.setRange(100, 60000)
            self.refresh_interval_spinbox.setSingleStep(100)
            self.refresh_interval_spinbox.setValue(500)
        except Exception:  # noqa: BLE001, S110
            pass

        # Action buttons
        self.connect_button = QPushButton("Connect", self)
        self.disconnect_button = QPushButton("Disconnect", self)
        self.load_button = QPushButton("Load .out", self)
        self.run_button = QPushButton("Run / Resume", self)
        self.halt_button = QPushButton("Halt", self)
        self.reset_button = QPushButton("Reset", self)
        self.run_all_button = QPushButton("Run All", self)
        self.halt_all_button = QPushButton("Halt All", self)

        # Status display
        self.state_badge = QLabel(CoreState.Disconnected.value, self)
        self.pc_label = QLabel("-", self)
        self.function_label = QLabel("-", self)
        self.status_label = QLabel("Disconnected", self)

        self._current_state = CoreState.Disconnected
        self._has_image = False
        self._connected_cores_count = 0

        self._build_layout()

        try:
            self.browse_button.clicked.connect(self._on_browse_clicked)
        except Exception:  # noqa: BLE001, S110
            pass

        # Wire recent file selection to image path input
        try:
            self.recent_files_dropdown.currentTextChanged.connect(self._on_recent_file_selected)
        except Exception:  # noqa: BLE001
            try:
                self.recent_files_dropdown.currentIndexChanged.connect(
                    lambda *_: self._on_recent_file_selected(self.recent_files_dropdown.currentText())
                )
            except Exception:  # noqa: BLE001, S110
                pass

        # Populate defaults
        self.populate_probe_kinds()
        self.populate_devices()
        self.update_actions_for_state(CoreState.Disconnected, False, 0)

    def _build_layout(self) -> None:
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)

            target_group = QGroupBox("Target & Firmware", self)
            form = QFormLayout(target_group)
            form.setContentsMargins(8, 8, 8, 8)
            form.setSpacing(6)
            form.addRow(QLabel("JTAG Probe:", target_group), self.probe_selector)
            form.addRow(QLabel("C2000 Device:", target_group), self.device_selector)

            file_row = QHBoxLayout()
            file_row.addWidget(self.image_path_input, 1)
            file_row.addWidget(self.browse_button)
            form.addRow(QLabel("Firmware (.out):", target_group), file_row)
            form.addRow(QLabel("Recent Files:", target_group), self.recent_files_dropdown)
            form.addRow(QLabel("Live Refresh (ms):", target_group), self.refresh_interval_spinbox)
            root.addWidget(target_group)

            ctrl_group = QGroupBox("Execution Control", self)
            grid = QGridLayout(ctrl_group)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(6)
            grid.addWidget(self.connect_button, 0, 0)
            grid.addWidget(self.disconnect_button, 0, 1)
            grid.addWidget(self.load_button, 1, 0, 1, 2)
            grid.addWidget(self.run_button, 2, 0)
            grid.addWidget(self.halt_button, 2, 1)
            grid.addWidget(self.reset_button, 3, 0, 1, 2)
            grid.addWidget(self.run_all_button, 4, 0)
            grid.addWidget(self.halt_all_button, 4, 1)
            root.addWidget(ctrl_group)

            info_group = QGroupBox("Active Core Status", self)
            info_form = QFormLayout(info_group)
            info_form.setContentsMargins(8, 8, 8, 8)
            info_form.setSpacing(4)
            info_form.addRow(QLabel("State:", info_group), self.state_badge)
            info_form.addRow(QLabel("PC:", info_group), self.pc_label)
            info_form.addRow(QLabel("Function:", info_group), self.function_label)
            root.addWidget(info_group)
            root.addStretch(1)
        except Exception:  # noqa: BLE001, S110
            pass

    def _on_browse_clicked(self) -> None:
        try:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select TI C2000 Firmware (.out)",
                "",
                "TI Firmware Files (*.out *.elf);;All Files (*.*)",
            )
            if path:
                self.set_image_path(path)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- population/helpers ---
    def populate_probe_kinds(self) -> None:
        try:
            self.probe_selector.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        for kind in ProbeKind:
            try:
                self.probe_selector.addItem(kind.value)
            except Exception:  # noqa: BLE001, S110
                pass

    def set_probes(self, probes: list[Any]) -> None:
        """Populate selector with discovered probes (Probe objects or labels)."""
        try:
            self.probe_selector.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        if not probes:
            self.populate_probe_kinds()
            return
        for p in probes:
            label = getattr(p, "description", None) or getattr(p, "kind", None)
            if hasattr(label, "value"):
                label = label.value
            if label is None:
                label = str(p)
            try:
                self.probe_selector.addItem(str(label))
            except Exception:  # noqa: BLE001, S110
                pass

    def populate_devices(self, device_ids: list[str] | None = None) -> None:
        if device_ids is None:
            device_ids = ["F28388D", "F28069M", "F28M35x", "F28M36x", "F28P65x"]
        try:
            self.device_selector.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        for dev in device_ids:
            try:
                self.device_selector.addItem(dev)
            except Exception:  # noqa: BLE001, S110
                pass

    def set_recent_files(self, files: list[str]) -> None:
        try:
            self.recent_files_dropdown.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        for f in files:
            try:
                self.recent_files_dropdown.addItem(str(f))
            except Exception:  # noqa: BLE001, S110
                pass

    def _on_recent_file_selected(self, text: str) -> None:
        if text:
            try:
                self.image_path_input.setText(text)
            except Exception:  # noqa: BLE001, S110
                pass

    def selected_device(self) -> str:
        try:
            return self.device_selector.currentText()
        except Exception:  # noqa: BLE001
            return "F28388D"

    def selected_probe_text(self) -> str:
        try:
            return self.probe_selector.currentText()
        except Exception:  # noqa: BLE001
            return ""

    def image_path(self) -> str:
        try:
            return self.image_path_input.text()
        except Exception:  # noqa: BLE001
            return ""

    def set_image_path(self, path: str) -> None:
        try:
            self.image_path_input.setText(str(path))
        except Exception:  # noqa: BLE001, S110
            pass

    def refresh_interval_ms(self) -> int:
        try:
            return max(100, int(self.refresh_interval_spinbox.value()))
        except Exception:  # noqa: BLE001
            return 500

    def set_refresh_interval_ms(self, value: int) -> None:
        try:
            self.refresh_interval_spinbox.setValue(max(100, int(value)))
        except Exception:  # noqa: BLE001, S110
            pass

    # --- state/UI updates ---
    def set_state(self, state: CoreState, pc: int | None = None, function_name: str | None = None) -> None:
        self._current_state = state
        label = state.value if hasattr(state, "value") else str(state)
        try:
            self.state_badge.setText(label)
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.status_label.setText(label)
        except Exception:  # noqa: BLE001, S110
            pass
        if state == CoreState.Halted:
            pc_text = f"0x{int(pc):X}" if pc is not None else ""
            fn_text = str(function_name) if function_name else ""
            try:
                self.pc_label.setText(pc_text)
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.function_label.setText(fn_text)
            except Exception:  # noqa: BLE001, S110
                pass
        else:
            try:
                self.pc_label.setText("")
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.function_label.setText("")
            except Exception:  # noqa: BLE001, S110
                pass
        self.update_actions_for_state(self._current_state, self._has_image, self._connected_cores_count)

    def update_actions_for_state(
        self, state: CoreState, has_image: bool, connected_cores_count: int
    ) -> None:
        """Strict button enablement state machine."""
        self._current_state = state
        self._has_image = bool(has_image)
        self._connected_cores_count = int(connected_cores_count)

        connect_enabled = state in (CoreState.Disconnected, CoreState.ConnectionLost)
        disconnect_enabled = state in (CoreState.Halted, CoreState.Running)
        load_enabled = state == CoreState.Halted and self._has_image
        run_enabled = state == CoreState.Halted
        reset_enabled = state == CoreState.Halted
        halt_enabled = state == CoreState.Running
        all_enabled = self._connected_cores_count >= 2

        self._set_btn(self.connect_button, connect_enabled)
        self._set_btn(self.disconnect_button, disconnect_enabled)
        self._set_btn(self.load_button, load_enabled)
        self._set_btn(self.run_button, run_enabled)
        self._set_btn(self.reset_button, reset_enabled)
        self._set_btn(self.halt_button, halt_enabled)
        self._set_btn(self.run_all_button, all_enabled)
        self._set_btn(self.halt_all_button, all_enabled)

    @staticmethod
    def _set_btn(btn: Any, enabled: bool) -> None:
        try:
            btn.setEnabled(bool(enabled))
        except Exception:  # noqa: BLE001, S110
            pass
