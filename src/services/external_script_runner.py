import subprocess
import uuid
from collections import deque
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import (
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Signal,
)


@dataclass
class ExternalScriptTask:
    """Represents a single external command execution request."""

    task_id: str
    command: List[str]
    blocking: bool = False
    retries: int = 0
    attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    working_dir: Optional[str] = None
    description: Optional[str] = None
    env: Optional[Dict[str, str]] = None

    def next_attempt(self) -> int:
        self.attempts += 1
        return self.attempts


class ExternalScriptRunner(QObject):
    """
    Queue-based runner that standardises execution of helper scripts.

    Emits Qt signals so GUI components can react to lifecycle changes:
      - started(task_id, attempt, metadata)
      - finished(task_id, exit_code, metadata)
      - error(task_id, exit_code, message, metadata)
      - log_message(task_id, level, message, metadata)
    """

    started = Signal(str, int, object)
    finished = Signal(str, int, object)
    error = Signal(str, int, str, object)
    log_message = Signal(str, str, str, object)

    def __init__(self, max_concurrent: int = 1, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.max_concurrent = max(1, max_concurrent)
        self._queue: deque[ExternalScriptTask] = deque()
        self._active: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_task(
        self,
        command: Iterable[str],
        *,
        blocking: bool = False,
        retries: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
        working_dir: Optional[str] = None,
        description: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Optional[int]]:
        """
        Schedule a command for execution.

        Returns (task_id, exit_code). For asynchronous tasks exit_code is None.
        """
        task = ExternalScriptTask(
            task_id=str(uuid.uuid4()),
            command=list(command),
            blocking=blocking,
            retries=retries,
            metadata=metadata or {},
            input_path=input_path,
            output_path=output_path,
            working_dir=working_dir,
            description=description,
            env=env,
        )

        if blocking:
            exit_code = self._run_blocking_task(task)
            return task.task_id, exit_code

        self._queue.append(task)
        QTimer.singleShot(0, self._try_start_next)
        return task.task_id, None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued or running task."""
        # Cancel queued task
        for task in list(self._queue):
            if task.task_id == task_id:
                self._queue.remove(task)
                self.error.emit(task_id, -1, "Task cancelled before execution.", task.metadata)
                return True

        # Cancel running task
        record = self._active.get(task_id)
        if not record:
            return False

        record["cancelled"] = True
        process: QProcess = record["process"]
        process.kill()
        return True

    def cancel_all(self) -> None:
        """Cancel all pending and active tasks."""
        while self._queue:
            task = self._queue.popleft()
            self.error.emit(task.task_id, -1, "Task cancelled before execution.", task.metadata)

        for task_id in list(self._active.keys()):
            self.cancel_task(task_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _try_start_next(self) -> None:
        while len(self._active) < self.max_concurrent and self._queue:
            task = self._queue.popleft()
            self._start_async_task(task)

    def _start_async_task(self, task: ExternalScriptTask) -> None:
        attempt = task.next_attempt()
        process = QProcess(self)
        if task.working_dir:
            process.setWorkingDirectory(task.working_dir)
        if task.env:
            env = QProcessEnvironment.systemEnvironment()
            for key, value in task.env.items():
                env.insert(key, value)
            process.setProcessEnvironment(env)

        self._active[task.task_id] = {
            "process": process,
            "task": task,
            "cancelled": False,
        }

        self.started.emit(task.task_id, attempt, task.metadata)
        if task.description:
            self.log_message.emit(
                task.task_id,
                "info",
                f"{task.description} (attempt {attempt})",
                task.metadata,
            )

        if task.input_path:
            self.log_message.emit(
                task.task_id,
                "debug",
                f"Input: {task.input_path}",
                task.metadata,
            )
        if task.output_path:
            self.log_message.emit(
                task.task_id,
                "debug",
                f"Output: {task.output_path}",
                task.metadata,
            )

        process.readyReadStandardOutput.connect(partial(self._handle_stdout, task.task_id))
        process.readyReadStandardError.connect(partial(self._handle_stderr, task.task_id))
        process.errorOccurred.connect(partial(self._handle_process_error, task.task_id))
        process.finished.connect(partial(self._handle_finished, task.task_id))

        process.start(task.command[0], task.command[1:])

    def _run_blocking_task(self, task: ExternalScriptTask) -> int:
        attempt = task.next_attempt()
        self.started.emit(task.task_id, attempt, task.metadata)
        if task.description:
            self.log_message.emit(
                task.task_id,
                "info",
                f"{task.description} (blocking attempt {attempt})",
                task.metadata,
            )

        try:
            result = subprocess.run(
                task.command,
                cwd=task.working_dir,
                env=task.env,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.log_message.emit(task.task_id, "info", line, task.metadata)
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.log_message.emit(task.task_id, "error", line, task.metadata)

            if result.returncode == 0:
                self.finished.emit(task.task_id, result.returncode, task.metadata)
            else:
                self._emit_or_retry_blocking_failure(task, result.returncode)
            return result.returncode
        except FileNotFoundError as exc:
            message = f"Command not found: {exc}"
            self.error.emit(task.task_id, -1, message, task.metadata)
            return -1
        except Exception as exc:  # pragma: no cover - safety net
            self.error.emit(task.task_id, -1, str(exc), task.metadata)
            return -1

    def _emit_or_retry_blocking_failure(self, task: ExternalScriptTask, exit_code: int) -> None:
        if task.attempts <= task.retries:
            self.log_message.emit(
                task.task_id,
                "warning",
                f"Command failed with exit code {exit_code}. Retrying (attempt {task.attempts + 1}).",
                task.metadata,
            )
            self._run_blocking_task(task)
            return
        self.error.emit(
            task.task_id,
            exit_code,
            f"Command exited with code {exit_code}.",
            task.metadata,
        )

    def _handle_stdout(self, task_id: str) -> None:
        record = self._active.get(task_id)
        if not record:
            return
        process: QProcess = record["process"]
        data = process.readAllStandardOutput().data().decode(errors="ignore")
        if not data:
            return
        for line in data.splitlines():
            if line:
                self.log_message.emit(task_id, "info", line, record["task"].metadata)

    def _handle_stderr(self, task_id: str) -> None:
        record = self._active.get(task_id)
        if not record:
            return
        process: QProcess = record["process"]
        data = process.readAllStandardError().data().decode(errors="ignore")
        if not data:
            return
        for line in data.splitlines():
            if line:
                self.log_message.emit(task_id, "error", line, record["task"].metadata)

    def _handle_process_error(self, task_id: str, error: QProcess.ProcessError) -> None:
        record = self._active.get(task_id)
        if not record:
            return
        process: QProcess = record["process"]
        message = process.errorString() or f"Process error: {error}"
        self._finalize_task(task_id, record, exit_code=-1, message=message, is_error=True)

    def _handle_finished(self, task_id: str, exit_code: int, _status: QProcess.ExitStatus) -> None:
        record = self._active.pop(task_id, None)
        if not record:
            return

        cancelled = record.get("cancelled", False)
        task: ExternalScriptTask = record["task"]

        if cancelled:
            self.error.emit(task_id, exit_code, "Task cancelled.", task.metadata)
            self._try_start_next()
            return

        if exit_code == 0:
            self.finished.emit(task_id, exit_code, task.metadata)
            self._try_start_next()
            return

        if task.attempts <= task.retries:
            self.log_message.emit(
                task_id,
                "warning",
                f"Command exited with code {exit_code}. Retrying (attempt {task.attempts + 1}).",
                task.metadata,
            )
            self._queue.append(task)
            QTimer.singleShot(0, self._try_start_next)
            return

        message = f"Command exited with code {exit_code}."
        self.error.emit(task_id, exit_code, message, task.metadata)
        self._try_start_next()

    def _finalize_task(
        self,
        task_id: str,
        record: Dict[str, Any],
        *,
        exit_code: int,
        message: str,
        is_error: bool,
    ) -> None:
        self._active.pop(task_id, None)
        task: ExternalScriptTask = record["task"]
        if is_error:
            self.error.emit(task_id, exit_code, message, task.metadata)
        else:
            self.finished.emit(task_id, exit_code, task.metadata)
        self._try_start_next()
