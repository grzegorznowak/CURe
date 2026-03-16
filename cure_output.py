from __future__ import annotations

import hashlib
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from cure_branding import LEGACY_SLUG
from cure_errors import ReviewflowError
from run import run_cmd
from ui import Dashboard, TailBuffer, UiState, Verbosity, StreamSink


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

        self.reviewflow_log = (self.logs_dir / f"{LEGACY_SLUG}.log").open(
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
        for fh in (self.reviewflow_log, self.chunkhound_log, self.codex_log):
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass

    def log(self, line: str) -> None:
        try:
            self.reviewflow_log.write(line + "\n")
            self.reviewflow_log.flush()
        except Exception:
            pass
        if not self.ui_enabled:
            self.stderr.write(line + "\n")
            self.stderr.flush()
        self.state.ping()

    def eprint(self, line: str) -> None:
        try:
            self.reviewflow_log.write(line + "\n")
            self.reviewflow_log.flush()
        except Exception:
            pass
        if not self.ui_enabled:
            self.stderr.write(line + "\n")
            self.stderr.flush()
        self.state.ping()

    def stream_sink(self, kind: str) -> StreamSink:
        if kind == "chunkhound":
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
    ):
        stream = True if self.ui_enabled else bool(stream_requested)
        label = self.stream_label(kind) if stream else None
        if stream:
            return run_cmd(
                cmd,
                cwd=cwd,
                env=env,
                check=check,
                stream=True,
                stream_to=self.stream_sink(kind),
                stream_label=label,
            )
        res = run_cmd(cmd, cwd=cwd, env=env, check=check, stream=False)
        try:
            self.stream_sink(kind).write(res.stdout)
            self.stream_sink(kind).write(res.stderr)
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
