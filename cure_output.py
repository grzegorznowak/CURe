from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO, cast

from chunkhound_summary import parse_chunkhound_index_summary
from cure_branding import RUNTIME_SLUG
from cure_errors import ReviewflowError
from run import run_cmd
from ui import Dashboard, TailBuffer, UiState, Verbosity, StreamSink

CURE_PROJECT_URL = "https://github.com/grzegorznowak/CURe"
_REVIEW_ARTIFACT_FOOTER_BLOCK_RE = re.compile(
    r"\n*---\n<!-- CURE_REVIEW_FOOTER_START -->\n.*?\n<!-- CURE_REVIEW_FOOTER_END -->\n*",
    re.DOTALL,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _compact_codex_text(text: str, *, max_chars: int = 240) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1] + "…"


def _progress_meta_dict(progress: Any) -> dict[str, Any] | None:
    meta = getattr(progress, "meta", None)
    return meta if isinstance(meta, dict) else None


def _flush_progress(progress: Any) -> None:
    flush = getattr(progress, "flush", None)
    if callable(flush):
        try:
            flush()
        except Exception:
            pass


_LIVE_PROGRESS_TIMELINE_MAX = 12


class ChunkhoundLiveProgressReporter:
    _PHASE_LABELS: dict[str, tuple[str, str]] = {
        "base_cache": ("Preparing base cache refresh", "Refreshing base cache"),
        "topup": ("Preparing session index top-up", "Building session index top-up"),
        "followup": ("Preparing follow-up index", "Building follow-up index"),
    }

    def __init__(self, *, progress: Any, scope: str) -> None:
        self._progress = progress
        self._scope = str(scope or "").strip() or "topup"
        self._source = "chunkhound_cache_build"
        self._started_mono: float | None = None
        self._running = False
        self._active = False
        self._summary: dict[str, Any] | None = None
        self._summary_key = ""
        self._lines: list[str] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        meta = _progress_meta_dict(self._progress)
        if meta is None:
            return
        now = _utc_now_iso()
        with self._lock:
            self._started_mono = time.monotonic()
            self._running = False
            self._active = True
            self._set_live_progress_locked(
                text=self._build_message_locked(),
                timestamp=now,
                event_type="chunkhound_cache_prepare",
                add_timeline=True,
            )
            self._ensure_thread_locked()

    def mark_running(self) -> None:
        meta = _progress_meta_dict(self._progress)
        if meta is None:
            return
        now = _utc_now_iso()
        with self._lock:
            if not self._active:
                return
            self._running = True
            self._set_live_progress_locked(
                text=self._build_message_locked(),
                timestamp=now,
                event_type="chunkhound_cache_active",
                add_timeline=True,
            )

    def consume_text(self, text: str) -> None:
        if not text:
            return
        meta = _progress_meta_dict(self._progress)
        if meta is None:
            return
        cleaned_lines: list[str] = []
        for raw_line in str(text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("[chunkhound] "):
                line = line[len("[chunkhound] ") :]
            cleaned_lines.append(line)
        if not cleaned_lines:
            return
        now = _utc_now_iso()
        with self._lock:
            if not self._active:
                return
            self._running = True
            self._lines.extend(cleaned_lines)
            if len(self._lines) > 200:
                self._lines = self._lines[-200:]
            parsed = parse_chunkhound_index_summary(self._lines, scope=self._scope)
            summary_key = json.dumps(parsed, sort_keys=True) if isinstance(parsed, dict) else ""
            if isinstance(parsed, dict):
                self._summary = parsed
            if summary_key != self._summary_key:
                self._summary_key = summary_key
            self._set_live_progress_locked(
                text=self._build_message_locked(),
                timestamp=now,
                event_type="chunkhound_cache_active",
                add_timeline=False,
            )

    def finish(self, *, status: str) -> dict[str, Any] | None:
        thread: threading.Thread | None = None
        with self._lock:
            self._active = False
            self._stop_event.set()
            thread = self._thread
            summary = dict(self._summary) if isinstance(self._summary, dict) else None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        meta = _progress_meta_dict(self._progress)
        if meta is None:
            return summary
        with self._lock:
            live = meta.get("live_progress")
            if not isinstance(live, dict) or live.get("source") != self._source:
                return summary
            if isinstance(summary, dict):
                chunkhound_value = meta.get("chunkhound")
                chunkhound: dict[str, Any] = (
                    dict(cast(dict[str, Any], chunkhound_value))
                    if isinstance(chunkhound_value, dict)
                    else {}
                )
                chunkhound["last_index"] = dict(summary)
                meta["chunkhound"] = chunkhound
            if str(status or "").strip().lower() == "error":
                timestamp = _utc_now_iso()
                live["status"] = "error"
                live["updated_at"] = timestamp
                live["current"] = {
                    "type": "chunkhound_cache_error",
                    "text": self._build_failure_message_locked(),
                    "ts": timestamp,
                }
                meta["live_progress"] = live
            else:
                meta.pop("live_progress", None)
            _flush_progress(self._progress)
        return summary

    def _ensure_thread_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(1.0):
            meta = _progress_meta_dict(self._progress)
            if meta is None:
                return
            with self._lock:
                if not self._active:
                    return
                self._set_live_progress_locked(
                    text=self._build_message_locked(),
                    timestamp=_utc_now_iso(),
                    event_type="chunkhound_cache_active" if self._running else "chunkhound_cache_prepare",
                    add_timeline=False,
                )

    def _label_pair_locked(self) -> tuple[str, str]:
        return self._PHASE_LABELS.get(
            self._scope,
            ("Preparing ChunkHound cache build", "Building ChunkHound cache"),
        )

    def _elapsed_seconds_locked(self) -> int:
        if self._started_mono is None:
            return 0
        return max(0, int(time.monotonic() - self._started_mono))

    def _summary_groups_locked(self) -> list[str]:
        summary = self._summary if isinstance(self._summary, dict) else {}
        groups: list[str] = []

        run_bits: list[str] = []
        if isinstance(summary.get("processed_files"), int):
            run_bits.append(f"{summary['processed_files']} proc")
        if isinstance(summary.get("skipped_files"), int):
            run_bits.append(f"{summary['skipped_files']} skip")
        if isinstance(summary.get("error_files"), int):
            run_bits.append(f"{summary['error_files']} err")
        if run_bits:
            groups.append("/".join(run_bits))

        output_bits: list[str] = []
        if isinstance(summary.get("total_chunks"), int):
            output_bits.append(f"{summary['total_chunks']} chunks")
        if isinstance(summary.get("embeddings"), int):
            output_bits.append(f"{summary['embeddings']} emb")
        if output_bits:
            groups.append("/".join(output_bits))

        if not groups:
            before_bits: list[str] = []
            if isinstance(summary.get("initial_files"), int):
                before_bits.append(f"{summary['initial_files']} files")
            if isinstance(summary.get("initial_chunks"), int):
                before_bits.append(f"{summary['initial_chunks']} chunks")
            if isinstance(summary.get("initial_embeddings"), int):
                before_bits.append(f"{summary['initial_embeddings']} emb")
            if before_bits:
                groups.append("/".join(before_bits))

        return groups

    def _build_message_locked(self) -> str:
        prepare_label, active_label = self._label_pair_locked()
        label = active_label if self._running else prepare_label
        parts = [label, f"{self._elapsed_seconds_locked()}s"]
        parts.extend(self._summary_groups_locked())
        return " · ".join(part for part in parts if part)

    def _build_failure_message_locked(self) -> str:
        _, active_label = self._label_pair_locked()
        return f"{active_label} failed after {self._elapsed_seconds_locked()}s"

    def _set_live_progress_locked(
        self,
        *,
        text: str,
        timestamp: str,
        event_type: str,
        add_timeline: bool,
    ) -> None:
        meta = _progress_meta_dict(self._progress)
        if meta is None:
            return
        live_value = meta.get("live_progress")
        live: dict[str, Any] = (
            dict(cast(dict[str, Any], live_value)) if isinstance(live_value, dict) else {}
        )
        live["source"] = self._source
        live["provider"] = "chunkhound"
        live["scope"] = self._scope
        live["status"] = "running"
        live["updated_at"] = timestamp
        current = {"type": event_type, "text": text, "ts": timestamp}
        live["current"] = current
        if add_timeline:
            timeline_value = live.get("timeline")
            timeline = (
                list(cast(list[dict[str, Any]], timeline_value))
                if isinstance(timeline_value, list)
                else []
            )
            last = timeline[-1] if timeline and isinstance(timeline[-1], dict) else {}
            if last.get("type") != event_type or last.get("text") != text:
                timeline.append(current)
            if len(timeline) > _LIVE_PROGRESS_TIMELINE_MAX:
                timeline = timeline[-_LIVE_PROGRESS_TIMELINE_MAX:]
            live["timeline"] = timeline
        meta["live_progress"] = live
        _flush_progress(self._progress)


class _TextCallbackSink:
    def __init__(self, sink: TextIO, callback: Callable[[str], None]) -> None:
        self._sink = sink
        self._callback = callback

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        written = self._sink.write(s)
        try:
            self._callback(s)
        except Exception:
            pass
        return written

    def flush(self) -> None:
        self._sink.flush()


class CodexJsonEventSink:
    """Stream Codex JSONL to a raw log while preserving readable tails for the dashboard."""

    def __init__(
        self,
        *,
        raw_file: TextIO,
        display_file: TextIO,
        tail: TailBuffer,
        also_to: TextIO | None = None,
        on_activity: Callable[[], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._raw_file = raw_file
        self._display_file = display_file
        self._tail = tail
        self._also_to = also_to
        self._on_activity = on_activity
        self._on_event = on_event
        self._lock = threading.Lock()
        self._pending = ""

    def writable(self) -> bool:
        return True

    def _emit_display_line(self, line: str) -> None:
        text = str(line or "").strip()
        if not text:
            return
        rendered = text + "\n"
        self._display_file.write(rendered)
        self._display_file.flush()
        self._tail.append_text(text)
        if self._also_to is not None:
            self._also_to.write(rendered)
            self._also_to.flush()

    def _normalize_event(self, payload: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
        event_type = str(payload.get("type") or "").strip()
        timestamp = _utc_now_iso()

        if event_type == "thread.started":
            text = "Codex session started."
            return ([text], {"type": "thread_started", "text": text, "ts": timestamp, "replace_current": True})

        if event_type == "turn.started":
            text = "Review turn started."
            return ([text], {"type": "turn_started", "text": text, "ts": timestamp, "replace_current": True})

        if event_type == "item.completed":
            item = payload.get("item")
            item = item if isinstance(item, dict) else {}
            if str(item.get("type") or "").strip() == "agent_message":
                raw_text = str(item.get("text") or "")
                text = _compact_codex_text(raw_text)
                if text:
                    return (
                        [text],
                        {
                            "type": "agent_message",
                            "text": text,
                            "raw_text": raw_text,
                            "ts": timestamp,
                            "replace_current": True,
                        },
                    )
            return ([], None)

        if event_type == "turn.completed":
            usage = payload.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            output_tokens = usage.get("output_tokens")
            text = "Review turn completed."
            if isinstance(output_tokens, int):
                text = f"Review turn completed ({output_tokens} output tok)."
            return ([text], {"type": "turn_completed", "text": text, "ts": timestamp, "replace_current": False})

        return ([], None)

    def _consume_line(self, line: str) -> None:
        text = str(line or "").rstrip("\r")
        if not text.strip():
            return
        try:
            payload = json.loads(text)
        except Exception:
            self._emit_display_line(_compact_codex_text(text))
            return
        if not isinstance(payload, dict):
            return
        lines, event = self._normalize_event(payload)
        for display_line in lines:
            self._emit_display_line(display_line)
        if event is not None and self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                pass

    def write(self, s: str) -> int:
        if not s:
            return 0
        with self._lock:
            self._raw_file.write(s)
            self._raw_file.flush()
            self._pending += s
            while "\n" in self._pending:
                line, self._pending = self._pending.split("\n", 1)
                self._consume_line(line)
        if self._on_activity is not None:
            try:
                self._on_activity()
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        with self._lock:
            if self._pending.strip():
                self._consume_line(self._pending)
            self._pending = ""
            self._raw_file.flush()
            self._display_file.flush()
            if self._also_to is not None:
                self._also_to.flush()


class ReviewflowOutput:
    def __init__(
        self,
        *,
        ui_enabled: bool,
        no_stream: bool,
        stderr: TextIO,
        meta_path: Path,
        logs_dir: Path,
        verbosity: Verbosity,
    ) -> None:
        self.ui_enabled = bool(ui_enabled)
        self.no_stream = bool(no_stream)
        self.stderr = stderr
        self.meta_path = meta_path
        self.logs_dir = logs_dir
        self.verbosity = verbosity
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.cure_log = (self.logs_dir / f"{RUNTIME_SLUG}.log").open(
            "a", encoding="utf-8", buffering=1
        )
        self.chunkhound_log = (self.logs_dir / "chunkhound.log").open(
            "a", encoding="utf-8", buffering=1
        )
        self.codex_log = (self.logs_dir / "codex.log").open("a", encoding="utf-8", buffering=1)

        self.state = UiState(verbosity=verbosity)
        self.tails: dict[str, TailBuffer] = {
            "chunkhound": TailBuffer(max_lines=200),
            "codex": TailBuffer(max_lines=400),
        }

        also_to = (
            None
            if (self.ui_enabled or self.no_stream or self.verbosity is Verbosity.quiet)
            else self.stderr
        )
        self.chunkhound_sink = StreamSink(
            label="chunkhound",
            file=self.chunkhound_log,
            tail=self.tails["chunkhound"],
            also_to=also_to,
            on_activity=self.state.ping,
        )
        self.codex_sink = StreamSink(
            label="codex",
            file=self.codex_log,
            tail=self.tails["codex"],
            also_to=also_to,
            on_activity=self.state.ping,
        )

        self.dashboard: Dashboard | None = None
        if self.ui_enabled:
            self.dashboard = Dashboard(
                meta_path=self.meta_path,
                state=self.state,
                tails=self.tails,
                stderr=self.stderr,
                no_stream=self.no_stream,
                refresh_hz=5.0,
            )

    def start(self) -> None:
        if self.dashboard is not None:
            self.dashboard.start()

    def stop(self) -> None:
        if self.dashboard is not None:
            self.dashboard.stop()
        for fh in (self.cure_log, self.chunkhound_log, self.codex_log):
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass

    def log(self, line: str) -> None:
        try:
            self.cure_log.write(line + "\n")
            self.cure_log.flush()
        except Exception:
            pass
        if not self.ui_enabled:
            self.stderr.write(line + "\n")
            self.stderr.flush()
        self.state.ping()

    def eprint(self, line: str) -> None:
        try:
            self.cure_log.write(line + "\n")
            self.cure_log.flush()
        except Exception:
            pass
        if not self.ui_enabled:
            self.stderr.write(line + "\n")
            self.stderr.flush()
        self.state.ping()

    def stream_sink(self, kind: str) -> StreamSink:
        if kind in {"chunkhound", "jira"}:
            return self.chunkhound_sink
        if kind == "codex":
            return self.codex_sink
        raise ReviewflowError(f"Unknown stream kind: {kind}")

    def stream_label(self, kind: str) -> str | None:
        return None if self.ui_enabled else kind

    def run_logged_cmd(
        self,
        cmd: list[str],
        *,
        kind: str,
        cwd: Path | None,
        env: dict[str, str] | None,
        check: bool,
        stream_requested: bool,
        codex_json_events_path: Path | None = None,
        codex_event_callback: Callable[[dict[str, Any]], None] | None = None,
        stream_text_callback: Callable[[str], None] | None = None,
    ):
        capture_codex_json = kind == "codex" and codex_json_events_path is not None
        stream = True if (self.ui_enabled or capture_codex_json) else bool(stream_requested)
        label = None if capture_codex_json else (self.stream_label(kind) if stream else None)
        if stream:
            sink: Any = self.stream_sink(kind)
            raw_fh: TextIO | None = None
            try:
                if capture_codex_json:
                    assert codex_json_events_path is not None
                    codex_json_events_path.parent.mkdir(parents=True, exist_ok=True)
                    raw_fh = codex_json_events_path.open("a", encoding="utf-8", buffering=1)
                    also_to = (
                        None
                        if (self.ui_enabled or self.no_stream or self.verbosity is Verbosity.quiet)
                        else self.stderr
                    )
                    sink = CodexJsonEventSink(
                        raw_file=raw_fh,
                        display_file=self.codex_log,
                        tail=self.tails["codex"],
                        also_to=also_to,
                        on_activity=self.state.ping,
                        on_event=codex_event_callback,
                    )
                if stream_text_callback is not None:
                    sink = _TextCallbackSink(sink, stream_text_callback)
                return run_cmd(
                    cmd,
                    cwd=cwd,
                    env=env,
                    check=check,
                    stream=True,
                    stream_to=sink,
                    stream_label=label,
                )
            finally:
                if raw_fh is not None:
                    try:
                        sink.flush()
                    except Exception:
                        pass
                    try:
                        raw_fh.flush()
                        raw_fh.close()
                    except Exception:
                        pass
        res = run_cmd(cmd, cwd=cwd, env=env, check=check, stream=False)
        try:
            self.stream_sink(kind).write(res.stdout)
            self.stream_sink(kind).write(res.stderr)
        except Exception:
            pass
        if stream_text_callback is not None:
            for chunk in (res.stdout, res.stderr):
                if not chunk:
                    continue
                try:
                    stream_text_callback(chunk)
                except Exception:
                    pass
        return res


_ACTIVE_OUTPUT: ReviewflowOutput | None = None


def active_output() -> ReviewflowOutput | None:
    return _ACTIVE_OUTPUT


def set_active_output(output: ReviewflowOutput | None) -> None:
    global _ACTIVE_OUTPUT
    _ACTIVE_OUTPUT = output


def clear_active_output(expected: ReviewflowOutput | None = None) -> None:
    global _ACTIVE_OUTPUT
    if expected is None or _ACTIVE_OUTPUT is expected:
        _ACTIVE_OUTPUT = None


def _eprint(*args: object) -> None:
    text = " ".join(str(a) for a in args)
    out = active_output()
    if out is not None:
        out.eprint(text)
        return
    print(*args, file=sys.stderr, flush=True)


def maybe_print_markdown_after_tui(*, ui_enabled: bool, stderr: TextIO, markdown_path: Path | None) -> None:
    if not ui_enabled:
        return
    if markdown_path is None:
        return
    if not markdown_path.is_file():
        return
    try:
        is_tty = bool(stderr.isatty())
    except Exception:
        is_tty = False
    if not is_tty:
        return
    try:
        body = markdown_path.read_text(encoding="utf-8")
    except Exception:
        return
    if not body.endswith("\n"):
        body += "\n"
    try:
        stderr.write("\x1b[2J\x1b[H")
        stderr.flush()
        stderr.write(body)
        stderr.flush()
    except Exception:
        return


def maybe_print_codex_resume_command(*, stderr: TextIO, command: str | None) -> None:
    return


def _shell_join(args: list[str]) -> str:
    return " ".join(shlex.quote(str(arg)) for arg in args)


def _linecol_suffix(*, line: str | None, col: str | None) -> str:
    if not line:
        return ""
    if col:
        return f":{line}:{col}"
    return f":{line}"


def _session_relative_display_path(*, session_dir: Path, target_path: Path) -> str | None:
    session_root = session_dir.resolve(strict=False)
    repo_root = (session_root / "repo").resolve(strict=False)
    resolved = target_path.resolve(strict=False)
    if resolved == repo_root or repo_root in resolved.parents:
        return resolved.relative_to(repo_root).as_posix()
    if resolved == session_root or session_root in resolved.parents:
        rel = resolved.relative_to(session_root).as_posix()
        return rel or resolved.name
    return None


def _normalize_local_target_ref(raw: str, *, session_dir: Path) -> str | None:
    text = str(raw or "").strip()
    if not text.startswith("/"):
        return None

    line: str | None = None
    col: str | None = None
    base = text
    if "#" in text:
        maybe_base, maybe_fragment = text.rsplit("#", 1)
        match = re.fullmatch(r"L(?P<line>\d+)(?:C(?P<col>\d+))?", maybe_fragment)
        if match:
            base = maybe_base
            line = match.group("line")
            col = match.group("col")

    display = _session_relative_display_path(session_dir=session_dir, target_path=Path(base))
    if display is None:
        return None
    return f"{display}{_linecol_suffix(line=line, col=col)}"


def normalize_markdown_local_refs(text: str, *, session_dir: Path) -> str:
    session_root = session_dir.resolve(strict=False)
    prefix = re.escape(str(session_root))
    link_re = re.compile(rf"\[(?P<label>[^\]]+)\]\((?P<target>{prefix}[^\s)]+)\)")
    raw_re = re.compile(rf"(?P<target>{prefix}[^\s),`]+(?:#L\d+(?:C\d+)?)?)")

    def replace_link(match: re.Match[str]) -> str:
        display = _normalize_local_target_ref(match.group("target"), session_dir=session_dir)
        return display or match.group(0)

    def replace_raw(match: re.Match[str]) -> str:
        display = _normalize_local_target_ref(match.group("target"), session_dir=session_dir)
        return display or match.group(0)

    rewritten = link_re.sub(replace_link, text)
    return raw_re.sub(replace_raw, rewritten)


def _strip_whole_document_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 3:
        return text
    start = 0
    end = len(lines) - 1
    while start <= end and not lines[start].strip():
        start += 1
    while end >= start and not lines[end].strip():
        end -= 1
    if (end - start + 1) < 3:
        return text
    first = lines[start].strip().lower()
    last = lines[end].strip()
    if last != "```":
        return text
    if first not in {"```", "```markdown", "```md"}:
        return text
    body = "\n".join(lines[start + 1 : end]).strip("\n")
    if not body:
        return ""
    return body + "\n"


def _normalize_review_subsection_headings(text: str) -> str:
    heading_map = {
        "**Strengths**:": "### Strengths",
        "### Strengths": "### Strengths",
        "**In Scope Issues**:": "### In Scope Issues",
        "### In Scope Issues": "### In Scope Issues",
        "**Out of Scope Issues**:": "### Out of Scope Issues",
        "### Out of Scope Issues": "### Out of Scope Issues",
        "**Reusability**:": "### Reusability",
        "### Reusability": "### Reusability",
    }
    lines = text.splitlines()
    out: list[str] = []
    changed = False
    for line in lines:
        stripped = line.strip()
        canonical = heading_map.get(stripped)
        if canonical is None:
            out.append(line)
            continue
        changed = changed or (stripped != canonical)
        if out and out[-1].strip():
            out.append("")
            changed = True
        out.append(canonical)
    if not changed:
        return text
    normalized = "\n".join(out)
    if text.endswith("\n"):
        normalized += "\n"
    return normalized


def normalize_markdown_artifact(*, markdown_path: Path, session_dir: Path) -> None:
    if not markdown_path.is_file():
        return
    original = markdown_path.read_text(encoding="utf-8")
    normalized = _strip_whole_document_markdown_fence(original)
    normalized = _normalize_review_subsection_headings(normalized)
    normalized = normalize_markdown_local_refs(normalized, session_dir=session_dir)
    if normalized != original:
        markdown_path.write_text(normalized, encoding="utf-8")


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_compact_token_count(value: int | None) -> str:
    if not isinstance(value, int) or value < 0:
        return "-"
    if value < 1000:
        return str(value)
    if value < 1_000_000:
        return f"{int(round(value / 1000.0))}k"
    return f"{int(round(value / 1_000_000.0))}m"


def _format_elapsed_short(*, created_at: str | None, completed_at: str | None) -> str:
    started = _parse_iso_datetime(created_at)
    finished = _parse_iso_datetime(completed_at)
    if started is None or finished is None:
        return "-"
    elapsed_seconds = int((finished - started).total_seconds())
    if elapsed_seconds < 0:
        return "-"
    hours, rem = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes}m{seconds}s"
    if minutes:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def format_review_artifact_footer(
    *,
    cure_version: str | None,
    stage_shape_label: str | None,
    review_head_sha: str | None,
    model: str | None,
    reasoning_effort: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    session_id: str | None,
    created_at: str | None,
    completed_at: str | None,
    project_url: str = CURE_PROJECT_URL,
) -> str:
    version_text = str(cure_version or "").strip() or "-"
    stage_text = str(stage_shape_label or "").strip() or "-"
    sha_text = str(review_head_sha or "").strip()
    short_sha = sha_text[:7] if sha_text else "-"
    model_text = str(model or "").strip() or "-"
    effort_text = str(reasoning_effort or "").strip() or "-"
    session_text = str(session_id or "").strip() or "-"
    elapsed_text = _format_elapsed_short(created_at=created_at, completed_at=completed_at)
    return (
        f"_review generated with [CURe]({project_url}) v. {version_text}"
        f" · {stage_text}"
        f" · sha {short_sha}"
        f" · model {model_text}/{effort_text}"
        f" · tok {_format_compact_token_count(input_tokens)}/"
        f"{_format_compact_token_count(output_tokens)}/"
        f"{_format_compact_token_count(total_tokens)}"
        f" · session {session_text}"
        f" · {elapsed_text}"
        "_"
    )


def upsert_review_artifact_footer(*, markdown_path: Path, footer_line: str) -> None:
    if not markdown_path.is_file():
        return
    original = markdown_path.read_text(encoding="utf-8")
    body = _REVIEW_ARTIFACT_FOOTER_BLOCK_RE.sub("\n", original).rstrip("\n")
    if not body:
        return
    updated = (
        f"{body}\n\n---\n"
        "<!-- CURE_REVIEW_FOOTER_START -->\n"
        f"{footer_line}\n"
        "<!-- CURE_REVIEW_FOOTER_END -->\n"
    )
    if updated != original:
        markdown_path.write_text(updated, encoding="utf-8")


def _now_hms_utc() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def log(msg: str, *, quiet: bool) -> None:
    if quiet:
        return
    line = f"{_now_hms_utc()} | {msg}"
    out = active_output()
    if out is not None:
        out.log(line)
        return
    _eprint(line)


def safe_cmd_for_meta(cmd: list[str], *, max_arg_chars: int = 200) -> list[str]:
    safe: list[str] = []
    for idx, arg in enumerate(cmd):
        text = str(arg)
        if cmd and cmd[0] == "codex" and idx == (len(cmd) - 1) and len(text) > max_arg_chars:
            safe.append(f"<prompt:{len(text)} chars>")
        elif len(text) > max_arg_chars:
            safe.append(f"<arg:{len(text)} chars>")
        else:
            safe.append(text)
    return safe


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
