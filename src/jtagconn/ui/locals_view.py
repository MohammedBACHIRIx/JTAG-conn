from __future__ import annotations

from typing import Any

from jtagconn.core.models import StackFrame, ValueStatus

from ._qt import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class LocalsView(QWidget):
    """Call stack and frame-local variables view."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.stack_list = QTreeWidget(self)
        try:
            self.stack_list.setHeaderLabels(["Frame", "Function", "PC"])
            if hasattr(self.stack_list, "header"):
                hdr = self.stack_list.header()
                if hdr is not None and hasattr(hdr, "setSectionResizeMode"):
                    hdr.setSectionResizeMode(QHeaderView.Stretch)
        except Exception:  # noqa: BLE001, S110
            pass
        self.locals_table = QTableWidget(0, 4, self)
        try:
            self.locals_table.setHorizontalHeaderLabels(["Name", "Type", "Value", "Status"])
            if hasattr(self.locals_table, "horizontalHeader"):
                hdr2 = self.locals_table.horizontalHeader()
                if hdr2 is not None and hasattr(hdr2, "setSectionResizeMode"):
                    hdr2.setSectionResizeMode(QHeaderView.Stretch)
        except Exception:  # noqa: BLE001, S110
            pass
        self.edit_name_input = QLineEdit(self)
        self.edit_value_input = QLineEdit(self)
        self.apply_button = QPushButton("Apply Local", self)
        self.error_label = QLabel("", self)

        try:
            self.edit_name_input.setPlaceholderText("Local name (e.g. err)")
            self.edit_value_input.setPlaceholderText("New value")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            stack_group = QGroupBox("Call Stack (Halted)", self)
            sl = QVBoxLayout(stack_group)
            sl.setContentsMargins(6, 6, 6, 6)
            sl.addWidget(self.stack_list)
            layout.addWidget(stack_group, 1)

            locals_group = QGroupBox("Frame Local Variables", self)
            ll = QVBoxLayout(locals_group)
            ll.setContentsMargins(6, 6, 6, 6)
            ll.addWidget(self.locals_table, 1)
            edit_row = QHBoxLayout()
            edit_row.addWidget(self.edit_name_input, 1)
            edit_row.addWidget(self.edit_value_input, 1)
            edit_row.addWidget(self.apply_button)
            ll.addLayout(edit_row)
            ll.addWidget(self.error_label)
            layout.addWidget(locals_group, 2)
        except Exception:  # noqa: BLE001, S110
            pass

        self._frames: list[StackFrame] = []
        self._selected_frame_index: int | None = None

        try:
            self.stack_list.currentItemChanged.connect(self._on_stack_selection_changed)
        except Exception:  # noqa: BLE001
            try:
                self.stack_list.itemSelectionChanged.connect(self._on_stack_selection_changed_fallback)
            except Exception:  # noqa: BLE001, S110
                pass

    def set_callstack(self, frames: list[StackFrame]) -> None:
        self._frames = list(frames or [])
        self._selected_frame_index = 0 if self._frames else None
        try:
            self.stack_list.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        for fr in self._frames:
            label = f"#{fr.index} {fr.function} @ 0x{int(fr.pc):X}"
            item = QTreeWidgetItem([str(fr.index), str(fr.function), f"0x{int(fr.pc):X}"])
            try:
                item.setData(0, "frame_index", fr.index)
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.stack_list.addTopLevelItem(item)
            except Exception:  # noqa: BLE001, S110
                pass
            # store label for convenience
            try:
                item.setText(0, label)
            except Exception:  # noqa: BLE001, S110
                pass
        if self._frames:
            self.set_locals(self._frames[0].locals)
            # select first item
            try:
                first = self.stack_list.topLevelItem(0)
                if first is not None and hasattr(self.stack_list, "setCurrentItem"):
                    self.stack_list.setCurrentItem(first)
            except Exception:  # noqa: BLE001, S110
                pass
        else:
            self.clear_locals()

    def clear(self) -> None:
        self._frames = []
        self._selected_frame_index = None
        try:
            self.stack_list.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        self.clear_locals()

    def clear_locals(self) -> None:
        try:
            self.locals_table.setRowCount(0)
        except Exception:  # noqa: BLE001
            try:
                self.locals_table.clearContents()
            except Exception:  # noqa: BLE001, S110
                pass

    def set_locals(self, locals_nodes: list[Any]) -> None:
        nodes = list(locals_nodes or [])
        try:
            self.locals_table.setRowCount(len(nodes))
        except Exception:  # noqa: BLE001, S110
            pass
        for i, node in enumerate(nodes):
            name = str(getattr(node, "name", ""))
            tname = str(getattr(node, "type_name", ""))
            disp = str(getattr(node, "display_value", ""))
            status = getattr(node, "status", ValueStatus.current)
            status_text = status.value if hasattr(status, "value") else str(status)
            self._set_cell(i, 0, name)
            self._set_cell(i, 1, tname)
            self._set_cell(i, 2, disp)
            self._set_cell(i, 3, status_text)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        try:
            self.locals_table.setItem(row, col, QTableWidgetItem(str(text)))
        except Exception:  # noqa: BLE001, S110
            pass

    def selected_frame_index(self) -> int | None:
        return self._selected_frame_index

    def _on_stack_selection_changed(self, current: Any, previous: Any = None) -> None:
        idx = None
        if current is not None:
            try:
                data = current.data(0, "frame_index") if hasattr(current, "data") else None
                if data is not None:
                    idx = int(data)
            except Exception:  # noqa: BLE001
                idx = None
            if idx is None:
                # parse "#0 ..." label
                try:
                    txt = current.text(0)
                    if txt.startswith("#"):
                        idx = int(txt[1:].split()[0])
                except Exception:  # noqa: BLE001
                    idx = None
        self._selected_frame_index = idx
        if idx is not None:
            for fr in self._frames:
                if int(fr.index) == int(idx):
                    self.set_locals(getattr(fr, "locals", []))
                    return

    def _on_stack_selection_changed_fallback(self) -> None:
        # fallback for implementations emitting no args
        try:
            current = self.stack_list.currentItem()
        except Exception:  # noqa: BLE001
            current = None
        self._on_stack_selection_changed(current, None)

    def set_error(self, message: str) -> None:
        try:
            self.error_label.setText(str(message))
        except Exception:  # noqa: BLE001, S110
            pass
