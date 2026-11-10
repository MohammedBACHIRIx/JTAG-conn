from __future__ import annotations

from typing import Any

from jtagconn.core.models import MemoryFormat, MemoryView

from ._qt import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class MemoryViewWidget(QWidget):
    """Memory view panel: address/symbol, length, format, refresh and formatted rows."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.start_expr_input = QLineEdit(self)
        self.length_input = QSpinBox(self)
        try:
            self.length_input.setRange(1, 65536)
            self.length_input.setValue(64)
        except Exception:  # noqa: BLE001, S110
            pass
        self.format_selector = QComboBox(self)
        self.refresh_button = QPushButton("Refresh", self)
        self.status_label = QLabel("", self)
        self.table = QTableWidget(0, 2, self)
        try:
            self.table.setHorizontalHeaderLabels(["Address", "Values"])
        except Exception:  # noqa: BLE001, S110
            pass

        for fmt in MemoryFormat:
            try:
                self.format_selector.addItem(fmt.value)
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
