from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from meta import json_fingerprint, write_json
from paths import (
    DEFAULT_PATHS,
    ReviewflowPaths,
    base_dir,
    repo_id_for_gh,
    safe_ref_slug,
    seed_dir,
)
from run import ReviewflowSubprocessError, merged_env, run_cmd

from ui import Dashboard, TailBuffer, UiSnapshot, UiState, Verbosity, StreamSink, build_dashboard_lines


class ReviewflowError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _eprint(*args: object) -> None:
    text = " ".join(str(a) for a in args)
    out = _ACTIVE_OUTPUT
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


def normalize_markdown_artifact(*, markdown_path: Path, session_dir: Path) -> None:
    if not markdown_path.is_file():
        return
    original = markdown_path.read_text(encoding="utf-8")
    normalized = _strip_whole_document_markdown_fence(original)
    normalized = normalize_markdown_local_refs(normalized, session_dir=session_dir)
    if normalized != original:
        markdown_path.write_text(normalized, encoding="utf-8")


def _now_hms_utc() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def log(msg: str, *, quiet: bool) -> None:
    if quiet:
        return
    line = f"{_now_hms_utc()} | {msg}"
    out = _ACTIVE_OUTPUT
    if out is not None:
        out.log(line)
        return
    _eprint(line)


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

        self.reviewflow_log = (self.logs_dir / "reviewflow.log").open(
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

        # Stream sinks (run_cmd(stream=True) writes here).
        # - In UI mode: do not write to terminal (avoid corrupting dashboard).
        # - In non-UI mode: tee to stderr to preserve existing behavior.
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
        # In UI mode, avoid printing raw lines that would corrupt the screen; rely on logs + final error.
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
        # In UI mode, keep tails/logs clean (no prefix spam); in non-UI, preserve existing prefixes.
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
        # In UI mode, always stream so logs are written incrementally and tails update.
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


def load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def toml_string(value: str) -> str:
    # JSON string literals are also valid TOML basic strings.
    return json.dumps(value)


def codex_flags_from_base_config(*, base_config_path: Path) -> tuple[list[str], dict[str, Any]]:
    cfg = load_toml(base_config_path)
    meta: dict[str, Any] = {"base_config_path": str(base_config_path), "loaded": bool(cfg)}
    flags: list[str] = []

    model = cfg.get("model")
    if isinstance(model, str) and model.strip():
        flags.extend(["-m", model.strip()])
        meta["model"] = model.strip()

    sandbox_mode = cfg.get("sandbox_mode")
    if (
        isinstance(sandbox_mode, str)
        and sandbox_mode in {"read-only", "workspace-write", "danger-full-access"}
    ):
        flags.extend(["--sandbox", sandbox_mode])
        meta["sandbox_mode"] = sandbox_mode

    web_search = cfg.get("web_search")
    if web_search == "live":
        flags.append("--search")
        meta["web_search"] = "live"

    model_reasoning_effort = cfg.get("model_reasoning_effort")
    if isinstance(model_reasoning_effort, str) and model_reasoning_effort.strip():
        flags.extend(
            ["-c", f"model_reasoning_effort={toml_string(model_reasoning_effort.strip())}"]
        )
        meta["model_reasoning_effort"] = model_reasoning_effort.strip()

    plan_mode_reasoning_effort = cfg.get("plan_mode_reasoning_effort")
    if isinstance(plan_mode_reasoning_effort, str) and plan_mode_reasoning_effort.strip():
        flags.extend(
            [
                "-c",
                f"plan_mode_reasoning_effort={toml_string(plan_mode_reasoning_effort.strip())}",
            ]
        )
        meta["plan_mode_reasoning_effort"] = plan_mode_reasoning_effort.strip()

    return flags, meta


DEFAULT_REVIEWFLOW_CONFIG_PATH = Path("/workspaces/.reviewflow.toml")
DEFAULT_CRAWL_ALLOW_HOSTS = ("github.com", "api.github.com")
DEFAULT_CRAWL_TIMEOUT_SECONDS = 20
DEFAULT_CRAWL_MAX_BYTES = 2_000_000
CODEX_REASONING_EFFORT_CHOICES = ("minimal", "low", "medium", "high", "xhigh")
DEFAULT_MULTIPASS_ENABLED = True
DEFAULT_MULTIPASS_MAX_STEPS = 20
MULTIPASS_MAX_STEPS_HARD_CAP = 20


def resolve_verbosity(args: argparse.Namespace) -> Verbosity:
    if bool(getattr(args, "quiet", False)):
        return Verbosity.quiet
    raw = getattr(args, "verbosity", None)
    if raw is None:
        return Verbosity.normal
    text = str(raw).strip().lower()
    if text == "quiet":
        return Verbosity.quiet
    if text == "debug":
        return Verbosity.debug
    return Verbosity.normal


def resolve_ui_enabled(args: argparse.Namespace, *, verbosity: Verbosity) -> bool:
    if bool(getattr(args, "quiet", False)):
        return False
    ui = str(getattr(args, "ui", "auto") or "auto").strip().lower()
    if ui == "off":
        return False
    if ui == "on":
        return bool(sys.stderr.isatty()) and (os.environ.get("TERM", "").strip().lower() not in {"", "dumb"})
    # auto
    return bool(sys.stderr.isatty()) and (os.environ.get("TERM", "").strip().lower() not in {"", "dumb"})


def load_reviewflow_multipass_defaults(
    *, config_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load reviewflow-level multipass defaults from `/workspaces/.reviewflow.toml`.

    Schema:
      [multipass]
      enabled = true
      max_steps = 20
    """

    path = config_path or DEFAULT_REVIEWFLOW_CONFIG_PATH
    raw = load_toml(path)
    mp = raw.get("multipass", {}) if isinstance(raw, dict) else {}
    mp = mp if isinstance(mp, dict) else {}

    enabled = mp.get("enabled")
    if not isinstance(enabled, bool):
        enabled = DEFAULT_MULTIPASS_ENABLED

    max_steps = mp.get("max_steps")
    if not isinstance(max_steps, int):
        max_steps = DEFAULT_MULTIPASS_MAX_STEPS

    if max_steps < 1:
        max_steps = 1
    if max_steps > MULTIPASS_MAX_STEPS_HARD_CAP:
        max_steps = MULTIPASS_MAX_STEPS_HARD_CAP

    cfg: dict[str, Any] = {"enabled": bool(enabled), "max_steps": int(max_steps)}
    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "multipass": dict(cfg),
    }
    return cfg, meta


def load_reviewflow_codex_defaults(
    *, config_path: Path | None = None
) -> tuple[dict[str, str], dict[str, Any]]:
    """Load reviewflow-level Codex defaults from `/workspaces/.reviewflow.toml`.

    Schema:
      [codex]
      model = "..."
      model_reasoning_effort = "..."
      plan_mode_reasoning_effort = "..."
    """

    path = config_path or DEFAULT_REVIEWFLOW_CONFIG_PATH
    raw = load_toml(path)
    codex = raw.get("codex", {}) if isinstance(raw, dict) else {}
    codex = codex if isinstance(codex, dict) else {}

    defaults: dict[str, str] = {}
    for key in ("model", "model_reasoning_effort", "plan_mode_reasoning_effort"):
        val = codex.get(key)
        if isinstance(val, str) and val.strip():
            defaults[key] = val.strip()

    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "codex": dict(defaults),
    }
    return defaults, meta


def resolve_codex_flags(
    *,
    base_config_path: Path,
    reviewflow_config_path: Path | None,
    cli_model: str | None,
    cli_effort: str | None,
    cli_plan_effort: str | None,
) -> tuple[list[str], dict[str, Any]]:
    """Resolve effective Codex flags for a reviewflow run.

    Precedence:
      1) CLI overrides
      2) reviewflow defaults (/workspaces/.reviewflow.toml [codex])
      3) base Codex config (/workspaces/academy+/.codex/config.toml)
    """

    base_cfg = load_toml(base_config_path)
    base_meta: dict[str, Any] = {"path": str(base_config_path), "loaded": bool(base_cfg)}

    base_model = base_cfg.get("model") if isinstance(base_cfg.get("model"), str) else None
    base_sandbox_mode = (
        base_cfg.get("sandbox_mode") if isinstance(base_cfg.get("sandbox_mode"), str) else None
    )
    base_web_search = (
        base_cfg.get("web_search") if isinstance(base_cfg.get("web_search"), str) else None
    )
    base_effort = (
        base_cfg.get("model_reasoning_effort")
        if isinstance(base_cfg.get("model_reasoning_effort"), str)
        else None
    )
    base_plan_effort = (
        base_cfg.get("plan_mode_reasoning_effort")
        if isinstance(base_cfg.get("plan_mode_reasoning_effort"), str)
        else None
    )

    rf_defaults, rf_meta = load_reviewflow_codex_defaults(config_path=reviewflow_config_path)

    def _pick(key: str, base: str | None, cli: str | None) -> tuple[str | None, str]:
        if cli and cli.strip():
            return cli.strip(), "cli"
        rf = rf_defaults.get(key)
        if rf:
            return rf, "reviewflow.toml"
        if base and str(base).strip():
            return str(base).strip(), "base_config"
        return None, "unset"

    model, model_src = _pick("model", base_model, cli_model)
    effort, effort_src = _pick("model_reasoning_effort", base_effort, cli_effort)
    plan_effort, plan_effort_src = _pick(
        "plan_mode_reasoning_effort", base_plan_effort, cli_plan_effort
    )

    for key, val in (
        ("model_reasoning_effort", effort),
        ("plan_mode_reasoning_effort", plan_effort),
    ):
        if val is None:
            continue
        if val not in CODEX_REASONING_EFFORT_CHOICES:
            raise ReviewflowError(
                f"Invalid {key}: {val!r}. Expected one of: {', '.join(CODEX_REASONING_EFFORT_CHOICES)}"
            )

    flags: list[str] = []
    if model:
        flags.extend(["-m", model])

    if (
        isinstance(base_sandbox_mode, str)
        and base_sandbox_mode in {"read-only", "workspace-write", "danger-full-access"}
    ):
        flags.extend(["--sandbox", base_sandbox_mode])

    if base_web_search == "live":
        flags.append("--search")

    if effort:
        flags.extend(["-c", f"model_reasoning_effort={toml_string(effort)}"])
    if plan_effort:
        flags.extend(["-c", f"plan_mode_reasoning_effort={toml_string(plan_effort)}"])

    meta: dict[str, Any] = {
        "base": base_meta,
        "reviewflow_defaults": rf_meta,
        "resolved": {
            "model": model,
            "model_source": model_src,
            "model_reasoning_effort": effort,
            "model_reasoning_effort_source": effort_src,
            "plan_mode_reasoning_effort": plan_effort,
            "plan_mode_reasoning_effort_source": plan_effort_src,
            "sandbox_mode": base_sandbox_mode,
            "web_search": base_web_search,
        },
        "flags": list(flags),
    }
    return flags, meta


@dataclass(frozen=True)
class CrawlConfig:
    allow_hosts: tuple[str, ...]
    timeout_seconds: int
    max_bytes: int


def load_crawl_config(*, config_path: Path | None = None) -> tuple[CrawlConfig, dict[str, Any]]:
    path = config_path or DEFAULT_REVIEWFLOW_CONFIG_PATH
    raw = load_toml(path)
    crawl = raw.get("crawl", {}) if isinstance(raw, dict) else {}
    crawl = crawl if isinstance(crawl, dict) else {}

    allow_hosts_raw = crawl.get("allow_hosts")
    allow_hosts: list[str] = []
    if isinstance(allow_hosts_raw, list):
        for item in allow_hosts_raw:
            if isinstance(item, str):
                host = item.strip().lower()
                if host:
                    allow_hosts.append(host)
    if not allow_hosts:
        allow_hosts = list(DEFAULT_CRAWL_ALLOW_HOSTS)

    timeout_seconds = crawl.get("timeout_seconds")
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0 or timeout_seconds > 300:
        timeout_seconds = DEFAULT_CRAWL_TIMEOUT_SECONDS

    max_bytes = crawl.get("max_bytes")
    if not isinstance(max_bytes, int) or max_bytes <= 0 or max_bytes > 50_000_000:
        max_bytes = DEFAULT_CRAWL_MAX_BYTES

    cfg = CrawlConfig(
        allow_hosts=tuple(allow_hosts),
        timeout_seconds=int(timeout_seconds),
        max_bytes=int(max_bytes),
    )
    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "crawl": {
            "allow_hosts": list(cfg.allow_hosts),
            "timeout_seconds": cfg.timeout_seconds,
            "max_bytes": cfg.max_bytes,
        },
    }
    return cfg, meta


def crawl_env(cfg: CrawlConfig) -> dict[str, str]:
    return {
        "REVIEWFLOW_CRAWL_ALLOW_HOSTS": ",".join(cfg.allow_hosts),
        "REVIEWFLOW_CRAWL_TIMEOUT_SECONDS": str(cfg.timeout_seconds),
        "REVIEWFLOW_CRAWL_MAX_BYTES": str(cfg.max_bytes),
    }


def write_rf_fetch_url(*, repo_dir: Path, cfg: CrawlConfig) -> Path:
    path = repo_dir / "rf-fetch-url"
    default_hosts_json = json.dumps(list(cfg.allow_hosts))
    script = """#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

_DEFAULT_ALLOW_HOSTS = __DEFAULT_ALLOW_HOSTS__
_DEFAULT_TIMEOUT_SECONDS = __DEFAULT_TIMEOUT_SECONDS__
_DEFAULT_MAX_BYTES = __DEFAULT_MAX_BYTES__


def _die(msg: str, code: int = 2) -> "NoReturn":
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return value if value > 0 else default


def _allow_hosts() -> set[str]:
    raw = os.environ.get("REVIEWFLOW_CRAWL_ALLOW_HOSTS", "").strip()
    if not raw:
        return set(h.lower() for h in _DEFAULT_ALLOW_HOSTS)
    return set(h.strip().lower() for h in raw.split(",") if h.strip())


def _require_allowed_url(url: str, allow_hosts: set[str]) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        _die("rf-fetch-url: disallowed scheme: %r" % (parsed.scheme,))
    if parsed.username or parsed.password:
        _die("rf-fetch-url: credentials in URL are not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        _die("rf-fetch-url: missing host")
    if host not in allow_hosts:
        _die("rf-fetch-url: host not allowlisted: %s" % host)
    return parsed


def _append_query(endpoint: str, parsed: urllib.parse.ParseResult) -> str:
    if parsed.query:
        return endpoint + "?" + parsed.query
    return endpoint


def _unsupported_github_url(parsed: urllib.parse.ParseResult) -> "NoReturn":
    _die("rf-fetch-url: unsupported GitHub URL shape: %s" % urllib.parse.urlunparse(parsed))


def _github_api_endpoint(parsed: urllib.parse.ParseResult) -> str:
    host = (parsed.hostname or "").lower()
    if host == "api.github.com":
        endpoint = parsed.path.lstrip("/")
        if not endpoint:
            _unsupported_github_url(parsed)
        return _append_query(endpoint, parsed)
    if host != "github.com":
        _die("rf-fetch-url: unsupported GitHub URL host: %s" % host)

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4:
        _unsupported_github_url(parsed)
    owner, repo, kind, number = parts[:4]
    fragment = (parsed.fragment or "").strip()

    if fragment:
        match = re.fullmatch(r"issuecomment-(\\d+)", fragment)
        if match:
            return _append_query(
                "repos/%s/%s/issues/comments/%s" % (owner, repo, match.group(1)),
                parsed,
            )
        match = re.fullmatch(r"discussion_r(\\d+)", fragment)
        if match:
            return _append_query(
                "repos/%s/%s/pulls/comments/%s" % (owner, repo, match.group(1)),
                parsed,
            )
        match = re.fullmatch(r"pullrequestreview-(\\d+)", fragment)
        if match:
            if kind != "pull" or not number.isdigit():
                _unsupported_github_url(parsed)
            return _append_query(
                "repos/%s/%s/pulls/%s/reviews/%s" % (owner, repo, number, match.group(1)),
                parsed,
            )

    if kind == "pull" and number.isdigit():
        tail = parts[4:]
        if not tail or tail == ["files"]:
            return _append_query("repos/%s/%s/pulls/%s" % (owner, repo, number), parsed)
        _unsupported_github_url(parsed)

    if kind == "issues" and number.isdigit() and len(parts) == 4:
        return _append_query("repos/%s/%s/issues/%s" % (owner, repo, number), parsed)

    _unsupported_github_url(parsed)


def _extract_http_status(stderr_text: str):
    for pattern in (
        r"\\bHTTP\\s+(\\d{3})\\b",
        r"\\((\\d{3})\\)",
        r"\\b(\\d{3})\\s+Not Found\\b",
        r"\\b(\\d{3})\\s+Forbidden\\b",
        r"\\b(\\d{3})\\s+Unauthorized\\b",
    ):
        match = re.search(pattern, stderr_text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _fetch_via_gh(parsed: urllib.parse.ParseResult, *, timeout: int, max_bytes: int) -> int:
    endpoint = _github_api_endpoint(parsed)
    cmd = ["gh", "api", "--hostname", "github.com", endpoint]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(os.environ),
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        _die("rf-fetch-url: `gh` not found on PATH")
    except subprocess.TimeoutExpired:
        _die("rf-fetch-url: network error: timed out")

    if proc.returncode != 0:
        err_text = (proc.stderr or b"").decode("utf-8", errors="replace")
        status = _extract_http_status(err_text)
        if status is not None:
            print("rf-fetch-url: HTTP %d" % status, file=sys.stderr)
        else:
            print("rf-fetch-url: gh api failed", file=sys.stderr)
        if proc.stderr:
            sys.stderr.buffer.write(b"\\n" + proc.stderr[:max_bytes])
        return 1

    data = proc.stdout or b""
    if len(data) > max_bytes:
        _die("rf-fetch-url: response exceeded max_bytes=%d" % max_bytes)
    sys.stdout.buffer.write(data)
    return 0


def _fetch_direct(url: str, *, allow_hosts: set[str], timeout: int, max_bytes: int) -> int:
    class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _require_allowed_url(newurl, allow_hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_AllowlistRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "reviewflow-rf-fetch-url/1.0"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                _die("rf-fetch-url: response exceeded max_bytes=%d" % max_bytes)
            sys.stdout.buffer.write(data)
        return 0
    except urllib.error.HTTPError as e:
        data = e.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
        print("rf-fetch-url: HTTP %d" % int(e.code), file=sys.stderr)
        if data:
            sys.stderr.buffer.write(b"\\n" + data)
        return 1
    except urllib.error.URLError as e:
        _die("rf-fetch-url: network error: %s" % e)


def main() -> int:
    if len(sys.argv) != 2:
        _die("Usage: ./rf-fetch-url <url>")
    url = sys.argv[1].strip()
    if not url:
        _die("rf-fetch-url: empty url")

    allow_hosts = _allow_hosts()
    parsed = _require_allowed_url(url, allow_hosts)

    timeout = _parse_int_env("REVIEWFLOW_CRAWL_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS)
    max_bytes = _parse_int_env("REVIEWFLOW_CRAWL_MAX_BYTES", _DEFAULT_MAX_BYTES)
    host = (parsed.hostname or "").lower()
    if host in {"github.com", "api.github.com"}:
        return _fetch_via_gh(parsed, timeout=timeout, max_bytes=max_bytes)
    return _fetch_direct(url, allow_hosts=allow_hosts, timeout=timeout, max_bytes=max_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script = script.replace("__DEFAULT_ALLOW_HOSTS__", default_hosts_json)
    script = script.replace("__DEFAULT_TIMEOUT_SECONDS__", str(cfg.timeout_seconds))
    script = script.replace("__DEFAULT_MAX_BYTES__", str(cfg.max_bytes))
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def build_codex_exec_cmd(
    *,
    repo_dir: Path,
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    review_md_path: Path,
    prompt: str,
    add_dirs: list[Path] | None = None,
    skip_git_repo_check: bool = False,
) -> list[str]:
    overrides = list(codex_config_overrides or [])
    cmd = [
        "codex",
        "-a",
        "never",
        "-C",
        str(repo_dir),
        "--add-dir",
        "/tmp",
        *codex_flags,
    ]
    for d in add_dirs or []:
        cmd.extend(["--add-dir", str(d)])
    for override in overrides:
        cmd.extend(["-c", override])
    cmd.extend(
        [
            "-c",
            "shell_environment_policy.inherit=all",
        ]
    )
    cmd.extend(
        [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        ]
    )
    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    cmd.extend(
        [
            "--output-last-message",
            str(review_md_path),
            "--",
            prompt,
        ]
    )
    return cmd


def run_codex_exec(
    *,
    repo_dir: Path,
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    stream: bool,
    progress: "SessionProgress",
    add_dirs: list[Path] | None = None,
    stream_label: str = "codex",
) -> CodexRunResult:
    started_at = datetime.now(timezone.utc)
    cmd = build_codex_exec_cmd(
        repo_dir=repo_dir,
        codex_flags=codex_flags,
        codex_config_overrides=codex_config_overrides,
        review_md_path=output_path,
        prompt=prompt,
        add_dirs=add_dirs,
        skip_git_repo_check=False,
    )
    progress.record_cmd(cmd)
    try:
        out = _ACTIVE_OUTPUT
        if out is not None:
            out.run_logged_cmd(
                cmd,
                kind="codex",
                cwd=repo_dir,
                env=env,
                check=True,
                stream_requested=stream,
            )
        else:
            run_cmd(
                cmd,
                cwd=repo_dir,
                env=env,
                check=True,
                stream=stream,
                stream_label=stream_label,
            )
        normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
        return CodexRunResult(
            resume=find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=started_at,
                env=env,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                add_dirs=add_dirs,
            )
        )
    except ReviewflowSubprocessError as e:
        msg = (e.stderr or "") + "\n" + (e.stdout or "")
        if "skip-git-repo-check" in msg or "trusted directory" in msg:
            fallback = build_codex_exec_cmd(
                repo_dir=repo_dir,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                review_md_path=output_path,
                prompt=prompt,
                add_dirs=add_dirs,
                skip_git_repo_check=True,
            )
            progress.record_cmd(fallback)
            out = _ACTIVE_OUTPUT
            if out is not None:
                out.run_logged_cmd(
                    fallback,
                    kind="codex",
                    cwd=repo_dir,
                    env=env,
                    check=True,
                    stream_requested=stream,
                )
            else:
                run_cmd(
                    fallback,
                    cwd=repo_dir,
                    env=env,
                    check=True,
                    stream=stream,
                    stream_label=stream_label,
                )
            normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
            return CodexRunResult(
                resume=find_codex_resume_info(
                    repo_dir=repo_dir,
                    started_at=started_at,
                    env=env,
                    codex_flags=codex_flags,
                    codex_config_overrides=codex_config_overrides,
                    add_dirs=add_dirs,
                )
            )
        raise


def codex_mcp_overrides_for_reviewflow(
    *,
    enable_sandbox_chunkhound: bool,
    sandbox_repo_dir: Path,
    chunkhound_db_path: Path | None = None,
    chunkhound_cwd: Path | None = None,
    chunkhound_config_path: Path | None = None,
    paths: ReviewflowPaths,
) -> list[str]:
    """Return Codex `-c` overrides to disable global MCP servers we don't want, and to optionally
    add a sandbox-scoped ChunkHound MCP server.

    Notes:
    - We intentionally disable the project-level `chunk-hound` server (indexes `/workspaces`) so
      review sessions are scoped to the sandbox repo only.
    - Codex validates MCP transports even if `enabled=false`, so we must supply `command` and `args`.
    - ChunkHound must run in daemon mode (default): do NOT pass `--no-daemon`.
    """

    overrides: list[str] = []

    # Disable the existing project-level MCP server (indexes `/workspaces`).
    overrides.append(f"mcp_servers.chunk-hound.command={toml_string('chunkhound')}")
    overrides.append(f"mcp_servers.chunk-hound.args={json.dumps(['mcp', '/workspaces'])}")
    overrides.append("mcp_servers.chunk-hound.enabled=false")
    overrides.append("mcp_servers.chunk-hound.tool_timeout_sec=12000")

    if not enable_sandbox_chunkhound:
        return overrides

    ch_db = chunkhound_db_path or (sandbox_repo_dir / ".chunkhound.db")
    ch_cwd = chunkhound_cwd or sandbox_repo_dir
    ch_cfg = chunkhound_config_path or paths.review_chunkhound_config
    ch_args = [
        "mcp",
        "--config",
        str(ch_cfg),
        str(sandbox_repo_dir),
    ]
    if chunkhound_config_path is None:
        # Backwards-compatible mode: pin DB/provider via CLI overrides.
        # When using a session-local config, prefer not to hot-patch config via CLI.
        ch_args[3:3] = ["--database-provider", "duckdb", "--db", str(ch_db)]
    overrides.append(f"mcp_servers.chunkhound.command={toml_string('chunkhound')}")
    overrides.append(f"mcp_servers.chunkhound.args={json.dumps(ch_args)}")
    overrides.append(f"mcp_servers.chunkhound.cwd={toml_string(str(ch_cwd))}")
    overrides.append(
        f"mcp_servers.chunkhound.env_vars={json.dumps(['CHUNKHOUND_EMBEDDING__API_KEY', 'VOYAGE_API_KEY', 'OPENAI_API_KEY'])}"
    )
    overrides.append("mcp_servers.chunkhound.startup_timeout_sec=20")
    overrides.append("mcp_servers.chunkhound.tool_timeout_sec=12000")
    return overrides


def real_user_home_dir() -> Path:
    # Avoid relying on $HOME which may be altered inside exec/sandbox environments.
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


class SessionProgress:
    def __init__(self, meta_path: Path, *, quiet: bool) -> None:
        self.meta_path = meta_path
        self.quiet = quiet
        self.meta: dict[str, Any] = {}

    def init(self, initial: dict[str, Any]) -> None:
        self.meta = dict(initial)
        self.meta.setdefault("status", "running")
        self.meta.setdefault("phase", "init")
        self.meta.setdefault("phases", {})
        self.flush()

    def flush(self) -> None:
        write_json(self.meta_path, self.meta)

    def set_phase(self, phase: str) -> None:
        self.meta["phase"] = phase
        self.flush()

    def record_cmd(self, cmd: list[str]) -> None:
        self.meta["last_cmd"] = safe_cmd_for_meta(cmd)
        self.flush()

    def phase_started(self, phase: str) -> None:
        phases = self.meta.setdefault("phases", {})
        entry = phases.get(phase) if isinstance(phases.get(phase), dict) else {}
        entry["started_at"] = _utc_now_iso()
        entry["status"] = "running"
        phases[phase] = entry
        self.meta["phase"] = phase
        self.flush()

    def phase_finished(self, phase: str, *, duration_seconds: float, ok: bool) -> None:
        phases = self.meta.setdefault("phases", {})
        entry = phases.get(phase) if isinstance(phases.get(phase), dict) else {}
        entry["finished_at"] = _utc_now_iso()
        entry["duration_seconds"] = float(duration_seconds)
        entry["status"] = "done" if ok else "error"
        phases[phase] = entry
        self.flush()

    def set_base_cache(self, base_cache_meta: dict[str, Any] | None) -> None:
        self.meta["base_cache"] = base_cache_meta
        self.flush()

    def done(self) -> None:
        self.meta["status"] = "done"
        self.meta["completed_at"] = _utc_now_iso()
        self.flush()

    def error(self, info: dict[str, Any]) -> None:
        self.meta["status"] = "error"
        self.meta["failed_at"] = _utc_now_iso()
        self.meta["error"] = info
        self.flush()


@contextlib.contextmanager
def phase(name: str, *, progress: SessionProgress | None, quiet: bool):
    started = time.perf_counter()
    if progress:
        progress.phase_started(name)
    log(f"START {name}", quiet=quiet)
    ok = False
    try:
        yield
        ok = True
    finally:
        duration = time.perf_counter() - started
        if progress:
            progress.phase_finished(name, duration_seconds=duration, ok=ok)
        if ok:
            log(f"DONE  {name} ({duration:.1f}s)", quiet=quiet)
        else:
            log(f"FAIL  {name} ({duration:.1f}s)", quiet=quiet)


@contextlib.contextmanager
def file_lock(lock_path: Path, *, quiet: bool) -> "contextlib.AbstractContextManager[None]":
    """Cross-process lock using `fcntl.flock` on a file path."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as fh:
        log(f"LOCK  {lock_path}", quiet=quiet)
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            log(f"UNLOCK {lock_path}", quiet=quiet)


@dataclass(frozen=True)
class PullRequestRef:
    host: str
    owner: str
    repo: str
    number: int

    @property
    def owner_repo(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def gh_repo(self) -> str:
        return repo_id_for_gh(self.host, self.owner, self.repo)


@dataclass(frozen=True)
class CodexResumeInfo:
    session_id: str
    cwd: Path
    command: str


@dataclass(frozen=True)
class CodexRunResult:
    resume: CodexResumeInfo | None = None


def _load_codex_session_meta(session_log_path: Path) -> dict[str, Any] | None:
    try:
        with session_log_path.open("r", encoding="utf-8") as fh:
            first_line = fh.readline().strip()
    except Exception:
        return None
    if not first_line:
        return None
    try:
        data = json.loads(first_line)
    except Exception:
        return None
    if data.get("type") != "session_meta":
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _iter_codex_session_logs(*, codex_root: Path, started_at: datetime) -> list[Path]:
    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return []
    dates = {
        started_at.astimezone(timezone.utc).date(),
        datetime.now(timezone.utc).date(),
    }
    logs: set[Path] = set()
    for day in dates:
        day_dir = sessions_root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if not day_dir.is_dir():
            continue
        logs.update(day_dir.glob("rollout-*.jsonl"))
    return sorted(logs, reverse=True)


def _iter_codex_session_logs_for_dates(*, codex_root: Path, dates: set[date]) -> list[Path]:
    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return []
    logs: set[Path] = set()
    for day in dates:
        day_dir = sessions_root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if not day_dir.is_dir():
            continue
        logs.update(day_dir.glob("rollout-*.jsonl"))
    return sorted(logs, reverse=True)


def _find_codex_session_log_by_id(
    *, codex_root: Path, session_id: str, created_at: str | None, completed_at: str | None
) -> Path | None:
    session_id = str(session_id or "").strip()
    if not session_id:
        return None

    candidate_dates: set[date] = {datetime.now(timezone.utc).date()}
    for raw in (completed_at, created_at):
        dt = _parse_iso_dt(str(raw or "").strip())
        if dt is None:
            continue
        dt = dt.astimezone(timezone.utc)
        candidate_dates.add((dt - timedelta(days=1)).date())
        candidate_dates.add(dt.date())
        candidate_dates.add((dt + timedelta(days=1)).date())

    searched: set[Path] = set()
    for session_log in _iter_codex_session_logs_for_dates(codex_root=codex_root, dates=candidate_dates):
        searched.add(session_log)
        payload = _load_codex_session_meta(session_log)
        if payload and str(payload.get("id") or "").strip() == session_id:
            return session_log

    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return None
    for session_log in sorted(sessions_root.rglob("rollout-*.jsonl"), reverse=True):
        if session_log in searched:
            continue
        payload = _load_codex_session_meta(session_log)
        if payload and str(payload.get("id") or "").strip() == session_id:
            return session_log
    return None


def _codex_session_contains_exact_user_message(*, session_log_path: Path, text: str) -> bool:
    needle = str(text or "").strip()
    if not needle or not session_log_path.is_file():
        return False
    try:
        with session_log_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except Exception:
                    continue
                if data.get("type") != "response_item":
                    continue
                payload = data.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                content = payload.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if str(part.get("type") or "").strip() != "input_text":
                        continue
                    if str(part.get("text") or "").strip() == needle:
                        return True
    except Exception:
        return False
    return False


def _codex_logs_contain_exact_user_message(
    *,
    codex_root: Path,
    text: str,
    created_at: str | None,
    completed_at: str | None,
) -> bool:
    needle = str(text or "").strip()
    if not needle:
        return False

    candidate_dates: set[date] = {datetime.now(timezone.utc).date()}
    for raw in (completed_at, created_at):
        dt = _parse_iso_dt(str(raw or "").strip())
        if dt is None:
            continue
        dt = dt.astimezone(timezone.utc)
        candidate_dates.add((dt - timedelta(days=1)).date())
        candidate_dates.add(dt.date())
        candidate_dates.add((dt + timedelta(days=1)).date())

    searched: set[Path] = set()
    for session_log in _iter_codex_session_logs_for_dates(codex_root=codex_root, dates=candidate_dates):
        searched.add(session_log)
        if _codex_session_contains_exact_user_message(session_log_path=session_log, text=needle):
            return True

    sessions_root = codex_root / "sessions"
    if not sessions_root.is_dir():
        return False
    for session_log in sorted(sessions_root.rglob("rollout-*.jsonl"), reverse=True):
        if session_log in searched:
            continue
        if _codex_session_contains_exact_user_message(session_log_path=session_log, text=needle):
            return True
    return False


def build_codex_resume_command(
    *,
    repo_dir: Path,
    session_id: str,
    env: dict[str, str],
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    add_dirs: list[Path] | None = None,
) -> str:
    assignments: list[str] = []
    for key in (
        "GH_CONFIG_DIR",
        "JIRA_CONFIG_FILE",
        "NETRC",
        "REVIEWFLOW_WORK_DIR",
        "REVIEWFLOW_CRAWL_ALLOW_HOSTS",
        "REVIEWFLOW_CRAWL_TIMEOUT_SECONDS",
        "REVIEWFLOW_CRAWL_MAX_BYTES",
    ):
        value = str(env.get(key) or "").strip()
        if value:
            assignments.append(f"{key}={shlex.quote(value)}")

    resume_cmd: list[str] = [
        "codex",
        "resume",
        "--dangerously-bypass-approvals-and-sandbox",
        "--add-dir",
        "/tmp",
    ]
    resume_cmd.extend(codex_flags)
    for override in codex_config_overrides or []:
        resume_cmd.extend(["-c", override])
    resume_cmd.extend(["-c", "shell_environment_policy.inherit=all", session_id])

    env_prefix = ""
    if assignments:
        env_prefix = "env " + " ".join(assignments) + " "
    return f"cd {shlex.quote(str(repo_dir))} && {env_prefix}{_shell_join(resume_cmd)}"


def find_codex_resume_info(
    *,
    repo_dir: Path,
    started_at: datetime,
    env: dict[str, str],
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    add_dirs: list[Path] | None = None,
    codex_root: Path | None = None,
) -> CodexResumeInfo | None:
    codex_home = codex_root or (real_user_home_dir() / ".codex")
    repo_root = repo_dir.resolve(strict=False)
    best: tuple[datetime, CodexResumeInfo] | None = None
    window_start = started_at - timedelta(minutes=5)

    for session_log in _iter_codex_session_logs(codex_root=codex_home, started_at=started_at):
        payload = _load_codex_session_meta(session_log)
        if not payload:
            continue
        originator = str(payload.get("originator") or "").strip()
        if originator not in {"codex_exec", "codex_cli_rs"}:
            continue

        raw_cwd = str(payload.get("cwd") or "").strip()
        if not raw_cwd:
            continue
        if Path(raw_cwd).resolve(strict=False) != repo_root:
            continue

        raw_session_id = str(payload.get("id") or "").strip()
        if not raw_session_id:
            continue

        raw_timestamp = str(payload.get("timestamp") or "").strip()
        timestamp = _parse_iso_dt(raw_timestamp)
        if timestamp is None or timestamp < window_start:
            continue

        info = CodexResumeInfo(
            session_id=raw_session_id,
            cwd=repo_root,
            command=build_codex_resume_command(
                repo_dir=repo_root,
                session_id=raw_session_id,
                env=env,
                codex_flags=codex_flags,
                codex_config_overrides=codex_config_overrides,
                add_dirs=add_dirs,
            ),
        )
        if best is None or timestamp > best[0]:
            best = (timestamp, info)

    return best[1] if best else None


def codex_resume_meta_dict(info: CodexResumeInfo | None) -> dict[str, str] | None:
    if info is None:
        return None
    return {
        "session_id": info.session_id,
        "cwd": str(info.cwd),
        "command": info.command,
    }


def record_codex_resume(container: dict[str, Any], info: CodexResumeInfo | None) -> str | None:
    payload = codex_resume_meta_dict(info)
    if payload is None:
        return None
    container["resume"] = payload
    return str(payload["command"])


def parse_pr_url(pr_url: str) -> PullRequestRef:
    # Accept:
    # - https://github.com/OWNER/REPO/pull/123
    # - https://github.com/OWNER/REPO/pull/123/files
    # - github.com/OWNER/REPO/pull/123
    text = pr_url.strip()
    if "://" not in text:
        text = "https://" + text

    parsed = urlparse(text)
    host = parsed.hostname or ""
    if not host:
        raise ReviewflowError(f"Invalid PR URL (missing host): {pr_url}")

    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 4 or parts[2] != "pull":
        raise ReviewflowError(
            f"Invalid PR URL (expected /OWNER/REPO/pull/NUMBER): {pr_url}"
        )

    owner, repo = parts[0], parts[1]
    try:
        number = int(parts[3])
    except ValueError as e:
        raise ReviewflowError(f"Invalid PR URL (bad PR number): {pr_url}") from e

    return PullRequestRef(host=host, owner=owner, repo=repo, number=number)


def resolve_resume_target(
    target: str, *, sandbox_root: Path, from_phase: str
) -> tuple[str, str]:
    """Resolve `reviewflow resume <target>` into (session_id, action).

    `target` may be either:
    - a session folder name (session_id), or
    - a GitHub PR URL (e.g. https://github.com/OWNER/REPO/pull/123)

    Action:
    - "resume": resume a multipass session (existing behavior)
    - "followup": run follow-up review for the latest completed session (PR URL mode only)
    """
    raw = str(target or "").strip()
    if not raw:
        raise ReviewflowError("resume requires a session_id.")

    pr: PullRequestRef | None = None
    try:
        pr = parse_pr_url(raw)
    except ReviewflowError:
        pr = None

    if pr is None:
        if Path(raw).is_absolute() or ("/" in raw) or ("\\" in raw):
            raise ReviewflowError(
                "resume expects a session id (folder name) or a PR URL. "
                f"Tip: run `python3 /workspaces/reviewflow/reviewflow.py list` to find a session id. Got: {raw!r}"
            )
        return (raw, "resume")

    root = sandbox_root
    if not root.is_dir():
        raise ReviewflowError(
            f"No review sandboxes found under {root} (needed to resolve PR {pr.owner}/{pr.repo}#{pr.number})."
        )

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    resumable: list[tuple[datetime, str]] = []
    completed: list[tuple[datetime, str]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta:
            continue
        if str(meta.get("host") or "") != pr.host:
            continue
        if str(meta.get("owner") or "") != pr.owner:
            continue
        if str(meta.get("repo") or "") != pr.repo:
            continue
        try:
            if int(meta.get("number") or 0) != int(pr.number):
                continue
        except Exception:
            continue

        status = str(meta.get("status") or "").strip()
        notes = meta.get("notes") if isinstance(meta.get("notes"), dict) else {}
        no_index = bool((notes or {}).get("no_index") or False)
        mp = meta.get("multipass") if isinstance(meta.get("multipass"), dict) else {}
        mp_enabled = bool((mp or {}).get("enabled") is True)

        if status in {"running", "error"} and mp_enabled and (not no_index):
            resumed_at = str(meta.get("resumed_at") or "").strip() or None
            failed_at = str(meta.get("failed_at") or "").strip() or None
            created_at = str(meta.get("created_at") or "").strip() or None
            dt = _parse_iso_dt(resumed_at) or _parse_iso_dt(failed_at) or _parse_iso_dt(created_at) or epoch
            resumable.append((dt, entry.name))
            continue

        completed_at = str(meta.get("completed_at") or "").strip() or None
        if status == "done" or completed_at:
            meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
            raw_review_md = str((meta_paths or {}).get("review_md") or (entry / "review.md")).strip()
            review_md_path = Path(raw_review_md) if raw_review_md else (entry / "review.md")
            if not review_md_path.is_absolute():
                review_md_path = (entry / review_md_path).resolve()
            else:
                review_md_path = review_md_path.resolve()
            if not review_md_path.is_file():
                continue
            created_at = str(meta.get("created_at") or "").strip() or None
            dt = _parse_iso_dt(completed_at) or _parse_iso_dt(created_at) or epoch
            completed.append((dt, entry.name))

    resumable.sort(key=lambda t: t[0], reverse=True)
    completed.sort(key=lambda t: t[0], reverse=True)

    if resumable:
        return (resumable[0][1], "resume")

    if str(from_phase or "auto").strip().lower() != "auto":
        raise ReviewflowError(
            f"No resumable multipass session found for PR {pr.owner}/{pr.repo}#{pr.number}. "
            "Tip: run `python3 /workspaces/reviewflow/reviewflow.py list` to find a session id."
        )

    if completed:
        return (completed[0][1], "followup")

    raise ReviewflowError(
        f"No sessions found for PR {pr.owner}/{pr.repo}#{pr.number} under {root}. "
        "Tip: run `python3 /workspaces/reviewflow/reviewflow.py list`."
    )


def resolve_resume_session_id(target: str, *, sandbox_root: Path, from_phase: str) -> str:
    session_id, _ = resolve_resume_target(target, sandbox_root=sandbox_root, from_phase=from_phase)
    return session_id


def parse_owner_repo(value: str) -> tuple[str, str, str]:
    """Parse OWNER/REPO or HOST/OWNER/REPO."""
    text = value.strip().strip("/")
    parts = text.split("/")
    if len(parts) == 2:
        return ("github.com", parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    raise ReviewflowError(f"Expected OWNER/REPO or HOST/OWNER/REPO, got: {value}")


def _tail_file_lines(path: Path, n: int, *, max_bytes: int = 256 * 1024) -> list[str]:
    n = max(0, int(n))
    if n == 0:
        return []
    try:
        if not path.is_file():
            return []
    except Exception:
        return []

    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            buf = b""
            block = 4096
            while pos > 0 and buf.count(b"\n") <= n:
                take = min(block, pos)
                pos -= take
                fh.seek(pos, os.SEEK_SET)
                buf = fh.read(take) + buf
                if len(buf) > max_bytes:
                    buf = buf[-max_bytes:]
                    break
        text = buf.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:] if len(lines) > n else lines
    except Exception:
        return []


def _resolve_log_path(*, session_dir: Path, raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        p = Path(str(raw)).expanduser()
        if not p.is_absolute():
            p = (session_dir / p).resolve()
        return p
    except Exception:
        return None


def ui_preview_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    session_id = str(getattr(args, "session_id", "") or "").strip()
    if not session_id:
        raise ReviewflowError("ui-preview: session_id is required")

    session_dir = paths.sandbox_root / session_id
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise ReviewflowError(f"ui-preview: missing meta.json at {meta_path}")

    verbosity_raw = str(getattr(args, "verbosity", "normal") or "normal").strip().lower()
    try:
        verbosity = Verbosity(verbosity_raw)
    except Exception:
        raise ReviewflowError("--verbosity must be one of: quiet, normal, debug")

    # Read generous tails; the renderer decides how much to display based on height.
    if verbosity is Verbosity.quiet:
        ch_n, cx_n = (0, 0)
    else:
        ch_n, cx_n = (200, 400)

    fallback_ch = session_dir / "work" / "logs" / "chunkhound.log"
    fallback_cx = session_dir / "work" / "logs" / "codex.log"

    snap = UiSnapshot(verbosity=verbosity, show_help=False)

    width_arg = getattr(args, "width", None)
    height_arg = getattr(args, "height", None)

    def _auto_color_enabled() -> bool:
        try:
            if not sys.stdout.isatty():
                return False
        except Exception:
            return False
        term = str(os.environ.get("TERM") or "")
        if term in {"", "dumb"}:
            return False
        if "NO_COLOR" in os.environ:
            return False
        return True

    color = _auto_color_enabled() and (not bool(getattr(args, "no_color", False)))

    def render_once(*, final_newline: bool) -> None:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ReviewflowError(f"ui-preview: failed to parse meta.json: {e}")
        if not isinstance(meta, dict):
            raise ReviewflowError("ui-preview: meta.json must contain a JSON object")

        logs = meta.get("logs")
        logs = logs if isinstance(logs, dict) else {}
        ch_log = _resolve_log_path(
            session_dir=session_dir, raw=str(logs.get("chunkhound") or "").strip()
        )
        cx_log = _resolve_log_path(
            session_dir=session_dir, raw=str(logs.get("codex") or "").strip()
        )

        if ch_log is None or (not ch_log.is_file()):
            ch_log = fallback_ch if fallback_ch.is_file() else None
        if cx_log is None or (not cx_log.is_file()):
            cx_log = fallback_cx if fallback_cx.is_file() else None

        chunkhound_tail = _tail_file_lines(ch_log, ch_n) if ch_log is not None else []
        codex_tail = _tail_file_lines(cx_log, cx_n) if cx_log is not None else []

        term = shutil.get_terminal_size(fallback=(120, 40))
        width = int(width_arg) if isinstance(width_arg, int) else int(term.columns)
        height = int(height_arg) if isinstance(height_arg, int) else int(term.lines)

        lines = build_dashboard_lines(
            meta=meta,
            snapshot=snap,
            chunkhound_tail=chunkhound_tail,
            codex_tail=codex_tail,
            no_stream=False,
            width=width,
            height=height,
            color=color,
        )
        sys.stdout.write("\n".join(lines))
        if final_newline:
            sys.stdout.write("\n")
        sys.stdout.flush()

    watch = bool(getattr(args, "watch", False))
    if not watch:
        # If the command line wrapped, some terminals start program output at a non-zero
        # column; add a leading newline in TTY mode to keep the dashboard aligned.
        try:
            if sys.stdout.isatty():
                sys.stdout.write("\n")
        except Exception:
            pass
        render_once(final_newline=True)
        return 0

    try:
        while True:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            render_once(final_newline=False)
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0


def compute_pr_stats(*, repo_dir: Path, base_ref: str, head_ref: str = "HEAD") -> dict[str, Any]:
    """Compute local diff stats using git (no GH API beyond checkout)."""
    name_only = run_cmd(
        ["git", "-C", str(repo_dir), "diff", "--name-only", f"{base_ref}...{head_ref}"]
    ).stdout
    changed_files = len([line for line in name_only.splitlines() if line.strip()])

    numstat = run_cmd(
        ["git", "-C", str(repo_dir), "diff", "--numstat", f"{base_ref}...{head_ref}"]
    ).stdout
    additions = 0
    deletions = 0
    binary_files = 0
    for raw in numstat.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add, delete = parts[0], parts[1]
        if add == "-" or delete == "-":
            binary_files += 1
            continue
        try:
            additions += int(add)
            deletions += int(delete)
        except ValueError:
            continue

    changed_lines = additions + deletions
    return {
        "detector": "git",
        "base_ref": base_ref,
        "head_ref": head_ref,
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
        "changed_lines": changed_lines,
        "binary_files": binary_files,
    }


def resolve_prompt_profile(
    *,
    requested: str,
    pr_stats: dict[str, Any] | None,
    big_if_files: int,
    big_if_lines: int,
) -> tuple[str, str]:
    """Return (resolved_profile, reason)."""
    if requested in {"normal", "big", "default"}:
        return (requested, f"requested:{requested}")

    if requested != "auto":
        return ("normal", f"unknown:{requested} -> normal")

    if not pr_stats:
        return ("big", "auto->big: stats unavailable")

    changed_files = int(pr_stats.get("changed_files") or 0)
    changed_lines = int(pr_stats.get("changed_lines") or 0)

    if changed_files >= big_if_files:
        return ("big", f"auto->big: changed_files={changed_files}>={big_if_files}")
    if changed_lines >= big_if_lines:
        return ("big", f"auto->big: changed_lines={changed_lines}>={big_if_lines}")

    return (
        "normal",
        f"auto->normal: changed_files={changed_files}<{big_if_files} and changed_lines={changed_lines}<{big_if_lines}",
    )


def prompt_template_path_for_profile(profile: str) -> Path:
    root = Path("/workspaces/reviewflow/prompts")
    if profile == "normal":
        return root / "mrereview_gh_local.md"
    if profile == "big":
        return root / "mrereview_gh_local_big.md"
    if profile == "default":
        return root / "default.md"
    raise ReviewflowError(f"Unknown prompt profile: {profile}")


def followup_prompt_template_path_for_profile(profile: str) -> Path:
    root = Path("/workspaces/reviewflow/prompts")
    if profile == "big":
        return root / "mrereview_gh_local_big_followup.md"
    return root / "mrereview_gh_local_followup.md"


def render_prompt(
    template_text: str,
    *,
    base_ref_for_review: str,
    pr_url: str,
    pr_number: int,
    gh_host: str,
    gh_owner: str,
    gh_repo_name: str,
    gh_repo: str,
    agent_desc: str,
    head_ref: str = "HEAD",
    extra_vars: dict[str, str] | None = None,
) -> str:
    # Back-compat: existing reviewflow placeholders.
    text = template_text.replace("<base>", base_ref_for_review)

    # Legacy-ish placeholders (mrereview_gh*).
    text = text.replace("$PR_URL", pr_url).replace("${PR_URL}", pr_url)
    text = text.replace("$PR_NUMBER", str(pr_number)).replace("${PR_NUMBER}", str(pr_number))
    text = text.replace("$GH_HOST", gh_host).replace("${GH_HOST}", gh_host)
    text = text.replace("$GH_OWNER", gh_owner).replace("${GH_OWNER}", gh_owner)
    text = text.replace("$GH_REPO_NAME", gh_repo_name).replace(
        "${GH_REPO_NAME}", gh_repo_name
    )
    text = text.replace("$GH_REPO", gh_repo).replace("${GH_REPO}", gh_repo)
    text = text.replace("$BASE_REF", base_ref_for_review).replace(
        "${BASE_REF}", base_ref_for_review
    )
    text = text.replace("$HEAD_REF", head_ref).replace("${HEAD_REF}", head_ref)
    if extra_vars:
        for k, v in extra_vars.items():
            key = str(k).strip()
            if not key:
                continue
            text = text.replace(f"${key}", str(v)).replace(f"${{{key}}}", str(v))
    # Replace AGENT_DESC last to avoid mutating its contents if it contains `$FOO`.
    text = text.replace("$AGENT_DESC", agent_desc).replace("${AGENT_DESC}", agent_desc)
    return text


_DECISION_LINE_RE = re.compile("(?im)^\\s*\\*\\*Decision\\*\\*:\\s*(.+?)\\s*$")


def extract_decision_from_markdown(text: str) -> str | None:
    matches = _DECISION_LINE_RE.findall(text or "")
    if not matches:
        return None
    for raw in reversed(matches):
        decision = str(raw).strip()
        if not decision:
            continue
        decision = decision.strip("[]").strip()
        decision = re.sub("^\\*+|\\*+$", "", decision).strip()
        if decision.startswith("`") and decision.endswith("`") and len(decision) >= 2:
            decision = decision[1:-1].strip()
        decision = re.sub(r"\\s+", " ", decision).strip()
        if not decision:
            continue
        upper = decision.upper()
        if upper in {"APPROVE", "REJECT"}:
            return upper
        if upper in {"REQUEST CHANGES", "REQUEST_CHANGES"}:
            return "REQUEST CHANGES"
        return decision
    return None


def multipass_prompt_template_paths() -> dict[str, Path]:
    root = Path("/workspaces/reviewflow/prompts")
    return {
        "plan": root / "mrereview_gh_local_big_plan.md",
        "step": root / "mrereview_gh_local_big_step.md",
        "synth": root / "mrereview_gh_local_big_synth.md",
    }


def _extract_first_fenced_block(text: str, *, lang: str) -> str | None:
    """Extract the first fenced code block for a given language (e.g. ```json ... ```)."""
    fence = f"```{lang}"
    start = text.find(fence)
    if start < 0:
        return None
    start = text.find("\n", start)
    if start < 0:
        return None
    start += 1
    end = text.find("```", start)
    if end < 0:
        return None
    return text[start:end].strip()


def parse_multipass_plan_json(text: str) -> dict[str, Any]:
    raw = _extract_first_fenced_block(text, lang="json")
    if not raw:
        raise ReviewflowError("Multipass plan JSON missing (expected a ```json fenced block).")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ReviewflowError(f"Multipass plan JSON invalid: {e}") from e
    if not isinstance(data, dict):
        raise ReviewflowError("Multipass plan JSON must be an object.")
    abort = data.get("abort")
    if not isinstance(abort, bool):
        raise ReviewflowError("Multipass plan JSON must include boolean field: abort")
    abort_reason = data.get("abort_reason")
    if abort_reason is not None and not isinstance(abort_reason, str):
        raise ReviewflowError("Multipass plan JSON abort_reason must be null or string.")
    steps = data.get("steps")
    if abort:
        if steps not in (None, [], ()):
            raise ReviewflowError("Multipass plan JSON must not include steps when abort=true.")
        return data
    if not isinstance(steps, list) or not steps:
        raise ReviewflowError("Multipass plan JSON must include a non-empty steps array.")
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ReviewflowError(f"Multipass plan step #{idx} must be an object.")
        if not isinstance(step.get("title"), str) or not str(step.get("title")).strip():
            raise ReviewflowError(f"Multipass plan step #{idx} missing title.")
        if not isinstance(step.get("focus"), str) or not str(step.get("focus")).strip():
            raise ReviewflowError(f"Multipass plan step #{idx} missing focus.")
    return data


def require_gh_auth(host: str) -> None:
    try:
        run_cmd(["gh", "auth", "status", "--hostname", host], check=True)
    except ReviewflowSubprocessError as e:
        msg = e.stderr.strip() or e.stdout.strip() or str(e)
        raise ReviewflowError(
            f"`gh` is not authenticated for {host}.\n"
            f"- Try: gh auth login -h {host}\n"
            f"- Details: {msg}"
        ) from e


def load_main_embedding_api_key(paths: ReviewflowPaths) -> str | None:
    try:
        raw = json.loads(paths.main_chunkhound_config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None

    embedding = raw.get("embedding")
    if not isinstance(embedding, dict):
        return None
    api_key = embedding.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    return None


def materialize_chunkhound_env_config(
    *,
    base_config_path: Path,
    output_config_path: Path,
    database_provider: str,
    database_path: Path,
) -> None:
    """Write a standalone ChunkHound config file for a reviewflow "environment".

    This improves reproducibility by pinning DB location/provider in a session-local config file
    rather than relying on CLI overrides (which can override/replace config lists like indexing.exclude).
    """
    raw = json.loads(base_config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ReviewflowError(f"ChunkHound config must be a JSON object: {base_config_path}")

    cfg = dict(raw)

    emb = cfg.get("embedding")
    if isinstance(emb, dict) and "api_key" in emb:
        # Avoid materializing secrets to disk, even if present in the source config.
        emb = dict(emb)
        emb.pop("api_key", None)
        cfg["embedding"] = emb

    db = cfg.get("database")
    if not isinstance(db, dict):
        db = {}
    db = dict(db)
    db["provider"] = str(database_provider)
    db["path"] = str(database_path)
    cfg["database"] = db

    write_json(output_config_path, cfg)


def chunkhound_env(paths: ReviewflowPaths) -> dict[str, str]:
    env: dict[str, str] = {}
    if os.environ.get("CHUNKHOUND_EMBEDDING__API_KEY"):
        return env

    # If the user has a provider-specific key in env, map it to what ChunkHound expects.
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if voyage_key:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = voyage_key
        return env

    inferred = load_main_embedding_api_key(paths)
    if inferred:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = inferred
    return env


def ensure_review_config(paths: ReviewflowPaths) -> None:
    if not paths.review_chunkhound_config.is_file():
        raise ReviewflowError(
            f"Missing review ChunkHound config: {paths.review_chunkhound_config}\n"
            "Create it first (see the epic Story 02)."
        )


def cache_prime(
    *,
    paths: ReviewflowPaths,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    require_gh_auth(host)
    ensure_review_config(paths)

    stream = (not quiet) and (not no_stream)

    base_root = base_dir(paths, host, owner, repo, base_ref)
    base_root.mkdir(parents=True, exist_ok=True)
    with file_lock(base_root / ".cache_prime.lock", quiet=quiet):
        seed = seed_dir(paths, host, owner, repo)
        seed.parent.mkdir(parents=True, exist_ok=True)
        with phase(f"cache_seed_sync {owner}/{repo}@{base_ref}", progress=None, quiet=quiet):
            if not seed.exists():
                run_cmd(["gh", "repo", "clone", repo_id_for_gh(host, owner, repo), str(seed)])
            else:
                # Validate it's a git repo before fetching.
                run_cmd(["git", "-C", str(seed), "rev-parse", "--is-inside-work-tree"])
                run_cmd(["git", "-C", str(seed), "fetch", "--prune", "origin"])

            # Reset seed to latest base ref.
            run_cmd(["git", "-C", str(seed), "fetch", "origin", base_ref])
            run_cmd(
                ["git", "-C", str(seed), "checkout", "-B", base_ref, f"origin/{base_ref}"]
            )
            base_sha = run_cmd(["git", "-C", str(seed), "rev-parse", "HEAD"]).stdout.strip()

        db_dir = base_root / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / ".chunkhound.db"
        ch_cfg_path = base_root / "chunkhound.json"
        materialize_chunkhound_env_config(
            base_config_path=paths.review_chunkhound_config,
            output_config_path=ch_cfg_path,
            database_provider="duckdb",
            database_path=db_path,
        )

        cfg_fp = json_fingerprint(paths.review_chunkhound_config)
        env_cfg_fp = json_fingerprint(ch_cfg_path)
        meta_path = base_root / "meta.json"

        need_reindex = force
        if not need_reindex and meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("config_fingerprint") != cfg_fp:
                    need_reindex = True
            except Exception:
                need_reindex = True

        env = merged_env(chunkhound_env(paths))
        index_cmd = [
            "chunkhound",
            "index",
            str(seed),
            "--config",
            str(ch_cfg_path),
        ]
        if need_reindex and db_path.exists():
            index_cmd.append("--force-reindex")

        with phase(
            f"cache_chunkhound_index {owner}/{repo}@{base_ref}", progress=None, quiet=quiet
        ):
            out = _ACTIVE_OUTPUT
            if out is not None:
                index_result = out.run_logged_cmd(
                    index_cmd,
                    kind="chunkhound",
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream_requested=stream,
                )
            else:
                index_result = run_cmd(
                    index_cmd,
                    cwd=base_root,
                    env=env,
                    check=True,
                    stream=stream,
                    stream_label="chunkhound",
                )
        db_size_bytes = path_size_bytes(db_path)

        meta = {
            "host": host,
            "owner": owner,
            "repo": repo,
            "base_ref": base_ref,
            "base_sha": base_sha,
            "indexed_at": _utc_now_iso(),
            "db_path": str(db_path),
            "db_size_bytes": db_size_bytes,
            "chunkhound_config_path": str(ch_cfg_path),
            "config_fingerprint": cfg_fp,
            "env_config_fingerprint": env_cfg_fp,
            "chunkhound_version": run_cmd(["chunkhound", "--version"]).stdout.strip(),
            "index_cmd": index_cmd,
            "index_duration_seconds": index_result.duration_seconds,
        }
        write_json(meta_path, meta)
        return meta


def cache_status(*, paths: ReviewflowPaths, host: str, owner: str, repo: str, base_ref: str) -> int:
    base_root = base_dir(paths, host, owner, repo, base_ref)
    meta_path = base_root / "meta.json"
    if not meta_path.is_file():
        _eprint(f"No cache meta found: {meta_path}")
        return 2

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0


def ttl_expired(indexed_at_iso: str, ttl_hours: int) -> bool:
    try:
        indexed_at = datetime.fromisoformat(indexed_at_iso)
    except Exception:
        return True
    age = datetime.now(timezone.utc) - indexed_at
    return age.total_seconds() > (ttl_hours * 3600)


def ensure_base_cache(
    *,
    paths: ReviewflowPaths,
    pr: PullRequestRef,
    base_ref: str,
    ttl_hours: int,
    refresh: bool,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    base_root = base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
    meta_path = base_root / "meta.json"
    if refresh or not meta_path.is_file():
        log(f"Base cache refresh: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return cache_prime(
            paths=paths,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            quiet=quiet,
            no_stream=no_stream,
        )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    try:
        cfg_fp = json_fingerprint(paths.review_chunkhound_config)
    except Exception as e:
        cfg_fp = None
        log(
            f"Base cache config fingerprint failed: {paths.review_chunkhound_config} ({e})",
            quiet=quiet,
        )

    if cfg_fp and meta.get("config_fingerprint") != cfg_fp:
        log(f"Base cache config changed: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return cache_prime(
            paths=paths,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            quiet=quiet,
            no_stream=no_stream,
        )

    if ttl_expired(str(meta.get("indexed_at") or ""), ttl_hours):
        log(f"Base cache expired: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return cache_prime(
            paths=paths,
            host=pr.host,
            owner=pr.owner,
            repo=pr.repo,
            base_ref=base_ref,
            force=False,
            quiet=quiet,
            no_stream=no_stream,
        )

    log(
        f"Base cache hit: {pr.owner}/{pr.repo}@{base_ref} (indexed_at={meta.get('indexed_at')})",
        quiet=quiet,
    )
    return meta


def path_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return 0


def same_device(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.stat().st_dev
    except Exception:
        return False


def copy_duckdb_files(src_db_path: Path, dst_db_path: Path) -> None:
    # ChunkHound's duckdb backend uses a "db path" that is a directory, e.g. `.chunkhound.db/`,
    # containing `chunks.db` (+ `.wal`) and potentially other files.
    if src_db_path.is_dir():
        if dst_db_path.exists():
            shutil.rmtree(dst_db_path)
        dst_db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_db_path, dst_db_path, copy_function=shutil.copy2)
        return

    src_wal = src_db_path.with_suffix(src_db_path.suffix + ".wal")
    dst_wal = dst_db_path.with_suffix(dst_db_path.suffix + ".wal")

    dst_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_db_path, dst_db_path)
    if src_wal.exists():
        shutil.copy2(src_wal, dst_wal)


def ensure_clean_git_worktree(*, repo_dir: Path) -> None:
    """Ensure the repo has no local changes that would block branch switches."""
    status = run_cmd(["git", "-C", str(repo_dir), "status", "--porcelain"]).stdout.strip()
    if not status:
        return
    # Only ever do this inside the sandbox/cache repos that reviewflow owns.
    run_cmd(["git", "-C", str(repo_dir), "reset", "--hard"])
    run_cmd(["git", "-C", str(repo_dir), "clean", "-fd"])


def prepare_gh_config_for_codex(*, dst_root: Path) -> Path | None:
    """Make `gh` auth available inside the Codex workspace root.

    Codex sandboxes commonly restrict filesystem access to the working root plus `--add-dir`s.
    Copy the user's GH config into the sandbox repo so `gh api` works without relying on $HOME.
    """
    src_env = os.environ.get("GH_CONFIG_DIR")
    src = Path(src_env).expanduser() if src_env else (Path.home() / ".config" / "gh")
    if not src.is_dir():
        return None

    dst = dst_root / "gh_config"
    if dst.exists():
        shutil.rmtree(dst)
    dst_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, copy_function=shutil.copy2)
    return dst


def prepare_jira_config_for_codex(*, dst_root: Path) -> Path | None:
    """Make `jira` auth available inside the Codex workspace root.

    Jira CLI reads auth from a config file. By default it uses:
    - `~/.config/.jira/.config.yml`
    or an explicit file path via `JIRA_CONFIG_FILE`.

    Codex sandboxes commonly restrict filesystem access to the working root plus `--add-dir`s,
    so copy the user's Jira config into the sandbox repo and set `JIRA_CONFIG_FILE`.
    """
    src_env = os.environ.get("JIRA_CONFIG_FILE")
    src = (
        Path(src_env).expanduser()
        if src_env
        else (Path.home() / ".config" / ".jira" / ".config.yml")
    )
    if not src.is_file():
        return None

    src_dir = src.parent
    dst_dir = dst_root / "jira_config"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_root.mkdir(parents=True, exist_ok=True)
    if src_dir.is_dir():
        shutil.copytree(src_dir, dst_dir, copy_function=shutil.copy2)
        dst = dst_dir / src.name
        return dst if dst.is_file() else None

    # Fallback (shouldn't happen): copy just the file.
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst if dst.is_file() else None


def write_rf_jira(*, repo_dir: Path) -> Path:
    path = repo_dir / "rf-jira"
    script = """#!/usr/bin/env python3
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path


def _die(msg: str, code: int = 2) -> "NoReturn":
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _real_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _debug(env: dict[str, str], *, cfg: Path) -> None:
    if env.get("RF_JIRA_DEBUG", "").strip() not in {"1", "true", "yes"}:
        return
    real_home = _real_home()
    netrc = real_home / ".netrc"
    print(
        "rf-jira: debug: uid=%s home=%s NETRC=%r netrc_exists=%s cfg=%s"
        % (os.getuid(), str(real_home), env.get("NETRC"), netrc.is_file(), str(cfg)),
        file=sys.stderr,
    )


def _run(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return int(p.returncode), p.stdout or "", p.stderr or ""


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    cfg_env = os.environ.get("JIRA_CONFIG_FILE", "").strip()
    if not cfg_env:
        _die("rf-jira: JIRA_CONFIG_FILE is required (sandbox-provided)")
    cfg = Path(cfg_env).expanduser().resolve()
    if not cfg.is_file():
        _die(f"rf-jira: missing jira config at {cfg}")

    env = dict(os.environ)

    # Ensure Jira CLI can locate credentials (this workspace commonly uses ~/.netrc).
    real_home = _real_home()
    env["HOME"] = str(real_home)
    netrc = real_home / ".netrc"
    if netrc.is_file():
        env["NETRC"] = str(netrc)

    cmd = ["jira", "--config", str(cfg), *sys.argv[1:]]
    _debug(env, cfg=cfg)

    try:
        rc, out, err = _run(cmd, env)
    except FileNotFoundError:
        _die("rf-jira: `jira` not found on PATH")

    combined = f"{out}\\n{err}"
    if rc == 0:
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
        if err:
            sys.stderr.write(err)
            sys.stderr.flush()
        return 0

    # Intermittent Jira 401s have been observed in some Codex-run sessions. Retry a few times
    # before surfacing the failure, alternating NETRC env handling (explicit NETRC vs HOME lookup).
    if "401 Unauthorized" in combined:
        max_tries = env.get("RF_JIRA_401_RETRIES", "").strip()
        tries = int(max_tries) if max_tries.isdigit() else 4
        tries = max(1, min(10, tries))

        last_rc, last_out, last_err = rc, out, err
        backoff = 0.5
        for attempt in range(1, tries + 1):
            time.sleep(backoff)
            backoff = min(4.0, backoff * 2)
            retry_env = dict(env)
            if attempt % 2 == 1:
                retry_env.pop("NETRC", None)
            else:
                if netrc.is_file():
                    retry_env["NETRC"] = str(netrc)
            _debug(retry_env, cfg=cfg)
            rc2, out2, err2 = _run(cmd, retry_env)
            if rc2 == 0:
                if out2:
                    sys.stdout.write(out2)
                    sys.stdout.flush()
                if err2:
                    sys.stderr.write(err2)
                    sys.stderr.flush()
                return 0
            last_rc, last_out, last_err = rc2, out2, err2
            if "401 Unauthorized" not in f"{out2}\\n{err2}":
                break

        if last_out:
            sys.stdout.write(last_out)
            sys.stdout.flush()
        if last_err:
            sys.stderr.write(last_err)
            sys.stderr.flush()
        return int(last_rc)

    if out:
        sys.stdout.write(out)
        sys.stdout.flush()
    if err:
        sys.stderr.write(err)
        sys.stderr.flush()
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def pr_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    global _ACTIVE_OUTPUT
    verbosity = resolve_verbosity(args)
    quiet = verbosity is Verbosity.quiet
    no_stream = bool(getattr(args, "no_stream", False))
    ui_enabled = resolve_ui_enabled(args, verbosity=verbosity)
    stream = (not quiet) and (not no_stream)

    if getattr(args, "agent_desc", None) and getattr(args, "agent_desc_file", None):
        raise ReviewflowError("Provide only one of --agent-desc or --agent-desc-file.")
    agent_desc = ""
    agent_desc_source = "none"
    if getattr(args, "agent_desc_file", None):
        agent_desc_source = "file"
        agent_desc = Path(str(args.agent_desc_file)).read_text(encoding="utf-8")
    elif getattr(args, "agent_desc", None):
        agent_desc_source = "inline"
        agent_desc = str(args.agent_desc)

    pr = parse_pr_url(args.pr_url)
    require_gh_auth(pr.host)
    ensure_review_config(paths)

    log(f"PR {pr.owner}/{pr.repo}#{pr.number} ({pr.host})", quiet=quiet)

    # PR metadata (base ref name + head SHA).
    with phase("resolve_pr_meta", progress=None, quiet=quiet):
        pr_api = run_cmd(
            [
                "gh",
                "api",
                "--hostname",
                pr.host,
                f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}",
            ]
        )
        pr_meta = json.loads(pr_api.stdout)
        base = pr_meta.get("base")
        head = pr_meta.get("head")
        base_ref = str((base.get("ref") if isinstance(base, dict) else "") or "").strip()
        head_sha = str((head.get("sha") if isinstance(head, dict) else "") or "").strip()
        title = str(pr_meta.get("title") or "").strip()

    if not base_ref:
        raise ReviewflowError("Failed to resolve baseRefName via `gh pr view`.")

    base_ref_for_review = f"reviewflow_base__{safe_ref_slug(base_ref)}"

    if_reviewed = str(getattr(args, "if_reviewed", "prompt") or "prompt").strip().lower()
    if if_reviewed not in {"prompt", "new", "list", "latest"}:
        raise ReviewflowError("--if-reviewed must be one of: prompt, new, list, latest")

    completed = scan_completed_sessions_for_pr(sandbox_root=paths.sandbox_root, pr=pr)
    if completed:
        _eprint(
            f"Found {len(completed)} completed prior review session(s) for "
            f"{pr.owner}/{pr.repo}#{pr.number}."
        )
        if if_reviewed == "prompt" and (not sys.stdin.isatty()):
            if_reviewed = "new"

        if if_reviewed == "list":
            _print_historical_sessions(completed)
            return 0
        if if_reviewed == "latest":
            latest = completed[0]
            text = latest.review_md_path.read_text(encoding="utf-8")
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
            return 0
        if if_reviewed == "prompt" and sys.stdin.isatty():
            selected = _choose_historical_session_tty(completed)
            if selected is not None:
                text = selected.review_md_path.read_text(encoding="utf-8")
                sys.stdout.write(text)
                if not text.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
                return 0
        _eprint("Proceeding with a new sandbox review.")

    session_root = paths.sandbox_root
    session_root.mkdir(parents=True, exist_ok=True)
    session_id = (
        f"{pr.owner}-{pr.repo}-pr{pr.number}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-"
        f"{secrets.token_hex(2)}"
    )
    session_dir = session_root / session_id
    repo_dir = session_dir / "repo"
    session_dir.mkdir(parents=True, exist_ok=False)

    work_dir = session_dir / "work"
    work_tmp_dir = work_dir / "tmp"
    chunkhound_work_dir = work_dir / "chunkhound"
    chunkhound_db_path = chunkhound_work_dir / ".chunkhound.db"
    chunkhound_cfg_path = chunkhound_work_dir / "chunkhound.json"
    logs_dir = work_dir / "logs"
    work_tmp_dir.mkdir(parents=True, exist_ok=True)
    chunkhound_work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    materialize_chunkhound_env_config(
        base_config_path=paths.review_chunkhound_config,
        output_config_path=chunkhound_cfg_path,
        database_provider="duckdb",
        database_path=chunkhound_db_path,
    )

    review_md_path = session_dir / "review.md"
    progress = SessionProgress(session_dir / "meta.json", quiet=quiet)
    prompt_profile_requested = str(getattr(args, "prompt_profile", "auto"))
    big_if_files = int(getattr(args, "big_if_files", 30))
    big_if_lines = int(getattr(args, "big_if_lines", 1500))
    progress.init(
        {
            "session_id": session_id,
            "created_at": _utc_now_iso(),
            "pr_url": args.pr_url,
            "host": pr.host,
            "owner": pr.owner,
            "repo": pr.repo,
            "number": pr.number,
            "title": title,
            "base_ref": base_ref,
            "base_ref_for_review": base_ref_for_review,
            "head_sha": head_sha,
            "paths": {
                "session_dir": str(session_dir),
                "repo_dir": str(repo_dir),
                "work_dir": str(work_dir),
                "work_tmp_dir": str(work_tmp_dir),
                "chunkhound_db": str(chunkhound_db_path),
                "chunkhound_cwd": str(chunkhound_work_dir),
                "chunkhound_config": str(chunkhound_cfg_path),
                "logs_dir": str(logs_dir),
                "review_md": str(review_md_path),
            },
            "base_cache": None,
            "notes": {
                "no_index": bool(args.no_index),
                "no_review": bool(args.no_review),
            },
            "agent_desc": {
                "source": agent_desc_source,
                "chars": len(agent_desc),
            },
            "options": {
                "quiet": quiet,
                "no_stream": no_stream,
                "ui": str(getattr(args, "ui", "auto") or "auto"),
                "ui_enabled": bool(ui_enabled),
                "verbosity": verbosity.value,
                "prompt_profile": prompt_profile_requested,
                "big_if_files": big_if_files,
                "big_if_lines": big_if_lines,
            },
        }
    )
    agent_desc_path = session_dir / "agent_desc.txt"
    agent_desc_path.write_text(agent_desc, encoding="utf-8")
    progress.meta.setdefault("paths", {})["agent_desc"] = str(agent_desc_path)
    progress.meta.setdefault("agent_desc", {})["sha256"] = sha256_text(agent_desc)
    progress.flush()
    # TUI/logging is started after meta.json exists (so the dashboard has something to read).
    out = ReviewflowOutput(
        ui_enabled=ui_enabled,
        no_stream=no_stream,
        stderr=sys.stderr,
        meta_path=progress.meta_path,
        logs_dir=logs_dir,
        verbosity=verbosity,
    )
    _ACTIVE_OUTPUT = out
    progress.meta["logs"] = {
        "reviewflow": str(logs_dir / "reviewflow.log"),
        "chunkhound": str(logs_dir / "chunkhound.log"),
        "codex": str(logs_dir / "codex.log"),
    }
    progress.flush()
    out.start()
    log(f"Session dir: {session_dir}", quiet=quiet)

    success_markdown_path: Path | None = None
    success_resume_command: str | None = None

    base_cache_meta: dict[str, Any] | None = None
    pr_stats: dict[str, Any] | None = None
    profile_resolved: str | None = None
    profile_reason: str | None = None
    profile_template_path: Path | None = None
    use_multipass = False
    crawl_cfg, crawl_meta = load_crawl_config()
    progress.meta["crawl"] = crawl_meta
    multipass_defaults, multipass_defaults_meta = load_reviewflow_multipass_defaults(
        config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH
    )
    progress.meta["multipass_defaults"] = multipass_defaults_meta
    cli_max_steps = getattr(args, "multipass_max_steps", None)
    if cli_max_steps is not None:
        try:
            cli_max_steps = int(cli_max_steps)
        except Exception:
            raise ReviewflowError("--multipass-max-steps must be an integer.")
        if cli_max_steps < 1:
            raise ReviewflowError("--multipass-max-steps must be >= 1.")
        if cli_max_steps > MULTIPASS_MAX_STEPS_HARD_CAP:
            raise ReviewflowError(
                f"--multipass-max-steps must be <= {MULTIPASS_MAX_STEPS_HARD_CAP}."
            )
        multipass_max_steps = cli_max_steps
        multipass_max_steps_source = "cli"
    else:
        multipass_max_steps = int(multipass_defaults.get("max_steps", DEFAULT_MULTIPASS_MAX_STEPS))
        multipass_max_steps_source = "reviewflow.toml"
    progress.meta["multipass"] = {
        "enabled": None,
        "max_steps": multipass_max_steps,
        "max_steps_source": multipass_max_steps_source,
        "mode": None,
        "plan_json_path": str(work_dir / "review_plan.json"),
        "artifacts": {},
        "runs": [],
    }
    progress.flush()
    try:
        if not args.no_index:
            with phase("ensure_base_cache", progress=progress, quiet=quiet):
                base_cache_meta = ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref=base_ref,
                    ttl_hours=int(args.base_ttl_hours),
                    refresh=bool(args.refresh_base),
                    quiet=quiet,
                    no_stream=no_stream,
                )
            progress.set_base_cache(base_cache_meta)

        # Create sandbox repo by cloning from seed for speed + object reuse.
        seed = seed_dir(paths, pr.host, pr.owner, pr.repo)
        if not seed.exists():
            raise ReviewflowError(
                f"Seed clone missing at {seed}. Try `reviewflow cache prime {pr.owner_repo} --base {base_ref}`."
            )

        with phase("seed_sanity", progress=progress, quiet=quiet):
            # The seed repo is a cache. Keep it clean so operations like rsync + checkout are safe.
            run_cmd(["git", "-C", str(seed), "rev-parse", "--is-inside-work-tree"])
            ensure_clean_git_worktree(repo_dir=seed)

        with phase("clone_seed", progress=progress, quiet=quiet):
            # Prefer a local clone for speed. If the seed and sandbox are on different devices,
            # hardlinks are not possible, so fall back to copying objects.
            clone_cmd = ["git", "clone"]
            if same_device(seed, session_dir):
                # Hardlinks (fast, self-contained, safe for kept sandboxes).
                clone_cmd.append("--local")
            else:
                clone_cmd.append("--no-hardlinks")
            clone_cmd.extend([str(seed), str(repo_dir)])
            progress.record_cmd(clone_cmd)
            run_cmd(clone_cmd)

            remote_url_cmd = ["git", "-C", str(seed), "remote", "get-url", "origin"]
            progress.record_cmd(remote_url_cmd)
            remote_url = run_cmd(remote_url_cmd).stdout.strip()
            if remote_url:
                set_remote_cmd = [
                    "git",
                    "-C",
                    str(repo_dir),
                    "remote",
                    "set-url",
                    "origin",
                    remote_url,
                ]
                progress.record_cmd(set_remote_cmd)
                run_cmd(set_remote_cmd)

            fetch_cmd = ["git", "-C", str(repo_dir), "fetch", "--prune", "origin"]
            progress.record_cmd(fetch_cmd)
            run_cmd(fetch_cmd)

        with phase("rsync_mtimes", progress=progress, quiet=quiet):
            checkout_base_cmd = [
                "git",
                "-C",
                str(repo_dir),
                "checkout",
                "-B",
                base_ref,
                f"origin/{base_ref}",
            ]
            progress.record_cmd(checkout_base_cmd)
            run_cmd(checkout_base_cmd)

            rsync_cmd = [
                "rsync",
                "-a",
                "--delete",
                "--exclude",
                ".git",
                "--exclude",
                ".DS_Store",
                "--exclude",
                "*/.DS_Store",
                f"{seed}/",
                f"{repo_dir}/",
            ]
            progress.record_cmd(rsync_cmd)
            run_cmd(rsync_cmd)
            ensure_clean_git_worktree(repo_dir=repo_dir)

        with phase("checkout_pr", progress=progress, quiet=quiet):
            checkout_pr_cmd = [
                "gh",
                "pr",
                "checkout",
                str(pr.number),
                "-R",
                pr.gh_repo,
                "--force",
            ]
            progress.record_cmd(checkout_pr_cmd)
            run_cmd(checkout_pr_cmd, cwd=repo_dir)
            review_head_sha_cmd = ["git", "-C", str(repo_dir), "rev-parse", "HEAD"]
            progress.record_cmd(review_head_sha_cmd)
            review_head_sha = run_cmd(review_head_sha_cmd).stdout.strip()
            if review_head_sha:
                progress.meta["review_head_sha"] = review_head_sha
                progress.flush()

        with phase("prepare_base_ref", progress=progress, quiet=quiet):
            fetch_base_cmd = ["git", "-C", str(repo_dir), "fetch", "origin", base_ref]
            progress.record_cmd(fetch_base_cmd)
            run_cmd(fetch_base_cmd)

            branch_cmd = [
                "git",
                "-C",
                str(repo_dir),
                "branch",
                "-f",
                base_ref_for_review,
                f"origin/{base_ref}",
            ]
            progress.record_cmd(branch_cmd)
            run_cmd(branch_cmd)

        with phase("detect_pr_size", progress=progress, quiet=quiet):
            try:
                pr_stats = compute_pr_stats(
                    repo_dir=repo_dir, base_ref=base_ref_for_review, head_ref="HEAD"
                )
            except ReviewflowSubprocessError as e:
                pr_stats = {
                    "detector": "git",
                    "base_ref": base_ref_for_review,
                    "head_ref": "HEAD",
                    "error": str(e),
                }
            progress.meta["pr_stats"] = pr_stats
            progress.flush()

        if args.prompt is None and args.prompt_file is None:
            with phase("select_prompt_profile", progress=progress, quiet=quiet):
                profile_resolved, profile_reason = resolve_prompt_profile(
                    requested=prompt_profile_requested,
                    pr_stats=pr_stats if pr_stats and "changed_lines" in pr_stats else None,
                    big_if_files=big_if_files,
                    big_if_lines=big_if_lines,
                )
                profile_template_path = prompt_template_path_for_profile(profile_resolved)
                progress.meta["prompt"] = {
                    "source": "profile",
                    "profile_requested": prompt_profile_requested,
                    "profile_resolved": profile_resolved,
                    "reason": profile_reason,
                    "template_path": str(profile_template_path),
                }
                progress.flush()

                if pr_stats and isinstance(pr_stats.get("changed_files"), int) and isinstance(
                    pr_stats.get("changed_lines"), int
                ):
                    log(
                        f"Selected prompt: {prompt_profile_requested}→{profile_resolved} "
                        f"(files={pr_stats['changed_files']}, lines={pr_stats['changed_lines']})",
                        quiet=quiet,
                    )
                else:
                    log(
                        f"Selected prompt: {prompt_profile_requested}→{profile_resolved} ({profile_reason})",
                        quiet=quiet,
                    )

                cli_multipass = getattr(args, "multipass", None)
                mp_default_enabled = bool(multipass_defaults.get("enabled", DEFAULT_MULTIPASS_ENABLED))
                if cli_multipass is True:
                    if profile_resolved != "big":
                        raise ReviewflowError(
                            "Multipass is only supported for the built-in big prompt profile."
                        )
                    use_multipass = True
                    mp_enabled_source = "cli"
                elif cli_multipass is False:
                    use_multipass = False
                    mp_enabled_source = "cli"
                else:
                    use_multipass = (profile_resolved == "big") and mp_default_enabled
                    mp_enabled_source = "reviewflow.toml"

                progress.meta.setdefault("multipass", {})["enabled"] = bool(use_multipass)
                progress.meta.setdefault("multipass", {})["enabled_source"] = mp_enabled_source
                progress.meta.setdefault("multipass", {})[
                    "mode"
                ] = "multipass" if use_multipass else "singlepass"
                progress.flush()

                if bool(getattr(args, "no_index", False)) and (not bool(getattr(args, "no_review", False))):
                    raise ReviewflowError(
                        "--no-index is not supported with the built-in prompt profiles. "
                        "These prompts require sandbox-scoped ChunkHound MCP; run without --no-index, "
                        "or use a custom --prompt/--prompt-file that does not require ChunkHound."
                    )

        if not args.no_index:
            assert base_cache_meta is not None
            base_db_path = Path(str(base_cache_meta["db_path"]))
            if not base_db_path.exists():
                raise ReviewflowError(f"Base DB missing: {base_db_path}")

            with phase("index_topup", progress=progress, quiet=quiet):
                log(
                    f"ChunkHound top-up index: db={chunkhound_db_path}",
                    quiet=quiet,
                )
                if chunkhound_db_path.exists():
                    if chunkhound_db_path.is_dir():
                        shutil.rmtree(chunkhound_db_path, ignore_errors=True)
                    else:
                        chunkhound_db_path.unlink(missing_ok=True)
                copy_duckdb_files(base_db_path, chunkhound_db_path)

                env = merged_env(chunkhound_env(paths))
                index_cmd = [
                    "chunkhound",
                    "index",
                    str(repo_dir),
                    "--config",
                    str(chunkhound_cfg_path),
                ]
                progress.record_cmd(index_cmd)
                out = _ACTIVE_OUTPUT
                if out is not None:
                    out.run_logged_cmd(
                        index_cmd,
                        kind="chunkhound",
                        cwd=chunkhound_work_dir,
                        env=env,
                        check=True,
                        stream_requested=stream,
                    )
                else:
                    run_cmd(
                        index_cmd,
                        cwd=chunkhound_work_dir,
                        env=env,
                        stream=stream,
                        stream_label="chunkhound",
                    )

        # Review phase
        if args.prompt is not None or args.prompt_file is not None:
            # Multipass is intentionally only supported for built-in profile prompts (big/auto->big).
            use_multipass = False
            progress.meta.setdefault("multipass", {})["enabled"] = False
            progress.meta.setdefault("multipass", {})["enabled_source"] = "forced_off:custom_prompt"
            progress.meta.setdefault("multipass", {})["mode"] = "singlepass"
            progress.flush()

        if not args.no_review:
            env = merged_env(chunkhound_env(paths))
            gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
            if gh_cfg:
                env["GH_CONFIG_DIR"] = str(gh_cfg)
            jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
            if jira_cfg:
                env["JIRA_CONFIG_FILE"] = str(jira_cfg)
            netrc = real_user_home_dir() / ".netrc"
            if netrc.is_file():
                env["NETRC"] = str(netrc)
            env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
            env.update(crawl_env(crawl_cfg))
            rf_fetch = write_rf_fetch_url(repo_dir=repo_dir, cfg=crawl_cfg)
            rf_jira = write_rf_jira(repo_dir=repo_dir)

            base_codex_config_path = Path("/workspaces/academy+/.codex/config.toml")
            codex_flags, codex_meta = resolve_codex_flags(
                base_config_path=base_codex_config_path,
                reviewflow_config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH,
                cli_model=getattr(args, "codex_model", None),
                cli_effort=getattr(args, "codex_effort", None),
                cli_plan_effort=getattr(args, "codex_plan_effort", None),
            )
            codex_overrides = codex_mcp_overrides_for_reviewflow(
                enable_sandbox_chunkhound=(not bool(getattr(args, "no_index", False))),
                sandbox_repo_dir=repo_dir,
                chunkhound_db_path=chunkhound_db_path,
                chunkhound_cwd=chunkhound_work_dir,
                chunkhound_config_path=chunkhound_cfg_path,
                paths=paths,
            )
            progress.meta["codex"] = {
                "config": codex_meta,
                "dangerously_bypass_approvals_and_sandbox": True,
                "config_overrides": codex_overrides,
                "flags": codex_flags,
                "env": {
                    "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
                    "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
                    "NETRC": env.get("NETRC"),
                    "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
                    "REVIEWFLOW_CRAWL_ALLOW_HOSTS": env.get("REVIEWFLOW_CRAWL_ALLOW_HOSTS"),
                    "REVIEWFLOW_CRAWL_TIMEOUT_SECONDS": env.get("REVIEWFLOW_CRAWL_TIMEOUT_SECONDS"),
                    "REVIEWFLOW_CRAWL_MAX_BYTES": env.get("REVIEWFLOW_CRAWL_MAX_BYTES"),
                },
                "helpers": {"rf_fetch_url": str(rf_fetch), "rf_jira": str(rf_jira)},
            }
            progress.flush()

            add_dirs = [session_dir]
            if not args.no_index:
                log(
                    "Codex MCP: sandbox ChunkHound enabled (daemon; startup_timeout_sec=20)",
                    quiet=quiet,
                )
            else:
                log("Codex MCP: sandbox ChunkHound disabled (--no-index)", quiet=quiet)

            if use_multipass:
                templates = multipass_prompt_template_paths()
                for k, pth in templates.items():
                    if not pth.is_file():
                        raise ReviewflowError(f"Missing multipass prompt template ({k}): {pth}")

                plan_md_path = session_dir / "review.plan.md"
                progress.meta.setdefault("multipass", {}).setdefault("artifacts", {})[
                    "plan_md"
                ] = str(plan_md_path)
                progress.meta.setdefault("multipass", {})["current"] = {
                    "stage": "plan",
                    "step_index": 0,
                    "step_count": int(multipass_max_steps),
                    "step_title": "plan",
                }
                progress.flush()

                with phase("codex_plan", progress=progress, quiet=quiet):
                    plan_template = templates["plan"].read_text(encoding="utf-8")
                    plan_prompt = render_prompt(
                        plan_template,
                        base_ref_for_review=base_ref_for_review,
                        pr_url=str(args.pr_url),
                        pr_number=int(pr.number),
                        gh_host=str(pr.host),
                        gh_owner=str(pr.owner),
                        gh_repo_name=str(pr.repo),
                        gh_repo=str(pr.gh_repo),
                        agent_desc=agent_desc,
                        head_ref="HEAD",
                        extra_vars={"MAX_STEPS": str(multipass_max_steps)},
                    )
                    progress.meta.setdefault("multipass", {}).setdefault("runs", []).append(
                        {
                            "kind": "plan",
                            "template_path": str(templates["plan"]),
                            "output_path": str(plan_md_path),
                            "prompt_chars": len(plan_prompt),
                            "prompt_sha256": sha256_text(plan_prompt),
                        }
                    )
                    progress.flush()
                    plan_result = run_codex_exec(
                        repo_dir=repo_dir,
                        codex_flags=codex_flags,
                        codex_config_overrides=codex_overrides,
                        output_path=plan_md_path,
                        prompt=plan_prompt,
                        env=env,
                        stream=stream,
                        progress=progress,
                        add_dirs=add_dirs,
                    )
                    plan_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                    if plan_runs and isinstance(plan_runs[-1], dict) and plan_result.resume is not None:
                        plan_runs[-1]["codex_session_id"] = plan_result.resume.session_id
                        progress.flush()

                plan_text = plan_md_path.read_text(encoding="utf-8") if plan_md_path.is_file() else ""
                try:
                    plan = parse_multipass_plan_json(plan_text)
                except ReviewflowError as e:
                    log(
                        f"Multipass plan parse failed; falling back to single-pass big review: {e}",
                        quiet=quiet,
                    )
                    use_multipass = False
                    progress.meta.setdefault("multipass", {})["enabled"] = False
                    progress.meta.setdefault("multipass", {})["mode"] = "fallback_singlepass"
                    progress.meta.setdefault("multipass", {})["fallback_reason"] = str(e)
                    progress.meta.setdefault("multipass", {}).pop("current", None)
                    progress.flush()
                else:
                    plan_json_path = work_dir / "review_plan.json"
                    plan_json_path.write_text(
                        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    progress.meta.setdefault("multipass", {})["plan_json_path"] = str(plan_json_path)
                    progress.meta.setdefault("multipass", {})["plan"] = {
                        "abort": bool(plan.get("abort")),
                        "abort_reason": plan.get("abort_reason"),
                        "step_count": len(plan.get("steps") or []),
                    }
                    progress.flush()

                    if bool(plan.get("abort")):
                        reason = str(plan.get("abort_reason") or "unknown")
                        review_md_path.write_text(
                            "\n".join(
                                [
                                    "### Steps taken",
                                    "- Multipass plan aborted",
                                    "",
                                    f"**Summary**: ABORT: {reason}",
                                    "**Strengths**: []",
                                    "**Issues**: []",
                                    "**Reusability**: []",
                                    "**Decision**: REJECT",
                                    "####",
                                    "",
                                ]
                            ),
                            encoding="utf-8",
                        )
                        progress.meta.setdefault("multipass", {})["status"] = "abort"
                        progress.flush()
                        try:
                            decision = extract_decision_from_markdown(
                                review_md_path.read_text(encoding="utf-8")
                            )
                            if decision:
                                progress.meta["decision"] = decision
                                progress.flush()
                        except Exception:
                            pass
                        progress.done()
                        success_markdown_path = review_md_path
                        print(str(session_dir))
                        return 0

                    steps = plan.get("steps") or []
                    if not isinstance(steps, list):
                        raise ReviewflowError("Multipass plan steps must be a list.")
                    if len(steps) > multipass_max_steps:
                        raise ReviewflowError(
                            f"Multipass plan produced {len(steps)} steps, exceeding max_steps={multipass_max_steps}."
                        )

                    progress.meta.setdefault("multipass", {})["current"] = {
                        "stage": "steps",
                        "step_index": 0,
                        "step_count": int(len(steps)),
                        "step_title": "",
                    }
                    progress.flush()

                    step_outputs: list[str] = []
                    for idx, step in enumerate(steps, start=1):
                        step_id = str(step.get("id") or f"{idx:02d}").strip()
                        step_title = str(step.get("title") or "").strip()
                        step_focus = str(step.get("focus") or "").strip()
                        out_path = session_dir / f"review.step-{idx:02d}.md"
                        step_outputs.append(str(out_path))
                        progress.meta.setdefault("multipass", {}).setdefault("artifacts", {}).setdefault(
                            "step_mds", []
                        ).append(str(out_path))
                        progress.meta.setdefault("multipass", {})["current"] = {
                            "stage": "step",
                            "step_index": int(idx),
                            "step_count": int(len(steps)),
                            "step_title": step_title,
                        }
                        progress.flush()

                        with phase(f"codex_step_{idx:02d}", progress=progress, quiet=quiet):
                            log(f"Multipass step {idx:02d}: {step_title}", quiet=quiet)
                            step_template = templates["step"].read_text(encoding="utf-8")
                            step_prompt = render_prompt(
                                step_template,
                                base_ref_for_review=base_ref_for_review,
                                pr_url=str(args.pr_url),
                                pr_number=int(pr.number),
                                gh_host=str(pr.host),
                                gh_owner=str(pr.owner),
                                gh_repo_name=str(pr.repo),
                                gh_repo=str(pr.gh_repo),
                                agent_desc=agent_desc,
                                head_ref="HEAD",
                                extra_vars={
                                    "PLAN_JSON_PATH": str(plan_json_path),
                                    "STEP_ID": step_id,
                                    "STEP_TITLE": step_title,
                                    "STEP_FOCUS": step_focus,
                                },
                            )
                            progress.meta.setdefault("multipass", {}).setdefault("runs", []).append(
                                {
                                    "kind": "step",
                                    "step_index": idx,
                                    "step_id": step_id,
                                    "step_title": step_title,
                                    "output_path": str(out_path),
                                    "template_path": str(templates["step"]),
                                    "prompt_chars": len(step_prompt),
                                    "prompt_sha256": sha256_text(step_prompt),
                                }
                            )
                            progress.flush()
                            try:
                                step_result = run_codex_exec(
                                    repo_dir=repo_dir,
                                    codex_flags=codex_flags,
                                    codex_config_overrides=codex_overrides,
                                    output_path=out_path,
                                    prompt=step_prompt,
                                    env=env,
                                    stream=stream,
                                    progress=progress,
                                    add_dirs=add_dirs,
                                )
                                step_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                                if step_runs and isinstance(step_runs[-1], dict) and step_result.resume is not None:
                                    step_runs[-1]["codex_session_id"] = step_result.resume.session_id
                                    progress.flush()
                            except ReviewflowSubprocessError:
                                _eprint(
                                    f"Multipass step failed. To resume: python3 /workspaces/reviewflow/reviewflow.py resume {session_id}"
                                )
                                raise

                    progress.meta.setdefault("multipass", {}).setdefault("artifacts", {})[
                        "step_outputs"
                    ] = step_outputs
                    progress.meta.setdefault("multipass", {})["current"] = {
                        "stage": "synth",
                        "step_index": int(len(step_outputs)),
                        "step_count": int(len(step_outputs)),
                        "step_title": "synth",
                    }
                    progress.flush()

                    with phase("codex_synth", progress=progress, quiet=quiet):
                        synth_template = templates["synth"].read_text(encoding="utf-8")
                        step_paths_text = "\n".join(f"- `{p}`" for p in step_outputs)
                        synth_prompt = render_prompt(
                            synth_template,
                            base_ref_for_review=base_ref_for_review,
                            pr_url=str(args.pr_url),
                            pr_number=int(pr.number),
                            gh_host=str(pr.host),
                            gh_owner=str(pr.owner),
                            gh_repo_name=str(pr.repo),
                            gh_repo=str(pr.gh_repo),
                            agent_desc=agent_desc,
                            head_ref="HEAD",
                            extra_vars={
                                "PLAN_JSON_PATH": str(plan_json_path),
                                "STEP_OUTPUT_PATHS": step_paths_text,
                            },
                        )
                        progress.meta.setdefault("multipass", {}).setdefault("runs", []).append(
                            {
                                "kind": "synth",
                                "template_path": str(templates["synth"]),
                                "output_path": str(review_md_path),
                                "prompt_chars": len(synth_prompt),
                                "prompt_sha256": sha256_text(synth_prompt),
                            }
                        )
                        progress.flush()
                        synth_result = run_codex_exec(
                            repo_dir=repo_dir,
                            codex_flags=codex_flags,
                            codex_config_overrides=codex_overrides,
                            output_path=review_md_path,
                            prompt=synth_prompt,
                            env=env,
                            stream=stream,
                            progress=progress,
                            add_dirs=add_dirs,
                        )
                        synth_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                        if synth_runs and isinstance(synth_runs[-1], dict) and synth_result.resume is not None:
                            synth_runs[-1]["codex_session_id"] = synth_result.resume.session_id
                        success_resume_command = record_codex_resume(
                            progress.meta.setdefault("codex", {}), synth_result.resume
                        )
                        progress.flush()

                    progress.meta.setdefault("multipass", {})["status"] = "done"
                    progress.flush()

            if not use_multipass:
                with phase("load_prompt", progress=progress, quiet=quiet):
                    prompt: str | None = None
                    prompt_info: dict[str, Any] = {}
                    if args.prompt is not None:
                        prompt = args.prompt
                        prompt_info["source"] = "inline"
                    elif args.prompt_file is not None:
                        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
                        prompt_info["source"] = "file"
                        prompt_info["template_path"] = str(args.prompt_file)
                    else:
                        if profile_template_path is None:
                            profile_resolved, profile_reason = resolve_prompt_profile(
                                requested=prompt_profile_requested,
                                pr_stats=pr_stats if pr_stats and "changed_lines" in pr_stats else None,
                                big_if_files=big_if_files,
                                big_if_lines=big_if_lines,
                            )
                            profile_template_path = prompt_template_path_for_profile(profile_resolved)
                        if not profile_template_path.is_file():
                            raise ReviewflowError(f"Missing prompt template: {profile_template_path}")
                        prompt = profile_template_path.read_text(encoding="utf-8")
                        prompt_info.update(
                            {
                                "source": "profile",
                                "profile_requested": prompt_profile_requested,
                                "profile_resolved": profile_resolved,
                                "reason": profile_reason,
                                "template_path": str(profile_template_path),
                            }
                        )

                    if not prompt and not args.no_review:
                        raise ReviewflowError("No prompt provided and no prompt template could be loaded.")
                    if prompt:
                        rendered = render_prompt(
                            prompt,
                            base_ref_for_review=base_ref_for_review,
                            pr_url=str(args.pr_url),
                            pr_number=int(pr.number),
                            gh_host=str(pr.host),
                            gh_owner=str(pr.owner),
                            gh_repo_name=str(pr.repo),
                            gh_repo=str(pr.gh_repo),
                            agent_desc=agent_desc,
                            head_ref="HEAD",
                        )
                        prompt_info["prompt_chars"] = len(rendered)
                        prompt_info["prompt_sha256"] = sha256_text(rendered)
                        progress.meta["prompt"] = prompt_info
                        progress.flush()
                        prompt = rendered

                assert prompt is not None
                with phase("codex_review", progress=progress, quiet=quiet):
                    review_result = run_codex_exec(
                        repo_dir=repo_dir,
                        codex_flags=codex_flags,
                        codex_config_overrides=codex_overrides,
                        output_path=review_md_path,
                        prompt=prompt,
                        env=env,
                        stream=stream,
                        progress=progress,
                        add_dirs=add_dirs,
                    )
                    success_resume_command = record_codex_resume(
                        progress.meta.setdefault("codex", {}), review_result.resume
                    )
                    progress.flush()

        try:
            decision = extract_decision_from_markdown(review_md_path.read_text(encoding="utf-8"))
            if decision:
                progress.meta["decision"] = decision
                progress.flush()
        except Exception:
            pass
        progress.done()
        success_markdown_path = review_md_path
    except ReviewflowSubprocessError as e:
        progress.error(
            {
                "type": "subprocess",
                "message": str(e),
                "cmd": safe_cmd_for_meta(e.cmd),
                "cwd": str(e.cwd) if e.cwd else None,
                "exit_code": e.exit_code,
                "stdout_tail": e.stdout,
                "stderr_tail": e.stderr,
            }
        )
        raise
    except Exception as e:
        progress.error(
            {
                "type": "exception",
                "message": str(e),
            }
        )
        raise
    finally:
        if _ACTIVE_OUTPUT is out:
            _ACTIVE_OUTPUT = None
        out.stop()
        maybe_print_markdown_after_tui(
            ui_enabled=ui_enabled, stderr=out.stderr, markdown_path=success_markdown_path
        )
        maybe_print_codex_resume_command(stderr=out.stderr, command=success_resume_command)

    # Success: keep stdout machine-friendly for scripting.
    print(str(session_dir))
    return 0


def resume_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    global _ACTIVE_OUTPUT
    verbosity = resolve_verbosity(args)
    quiet = verbosity is Verbosity.quiet
    no_stream = bool(getattr(args, "no_stream", False))
    ui_enabled = resolve_ui_enabled(args, verbosity=verbosity)
    stream = (not quiet) and (not no_stream)

    if bool(getattr(args, "no_index", False)):
        raise ReviewflowError(
            "resume does not support --no-index. Multipass resumption requires sandbox-scoped ChunkHound MCP."
        )

    from_phase = str(getattr(args, "from_phase", "auto") or "auto").strip().lower()
    if from_phase not in {"auto", "plan", "steps", "synth"}:
        raise ReviewflowError("--from must be one of: auto, plan, steps, synth")

    target = str(getattr(args, "session_id", "") or "").strip()
    session_id, action = resolve_resume_target(target, sandbox_root=paths.sandbox_root, from_phase=from_phase)

    if action == "followup":
        followup_args = argparse.Namespace(
            session_id=session_id,
            no_update=False,
            codex_model=getattr(args, "codex_model", None),
            codex_effort=getattr(args, "codex_effort", None),
            codex_plan_effort=getattr(args, "codex_plan_effort", None),
            quiet=bool(getattr(args, "quiet", False)),
            no_stream=bool(getattr(args, "no_stream", False)),
            ui=str(getattr(args, "ui", "auto") or "auto"),
            verbosity=str(getattr(args, "verbosity", "normal") or "normal"),
        )
        return followup_flow(followup_args, paths=paths)

    root = paths.sandbox_root.resolve()
    session_dir = (paths.sandbox_root / session_id).resolve()
    if root not in session_dir.parents:
        raise ReviewflowError(f"Refusing to access outside sandbox root: {session_dir}")
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise ReviewflowError(
            f"Session meta.json not found: {meta_path}. "
            "Tip: run `python3 /workspaces/reviewflow/reviewflow.py list` to find a session id."
        )

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReviewflowError(f"Failed to parse meta.json: {e}") from e

    meta_paths = meta.get("paths") or {}
    meta_paths = meta_paths if isinstance(meta_paths, dict) else {}

    repo_dir = Path(str((meta_paths.get("repo_dir")) or "")).resolve()
    review_md_raw = str((meta_paths.get("review_md")) or "").strip()
    review_md_path = Path(review_md_raw).resolve() if review_md_raw else (session_dir / "review.md").resolve()
    pr_url = str(meta.get("pr_url") or "").strip()
    if not repo_dir.is_dir():
        raise ReviewflowError(f"Session repo_dir missing: {repo_dir}")
    if not pr_url:
        raise ReviewflowError("Session meta missing pr_url.")

    already_done = (
        from_phase == "auto"
        and review_md_path.is_file()
        and (
            str(meta.get("status") or "").strip() == "done"
            or bool(str(meta.get("completed_at") or "").strip())
        )
    )
    if already_done:
        # Fast no-op for completed sessions (do not rewrite meta.json).
        print(str(session_dir))
        maybe_print_markdown_after_tui(ui_enabled=ui_enabled, stderr=sys.stderr, markdown_path=review_md_path)
        existing_codex = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
        existing_resume = existing_codex.get("resume") if isinstance(existing_codex.get("resume"), dict) else {}
        existing_resume_cmd = str((existing_resume or {}).get("command") or "").strip() or None
        maybe_print_codex_resume_command(stderr=sys.stderr, command=existing_resume_cmd)
        return 0

    work_dir = Path(str(meta_paths.get("work_dir") or (session_dir / "work"))).resolve()
    work_tmp_dir = Path(str(meta_paths.get("work_tmp_dir") or (work_dir / "tmp"))).resolve()
    chunkhound_work_dir = Path(str(meta_paths.get("chunkhound_cwd") or (work_dir / "chunkhound"))).resolve()
    chunkhound_db_path = Path(
        str(meta_paths.get("chunkhound_db") or (chunkhound_work_dir / ".chunkhound.db"))
    ).resolve()
    chunkhound_cfg_path = Path(
        str(meta_paths.get("chunkhound_config") or (chunkhound_work_dir / "chunkhound.json"))
    ).resolve()
    work_tmp_dir.mkdir(parents=True, exist_ok=True)
    chunkhound_work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = work_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    if (not chunkhound_db_path.exists()) and (repo_dir / ".chunkhound.db").exists():
        # Legacy sessions stored the DB under the sandbox repo.
        chunkhound_db_path = (repo_dir / ".chunkhound.db").resolve()

    session_no_index = bool(((meta.get("notes") or {}).get("no_index")) or False)
    if session_no_index:
        raise ReviewflowError(
            "This session was created with --no-index and cannot be resumed as a multipass review. "
            "Re-run the review without --no-index."
        )

    pr = parse_pr_url(pr_url)
    require_gh_auth(pr.host)
    ensure_review_config(paths)
    # Always refresh the session-local ChunkHound config so it tracks updates
    # in /workspaces/.chunkhound.review.json on every resume run.
    materialize_chunkhound_env_config(
        base_config_path=paths.review_chunkhound_config,
        output_config_path=chunkhound_cfg_path,
        database_provider="duckdb",
        database_path=chunkhound_db_path,
    )
    meta_paths["chunkhound_config"] = str(chunkhound_cfg_path)
    meta["paths"] = meta_paths

    progress = SessionProgress(meta_path, quiet=quiet)
    progress.meta = dict(meta)
    progress.meta["status"] = "running"
    # Resuming re-opens the session; clear completion/failure markers so the UI can
    # correctly show an active spinner and listings don't treat it as completed.
    progress.meta.pop("completed_at", None)
    progress.meta.pop("failed_at", None)
    progress.meta.pop("error", None)
    progress.meta["resumed_at"] = _utc_now_iso()
    progress.meta.setdefault("options", {})["quiet"] = quiet
    progress.meta.setdefault("options", {})["no_stream"] = no_stream
    progress.meta.setdefault("options", {})["ui"] = str(getattr(args, "ui", "auto") or "auto")
    progress.meta.setdefault("options", {})["ui_enabled"] = bool(ui_enabled)
    progress.meta.setdefault("options", {})["verbosity"] = verbosity.value
    progress.meta.setdefault("paths", {})["logs_dir"] = str(logs_dir)
    progress.flush()

    out = ReviewflowOutput(
        ui_enabled=ui_enabled,
        no_stream=no_stream,
        stderr=sys.stderr,
        meta_path=meta_path,
        logs_dir=logs_dir,
        verbosity=verbosity,
    )
    _ACTIVE_OUTPUT = out
    progress.meta["logs"] = {
        "reviewflow": str(logs_dir / "reviewflow.log"),
        "chunkhound": str(logs_dir / "chunkhound.log"),
        "codex": str(logs_dir / "codex.log"),
    }
    progress.flush()
    out.start()

    success_markdown_path: Path | None = None
    success_resume_command: str | None = None

    try:
        agent_desc = ""
        agent_desc_path = Path(str(((meta.get("paths") or {}).get("agent_desc")) or "")).resolve()
        if agent_desc_path.is_file():
            agent_desc = agent_desc_path.read_text(encoding="utf-8")

        base_ref_for_review = str(meta.get("base_ref_for_review") or "").strip()
        if not base_ref_for_review:
            raise ReviewflowError("Session meta missing base_ref_for_review.")

        crawl_cfg, crawl_meta = load_crawl_config()
        progress.meta["crawl"] = crawl_meta
        progress.flush()

        env = merged_env(chunkhound_env(paths))
        gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
        if gh_cfg:
            env["GH_CONFIG_DIR"] = str(gh_cfg)
        jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
        if jira_cfg:
            env["JIRA_CONFIG_FILE"] = str(jira_cfg)
        netrc = real_user_home_dir() / ".netrc"
        if netrc.is_file():
            env["NETRC"] = str(netrc)
        env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
        env.update(crawl_env(crawl_cfg))
        rf_fetch = write_rf_fetch_url(repo_dir=repo_dir, cfg=crawl_cfg)
        rf_jira = write_rf_jira(repo_dir=repo_dir)

        base_codex_config_path = Path("/workspaces/academy+/.codex/config.toml")
        codex_flags, codex_meta = resolve_codex_flags(
            base_config_path=base_codex_config_path,
            reviewflow_config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH,
            cli_model=getattr(args, "codex_model", None),
            cli_effort=getattr(args, "codex_effort", None),
            cli_plan_effort=getattr(args, "codex_plan_effort", None),
        )

        no_index = False
        codex_overrides = codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=(not no_index),
            sandbox_repo_dir=repo_dir,
            chunkhound_db_path=chunkhound_db_path,
            chunkhound_cwd=chunkhound_work_dir,
            chunkhound_config_path=chunkhound_cfg_path,
            paths=paths,
        )
        progress.meta["codex"] = {
            "config": codex_meta,
            "dangerously_bypass_approvals_and_sandbox": True,
            "config_overrides": codex_overrides,
            "flags": codex_flags,
            "env": {
                "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
                "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
                "NETRC": env.get("NETRC"),
                "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
                "REVIEWFLOW_CRAWL_ALLOW_HOSTS": env.get("REVIEWFLOW_CRAWL_ALLOW_HOSTS"),
                "REVIEWFLOW_CRAWL_TIMEOUT_SECONDS": env.get("REVIEWFLOW_CRAWL_TIMEOUT_SECONDS"),
                "REVIEWFLOW_CRAWL_MAX_BYTES": env.get("REVIEWFLOW_CRAWL_MAX_BYTES"),
            },
            "helpers": {"rf_fetch_url": str(rf_fetch), "rf_jira": str(rf_jira)},
        }
        progress.flush()

        add_dirs = [session_dir]
        if not no_index:
            log(
                "Codex MCP: sandbox ChunkHound enabled (daemon; startup_timeout_sec=20)",
                quiet=quiet,
            )
        else:
            log("Codex MCP: sandbox ChunkHound disabled (--no-index)", quiet=quiet)

        templates = multipass_prompt_template_paths()
        for k, pth in templates.items():
            if not pth.is_file():
                raise ReviewflowError(f"Missing multipass prompt template ({k}): {pth}")

        # If already complete, no-op.
        if from_phase == "auto" and review_md_path.is_file() and str(meta.get("status")) == "done":
            success_markdown_path = review_md_path
            print(str(session_dir))
            return 0

        multipass_cfg, _ = load_reviewflow_multipass_defaults(
            config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH
        )
        cli_max_steps = getattr(args, "multipass_max_steps", None)
        if cli_max_steps is not None:
            max_steps = int(cli_max_steps)
            if max_steps < 1 or max_steps > MULTIPASS_MAX_STEPS_HARD_CAP:
                raise ReviewflowError(
                    f"--multipass-max-steps must be between 1 and {MULTIPASS_MAX_STEPS_HARD_CAP}."
                )
        else:
            max_steps = int(multipass_cfg.get("max_steps", DEFAULT_MULTIPASS_MAX_STEPS))

        plan_md_path = session_dir / "review.plan.md"
        mp_meta = meta.get("multipass") or {}
        mp_meta = mp_meta if isinstance(mp_meta, dict) else {}
        mp_plan_json = str(mp_meta.get("plan_json_path") or "").strip()

        preferred_plan_json = (work_dir / "review_plan.json").resolve()
        plan_json_candidates: list[Path] = []
        legacy_repo_plan_json: Path | None = None
        if mp_plan_json:
            candidate = Path(mp_plan_json).resolve()
            if repo_dir in candidate.parents:
                legacy_repo_plan_json = candidate
            elif session_dir in candidate.parents:
                plan_json_candidates.append(candidate)
        plan_json_candidates.append(preferred_plan_json)

        if legacy_repo_plan_json and legacy_repo_plan_json.is_file() and (not preferred_plan_json.is_file()):
            preferred_plan_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_repo_plan_json, preferred_plan_json)

        plan_json_path = next((p for p in plan_json_candidates if p.is_file()), preferred_plan_json)
        if repo_dir in plan_json_path.parents:
            raise ReviewflowError(
                f"Refusing to use multipass plan JSON under the repo tree: {plan_json_path}"
            )
        plan_json_path.parent.mkdir(parents=True, exist_ok=True)
        progress.meta.setdefault("multipass", {})["plan_json_path"] = str(plan_json_path)
        progress.flush()

        did_work = False

        if from_phase in {"plan", "auto"} and (from_phase == "plan" or not plan_json_path.is_file()):
            progress.meta.setdefault("multipass", {})["enabled"] = True
            progress.meta.setdefault("multipass", {})["current"] = {
                "stage": "plan",
                "step_index": 0,
                "step_count": int(max_steps),
                "step_title": "plan",
            }
            progress.flush()
            with phase("codex_plan", progress=progress, quiet=quiet):
                did_work = True
                plan_template = templates["plan"].read_text(encoding="utf-8")
                plan_prompt = render_prompt(
                    plan_template,
                    base_ref_for_review=base_ref_for_review,
                    pr_url=pr_url,
                    pr_number=int(meta.get("number") or pr.number),
                    gh_host=str(pr.host),
                    gh_owner=str(pr.owner),
                    gh_repo_name=str(pr.repo),
                    gh_repo=str(pr.gh_repo),
                    agent_desc=agent_desc,
                    head_ref="HEAD",
                    extra_vars={"MAX_STEPS": str(max_steps)},
                )
                plan_result = run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=codex_flags,
                    codex_config_overrides=codex_overrides,
                    output_path=plan_md_path,
                    prompt=plan_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                )
                success_resume_command = record_codex_resume(
                    progress.meta.setdefault("codex", {}), plan_result.resume
                )
                progress.flush()
            plan_text = plan_md_path.read_text(encoding="utf-8") if plan_md_path.is_file() else ""
            plan = parse_multipass_plan_json(plan_text)
            plan_json_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

        if not plan_json_path.is_file():
            raise ReviewflowError(f"Missing multipass plan JSON: {plan_json_path}")

        plan = json.loads(plan_json_path.read_text(encoding="utf-8"))
        if bool(plan.get("abort")):
            reason = str(plan.get("abort_reason") or "unknown")
            progress.meta.setdefault("multipass", {})["enabled"] = True
            progress.meta.setdefault("multipass", {})["current"] = {
                "stage": "abort",
                "step_index": 0,
                "step_count": 0,
                "step_title": str(reason),
            }
            progress.flush()
            review_md_path.write_text(
                "\n".join(
                    [
                        "### Steps taken",
                        "- Multipass plan aborted",
                        "",
                        f"**Summary**: ABORT: {reason}",
                        "**Strengths**: []",
                        "**Issues**: []",
                        "**Reusability**: []",
                        "**Decision**: REJECT",
                        "####",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                decision = extract_decision_from_markdown(
                    review_md_path.read_text(encoding="utf-8")
                )
                if decision:
                    progress.meta["decision"] = decision
                    progress.flush()
            except Exception:
                pass
            progress.done()
            success_markdown_path = review_md_path
            print(str(session_dir))
            return 0

        steps = plan.get("steps") or []
        if not isinstance(steps, list) or not steps:
            raise ReviewflowError("Multipass plan steps missing/invalid.")
        if len(steps) > max_steps:
            raise ReviewflowError(f"Multipass plan has {len(steps)} steps > max_steps={max_steps}.")

        progress.meta.setdefault("multipass", {})["enabled"] = True
        progress.meta.setdefault("multipass", {})["current"] = {
            "stage": "steps",
            "step_index": 0,
            "step_count": int(len(steps)),
            "step_title": "",
        }
        progress.flush()

        step_outputs: list[str] = []
        for idx, step in enumerate(steps, start=1):
            out_path = session_dir / f"review.step-{idx:02d}.md"
            step_outputs.append(str(out_path))

            if from_phase == "synth":
                continue
            if from_phase in {"plan"}:
                should_run = True
            else:
                should_run = (not out_path.is_file()) or (out_path.stat().st_size == 0)
            if not should_run:
                continue

            step_id = str(step.get("id") or f"{idx:02d}").strip()
            step_title = str(step.get("title") or "").strip()
            step_focus = str(step.get("focus") or "").strip()
            progress.meta.setdefault("multipass", {})["current"] = {
                "stage": "step",
                "step_index": int(idx),
                "step_count": int(len(steps)),
                "step_title": step_title,
            }
            progress.flush()

            with phase(f"codex_step_{idx:02d}", progress=progress, quiet=quiet):
                did_work = True
                log(f"Multipass step {idx:02d}: {step_title}", quiet=quiet)
                step_template = templates["step"].read_text(encoding="utf-8")
                step_prompt = render_prompt(
                    step_template,
                    base_ref_for_review=base_ref_for_review,
                    pr_url=pr_url,
                    pr_number=int(meta.get("number") or pr.number),
                    gh_host=str(pr.host),
                    gh_owner=str(pr.owner),
                    gh_repo_name=str(pr.repo),
                    gh_repo=str(pr.gh_repo),
                    agent_desc=agent_desc,
                    head_ref="HEAD",
                    extra_vars={
                        "PLAN_JSON_PATH": str(plan_json_path),
                        "STEP_ID": step_id,
                        "STEP_TITLE": step_title,
                        "STEP_FOCUS": step_focus,
                    },
                )
                step_result = run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=codex_flags,
                    codex_config_overrides=codex_overrides,
                    output_path=out_path,
                    prompt=step_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                )
                success_resume_command = record_codex_resume(
                    progress.meta.setdefault("codex", {}), step_result.resume
                )
                progress.flush()

        should_synth = from_phase in {"synth", "plan", "steps"} or (not review_md_path.is_file())
        if should_synth:
            progress.meta.setdefault("multipass", {})["current"] = {
                "stage": "synth",
                "step_index": int(len(step_outputs)),
                "step_count": int(len(step_outputs)),
                "step_title": "synth",
            }
            progress.flush()
            with phase("codex_synth", progress=progress, quiet=quiet):
                did_work = True
                synth_template = templates["synth"].read_text(encoding="utf-8")
                step_paths_text = "\n".join(f"- `{p}`" for p in step_outputs)
                synth_prompt = render_prompt(
                    synth_template,
                    base_ref_for_review=base_ref_for_review,
                    pr_url=pr_url,
                    pr_number=int(meta.get("number") or pr.number),
                    gh_host=str(pr.host),
                    gh_owner=str(pr.owner),
                    gh_repo_name=str(pr.repo),
                    gh_repo=str(pr.gh_repo),
                    agent_desc=agent_desc,
                    head_ref="HEAD",
                    extra_vars={
                        "PLAN_JSON_PATH": str(plan_json_path),
                        "STEP_OUTPUT_PATHS": step_paths_text,
                    },
                )
                synth_result = run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=codex_flags,
                    codex_config_overrides=codex_overrides,
                    output_path=review_md_path,
                    prompt=synth_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                )
                success_resume_command = record_codex_resume(
                    progress.meta.setdefault("codex", {}), synth_result.resume
                )
                progress.flush()

        if did_work:
            progress.meta["status"] = "running"
            progress.flush()
        try:
            decision = extract_decision_from_markdown(review_md_path.read_text(encoding="utf-8"))
            if decision:
                progress.meta["decision"] = decision
                progress.flush()
        except Exception:
            pass
        progress.done()
        success_markdown_path = review_md_path
        print(str(session_dir))
        return 0
    except ReviewflowSubprocessError as e:
        progress.error(
            {
                "type": "subprocess",
                "message": str(e),
                "cmd": safe_cmd_for_meta(e.cmd),
                "cwd": str(e.cwd) if e.cwd else None,
                "exit_code": e.exit_code,
                "stdout_tail": e.stdout,
                "stderr_tail": e.stderr,
            }
        )
        raise
    except Exception as e:
        progress.error({"type": "exception", "message": str(e)})
        raise
    finally:
        if _ACTIVE_OUTPUT is out:
            _ACTIVE_OUTPUT = None
        out.stop()
        maybe_print_markdown_after_tui(
            ui_enabled=ui_enabled, stderr=out.stderr, markdown_path=success_markdown_path
        )
        maybe_print_codex_resume_command(stderr=out.stderr, command=success_resume_command)


def followup_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    global _ACTIVE_OUTPUT
    verbosity = resolve_verbosity(args)
    quiet = verbosity is Verbosity.quiet
    no_stream = bool(getattr(args, "no_stream", False))
    ui_enabled = resolve_ui_enabled(args, verbosity=verbosity)
    stream = (not quiet) and (not no_stream)

    session_id = str(getattr(args, "session_id", "") or "").strip()
    if not session_id:
        raise ReviewflowError("followup requires a session_id.")

    session_dir = paths.sandbox_root / session_id
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise ReviewflowError(f"Session meta.json not found: {meta_path}")

    meta = _load_session_meta(meta_path)
    if not meta:
        raise ReviewflowError(f"Failed to parse meta.json: {meta_path}")

    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    repo_dir = Path(str((meta_paths or {}).get("repo_dir") or (session_dir / "repo"))).resolve()
    work_dir = Path(str((meta_paths or {}).get("work_dir") or (session_dir / "work"))).resolve()
    work_tmp_dir = Path(
        str((meta_paths or {}).get("work_tmp_dir") or (work_dir / "tmp"))
    ).resolve()
    chunkhound_work_dir = Path(
        str((meta_paths or {}).get("chunkhound_cwd") or (work_dir / "chunkhound"))
    ).resolve()
    chunkhound_db_path = Path(
        str((meta_paths or {}).get("chunkhound_db") or (chunkhound_work_dir / ".chunkhound.db"))
    ).resolve()
    chunkhound_cfg_path = Path(
        str((meta_paths or {}).get("chunkhound_config") or (chunkhound_work_dir / "chunkhound.json"))
    ).resolve()
    review_md_path = Path(str((meta_paths or {}).get("review_md") or (session_dir / "review.md"))).resolve()

    if not repo_dir.is_dir():
        raise ReviewflowError(f"Session repo_dir missing: {repo_dir}")

    pr_url = str(meta.get("pr_url") or "").strip()
    if not pr_url:
        raise ReviewflowError("Session meta missing pr_url.")
    pr = parse_pr_url(pr_url)
    require_gh_auth(pr.host)
    ensure_review_config(paths)

    work_tmp_dir.mkdir(parents=True, exist_ok=True)
    chunkhound_work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = work_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if (not chunkhound_db_path.exists()) and (repo_dir / ".chunkhound.db").exists():
        # Legacy sessions stored the DB under the sandbox repo.
        chunkhound_db_path = (repo_dir / ".chunkhound.db").resolve()

    if not chunkhound_db_path.exists():
        base_cache = meta.get("base_cache") if isinstance(meta.get("base_cache"), dict) else {}
        base_db_raw = str((base_cache or {}).get("db_path") or "").strip()
        base_db_path = Path(base_db_raw).resolve() if base_db_raw else None
        if base_db_path and base_db_path.exists():
            # Bring the base DB into the session work dir for faster top-ups.
            if chunkhound_db_path.exists():
                if chunkhound_db_path.is_dir():
                    shutil.rmtree(chunkhound_db_path, ignore_errors=True)
                else:
                    chunkhound_db_path.unlink(missing_ok=True)
            chunkhound_db_path.parent.mkdir(parents=True, exist_ok=True)
            copy_duckdb_files(base_db_path, chunkhound_db_path)

    # Always refresh the session-local ChunkHound config so it tracks updates
    # in /workspaces/.chunkhound.review.json on every follow-up run.
    materialize_chunkhound_env_config(
        base_config_path=paths.review_chunkhound_config,
        output_config_path=chunkhound_cfg_path,
        database_provider="duckdb",
        database_path=chunkhound_db_path,
    )
    meta_paths = dict(meta_paths or {})
    meta_paths["work_dir"] = str(work_dir)
    meta_paths["work_tmp_dir"] = str(work_tmp_dir)
    meta_paths["chunkhound_cwd"] = str(chunkhound_work_dir)
    meta_paths["chunkhound_db"] = str(chunkhound_db_path)
    meta_paths["chunkhound_config"] = str(chunkhound_cfg_path)
    meta["paths"] = meta_paths
    write_json(meta_path, meta)

    out = ReviewflowOutput(
        ui_enabled=ui_enabled,
        no_stream=no_stream,
        stderr=sys.stderr,
        meta_path=meta_path,
        logs_dir=logs_dir,
        verbosity=verbosity,
    )
    _ACTIVE_OUTPUT = out
    out.start()

    success_markdown_path: Path | None = None

    try:
        progress = SessionProgress(meta_path, quiet=True)
        progress.meta = meta

        base_ref_for_review = str(meta.get("base_ref_for_review") or "").strip()
        if not base_ref_for_review:
            raise ReviewflowError("Session meta missing base_ref_for_review.")
        base_ref = str(meta.get("base_ref") or "").strip()
        if not base_ref:
            raise ReviewflowError("Session meta missing base_ref.")

        crawl_cfg, crawl_meta = load_crawl_config()
        meta["crawl"] = crawl_meta

        agent_desc = ""
        agent_desc_path = Path(str(((meta.get("paths") or {}).get("agent_desc")) or "")).resolve()
        if agent_desc_path.is_file():
            agent_desc = agent_desc_path.read_text(encoding="utf-8")

        # Prep env for ChunkHound + Codex.
        env = merged_env(chunkhound_env(paths))
        gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
        if gh_cfg:
            env["GH_CONFIG_DIR"] = str(gh_cfg)
        jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
        if jira_cfg:
            env["JIRA_CONFIG_FILE"] = str(jira_cfg)
        netrc = real_user_home_dir() / ".netrc"
        if netrc.is_file():
            env["NETRC"] = str(netrc)
        env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
        env.update(crawl_env(crawl_cfg))
        rf_fetch = write_rf_fetch_url(repo_dir=repo_dir, cfg=crawl_cfg)
        rf_jira = write_rf_jira(repo_dir=repo_dir)

        base_codex_config_path = Path("/workspaces/academy+/.codex/config.toml")
        codex_flags, codex_meta = resolve_codex_flags(
            base_config_path=base_codex_config_path,
            reviewflow_config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH,
            cli_model=getattr(args, "codex_model", None),
            cli_effort=getattr(args, "codex_effort", None),
            cli_plan_effort=getattr(args, "codex_plan_effort", None),
        )

        meta.setdefault("followups", [])
        followup_started_at = _utc_now_iso()
        followup_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        followups_dir = session_dir / "followups"
        followups_dir.mkdir(parents=True, exist_ok=True)
        followup_md_path = followups_dir / f"followup-{followup_ts}.md"

        head_before = run_cmd(["git", "-C", str(repo_dir), "rev-parse", "HEAD"]).stdout.strip()
        update_enabled = not bool(getattr(args, "no_update", False))
        head_after = head_before

        if update_enabled:
            with phase("followup_update", progress=None, quiet=quiet):
                fetch_cmd = ["git", "-C", str(repo_dir), "fetch", "--prune", "origin"]
                run_cmd(fetch_cmd, stream=stream, stream_label="git")
                checkout_pr_cmd = [
                    "gh",
                    "pr",
                    "checkout",
                    str(pr.number),
                    "-R",
                    pr.gh_repo,
                    "--force",
                ]
                run_cmd(checkout_pr_cmd, cwd=repo_dir, stream=stream, stream_label="gh")

                fetch_base_cmd = ["git", "-C", str(repo_dir), "fetch", "origin", base_ref]
                run_cmd(fetch_base_cmd, stream=stream, stream_label="git")
                branch_cmd = [
                    "git",
                    "-C",
                    str(repo_dir),
                    "branch",
                    "-f",
                    base_ref_for_review,
                    f"origin/{base_ref}",
                ]
                run_cmd(branch_cmd, stream=stream, stream_label="git")

                head_after = run_cmd(
                    ["git", "-C", str(repo_dir), "rev-parse", "HEAD"]
                ).stdout.strip()

        with phase("followup_index", progress=None, quiet=quiet):
            index_cmd = [
                "chunkhound",
                "index",
                str(repo_dir),
                "--config",
                str(chunkhound_cfg_path),
            ]
            out_obj = _ACTIVE_OUTPUT
            if out_obj is not None:
                out_obj.run_logged_cmd(
                    index_cmd,
                    kind="chunkhound",
                    cwd=chunkhound_work_dir,
                    env=env,
                    check=True,
                    stream_requested=stream,
                )
            else:
                run_cmd(
                    index_cmd,
                    cwd=chunkhound_work_dir,
                    env=env,
                    check=True,
                    stream=stream,
                    stream_label="chunkhound",
                )

        # Pick follow-up prompt template based on the original profile (best-effort).
        prompt_meta = meta.get("prompt") if isinstance(meta.get("prompt"), dict) else {}
        profile_resolved = str((prompt_meta or {}).get("profile_resolved") or "").strip().lower()
        if profile_resolved not in {"big", "normal"}:
            profile_resolved = "normal"
        followup_template_path = followup_prompt_template_path_for_profile(profile_resolved)
        if not followup_template_path.is_file():
            raise ReviewflowError(f"Missing follow-up prompt template: {followup_template_path}")

        followup_template = followup_template_path.read_text(encoding="utf-8")
        followup_prompt = render_prompt(
            followup_template,
            base_ref_for_review=base_ref_for_review,
            pr_url=pr_url,
            pr_number=int(meta.get("number") or pr.number),
            gh_host=str(pr.host),
            gh_owner=str(pr.owner),
            gh_repo_name=str(pr.repo),
            gh_repo=str(pr.gh_repo),
            agent_desc=agent_desc,
            head_ref="HEAD",
            extra_vars={
                "PREVIOUS_REVIEW_MD": str(review_md_path),
                "HEAD_SHA_BEFORE": head_before,
                "HEAD_SHA_AFTER": head_after,
                "FOLLOWUP_OUTPUT_MD": str(followup_md_path),
            },
        )

        codex_overrides = codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=True,
            sandbox_repo_dir=repo_dir,
            chunkhound_cwd=chunkhound_work_dir,
            chunkhound_config_path=chunkhound_cfg_path,
            paths=paths,
        )

        with phase("followup_review", progress=None, quiet=quiet):
            followup_result = run_codex_exec(
                repo_dir=repo_dir,
                codex_flags=codex_flags,
                codex_config_overrides=codex_overrides,
                output_path=followup_md_path,
                prompt=followup_prompt,
                env=env,
                stream=stream,
                progress=progress,
                add_dirs=[session_dir],
            )
        success_resume_command = record_codex_resume(meta.setdefault("codex", {}), followup_result.resume)

        decision = extract_decision_from_markdown(followup_md_path.read_text(encoding="utf-8"))
        followup_entry: dict[str, Any] = {
            "started_at": followup_started_at,
            "completed_at": _utc_now_iso(),
            "no_update": (not update_enabled),
            "head_sha_before": head_before,
            "head_sha_after": head_after,
            "template_path": str(followup_template_path),
            "output_path": str(followup_md_path),
            "decision": decision,
            "codex": {"config": codex_meta, "flags": codex_flags},
            "helpers": {"rf_fetch_url": str(rf_fetch), "rf_jira": str(rf_jira)},
        }
        followup_codex_meta = followup_entry.get("codex")
        if isinstance(followup_codex_meta, dict):
            record_codex_resume(followup_codex_meta, followup_result.resume)
        meta.setdefault("followups", []).append(followup_entry)
        write_json(meta_path, meta)

        success_markdown_path = followup_md_path
        print(str(followup_md_path))
        return 0
    finally:
        if _ACTIVE_OUTPUT is out:
            _ACTIVE_OUTPUT = None
        out.stop()
        maybe_print_markdown_after_tui(
            ui_enabled=ui_enabled, stderr=out.stderr, markdown_path=success_markdown_path
        )
        maybe_print_codex_resume_command(stderr=out.stderr, command=success_resume_command)


@dataclass(frozen=True)
class ZipSourceArtifact:
    session_id: str
    session_dir: Path
    kind: str  # "review" | "followup"
    artifact_path: Path
    completed_at: str | None
    decision: str | None
    target_head_sha: str

    def sort_dt(self) -> datetime:
        return _parse_iso_dt(self.completed_at) or datetime(1970, 1, 1, tzinfo=timezone.utc)


def _short_sha(value: str | None, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return "?"
    return text[: max(1, int(length))]


def _zip_input_display_line(entry: dict[str, Any], *, markdown: bool) -> str:
    session_id = str(entry.get("session_id") or "?").strip() or "?"
    kind = str(entry.get("kind") or "?").strip() or "?"
    decision = str(entry.get("decision") or "?").strip() or "?"
    completed_at = str(entry.get("completed_at") or "?").strip() or "?"
    target_head_sha = _short_sha(str(entry.get("target_head_sha") or "").strip(), length=12)
    path = str(entry.get("path") or "?").strip() or "?"
    if markdown:
        return (
            f"- `{session_id}`"
            f" • `{kind}`"
            f" • {decision}"
            f" • {completed_at}"
            f" • head `{target_head_sha}`"
            f" • `{path}`"
        )
    return (
        f"- {session_id}"
        f" [{kind}]"
        f" {decision}"
        f" {completed_at}"
        f" head {target_head_sha}"
        f" {path}"
    )


def build_zip_input_display_lines(
    *, inputs_meta: list[dict[str, Any]], markdown: bool = False
) -> list[str]:
    return [
        _zip_input_display_line(entry, markdown=markdown)
        for entry in inputs_meta
        if isinstance(entry, dict)
    ]


def append_zip_inputs_provenance(*, markdown_path: Path, inputs_meta: list[dict[str, Any]]) -> None:
    if not markdown_path.is_file():
        raise ReviewflowError(f"zip: output markdown missing: {markdown_path}")
    body = markdown_path.read_text(encoding="utf-8")
    if not body.endswith("\n"):
        body += "\n"
    lines = build_zip_input_display_lines(inputs_meta=inputs_meta, markdown=True)
    if not lines:
        return
    section = "\n".join(["---", "## Inputs Processed", *lines]) + "\n"
    markdown_path.write_text(body + "\n" + section, encoding="utf-8")


def _resolve_session_relative_path(*, session_dir: Path, raw: str | None, default: Path) -> Path:
    if raw:
        p = Path(str(raw)).expanduser()
        if not p.is_absolute():
            return (session_dir / p).resolve()
        return p.resolve()
    return default.resolve()


def select_zip_sources_for_pr_head(
    *, sandbox_root: Path, pr: PullRequestRef, head_sha: str
) -> list[ZipSourceArtifact]:
    """Select one newest artifact per completed session, filtered to the given PR + target head SHA."""
    head = str(head_sha or "").strip().lower()
    if not head:
        raise ReviewflowError("zip: missing head SHA")

    root = sandbox_root
    if not root.is_dir():
        return []

    selected_by_session: dict[str, ZipSourceArtifact] = {}
    kind_rank = {"review": 0, "followup": 1}

    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta:
            continue
        if str(meta.get("status") or "") != "done":
            continue
        if str(meta.get("host") or "") != pr.host:
            continue
        if str(meta.get("owner") or "") != pr.owner:
            continue
        if str(meta.get("repo") or "") != pr.repo:
            continue
        try:
            if int(meta.get("number") or 0) != int(pr.number):
                continue
        except Exception:
            continue

        session_id = str(meta.get("session_id") or entry.name)
        session_dir = entry

        # Candidate: main review.md (if it targets this head SHA).
        meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
        review_md_raw = str((meta_paths or {}).get("review_md") or "").strip()
        review_md_default = session_dir / "review.md"
        review_md_path = _resolve_session_relative_path(
            session_dir=session_dir, raw=review_md_raw, default=review_md_default
        )
        review_head_sha = str(meta.get("head_sha") or "").strip().lower()
        review_completed_at = str(meta.get("completed_at") or meta.get("created_at") or "").strip() or None
        review_decision = str(meta.get("decision") or "").strip() or None
        if review_md_path.is_file() and review_head_sha and (review_head_sha == head):
            if review_decision is None:
                try:
                    review_decision = extract_decision_from_markdown(
                        review_md_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    review_decision = None
            cand = ZipSourceArtifact(
                session_id=session_id,
                session_dir=session_dir,
                kind="review",
                artifact_path=review_md_path,
                completed_at=review_completed_at,
                decision=review_decision,
                target_head_sha=review_head_sha,
            )
            selected_by_session[session_id] = cand

        # Candidates: followups that target this head SHA.
        followups = meta.get("followups") if isinstance(meta.get("followups"), list) else []
        for fu in followups:
            if not isinstance(fu, dict):
                continue
            fu_head_sha = str(fu.get("head_sha_after") or "").strip().lower()
            if not fu_head_sha or fu_head_sha != head:
                continue
            fu_completed_at = str(fu.get("completed_at") or "").strip() or None
            fu_output_raw = str(fu.get("output_path") or "").strip()
            if not fu_output_raw:
                continue
            fu_path = _resolve_session_relative_path(
                session_dir=session_dir, raw=fu_output_raw, default=session_dir / fu_output_raw
            )
            if not fu_path.is_file():
                continue
            fu_decision = str(fu.get("decision") or "").strip() or None
            if fu_decision is None:
                try:
                    fu_decision = extract_decision_from_markdown(fu_path.read_text(encoding="utf-8"))
                except Exception:
                    fu_decision = None
            cand = ZipSourceArtifact(
                session_id=session_id,
                session_dir=session_dir,
                kind="followup",
                artifact_path=fu_path,
                completed_at=fu_completed_at,
                decision=fu_decision,
                target_head_sha=fu_head_sha,
            )
            prev = selected_by_session.get(session_id)
            if prev is None:
                selected_by_session[session_id] = cand
                continue
            if cand.sort_dt() > prev.sort_dt():
                selected_by_session[session_id] = cand
                continue
            if cand.sort_dt() == prev.sort_dt() and kind_rank.get(cand.kind, 0) > kind_rank.get(prev.kind, 0):
                selected_by_session[session_id] = cand

    sources = list(selected_by_session.values())
    sources.sort(key=lambda s: s.sort_dt(), reverse=True)
    return sources


def zip_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    global _ACTIVE_OUTPUT
    verbosity = resolve_verbosity(args)
    quiet = verbosity is Verbosity.quiet
    no_stream = bool(getattr(args, "no_stream", False))
    ui_enabled = resolve_ui_enabled(args, verbosity=verbosity)
    stream = (not quiet) and (not no_stream)

    pr_url = str(getattr(args, "pr_url", "") or "").strip()
    if not pr_url:
        raise ReviewflowError("zip requires a PR URL.")
    pr = parse_pr_url(pr_url)
    require_gh_auth(pr.host)

    with phase("zip_resolve_pr_head", progress=None, quiet=quiet):
        pr_api = run_cmd(
            [
                "gh",
                "api",
                "--hostname",
                pr.host,
                f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}",
            ]
        )
        pr_meta = json.loads(pr_api.stdout)
        head = pr_meta.get("head")
        head_sha = str((head.get("sha") if isinstance(head, dict) else "") or "").strip()
        title = str(pr_meta.get("title") or "").strip()

    if not head_sha:
        raise ReviewflowError("zip: failed to resolve PR head SHA via `gh api`.")

    sources = select_zip_sources_for_pr_head(
        sandbox_root=paths.sandbox_root, pr=pr, head_sha=head_sha
    )
    if not sources:
        raise ReviewflowError(
            f"zip: no completed review artifacts found for PR HEAD {head_sha[:12]}.\n"
            "Run a fresh review or follow-up first:\n"
            f"  python3 /workspaces/reviewflow/reviewflow.py pr {pr_url}\n"
            "  # or\n"
            "  python3 /workspaces/reviewflow/reviewflow.py followup <session_id>"
        )

    host_session_dir = sources[0].session_dir
    host_meta_path = host_session_dir / "meta.json"
    host_meta = _load_session_meta(host_meta_path)
    if not host_meta:
        raise ReviewflowError(f"zip: failed to load host meta.json: {host_meta_path}")
    host_paths = host_meta.get("paths") if isinstance(host_meta.get("paths"), dict) else {}
    host_repo_dir = Path(str((host_paths or {}).get("repo_dir") or (host_session_dir / "repo"))).resolve()
    host_work_dir = Path(str((host_paths or {}).get("work_dir") or (host_session_dir / "work"))).resolve()
    if not host_repo_dir.is_dir():
        raise ReviewflowError(f"zip: host repo_dir missing: {host_repo_dir}")
    host_work_dir.mkdir(parents=True, exist_ok=True)

    base_ref_for_review = str(host_meta.get("base_ref_for_review") or "").strip()
    base_ref = str(host_meta.get("base_ref") or "").strip()
    if not base_ref_for_review:
        base_ref_for_review = "HEAD"
    if not base_ref:
        base_ref = "HEAD"

    zip_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    zip_run_id = (
        f"zip-{pr.owner}-{pr.repo}-pr{pr.number}-"
        f"{zip_ts}-"
        f"{secrets.token_hex(2)}"
    )
    zips_dir = host_session_dir / "zips"
    zips_dir.mkdir(parents=True, exist_ok=True)
    output_md_path = zips_dir / f"zip-{zip_ts}.md"
    zip_meta_path = zips_dir / f"zip-{zip_ts}.meta.json"
    zip_logs_dir = zips_dir / "logs" / f"zip-{zip_ts}"
    zip_logs_dir.mkdir(parents=True, exist_ok=True)

    zip_started_at = _utc_now_iso()
    inputs_meta: list[dict[str, Any]] = []
    inputs_lines: list[str] = []
    for src in sources:
        inputs_meta.append(
            {
                "session_id": src.session_id,
                "kind": src.kind,
                "path": str(src.artifact_path),
                "completed_at": src.completed_at,
                "decision": src.decision,
                "target_head_sha": src.target_head_sha,
            }
        )
        when = src.completed_at or ""
        decision = src.decision or "?"
        inputs_lines.append(
            f"- {src.session_id} ({src.kind}, {when}, {decision})  `{src.artifact_path}`"
        )
    zip_inputs_text = "\n".join(inputs_lines)
    zip_display_inputs = build_zip_input_display_lines(inputs_meta=inputs_meta)

    zip_progress = SessionProgress(zip_meta_path, quiet=quiet)
    zip_progress.init(
        {
            "session_id": zip_run_id,
            "created_at": zip_started_at,
            "status": "running",
            "phase": "init",
            "kind": "zip",
            "pr_url": pr_url,
            "host": pr.host,
            "owner": pr.owner,
            "repo": pr.repo,
            "number": pr.number,
            "title": title,
            "head_sha": head_sha,
            "host_session_id": str(host_meta.get("session_id") or host_session_dir.name),
            "paths": {
                "host_session_dir": str(host_session_dir),
                "repo_dir": str(host_repo_dir),
                "work_dir": str(host_work_dir),
                "logs_dir": str(zip_logs_dir),
                "output_md": str(output_md_path),
            },
            "zip": {
                "inputs": inputs_meta,
                "display_inputs": zip_display_inputs,
                "selected_input_count": len(inputs_meta),
            },
            "options": {
                "quiet": quiet,
                "no_stream": no_stream,
                "ui": str(getattr(args, "ui", "auto") or "auto"),
                "ui_enabled": bool(ui_enabled),
                "verbosity": verbosity.value,
            },
        }
    )

    out = ReviewflowOutput(
        ui_enabled=ui_enabled,
        no_stream=no_stream,
        stderr=sys.stderr,
        meta_path=zip_progress.meta_path,
        logs_dir=zip_logs_dir,
        verbosity=verbosity,
    )
    _ACTIVE_OUTPUT = out
    zip_progress.meta["logs"] = {
        "reviewflow": str(zip_logs_dir / "reviewflow.log"),
        "chunkhound": str(zip_logs_dir / "chunkhound.log"),
        "codex": str(zip_logs_dir / "codex.log"),
    }
    zip_progress.flush()
    out.start()
    log(
        f"zip selected {len(inputs_meta)} input artifact(s) for HEAD {_short_sha(head_sha, length=12)}",
        quiet=quiet,
    )
    for line in zip_display_inputs:
        log(f"zip input {line[2:] if line.startswith('- ') else line}", quiet=quiet)

    success_markdown_path: Path | None = None
    success_resume_command: str | None = None
    try:
        env = merged_env({})
        env["REVIEWFLOW_WORK_DIR"] = str(host_work_dir)

        base_codex_config_path = Path("/workspaces/academy+/.codex/config.toml")
        codex_flags, codex_meta = resolve_codex_flags(
            base_config_path=base_codex_config_path,
            reviewflow_config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH,
            cli_model=getattr(args, "codex_model", None),
            cli_effort=getattr(args, "codex_effort", None),
            cli_plan_effort=getattr(args, "codex_plan_effort", None),
        )
        codex_overrides = codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=False,
            sandbox_repo_dir=host_repo_dir,
            paths=paths,
        )

        template_path = Path("/workspaces/reviewflow/prompts/mrereview_zip.md")
        if not template_path.is_file():
            raise ReviewflowError(f"zip: missing arbiter prompt template: {template_path}")
        template_text = template_path.read_text(encoding="utf-8")
        rendered = render_prompt(
            template_text,
            base_ref_for_review=base_ref_for_review,
            pr_url=pr_url,
            pr_number=int(pr.number),
            gh_host=str(pr.host),
            gh_owner=str(pr.owner),
            gh_repo_name=str(pr.repo),
            gh_repo=str(pr.gh_repo),
            agent_desc="",
            head_ref="HEAD",
            extra_vars={
                "HEAD_SHA": head_sha,
                "ZIP_INPUTS": zip_inputs_text,
            },
        )

        zip_progress.meta["prompt"] = {
            "template_path": str(template_path),
            "prompt_chars": len(rendered),
            "prompt_sha256": sha256_text(rendered),
        }
        zip_progress.meta["codex"] = {
            "config": codex_meta,
            "dangerously_bypass_approvals_and_sandbox": True,
            "config_overrides": codex_overrides,
            "flags": codex_flags,
            "env": {
                "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
            },
        }
        zip_progress.flush()

        zip_progress.set_phase("codex_zip")
        with phase("codex_zip", progress=zip_progress, quiet=quiet):
            zip_result = run_codex_exec(
                repo_dir=host_repo_dir,
                codex_flags=codex_flags,
                codex_config_overrides=codex_overrides,
                output_path=output_md_path,
                prompt=rendered,
                env=env,
                stream=stream,
                progress=zip_progress,
                add_dirs=[paths.sandbox_root, host_session_dir],
            )
        success_resume_command = record_codex_resume(
            zip_progress.meta.setdefault("codex", {}), zip_result.resume
        )
        zip_progress.flush()

        normalize_markdown_artifact(markdown_path=output_md_path, session_dir=host_session_dir)
        append_zip_inputs_provenance(markdown_path=output_md_path, inputs_meta=inputs_meta)
        decision = None
        try:
            decision = extract_decision_from_markdown(output_md_path.read_text(encoding="utf-8"))
        except Exception:
            decision = None
        if decision:
            zip_progress.meta["decision"] = decision
            zip_progress.flush()

        zip_progress.done()
        zip_completed_at = zip_progress.meta.get("completed_at")

        # Record provenance in the host session meta.json.
        host_meta2 = _load_session_meta(host_meta_path) or host_meta
        zip_entry: dict[str, Any] = {
            "started_at": zip_started_at,
            "completed_at": zip_completed_at,
            "head_sha": head_sha,
            "output_path": str(output_md_path),
            "decision": decision,
            "inputs": inputs_meta,
            "prompt": zip_progress.meta.get("prompt"),
            "codex": {"config": codex_meta, "flags": codex_flags},
        }
        zip_codex_meta = zip_entry.get("codex")
        if isinstance(zip_codex_meta, dict):
            record_codex_resume(zip_codex_meta, zip_result.resume)
        host_meta2.setdefault("zips", []).append(zip_entry)
        write_json(host_meta_path, host_meta2)

        success_markdown_path = output_md_path
        print(str(output_md_path))
        return 0
    except ReviewflowSubprocessError as e:
        zip_progress.error(
            {
                "type": "subprocess",
                "message": str(e),
                "cmd": safe_cmd_for_meta(e.cmd),
                "cwd": str(e.cwd) if e.cwd else None,
                "exit_code": e.exit_code,
                "stdout_tail": e.stdout,
                "stderr_tail": e.stderr,
            }
        )
        raise
    except Exception as e:
        zip_progress.error({"type": "exception", "message": str(e)})
        raise
    finally:
        if _ACTIVE_OUTPUT is out:
            _ACTIVE_OUTPUT = None
        out.stop()
        maybe_print_markdown_after_tui(
            ui_enabled=ui_enabled, stderr=out.stderr, markdown_path=success_markdown_path
        )
        maybe_print_codex_resume_command(stderr=out.stderr, command=success_resume_command)


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


@dataclass(frozen=True)
class HistoricalReviewSession:
    session_id: str
    session_dir: Path
    review_md_path: Path
    created_at: str | None
    completed_at: str | None
    decision: str | None
    review_head_sha: str | None = None

    def sort_dt(self) -> datetime:
        return (
            _parse_iso_dt(self.completed_at)
            or _parse_iso_dt(self.created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )


@dataclass(frozen=True)
class InteractiveReviewSession:
    session_id: str
    session_dir: Path
    host: str
    owner: str
    repo: str
    number: int
    repo_slug: str
    review_md_path: Path
    latest_artifact_path: Path
    created_at: str | None
    completed_at: str | None
    decision: str | None
    resume_command: str

    def sort_dt(self) -> datetime:
        return (
            _parse_iso_dt(self.completed_at)
            or _parse_iso_dt(self.created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )

def _load_session_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _resolve_session_review_md_path(*, session_dir: Path, meta: dict[str, Any]) -> Path | None:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw_review_md = str((meta_paths or {}).get("review_md") or (session_dir / "review.md")).strip()
    review_md_path = Path(raw_review_md) if raw_review_md else (session_dir / "review.md")
    if not review_md_path.is_absolute():
        review_md_path = (session_dir / review_md_path).resolve()
    else:
        review_md_path = review_md_path.resolve()
    if not review_md_path.is_file():
        return None
    return review_md_path


def _resolve_session_decision(
    *, meta_path: Path, meta: dict[str, Any], review_md_path: Path
) -> str | None:
    decision = str(meta.get("decision") or "").strip() or None
    if decision is not None:
        normalized = extract_decision_from_markdown(f"**Decision**: {decision}") or decision
        if normalized != decision:
            decision = normalized
            meta["decision"] = normalized
            try:
                write_json(meta_path, meta)
            except Exception:
                pass
        return decision

    extracted = extract_decision_from_markdown(review_md_path.read_text(encoding="utf-8"))
    if extracted:
        # Opportunistically persist for faster future scans.
        meta["decision"] = extracted
        try:
            write_json(meta_path, meta)
        except Exception:
            pass
    return extracted


def _resolve_session_review_head_sha(*, meta: dict[str, Any]) -> str | None:
    for key in ("review_head_sha", "head_sha"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return None


def _resolve_latest_session_artifact_path(*, session_dir: Path, meta: dict[str, Any], review_md_path: Path) -> Path:
    latest_path = review_md_path
    latest_dt = _parse_iso_dt(str(meta.get("completed_at") or "").strip())
    followups = meta.get("followups") if isinstance(meta.get("followups"), list) else []
    for followup in followups:
        if not isinstance(followup, dict):
            continue
        raw_output = str(followup.get("output_path") or "").strip()
        if not raw_output:
            continue
        candidate = _resolve_session_relative_path(
            session_dir=session_dir,
            raw=raw_output,
            default=session_dir / raw_output,
        )
        if not candidate.is_file():
            continue
        candidate_dt = _parse_iso_dt(str(followup.get("completed_at") or "").strip())
        if latest_dt is None or (candidate_dt is not None and candidate_dt >= latest_dt):
            latest_path = candidate
            latest_dt = candidate_dt
    return latest_path


def scan_completed_sessions_for_pr(*, sandbox_root: Path, pr: PullRequestRef) -> list[HistoricalReviewSession]:
    root = sandbox_root
    if not root.is_dir():
        return []

    sessions: list[HistoricalReviewSession] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta:
            continue
        if str(meta.get("status") or "") != "done":
            continue
        if str(meta.get("host") or "") != pr.host:
            continue
        if str(meta.get("owner") or "") != pr.owner:
            continue
        if str(meta.get("repo") or "") != pr.repo:
            continue
        try:
            if int(meta.get("number") or 0) != int(pr.number):
                continue
        except Exception:
            continue

        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        if review_md_path is None:
            continue

        decision = _resolve_session_decision(meta_path=meta_path, meta=meta, review_md_path=review_md_path)
        review_head_sha = _resolve_session_review_head_sha(meta=meta)

        sessions.append(
            HistoricalReviewSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                review_md_path=review_md_path,
                created_at=str(meta.get("created_at") or "").strip() or None,
                completed_at=str(meta.get("completed_at") or "").strip() or None,
                decision=decision,
                review_head_sha=review_head_sha,
            )
        )

    sessions.sort(key=lambda s: s.sort_dt(), reverse=True)
    return sessions


def scan_interactive_review_sessions(*, sandbox_root: Path) -> list[InteractiveReviewSession]:
    root = sandbox_root
    if not root.is_dir():
        return []

    sessions: list[InteractiveReviewSession] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta:
            continue
        if str(meta.get("status") or "").strip() != "done":
            continue

        existing_codex = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
        existing_resume = existing_codex.get("resume") if isinstance(existing_codex.get("resume"), dict) else {}
        resume_command = str((existing_resume or {}).get("command") or "").strip()
        if not resume_command:
            continue

        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        if review_md_path is None:
            continue

        host = str(meta.get("host") or "").strip() or "?"
        owner = str(meta.get("owner") or "").strip() or "?"
        repo = str(meta.get("repo") or "").strip() or "?"
        raw_number = meta.get("number")
        try:
            number = int(raw_number)
        except Exception:
            number = 0
        decision = _resolve_session_decision(meta_path=meta_path, meta=meta, review_md_path=review_md_path)
        latest_artifact_path = _resolve_latest_session_artifact_path(
            session_dir=entry,
            meta=meta,
            review_md_path=review_md_path,
        )

        sessions.append(
            InteractiveReviewSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                host=host,
                owner=owner,
                repo=repo,
                number=number,
                repo_slug=f"{owner}/{repo}#{number}",
                review_md_path=review_md_path,
                latest_artifact_path=latest_artifact_path,
                created_at=str(meta.get("created_at") or "").strip() or None,
                completed_at=str(meta.get("completed_at") or "").strip() or None,
                decision=decision,
                resume_command=resume_command,
            )
        )

    sessions.sort(key=lambda s: s.sort_dt(), reverse=True)
    return sessions


def _print_historical_sessions(sessions: list[HistoricalReviewSession]) -> None:
    for idx, s in enumerate(sessions, start=1):
        when = s.completed_at or s.created_at or ""
        decision = s.decision or "?"
        print(f"{idx:02d}  {when}  {decision}  {s.session_id}")


def _historical_picker_color_enabled(stream: TextIO) -> bool:
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


def _short_review_head_sha(review_head_sha: str | None) -> str:
    text = str(review_head_sha or "").strip()
    if not text:
        return "unknown"
    return text[:12]


def _historical_review_picker_lines(
    sessions: list[HistoricalReviewSession], *, color: bool
) -> list[str]:
    lines = ["", "Completed prior reviews found for this PR (newest first):"]
    groups: list[tuple[str, list[HistoricalReviewSession]]] = []
    grouped: dict[str, list[HistoricalReviewSession]] = {}
    for session in sessions:
        key = str(session.review_head_sha or "").strip() or "unknown"
        bucket = grouped.get(key)
        if bucket is None:
            bucket = []
            grouped[key] = bucket
            groups.append((key, bucket))
        bucket.append(session)

    palette = ["\x1b[1;36m", "\x1b[1;33m", "\x1b[1;35m", "\x1b[1;34m", "\x1b[1;32m"]
    idx = 1
    for group_idx, (group_key, bucket) in enumerate(groups):
        count = len(bucket)
        label = _short_review_head_sha(None if group_key == "unknown" else group_key)
        review_label = "review" if count == 1 else "review(s)"
        header = f"  head {label} ({count} {review_label})"
        if color:
            header = f"{palette[group_idx % len(palette)]}{header}\x1b[0m"
        lines.append(header)
        for session in bucket:
            when = session.completed_at or session.created_at or ""
            decision = session.decision or "?"
            lines.append(f"  {idx}) {when}  {decision}  {session.session_id}")
            idx += 1
    lines.append("  n) create a NEW sandbox review")
    lines.append("")
    lines.append("Select a prior review to view (number), or 'n' for new:")
    return lines


def _choose_historical_session_tty(
    sessions: list[HistoricalReviewSession],
) -> HistoricalReviewSession | None:
    for line in _historical_review_picker_lines(
        sessions,
        color=_historical_picker_color_enabled(sys.stderr),
    ):
        _eprint(line)
    try:
        choice = sys.stdin.readline()
    except Exception:
        return None
    choice = (choice or "").strip().lower()
    if choice in {"", "n", "new", "0"}:
        return None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(sessions):
            return sessions[idx - 1]
    _eprint(f"Invalid selection: {choice!r} (continuing with new review)")
    return None


def _choose_interactive_review_session_tty(
    sessions: list[InteractiveReviewSession], *, stdin: TextIO, stderr: TextIO
) -> InteractiveReviewSession | None:
    try:
        stderr.write("\n")
        stderr.write("Past review sessions with saved Codex state (newest first):\n")
        for idx, s in enumerate(sessions, start=1):
            when = s.completed_at or s.created_at or ""
            decision = s.decision or "?"
            stderr.write(f"  {idx}) {when}  {decision}  {s.repo_slug}  {s.session_id}\n")
        stderr.write("  q) cancel\n\n")
        stderr.write("Select a review to continue (number), or 'q' to cancel:\n")
        stderr.flush()
    except Exception:
        return None

    try:
        choice = stdin.readline()
    except Exception:
        return None
    choice = (choice or "").strip().lower()
    if choice in {"", "q", "quit", "n", "no", "0"}:
        return None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(sessions):
            return sessions[idx - 1]
    try:
        stderr.write(f"Invalid selection: {choice!r}\n")
        stderr.flush()
    except Exception:
        pass
    return None


def run_interactive_resume_command(command: str, *, env: dict[str, str] | None = None) -> int:
    return int(subprocess.run(["bash", "-lc", command], check=False, env=env).returncode)


def _interactive_session_resume_is_poisoned(
    *,
    session: InteractiveReviewSession,
    codex_root: Path | None = None,
) -> bool:
    meta_path = session.session_dir / "meta.json"
    meta = _load_session_meta(meta_path)
    if not meta:
        raise ReviewflowError(f"Failed to parse meta.json: {meta_path}")

    codex_meta = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
    resume_meta = codex_meta.get("resume") if isinstance(codex_meta.get("resume"), dict) else {}
    resume_session_id = str((resume_meta or {}).get("session_id") or "").strip()
    if not resume_session_id:
        return False

    codex_home = codex_root or (real_user_home_dir() / ".codex")
    session_dir_text = str(session.session_dir.resolve())
    if _codex_logs_contain_exact_user_message(
        codex_root=codex_home,
        text=session_dir_text,
        created_at=session.created_at,
        completed_at=session.completed_at,
    ):
        return True

    session_log = _find_codex_session_log_by_id(
        codex_root=codex_home,
        session_id=resume_session_id,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )
    if session_log is None:
        return False
    return _codex_session_contains_exact_user_message(
        session_log_path=session_log,
        text=session_dir_text,
    )

def build_interactive_resume_command(
    *, session: InteractiveReviewSession, paths: ReviewflowPaths
) -> tuple[str, dict[str, str]]:
    meta_path = session.session_dir / "meta.json"
    meta = _load_session_meta(meta_path)
    if not meta:
        raise ReviewflowError(f"Failed to parse meta.json: {meta_path}")

    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    repo_dir = Path(str((meta_paths or {}).get("repo_dir") or (session.session_dir / "repo"))).resolve()
    work_dir = Path(str((meta_paths or {}).get("work_dir") or (session.session_dir / "work"))).resolve()
    chunkhound_work_dir = Path(
        str((meta_paths or {}).get("chunkhound_cwd") or (work_dir / "chunkhound"))
    ).resolve()
    chunkhound_db_path = Path(
        str((meta_paths or {}).get("chunkhound_db") or (chunkhound_work_dir / ".chunkhound.db"))
    ).resolve()
    chunkhound_cfg_path = Path(
        str((meta_paths or {}).get("chunkhound_config") or (chunkhound_work_dir / "chunkhound.json"))
    ).resolve()
    work_tmp_dir = Path(
        str((meta_paths or {}).get("work_tmp_dir") or (work_dir / "tmp"))
    ).resolve()

    if not repo_dir.is_dir():
        raise ReviewflowError(f"Session repo_dir missing: {repo_dir}")

    ensure_review_config(paths)
    work_dir.mkdir(parents=True, exist_ok=True)
    work_tmp_dir.mkdir(parents=True, exist_ok=True)
    chunkhound_work_dir.mkdir(parents=True, exist_ok=True)
    materialize_chunkhound_env_config(
        base_config_path=paths.review_chunkhound_config,
        output_config_path=chunkhound_cfg_path,
        database_provider="duckdb",
        database_path=chunkhound_db_path,
    )

    crawl_cfg, _ = load_crawl_config()
    env = merged_env(chunkhound_env(paths))
    gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
    if gh_cfg:
        env["GH_CONFIG_DIR"] = str(gh_cfg)
    jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
    if jira_cfg:
        env["JIRA_CONFIG_FILE"] = str(jira_cfg)
    netrc = real_user_home_dir() / ".netrc"
    if netrc.is_file():
        env["NETRC"] = str(netrc)
    env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
    env.update(crawl_env(crawl_cfg))
    _ = write_rf_fetch_url(repo_dir=repo_dir, cfg=crawl_cfg)
    _ = write_rf_jira(repo_dir=repo_dir)

    codex_meta = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
    resume_meta = codex_meta.get("resume") if isinstance(codex_meta.get("resume"), dict) else {}
    resume_session_id = str((resume_meta or {}).get("session_id") or "").strip()

    codex_flags_raw = codex_meta.get("flags")
    codex_flags = (
        [str(item) for item in codex_flags_raw if isinstance(item, str)]
        if isinstance(codex_flags_raw, list)
        else []
    )
    codex_overrides = codex_mcp_overrides_for_reviewflow(
        enable_sandbox_chunkhound=True,
        sandbox_repo_dir=repo_dir,
        chunkhound_db_path=chunkhound_db_path,
        chunkhound_cwd=chunkhound_work_dir,
        chunkhound_config_path=chunkhound_cfg_path,
        paths=paths,
    )

    codex_meta["config_overrides"] = codex_overrides
    codex_meta["env"] = {
        "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
        "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
        "NETRC": env.get("NETRC"),
        "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
        "REVIEWFLOW_CRAWL_ALLOW_HOSTS": env.get("REVIEWFLOW_CRAWL_ALLOW_HOSTS"),
        "REVIEWFLOW_CRAWL_TIMEOUT_SECONDS": env.get("REVIEWFLOW_CRAWL_TIMEOUT_SECONDS"),
        "REVIEWFLOW_CRAWL_MAX_BYTES": env.get("REVIEWFLOW_CRAWL_MAX_BYTES"),
    }
    meta_paths = dict(meta_paths or {})
    meta_paths["work_dir"] = str(work_dir)
    meta_paths["work_tmp_dir"] = str(work_tmp_dir)
    meta_paths["chunkhound_cwd"] = str(chunkhound_work_dir)
    meta_paths["chunkhound_db"] = str(chunkhound_db_path)
    meta_paths["chunkhound_config"] = str(chunkhound_cfg_path)
    meta["paths"] = meta_paths
    meta["codex"] = codex_meta
    if _interactive_session_resume_is_poisoned(session=session):
        raise ReviewflowError(
            f"Interactive cannot resume {session.session_id}: saved Codex session is corrupted by a stray "
            f"sandbox-path input. Start a fresh review session instead. Latest artifact: "
            f"{session.latest_artifact_path}"
        )

    if not resume_session_id:
        fallback_command = str((resume_meta or {}).get("command") or "").strip()
        if not fallback_command:
            raise ReviewflowError(f"Session {session.session_id} is missing codex.resume metadata.")
        write_json(meta_path, meta)
        return (fallback_command, env)

    command = build_codex_resume_command(
        repo_dir=repo_dir,
        session_id=resume_session_id,
        env=env,
        codex_flags=codex_flags,
        codex_config_overrides=codex_overrides,
        add_dirs=None,
    )
    record_codex_resume(
        codex_meta,
        CodexResumeInfo(session_id=resume_session_id, cwd=repo_dir, command=command),
    )
    meta["codex"] = codex_meta
    write_json(meta_path, meta)
    return (command, env)


def interactive_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    in_stream = stdin or sys.stdin
    err_stream = stderr or sys.stderr
    try:
        is_tty = bool(in_stream.isatty()) and bool(err_stream.isatty())
    except Exception:
        is_tty = False
    if not is_tty:
        raise ReviewflowError("interactive requires a TTY on stdin/stderr.")

    sessions = scan_interactive_review_sessions(sandbox_root=paths.sandbox_root)
    target = str(getattr(args, "target", "") or "").strip()
    if target:
        pr = parse_pr_url(target)
        sessions = [
            s
            for s in sessions
            if s.host == pr.host and s.owner == pr.owner and s.repo == pr.repo and int(s.number) == int(pr.number)
        ]
    if not sessions:
        if target:
            raise ReviewflowError(
                f"No completed review sessions with saved Codex state found for {target} under {paths.sandbox_root}."
            )
        raise ReviewflowError(
            f"No completed review sessions with saved Codex state found under {paths.sandbox_root}."
        )

    selected = _choose_interactive_review_session_tty(sessions, stdin=in_stream, stderr=err_stream)
    if selected is None:
        return 0

    resume_command, resume_env = build_interactive_resume_command(session=selected, paths=paths)
    try:
        err_stream.write(f"\nLatest review artifact: {selected.latest_artifact_path}\n")
        err_stream.write(f"\nContinuing {selected.repo_slug} ({selected.session_id})...\n")
        err_stream.flush()
    except Exception:
        pass
    return run_interactive_resume_command(resume_command, env=resume_env)


def list_sessions(*, paths: ReviewflowPaths) -> int:
    root = paths.sandbox_root
    if not root.is_dir():
        return 0
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        meta = entry / "meta.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                print(
                    f"{data.get('session_id')}  {data.get('owner')}/{data.get('repo')}#{data.get('number')}  {data.get('created_at')}"
                )
            except Exception:
                print(entry.name)
        else:
            print(entry.name)
    return 0


def clean_session(session_id: str, *, paths: ReviewflowPaths) -> int:
    root = paths.sandbox_root.resolve()
    target = (paths.sandbox_root / session_id).resolve()
    if root not in target.parents:
        raise ReviewflowError(f"Refusing to delete outside sandbox root: {target}")
    if not target.is_dir():
        _eprint(f"Session not found: {target}")
        return 2
    shutil.rmtree(target)
    return 0


def jira_smoke_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    quiet = bool(getattr(args, "quiet", False))
    no_stream = bool(getattr(args, "no_stream", False))
    stream = (not quiet) and (not no_stream)

    jira_key = str(args.jira_key).strip()
    if not jira_key:
        raise ReviewflowError("jira-smoke requires a Jira key (e.g. ABAU-985).")

    session_root = paths.sandbox_root
    session_root.mkdir(parents=True, exist_ok=True)
    session_id = (
        "jira-smoke-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-"
        f"{secrets.token_hex(2)}"
    )
    session_dir = session_root / session_id
    repo_dir = session_dir / "repo"
    session_dir.mkdir(parents=True, exist_ok=True)
    repo_dir.mkdir(parents=True, exist_ok=True)
    work_dir = session_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Prepare sandbox-local Jira config + helper.
    jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
    if not jira_cfg:
        raise ReviewflowError(
            "jira-smoke: Jira config not found. Ensure Jira CLI is initialized (e.g. `jira init`) "
            "and/or `JIRA_CONFIG_FILE` is set."
        )
    _ = write_rf_jira(repo_dir=repo_dir)

    env = merged_env({})
    env["JIRA_CONFIG_FILE"] = str(jira_cfg)
    env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
    netrc = real_user_home_dir() / ".netrc"
    if netrc.is_file():
        env["NETRC"] = str(netrc)

    base_codex_config_path = Path("/workspaces/academy+/.codex/config.toml")
    codex_flags, _ = resolve_codex_flags(
        base_config_path=base_codex_config_path,
        reviewflow_config_path=DEFAULT_REVIEWFLOW_CONFIG_PATH,
        cli_model=None,
        cli_effort=None,
        cli_plan_effort=None,
    )
    codex_overrides = codex_mcp_overrides_for_reviewflow(
        enable_sandbox_chunkhound=False,
        sandbox_repo_dir=repo_dir,
        paths=paths,
    )

    smoke_cmd = (
        "set -uo pipefail; "
        "if ./rf-jira me >/dev/null && "
        f"./rf-jira issue view {jira_key} --plain --comments 1 >/dev/null; "
        "then echo RF_JIRA_SMOKE_OK; "
        "else echo RF_JIRA_SMOKE_FAIL; exit 1; fi"
    )
    prompt = f"""You are running an automated smoke test for Jira access inside Codex.

Do exactly ONE command and then stop:

/bin/bash -lc {toml_string(smoke_cmd)}

Requirements:
- If the command succeeds, its output must include: RF_JIRA_SMOKE_OK
- If the command fails for any reason, output must include: RF_JIRA_SMOKE_FAIL
- Do not do anything else.
"""

    attempts = int(getattr(args, "attempts", 1) or 1)
    attempts = max(1, attempts)
    sleep_seconds = float(getattr(args, "sleep_seconds", 0.0) or 0.0)
    sleep_seconds = max(0.0, sleep_seconds)

    for attempt in range(1, attempts + 1):
        out_path = session_dir / f"jira_smoke_attempt_{attempt}.md"
        codex_cmd = build_codex_exec_cmd(
            repo_dir=repo_dir,
            codex_flags=codex_flags,
            codex_config_overrides=codex_overrides,
            review_md_path=out_path,
            prompt=prompt,
            add_dirs=[session_dir],
            skip_git_repo_check=True,
        )
        log(f"Jira smoke attempt {attempt}/{attempts}", quiet=quiet)
        res = run_cmd(
            codex_cmd,
            cwd=repo_dir,
            env=env,
            check=False,
            stream=stream,
            stream_label="codex",
        )
        combined = f"{res.stdout}\n{res.stderr}"
        ok = ("RF_JIRA_SMOKE_OK" in combined) and ("401 Unauthorized" not in combined)
        if ok:
            log(f"Jira smoke PASS (session {session_id})", quiet=quiet)
            return 0
        if attempt < attempts and sleep_seconds:
            time.sleep(sleep_seconds)

    raise ReviewflowError(f"jira-smoke FAILED; inspect: {session_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reviewflow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    prp = sub.add_parser("pr", help="Create PR sandbox, index, and run review")
    prp.add_argument("pr_url", help="GitHub PR URL")
    prp.add_argument(
        "--if-reviewed",
        dest="if_reviewed",
        choices=["prompt", "new", "list", "latest"],
        default="prompt",
        help="If a completed review exists for this PR, prompt (TTY), create new, list, or show latest (default: prompt)",
    )
    prp.add_argument("--prompt", help="Inline review prompt", default=None)
    prp.add_argument("--prompt-file", help="Path to prompt file", default=None)
    prp.add_argument(
        "--prompt-profile",
        choices=["auto", "normal", "big", "default"],
        default="auto",
        help="Prompt profile to use when no --prompt/--prompt-file is provided (default: auto)",
    )
    prp.add_argument(
        "--big-if-files",
        type=int,
        default=30,
        help="Auto-select big prompt if changed files >= N (default: 30)",
    )
    prp.add_argument(
        "--big-if-lines",
        type=int,
        default=1500,
        help="Auto-select big prompt if additions+deletions >= N (default: 1500)",
    )
    prp.add_argument("--agent-desc", help="Extra contributor context ($AGENT_DESC)", default=None)
    prp.add_argument(
        "--agent-desc-file",
        help="Path to file containing extra contributor context ($AGENT_DESC)",
        default=None,
    )
    prp.add_argument("--refresh-base", action="store_true", help="Force base cache refresh")
    prp.add_argument("--base-ttl-hours", type=int, default=24, help="Base cache TTL in hours")
    prp.add_argument(
        "--codex-model",
        dest="codex_model",
        default=None,
        help="Override Codex model for the review agent (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    prp.add_argument(
        "--codex-effort",
        dest="codex_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex model_reasoning_effort (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    prp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex plan_mode_reasoning_effort (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    mpg = prp.add_mutually_exclusive_group()
    mpg.add_argument(
        "--multipass",
        dest="multipass",
        action="store_true",
        default=None,
        help="Enable multipass review for the built-in big prompt profile (plan -> steps -> synth)",
    )
    mpg.add_argument(
        "--no-multipass",
        dest="multipass",
        action="store_false",
        default=None,
        help="Disable multipass review execution (forces single-pass)",
    )
    prp.add_argument(
        "--multipass-max-steps",
        dest="multipass_max_steps",
        type=int,
        default=None,
        help=f"Hard cap multipass steps (1..{MULTIPASS_MAX_STEPS_HARD_CAP}; default: from /workspaces/.reviewflow.toml or 20)",
    )
    prp.add_argument("--no-index", action="store_true", help="Skip ChunkHound indexing")
    prp.add_argument("--no-review", action="store_true", help="Skip running codex review")
    prp.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (meta.json still updates)",
    )
    prp.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream chunkhound/codex output (phase markers still print)",
    )
    prp.add_argument(
        "--ui",
        choices=["auto", "on", "off"],
        default="auto",
        help="Terminal UI dashboard (stderr): auto enables on TTY; off disables",
    )
    prp.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "debug"],
        default="normal",
        help="Output verbosity for the TUI/plain output (default: normal). In TUI, verbosity can be changed live via keys.",
    )

    cachep = sub.add_parser("cache", help="Manage base cache")
    cachesub = cachep.add_subparsers(dest="cache_cmd", required=True)
    prime = cachesub.add_parser("prime", help="Prime/update base cache for a repo/base branch")
    prime.add_argument("owner_repo", help="OWNER/REPO or HOST/OWNER/REPO")
    prime.add_argument("--base", required=True, help="Base branch/ref to index (e.g., develop)")
    prime.add_argument("--force", action="store_true", help="Force reindex of all files")
    prime.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    prime.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream chunkhound output (phase markers still print)",
    )

    status = cachesub.add_parser("status", help="Show cache metadata JSON")
    status.add_argument("owner_repo", help="OWNER/REPO or HOST/OWNER/REPO")
    status.add_argument("--base", required=True, help="Base branch/ref")

    lp = sub.add_parser("list", help="List existing review sandboxes")
    _ = lp

    ip = sub.add_parser("interactive", help="Pick a past review and resume its Codex session")
    ip.add_argument("target", nargs="?", help="Optional PR URL to filter the picker")

    cp = sub.add_parser("clean", help="Delete one review sandbox session")
    cp.add_argument("session_id", help="Session id (folder name)")

    rp = sub.add_parser(
        "resume",
        help="Resume a multipass review session (PR URL: runs follow-up if already completed)",
    )
    rp.add_argument("session_id", help="Session id (folder name) or PR URL")
    rp.add_argument(
        "--from",
        dest="from_phase",
        choices=["auto", "plan", "steps", "synth"],
        default="auto",
        help="Where to resume from (default: auto)",
    )
    rp.add_argument(
        "--codex-model",
        dest="codex_model",
        default=None,
        help="Override Codex model for remaining calls (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    rp.add_argument(
        "--codex-effort",
        dest="codex_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex model_reasoning_effort for remaining calls",
    )
    rp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex plan_mode_reasoning_effort for remaining calls",
    )
    rp.add_argument(
        "--multipass-max-steps",
        dest="multipass_max_steps",
        type=int,
        default=None,
        help=f"Hard cap multipass steps (1..{MULTIPASS_MAX_STEPS_HARD_CAP}; default: from /workspaces/.reviewflow.toml or 20)",
    )
    rp.add_argument("--no-index", action="store_true", help="Disable ChunkHound MCP for resume")
    rp.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (meta.json still updates)",
    )
    rp.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream chunkhound/codex output (phase markers still print)",
    )
    rp.add_argument(
        "--ui",
        choices=["auto", "on", "off"],
        default="auto",
        help="Terminal UI dashboard (stderr): auto enables on TTY; off disables",
    )
    rp.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "debug"],
        default="normal",
        help="Output verbosity for the TUI/plain output (default: normal). In TUI, verbosity can be changed live via keys.",
    )

    fup = sub.add_parser("followup", help="Run a follow-up review for an existing session sandbox")
    fup.add_argument("session_id", help="Session id (folder name)")
    fup.add_argument(
        "--no-update",
        action="store_true",
        help="Do not update the sandbox repo to the latest PR HEAD before reviewing",
    )
    fup.add_argument(
        "--codex-model",
        dest="codex_model",
        default=None,
        help="Override Codex model for the follow-up review agent (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    fup.add_argument(
        "--codex-effort",
        dest="codex_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex model_reasoning_effort for the follow-up review agent",
    )
    fup.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex plan_mode_reasoning_effort for the follow-up review agent",
    )
    fup.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (meta.json still updates)",
    )
    fup.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream chunkhound/codex output (phase markers still print)",
    )
    fup.add_argument(
        "--ui",
        choices=["auto", "on", "off"],
        default="auto",
        help="Terminal UI dashboard (stderr): auto enables on TTY; off disables",
    )
    fup.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "debug"],
        default="normal",
        help="Output verbosity for the TUI/plain output (default: normal). In TUI, verbosity can be changed live via keys.",
    )

    zp = sub.add_parser("zip", help="Synthesize a final review from the latest generated reviews for a PR")
    zp.add_argument("pr_url", help="GitHub PR URL")
    zp.add_argument(
        "--codex-model",
        dest="codex_model",
        default=None,
        help="Override Codex model for the zip arbiter agent (default: from /workspaces/.reviewflow.toml or /workspaces/academy+/.codex/config.toml)",
    )
    zp.add_argument(
        "--codex-effort",
        dest="codex_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex model_reasoning_effort for the zip arbiter agent",
    )
    zp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override Codex plan_mode_reasoning_effort for the zip arbiter agent",
    )
    zp.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (zip meta.json still updates)",
    )
    zp.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream codex output (phase markers still print)",
    )
    zp.add_argument(
        "--ui",
        choices=["auto", "on", "off"],
        default="auto",
        help="Terminal UI dashboard (stderr): auto enables on TTY; off disables",
    )
    zp.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "debug"],
        default="normal",
        help="Output verbosity for the TUI/plain output (default: normal). In TUI, verbosity can be changed live via keys.",
    )

    upp = sub.add_parser("ui-preview", help="Render the TUI dashboard from an existing session")
    upp.add_argument("session_id", help="Session id (folder name)")
    upp.add_argument(
        "--watch",
        action="store_true",
        help="Continuously repaint the dashboard (~5 Hz) until Ctrl+C",
    )
    upp.add_argument("--width", type=int, default=None, help="Terminal width (default: auto)")
    upp.add_argument("--height", type=int, default=None, help="Terminal height (default: auto)")
    upp.add_argument(
        "--verbosity",
        choices=["quiet", "normal", "debug"],
        default="normal",
        help="Dashboard verbosity (default: normal)",
    )
    upp.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI styling (default: auto-enable on supported TTYs)",
    )

    jsp = sub.add_parser("jira-smoke", help="Acceptance smoke test: Jira access via Codex")
    jsp.add_argument("jira_key", help="Jira key to fetch (e.g., ABAU-985)")
    jsp.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="How many attempts to run (default: 1)",
    )
    jsp.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Seconds to wait between attempts (default: 0.0)",
    )
    jsp.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    jsp.add_argument(
        "--no-stream",
        action="store_true",
        help="Do not stream codex output",
    )

    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    paths = DEFAULT_PATHS

    try:
        if args.cmd == "pr":
            return pr_flow(args, paths=paths)
        if args.cmd == "ui-preview":
            return ui_preview_flow(args, paths=paths)
        if args.cmd == "cache":
            host, owner, repo = parse_owner_repo(args.owner_repo)
            if args.cache_cmd == "prime":
                cache_prime(
                    paths=paths,
                    host=host,
                    owner=owner,
                    repo=repo,
                    base_ref=str(args.base),
                    force=bool(args.force),
                    quiet=bool(getattr(args, "quiet", False)),
                    no_stream=bool(getattr(args, "no_stream", False)),
                )
                return 0
            if args.cache_cmd == "status":
                return cache_status(
                    paths=paths,
                    host=host,
                    owner=owner,
                    repo=repo,
                    base_ref=str(args.base),
                )
        if args.cmd == "list":
            return list_sessions(paths=paths)
        if args.cmd == "interactive":
            return interactive_flow(args, paths=paths)
        if args.cmd == "clean":
            return clean_session(str(args.session_id), paths=paths)
        if args.cmd == "resume":
            return resume_flow(args, paths=paths)
        if args.cmd == "followup":
            return followup_flow(args, paths=paths)
        if args.cmd == "zip":
            return zip_flow(args, paths=paths)
        if args.cmd == "jira-smoke":
            return jira_smoke_flow(args, paths=paths)
    except ReviewflowError as e:
        _eprint(str(e))
        return 2
    except ReviewflowSubprocessError as e:
        _eprint(str(e))
        if e.stderr.strip():
            _eprint(e.stderr.strip())
        return int(e.exit_code) or 2

    raise AssertionError("Unhandled command")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
