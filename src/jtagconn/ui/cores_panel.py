from __future__ import annotations

from pathlib import Path
from typing import Any

from jtagconn.core.models import CoreState

from ._qt import QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QWidget, Signal


class CoresPanel(QWidget):
    """Lists debuggable cores and supports active core selection and per-core connect/disconnect."""

    coreSelected = Signal(str) if callable(Signal) else None  # type: ignore

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        # compatibility: real Qt Signal assigned at class or fallback descriptor; ensure instance access works
        if not hasattr(self, "coreSelected"):
            # fallback: create a simple signal-like object
            class _Sig:
                def __init__(self) -> None:
                    self._slots = []
                def connect(self, s): self._slots.append(s)
                def emit(self, *a): 
                    for s in list(self._slots):
                        try:
                            s(*a)
                        except Exception:  # noqa: BLE001, S110
                            pass
            self.coreSelected = _Sig()  # type: ignore

        self.core_selector = QComboBox(self)
        self.cores_table = QTableWidget(0, 4, self)
        try:
            self.cores_table.setHorizontalHeaderLabels(["Core", "State", "PC / Function", "Image"])
        except Exception:  # noqa: BLE001, S110
            pass
        self.connect_core_button = QPushButton("Connect Core", self)
        self.disconnect_core_button = QPushButton("Disconnect Core", self)

        self._cores: list[str] = []
        self._core_rows: dict[str, int] = {}
        self._core_states: dict[str, CoreState] = {}
        self._core_pcs: dict[str, tuple[int | None, str | None]] = {}
        self._core_images: dict[str, str] = {}
        self._active_core: str | None = None

        try:
            self.core_selector.currentTextChanged.connect(self._on_core_changed)
        except Exception:  # noqa: BLE001
            try:
                self.core_selector.currentIndexChanged.connect(
                    lambda *_: self._on_core_changed(self.core_selector.currentText())
                )
            except Exception:  # noqa: BLE001, S110
                pass

    def set_cores(self, cores: list[str]) -> None:
        self._cores = list(cores)
        try:
            self.core_selector.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        self._core_rows = {}
        try:
            self.cores_table.setRowCount(0)
        except Exception:  # noqa: BLE001, S110
            pass
        for i, core in enumerate(self._cores):
            try:
                self.core_selector.addItem(core)
            except Exception:  # noqa: BLE001, S110
                pass
            self._core_rows[core] = i
            self._ensure_row(core)
            self.update_core_row(core)
        if self._cores:
            self.set_active_core(self._active_core or self._cores[0])
        else:
            self._active_core = None

    def _ensure_row(self, core: str) -> int:
        row = self._core_rows.get(core)
        if row is None:
            row = int(getattr(self.cores_table, "rowCount", lambda: 0)())
            self._core_rows[core] = row
            try:
                self.cores_table.setRowCount(row + 1)
            except Exception:  # noqa: BLE001, S110
                pass
        return row

    def set_active_core(self, core: str | None) -> None:
        if core and core in self._cores:
            self._active_core = core
            try:
                self.core_selector.setCurrentText(core)
            except Exception:  # noqa: BLE001, S110
                pass

    def active_core(self) -> str | None:
        try:
            text = self.core_selector.currentText()
            if text:
                return text
        except Exception:  # noqa: BLE001, S110
            pass
        return self._active_core

    def _on_core_changed(self, core: str) -> None:
        if core:
            self._active_core = core
            try:
                self.coreSelected.emit(core)
            except Exception:  # noqa: BLE001, S110
                pass

    def update_core_state(self, core: str, state: CoreState) -> None:
        self._core_states[core] = state
        self.update_core_row(core)

    def update_core_halted_info(self, core: str, pc: int | None, function_name: str | None) -> None:
        self._core_pcs[core] = (pc, function_name)
        self.update_core_row(core)

    def update_core_image(self, core: str, image_path: str | None) -> None:
        if image_path:
            self._core_images[core] = Path(str(image_path)).name
        else:
            self._core_images.pop(core, None)
        self.update_core_row(core)

    def update_core_row(self, core: str) -> None:
        row = self._ensure_row(core)
        state = self._core_states.get(core, CoreState.Disconnected)
        state_text = state.value if hasattr(state, "value") else str(state)
        pc, fn = self._core_pcs.get(core, (None, None))
        pc_fn = ""
        if pc is not None:
            pc_fn = f"0x{int(pc):X}"
            if fn:
                pc_fn += f" ({fn})"
        elif fn:
            pc_fn = str(fn)
        image_name = self._core_images.get(core, "")

        self._set_cell(row, 0, core)
        self._set_cell(row, 1, state_text)
        self._set_cell(row, 2, pc_fn)
        self._set_cell(row, 3, image_name)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        try:
            item = QTableWidgetItem(str(text))
        except Exception:  # noqa: BLE001
            return
        try:
            self.cores_table.setItem(row, col, item)
        except Exception:  # noqa: BLE001, S110
            pass

    def connected_cores_count(self) -> int:
        count = 0
        for c in self._cores:
            st = self._core_states.get(c, CoreState.Disconnected)
            if st in (CoreState.Halted, CoreState.Running):
                count += 1
        return count
