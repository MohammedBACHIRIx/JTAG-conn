"""Qt compatibility layer for JTAG-conn UI.

On Windows/desktop environments with full Qt runtime, exports real PySide6 classes.
In headless Linux environments missing system libs (e.g. libEGL), provides a
lightweight stateful fallback API so UI controllers/panels can be exercised in tests.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _SignalInstance:
    def __init__(self) -> None:
        self._slots: list[Callable[..., Any]] = []

    def connect(self, slot: Callable[..., Any]) -> None:
        if slot not in self._slots:
            self._slots.append(slot)

    def disconnect(self, slot: Callable[..., Any] | None = None) -> None:
        if slot is None:
            self._slots.clear()
            return
        try:
            self._slots.remove(slot)
        except ValueError:
            pass

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for slot in list(self._slots):
            try:
                slot(*args, **kwargs)
            except TypeError:
                # be permissive for slots declared with fewer args in fallback mode
                try:
                    slot(*args[: slot.__code__.co_argcount - 1])
                except Exception:  # noqa: BLE001, S110
                    pass
            except Exception:  # noqa: BLE001, S110
                pass


class _SignalDescriptor:
    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        signals = obj.__dict__.setdefault("_qt_signals", {})
        sig = signals.get(self._name)
        if sig is None:
            sig = _SignalInstance()
            signals[self._name] = sig
        return sig


class Signal:
    def __init__(self, *arg_types: Any) -> None:
        self._arg_types = arg_types

    def __set_name__(self, owner: type, name: str) -> None:
        desc = _SignalDescriptor()
        desc.__set_name__(owner, name)
        setattr(owner, name, desc)


HAS_QT_WIDGETS = False
try:
    # Prefer real Qt when available (Windows target / dev with full libs)
    from PySide6 import (
        QtCore,  # type: ignore
        QtGui,  # type: ignore
        QtWidgets,  # type: ignore
    )

    HAS_QT_WIDGETS = True
    # Re-export Signal for convenience in fallback-style code paths if needed
    try:
        Signal = QtCore.Signal  # type: ignore[assignment]
    except Exception:  # noqa: BLE001, S110
        pass
except Exception:  # noqa: BLE001
    # Headless fallback: provide minimal stateful API compatible with our UI code/tests.
    HAS_QT_WIDGETS = False

    class QObject:
        def __init__(self, parent: Any = None) -> None:
            self._parent = parent
            self._children: list[Any] = []
            if parent is not None and hasattr(parent, "_children"):
                try:
                    parent._children.append(self)
                except Exception:  # noqa: BLE001, S110
                    pass

        def parent(self) -> Any:
            return self._parent

        def setParent(self, parent: Any) -> None:
            self._parent = parent

        def deleteLater(self) -> None:
            pass

    class QWidget(QObject):
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._visible = True
            self._enabled = True
            self._window_title = ""
            self._layout = None
            self._minimized = False

        def show(self) -> None:
            self._visible = True

        def hide(self) -> None:
            self._visible = False

        def isVisible(self) -> bool:
            return self._visible

        def setEnabled(self, enabled: bool) -> None:
            self._enabled = bool(enabled)

        def isEnabled(self) -> bool:
            return self._enabled

        def setWindowTitle(self, title: str) -> None:
            self._window_title = str(title)

        def windowTitle(self) -> str:
            return self._window_title

        def setLayout(self, layout: Any) -> None:
            self._layout = layout

        def layout(self) -> Any:
            return self._layout

        def showMinimized(self) -> None:
            self._minimized = True
            self._visible = True

        def isMinimized(self) -> bool:
            return bool(self._minimized)

        def setVisible(self, visible: bool) -> None:
            self._visible = bool(visible)

    class QMainWindow(QWidget):
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._central_widget: Any = None
            self._docks: list[Any] = []
            self._status_bar: Any = None
            self._toolbar: Any = None
            self._menu_bar: Any = None

        def setCentralWidget(self, widget: Any) -> None:
            self._central_widget = widget

        def centralWidget(self) -> Any:
            return self._central_widget

        def addDockWidget(self, area: Any, dock: Any) -> None:
            self._docks.append((area, dock))

        def dockWidgets(self) -> list[Any]:
            return [d for _, d in self._docks]

        def setStatusBar(self, status_bar: Any) -> None:
            self._status_bar = status_bar

        def statusBar(self) -> Any:
            return self._status_bar

        def addToolBar(self, *args: Any, **kwargs: Any) -> Any:
            tb = QToolBar(self)
            self._toolbar = tb
            return tb

        def toolBar(self) -> Any:
            return self._toolbar

        def menuBar(self) -> Any:
            if self._menu_bar is None:
                self._menu_bar = QWidget(self)
            return self._menu_bar

    class Qt:
        LeftDockWidgetArea = 0x1
        RightDockWidgetArea = 0x2
        TopDockWidgetArea = 0x4
        BottomDockWidgetArea = 0x8
        AllDockWidgetAreas = 0xF
        Horizontal = 0x1
        Vertical = 0x2

    class QDockWidget(QWidget):
        def __init__(self, title: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._title = str(title)
            self._widget: Any = None
            self._area: Any = None

        def setWidget(self, widget: Any) -> None:
            self._widget = widget

        def widget(self) -> Any:
            return self._widget

        def setWindowTitle(self, title: str) -> None:
            self._title = str(title)

        def windowTitle(self) -> str:
            return self._title

        def title(self) -> str:
            return self._title

    class QAction(QObject):
        triggered = _SignalDescriptor()
        toggled = _SignalDescriptor()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = str(text)
            self._enabled = True
            self._checkable = False
            self._checked = False

        def text(self) -> str:
            return self._text

        def setText(self, text: str) -> None:
            self._text = str(text)

        def setEnabled(self, enabled: bool) -> None:
            self._enabled = bool(enabled)

        def isEnabled(self) -> bool:
            return self._enabled

        def setCheckable(self, c: bool) -> None:
            self._checkable = bool(c)

        def isCheckable(self) -> bool:
            return self._checkable

        def setChecked(self, c: bool) -> None:
            self._checked = bool(c)
            try:
                self.toggled.emit(self._checked)
            except Exception:  # noqa: BLE001, S110
                pass

        def isChecked(self) -> bool:
            return self._checked

        def trigger(self) -> None:
            if self._enabled:
                self.triggered.emit()

    class QToolBar(QWidget):
        def __init__(self, title: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._actions: list[Any] = []

        def addAction(self, action_or_text: Any, *args: Any) -> Any:
            if isinstance(action_or_text, QAction):
                act = action_or_text
            else:
                act = QAction(str(action_or_text), self)
            self._actions.append(act)
            return act

        def addWidget(self, widget: Any) -> Any:
            self._actions.append(widget)
            return widget

        def actions(self) -> list[Any]:
            return list(self._actions)

    class QLabel(QWidget):
        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = str(text)

        def setText(self, text: str) -> None:
            self._text = str(text)

        def text(self) -> str:
            return self._text

    class QPushButton(QWidget):
        clicked = _SignalDescriptor()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = str(text)

        def setText(self, text: str) -> None:
            self._text = str(text)

        def text(self) -> str:
            return self._text

        def click(self) -> None:
            if self.isEnabled():
                self.clicked.emit()

    class QLineEdit(QWidget):
        textChanged = _SignalDescriptor()
        returnPressed = _SignalDescriptor()
        editingFinished = _SignalDescriptor()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = str(text)
            self._placeholder = ""

        def setText(self, text: str) -> None:
            self._text = str(text)
            try:
                self.textChanged.emit(self._text)
            except Exception:  # noqa: BLE001, S110
                pass

        def text(self) -> str:
            return self._text

        def setPlaceholderText(self, text: str) -> None:
            self._placeholder = str(text)

        def placeholderText(self) -> str:
            return self._placeholder

        def clear(self) -> None:
            self.setText("")

    class QSpinBox(QWidget):
        valueChanged = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._min = 0
            self._max = 100
            self._value = 0
            self._step = 1

        def setRange(self, minimum: int, maximum: int) -> None:
            self._min = int(minimum)
            self._max = int(maximum)
            self._value = min(max(self._value, self._min), self._max)

        def setMinimum(self, minimum: int) -> None:
            self.setRange(int(minimum), self._max)

        def setMaximum(self, maximum: int) -> None:
            self.setRange(self._min, int(maximum))

        def setSingleStep(self, step: int) -> None:
            self._step = int(step)

        def setValue(self, value: int) -> None:
            v = int(value)
            v = min(max(v, self._min), self._max)
            if v != self._value:
                self._value = v
                self.valueChanged.emit(self._value)
            else:
                self._value = v

        def value(self) -> int:
            return self._value

    class QComboBox(QWidget):
        currentIndexChanged = _SignalDescriptor()
        currentTextChanged = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._items: list[str] = []
            self._current_index = -1
            self._editable = False

        def addItem(self, text: str, userData: Any = None) -> None:
            self._items.append(str(text))
            if self._current_index < 0:
                self.setCurrentIndex(0)

        def addItems(self, texts: list[str]) -> None:
            for t in texts:
                self.addItem(t)

        def clear(self) -> None:
            self._items.clear()
            self._current_index = -1

        def count(self) -> int:
            return len(self._items)

        def itemText(self, index: int) -> str:
            if 0 <= index < len(self._items):
                return self._items[index]
            return ""

        def currentIndex(self) -> int:
            return self._current_index

        def setCurrentIndex(self, index: int) -> None:
            if index < 0 or index >= len(self._items):
                if not self._items:
                    self._current_index = -1
                return
            self._current_index = int(index)
            try:
                self.currentIndexChanged.emit(self._current_index)
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.currentTextChanged.emit(self.currentText())
            except Exception:  # noqa: BLE001, S110
                pass

        def currentText(self) -> str:
            return self.itemText(self._current_index)

        def setCurrentText(self, text: str) -> None:
            t = str(text)
            for i, item in enumerate(self._items):
                if item == t:
                    self.setCurrentIndex(i)
                    return
            # if editable in fallback, allow setting by adding/selecting
            if self._editable:
                self.addItem(t)
                self.setCurrentIndex(len(self._items) - 1)

        def setEditable(self, editable: bool) -> None:
            self._editable = bool(editable)

        def setItemText(self, index: int, text: str) -> None:
            if 0 <= index < len(self._items):
                self._items[index] = str(text)

        def removeItem(self, index: int) -> None:
            if 0 <= index < len(self._items):
                del self._items[index]
                if not self._items:
                    self._current_index = -1
                elif self._current_index >= len(self._items):
                    self.setCurrentIndex(len(self._items) - 1)

    class QTableWidgetItem:
        def __init__(self, text: str = "") -> None:
            self._text = str(text)
            self._data: dict[Any, Any] = {}

        def text(self) -> str:
            return self._text

        def setText(self, text: str) -> None:
            self._text = str(text)

        def setData(self, role: Any, value: Any) -> None:
            self._data[role] = value

        def data(self, role: Any) -> Any:
            return self._data.get(role)

    class QTableWidget(QWidget):
        itemChanged = _SignalDescriptor()
        cellChanged = _SignalDescriptor()
        currentCellChanged = _SignalDescriptor()

        def __init__(self, rows: int = 0, cols: int = 0, parent: Any = None) -> None:
            super().__init__(parent)
            self._rows = int(rows)
            self._cols = int(cols)
            self._headers: list[str] = [""] * self._cols
            self._items: dict[tuple[int, int], QTableWidgetItem] = {}
            self._current_row = -1
            self._current_col = -1

        def setColumnCount(self, cols: int) -> None:
            self._cols = int(cols)
            if len(self._headers) < self._cols:
                self._headers.extend([""] * (self._cols - len(self._headers)))
            else:
                self._headers = self._headers[: self._cols]

        def columnCount(self) -> int:
            return self._cols

        def setRowCount(self, rows: int) -> None:
            self._rows = int(rows)
            # drop out-of-range items
            self._items = {k: v for k, v in self._items.items() if k[0] < self._rows and k[1] < self._cols}

        def rowCount(self) -> int:
            return self._rows

        def setHorizontalHeaderLabels(self, labels: list[str]) -> None:
            self._headers = [str(x) for x in labels]
            if len(self._headers) < self._cols:
                self._headers.extend([""] * (self._cols - len(self._headers)))
            self._cols = max(self._cols, len(self._headers))

        def horizontalHeaderItem(self, col: int) -> QTableWidgetItem | None:
            if 0 <= col < len(self._headers):
                return QTableWidgetItem(self._headers[col])
            return None

        def setItem(self, row: int, col: int, item: QTableWidgetItem | None) -> None:
            if row < 0 or col < 0:
                return
            if row >= self._rows:
                self.setRowCount(row + 1)
            if col >= self._cols:
                self.setColumnCount(col + 1)
            if item is None:
                self._items.pop((row, col), None)
            else:
                self._items[(row, col)] = item

        def item(self, row: int, col: int) -> QTableWidgetItem | None:
            return self._items.get((row, col))

        def clearContents(self) -> None:
            self._items.clear()

        def clear(self) -> None:
            self._items.clear()
            self._rows = 0
            self._headers = []

        def setCurrentCell(self, row: int, col: int) -> None:
            self._current_row = row
            self._current_col = col
            try:
                self.currentCellChanged.emit(row, col, -1, -1)
            except Exception:  # noqa: BLE001, S110
                pass

        def currentRow(self) -> int:
            return self._current_row

        def removeRow(self, row: int) -> None:
            if row < 0 or row >= self._rows:
                return
            new_items: dict[tuple[int, int], QTableWidgetItem] = {}
            for (r, c), it in self._items.items():
                if r == row:
                    continue
                nr = r - 1 if r > row else r
                new_items[(nr, c)] = it
            self._items = new_items
            self._rows -= 1

    class QTreeWidgetItem:
        def __init__(self, strings: list[str] | None = None) -> None:
            self._texts = [str(s) for s in (strings or [])]
            self._children: list[QTreeWidgetItem] = []
            self._parent: QTreeWidgetItem | None = None
            self._data: dict[tuple[int, Any], Any] = {}
            self._expanded = False

        def setText(self, column: int, text: str) -> None:
            while len(self._texts) <= column:
                self._texts.append("")
            self._texts[column] = str(text)

        def text(self, column: int) -> str:
            if 0 <= column < len(self._texts):
                return self._texts[column]
            return ""

        def addChild(self, item: QTreeWidgetItem) -> None:
            item._parent = self
            self._children.append(item)

        def child(self, index: int) -> QTreeWidgetItem | None:
            if 0 <= index < len(self._children):
                return self._children[index]
            return None

        def childCount(self) -> int:
            return len(self._children)

        def takeChildren(self) -> list[QTreeWidgetItem]:
            children = list(self._children)
            for c in children:
                c._parent = None
            self._children.clear()
            return children

        def setData(self, column: int, role: Any, value: Any) -> None:
            self._data[(column, role)] = value

        def data(self, column: int, role: Any) -> Any:
            return self._data.get((column, role))

        def parent(self) -> QTreeWidgetItem | None:
            return self._parent

        def setExpanded(self, expanded: bool) -> None:
            self._expanded = bool(expanded)

        def isExpanded(self) -> bool:
            return self._expanded

    class QTreeWidget(QWidget):
        itemChanged = _SignalDescriptor()
        itemSelectionChanged = _SignalDescriptor()
        currentItemChanged = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._headers: list[str] = []
            self._root = QTreeWidgetItem()
            self._col_count = 1
            self._current_item: QTreeWidgetItem | None = None

        def setHeaderLabels(self, labels: list[str]) -> None:
            self._headers = [str(x) for x in labels]
            self._col_count = max(1, len(self._headers))

        def setColumnCount(self, cols: int) -> None:
            self._col_count = max(1, int(cols))

        def columnCount(self) -> int:
            return self._col_count

        def headerItem(self) -> QTreeWidgetItem:
            return QTreeWidgetItem(self._headers)

        def clear(self) -> None:
            self._root.takeChildren()
            self._current_item = None

        def invisibleRootItem(self) -> QTreeWidgetItem:
            return self._root

        def addTopLevelItem(self, item: QTreeWidgetItem) -> None:
            self._root.addChild(item)

        def topLevelItemCount(self) -> int:
            return self._root.childCount()

        def topLevelItem(self, index: int) -> QTreeWidgetItem | None:
            return self._root.child(index)

        def setCurrentItem(self, item: QTreeWidgetItem | None) -> None:
            prev = self._current_item
            self._current_item = item
            try:
                self.currentItemChanged.emit(item, prev)
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.itemSelectionChanged.emit()
            except Exception:  # noqa: BLE001, S110
                pass

        def currentItem(self) -> QTreeWidgetItem | None:
            return self._current_item

    class QPlainTextEdit(QWidget):
        textChanged = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._lines: list[str] = []
            self._readonly = False

        def appendPlainText(self, text: str) -> None:
            self._lines.append(str(text))
            try:
                self.textChanged.emit()
            except Exception:  # noqa: BLE001, S110
                pass

        def setPlainText(self, text: str) -> None:
            self._lines = str(text).splitlines()
            try:
                self.textChanged.emit()
            except Exception:  # noqa: BLE001, S110
                pass

        def toPlainText(self) -> str:
            return "\n".join(self._lines)

        def clear(self) -> None:
            self._lines = []
            try:
                self.textChanged.emit()
            except Exception:  # noqa: BLE001, S110
                pass

        def setReadOnly(self, ro: bool) -> None:
            self._readonly = bool(ro)

        def isReadOnly(self) -> bool:
            return self._readonly

    class QTextEdit(QPlainTextEdit):
        pass

    class QStatusBar(QWidget):
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._message = ""

        def showMessage(self, message: str, timeout: int = 0) -> None:
            self._message = str(message)

        def currentMessage(self) -> str:
            return self._message

        def clearMessage(self) -> None:
            self._message = ""

    class QTabWidget(QWidget):
        currentChanged = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._tabs: list[tuple[str, Any]] = []
            self._current_index = -1

        def addTab(self, widget: Any, label: str) -> int:
            self._tabs.append((str(label), widget))
            self._current_index = max(self._current_index, 0)
            return len(self._tabs) - 1

        def count(self) -> int:
            return len(self._tabs)

        def widget(self, index: int) -> Any:
            if 0 <= index < len(self._tabs):
                return self._tabs[index][1]
            return None

        def tabText(self, index: int) -> str:
            if 0 <= index < len(self._tabs):
                return self._tabs[index][0]
            return ""

        def setCurrentIndex(self, index: int) -> None:
            if 0 <= index < len(self._tabs):
                self._current_index = index
                try:
                    self.currentChanged.emit(index)
                except Exception:  # noqa: BLE001, S110
                    pass

        def currentIndex(self) -> int:
            return self._current_index

        def currentWidget(self) -> Any:
            return self.widget(self._current_index)

    class QTimer(QObject):
        timeout = _SignalDescriptor()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._interval_ms = 0
            self._active = False
            self._single_shot = False

        def start(self, msec: int | None = None) -> None:
            if msec is not None:
                self._interval_ms = int(msec)
            self._active = True

        def stop(self) -> None:
            self._active = False

        def isActive(self) -> bool:
            return self._active

        def setInterval(self, msec: int) -> None:
            self._interval_ms = int(msec)

        def interval(self) -> int:
            return self._interval_ms

        def setSingleShot(self, single: bool) -> None:
            self._single_shot = bool(single)

        def isSingleShot(self) -> bool:
            return self._single_shot

        def tick(self) -> None:
            """Test/helper hook to fire timeout if active (no real event loop in fallback)."""
            if self._active:
                self.timeout.emit()
                if self._single_shot:
                    self._active = False

    class QMessageBox:
        Yes = 0x4000
        No = 0x10000
        Cancel = 0x20000
        Ok = 0x0400

        @staticmethod
        def question(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> int:
            # In fallback/headless mode default to No (safety)
            return QMessageBox.No

        @staticmethod
        def information(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> int:
            return QMessageBox.Ok

        @staticmethod
        def warning(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> int:
            return QMessageBox.Ok

        @staticmethod
        def critical(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> int:
            return QMessageBox.Ok

    class QFileDialog(QWidget):
        @staticmethod
        def getOpenFileName(parent: Any = None, caption: str = "", dir: str = "", filter: str = "") -> tuple[str, str]:
            return ("", "")

    class _BaseLayout(QObject):
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._items: list[Any] = []
            if parent is not None and hasattr(parent, "setLayout"):
                try:
                    parent.setLayout(self)
                except Exception:  # noqa: BLE001, S110
                    pass

        def addWidget(self, widget: Any, *args: Any, **kwargs: Any) -> None:
            self._items.append(widget)

        def addLayout(self, layout: Any, *args: Any, **kwargs: Any) -> None:
            self._items.append(layout)

        def addRow(self, *args: Any, **kwargs: Any) -> None:
            self._items.append(args)

        def addStretch(self, *args: Any, **kwargs: Any) -> None:
            pass

        def setContentsMargins(self, *args: Any, **kwargs: Any) -> None:
            pass

        def setSpacing(self, *args: Any, **kwargs: Any) -> None:
            pass

        def count(self) -> int:
            return len(self._items)

    class QVBoxLayout(_BaseLayout):
        pass

    class QHBoxLayout(_BaseLayout):
        pass

    class QFormLayout(_BaseLayout):
        pass

    class QGridLayout(_BaseLayout):
        pass

    class QGroupBox(QWidget):
        def __init__(self, title: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._title = str(title)

        def title(self) -> str:
            return self._title

        def setTitle(self, title: str) -> None:
            self._title = str(title)

    class QSplitter(QWidget):
        def __init__(self, orientation: Any = None, parent: Any = None) -> None:
            super().__init__(parent)
            self._orientation = orientation
            self._widgets: list[Any] = []

        def addWidget(self, widget: Any) -> None:
            self._widgets.append(widget)

        def setSizes(self, sizes: list[int]) -> None:
            pass

        def setStretchFactor(self, index: int, stretch: int) -> None:
            pass

    class QHeaderView(QWidget):
        Stretch = 1
        ResizeToContents = 3
        Interactive = 0

        def setSectionResizeMode(self, *args: Any, **kwargs: Any) -> None:
            pass

        def setStretchLastSection(self, *args: Any, **kwargs: Any) -> None:
            pass

    class QApplication:
        _instance: QApplication | None = None

        def __init__(self, args: list[str] | None = None) -> None:
            self._args = list(args or [])
            QApplication._instance = self

        @staticmethod
        def instance() -> QApplication | None:
            return QApplication._instance

        @staticmethod
        def processEvents(*args: Any, **kwargs: Any) -> None:
            return None

        def exec(self) -> int:
            return 0

        def exec_(self) -> int:
            return 0

    # Build QtCore/QtGui/QtWidgets namespaces for attribute-style imports
    class _QtCoreNS:
        QObject = QObject
        QTimer = QTimer
        Signal = Signal
        Qt = Qt

    class _QtGuiNS:
        QAction = QAction

    class _QtWidgetsNS:
        QApplication = QApplication
        QMainWindow = QMainWindow
        QWidget = QWidget
        QDockWidget = QDockWidget
        QToolBar = QToolBar
        QLabel = QLabel
        QPushButton = QPushButton
        QLineEdit = QLineEdit
        QSpinBox = QSpinBox
        QComboBox = QComboBox
        QTableWidget = QTableWidget
        QTableWidgetItem = QTableWidgetItem
        QTreeWidget = QTreeWidget
        QTreeWidgetItem = QTreeWidgetItem
        QPlainTextEdit = QPlainTextEdit
        QTextEdit = QTextEdit
        QStatusBar = QStatusBar
        QTabWidget = QTabWidget
        QMessageBox = QMessageBox
        QFileDialog = QFileDialog
        QVBoxLayout = QVBoxLayout
        QHBoxLayout = QHBoxLayout
        QFormLayout = QFormLayout
        QGridLayout = QGridLayout
        QGroupBox = QGroupBox
        QSplitter = QSplitter
        QHeaderView = QHeaderView

    QtCore = _QtCoreNS()  # type: ignore[assignment]
    QtGui = _QtGuiNS()  # type: ignore[assignment]
    QtWidgets = _QtWidgetsNS()  # type: ignore[assignment]

# Convenience exports used by UI modules
if HAS_QT_WIDGETS:
    QObject = QtCore.QObject
    QTimer = QtCore.QTimer
    Qt = QtCore.Qt
    try:
        Signal = QtCore.Signal
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        from PySide6.QtGui import QAction  # type: ignore
    except Exception:  # noqa: BLE001
        QAction = getattr(QtGui, "QAction", None)  # type: ignore
    QApplication = QtWidgets.QApplication
    QMainWindow = QtWidgets.QMainWindow
    QWidget = QtWidgets.QWidget
    QDockWidget = QtWidgets.QDockWidget
    QToolBar = QtWidgets.QToolBar
    QLabel = QtWidgets.QLabel
    QPushButton = QtWidgets.QPushButton
    QLineEdit = QtWidgets.QLineEdit
    QSpinBox = QtWidgets.QSpinBox
    QComboBox = QtWidgets.QComboBox
    QTableWidget = QtWidgets.QTableWidget
    QTableWidgetItem = QtWidgets.QTableWidgetItem
    QTreeWidget = QtWidgets.QTreeWidget
    QTreeWidgetItem = QtWidgets.QTreeWidgetItem
    QPlainTextEdit = QtWidgets.QPlainTextEdit
    QTextEdit = QtWidgets.QTextEdit
    QStatusBar = QtWidgets.QStatusBar
    QTabWidget = QtWidgets.QTabWidget
    QMessageBox = QtWidgets.QMessageBox
    QFileDialog = QtWidgets.QFileDialog
    QVBoxLayout = QtWidgets.QVBoxLayout
    QHBoxLayout = QtWidgets.QHBoxLayout
    QFormLayout = QtWidgets.QFormLayout
    QGridLayout = QtWidgets.QGridLayout
    QGroupBox = QtWidgets.QGroupBox
    QSplitter = QtWidgets.QSplitter
    QHeaderView = QtWidgets.QHeaderView
