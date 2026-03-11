from __future__ import annotations

import json
import os
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from shutil import get_terminal_size
from typing import Callable, TextIO


class Verbosity(str, Enum):
    quiet = "quiet"
    normal = "normal"
    debug = "debug"

    def cycle(self) -> "Verbosity":
        if self is Verbosity.quiet:
            return Verbosity.normal
        if self is Verbosity.normal:
            return Verbosity.debug
        return Verbosity.quiet


@dataclass(frozen=True)
class UiSnapshot:
    verbosity: Verbosity
    show_help: bool


class UiState:
    def __init__(self, *, verbosity: Verbosity) -> None:
        self._lock = threading.Lock()
        self._verbosity = verbosity
        self._show_help = False
        self._activity = threading.Event()
        self._stop = False
        self._force_redraw = False

    def snapshot(self) -> UiSnapshot:
        with self._lock:
            return UiSnapshot(verbosity=self._verbosity, show_help=self._show_help)

    def stop_requested(self) -> bool:
        with self._lock:
            return self._stop

    def request_stop(self) -> None:
        with self._lock:
            self._stop = True
        self.ping()

    def request_redraw(self) -> None:
        with self._lock:
            self._force_redraw = True
        self.ping()

    def consume_force_redraw(self) -> bool:
        with self._lock:
            val = self._force_redraw
            self._force_redraw = False
            return val

    def ping(self) -> None:
        self._activity.set()

    def wait_activity(self, timeout: float) -> None:
        self._activity.wait(timeout=timeout)
        self._activity.clear()

    def cycle_verbosity(self) -> None:
        with self._lock:
            self._verbosity = self._verbosity.cycle()
        self.ping()

    def set_verbosity(self, verbosity: Verbosity) -> None:
        with self._lock:
            self._verbosity = verbosity
        self.ping()

    def toggle_help(self) -> None:
        with self._lock:
            self._show_help = not self._show_help
        self.ping()


class TailBuffer:
    def __init__(self, *, max_lines: int = 200) -> None:
        self._lock = threading.Lock()
        self._max_lines = max(1, int(max_lines))
        self._lines: list[str] = []

    def append_text(self, text: str) -> None:
        if not text:
            return
        parts = text.splitlines(keepends=False)
        if not parts:
            return
        with self._lock:
            for line in parts:
                self._lines.append(line)
            if len(self._lines) > self._max_lines:
                self._lines = self._lines[-self._max_lines :]

    def tail(self, n: int) -> list[str]:
        n = max(0, int(n))
        if n == 0:
            return []
        with self._lock:
            return list(self._lines[-n:])


def _normalize_verdict(raw: object) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.strip("[]").strip()
    text = text.strip("*").strip()
    if text.startswith("`") and text.endswith("`") and len(text) >= 2:
        text = text[1:-1].strip()
    text = " ".join(text.split())
    upper = text.upper()
    if upper in {"APPROVE", "REJECT"}:
        return upper
    if upper in {"REQUEST CHANGES", "REQUEST_CHANGES"}:
        return "REQUEST CHANGES"
    return text or None


def _format_verdicts(meta: dict[str, object]) -> str:
    verdicts = meta.get("verdicts")
    biz = None
    tech = None
    if isinstance(verdicts, dict):
        biz = _normalize_verdict(verdicts.get("business"))
        tech = _normalize_verdict(verdicts.get("technical"))
    if not biz and not tech:
        legacy = _normalize_verdict(meta.get("decision"))
        if legacy:
            biz = legacy
            tech = legacy
    if not biz and not tech:
        return ""
    return f"biz={biz or '?'} tech={tech or '?'}"


class StreamSink:
    """A minimal TextIO-like sink for run_cmd(stream=True, stream_to=...)."""

    def __init__(
        self,
        *,
        label: str,
        file: TextIO | None,
        tail: TailBuffer,
        also_to: TextIO | None = None,
        on_activity: Callable[[], None] | None = None,
    ) -> None:
        self._label = label
        self._file = file
        self._tail = tail
        self._also_to = also_to
        self._on_activity = on_activity
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not s:
            return 0
        with self._lock:
            if self._file is not None:
                self._file.write(s)
                self._file.flush()
            self._tail.append_text(s)
            if self._also_to is not None:
                self._also_to.write(s)
                self._also_to.flush()
        if self._on_activity:
            try:
                self._on_activity()
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.flush()
            if self._also_to is not None:
                self._also_to.flush()


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _fmt_age_seconds(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "?"
    s = max(0.0, float(age_seconds))
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s/60:.0f}m"
    return f"{s/3600:.1f}h"


def _parse_iso8601_seconds(text: str | None) -> float | None:
    if not text:
        return None
    # Minimal parser: accept "YYYY-MM-DDTHH:MM:SS+00:00" and "Z".
    try:
        # Avoid datetime import overhead here; this is best-effort.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # Python's fromisoformat is fine but requires datetime; keep simple.
        from datetime import datetime

        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _multipass_line(meta: dict) -> str | None:
    mp = meta.get("multipass")
    if not isinstance(mp, dict):
        return None
    if mp.get("enabled") is not True:
        return None
    current = mp.get("current")
    current = current if isinstance(current, dict) else {}
    stage = str(current.get("stage") or "").strip() or "?"
    step_index = current.get("step_index")
    step_count = current.get("step_count")
    title = str(current.get("step_title") or "").strip()
    if isinstance(step_index, int) and isinstance(step_count, int) and step_count > 0:
        base = f"Multipass: stage={stage} step {step_index}/{step_count}"
    else:
        base = f"Multipass: stage={stage}"
    if title:
        return f"{base} — {_truncate(title, 80)}"
    return base


KNOWN_PHASE_PREFIX = (
    "resolve_pr_meta",
    "ensure_base_cache",
    "seed_sanity",
    "clone_seed",
    "rsync_mtimes",
    "checkout_pr",
    "prepare_base_ref",
    "detect_pr_size",
    "select_prompt_profile",
    "index_topup",
    "codex_plan",
    "codex_review",
    "codex_synth",
)


def _ordered_phases(meta: dict) -> tuple[str, dict, list[str]]:
    phase = str(meta.get("phase") or "").strip() or "?"
    phases = meta.get("phases")
    phases = phases if isinstance(phases, dict) else {}

    # Prefer a stable ordering for known phases; then include codex_step_XX and any extras.
    ordered: list[str] = []
    for p in KNOWN_PHASE_PREFIX:
        if p in phases or p == phase:
            ordered.append(p)

    step_keys = [k for k in phases.keys() if isinstance(k, str) and k.startswith("codex_step_")]
    step_keys.sort()
    for k in step_keys:
        if k not in ordered:
            ordered.append(k)

    for k in phases.keys():
        if isinstance(k, str) and k not in ordered:
            ordered.append(k)

    if phase and phase not in ordered:
        ordered.append(phase)

    return (phase, phases, ordered)


def _spinner_char(ts: float) -> str:
    # Avoid braille/emoji spinners: many terminals/font stacks render them poorly or
    # with ambiguous cell widths, which can cause wraps/misalignment.
    frames = "|/-\\"
    idx = int(max(0.0, float(ts)) * 10) % len(frames)
    return frames[idx]


def _format_phase_lines(
    *, meta: dict, max_lines: int, width: int, now_ts: float | None, active: bool
) -> list[str]:
    max_lines = max(0, int(max_lines))
    width = max(1, int(width))
    if max_lines == 0:
        return []

    phase, phases, ordered = _ordered_phases(meta)

    entries: list[tuple[str, str, str | None]] = []
    done = 0
    errs = 0
    for p in ordered:
        entry = phases.get(p)
        entry = entry if isinstance(entry, dict) else {}
        status = str(entry.get("status") or "").strip()
        dur = entry.get("duration_seconds")
        dur_txt = None
        if isinstance(dur, (int, float)):
            dur_txt = f"{float(dur):.1f}s"
        if p == phase:
            if active and now_ts is not None:
                mark = f"▶{_spinner_char(now_ts)}"
            else:
                mark = "▶"
        elif status == "done":
            mark = "✔"
            done += 1
        elif status == "error":
            mark = "✖"
            errs += 1
        else:
            mark = "•"
        entries.append((mark, p, dur_txt))

    # Summary line improves scanability; only include if we have room.
    lines: list[str] = []
    if max_lines >= 3 and ordered:
        total = len(ordered)
        summary = f"Phases: {done}/{total} done"
        if errs:
            summary += f" • {errs} err"
        lines.append(_truncate(summary, width))

    remaining = max_lines - len(lines)
    if remaining <= 0:
        return lines[:max_lines]

    # Format phase entries with duration right-aligned.
    formatted: list[str] = []
    for mark, name, dur_txt in entries:
        base = f"{mark} {name}"
        if dur_txt:
            # Leave at least 1 space between base and dur when possible.
            avail = width - len(dur_txt) - 1
            if avail >= 3:
                left = _truncate(base, avail)
                pad = max(1, width - len(left) - len(dur_txt))
                formatted.append(left + (" " * pad) + dur_txt)
            else:
                formatted.append(_truncate(base, width))
        else:
            formatted.append(_truncate(base, width))

    # If extremely tight, always show the current phase line (preferable to summary).
    if max_lines == 1:
        current = next((l for l in formatted if l.lstrip().startswith("▶")), None)
        return [_truncate(current or (formatted[-1] if formatted else ""), width)]

    if len(formatted) > remaining:
        if remaining == 1:
            return lines + ["…"]
        tail_n = remaining - 1
        return lines + ["…"] + formatted[-tail_n:]
    return lines + formatted


def _pack_lr(*, left: str, right: str, width: int) -> str:
    width = max(1, int(width))
    left = str(left or "")
    right = str(right or "")
    if len(right) >= width:
        return _truncate(right, width).ljust(width)
    left_w = max(0, width - len(right) - 1)
    return _truncate(left, left_w).ljust(left_w) + " " + right


def _divider_segment(*, label: str, width: int) -> str:
    width = max(1, int(width))
    label = str(label or "").strip()
    if not label:
        return "─" * width
    # "─ {label} " then fill with dashes.
    prefix = f"─ {label} "
    if len(prefix) >= width:
        return _truncate(prefix, width)
    return prefix + ("─" * (width - len(prefix)))


def _divider_two_col(
    *, left_label: str, right_label: str, left_w: int, right_w: int, sep: str
) -> str:
    left = _divider_segment(label=left_label, width=left_w)
    right = _divider_segment(label=right_label, width=right_w)
    sep = str(sep or "")
    return left + sep + right


def _footer_bar(*, text: str, width: int) -> str:
    width = max(1, int(width))
    label = _truncate(str(text or "").strip(), max(0, width - 4))
    if not label:
        return "┄" * width
    prefix = f"┄ {label} "
    if len(prefix) >= width:
        return _truncate(prefix, width)
    return prefix + ("┄" * (width - len(prefix)))


def build_dashboard_lines(
    *,
    meta: dict,
    snapshot: UiSnapshot,
    chunkhound_tail: list[str],
    codex_tail: list[str],
    no_stream: bool,
    width: int,
    height: int,
    color: bool = False,
) -> list[str]:
    width = max(40, int(width))
    height = max(10, int(height))

    host = str(meta.get("host") or "").strip()
    owner = str(meta.get("owner") or "").strip()
    repo = str(meta.get("repo") or "").strip()
    number = meta.get("number")
    pr = f"{owner}/{repo}#{number}" if owner and repo and number else "?"
    title = str(meta.get("title") or "").strip()
    session_id = str(meta.get("session_id") or "").strip()
    paths = meta.get("paths")
    paths = paths if isinstance(paths, dict) else {}
    session_dir = str(paths.get("session_dir") or "").strip()
    review_md = str(paths.get("review_md") or "").strip()
    meta_path = str((Path(session_dir) / "meta.json")) if session_dir else ""

    created_at = str(meta.get("created_at") or "").strip()
    created_ts = _parse_iso8601_seconds(created_at)
    now_ts = time.time()
    elapsed = _fmt_age_seconds(now_ts - created_ts) if created_ts else "?"

    status = str(meta.get("status") or "running").strip()
    phase = str(meta.get("phase") or "").strip() or "?"

    completed_at = str(meta.get("completed_at") or "").strip()

    status_token = "RUN"
    if status.lower() in {"done", "completed", "success", "succeeded"}:
        status_token = "DONE"
    elif status.lower() in {"error", "failed", "failure"}:
        status_token = "ERR"
    elif completed_at:
        # Some older/partial meta writes may leave status="running" while still recording completed_at.
        status_token = "DONE"

    active = status_token == "RUN"
    status_display = f"RUN{_spinner_char(now_ts)}" if active else status_token

    verdicts = _format_verdicts(meta)
    right_bits: list[str] = [status_display]
    if status_token == "DONE" and verdicts:
        right_bits.append(verdicts)
    right_bits.extend([phase, elapsed, f"v:{snapshot.verbosity.value}"])
    if no_stream:
        right_bits.append("stream:off")
    right = " • ".join([b for b in right_bits if b])

    left = pr if pr != "?" else f"{host or '?'} ?"
    if host and host != "github.com":
        left = f"{left} ({host})"

    header_lines: list[str] = [_pack_lr(left=left, right=right, width=width)]
    if snapshot.verbosity in {Verbosity.normal, Verbosity.debug} and title:
        header_lines.append(f"title: {_truncate(title, max(0, width - 7))}")
    if snapshot.verbosity is Verbosity.debug:
        if session_id:
            header_lines.append(f"session: {session_id}")
        if session_dir:
            header_lines.append(f"dir: {_truncate(session_dir, width - 5)}")
        if review_md:
            header_lines.append(f"review: {_truncate(review_md, width - 7)}")

    mp_line = _multipass_line(meta)
    if mp_line and snapshot.verbosity is not Verbosity.quiet:
        header_lines.append(mp_line)

    # Body panes (progress + dials)
    wide = width >= 100
    col_sep = " │ "
    if wide:
        min_right = 30
        left_w = max(40, int(width * 0.58))
        left_w = min(left_w, max(40, width - len(col_sep) - min_right))
        right_w = max(1, width - left_w - len(col_sep))
    else:
        left_w = width
        right_w = width

    # Dials
    dials: list[tuple[str, str]] = []
    base_ref = str(meta.get("base_ref") or "").strip()
    head_sha = str(meta.get("head_sha") or "").strip()
    if base_ref:
        dials.append(("Base", base_ref))
    if head_sha:
        dials.append(("Head", _truncate(head_sha, 12)))

    pr_stats = meta.get("pr_stats")
    pr_stats = pr_stats if isinstance(pr_stats, dict) else {}
    cf = pr_stats.get("changed_files")
    add = pr_stats.get("additions")
    dele = pr_stats.get("deletions")
    cl = pr_stats.get("changed_lines")
    if isinstance(cf, int) or isinstance(cl, int):
        pr_bits = []
        if isinstance(cf, int):
            pr_bits.append(f"{cf} files")
        if isinstance(add, int) or isinstance(dele, int):
            pr_bits.append(f"+{add if isinstance(add, int) else '?'}")
            pr_bits.append(f"-{dele if isinstance(dele, int) else '?'}")
        if isinstance(cl, int):
            pr_bits.append(f"({cl})")
        dials.append(("PR", " ".join(pr_bits).strip()))

    prompt = meta.get("prompt")
    prompt = prompt if isinstance(prompt, dict) else {}
    pr_req = str(prompt.get("profile_requested") or "").strip()
    pr_res = str(prompt.get("profile_resolved") or "").strip()
    reason = str(prompt.get("reason") or "").strip()
    if pr_req or pr_res:
        r = _truncate(reason, 60)
        bits = f"{pr_req or '?'}→{pr_res or '?'}"
        if r:
            bits += f" {r}"
        dials.append(("Prompt", bits))

    base_cache = meta.get("base_cache")
    base_cache = base_cache if isinstance(base_cache, dict) else {}
    indexed_at = str(base_cache.get("indexed_at") or "").strip()
    idx_ts = _parse_iso8601_seconds(indexed_at)
    age = _fmt_age_seconds(now_ts - idx_ts) if idx_ts else "?"
    db_size = base_cache.get("db_size_bytes")
    if isinstance(db_size, int):
        db_size_mb = db_size / (1024 * 1024)
        dials.append(("Cache", f"{age} {db_size_mb:.0f}MB"))
    elif base_cache:
        dials.append(("Cache", f"{age}"))

    llm = meta.get("llm")
    llm = llm if isinstance(llm, dict) else {}
    if llm:
        preset = str(llm.get("preset") or "").strip()
        provider = str(llm.get("provider") or "").strip()
        model = str(llm.get("model") or "").strip()
        eff = str(llm.get("reasoning_effort") or "").strip()
        peff = str(llm.get("plan_reasoning_effort") or "").strip()
        bits = []
        if preset:
            bits.append(preset)
        if provider:
            bits.append(f"[{provider}]")
        if model:
            bits.append(model)
        if eff:
            bits.append(f"eff={eff}")
        if peff:
            bits.append(f"plan={peff}")
        if bits:
            dials.append(("LLM", " ".join(bits)))
    else:
        codex = meta.get("codex")
        codex = codex if isinstance(codex, dict) else {}
        cfg = codex.get("config")
        cfg = cfg if isinstance(cfg, dict) else {}
        resolved = cfg.get("resolved")
        resolved = resolved if isinstance(resolved, dict) else {}
        model = str(resolved.get("model") or "").strip()
        eff = str(resolved.get("model_reasoning_effort") or "").strip()
        peff = str(resolved.get("plan_mode_reasoning_effort") or "").strip()
        if model or eff or peff:
            bits = []
            if model:
                bits.append(model)
            if eff:
                bits.append(f"eff={eff}")
            if peff:
                bits.append(f"plan={peff}")
            dials.append(("Codex", " ".join(bits)))

    kind = str(meta.get("kind") or "").strip()
    zip_meta = meta.get("zip")
    zip_meta = zip_meta if isinstance(zip_meta, dict) else {}
    zip_display_inputs: list[str] = []
    raw_zip_display = zip_meta.get("display_inputs")
    if isinstance(raw_zip_display, list):
        zip_display_inputs = [str(item) for item in raw_zip_display if isinstance(item, str) and str(item).strip()]
    if not zip_display_inputs:
        raw_inputs = zip_meta.get("inputs")
        raw_inputs = raw_inputs if isinstance(raw_inputs, list) else []
        for item in raw_inputs:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id") or "?").strip() or "?"
            item_kind = str(item.get("kind") or "?").strip() or "?"
            item_verdicts = _format_verdicts(item)
            completed = str(item.get("completed_at") or "?").strip() or "?"
            target = str(item.get("target_head_sha") or "").strip()
            target = target[:12] if target else "?"
            path = str(item.get("path") or "?").strip() or "?"
            zip_display_inputs.append(
                f"- {session_id} [{item_kind}] {item_verdicts or 'biz=? tech=?'} {completed} head {target} {path}"
            )
    if kind == "zip" and zip_display_inputs:
        dials.append(("Zip", f"{len(zip_display_inputs)} inputs"))

    if snapshot.verbosity is Verbosity.debug:
        last_cmd = meta.get("last_cmd")
        if isinstance(last_cmd, list) and last_cmd:
            cmd_txt = " ".join(str(x) for x in last_cmd)
            dials.append(("last_cmd", _truncate(cmd_txt, 160)))
        if meta_path:
            dials.append(("meta", meta_path))
        logs = meta.get("logs")
        logs = logs if isinstance(logs, dict) else {}
        if logs:
            dials.append(("logs", _truncate(str(logs.get("reviewflow") or ""), 200)))

    def _dial_lines_full(*, width: int) -> list[str]:
        width = max(1, int(width))
        if not dials:
            return []
        label_w = max(len(k) for k, _ in dials)
        label_w = min(label_w, 12)
        out: list[str] = []
        for k, v in dials:
            key = f"{k}:"
            key = _truncate(key, label_w + 1).ljust(label_w + 1)
            out.append(_truncate(f"{key} {_truncate(str(v), max(0, width - len(key) - 1))}", width))
        return out

    def format_context(*, max_lines: int, width: int) -> list[str]:
        max_lines = max(0, int(max_lines))
        width = max(1, int(width))
        if max_lines == 0:
            return []
        out: list[str] = _dial_lines_full(width=width)
        if kind == "zip" and snapshot.verbosity is not Verbosity.quiet and zip_display_inputs:
            if out:
                out.append("")
            out.append("Inputs:")
            out.extend(_truncate(line, width) for line in zip_display_inputs)
        if len(out) > max_lines:
            if max_lines == 1:
                return ["…"]
            return out[: max_lines - 1] + ["…"]
        return out

    # Footer/help
    if snapshot.show_help:
        footer_lines: list[str] = [
            _footer_bar(text="Keys", width=width),
            "Keys:",
            "  v        cycle verbosity (quiet/normal/debug)",
            "  1/2/3    set verbosity",
            "  h or ?   toggle this help",
            "  Ctrl+L   redraw",
        ]
    else:
        footer_lines = [_footer_bar(text="v verbosity • h help • Ctrl+L redraw", width=width)]

    # Logs/tails (stacked)
    def _log_min_counts() -> tuple[int, int]:
        # Baseline defaults; the effective minimum is further capped by terminal height.
        if snapshot.verbosity is Verbosity.debug:
            return (18, 28)
        if snapshot.verbosity is Verbosity.normal:
            return (6, 10)
        return (0, 0)

    def _alloc_tails(*, budget: int, ch_avail: int, cx_avail: int) -> tuple[int, int]:
        budget = max(0, int(budget))
        ch_min, cx_min = _log_min_counts()
        ch = min(ch_min, ch_avail)
        cx = min(cx_min, cx_avail)
        if ch + cx > budget:
            # Shrink proportionally under extreme small terminals.
            if budget <= 0:
                return (0, 0)
            # Prefer keeping more Codex than ChunkHound.
            cx = min(cx, budget)
            ch = min(ch, max(0, budget - cx))
            return (ch, cx)

        extra = budget - (ch + cx)
        if extra <= 0:
            return (ch, cx)

        # Prefer Codex, but still give ChunkHound some share.
        cx_add = int(extra * 0.65)
        ch_add = extra - cx_add
        cx = min(cx_avail, cx + cx_add)
        ch = min(ch_avail, ch + ch_add)
        # If one side hit its cap, give remaining to the other.
        remaining = budget - (ch + cx)
        if remaining > 0:
            if cx < cx_avail:
                add = min(remaining, cx_avail - cx)
                cx += add
                remaining -= add
            if remaining > 0 and ch < ch_avail:
                ch += min(remaining, ch_avail - ch)
        return (ch, cx)

    def _alloc_tails_compact(*, budget: int, ch_avail: int, cx_avail: int) -> tuple[int, int]:
        """
        Like _alloc_tails, but ensures we show at least 1 line from each stream when:
        - budget allows (>=2), and
        - both streams have available lines.
        """
        budget = max(0, int(budget))
        ch, cx = _alloc_tails(budget=budget, ch_avail=ch_avail, cx_avail=cx_avail)
        if budget >= 2 and ch_avail > 0 and cx_avail > 0:
            if ch <= 0 and cx >= 2:
                ch = 1
                cx = max(1, cx - 1)
            if cx <= 0 and ch >= 2:
                cx = 1
                ch = max(1, ch - 1)
            if ch <= 0 and cx <= 0:
                ch, cx = (1, 1)
        return (ch, cx)

    def _render_logs_block(*, budget: int) -> list[str]:
        budget = max(0, int(budget))
        if snapshot.verbosity is Verbosity.quiet or budget <= 0:
            return []

        out: list[str] = []
        out.append(_divider_segment(label="Logs", width=width))
        if budget == 1:
            return out

        if no_stream:
            out.append("stream hidden (--no-stream); see session logs under <session>/work/logs/")
            return out[:budget]

        def _clean_tail(raw_lines: list[str]) -> list[str]:
            cleaned: list[str] = []
            last_blank = False
            for raw in raw_lines:
                s = str(raw).rstrip("\r\n")
                t = s.strip()
                # Drop the "####" delimiter artifact that sometimes appears at the end
                # of Codex markdown output.
                if t and len(t) >= 3 and set(t) == {"#"}:
                    continue
                if not t:
                    if last_blank:
                        continue
                    last_blank = True
                    cleaned.append("")
                    continue
                last_blank = False
                cleaned.append(s)
            return cleaned

        ch_tail = _clean_tail(chunkhound_tail)
        cx_tail = _clean_tail(codex_tail)

        # Prefer showing Codex when space is tight.
        show_chunkhound = budget >= 5 and bool(ch_tail)
        show_codex = budget >= 2

        overhead = 1 + (1 if show_chunkhound else 0) + (1 if show_codex else 0)
        tail_budget = max(0, budget - overhead)

        if show_chunkhound and show_codex:
            ch_show, cx_show = _alloc_tails_compact(
                budget=tail_budget, ch_avail=len(ch_tail), cx_avail=len(cx_tail)
            )
            ch_lines = ch_tail[-ch_show:] if ch_show > 0 else []
            cx_lines = cx_tail[-cx_show:] if cx_show > 0 else []
            out.append(f"ChunkHound (last {len(ch_lines)}):")
            out.extend(ch_lines)
            out.append(f"Codex (last {len(cx_lines)}):")
            out.extend(cx_lines)
        else:
            # Codex-only compact mode.
            cx_show = min(len(cx_tail), tail_budget)
            cx_lines = cx_tail[-cx_show:] if cx_show > 0 else []
            out.append(f"Codex (last {len(cx_lines)}):")
            out.extend(cx_lines)

        # If we had no actual output lines (empty logs), include a placeholder if we can.
        if len(out) <= 2 and budget >= 3:
            out.append("(no output yet)")
        return out[:budget]

    lines: list[str] = []
    lines.extend(header_lines)

    if wide:
        divider = _divider_two_col(
            left_label="Phases",
            right_label="Context",
            left_w=left_w,
            right_w=right_w,
            sep="─┬─",
        )
        lines.append(divider)

        # Compute an estimated full body height so we can cap compactly while still
        # guaranteeing logs get meaningful room on short terminals.
        _, _, ordered = _ordered_phases(meta)
        phase_full_rows = (1 + len(ordered)) if ordered else 0  # includes summary when present
        context_full_rows = len(format_context(max_lines=10_000, width=right_w))
        content_rows = max(phase_full_rows, context_full_rows)

        base_cap = (
            18
            if snapshot.verbosity is Verbosity.debug
            else (12 if snapshot.verbosity is Verbosity.normal else 8)
        )
        # Keep progress compact when height is tight; logs are the primary "live" signal.
        body_cap = min(base_cap, max(4, int(height * 0.30)))
        desired_rows = min(body_cap, content_rows) if content_rows else 0

        if snapshot.verbosity is Verbosity.quiet:
            min_logs_budget = 0
        elif no_stream:
            min_logs_budget = 2
        elif snapshot.verbosity is Verbosity.debug:
            min_logs_budget = max(8, min(18, int(height * 0.45)))
        else:
            min_logs_budget = max(6, min(14, int(height * 0.40)))

        fixed_no_body = len(lines) + len(footer_lines) + min_logs_budget
        body_max = max(0, height - fixed_no_body)
        body_rows = min(desired_rows, body_max) if desired_rows else 0

        phase_lines = _format_phase_lines(
            meta=meta, max_lines=body_rows, width=left_w, now_ts=now_ts, active=active
        )
        context_lines = format_context(max_lines=body_rows, width=right_w)
        body_rows_render = max(len(phase_lines), len(context_lines))
        for i in range(body_rows_render):
            ltxt = phase_lines[i] if i < len(phase_lines) else ""
            rtxt = context_lines[i] if i < len(context_lines) else ""
            lines.append(
                _truncate(ltxt, left_w).ljust(left_w)
                + col_sep
                + _truncate(rtxt, right_w).ljust(right_w)
            )
    else:
        context_lines_full = format_context(max_lines=10_000, width=width)

        base_cap = (
            16
            if snapshot.verbosity is Verbosity.debug
            else (10 if snapshot.verbosity is Verbosity.normal else 8)
        )
        body_cap = min(base_cap, max(4, int(height * 0.35)))

        if snapshot.verbosity is Verbosity.quiet:
            min_logs_budget = 0
        elif no_stream:
            min_logs_budget = 2
        elif snapshot.verbosity is Verbosity.debug:
            min_logs_budget = max(8, min(18, int(height * 0.45)))
        else:
            min_logs_budget = max(6, min(14, int(height * 0.40)))

        fixed_no_body = len(lines) + len(footer_lines) + min_logs_budget
        body_avail = max(0, height - fixed_no_body)

        if context_lines_full:
            body_content = max(0, body_avail - 2)  # phases divider + context divider
            # Phases list can be long; ensure current phase stays visible via _format_phase_lines.
            phase_desired = min(body_cap, max(4, int(body_content * 0.55)))
            context_desired = min(body_cap, len(context_lines_full), max(3, body_content - phase_desired))
            phase_h = min(phase_desired, body_content)
            context_h = min(context_desired, max(0, body_content - phase_h))
            lines.append(_divider_segment(label="Phases", width=width))
            lines.extend(
                _format_phase_lines(meta=meta, max_lines=phase_h, width=width, now_ts=now_ts, active=active)
            )
            lines.append(_divider_segment(label="Context", width=width))
            lines.extend(context_lines_full[:context_h])
        else:
            lines.append(_divider_segment(label="Phases", width=width))
            lines.extend(
                _format_phase_lines(
                    meta=meta,
                    max_lines=min(body_cap, body_avail),
                    width=width,
                    now_ts=now_ts,
                    active=active,
                )
            )

    # Allocate remaining height to logs (budgeted to avoid truncating away the actual tail lines).
    remaining_for_logs = max(0, height - (len(lines) + len(footer_lines)))
    logs_block = _render_logs_block(budget=remaining_for_logs)
    if logs_block:
        lines.extend(logs_block)
    lines.extend(footer_lines)

    # Ensure no line exceeds width and fit height.
    lines = [_truncate(l, width) for l in lines]
    out = lines[:height]
    if not color:
        return out

    ANSI_RESET = "\x1b[0m"
    ANSI_BOLD = "\x1b[1m"
    ANSI_REVERSE = "\x1b[7m"
    ANSI_DIM = "\x1b[2m"
    ANSI_CYAN = "\x1b[36m"
    ANSI_GREEN = "\x1b[32m"
    ANSI_RED = "\x1b[31m"

    def wrap(code: str, text: str) -> str:
        if not text:
            return text
        return f"{code}{text}{ANSI_RESET}"

    # Status bar: reverse + bold.
    if out:
        out[0] = wrap(ANSI_REVERSE + ANSI_BOLD, out[0])

    # Divider lines + tail headings: bold.
    for i, line in enumerate(out):
        if line.startswith("─"):
            out[i] = wrap(ANSI_BOLD, line)
        if line.startswith("ChunkHound") or line.startswith("Codex"):
            out[i] = wrap(ANSI_BOLD, line)

    # Footer/help: dim so it doesn't fight the logs.
    footer_set = set(footer_lines)
    for i, line in enumerate(out):
        if line in footer_set or line.startswith("Keys:") or line.startswith("  "):
            out[i] = wrap(ANSI_DIM, line)

    # Phase markers: colorize phases (left column in wide, full line in narrow).
    if wide:
        # body rows start after header + divider.
        body_start = len(header_lines) + 1
        # body_height rows were appended after divider.
        body_end = body_start
        for idx in range(body_start, len(out)):
            line = out[idx]
            if col_sep not in line:
                continue
            prefix, suffix = line.split(col_sep, 1)
            stripped = prefix.lstrip()
            if not stripped:
                continue
            mark = stripped[0]
            if mark == "▶":
                out[idx] = wrap(ANSI_CYAN, prefix) + col_sep + suffix
            elif mark == "✔":
                out[idx] = wrap(ANSI_GREEN, prefix) + col_sep + suffix
            elif mark == "✖":
                out[idx] = wrap(ANSI_RED, prefix) + col_sep + suffix
    else:
        for idx, line in enumerate(out):
            stripped = line.lstrip()
            if not stripped:
                continue
            mark = stripped[0]
            if mark == "▶":
                out[idx] = wrap(ANSI_CYAN, line)
            elif mark == "✔":
                out[idx] = wrap(ANSI_GREEN, line)
            elif mark == "✖":
                out[idx] = wrap(ANSI_RED, line)

    return out


def _auto_color_enabled(stream: TextIO) -> bool:
    try:
        if not stream.isatty():
            return False
    except Exception:
        return False
    term = str(os.environ.get("TERM") or "")
    if term in {"", "dumb"}:
        return False
    if "NO_COLOR" in os.environ:
        return False
    return True


class Dashboard:
    def __init__(
        self,
        *,
        meta_path: Path,
        state: UiState,
        tails: dict[str, TailBuffer],
        stderr: TextIO,
        no_stream: bool,
        refresh_hz: float = 5.0,
    ) -> None:
        self._meta_path = meta_path
        self._state = state
        self._tails = tails
        self._stderr = stderr
        self._no_stream = bool(no_stream)
        self._refresh_interval = 1.0 / max(1.0, float(refresh_hz))

        self._thread: threading.Thread | None = None
        self._tty_fd: int | None = None
        self._tty_old: list[int] | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="reviewflow-dashboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._state.request_stop()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._restore_tty()
        # Restore cursor.
        try:
            self._stderr.write("\x1b[?25h")
            self._stderr.flush()
        except Exception:
            pass

    def _setup_tty(self) -> None:
        try:
            fd = os.open("/dev/tty", os.O_RDONLY)
        except Exception:
            return
        try:
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            # Disable echo so keystrokes don't corrupt the dashboard.
            new = termios.tcgetattr(fd)
            new[3] = new[3] & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, new)
            self._tty_fd = fd
            self._tty_old = old
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass

    def _restore_tty(self) -> None:
        fd = self._tty_fd
        old = self._tty_old
        self._tty_fd = None
        self._tty_old = None
        if fd is None:
            return
        try:
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        try:
            os.close(fd)
        except Exception:
            pass

    def _poll_keys(self) -> None:
        fd = self._tty_fd
        if fd is None:
            return
        try:
            r, _, _ = select.select([fd], [], [], 0)
        except Exception:
            return
        if not r:
            return
        try:
            # Drain a few bytes to handle fast key repeats and avoid backlog.
            b = os.read(fd, 32)
        except Exception:
            return
        if not b:
            return
        text = b.decode("utf-8", errors="ignore")
        if not text:
            return
        for ch in text:
            if ch == "v":
                self._state.cycle_verbosity()
            elif ch == "1":
                self._state.set_verbosity(Verbosity.quiet)
            elif ch == "2":
                self._state.set_verbosity(Verbosity.normal)
            elif ch == "3":
                self._state.set_verbosity(Verbosity.debug)
            elif ch in {"h", "?"}:
                self._state.toggle_help()
            elif ch == "\x0c":  # Ctrl+L
                self._state.request_redraw()

    def _read_meta(self) -> dict:
        try:
            raw = self._meta_path.read_text(encoding="utf-8")
        except Exception:
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _render(self, meta: dict) -> None:
        snap = self._state.snapshot()
        term = get_terminal_size(fallback=(120, 40))
        width, height = int(term.columns), int(term.lines)

        # Provide generous tails; the renderer will decide how much to display based on height.
        if snap.verbosity is Verbosity.quiet:
            ch_tail: list[str] = []
            cx_tail: list[str] = []
        else:
            ch_tail = self._tails.get("chunkhound", TailBuffer()).tail(200)
            cx_tail = self._tails.get("codex", TailBuffer()).tail(400)

        lines = build_dashboard_lines(
            meta=meta,
            snapshot=snap,
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=self._no_stream,
            width=width,
            height=height,
            color=_auto_color_enabled(self._stderr),
        )

        # Hide cursor, clear screen, repaint.
        self._stderr.write("\x1b[?25l")
        # Always clear to avoid leftover content and reduce "merry" artifacts.
        _ = self._state.consume_force_redraw()
        self._stderr.write("\x1b[2J\x1b[H")
        # Avoid trailing newline to prevent scroll when height==terminal lines.
        self._stderr.write("\n".join(lines))
        self._stderr.flush()

    def _run(self) -> None:
        self._setup_tty()
        last_render = 0.0
        while not self._state.stop_requested():
            self._poll_keys()
            now = time.time()
            if now - last_render >= self._refresh_interval:
                meta = self._read_meta()
                self._render(meta)
                last_render = now
            self._state.wait_activity(timeout=self._refresh_interval)
