import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

_POLL_INTERVAL = 0.1
_TERMINATE_TIMEOUT = 5.0
_PROGRESS_ARGS = ("-progress", "pipe:1", "-nostats")
_INTERPRETER_PREFIXES = ("python", "pypy")
_INTERPRETER_VALUE_OPTIONS = frozenset({"-W", "-X", "-Q"})


@dataclass(frozen=True)
class Progress:
    percent: float
    seconds: float
    speed: str


class Cancelled(Exception):
    pass


def _is_interpreter(executable):
    name = os.path.basename(executable).lower()
    return any(name.startswith(prefix) for prefix in _INTERPRETER_PREFIXES)


def _with_progress_args(args):
    """Insert FFmpeg's global progress flags into a command.

    For normal tools the flags go immediately after the executable. Interpreters
    (Python/PyPy) are exempt because the test harnesses run Python scripts and an
    interpreter rejects FFmpeg's flags as its own options; for those the flags
    follow the script/module/code argument so fake scripts still receive them.
    """
    command = list(args)
    if not command:
        raise ValueError("args must not be empty")

    index = 1
    if _is_interpreter(command[0]):
        while index < len(command):
            argument = command[index]
            if argument in ("-c", "-m"):
                index = min(index + 2, len(command))
                break
            if argument.startswith("-") and argument != "-":
                index += 2 if argument in _INTERPRETER_VALUE_OPTIONS else 1
                continue
            index += 1
            break

    command[index:index] = _PROGRESS_ARGS
    return command


def _read_lines(stream, lines):
    try:
        for line in stream:
            lines.put(line)
    finally:
        lines.put(None)


def _stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_with_progress(
    args: list,
    duration_s: float,
    *,
    progress: Optional[Callable[[Progress], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> int:
    process = subprocess.Popen(
        _with_progress_args(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = queue.Queue()
    reader = threading.Thread(
        target=_read_lines, args=(process.stdout, lines), daemon=True
    )
    reader.start()

    seconds = 0.0
    speed = ""
    pending = False

    def report():
        if progress is None:
            return
        percent = 0.0
        if duration_s > 0:
            percent = min(100.0, seconds / duration_s * 100.0)
        progress(Progress(percent=percent, seconds=seconds, speed=speed))

    try:
        while True:
            if cancel is not None and cancel.is_set():
                _stop(process)
                raise Cancelled()
            try:
                line = lines.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                continue
            if line is None:
                break

            key, separator, value = line.strip().partition("=")
            if not separator:
                continue
            if key in ("out_time_ms", "out_time_us"):
                try:
                    seconds = float(value) / 1_000_000.0
                except (TypeError, ValueError):
                    continue
                pending = True
            elif key == "speed":
                speed = value.strip()
            elif key == "progress":
                if pending:
                    report()
                    pending = False

        if pending:
            report()
        return process.wait()
    finally:
        if process.poll() is None:
            _stop(process)
        reader.join(timeout=_POLL_INTERVAL)
        process.stdout.close()
