from __future__ import annotations

from typing import Any

from jtagconn.core.models import MemoryFormat, MemoryView

from ._qt import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MemoryViewWidget(QWidget):
    """Memory view panel: address/symbol, length, format, refresh and formatted rows."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.start_expr_input = QLineEdit(self)
        try:
            self.start_expr_input.setPlaceholderText("Address (0xC000) or symbol (g_buffer)...")
            self.start_expr_input.setText("0xC000")
        except Exception:  # noqa: BLE001, S110
            pass
        self.length_input = QSpinBox(self)
        try:
            self.length_input.setRange(1, 65536)
            self.length_input.setValue(64)
        except Exception:  # noqa: BLE001, S110
            pass
        self.format_selector = QComboBox(self)
        self.refresh_button = QPushButton("Refresh Memory", self)
        self.status_label = QLabel("", self)
        self.table = QTableWidget(0, 2, self)
        try:
            self.table.setHorizontalHeaderLabels(["Address", "Values"])
            if hasattr(self.table, "horizontalHeader"):
                hdr = self.table.horizontalHeader()
                if hdr is not None and hasattr(hdr, "setStretchLastSection"):
                    hdr.setStretchLastSection(True)
                if hdr is not None and hasattr(hdr, "setSectionResizeMode"):
                    hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        except Exception:  # noqa: BLE001, S110
            pass

        for fmt in MemoryFormat:
            try:
                self.format_selector.addItem(fmt.value)
            except Exception:  # noqa: BLE001, S110
                pass

        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
            top = QHBoxLayout()
            top.addWidget(QLabel("Start Address / Symbol:", self))
            top.addWidget(self.start_expr_input, 2)
            top.addWidget(QLabel("Length:", self))
            top.addWidget(self.length_input)
            top.addWidget(QLabel("Format:", self))
            top.addWidget(self.format_selector)
            top.addWidget(self.refresh_button)
            top.addWidget(QLabel("Status:", self))
            top.addWidget(self.status_label)
            layout.addLayout(top)
            layout.addWidget(self.table, 1)
        except Exception:  # noqa: BLE001, S110
            pass

        self._last_view: MemoryView | None = None

    def selected_format(self) -> MemoryFormat:
        try:
            text = self.format_selector.currentText()
            return MemoryFormat(text)
        except Exception:  # noqa: BLE001
            return MemoryFormat.hex16

    def set_view(self, view: MemoryView, formatted_cells: list[str] | None = None) -> None:
        self._last_view = view
        status = getattr(view, "status", None)
        status_text = status.value if hasattr(status, "value") else str(status or "")
        try:
            self.status_label.setText(status_text)
        except Exception:  # noqa: BLE001, S110
            pass

        # Render simple rows: address + chunk of formatted values (8 per row)
        cells = formatted_cells or [str(v) for v in (getattr(view, "data", []) or [])]
        addr = int(getattr(view, "start_address", 0) or 0)
        per_row = 8
        rows = (len(cells) + per_row - 1) // per_row if cells else 0
        try:
            self.table.setRowCount(rows)
            self.table.setColumnCount(2)
        except Exception:  # noqa: BLE001, S110
            pass
        for r in range(rows):
            chunk = cells[r * per_row : (r + 1) * per_row]
            # Address units depend on width; display raw offset in units for simplicity
            row_addr = addr + r * per_row
            addr_text = f"0x{row_addr:X}"
            values_text = " ".join(chunk)
            self._set_cell(r, 0, addr_text)
            self._set_cell(r, 1, values_text)

        if rows == 0:
            try:
                self.table.clearContents()
            except Exception:  # noqa: BLE001, S110
                pass

    def _set_cell(self, row: int, col: int, text: str) -> None:
        try:
            item = QTableWidgetItem(str(text))
            self.table.setItem(row, col, item)
        except Exception:  # noqa: BLE001, S110
            pass
