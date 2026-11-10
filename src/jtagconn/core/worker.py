from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

try:
    from PySide6.QtCore import QObject, Signal
except Exception:  # noqa: BLE001  # pragma: no cover - fallback when Qt unavailable
    class QObject:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _SignalDescriptor:
        def __init__(self) -> None:
            self._name = ""

        def __set_name__(self, owner: type, name: str) -> None:
            self._name = name

        def __get__(self, obj: Any, objtype: type | None = None) -> _SignalInstance:
            if obj is None:
                return _SignalInstance(None, self._name)
            signals = obj.__dict__.setdefault("_signals", {})
            inst = signals.get(self._name)
            if inst is None:
                inst = _SignalInstance(obj, self._name)
                signals[self._name] = inst
            return inst

    class _SignalInstance:
        def __init__(self, obj: Any, name: str) -> None:
            self._obj = obj
            self._name = name

        def connect(self, slot: Callable[..., Any]) -> None:
            if self._obj is None:
                return
            self._obj.__dict__.setdefault("_slots", {}).setdefault(self._name, []).append(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            if self._obj is None:
                return
            for slot in self._obj.__dict__.get("_slots", {}).get(self._name, []):
                try:
                    slot(*args, **kwargs)
                except Exception:  # noqa: BLE001, S110
                    pass

    class Signal:  # type: ignore[no-redef]
        def __init__(self, *args: Any) -> None:
            self._desc = _SignalDescriptor()

        def __set_name__(self, owner: type, name: str) -> None:
            self._desc.__set_name__(owner, name)

        def __get__(self, obj: Any, objtype: type | None = None) -> Any:
            return self._desc.__get__(obj, objtype)

from jtagconn.backend.base import DebugBackend


@dataclass
class _Task:
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: Future[Any]
    callback: Callable[[Any], None] | None = None
    err_callback: Callable[[BaseException], None] | None = None
    description: str = ""


class EngineWorker(QObject):
    """Background engine worker that executes backend commands sequentially.

    Uses a blocking queue with no polling loops, so it consumes 0% CPU when idle.
    """

    taskCompleted = Signal(object, object)  # (description, result)
    taskFailed = Signal(object, object)  # (description, exception)
    progressUpdated = Signal(object, int)  # (description, percent)

    def __init__(self, backend: DebugBackend, name: str = "EngineWorker") -> None:
        super().__init__()
        self.backend = backend
        self._queue: queue.Queue[_Task | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._stopping = threading.Event()
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive() and not self._stopping.is_set()

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        callback: Callable[[Any], None] | None = None,
        err_callback: Callable[[BaseException], None] | None = None,
        description: str = "",
        **kwargs: Any,
    ) -> Future[Any]:
        future: Future[Any] = Future()
        task = _Task(
            func=func,
            args=args,
            kwargs=kwargs,
            future=future,
            callback=callback,
            err_callback=err_callback,
            description=description or getattr(func, "__name__", "task"),
        )
        self._queue.put(task)
        return future

    def submit_backend_call(
        self,
        method_name: str,
        *args: Any,
        callback: Callable[[Any], None] | None = None,
        err_callback: Callable[[BaseException], None] | None = None,
        **kwargs: Any,
    ) -> Future[Any]:
        method = getattr(self.backend, method_name)
        return self.submit(
            method,
            *args,
            callback=callback,
            err_callback=err_callback,
            description=method_name,
            **kwargs,
        )

    def _run(self) -> None:
        while True:
            task = self._queue.get()  # blocking, zero busy-wait when idle
            if task is None:
                self._queue.task_done()
                break
            try:
                result = task.func(*task.args, **task.kwargs)
                if not task.future.done():
                    task.future.set_result(result)
                if task.callback:
                    try:
                        task.callback(result)
                    except Exception:  # noqa: BLE001, S110
                        pass
                self.taskCompleted.emit(task.description, result)
            except BaseException as exc:  # noqa: BLE001 - propagate all failures to caller
                if not task.future.done():
                    task.future.set_exception(exc)
                if task.err_callback:
                    try:
                        task.err_callback(exc)
                    except Exception:  # noqa: BLE001, S110
                        pass
                self.taskFailed.emit(task.description, exc)
            finally:
                self._queue.task_done()

    def shutdown(self, wait: bool = True, timeout: float | None = 5.0) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        self._queue.put(None)
        if wait:
            self._thread.join(timeout=timeout)
