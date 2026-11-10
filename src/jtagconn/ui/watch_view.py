from __future__ import annotations

from typing import Any

from jtagconn.core.models import DisplayFormat, ValueNode, ValueStatus
from jtagconn.symbols.index import SymbolIndex

from ._qt import QComboBox, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QWidget


class WatchView(QWidget):
    """Watch panel: symbol search/add/remove, formatted tree display, inline edit support."""

    COL_EXPR = 0
    COL_TYPE = 1
    COL_VALUE = 2
    COL_FORMAT = 3
    COL_STATUS = 4

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.search_input = QLineEdit(self)
        self.add_button = QPushButton("Add Watch", self)
        self.remove_button = QPushButton("Remove Watch", self)
        self.format_selector = QComboBox(self)
        self.edit_value_input = QLineEdit(self)
        self.apply_edit_button = QPushButton("Apply", self)
        self.error_label = QLabel("", self)
        self.suggestions_label = QLabel("", self)

        self.tree = QTreeWidget(self)
        try:
            self.tree.setColumnCount(5)
            self.tree.setHeaderLabels(["Expression", "Type", "Value", "Format", "Status"])
        except Exception:  # noqa: BLE001, S110
            pass

        for fmt in DisplayFormat:
            try:
                self.format_selector.addItem(fmt.value)
            except Exception:  # noqa: BLE001, S110
                pass

        self._symbol_index = SymbolIndex()
        self._entries_by_expr: dict[str, Any] = {}
        self._top_items: dict[str, QTreeWidgetItem] = {}

        try:
            self.search_input.textChanged.connect(self._on_search_text_changed)
        except Exception:  # noqa: BLE001, S110
            pass

    # --- symbol index / autocomplete ---
    def set_symbol_index(self, symbols: list[Any] | SymbolIndex) -> None:
        if isinstance(symbols, SymbolIndex):
            self._symbol_index = symbols
        else:
            self._symbol_index = SymbolIndex(list(symbols))

    def suggest_symbols(self, query: str, limit: int = 20) -> list[str]:
        try:
            syms = self._symbol_index.search(query, limit=limit)
        except Exception:  # noqa: BLE001
            return []
        suggestions: list[str] = []
        for s in syms:
            name = getattr(s, "name", str(s))
            addr = getattr(s, "address", None)
            tinfo = getattr(s, "type_info", None)
            tname = getattr(tinfo, "name", "") if tinfo is not None else ""
            if addr is not None:
                suggestions.append(f"{name} ({tname} @ 0x{int(addr):X})")
            else:
                suggestions.append(str(name))
        return suggestions

    def _on_search_text_changed(self, text: str) -> None:
        sugg = self.suggest_symbols(text)
        try:
            self.suggestions_label.setText("; ".join(sugg[:10]))
        except Exception:  # noqa: BLE001, S110
            pass

    # --- watch entry management ---
    def clear(self) -> None:
        self._entries_by_expr.clear()
        self._top_items.clear()
        try:
            self.tree.clear()
        except Exception:  # noqa: BLE001, S110
            pass

    def upsert_entries(self, entries: list[Any]) -> None:
        """Diff-only UI update: update/add changed entries by expression."""
        for entry in entries:
            expr = getattr(entry, "expression", None)
            if not expr:
                continue
            self._entries_by_expr[expr] = entry
            item = self._top_items.get(expr)
            if item is None:
                item = QTreeWidgetItem(["", "", "", "", ""])
                self._top_items[expr] = item
                try:
                    self.tree.addTopLevelItem(item)
                except Exception:  # noqa: BLE001, S110
                    pass
            self._populate_item_from_entry(item, entry)

    def set_entries(self, entries: list[Any]) -> None:
        self.clear()
        self.upsert_entries(entries)

    def remove_expression(self, expression: str) -> None:
        expr = str(expression).strip()
        self._entries_by_expr.pop(expr, None)
        item = self._top_items.pop(expr, None)
        if item is not None:
            # find and remove from root
            try:
                root = self.tree.invisibleRootItem()
                for i in range(root.childCount() - 1, -1, -1):
                    ch = root.child(i)
                    if ch is item:
                        # QTreeWidgetItem has no direct remove in fallback; rebuild children list
                        children = root.takeChildren()
                        for c in children:
                            if c is not item:
                                root.addChild(c)
                        break
            except Exception:  # noqa: BLE001, S110
                pass

    def _populate_item_from_entry(self, item: QTreeWidgetItem, entry: Any) -> None:
        expr = str(getattr(entry, "expression", ""))
        fmt = getattr(entry, "format", DisplayFormat.natural)
        fmt_text = fmt.value if hasattr(fmt, "value") else str(fmt)
        status = getattr(entry, "status", ValueStatus.current)
        status_text = status.value if hasattr(status, "value") else str(status)
        val_node = getattr(entry, "value", None)

        type_text = ""
        value_text = ""
        if val_node is not None:
            type_text = str(getattr(val_node, "type_name", "") or "")
            value_text = str(getattr(val_node, "display_value", "") or "")
            st = getattr(val_node, "status", None)
            if st is not None:
                status_text = st.value if hasattr(st, "value") else str(st)

        try:
            item.setText(self.COL_EXPR, expr)
            item.setText(self.COL_TYPE, type_text)
            item.setText(self.COL_VALUE, value_text)
            item.setText(self.COL_FORMAT, fmt_text)
            item.setText(self.COL_STATUS, status_text)
        except Exception:  # noqa: BLE001, S110
            pass

        # Expand struct/array children
        try:
            if hasattr(item, "takeChildren"):
                item.takeChildren()
        except Exception:  # noqa: BLE001, S110
            pass
        children = getattr(val_node, "children", None) if val_node is not None else None
        if children:
            self._add_child_nodes(item, children)

    def _add_child_nodes(self, parent_item: QTreeWidgetItem, nodes: list[ValueNode]) -> None:
        for node in nodes:
            name = str(getattr(node, "name", "") or "")
            expr = str(getattr(node, "expression", "") or "")
            type_text = str(getattr(node, "type_name", "") or "")
            value_text = str(getattr(node, "display_value", "") or "")
            st = getattr(node, "status", ValueStatus.current)
            status_text = st.value if hasattr(st, "value") else str(st)
            child = QTreeWidgetItem([expr or name, type_text, value_text, "", status_text])
            try:
                child.setText(self.COL_EXPR, expr or name)
                child.setText(self.COL_TYPE, type_text)
                child.setText(self.COL_VALUE, value_text)
                child.setText(self.COL_STATUS, status_text)
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                parent_item.addChild(child)
            except Exception:  # noqa: BLE001, S110
                pass
            sub = getattr(node, "children", None)
            if sub:
                self._add_child_nodes(child, sub)

    # --- edit helpers ---
    def set_edit_error(self, message: str) -> None:
        try:
            self.error_label.setText(str(message))
        except Exception:  # noqa: BLE001, S110
            pass

    def clear_edit_error(self) -> None:
        self.set_edit_error("")
