from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import TextIO


class ReviewflowSubprocessError(RuntimeError):
    def __init__(
        self,
        *,
        cmd: list[str],
        cwd: Path | None,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        super().__init__(f"Command failed ({exit_code}): {' '.join(cmd)}")
        self.cmd = cmd
        self.cwd = cwd
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class CommandResult:
    cmd: list[str]
    cwd: Path | None
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str


class _TailBuffer:
    def __init__(self, max_chars: int) -> None:
        self._max_chars = max(0, int(max_chars))
        self._chunks: deque[str] = deque()
        self._size = 0

    def append(self, text: str) -> None:
        if not text or self._max_chars == 0:
            return
        self._chunks.append(text)
        self._size += len(text)
        while self._size > self._max_chars and self._chunks:
            removed = self._chunks.popleft()
            self._size -= len(removed)

    def get(self) -> str:
        if not self._chunks:
            return ""
        return "".join(self._chunks)


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    stream: bool = False,
    stream_to: TextIO | None = None,
    stream_label: str | None = None,
    capture_tail_chars: int = 200_000,
) -> CommandResult:
    started = time.perf_counter()
    if not stream:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        duration = time.perf_counter() - started

        result = CommandResult(
            cmd=cmd,
            cwd=cwd,
            exit_code=int(completed.returncode),
            duration_seconds=float(duration),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    else:
        out = stream_to or sys.stderr
        write_lock = Lock()

        stdout_tail = _TailBuffer(capture_tail_chars)
        stderr_tail = _TailBuffer(capture_tail_chars)

        prefix = ""
        if stream_label:
            prefix = f"[{stream_label}] "

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )

        assert proc.stdout is not None
        assert proc.stderr is not None

        def pump(src: TextIO, *, tail: _TailBuffer) -> None:
            for line in src:
                tail.append(line)
                with write_lock:
                    out.write(prefix + line)
                    out.flush()

        t_out = Thread(target=pump, args=(proc.stdout,), kwargs={"tail": stdout_tail})
        t_err = Thread(target=pump, args=(proc.stderr,), kwargs={"tail": stderr_tail})
        t_out.daemon = True
        t_err.daemon = True
        t_out.start()
        t_err.start()

        exit_code = int(proc.wait())
        t_out.join()
        t_err.join()

        duration = time.perf_counter() - started

        result = CommandResult(
            cmd=cmd,
            cwd=cwd,
            exit_code=exit_code,
            duration_seconds=float(duration),
            stdout=stdout_tail.get(),
            stderr=stderr_tail.get(),
        )

    if check and result.exit_code != 0:
        raise ReviewflowSubprocessError(
            cmd=cmd,
            cwd=cwd,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result


def merged_env(extra: dict[str, str] | None) -> dict[str, str]:
    base = dict(os.environ)
    if extra:
        base.update(extra)
    return base
