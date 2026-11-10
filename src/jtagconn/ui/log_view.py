from __future__ import annotations

import time
from typing import Any

from jtagconn.core.logging_service import LogEntry, OperationLogger

from ._qt import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class LogView(QWidget):
    """Diagnostic log view subscribed to OperationLogger with level filtering and clear."""

    def __init__(self, logger: OperationLogger | None = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.level_filter = QComboBox(self)
        for lvl in ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"]:
            try:
                self.level_filter.addItem(lvl)
            except Exception:  # noqa: BLE001, S110
                pass
        self.text = QPlainTextEdit(self)
        try:
            self.text.setReadOnly(True)
        except Exception:  # noqa: BLE001, S110
            pass
        self.clear_button = QPushButton("Clear Log", self)

        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)
            top = QHBoxLayout()
            top.addWidget(QLabel("Log Level:", self))
            top.addWidget(self.level_filter)
            top.addStretch(1)
            top.addWidget(self.clear_button)
            layout.addLayout(top)
            layout.addWidget(self.text, 1)
        except Exception:  # noqa: BLE001, S110
            pass

        self._logger: OperationLogger | None = None
        self._entries: list[LogEntry] = []
        self._listener = self._on_log_entry

        try:
            self.level_filter.currentTextChanged.connect(lambda *_: self._render())
        except Exception:  # noqa: BLE001
            try:
                self.level_filter.currentIndexChanged.connect(lambda *_: self._render())
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            self.clear_button.clicked.connect(self.clear)
        except Exception:  # noqa: BLE001, S110
            pass

        if logger is not None:
            self.set_logger(logger)

    def set_logger(self, logger: OperationLogger) -> None:
        if self._logger is not None:
            try:
                self._logger.remove_listener(self._listener)
            except Exception:  # noqa: BLE001, S110
                pass
        self._logger = logger
        self._entries = list(logger.entries())
        try:
            logger.add_listener(self._listener)
        except Exception:  # noqa: BLE001, S110
            pass
        self._render()

    def _on_log_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        self._render(append_only=True, new_entry=entry)

    def clear(self) -> None:
        self._entries = []
        if self._logger is not None:
            try:
                self._logger.clear()
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            self.text.clear()
        except Exception:  # noqa: BLE001, S110
            pass

    def _selected_level(self) -> str:
        try:
            return self.level_filter.currentText().upper()
        except Exception:  # noqa: BLE001
            return "ALL"

    def _entry_matches(self, entry: LogEntry) -> bool:
        lvl = self._selected_level()
        if lvl == "ALL":
            return True
        return str(getattr(entry, "level", "")).upper() == lvl

    def _format_entry(self, entry: LogEntry) -> str:
        ts = getattr(entry, "timestamp", time.time())
        try:
            ts_text = time.strftime("%H:%M:%S", time.localtime(float(ts)))
        except Exception:  # noqa: BLE001
            ts_text = str(ts)
        level = str(getattr(entry, "level", "info")).upper()
        op = str(getattr(entry, "operation", ""))
        core = getattr(entry, "core", None)
        msg = str(getattr(entry, "message", ""))
        dur = getattr(entry, "duration_ms", None)
        core_part = f" [{core}]" if core else ""
        dur_part = f" ({dur} ms)" if dur is not None else ""
        return f"{ts_text} {level}{core_part} {op}: {msg}{dur_part}".strip()

    def _render(self, append_only: bool = False, new_entry: LogEntry | None = None) -> None:
        if append_only and new_entry is not None:
            if self._entry_matches(new_entry):
                try:
                    self.text.appendPlainText(self._format_entry(new_entry))
                except Exception:  # noqa: BLE001, S110
                    pass
            return
        try:
            self.text.clear()
        except Exception:  # noqa: BLE001, S110
            pass
        for entry in self._entries:
            if self._entry_matches(entry):
                try:
                    self.text.appendPlainText(self._format_entry(entry))
                except Exception:  # noqa: BLE001, S110
                    pass
