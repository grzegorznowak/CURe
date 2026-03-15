from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import importlib.util
import json
import os
import re
import select
import secrets
import shlex
import shutil
import subprocess
import sys
import termios
import time
import tomllib
import tty
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from meta import json_fingerprint, write_json, write_redacted_json
from paths import (
    DEFAULT_PATHS,
    ReviewflowPaths,
    base_dir,
    default_cache_root,
    default_codex_base_config_path,
    default_reviewflow_config_path,
    default_sandbox_root,
    repo_id_for_gh,
    real_user_home_dir,
    safe_ref_slug,
    seed_dir,
)
from run import ReviewflowSubprocessError, merged_env, run_cmd

from ui import Dashboard, TailBuffer, UiSnapshot, UiState, Verbosity, StreamSink, build_dashboard_lines


class ReviewflowError(RuntimeError):
    pass


_DISABLED_REVIEWFLOW_CONFIG_PATH: Path | None = None


def _set_disabled_reviewflow_config_path(path: Path | None) -> None:
    global _DISABLED_REVIEWFLOW_CONFIG_PATH
    _DISABLED_REVIEWFLOW_CONFIG_PATH = path.resolve(strict=False) if path is not None else None


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
    disabled = _DISABLED_REVIEWFLOW_CONFIG_PATH
    if disabled is not None and path.resolve(strict=False) == disabled:
        return {}
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

DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE = "cure_first_unrestricted"
CODEX_REASONING_EFFORT_CHOICES = ("minimal", "low", "medium", "high", "xhigh")
LLM_TRANSPORT_CHOICES = ("http", "cli")
HTTP_LLM_PROVIDERS = ("openai", "openrouter")
CLI_LLM_PROVIDERS = ("codex", "claude", "gemini")
LLM_RESUME_PROVIDERS = ("codex", "claude")
DEFAULT_LEGACY_CODEX_PRESET = "legacy_codex"
BUILTIN_PROMPT_PACKAGE = "prompts"
AGENT_RUNTIME_PROFILE_CHOICES = ("balanced", "strict", "permissive")
DEFAULT_AGENT_RUNTIME_PROFILE = "balanced"
BUILTIN_LLM_PRESET_IDS = (
    "codex-cli",
    "claude-cli",
    "gemini-cli",
    "openai-responses",
    "openrouter-responses",
)
CURATED_ENV_INHERIT_KEYS = (
    "ANTHROPIC_API_KEY",
    "CHUNKHOUND_EMBEDDING__API_KEY",
    "CHUNKHOUND_LLM_API_KEY",
    "COLORTERM",
    "FORCE_COLOR",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_COLOR",
    "OPENAI_API_KEY",
    "PATH",
    "SHELL",
    "SSH_AUTH_SOCK",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "VOYAGE_API_KEY",
)
DEFAULT_MULTIPASS_ENABLED = True
DEFAULT_MULTIPASS_MAX_STEPS = 20
MULTIPASS_MAX_STEPS_HARD_CAP = 20
PRIMARY_CLI_COMMAND = "cure"
DEPRECATED_CLI_ALIAS = "reviewflow"
DEPRECATED_ALIAS_WARNING = (
    "`reviewflow` is deprecated for this release and will be removed after the alias window. "
    "Use `cure` instead."
)

REVIEW_INTELLIGENCE_CONFIG_EXAMPLE = """[review_intelligence]
tool_prompt_fragment = \"\"\"
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
\"\"\"
"""

CHUNKHOUND_CONFIG_EXAMPLE = """[chunkhound]
base_config_path = \"/absolute/path/to/chunkhound-base.json\"

[chunkhound.indexing]
# Optional: when set, these replace the corresponding lists in the base config.
include = [\"**/*.py\", \"**/*.ts\"]
exclude = [\"**/.claude/**\", \"**/openspec/**\"]
per_file_timeout_seconds = 6
per_file_timeout_min_size_kb = 128

[chunkhound.research]
algorithm = \"hybrid\"
"""


@dataclass(frozen=True)
class ReviewflowRuntime:
    config_path: Path
    config_source: str
    config_enabled: bool
    paths: ReviewflowPaths
    sandbox_root_source: str
    cache_root_source: str
    codex_base_config_path: Path
    codex_base_config_source: str


def _resolve_optional_path(raw: object, *, base_dir: Path | None = None) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        anchor = base_dir or Path.cwd()
        path = anchor / path
    return path.resolve(strict=False)


def _select_path_with_source(
    *,
    cli_value: object,
    env_value: object,
    config_value: Path | None,
    default_value: Path,
    base_dir: Path | None = None,
) -> tuple[Path, str]:
    cli_path = _resolve_optional_path(cli_value, base_dir=base_dir)
    if cli_path is not None:
        return cli_path, "cli"
    env_path = _resolve_optional_path(env_value, base_dir=base_dir)
    if env_path is not None:
        return env_path, "env"
    if config_value is not None:
        return config_value, "config"
    return default_value.resolve(strict=False), "default"


def load_reviewflow_paths_defaults(
    *, config_path: Path | None = None
) -> tuple[dict[str, Path | None], dict[str, Any]]:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("paths", {}) if isinstance(raw, dict) else {}
    section = section if isinstance(section, dict) else {}
    base_dir = path.parent
    sandbox_root = _resolve_optional_path(section.get("sandbox_root"), base_dir=base_dir)
    cache_root = _resolve_optional_path(section.get("cache_root"), base_dir=base_dir)
    cfg = {"sandbox_root": sandbox_root, "cache_root": cache_root}
    meta = {
        "config_path": str(path),
        "loaded": bool(raw),
        "paths": {
            "sandbox_root": str(sandbox_root) if sandbox_root is not None else None,
            "cache_root": str(cache_root) if cache_root is not None else None,
        },
    }
    return cfg, meta


def load_reviewflow_codex_base_config_path(*, config_path: Path | None = None) -> Path | None:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("codex", {}) if isinstance(raw, dict) else {}
    section = section if isinstance(section, dict) else {}
    return _resolve_optional_path(section.get("base_config_path"), base_dir=path.parent)


def resolve_reviewflow_config_path(args: argparse.Namespace) -> tuple[Path, str, bool]:
    config_path, config_source = _select_path_with_source(
        cli_value=getattr(args, "config_path", None),
        env_value=os.environ.get("REVIEWFLOW_CONFIG"),
        config_value=None,
        default_value=default_reviewflow_config_path(),
    )
    config_enabled = not bool(getattr(args, "no_config", False))
    _set_disabled_reviewflow_config_path(None if config_enabled else config_path)
    return config_path, config_source, config_enabled


def resolve_runtime_paths(args: argparse.Namespace, *, config_path: Path) -> tuple[ReviewflowPaths, str, str]:
    path_defaults, _ = load_reviewflow_paths_defaults(config_path=config_path)
    sandbox_root, sandbox_root_source = _select_path_with_source(
        cli_value=getattr(args, "sandbox_root", None),
        env_value=os.environ.get("REVIEWFLOW_SANDBOX_ROOT"),
        config_value=path_defaults.get("sandbox_root"),
        default_value=default_sandbox_root(),
    )
    cache_root, cache_root_source = _select_path_with_source(
        cli_value=getattr(args, "cache_root", None),
        env_value=os.environ.get("REVIEWFLOW_CACHE_ROOT"),
        config_value=path_defaults.get("cache_root"),
        default_value=default_cache_root(),
    )
    return ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root), sandbox_root_source, cache_root_source


def resolve_codex_base_config_path(args: argparse.Namespace, *, config_path: Path) -> tuple[Path, str]:
    return _select_path_with_source(
        cli_value=getattr(args, "codex_config_path", None),
        env_value=os.environ.get("REVIEWFLOW_CODEX_CONFIG"),
        config_value=load_reviewflow_codex_base_config_path(config_path=config_path),
        default_value=default_codex_base_config_path(),
    )


def resolve_runtime(args: argparse.Namespace) -> ReviewflowRuntime:
    config_path, config_source, config_enabled = resolve_reviewflow_config_path(args)
    paths, sandbox_root_source, cache_root_source = resolve_runtime_paths(args, config_path=config_path)
    codex_base_config_path, codex_base_config_source = resolve_codex_base_config_path(
        args, config_path=config_path
    )
    return ReviewflowRuntime(
        config_path=config_path,
        config_source=config_source,
        config_enabled=config_enabled,
        paths=paths,
        sandbox_root_source=sandbox_root_source,
        cache_root_source=cache_root_source,
        codex_base_config_path=codex_base_config_path,
        codex_base_config_source=codex_base_config_source,
    )


def builtin_prompt_id(name: str) -> str:
    return f"builtin:{name}"


def load_builtin_prompt_text(name: str) -> str:
    try:
        return resources.files(BUILTIN_PROMPT_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise ReviewflowError(f"Missing built-in prompt template: {builtin_prompt_id(name)}") from e


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


def parse_llm_key_value(raw: str, *, value_mode: str) -> tuple[str, Any]:
    text = str(raw or "").strip()
    if "=" not in text:
        raise ReviewflowError(f"Expected KEY=VALUE for --llm-{value_mode}, got: {raw!r}")
    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise ReviewflowError(f"Expected non-empty KEY for --llm-{value_mode}.")
    if value_mode == "header":
        return key, value.strip()
    try:
        parsed = tomllib.loads(f"value = {value}\n").get("value")
    except Exception:
        parsed = value.strip()
    return key, parsed


def parse_llm_request_overrides(raw_items: object) -> dict[str, Any]:
    if not isinstance(raw_items, list):
        return {}
    out: dict[str, Any] = {}
    for item in raw_items:
        key, value = parse_llm_key_value(str(item), value_mode="set")
        out[key] = value
    return out


def parse_llm_header_overrides(raw_items: object) -> dict[str, str]:
    if not isinstance(raw_items, list):
        return {}
    out: dict[str, str] = {}
    for item in raw_items:
        key, value = parse_llm_key_value(str(item), value_mode="header")
        out[key] = str(value)
    return out


def add_llm_override_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--llm-preset",
        dest="llm_preset",
        default=None,
        help="Select a named review-agent preset from the active CURe config",
    )
    parser.add_argument(
        "--llm-model",
        dest="llm_model",
        default=None,
        help="Override the resolved review-agent model",
    )
    parser.add_argument(
        "--llm-effort",
        dest="llm_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override the resolved review-agent reasoning effort",
    )
    parser.add_argument(
        "--llm-plan-effort",
        dest="llm_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help="Override the resolved review-agent plan reasoning effort",
    )
    parser.add_argument(
        "--llm-verbosity",
        dest="llm_verbosity",
        default=None,
        help="Override the resolved review-agent text verbosity",
    )
    parser.add_argument(
        "--llm-max-output-tokens",
        dest="llm_max_output_tokens",
        type=int,
        default=None,
        help="Override the resolved review-agent max_output_tokens",
    )
    parser.add_argument(
        "--llm-set",
        dest="llm_set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Merge a provider-specific request field into the selected llm preset",
    )
    parser.add_argument(
        "--llm-header",
        dest="llm_header",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Merge an HTTP header into the selected llm preset",
    )


def resolve_llm_config_from_args(
    args: argparse.Namespace,
    *,
    reviewflow_config_path: Path | None = None,
    base_codex_config_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return resolve_llm_config(
        base_codex_config_path=(base_codex_config_path or default_codex_base_config_path()),
        reviewflow_config_path=(reviewflow_config_path or default_reviewflow_config_path()),
        cli_preset=getattr(args, "llm_preset", None),
        cli_model=getattr(args, "llm_model", None),
        cli_effort=getattr(args, "llm_effort", None),
        cli_plan_effort=getattr(args, "llm_plan_effort", None),
        cli_verbosity=getattr(args, "llm_verbosity", None),
        cli_max_output_tokens=getattr(args, "llm_max_output_tokens", None),
        cli_request_overrides=parse_llm_request_overrides(getattr(args, "llm_set", [])),
        cli_header_overrides=parse_llm_header_overrides(getattr(args, "llm_header", [])),
        deprecated_codex_model=getattr(args, "codex_model", None),
        deprecated_codex_effort=getattr(args, "codex_effort", None),
        deprecated_codex_plan_effort=getattr(args, "codex_plan_effort", None),
    )


def build_llm_meta(
    *,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    env: dict[str, str],
    adapter_meta: dict[str, Any] | None = None,
    helpers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "preset": resolved.get("preset"),
        "selected_name": resolved.get("selected_name"),
        "transport": resolved.get("transport"),
        "provider": resolved.get("provider"),
        "command": resolved.get("command"),
        "model": resolved.get("model"),
        "reasoning_effort": resolved.get("reasoning_effort"),
        "plan_reasoning_effort": resolved.get("plan_reasoning_effort"),
        "text_verbosity": resolved.get("text_verbosity"),
        "max_output_tokens": resolved.get("max_output_tokens"),
        "runtime_overrides": resolution_meta.get("runtime_overrides"),
        "config": resolution_meta,
        "adapter": dict(adapter_meta or {}),
        "helpers": dict(helpers or {}),
        "env_keys": sorted(_string_dict(resolved.get("env")).keys()),
        "capabilities": dict(resolved.get("capabilities") or {}),
    }


def apply_llm_env(base_env: dict[str, str], *, resolved: dict[str, Any]) -> dict[str, str]:
    env = dict(base_env)
    env.update(_string_dict(resolved.get("env")))
    return env


def build_curated_subprocess_env(
    *,
    inherited_env: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
    home_override: Path | None = None,
) -> dict[str, str]:
    source = inherited_env if inherited_env is not None else os.environ
    env: dict[str, str] = {}
    for key in CURATED_ENV_INHERIT_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            env[key] = value
    if home_override is not None:
        env["HOME"] = str(home_override)
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items() if str(v)})
    return env


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        resolved = str(path.resolve(strict=False))
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def load_reviewflow_multipass_defaults(
    *, config_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load reviewflow-level multipass defaults from the active reviewflow config.

    Schema:
      [multipass]
      enabled = true
      max_steps = 20
    """

    path = config_path or default_reviewflow_config_path()
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
    """Load reviewflow-level Codex defaults from the active reviewflow config.

    Schema:
      [codex]
      model = "..."
      model_reasoning_effort = "..."
      plan_mode_reasoning_effort = "..."
    """

    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    wanted_keys = ("model", "model_reasoning_effort", "plan_mode_reasoning_effort")

    source_table = "codex"
    codex = raw.get("codex", {}) if isinstance(raw, dict) else {}
    codex = codex if isinstance(codex, dict) else {}
    if not any(isinstance(codex.get(key), str) and codex.get(key).strip() for key in wanted_keys):
        root_defaults = raw if isinstance(raw, dict) else {}
        if any(
            isinstance(root_defaults.get(key), str) and root_defaults.get(key).strip()
            for key in wanted_keys
        ):
            codex = root_defaults
            source_table = "root"

    defaults: dict[str, str] = {}
    for key in wanted_keys:
        val = codex.get(key)
        if isinstance(val, str) and val.strip():
            defaults[key] = val.strip()

    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "codex": dict(defaults),
        "codex_source_table": source_table if defaults else "unset",
    }
    return defaults, meta


def _string_dict(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        out[name] = str(value)
    return out


def _plain_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        out[name] = value
    return out


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def builtin_llm_presets() -> dict[str, dict[str, Any]]:
    return {
        "codex-cli": {
            "transport": "cli",
            "provider": "codex",
            "command": "codex",
            "endpoint": None,
            "base_url": None,
            "api_key": None,
            "store": None,
            "include": [],
            "metadata": {},
            "headers": {},
            "request": {},
            "env": {},
            "text_verbosity": None,
            "max_output_tokens": None,
        },
        "claude-cli": {
            "transport": "cli",
            "provider": "claude",
            "command": "claude",
            "endpoint": None,
            "base_url": None,
            "api_key": None,
            "store": None,
            "include": [],
            "metadata": {},
            "headers": {},
            "request": {},
            "env": {},
            "text_verbosity": None,
            "max_output_tokens": None,
        },
        "gemini-cli": {
            "transport": "cli",
            "provider": "gemini",
            "command": "gemini",
            "endpoint": None,
            "base_url": None,
            "api_key": None,
            "store": None,
            "include": [],
            "metadata": {},
            "headers": {},
            "request": {},
            "env": {},
            "text_verbosity": None,
            "max_output_tokens": None,
        },
        "openai-responses": {
            "transport": "http",
            "provider": "openai",
            "command": None,
            "endpoint": "responses",
            "base_url": "https://api.openai.com/v1",
            "store": None,
            "include": [],
            "metadata": {},
            "headers": {},
            "request": {},
            "env": {},
        },
        "openrouter-responses": {
            "transport": "http",
            "provider": "openrouter",
            "command": None,
            "endpoint": "responses",
            "base_url": "https://openrouter.ai/api/v1",
            "store": None,
            "include": [],
            "metadata": {},
            "headers": {},
            "request": {},
            "env": {},
        },
    }


def _preset_compat_id_from_explicit_block(raw_preset: dict[str, Any]) -> str | None:
    transport = str(raw_preset.get("transport") or "").strip().lower()
    provider = str(raw_preset.get("provider") or "").strip().lower()
    endpoint = str(raw_preset.get("endpoint") or "responses").strip().lower()
    base_url = str(raw_preset.get("base_url") or "").strip().rstrip("/")
    command = str(raw_preset.get("command") or "").strip()

    if transport == "cli" and provider == "codex" and command in {"", "codex"}:
        return "codex-cli"
    if transport == "cli" and provider == "claude" and command in {"", "claude"}:
        return "claude-cli"
    if transport == "cli" and provider == "gemini" and command in {"", "gemini"}:
        return "gemini-cli"
    if (
        transport == "http"
        and provider == "openai"
        and endpoint == "responses"
        and base_url in {"", "https://api.openai.com/v1"}
    ):
        return "openai-responses"
    if (
        transport == "http"
        and provider == "openrouter"
        and endpoint == "responses"
        and base_url in {"", "https://openrouter.ai/api/v1"}
    ):
        return "openrouter-responses"
    return None


def _normalized_preset_overrides(raw_preset: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": str(raw_preset.get("model") or "").strip() or None,
        "reasoning_effort": str(raw_preset.get("reasoning_effort") or "").strip() or None,
        "plan_reasoning_effort": str(raw_preset.get("plan_reasoning_effort") or "").strip() or None,
        "text_verbosity": str(raw_preset.get("text_verbosity") or "").strip() or None,
        "max_output_tokens": (
            int(raw_preset.get("max_output_tokens"))
            if isinstance(raw_preset.get("max_output_tokens"), int)
            else None
        ),
        "request": _plain_dict(raw_preset.get("request")),
        "api_key": str(raw_preset.get("api_key") or "").strip() or None,
        "store": raw_preset.get("store") if isinstance(raw_preset.get("store"), bool) else None,
        "include": _string_list(raw_preset.get("include")),
        "metadata": _plain_dict(raw_preset.get("metadata")),
        "headers": _string_dict(raw_preset.get("headers")),
        "env": _string_dict(raw_preset.get("env")),
    }


def _merge_builtin_preset(
    *, preset_id: str, raw_preset: dict[str, Any], source_mode: str
) -> dict[str, Any]:
    builtins = builtin_llm_presets()
    if preset_id not in builtins:
        raise ReviewflowError(
            f"Unknown built-in llm preset: {preset_id!r}. Expected one of: {', '.join(BUILTIN_LLM_PRESET_IDS)}"
        )
    merged = dict(builtins[preset_id])
    overrides = _normalized_preset_overrides(raw_preset)
    for key, value in overrides.items():
        if key in {"request", "metadata", "headers", "env"}:
            merged[key] = dict(value)
            continue
        if key == "include":
            merged[key] = list(value)
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    merged["preset"] = preset_id
    merged["_source_mode"] = source_mode
    return merged


def load_reviewflow_llm_config(
    *, config_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    llm = raw.get("llm", {}) if isinstance(raw, dict) else {}
    llm = llm if isinstance(llm, dict) else {}
    default_preset = str(llm.get("default_preset") or "").strip() or None

    presets_raw = raw.get("llm_presets", {}) if isinstance(raw, dict) else {}
    presets_raw = presets_raw if isinstance(presets_raw, dict) else {}
    presets: dict[str, dict[str, Any]] = {}
    deprecated_explicit_presets: list[str] = []
    invalid_mixed_presets: list[str] = []
    for raw_name, raw_preset in presets_raw.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_preset, dict):
            continue
        builtin_id = str(raw_preset.get("preset") or "").strip()
        removed_keys = {"transport", "provider", "endpoint", "base_url", "command"}
        present_removed = [key for key in removed_keys if key in raw_preset]
        if builtin_id:
            if present_removed:
                invalid_mixed_presets.append(name)
                continue
            preset = _merge_builtin_preset(preset_id=builtin_id, raw_preset=raw_preset, source_mode="builtin")
        else:
            compat_id = _preset_compat_id_from_explicit_block(raw_preset)
            if compat_id is None:
                continue
            deprecated_explicit_presets.append(name)
            preset = _merge_builtin_preset(
                preset_id=compat_id,
                raw_preset=raw_preset,
                source_mode="deprecated_explicit",
            )
        presets[name] = preset

    if invalid_mixed_presets:
        raise ReviewflowError(
            "llm preset blocks cannot mix `preset = ...` with explicit transport/provider/command/base_url/endpoint "
            f"fields: {', '.join(sorted(invalid_mixed_presets))}"
        )

    cfg = {"default_preset": default_preset, "presets": presets}
    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "default_preset": default_preset,
        "preset_names": sorted(presets.keys()),
        "builtin_preset_ids": list(BUILTIN_LLM_PRESET_IDS),
        "deprecated_explicit_presets": sorted(deprecated_explicit_presets),
    }
    return cfg, meta


def _normalize_agent_runtime_profile(value: object, *, source: str) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text not in AGENT_RUNTIME_PROFILE_CHOICES:
        raise ReviewflowError(
            f"Invalid agent runtime profile from {source}: {text!r}. "
            f"Expected one of: {', '.join(AGENT_RUNTIME_PROFILE_CHOICES)}"
        )
    return text


def load_reviewflow_agent_runtime_config(
    *, config_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("agent_runtime", {}) if isinstance(raw, dict) else {}
    section = section if isinstance(section, dict) else {}
    gemini = section.get("gemini", {})
    gemini = gemini if isinstance(gemini, dict) else {}

    profile = _normalize_agent_runtime_profile(section.get("profile"), source="config")
    sandbox = str(gemini.get("sandbox") or "").strip() or None
    seatbelt_profile = str(gemini.get("seatbelt_profile") or "").strip() or None

    cfg = {
        "profile": profile,
        "gemini": {
            "sandbox": sandbox,
            "seatbelt_profile": seatbelt_profile,
        },
    }
    meta = {
        "config_path": str(path),
        "loaded": bool(raw),
        "agent_runtime": {
            "profile": profile,
            "gemini": dict(cfg["gemini"]),
        },
    }
    return cfg, meta


def resolve_agent_runtime_profile(
    *,
    cli_value: str | None,
    config_path: Path | None = None,
    config_enabled: bool = True,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    cfg, meta = load_reviewflow_agent_runtime_config(config_path=config_path)
    cli_profile = _normalize_agent_runtime_profile(cli_value, source="cli")
    if cli_profile is not None:
        return cli_profile, "cli", cfg, meta

    env_profile = _normalize_agent_runtime_profile(
        os.environ.get("REVIEWFLOW_AGENT_RUNTIME_PROFILE"), source="env"
    )
    if env_profile is not None:
        return env_profile, "env", cfg, meta

    if config_enabled:
        config_profile = _normalize_agent_runtime_profile(cfg.get("profile"), source="config")
        if config_profile is not None:
            return config_profile, "config", cfg, meta

    return DEFAULT_AGENT_RUNTIME_PROFILE, "default", cfg, meta


def _base_codex_runtime_defaults(base_config_path: Path) -> dict[str, Any]:
    raw = load_toml(base_config_path)
    return {
        "path": str(base_config_path),
        "loaded": bool(raw),
        "model": str(raw.get("model") or "").strip() or None,
        "sandbox_mode": str(raw.get("sandbox_mode") or "").strip() or None,
        "web_search": str(raw.get("web_search") or "").strip() or None,
        "reasoning_effort": str(raw.get("model_reasoning_effort") or "").strip() or None,
        "plan_reasoning_effort": str(raw.get("plan_mode_reasoning_effort") or "").strip() or None,
    }


def _synthetic_legacy_codex_preset(
    *, base_codex_config_path: Path, reviewflow_config_path: Path | None
) -> dict[str, Any]:
    legacy_defaults, _ = load_reviewflow_codex_defaults(config_path=reviewflow_config_path)
    return {
        "transport": "cli",
        "provider": "codex",
        "command": "codex",
        "model": legacy_defaults.get("model"),
        "reasoning_effort": legacy_defaults.get("model_reasoning_effort"),
        "plan_reasoning_effort": legacy_defaults.get("plan_mode_reasoning_effort"),
        "text_verbosity": None,
        "max_output_tokens": None,
        "env": {},
        "request": {},
        "headers": {},
        "endpoint": None,
        "base_url": None,
        "api_key": None,
        "store": None,
        "include": [],
        "metadata": {},
    }


def resolve_llm_config(
    *,
    base_codex_config_path: Path,
    reviewflow_config_path: Path | None,
    cli_preset: str | None,
    cli_model: str | None,
    cli_effort: str | None,
    cli_plan_effort: str | None,
    cli_verbosity: str | None,
    cli_max_output_tokens: int | None,
    cli_request_overrides: dict[str, Any] | None,
    cli_header_overrides: dict[str, str] | None,
    deprecated_codex_model: str | None,
    deprecated_codex_effort: str | None,
    deprecated_codex_plan_effort: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    llm_cfg, llm_meta = load_reviewflow_llm_config(config_path=reviewflow_config_path)
    presets = llm_cfg.get("presets", {})
    presets = presets if isinstance(presets, dict) else {}
    builtin_presets = builtin_llm_presets()

    selected_name = str(cli_preset or "").strip() or str(llm_cfg.get("default_preset") or "").strip()
    preset_source = "cli" if str(cli_preset or "").strip() else "reviewflow.toml"
    if selected_name:
        if selected_name in presets:
            base_preset = dict(presets[selected_name])
            resolved_preset_id = str(base_preset.get("preset") or selected_name).strip() or selected_name
        elif selected_name in builtin_presets:
            base_preset = dict(builtin_presets[selected_name])
            base_preset["preset"] = selected_name
            base_preset["_source_mode"] = "builtin_direct"
            resolved_preset_id = selected_name
        else:
            available = sorted(set(presets.keys()) | set(builtin_presets.keys()))
            raise ReviewflowError(
                f"Unknown llm preset: {selected_name!r}. Available presets: {', '.join(available) or '(none)'}"
            )
    else:
        selected_name = DEFAULT_LEGACY_CODEX_PRESET
        preset_source = "synthetic_legacy_codex"
        base_preset = _synthetic_legacy_codex_preset(
            base_codex_config_path=base_codex_config_path,
            reviewflow_config_path=reviewflow_config_path,
        )
        resolved_preset_id = DEFAULT_LEGACY_CODEX_PRESET

    transport = str(base_preset.get("transport") or "").strip().lower()
    provider = str(base_preset.get("provider") or "").strip().lower()
    if transport not in LLM_TRANSPORT_CHOICES:
        raise ReviewflowError(f"Invalid llm preset transport for {selected_name!r}: {transport!r}")
    if transport == "http" and provider not in HTTP_LLM_PROVIDERS:
        raise ReviewflowError(f"Invalid HTTP llm provider for {selected_name!r}: {provider!r}")
    if transport == "cli" and provider not in CLI_LLM_PROVIDERS:
        raise ReviewflowError(f"Invalid CLI llm provider for {selected_name!r}: {provider!r}")

    legacy_defaults, legacy_meta = load_reviewflow_codex_defaults(config_path=reviewflow_config_path)
    base_codex_meta = _base_codex_runtime_defaults(base_codex_config_path)

    def _pick(
        *,
        field: str,
        generic_value: Any,
        deprecated_value: Any = None,
        allow_deprecated: bool = False,
        base_value: Any = None,
    ) -> tuple[Any, str]:
        if generic_value not in (None, ""):
            return generic_value, "cli"
        if allow_deprecated and provider == "codex" and deprecated_value not in (None, ""):
            return deprecated_value, "deprecated_codex_cli"
        preset_value = base_preset.get(field)
        if preset_value not in (None, "", [], {}):
            return preset_value, "preset"
        if provider == "codex":
            legacy_key = {
                "reasoning_effort": "model_reasoning_effort",
                "plan_reasoning_effort": "plan_mode_reasoning_effort",
            }.get(field, field)
            legacy_value = legacy_defaults.get(legacy_key)
            if legacy_value not in (None, ""):
                return legacy_value, "legacy_codex"
            if base_value not in (None, ""):
                return base_value, "base_codex_config"
        return None, "unset"

    model, model_source = _pick(
        field="model",
        generic_value=(str(cli_model).strip() if cli_model else None),
        deprecated_value=(str(deprecated_codex_model).strip() if deprecated_codex_model else None),
        allow_deprecated=True,
        base_value=base_codex_meta.get("model"),
    )
    reasoning_effort, reasoning_effort_source = _pick(
        field="reasoning_effort",
        generic_value=(str(cli_effort).strip() if cli_effort else None),
        deprecated_value=(str(deprecated_codex_effort).strip() if deprecated_codex_effort else None),
        allow_deprecated=True,
        base_value=base_codex_meta.get("reasoning_effort"),
    )
    plan_reasoning_effort, plan_reasoning_effort_source = _pick(
        field="plan_reasoning_effort",
        generic_value=(str(cli_plan_effort).strip() if cli_plan_effort else None),
        deprecated_value=(
            str(deprecated_codex_plan_effort).strip() if deprecated_codex_plan_effort else None
        ),
        allow_deprecated=True,
        base_value=base_codex_meta.get("plan_reasoning_effort"),
    )
    text_verbosity, text_verbosity_source = _pick(
        field="text_verbosity",
        generic_value=(str(cli_verbosity).strip() if cli_verbosity else None),
    )
    max_output_tokens, max_output_tokens_source = _pick(
        field="max_output_tokens",
        generic_value=cli_max_output_tokens,
    )

    for key, val in (
        ("reasoning_effort", reasoning_effort),
        ("plan_reasoning_effort", plan_reasoning_effort),
    ):
        if val is None:
            continue
        if str(val) not in CODEX_REASONING_EFFORT_CHOICES:
            raise ReviewflowError(
                f"Invalid {key}: {val!r}. Expected one of: {', '.join(CODEX_REASONING_EFFORT_CHOICES)}"
            )

    request = dict(_plain_dict(base_preset.get("request")))
    if cli_request_overrides:
        request.update(cli_request_overrides)
    headers = dict(_string_dict(base_preset.get("headers")))
    if cli_header_overrides:
        headers.update({str(k): str(v) for k, v in cli_header_overrides.items()})

    resolved = {
        "preset": resolved_preset_id,
        "selected_name": selected_name,
        "transport": transport,
        "provider": provider,
        "command": str(base_preset.get("command") or provider).strip() if transport == "cli" else None,
        "endpoint": str(base_preset.get("endpoint") or "responses").strip() if transport == "http" else None,
        "base_url": str(base_preset.get("base_url") or "").strip() or None,
        "api_key": str(base_preset.get("api_key") or "").strip() or None,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "plan_reasoning_effort": plan_reasoning_effort,
        "text_verbosity": text_verbosity,
        "max_output_tokens": int(max_output_tokens) if isinstance(max_output_tokens, int) else None,
        "store": base_preset.get("store") if isinstance(base_preset.get("store"), bool) else None,
        "include": _string_list(base_preset.get("include")),
        "metadata": _plain_dict(base_preset.get("metadata")),
        "headers": headers,
        "request": request,
        "env": _string_dict(base_preset.get("env")),
        "capabilities": {"supports_resume": provider in LLM_RESUME_PROVIDERS},
    }

    meta: dict[str, Any] = {
        "llm_config": llm_meta,
        "legacy_codex_defaults": legacy_meta,
        "base_codex_config": base_codex_meta,
        "selected_preset_source": preset_source,
        "selected_name": selected_name,
        "resolved_preset_id": resolved_preset_id,
        "resolved": {
            "model": model,
            "model_source": model_source,
            "reasoning_effort": reasoning_effort,
            "reasoning_effort_source": reasoning_effort_source,
            "plan_reasoning_effort": plan_reasoning_effort,
            "plan_reasoning_effort_source": plan_reasoning_effort_source,
            "text_verbosity": text_verbosity,
            "text_verbosity_source": text_verbosity_source,
            "max_output_tokens": resolved["max_output_tokens"],
            "max_output_tokens_source": max_output_tokens_source,
            "sandbox_mode": base_codex_meta.get("sandbox_mode"),
            "web_search": base_codex_meta.get("web_search"),
        },
        "runtime_overrides": {
            "preset": (str(cli_preset).strip() if cli_preset else None),
            "model": (str(cli_model).strip() if cli_model else None),
            "reasoning_effort": (str(cli_effort).strip() if cli_effort else None),
            "plan_reasoning_effort": (str(cli_plan_effort).strip() if cli_plan_effort else None),
            "text_verbosity": (str(cli_verbosity).strip() if cli_verbosity else None),
            "max_output_tokens": cli_max_output_tokens if isinstance(cli_max_output_tokens, int) else None,
            "request": dict(cli_request_overrides or {}),
            "headers": dict(cli_header_overrides or {}),
            "deprecated_codex_model": (
                str(deprecated_codex_model).strip() if deprecated_codex_model else None
            ),
            "deprecated_codex_effort": (
                str(deprecated_codex_effort).strip() if deprecated_codex_effort else None
            ),
            "deprecated_codex_plan_effort": (
                str(deprecated_codex_plan_effort).strip() if deprecated_codex_plan_effort else None
            ),
        },
    }
    return resolved, meta


def build_http_response_request(resolved: dict[str, Any], *, prompt: str) -> dict[str, Any]:
    provider = str(resolved.get("provider") or "").strip().lower()
    base_url = str(resolved.get("base_url") or "").rstrip("/")
    endpoint = str(resolved.get("endpoint") or "responses").strip().lower()
    if provider not in HTTP_LLM_PROVIDERS:
        raise ReviewflowError(f"Unsupported HTTP llm provider: {provider!r}")
    if endpoint != "responses":
        raise ReviewflowError(f"Unsupported HTTP endpoint for reviewflow: {endpoint!r}")
    if not base_url:
        raise ReviewflowError("HTTP llm preset is missing base_url.")
    api_key = str(resolved.get("api_key") or "").strip()
    if not api_key:
        raise ReviewflowError(f"HTTP llm preset {resolved.get('preset')!r} is missing api_key.")

    url = f"{base_url}/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    extra_headers = _string_dict(resolved.get("headers"))
    if provider == "openrouter":
        allowed = {"HTTP-Referer", "X-OpenRouter-Title", "X-OpenRouter-Categories", "X-Title"}
        extra_headers = {k: v for k, v in extra_headers.items() if k in allowed}
    headers.update(extra_headers)

    payload: dict[str, Any] = {"model": resolved.get("model"), "input": prompt}
    reasoning_effort = str(resolved.get("reasoning_effort") or "").strip()
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    text_verbosity = str(resolved.get("text_verbosity") or "").strip()
    if text_verbosity:
        payload["text"] = {"verbosity": text_verbosity}
    if isinstance(resolved.get("store"), bool):
        payload["store"] = resolved["store"]
    include = _string_list(resolved.get("include"))
    if include:
        payload["include"] = include
    metadata = _plain_dict(resolved.get("metadata"))
    if metadata:
        payload["metadata"] = metadata
    if isinstance(resolved.get("max_output_tokens"), int):
        payload["max_output_tokens"] = int(resolved["max_output_tokens"])
    payload.update(_plain_dict(resolved.get("request")))
    return {"url": url, "headers": headers, "json": payload}


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
      2) reviewflow config defaults ([codex] in the active reviewflow config)
      3) base Codex config (the resolved Codex base config path)
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
class ReviewIntelligenceConfig:
    tool_prompt_fragment: str
    policy_mode: str = DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE


def _resolve_review_intelligence_config_error(*, path: Path) -> ReviewflowError:
    return ReviewflowError(
        "Built-in prompt profiles require `[review_intelligence].tool_prompt_fragment` "
        f"in {path}.\n"
        "Example:\n"
        f"{REVIEW_INTELLIGENCE_CONFIG_EXAMPLE.rstrip()}"
    )


def _review_intelligence_meta_dict(
    cfg: ReviewIntelligenceConfig, *, path: Path, loaded: bool
) -> dict[str, Any]:
    return {
        "config_path": str(path),
        "loaded": loaded,
        "review_intelligence": {
            "tool_prompt_fragment": cfg.tool_prompt_fragment,
            "policy_mode": cfg.policy_mode,
        },
    }


def load_review_intelligence_config(
    *, config_path: Path | None = None, require_tool_prompt_fragment: bool = False
) -> tuple[ReviewIntelligenceConfig, dict[str, Any]]:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    review_intelligence = raw.get("review_intelligence", {}) if isinstance(raw, dict) else {}
    review_intelligence = review_intelligence if isinstance(review_intelligence, dict) else {}

    legacy_keys = {
        key
        for key in ("allow_hosts", "timeout_seconds", "max_bytes", "external_fetch_gateway")
        if key in review_intelligence
    }
    if legacy_keys:
        raise ReviewflowError(
            "Legacy review-intelligence URL policy fields are no longer supported: "
            f"{', '.join(sorted(legacy_keys))}\n"
            "Use the reduced schema:\n"
            f"{REVIEW_INTELLIGENCE_CONFIG_EXAMPLE.rstrip()}"
        )
    if isinstance(raw, dict) and ("crawl" in raw):
        raise ReviewflowError(
            "Deprecated `[crawl]` config is no longer supported.\n"
            "Use the reduced schema:\n"
            f"{REVIEW_INTELLIGENCE_CONFIG_EXAMPLE.rstrip()}"
        )

    tool_prompt_fragment = str(review_intelligence.get("tool_prompt_fragment") or "").strip()
    if require_tool_prompt_fragment and (not tool_prompt_fragment):
        raise _resolve_review_intelligence_config_error(path=path)

    cfg = ReviewIntelligenceConfig(
        tool_prompt_fragment=tool_prompt_fragment,
        policy_mode=DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE,
    )
    return cfg, _review_intelligence_meta_dict(cfg, path=path, loaded=bool(raw))


def build_review_intelligence_guidance(cfg: ReviewIntelligenceConfig) -> str:
    lines = ["## Review-Intelligence Guidance"]
    if cfg.tool_prompt_fragment:
        lines.append(cfg.tool_prompt_fragment)
        lines.append("")
    lines.extend(
        [
            "Code under review first policy:",
            "- Use any source or tool that materially improves understanding of the code under review.",
            "- Favor depth, relevance, and evidence over source restrictions.",
            "- Avoid spending time on context that does not improve understanding of the code under review or the change under review.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def require_builtin_review_intelligence(
    cfg: ReviewIntelligenceConfig, *, config_path: Path | None = None
) -> None:
    if cfg.tool_prompt_fragment:
        return
    raise _resolve_review_intelligence_config_error(
        path=(config_path or default_reviewflow_config_path())
    )
def build_codex_exec_cmd(
    *,
    repo_dir: Path,
    codex_flags: list[str],
    codex_config_overrides: list[str] | None,
    review_md_path: Path,
    prompt: str,
    add_dirs: list[Path] | None = None,
    skip_git_repo_check: bool = False,
    approval_policy: str = "never",
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
) -> list[str]:
    overrides = list(codex_config_overrides or [])
    has_explicit_approval_flag = any(flag in {"-a", "--ask-for-approval"} for flag in codex_flags)
    cmd = [
        "codex",
        "-C",
        str(repo_dir),
        "--add-dir",
        "/tmp",
    ]
    for d in add_dirs or []:
        cmd.extend(["--add-dir", str(d)])
    cmd.extend(codex_flags)
    if approval_policy and (not dangerously_bypass_approvals_and_sandbox) and (not has_explicit_approval_flag):
        cmd.extend(["-a", approval_policy])
    for override in overrides:
        cmd.extend(["-c", override])
    if include_shell_environment_inherit_all:
        cmd.extend(["-c", "shell_environment_policy.inherit=all"])
    cmd.extend(
        [
        "exec",
        ]
    )
    if dangerously_bypass_approvals_and_sandbox:
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
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
    approval_policy: str = "never",
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
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
        approval_policy=approval_policy,
        dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
        include_shell_environment_inherit_all=include_shell_environment_inherit_all,
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
                approval_policy=approval_policy,
                dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
                include_shell_environment_inherit_all=include_shell_environment_inherit_all,
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


def build_codex_flags_from_llm_config(
    *, resolved: dict[str, Any], resolution_meta: dict[str, Any], include_sandbox: bool = True
) -> tuple[list[str], dict[str, Any]]:
    base_meta = resolution_meta.get("base_codex_config")
    base_meta = base_meta if isinstance(base_meta, dict) else {}
    flags: list[str] = []
    model = str(resolved.get("model") or "").strip()
    if model:
        flags.extend(["-m", model])
    sandbox_mode = str(base_meta.get("sandbox_mode") or "").strip()
    if include_sandbox and sandbox_mode in {"read-only", "workspace-write", "danger-full-access"}:
        flags.extend(["--sandbox", sandbox_mode])
    if str(base_meta.get("web_search") or "").strip() == "live":
        flags.append("--search")
    reasoning_effort = str(resolved.get("reasoning_effort") or "").strip()
    if reasoning_effort:
        flags.extend(["-c", f"model_reasoning_effort={toml_string(reasoning_effort)}"])
    plan_reasoning_effort = str(resolved.get("plan_reasoning_effort") or "").strip()
    if plan_reasoning_effort:
        flags.extend(["-c", f"plan_mode_reasoning_effort={toml_string(plan_reasoning_effort)}"])

    meta = {
        "base": base_meta,
        "reviewflow_defaults": resolution_meta.get("legacy_codex_defaults"),
        "resolved": {
            "model": resolved.get("model"),
            "model_source": ((resolution_meta.get("resolved") or {}).get("model_source")),
            "model_reasoning_effort": resolved.get("reasoning_effort"),
            "model_reasoning_effort_source": (
                (resolution_meta.get("resolved") or {}).get("reasoning_effort_source")
            ),
            "plan_mode_reasoning_effort": resolved.get("plan_reasoning_effort"),
            "plan_mode_reasoning_effort_source": (
                (resolution_meta.get("resolved") or {}).get("plan_reasoning_effort_source")
            ),
            "sandbox_mode": base_meta.get("sandbox_mode"),
            "web_search": base_meta.get("web_search"),
            "preset": resolved.get("preset"),
        },
        "flags": list(flags),
    }
    return flags, meta


def _build_env_prefix_assignments(env: dict[str, str], keys: tuple[str, ...]) -> str:
    assignments: list[str] = []
    for key in keys:
        value = str(env.get(key) or "").strip()
        if value:
            assignments.append(f"{key}={shlex.quote(value)}")
    if not assignments:
        return ""
    return "env " + " ".join(assignments) + " "


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    candidates.extend(line.strip() for line in raw.splitlines() if line.strip())
    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def _extract_http_response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    outputs = payload.get("output")
    if not isinstance(outputs, list):
        raise ReviewflowError("HTTP response payload did not contain output text.")
    chunks: list[str] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if part_type in {"output_text", "text"}:
                text = str(part.get("text") or "").strip()
                if text:
                    chunks.append(text)
    if not chunks:
        raise ReviewflowError("HTTP response payload did not contain output text.")
    return "\n\n".join(chunks)


def _run_logged_text_command(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
) -> "CommandResult":
    out = _ACTIVE_OUTPUT
    if out is not None:
        return out.run_logged_cmd(
            cmd,
            kind="codex",
            cwd=cwd,
            env=env,
            check=True,
            stream_requested=False,
        )
    return run_cmd(cmd, cwd=cwd, env=env, check=True, stream=False, stream_label="codex")


def build_claude_exec_cmd(
    *,
    command: str,
    model: str | None,
    prompt: str,
    runtime_policy: dict[str, Any] | None = None,
) -> list[str]:
    cmd = [command, "--print", "--output-format", "json"]
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        cmd.extend([str(item) for item in provider_args])
    elif not policy:
        cmd.append("--dangerously-skip-permissions")
    if bool(policy.get("dangerously_skip_permissions")):
        cmd.append("--dangerously-skip-permissions")
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    return cmd


def build_claude_resume_command(
    *,
    repo_dir: Path,
    session_id: str,
    env: dict[str, str],
    command: str,
    runtime_policy: dict[str, Any] | None = None,
) -> str:
    env_prefix = _build_env_prefix_assignments(
        env,
        (
            "ANTHROPIC_API_KEY",
            "GH_CONFIG_DIR",
            "JIRA_CONFIG_FILE",
            "NETRC",
            "REVIEWFLOW_WORK_DIR",
        ),
    )
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    resume_cmd = [command]
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        resume_cmd.extend([str(item) for item in provider_args])
    elif not policy:
        resume_cmd.append("--dangerously-skip-permissions")
    if bool(policy.get("dangerously_skip_permissions")):
        resume_cmd.append("--dangerously-skip-permissions")
    resume_cmd.extend(["--resume", session_id])
    return f"cd {shlex.quote(str(repo_dir))} && {env_prefix}{_shell_join(resume_cmd)}"


def run_claude_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    progress: "SessionProgress",
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    cmd = build_claude_exec_cmd(
        command=str(resolved.get("command") or "claude"),
        model=str(resolved.get("model") or "").strip() or None,
        prompt=prompt,
        runtime_policy=runtime_policy,
    )
    progress.record_cmd(cmd)
    result = _run_logged_text_command(cmd=cmd, cwd=repo_dir, env=env)
    payload = _extract_json_object(result.stdout) or {}
    text = str(payload.get("result") or result.stdout or "").strip()
    if not text:
        raise ReviewflowError("Claude did not return any printable review output.")
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    session_id = str(payload.get("session_id") or "").strip()
    resume = None
    if session_id:
        resume = LlmResumeInfo(
            provider="claude",
            session_id=session_id,
            cwd=repo_dir.resolve(),
            command=build_claude_resume_command(
                repo_dir=repo_dir.resolve(),
                session_id=session_id,
                env=env,
                command=str(resolved.get("command") or "claude"),
                runtime_policy=runtime_policy,
            ),
        )
    return LlmRunResult(
        resume=resume,
        adapter_meta={"transport": "cli-claude", "command": safe_cmd_for_meta(cmd)},
    )


def build_gemini_exec_cmd(
    *,
    command: str,
    model: str | None,
    prompt: str,
    runtime_policy: dict[str, Any] | None = None,
) -> list[str]:
    cmd = [command]
    policy = runtime_policy if isinstance(runtime_policy, dict) else {}
    provider_args = policy.get("provider_args")
    if isinstance(provider_args, list):
        cmd.extend([str(item) for item in provider_args])
    if model:
        cmd.extend(["-m", model])
    cmd.extend(["-p", prompt])
    return cmd


def run_gemini_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    progress: "SessionProgress",
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    cmd = build_gemini_exec_cmd(
        command=str(resolved.get("command") or "gemini"),
        model=str(resolved.get("model") or "").strip() or None,
        prompt=prompt,
        runtime_policy=runtime_policy,
    )
    progress.record_cmd(cmd)
    result = _run_logged_text_command(cmd=cmd, cwd=repo_dir, env=env)
    payload = _extract_json_object(result.stdout)
    text = str((payload or {}).get("response") or result.stdout or "").strip()
    if not text:
        raise ReviewflowError("Gemini did not return any printable review output.")
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    return LlmRunResult(
        resume=None,
        adapter_meta={"transport": "cli-gemini", "command": safe_cmd_for_meta(cmd)},
    )


def run_http_response_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    output_path: Path,
    prompt: str,
    progress: "SessionProgress",
) -> LlmRunResult:
    request_meta = build_http_response_request(resolved, prompt=prompt)
    cmd_meta = [
        "http-responses",
        str(resolved.get("provider") or "?"),
        str(request_meta["url"]),
    ]
    progress.record_cmd(cmd_meta)
    payload_bytes = json.dumps(request_meta["json"]).encode("utf-8")
    req = urllib.request.Request(
        str(request_meta["url"]),
        data=payload_bytes,
        headers=request_meta["headers"],
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status_code = int(getattr(resp, "status", 200))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ReviewflowSubprocessError(
            cmd=cmd_meta,
            cwd=repo_dir,
            exit_code=int(getattr(e, "code", 1) or 1),
            stdout="",
            stderr=body,
        ) from e
    except urllib.error.URLError as e:
        raise ReviewflowSubprocessError(
            cmd=cmd_meta,
            cwd=repo_dir,
            exit_code=1,
            stdout="",
            stderr=str(e),
        ) from e

    if _ACTIVE_OUTPUT is not None:
        try:
            _ACTIVE_OUTPUT.stream_sink("codex").write(body)
        except Exception:
            pass

    payload = _extract_json_object(body)
    if payload is None:
        raise ReviewflowError("HTTP llm provider returned non-JSON output.")
    text = _extract_http_response_output_text(payload)
    output_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    normalize_markdown_artifact(markdown_path=output_path, session_dir=repo_dir.parent)
    return LlmRunResult(
        resume=None,
        adapter_meta={
            "transport": "http-responses",
            "status_code": status_code,
            "url": request_meta["url"],
            "response_id": str(payload.get("id") or "").strip() or None,
        },
    )


def run_llm_exec(
    *,
    repo_dir: Path,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    output_path: Path,
    prompt: str,
    env: dict[str, str],
    stream: bool,
    progress: "SessionProgress",
    add_dirs: list[Path] | None = None,
    codex_config_overrides: list[str] | None = None,
    runtime_policy: dict[str, Any] | None = None,
) -> LlmRunResult:
    provider = str(resolved.get("provider") or "").strip().lower()
    if provider == "codex":
        codex_flags, _ = build_codex_flags_from_llm_config(resolved=resolved, resolution_meta=resolution_meta)
        policy = runtime_policy if isinstance(runtime_policy, dict) else {}
        codex_flags = list(policy.get("codex_flags") or codex_flags)
        codex_config_overrides = list(policy.get("codex_config_overrides") or codex_config_overrides or [])
        result = run_codex_exec(
            repo_dir=repo_dir,
            codex_flags=codex_flags,
            codex_config_overrides=codex_config_overrides,
            output_path=output_path,
            prompt=prompt,
            env=env,
            stream=stream,
            progress=progress,
            add_dirs=list(policy.get("add_dirs") or add_dirs or []),
            approval_policy=str(policy.get("approval_policy") or "never"),
            dangerously_bypass_approvals_and_sandbox=bool(
                policy.get("dangerously_bypass_approvals_and_sandbox", True)
            ),
            include_shell_environment_inherit_all=bool(
                policy.get("include_shell_environment_inherit_all", False)
            ),
        )
        resume = None
        if result.resume is not None:
            resume = LlmResumeInfo(
                provider="codex",
                session_id=result.resume.session_id,
                cwd=result.resume.cwd,
                command=result.resume.command,
            )
        return LlmRunResult(
            resume=resume,
            adapter_meta={"transport": "cli-codex", "flags": codex_flags},
        )
    if provider == "claude":
        return run_claude_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            env=env,
            progress=progress,
            runtime_policy=runtime_policy,
        )
    if provider == "gemini":
        return run_gemini_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            env=env,
            progress=progress,
            runtime_policy=runtime_policy,
        )
    if provider in HTTP_LLM_PROVIDERS:
        return run_http_response_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            output_path=output_path,
            prompt=prompt,
            progress=progress,
        )
    raise ReviewflowError(f"Unsupported llm provider: {provider!r}")


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
    - We intentionally disable any non-sandbox `chunk-hound` server from the base Codex config so
      review sessions stay scoped to the sandbox repo only.
    - Codex validates MCP transports even if `enabled=false`, so we must supply `command` and `args`.
    - ChunkHound must run in daemon mode (default): do NOT pass `--no-daemon`.
    """

    overrides: list[str] = []

    # Disable the existing non-sandbox MCP server while leaving Codex with a valid command/args pair.
    overrides.append(f"mcp_servers.chunk-hound.command={toml_string('chunkhound')}")
    overrides.append(f"mcp_servers.chunk-hound.args={json.dumps(['mcp', str(sandbox_repo_dir)])}")
    overrides.append("mcp_servers.chunk-hound.enabled=false")
    overrides.append("mcp_servers.chunk-hound.tool_timeout_sec=12000")

    if not enable_sandbox_chunkhound:
        return overrides

    ch_db = chunkhound_db_path or (sandbox_repo_dir / ".chunkhound.db")
    ch_cwd = chunkhound_cwd or sandbox_repo_dir
    ch_cfg = chunkhound_config_path or (ch_cwd / "chunkhound.json")
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
        f"mcp_servers.chunkhound.env_vars={json.dumps(['CHUNKHOUND_EMBEDDING__API_KEY', 'CHUNKHOUND_LLM_API_KEY', 'VOYAGE_API_KEY', 'OPENAI_API_KEY'])}"
    )
    overrides.append("mcp_servers.chunkhound.startup_timeout_sec=20")
    overrides.append("mcp_servers.chunkhound.tool_timeout_sec=12000")
    return overrides


def _require_provider_command(command: str, *, provider: str) -> str:
    name = str(command or provider).strip() or provider
    if shutil.which(name) is None:
        raise ReviewflowError(
            f"Required {provider} command not found on PATH: {name}. "
            "Install the provider CLI or choose a different llm preset."
        )
    return name


def _stage_review_auth_support(*, work_dir: Path, repo_dir: Path, env: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    staged_paths: dict[str, str] = {}
    gh_cfg = prepare_gh_config_for_codex(dst_root=work_dir)
    if gh_cfg:
        env["GH_CONFIG_DIR"] = str(gh_cfg)
        staged_paths["gh_config_dir"] = str(gh_cfg)
    jira_cfg = prepare_jira_config_for_codex(dst_root=work_dir)
    if jira_cfg:
        env["JIRA_CONFIG_FILE"] = str(jira_cfg)
        staged_paths["jira_config_file"] = str(jira_cfg)
    netrc = prepare_netrc_for_reviewflow(dst_root=work_dir)
    if netrc:
        env["NETRC"] = str(netrc)
        staged_paths["netrc"] = str(netrc)
    env["REVIEWFLOW_WORK_DIR"] = str(work_dir)
    staged_paths["reviewflow_work_dir"] = str(work_dir)
    rf_jira = write_rf_jira(repo_dir=repo_dir)
    staged_paths["rf_jira"] = str(rf_jira)
    return env, staged_paths


SENSITIVE_STAGED_PATH_KEYS = ("gh_config_dir", "jira_config_file", "netrc")


def cleanup_sensitive_staged_paths(staged_paths: dict[str, Any] | None) -> None:
    if not isinstance(staged_paths, dict):
        return
    for key in SENSITIVE_STAGED_PATH_KEYS:
        raw = str(staged_paths.get(key) or "").strip()
        if not raw:
            continue
        target = Path(raw)
        if key in {"jira_config_file", "netrc"}:
            target = target.parent
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
        except Exception:
            continue


def _reviewflow_chunkhound_mcp_entry(
    *,
    sandbox_repo_dir: Path,
    chunkhound_config_path: Path | None,
    chunkhound_db_path: Path | None,
    chunkhound_cwd: Path | None,
    trust: bool | None = None,
) -> dict[str, Any]:
    ch_db = chunkhound_db_path or (sandbox_repo_dir / ".chunkhound.db")
    ch_cwd = chunkhound_cwd or sandbox_repo_dir
    ch_cfg = chunkhound_config_path or (ch_cwd / "chunkhound.json")
    args = [
        "mcp",
        "--config",
        str(ch_cfg),
        str(sandbox_repo_dir),
    ]
    if chunkhound_config_path is None:
        args[3:3] = ["--database-provider", "duckdb", "--db", str(ch_db)]
    entry: dict[str, Any] = {
        "command": "chunkhound",
        "args": args,
        "cwd": str(ch_cwd),
    }
    if trust is not None:
        entry["trust"] = bool(trust)
    return entry


def _write_json_file(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return path


def _prepare_gemini_cli_home(*, work_dir: Path) -> tuple[Path, Path]:
    home_root = work_dir / "gemini_home"
    cli_dir = home_root / ".gemini"
    if home_root.exists():
        shutil.rmtree(home_root)
    cli_dir.mkdir(parents=True, exist_ok=True)
    src = real_user_home_dir() / ".gemini"
    if src.is_dir():
        shutil.copytree(src, cli_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    return home_root, cli_dir


def prepare_review_agent_runtime(
    *,
    args: argparse.Namespace,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    reviewflow_config_path: Path,
    config_enabled: bool,
    repo_dir: Path,
    session_dir: Path,
    work_dir: Path,
    base_env: dict[str, str],
    chunkhound_config_path: Path | None,
    chunkhound_db_path: Path | None,
    chunkhound_cwd: Path | None,
    enable_mcp: bool,
    interactive: bool,
    paths: ReviewflowPaths,
) -> dict[str, Any]:
    _ = paths
    transport = str(resolved.get("transport") or "").strip().lower()
    provider = str(resolved.get("provider") or "").strip().lower()
    profile, profile_source, runtime_cfg, runtime_meta = resolve_agent_runtime_profile(
        cli_value=getattr(args, "agent_runtime_profile", None),
        config_path=reviewflow_config_path,
        config_enabled=config_enabled,
    )
    env = build_curated_subprocess_env(extra_env=base_env)
    env.update(_string_dict(resolved.get("env")))
    env, staged_paths = _stage_review_auth_support(work_dir=work_dir, repo_dir=repo_dir, env=env)

    add_dirs = _dedupe_paths([session_dir, work_dir])
    runtime: dict[str, Any] = {
        "profile": profile,
        "profile_source": profile_source,
        "provider": provider,
        "transport": transport,
        "command": str(resolved.get("command") or provider).strip() or None,
        "env": env,
        "add_dirs": add_dirs,
        "staged_paths": staged_paths,
        "dangerously_bypass_approvals_and_sandbox": False,
        "dangerously_skip_permissions": False,
        "sandbox_mode": None,
        "approval_policy": None,
        "permission_mode": None,
        "approval_mode": None,
        "codex_flags": [],
        "codex_config_overrides": [],
        "provider_args": [],
        "config": {
            "resolved_profile": profile,
            "profile_source": profile_source,
            "agent_runtime": runtime_meta.get("agent_runtime"),
        },
    }

    if transport != "cli" or provider not in CLI_LLM_PROVIDERS:
        runtime["command"] = str(resolved.get("command") or "") or None
        runtime["metadata"] = {
            "profile": profile,
            "profile_source": profile_source,
            "provider": provider,
            "transport": transport,
            "supported": False,
            "detail": "agent runtime profiles apply only to CLI coding-agent providers",
            "env_keys": sorted(env.keys()),
            "add_dirs": [str(path) for path in add_dirs],
            "staged_paths": dict(staged_paths),
        }
        return runtime

    command = _require_provider_command(str(resolved.get("command") or provider), provider=provider)
    runtime["command"] = command

    if provider == "codex":
        codex_flags, _ = build_codex_flags_from_llm_config(
            resolved=resolved,
            resolution_meta=resolution_meta,
            include_sandbox=False,
        )
        if profile == "balanced":
            runtime["sandbox_mode"] = "workspace-write"
            runtime["approval_policy"] = "on-request" if interactive else "never"
        elif profile == "strict":
            runtime["sandbox_mode"] = "read-only"
            runtime["approval_policy"] = "on-request" if interactive else "never"
        elif profile == "permissive":
            runtime["dangerously_bypass_approvals_and_sandbox"] = True
        else:
            raise ReviewflowError(f"Unsupported codex agent runtime profile: {profile!r}")
        if runtime["sandbox_mode"]:
            codex_flags.extend(["--sandbox", str(runtime["sandbox_mode"])])
        if runtime["approval_policy"]:
            codex_flags.extend(["-a", str(runtime["approval_policy"])])
        runtime["codex_flags"] = codex_flags
        runtime["codex_config_overrides"] = codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=enable_mcp,
            sandbox_repo_dir=repo_dir,
            chunkhound_db_path=chunkhound_db_path,
            chunkhound_cwd=chunkhound_cwd,
            chunkhound_config_path=chunkhound_config_path,
            paths=paths,
        )
    elif provider == "claude":
        claude_dir = work_dir / "claude"
        settings_path = _write_json_file(claude_dir / "settings.json", {})
        runtime["staged_paths"]["claude_settings"] = str(settings_path)
        provider_args: list[str] = [
            "--setting-sources",
            "user",
            "--settings",
            str(settings_path),
        ]
        for add_dir in add_dirs:
            provider_args.extend(["--add-dir", str(add_dir)])
        if enable_mcp:
            mcp_path = _write_json_file(
                claude_dir / "mcp.json",
                {
                    "mcpServers": {
                        "reviewflow-chunkhound": _reviewflow_chunkhound_mcp_entry(
                            sandbox_repo_dir=repo_dir,
                            chunkhound_config_path=chunkhound_config_path,
                            chunkhound_db_path=chunkhound_db_path,
                            chunkhound_cwd=chunkhound_cwd,
                        )
                    }
                },
            )
            runtime["staged_paths"]["claude_mcp_config"] = str(mcp_path)
            provider_args.extend(["--mcp-config", str(mcp_path), "--strict-mcp-config"])
        if profile == "balanced":
            runtime["permission_mode"] = "default" if interactive else "dontAsk"
        elif profile == "strict":
            runtime["permission_mode"] = "plan"
        elif profile == "permissive":
            runtime["dangerously_skip_permissions"] = True
        else:
            raise ReviewflowError(f"Unsupported claude agent runtime profile: {profile!r}")
        if runtime["permission_mode"]:
            provider_args.extend(["--permission-mode", str(runtime["permission_mode"])])
        runtime["provider_args"] = provider_args
    elif provider == "gemini":
        gemini_cfg = runtime_cfg.get("gemini")
        gemini_cfg = gemini_cfg if isinstance(gemini_cfg, dict) else {}
        configured_sandbox = str(gemini_cfg.get("sandbox") or "").strip() or None
        seatbelt_profile = str(gemini_cfg.get("seatbelt_profile") or "").strip() or None
        if profile == "balanced":
            runtime["approval_mode"] = "auto_edit"
            env["GEMINI_SANDBOX"] = configured_sandbox or "true"
        elif profile == "strict":
            runtime["approval_mode"] = "plan"
            if not configured_sandbox:
                raise ReviewflowError(
                    "Gemini strict agent runtime requires [agent_runtime.gemini].sandbox to be configured."
                )
            env["GEMINI_SANDBOX"] = configured_sandbox
        elif profile == "permissive":
            runtime["approval_mode"] = "yolo"
            if configured_sandbox:
                env["GEMINI_SANDBOX"] = configured_sandbox
        else:
            raise ReviewflowError(f"Unsupported gemini agent runtime profile: {profile!r}")
        if seatbelt_profile:
            env["SEATBELT_PROFILE"] = seatbelt_profile

        home_root, cli_dir = _prepare_gemini_cli_home(work_dir=work_dir)
        trusted_folders_path = _write_json_file(
            cli_dir / "trustedFolders.json",
            {str(repo_dir.resolve(strict=False)): "TRUST_FOLDER"},
        )
        system_settings: dict[str, Any] = {}
        if enable_mcp:
            system_settings["mcpServers"] = {
                "reviewflow-chunkhound": _reviewflow_chunkhound_mcp_entry(
                    sandbox_repo_dir=repo_dir,
                    chunkhound_config_path=chunkhound_config_path,
                    chunkhound_db_path=chunkhound_db_path,
                    chunkhound_cwd=chunkhound_cwd,
                    trust=False,
                )
            }
            system_settings["mcp"] = {"allowed": ["reviewflow-chunkhound"]}
        system_settings_path = _write_json_file(work_dir / "gemini" / "system-settings.json", system_settings)
        env["GEMINI_CLI_HOME"] = str(home_root)
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(system_settings_path)
        runtime["staged_paths"]["gemini_home"] = str(home_root)
        runtime["staged_paths"]["gemini_trusted_folders"] = str(trusted_folders_path)
        runtime["staged_paths"]["gemini_system_settings"] = str(system_settings_path)
        provider_args = ["--output-format", "json", "--approval-mode", str(runtime["approval_mode"])]
        for add_dir in add_dirs:
            provider_args.extend(["--include-directories", str(add_dir)])
        runtime["provider_args"] = provider_args
    else:
        raise ReviewflowError(f"Unsupported CLI provider for agent runtime preparation: {provider!r}")

    runtime["metadata"] = {
        "profile": runtime["profile"],
        "profile_source": runtime["profile_source"],
        "provider": runtime["provider"],
        "sandbox_mode": runtime["sandbox_mode"],
        "approval_policy": runtime["approval_policy"],
        "permission_mode": runtime["permission_mode"],
        "approval_mode": runtime["approval_mode"],
        "dangerously_bypass_approvals_and_sandbox": bool(
            runtime["dangerously_bypass_approvals_and_sandbox"]
        ),
        "dangerously_skip_permissions": bool(runtime["dangerously_skip_permissions"]),
        "env_keys": sorted(env.keys()),
        "add_dirs": [str(path) for path in add_dirs],
        "staged_paths": dict(runtime["staged_paths"]),
    }
    return runtime
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
        write_redacted_json(self.meta_path, self.meta)

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
class LlmResumeInfo:
    provider: str
    session_id: str
    cwd: Path
    command: str


@dataclass(frozen=True)
class LlmRunResult:
    resume: LlmResumeInfo | None = None
    adapter_meta: dict[str, Any] = field(default_factory=dict)


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


def _codex_session_meta_is_subagent(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("forked_from_id") or "").strip():
        return True
    source = payload.get("source")
    return isinstance(source, dict) and isinstance(source.get("subagent"), dict)


def _resolve_top_level_codex_session_id(
    *, codex_root: Path, session_id: str, created_at: str | None, completed_at: str | None
) -> str:
    current = str(session_id or "").strip()
    if not current:
        return current

    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        session_log = _find_codex_session_log_by_id(
            codex_root=codex_root,
            session_id=current,
            created_at=created_at,
            completed_at=completed_at,
        )
        if session_log is None:
            return current
        payload = _load_codex_session_meta(session_log)
        if not payload:
            return current
        parent = str(payload.get("forked_from_id") or "").strip()
        if not parent:
            return current
        current = parent
    return current or str(session_id or "").strip()


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
    approval_policy: str | None = None,
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
) -> str:
    assignments: list[str] = []
    has_explicit_approval_flag = any(flag in {"-a", "--ask-for-approval"} for flag in codex_flags)
    for key in (
        "GH_CONFIG_DIR",
        "JIRA_CONFIG_FILE",
        "NETRC",
        "REVIEWFLOW_WORK_DIR",
    ):
        value = str(env.get(key) or "").strip()
        if value:
            assignments.append(f"{key}={shlex.quote(value)}")

    resume_cmd: list[str] = [
        "codex",
        "resume",
        "--add-dir",
        "/tmp",
    ]
    if approval_policy and (not dangerously_bypass_approvals_and_sandbox) and (not has_explicit_approval_flag):
        resume_cmd.extend(["-a", approval_policy])
    resume_cmd.extend(codex_flags)
    for override in codex_config_overrides or []:
        resume_cmd.extend(["-c", override])
    if include_shell_environment_inherit_all:
        resume_cmd.extend(["-c", "shell_environment_policy.inherit=all"])
    if dangerously_bypass_approvals_and_sandbox:
        resume_cmd.append("--dangerously-bypass-approvals-and-sandbox")
    resume_cmd.append(session_id)

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
    approval_policy: str | None = None,
    dangerously_bypass_approvals_and_sandbox: bool = True,
    include_shell_environment_inherit_all: bool = True,
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
        if _codex_session_meta_is_subagent(payload):
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
                approval_policy=approval_policy,
                dangerously_bypass_approvals_and_sandbox=dangerously_bypass_approvals_and_sandbox,
                include_shell_environment_inherit_all=include_shell_environment_inherit_all,
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


def llm_resume_meta_dict(info: LlmResumeInfo | None) -> dict[str, str] | None:
    if info is None:
        return None
    return {
        "provider": str(info.provider),
        "session_id": info.session_id,
        "cwd": str(info.cwd),
        "command": info.command,
    }


def record_llm_resume(container: dict[str, Any], info: LlmResumeInfo | None) -> str | None:
    payload = llm_resume_meta_dict(info)
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
    """Resolve `cure resume <target>` into (session_id, action).

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
                f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id. Got: {raw!r}"
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
            f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id."
        )

    if completed:
        return (completed[0][1], "followup")

    raise ReviewflowError(
        f"No sessions found for PR {pr.owner}/{pr.repo}#{pr.number} under {root}. "
        f"Tip: run `{PRIMARY_CLI_COMMAND} list`."
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


@dataclass(frozen=True)
class ResolvedObservationTarget:
    requested_target: dict[str, Any]
    resolved_target: dict[str, Any]
    resolution_strategy: str
    session_id: str
    session_dir: Path
    meta_path: Path
    meta: dict[str, Any]


def _resolve_session_id_target(raw: str, *, sandbox_root: Path, command_name: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ReviewflowError(f"{command_name} requires a session_id or PR URL.")
    if Path(text).is_absolute() or ("/" in text) or ("\\" in text):
        raise ReviewflowError(
            f"{command_name} expects a session id (folder name) or a PR URL. "
            f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id. Got: {text!r}"
        )
    return text


def _load_session_meta_strict(meta_path: Path, *, command_name: str) -> dict[str, Any]:
    if not meta_path.is_file():
        raise ReviewflowError(f"{command_name}: missing meta.json at {meta_path}")
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReviewflowError(f"{command_name}: failed to parse meta.json at {meta_path}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"{command_name}: meta.json must contain a JSON object: {meta_path}")
    return payload


def _meta_matches_pr(*, meta: dict[str, Any], pr: PullRequestRef) -> bool:
    if str(meta.get("host") or "").strip() != pr.host:
        return False
    if str(meta.get("owner") or "").strip() != pr.owner:
        return False
    if str(meta.get("repo") or "").strip() != pr.repo:
        return False
    try:
        return int(meta.get("number") or 0) == int(pr.number)
    except Exception:
        return False


def _observation_activity_dt(meta: dict[str, Any]) -> datetime:
    return (
        _parse_iso_dt(str(meta.get("resumed_at") or "").strip())
        or _parse_iso_dt(str(meta.get("created_at") or "").strip())
        or datetime(1970, 1, 1, tzinfo=timezone.utc)
    )


def resolve_observation_target(
    target: str,
    *,
    sandbox_root: Path,
    command_name: str,
) -> ResolvedObservationTarget:
    raw = str(target or "").strip()
    if not raw:
        raise ReviewflowError(f"{command_name} requires a session_id or PR URL.")

    pr: PullRequestRef | None = None
    try:
        pr = parse_pr_url(raw)
    except ReviewflowError:
        pr = None

    if pr is None:
        session_id = _resolve_session_id_target(raw, sandbox_root=sandbox_root, command_name=command_name)
        session_dir = sandbox_root / session_id
        if not session_dir.is_dir():
            raise ReviewflowError(f"{command_name}: session not found under {sandbox_root}: {session_id}")
        meta_path = session_dir / "meta.json"
        meta = _load_session_meta_strict(meta_path, command_name=command_name)
        host = str(meta.get("host") or "").strip() or "github.com"
        owner = str(meta.get("owner") or "").strip()
        repo = str(meta.get("repo") or "").strip()
        number_raw = meta.get("number")
        try:
            number = int(number_raw or 0)
        except Exception:
            number = 0
        pr_url = f"https://{host}/{owner}/{repo}/pull/{number}" if owner and repo and number > 0 else None
        return ResolvedObservationTarget(
            requested_target={"raw": raw, "kind": "session_id"},
            resolved_target={
                "kind": "session",
                "session_id": session_id,
                "session_dir": str(session_dir),
                "pr_url": pr_url,
            },
            resolution_strategy="exact_session_id",
            session_id=session_id,
            session_dir=session_dir,
            meta_path=meta_path,
            meta=meta,
        )

    if not sandbox_root.is_dir():
        raise ReviewflowError(
            f"No review sandboxes found under {sandbox_root} (needed to resolve PR {pr.owner}/{pr.repo}#{pr.number})."
        )

    running: list[tuple[datetime, Path, dict[str, Any]]] = []
    others: list[tuple[datetime, Path, dict[str, Any]]] = []
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta = _load_session_meta(entry / "meta.json")
        if not meta or (not _meta_matches_pr(meta=meta, pr=pr)):
            continue
        status = str(meta.get("status") or "").strip().lower()
        activity_dt = _observation_activity_dt(meta)
        if status == "running":
            running.append((activity_dt, entry, meta))
        else:
            others.append((activity_dt, entry, meta))

    strategy = ""
    selected: tuple[datetime, Path, dict[str, Any]] | None = None
    if running:
        running.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected = running[0]
        strategy = "newest_running"
    elif others:
        others.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected = others[0]
        strategy = "newest_activity"

    if selected is None:
        raise ReviewflowError(
            f"No sessions found for PR {pr.owner}/{pr.repo}#{pr.number} under {sandbox_root}. "
            f"Tip: run `{PRIMARY_CLI_COMMAND} list`."
        )

    _, session_dir, meta = selected
    session_id = str(meta.get("session_id") or session_dir.name).strip() or session_dir.name
    meta_path = session_dir / "meta.json"
    pr_url = f"https://{pr.host}/{pr.owner}/{pr.repo}/pull/{pr.number}"
    return ResolvedObservationTarget(
        requested_target={
            "raw": raw,
            "kind": "pr_url",
            "host": pr.host,
            "owner": pr.owner,
            "repo": pr.repo,
            "number": pr.number,
            "pr_url": pr_url,
        },
        resolved_target={
            "kind": "session",
            "session_id": session_id,
            "session_dir": str(session_dir),
            "pr_url": pr_url,
        },
        resolution_strategy=strategy,
        session_id=session_id,
        session_dir=session_dir,
        meta_path=meta_path,
        meta=meta,
    )


def _resolve_session_work_dir(*, session_dir: Path, meta: dict[str, Any]) -> Path:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw = str((meta_paths or {}).get("work_dir") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = (session_dir / path).resolve()
        else:
            path = path.resolve()
        return path
    return session_dir / "work"


def _resolve_session_logs_dir(*, session_dir: Path, meta: dict[str, Any], work_dir: Path) -> Path:
    meta_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    raw = str((meta_paths or {}).get("logs_dir") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = (session_dir / path).resolve()
        else:
            path = path.resolve()
        return path
    logs = meta.get("logs") if isinstance(meta.get("logs"), dict) else {}
    for key in ("reviewflow", "chunkhound", "codex"):
        candidate = _resolve_log_path(session_dir=session_dir, raw=str(logs.get(key) or "").strip())
        if candidate is not None:
            return candidate.parent
    return work_dir / "logs"


def _resolve_session_log_paths(*, session_dir: Path, meta: dict[str, Any], logs_dir: Path) -> dict[str, str]:
    logs = meta.get("logs") if isinstance(meta.get("logs"), dict) else {}
    payload: dict[str, str] = {}
    for key in ("reviewflow", "chunkhound", "codex"):
        candidate = _resolve_log_path(session_dir=session_dir, raw=str(logs.get(key) or "").strip())
        if candidate is None:
            fallback = logs_dir / f"{key}.log"
            candidate = fallback if fallback.exists() else None
        if candidate is not None:
            payload[key] = str(candidate)
    return payload


def build_status_payload(
    target: str,
    *,
    sandbox_root: Path,
    command_name: str = "status",
) -> dict[str, Any]:
    resolved = resolve_observation_target(target, sandbox_root=sandbox_root, command_name=command_name)
    meta = _load_session_meta_strict(resolved.meta_path, command_name=command_name)
    session_dir = resolved.session_dir
    work_dir = _resolve_session_work_dir(session_dir=session_dir, meta=meta)
    logs_dir = _resolve_session_logs_dir(session_dir=session_dir, meta=meta, work_dir=work_dir)
    logs = _resolve_session_log_paths(session_dir=session_dir, meta=meta, logs_dir=logs_dir)
    review_md_path = _resolve_session_review_md_path(session_dir=session_dir, meta=meta)
    repo_dir_raw = str(
        ((meta.get("paths") or {}).get("repo_dir") if isinstance(meta.get("paths"), dict) else "")
        or (session_dir / "repo")
    ).strip()
    repo_dir = Path(repo_dir_raw)
    if not repo_dir.is_absolute():
        repo_dir = (session_dir / repo_dir).resolve()
    else:
        repo_dir = repo_dir.resolve()

    latest_artifact: dict[str, Any] | None = None
    if review_md_path is not None:
        latest_artifact_path = _resolve_latest_session_artifact_path(
            session_dir=session_dir,
            meta=meta,
            review_md_path=review_md_path,
        )
        latest_artifact = {"path": str(latest_artifact_path)}

    llm_meta = resolve_meta_llm(meta)
    llm_payload: dict[str, Any] | None = None
    if isinstance(llm_meta, dict) and llm_meta:
        llm_payload = dict(llm_meta)
        llm_payload["summary"] = resolve_codex_summary(meta)

    agent_runtime = meta.get("agent_runtime") if isinstance(meta.get("agent_runtime"), dict) else None
    agent_runtime_payload: dict[str, Any] | None = None
    if agent_runtime:
        agent_runtime_payload = dict(agent_runtime)
        profile = str(agent_runtime_payload.get("profile") or "").strip()
        provider = str(agent_runtime_payload.get("provider") or "").strip()
        if profile or provider:
            agent_runtime_payload["summary"] = "/".join(part for part in (profile, provider) if part)

    host = str(meta.get("host") or "").strip() or "github.com"
    owner = str(meta.get("owner") or "").strip()
    repo = str(meta.get("repo") or "").strip()
    number_raw = meta.get("number")
    try:
        number = int(number_raw or 0)
    except Exception:
        number = 0
    pr_url = f"https://{host}/{owner}/{repo}/pull/{number}" if owner and repo and number > 0 else None

    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reviewflow.status",
        "requested_target": resolved.requested_target,
        "resolved_target": resolved.resolved_target,
        "resolution_strategy": resolved.resolution_strategy,
        "session_id": resolved.session_id,
        "status": str(meta.get("status") or "").strip() or "unknown",
        "phase": str(meta.get("phase") or "").strip() or "unknown",
        "phases": meta.get("phases") if isinstance(meta.get("phases"), dict) else {},
        "pr": {
            "host": host,
            "owner": owner,
            "repo": repo,
            "number": number,
            "pr_url": pr_url,
        },
        "paths": {
            "session_dir": str(session_dir),
            "repo_dir": str(repo_dir),
            "work_dir": str(work_dir),
            "logs_dir": str(logs_dir),
            "review_md": (str(review_md_path) if review_md_path is not None else None),
            "meta_json": str(resolved.meta_path),
        },
        "logs": logs,
    }
    if latest_artifact is not None:
        payload["latest_artifact"] = latest_artifact
    if llm_payload is not None:
        payload["llm"] = llm_payload
    if agent_runtime_payload is not None:
        payload["agent_runtime"] = agent_runtime_payload
    if isinstance(meta.get("error"), dict):
        payload["error"] = meta.get("error")
        payload["terminal_error"] = meta.get("error")
    return payload


def _coerce_ui_verbosity(raw: str) -> Verbosity:
    try:
        return Verbosity(str(raw or "normal").strip().lower())
    except Exception as e:
        raise ReviewflowError("--verbosity must be one of: quiet, normal, debug") from e


def _stream_supports_color(stream: TextIO) -> bool:
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


def _load_ui_preview_snapshot(
    *,
    meta_path: Path,
    session_dir: Path,
    verbosity: Verbosity,
) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReviewflowError(f"ui-preview: failed to parse meta.json: {e}") from e
    if not isinstance(meta, dict):
        raise ReviewflowError("ui-preview: meta.json must contain a JSON object")

    if verbosity is Verbosity.quiet:
        ch_n, cx_n = (0, 0)
    else:
        ch_n, cx_n = (200, 400)

    fallback_ch = session_dir / "work" / "logs" / "chunkhound.log"
    fallback_cx = session_dir / "work" / "logs" / "codex.log"
    logs = meta.get("logs")
    logs = logs if isinstance(logs, dict) else {}
    ch_log = _resolve_log_path(session_dir=session_dir, raw=str(logs.get("chunkhound") or "").strip())
    cx_log = _resolve_log_path(session_dir=session_dir, raw=str(logs.get("codex") or "").strip())
    if ch_log is None or (not ch_log.is_file()):
        ch_log = fallback_ch if fallback_ch.is_file() else None
    if cx_log is None or (not cx_log.is_file()):
        cx_log = fallback_cx if fallback_cx.is_file() else None

    chunkhound_tail = _tail_file_lines(ch_log, ch_n) if ch_log is not None else []
    codex_tail = _tail_file_lines(cx_log, cx_n) if cx_log is not None else []
    return meta, chunkhound_tail, codex_tail


def _render_ui_preview(
    *,
    session_dir: Path,
    meta_path: Path,
    verbosity: Verbosity,
    color: bool,
    width: int | None,
    height: int | None,
    final_newline: bool,
    stdout: TextIO,
) -> str:
    meta, chunkhound_tail, codex_tail = _load_ui_preview_snapshot(
        meta_path=meta_path,
        session_dir=session_dir,
        verbosity=verbosity,
    )
    snap = UiSnapshot(verbosity=verbosity, show_help=False)
    term = shutil.get_terminal_size(fallback=(120, 40))
    render_width = int(width) if isinstance(width, int) else int(term.columns)
    render_height = int(height) if isinstance(height, int) else int(term.lines)
    lines = build_dashboard_lines(
        meta=meta,
        snapshot=snap,
        chunkhound_tail=chunkhound_tail,
        codex_tail=codex_tail,
        no_stream=False,
        width=render_width,
        height=render_height,
        color=color,
    )
    stdout.write("\n".join(lines))
    if final_newline:
        stdout.write("\n")
    stdout.flush()
    return str(meta.get("status") or "").strip().lower() or "unknown"


def _watch_line_for_payload(payload: dict[str, Any]) -> str:
    pr = payload.get("pr") if isinstance(payload.get("pr"), dict) else {}
    repo_slug = f"{pr.get('owner')}/{pr.get('repo')}#{pr.get('number')}"
    parts = [
        f"session={payload.get('session_id')}",
        f"repo={repo_slug}",
        f"status={payload.get('status')}",
        f"phase={payload.get('phase')}",
    ]
    latest_artifact = payload.get("latest_artifact") if isinstance(payload.get("latest_artifact"), dict) else {}
    latest_path = str((latest_artifact or {}).get("path") or "").strip()
    if latest_path:
        parts.append(f"artifact={latest_path}")
    llm = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
    llm_summary = str((llm or {}).get("summary") or "").strip()
    if llm_summary:
        parts.append(llm_summary)
    return " ".join(parts)


def preferred_cli_invocation(invocation: str) -> str:
    return f"{PRIMARY_CLI_COMMAND} {invocation}"


def deprecated_cli_invocation(invocation: str) -> str:
    return f"{DEPRECATED_CLI_ALIAS} {invocation}"


def deprecated_alias_variant(invocation: str) -> dict[str, str]:
    return {
        "name": "deprecated_alias",
        "summary": "Temporary one-release alias; prints a deprecation warning on stderr.",
        "invocation": deprecated_cli_invocation(invocation),
    }


def build_commands_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "reviewflow.commands",
        "commands": [
            {
                "name": "pr",
                "summary": "Create a new review session for a PR.",
                "targets": ["PR_URL"],
                "safety": "Use `--if-reviewed new` for stable agent-safe start semantics.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Prints the created session directory path on success.",
                "exit_codes": {"0": "review started", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("pr <PR_URL> --if-reviewed new"),
                "variants": [
                    {
                        "name": "compatibility",
                        "summary": "Bare `pr` keeps current prompt-or-new compatibility behavior.",
                        "invocation": preferred_cli_invocation("pr <PR_URL>"),
                    },
                    deprecated_alias_variant("pr <PR_URL>"),
                ],
            },
            {
                "name": "followup",
                "summary": "Run a follow-up review inside an existing session sandbox.",
                "targets": ["session_id"],
                "safety": "Reuses the existing sandbox and appends a new follow-up artifact.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Human-readable progress only; follow-up artifact path is not a stable stdout contract.",
                "exit_codes": {"0": "follow-up completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("followup <session_id>"),
                "variants": [deprecated_alias_variant("followup <session_id>")],
            },
            {
                "name": "resume",
                "summary": "Resume a multipass session, or use its existing PR URL compatibility behavior.",
                "targets": ["session_id", "PR_URL"],
                "safety": "PR URL mode keeps its special resume-or-followup behavior for compatibility.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Human-readable progress only.",
                "exit_codes": {"0": "resume or compatible follow-up completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("resume <session_id>"),
                "variants": [
                    {
                        "name": "pr_url_compatibility",
                        "summary": "PR URL mode preserves the existing special behavior documented in the README.",
                        "invocation": preferred_cli_invocation("resume <PR_URL>"),
                    },
                    deprecated_alias_variant("resume <session_id>"),
                ],
            },
            {
                "name": "zip",
                "summary": "Synthesize a final arbiter review for the PR's current HEAD.",
                "targets": ["PR_URL"],
                "safety": "Reads existing review artifacts; does not create a new sandbox.",
                "tty": "Optional TUI on stderr when running in a real terminal.",
                "stdout": "Prints the generated zip markdown path on success.",
                "exit_codes": {"0": "zip completed", "2": "usage or runtime error"},
                "recommended_invocation": preferred_cli_invocation("zip <PR_URL>"),
                "variants": [deprecated_alias_variant("zip <PR_URL>")],
            },
            {
                "name": "clean",
                "summary": "Delete an exact session, preview closed-session cleanup, or use the TTY cleaner.",
                "targets": ["session_id", "closed"],
                "safety": "Bulk cleanup is preview-first with `clean closed --json`; exact delete rejects `--yes`.",
                "tty": "Required only for `clean` with no target and `clean closed` without `--yes`.",
                "stdout": "Structured JSON on `--json`; otherwise human-readable cleanup output.",
                "exit_codes": {"0": "cleanup query or deletion completed", "2": "usage, lookup, or runtime error"},
                "recommended_invocation": preferred_cli_invocation("clean closed --json"),
                "variants": [
                    {
                        "name": "bulk_execute",
                        "summary": "Execute closed-session cleanup after previewing matches.",
                        "invocation": preferred_cli_invocation("clean closed --yes --json"),
                    },
                    {
                        "name": "exact_delete",
                        "summary": "Delete one exact session with a structured result.",
                        "invocation": preferred_cli_invocation("clean <session_id> --json"),
                    },
                    deprecated_alias_variant("clean <session_id>"),
                ],
            },
            {
                "name": "status",
                "summary": "Resolve a session or PR URL and report the current recorded run state.",
                "targets": ["session_id", "PR_URL"],
                "safety": "Read-only view backed by `meta.json` and recorded artifacts/logs.",
                "tty": "No TTY required.",
                "stdout": "Human-readable single-line status by default, structured JSON with `--json`.",
                "exit_codes": {"0": "target resolved", "2": "invalid target, lookup failure, or corrupt metadata"},
                "recommended_invocation": preferred_cli_invocation("status <session_id|PR_URL> --json"),
                "variants": [deprecated_alias_variant("status <session_id|PR_URL>")],
            },
            {
                "name": "watch",
                "summary": "Attach to a recorded session and follow progress until completion.",
                "targets": ["session_id", "PR_URL"],
                "safety": "Read-only attach flow; uses the same resolver as `status`.",
                "tty": "TTY mode reuses the existing dashboard; non-TTY mode prints plain polling lines.",
                "stdout": "Progress lines until the session reaches `done` or `error`.",
                "exit_codes": {
                    "0": "session finished with status=done",
                    "1": "session finished with status=error",
                    "2": "invalid target, lookup failure, or corrupt metadata",
                },
                "recommended_invocation": preferred_cli_invocation("watch <session_id|PR_URL>"),
                "variants": [deprecated_alias_variant("watch <session_id|PR_URL>")],
            },
        ],
    }


def commands_flow(args: argparse.Namespace, *, stdout: TextIO | None = None) -> int:
    out = stdout or sys.stdout
    payload = build_commands_catalog_payload()
    if bool(getattr(args, "json_output", False)):
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
        return 0
    for command in payload["commands"]:
        print(f"{command['name']}: {command['summary']}", file=out)
        print(f"  {command['recommended_invocation']}", file=out)
        for variant in command.get("variants", []):
            if isinstance(variant, dict) and str(variant.get("invocation") or "").strip():
                print(f"    {variant['name']}: {variant['invocation']}", file=out)
    return 0


def status_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdout: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    payload = build_status_payload(str(getattr(args, "target", "") or ""), sandbox_root=paths.sandbox_root)
    if bool(getattr(args, "json_output", False)):
        print(json.dumps(payload, indent=2, sort_keys=True), file=out)
        return 0
    print(
        _watch_line_for_payload(payload),
        file=out,
    )
    return 0


def watch_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    target = str(getattr(args, "target", "") or "")
    resolved = resolve_observation_target(target, sandbox_root=paths.sandbox_root, command_name="watch")
    interval = max(0.0, float(getattr(args, "interval", 2.0) or 0.0))
    verbosity = _coerce_ui_verbosity(str(getattr(args, "verbosity", "normal") or "normal"))

    try:
        is_tty = bool(out.isatty()) and bool(err.isatty())
    except Exception:
        is_tty = False

    if is_tty:
        color = _stream_supports_color(out) and (not bool(getattr(args, "no_color", False)))
        while True:
            out.write("\x1b[2J\x1b[H")
            out.flush()
            status = _render_ui_preview(
                session_dir=resolved.session_dir,
                meta_path=resolved.meta_path,
                verbosity=verbosity,
                color=color,
                width=None,
                height=None,
                final_newline=False,
                stdout=out,
            )
            if status in {"done", "error"}:
                return 0 if status == "done" else 1
            time.sleep(interval if interval > 0 else 0.2)

    last_line = None
    while True:
        payload = build_status_payload(resolved.session_id, sandbox_root=paths.sandbox_root, command_name="watch")
        line = _watch_line_for_payload(payload)
        if line != last_line:
            print(line, file=out)
            out.flush()
            last_line = line
        status = str(payload.get("status") or "").strip().lower()
        if status in {"done", "error"}:
            return 0 if status == "done" else 1
        time.sleep(interval if interval > 0 else 0.2)


def ui_preview_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    session_id = str(getattr(args, "session_id", "") or "").strip()
    if not session_id:
        raise ReviewflowError("ui-preview: session_id is required")

    session_dir = paths.sandbox_root / session_id
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise ReviewflowError(f"ui-preview: missing meta.json at {meta_path}")

    verbosity = _coerce_ui_verbosity(str(getattr(args, "verbosity", "normal") or "normal"))
    width_arg = getattr(args, "width", None)
    height_arg = getattr(args, "height", None)
    color = _stream_supports_color(sys.stdout) and (not bool(getattr(args, "no_color", False)))

    watch = bool(getattr(args, "watch", False))
    if not watch:
        # If the command line wrapped, some terminals start program output at a non-zero
        # column; add a leading newline in TTY mode to keep the dashboard aligned.
        try:
            if sys.stdout.isatty():
                sys.stdout.write("\n")
        except Exception:
            pass
        _render_ui_preview(
            session_dir=session_dir,
            meta_path=meta_path,
            verbosity=verbosity,
            color=color,
            width=width_arg,
            height=height_arg,
            final_newline=True,
            stdout=sys.stdout,
        )
        return 0

    try:
        while True:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            _render_ui_preview(
                session_dir=session_dir,
                meta_path=meta_path,
                verbosity=verbosity,
                color=color,
                width=width_arg,
                height=height_arg,
                final_newline=False,
                stdout=sys.stdout,
            )
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


def prompt_template_name_for_profile(profile: str) -> str:
    if profile == "normal":
        return "mrereview_gh_local.md"
    if profile == "big":
        return "mrereview_gh_local_big.md"
    if profile == "default":
        return "default.md"
    raise ReviewflowError(f"Unknown prompt profile: {profile}")


def followup_prompt_template_name_for_profile(profile: str) -> str:
    if profile == "big":
        return "mrereview_gh_local_big_followup.md"
    return "mrereview_gh_local_followup.md"


def review_intelligence_prompt_vars(cfg: ReviewIntelligenceConfig) -> dict[str, str]:
    return {"REVIEW_INTELLIGENCE_GUIDANCE": build_review_intelligence_guidance(cfg)}


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
    review_intelligence_guidance: str | None = None
    if extra_vars:
        for k, v in extra_vars.items():
            key = str(k).strip()
            if not key:
                continue
            if key == "REVIEW_INTELLIGENCE_GUIDANCE":
                review_intelligence_guidance = str(v)
                continue
            text = text.replace(f"${key}", str(v)).replace(f"${{{key}}}", str(v))
    if review_intelligence_guidance is not None:
        text = text.replace("$REVIEW_INTELLIGENCE_GUIDANCE", review_intelligence_guidance).replace(
            "${REVIEW_INTELLIGENCE_GUIDANCE}", review_intelligence_guidance
        )
    # Replace AGENT_DESC last to avoid mutating its contents if it contains `$FOO`.
    text = text.replace("$AGENT_DESC", agent_desc).replace("${AGENT_DESC}", agent_desc)
    return text


@dataclass(frozen=True)
class ReviewVerdicts:
    business: str | None
    technical: str | None

    def is_empty(self) -> bool:
        return not (self.business or self.technical)


_DECISION_LINE_RE = re.compile("(?im)^\\s*\\*\\*Decision\\*\\*:\\s*(.+?)\\s*$")
_VERDICT_LINE_RE = re.compile("(?im)^\\s*\\*\\*Verdict\\*\\*:\\s*(.+?)\\s*$")
_SECTION_HEADING_RE = re.compile("(?im)^\\s{0,3}#{1,6}\\s+.+?\\s*$")
_BUSINESS_SECTION_RE = re.compile(
    "(?im)^\\s{0,3}#{1,6}\\s+Business\\s*/\\s*Product\\s+Assessment\\s*$"
)
_TECHNICAL_SECTION_RE = re.compile("(?im)^\\s{0,3}#{1,6}\\s+Technical\\s+Assessment\\s*$")


def normalize_review_verdict(raw: object) -> str | None:
    verdict = str(raw or "").strip()
    if not verdict:
        return None
    verdict = verdict.strip("[]").strip()
    verdict = re.sub("^\\*+|\\*+$", "", verdict).strip()
    if verdict.startswith("`") and verdict.endswith("`") and len(verdict) >= 2:
        verdict = verdict[1:-1].strip()
    verdict = re.sub(r"\\s+", " ", verdict).strip()
    if not verdict:
        return None
    upper = verdict.upper()
    if upper in {"APPROVE", "REJECT"}:
        return upper
    if upper in {"REQUEST CHANGES", "REQUEST_CHANGES"}:
        return "REQUEST CHANGES"
    return verdict


def _extract_markdown_section(text: str, *, heading_re: re.Pattern[str]) -> str | None:
    match = heading_re.search(text or "")
    if match is None:
        return None
    start = match.end()
    next_heading = _SECTION_HEADING_RE.search(text or "", start)
    end = next_heading.start() if next_heading is not None else len(text or "")
    return (text or "")[start:end]


def extract_decision_from_markdown(text: str) -> str | None:
    matches = _DECISION_LINE_RE.findall(text or "")
    if not matches:
        return None
    for raw in reversed(matches):
        decision = normalize_review_verdict(raw)
        if decision:
            return decision
    return None


def normalize_review_verdicts(raw: object) -> ReviewVerdicts | None:
    if isinstance(raw, ReviewVerdicts):
        verdicts = ReviewVerdicts(
            business=normalize_review_verdict(raw.business),
            technical=normalize_review_verdict(raw.technical),
        )
        return None if verdicts.is_empty() else verdicts
    if not isinstance(raw, dict):
        return None
    verdicts = ReviewVerdicts(
        business=normalize_review_verdict(raw.get("business")),
        technical=normalize_review_verdict(raw.get("technical")),
    )
    return None if verdicts.is_empty() else verdicts


def review_verdicts_to_meta(verdicts: ReviewVerdicts) -> dict[str, str | None]:
    return {"business": verdicts.business, "technical": verdicts.technical}


def extract_review_verdicts_from_markdown(text: str) -> ReviewVerdicts | None:
    business_section = _extract_markdown_section(text, heading_re=_BUSINESS_SECTION_RE)
    technical_section = _extract_markdown_section(text, heading_re=_TECHNICAL_SECTION_RE)

    business = None
    technical = None
    if business_section is not None:
        match = _VERDICT_LINE_RE.search(business_section)
        if match is not None:
            business = normalize_review_verdict(match.group(1))
    if technical_section is not None:
        match = _VERDICT_LINE_RE.search(technical_section)
        if match is not None:
            technical = normalize_review_verdict(match.group(1))

    verdicts = ReviewVerdicts(business=business, technical=technical)
    if not verdicts.is_empty():
        return verdicts

    legacy = extract_decision_from_markdown(text)
    if legacy is None:
        return None
    return ReviewVerdicts(business=legacy, technical=legacy)


def format_review_verdicts_compact(verdicts: ReviewVerdicts | None) -> str:
    if verdicts is None:
        return "biz=? tech=?"
    return f"biz={verdicts.business or '?'} tech={verdicts.technical or '?'}"


def _parse_codex_flag_assignment(raw: object, *, key: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    prefix = f"{key}="
    if not text.startswith(prefix):
        return None
    value = text[len(prefix) :].strip()
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    value = value.strip()
    return value or None


def _legacy_llm_meta_from_codex(meta: dict[str, Any]) -> dict[str, Any]:
    codex = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
    cfg = codex.get("config") if isinstance(codex.get("config"), dict) else {}
    resolved = cfg.get("resolved") if isinstance(cfg.get("resolved"), dict) else {}

    model = str(resolved.get("model") or "").strip() or None
    effort = str(resolved.get("model_reasoning_effort") or "").strip() or None
    plan_effort = str(resolved.get("plan_mode_reasoning_effort") or "").strip() or None

    flags = codex.get("flags")
    if isinstance(flags, list):
        flag_items = [str(item) for item in flags if isinstance(item, str)]
        for idx, item in enumerate(flag_items):
            if model is None and item == "-m" and idx + 1 < len(flag_items):
                candidate = str(flag_items[idx + 1]).strip()
                if candidate:
                    model = candidate
            if item != "-c" or idx + 1 >= len(flag_items):
                continue
            assignment = flag_items[idx + 1]
            if effort is None:
                effort = _parse_codex_flag_assignment(assignment, key="model_reasoning_effort")
            if plan_effort is None:
                plan_effort = _parse_codex_flag_assignment(
                    assignment, key="plan_mode_reasoning_effort"
                )

    resume = codex.get("resume") if isinstance(codex.get("resume"), dict) else {}
    return {
        "preset": DEFAULT_LEGACY_CODEX_PRESET,
        "transport": "cli",
        "provider": "codex",
        "model": model,
        "reasoning_effort": effort,
        "plan_reasoning_effort": plan_effort,
        "resume": resume,
        "capabilities": {"supports_resume": bool(resume.get("command"))},
    }


def resolve_meta_llm(meta: dict[str, Any]) -> dict[str, Any]:
    llm = meta.get("llm") if isinstance(meta.get("llm"), dict) else {}
    if llm:
        out = dict(llm)
        out["capabilities"] = (
            dict(out.get("capabilities"))
            if isinstance(out.get("capabilities"), dict)
            else {"supports_resume": False}
        )
        return out
    return _legacy_llm_meta_from_codex(meta)


def resolve_codex_summary(meta: dict[str, Any]) -> str:
    llm = resolve_meta_llm(meta)
    preset = str(llm.get("preset") or DEFAULT_LEGACY_CODEX_PRESET).strip() or DEFAULT_LEGACY_CODEX_PRESET
    model = str(llm.get("model") or "").strip() or None
    effort = str(llm.get("reasoning_effort") or "").strip() or None
    plan_effort = str(llm.get("plan_reasoning_effort") or "").strip() or None
    thinking = effort or plan_effort
    if model and thinking:
        return f"llm={preset}/{model}/{thinking}"
    if model:
        return f"llm={preset}/{model}/?"
    if thinking:
        return f"llm={preset}/?/{thinking}"
    return f"llm={preset}/?"


def review_verdicts_include_reject(verdicts: ReviewVerdicts | None) -> bool:
    if verdicts is None:
        return False
    return verdicts.business == "REJECT" or verdicts.technical == "REJECT"


def build_abort_review_markdown(*, reason: str, include_steps_taken: bool = False) -> str:
    lines: list[str] = []
    if include_steps_taken:
        lines.extend(["### Steps taken", "- Multipass plan aborted", ""])
    lines.extend(
        [
            f"**Summary**: ABORT: {reason}",
            "",
            "## Business / Product Assessment",
            "**Verdict**: REJECT",
            "",
            "### Strengths",
            "- None.",
            "",
            "### In Scope Issues",
            f"- ABORT: {reason}",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            "**Verdict**: REJECT",
            "",
            "### Strengths",
            "- None.",
            "",
            "### In Scope Issues",
            f"- ABORT: {reason}",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "### Reusability",
            "- None.",
        ]
    )
    if include_steps_taken:
        lines.extend(["####", ""])
    else:
        lines.append("")
    return "\n".join(lines)


def persist_review_verdicts_from_markdown(*, meta: dict[str, Any], markdown_path: Path) -> ReviewVerdicts | None:
    try:
        verdicts = extract_review_verdicts_from_markdown(markdown_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if verdicts is not None:
        meta["verdicts"] = review_verdicts_to_meta(verdicts)
    return verdicts


def multipass_prompt_template_names() -> dict[str, str]:
    return {
        "plan": "mrereview_gh_local_big_plan.md",
        "step": "mrereview_gh_local_big_step.md",
        "synth": "mrereview_gh_local_big_synth.md",
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
    ticket_keys = data.get("ticket_keys")
    jira_keys = data.get("jira_keys")
    if ticket_keys is not None:
        if not isinstance(ticket_keys, list) or not all(isinstance(item, str) for item in ticket_keys):
            raise ReviewflowError("Multipass plan JSON ticket_keys must be an array of strings.")
        if jira_keys is None:
            data["jira_keys"] = list(ticket_keys)
    elif jira_keys is not None and (
        not isinstance(jira_keys, list) or not all(isinstance(item, str) for item in jira_keys)
    ):
        raise ReviewflowError("Multipass plan JSON jira_keys must be an array of strings.")
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
        _raise_gh_auth_error(host=host, error=e)


def _gh_error_text(error: ReviewflowSubprocessError) -> str:
    return (error.stderr or error.stdout or str(error)).strip()


def _looks_like_gh_auth_error(error: ReviewflowSubprocessError) -> bool:
    text = _gh_error_text(error).lower()
    needles = (
        "gh auth login",
        "not logged into any github hosts",
        "not authenticated",
        "populate the gh_token",
        "please run:  gh auth login",
        "please run gh auth login",
    )
    return any(needle in text for needle in needles)


def _raise_gh_auth_error(*, host: str, error: ReviewflowSubprocessError) -> None:
    msg = _gh_error_text(error) or str(error)
    raise ReviewflowError(
        f"`gh` is not authenticated for {host}.\n"
        f"- Try: gh auth login -h {host}\n"
        f"- Details: {msg}"
    ) from error


def _supports_public_github_fallback(host: str) -> bool:
    return host == "github.com"


def _public_github_repo_clone_url(*, host: str, owner: str, repo: str) -> str:
    if not _supports_public_github_fallback(host):
        raise ReviewflowError(
            f"Unauthenticated public clone fallback is only supported for github.com, got: {host}"
        )
    return f"https://github.com/{owner}/{repo}.git"


def _github_public_api_json(*, path: str) -> dict[str, Any]:
    normalized = path if path.startswith("/") else f"/{path}"
    req = urllib.request.Request(
        f"https://api.github.com{normalized}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "reviewflow/0.1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ReviewflowError(
            f"Public GitHub API request failed ({getattr(e, 'code', '?')}): {normalized}\n{body}"
        ) from e
    except urllib.error.URLError as e:
        raise ReviewflowError(f"Public GitHub API request failed: {normalized}\n{e}") from e
    try:
        payload = json.loads(body)
    except Exception as e:
        raise ReviewflowError(f"Public GitHub API returned invalid JSON for {normalized}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"Public GitHub API returned unexpected payload for {normalized}")
    return payload


def gh_api_json(*, host: str, path: str, allow_public_fallback: bool = False) -> dict[str, Any]:
    cmd = ["gh", "api", "--hostname", host, path]
    try:
        result = run_cmd(cmd)
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if allow_public_fallback and _supports_public_github_fallback(host):
                _eprint(f"`gh` is not authenticated for {host}; falling back to the public GitHub API.")
                return _github_public_api_json(path=path)
            _raise_gh_auth_error(host=host, error=e)
        raise
    try:
        payload = json.loads(result.stdout)
    except Exception as e:
        raise ReviewflowError(f"`gh api` returned invalid JSON for {path}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"`gh api` returned unexpected payload for {path}")
    return payload


def write_pr_context_file(
    *,
    work_dir: Path,
    pr: PullRequestRef,
    pr_meta: dict[str, Any],
) -> Path:
    path = work_dir / "pr_context.json"
    base = pr_meta.get("base") if isinstance(pr_meta.get("base"), dict) else {}
    head = pr_meta.get("head") if isinstance(pr_meta.get("head"), dict) else {}
    user = pr_meta.get("user") if isinstance(pr_meta.get("user"), dict) else {}
    write_json(
        path,
        {
            "source": "reviewflow.resolve_pr_meta",
            "pr": {
                "host": pr.host,
                "owner": pr.owner,
                "repo": pr.repo,
                "number": pr.number,
                "url": str(pr_meta.get("html_url") or f"https://{pr.host}/{pr.owner}/{pr.repo}/pull/{pr.number}"),
                "title": str(pr_meta.get("title") or ""),
                "body": str(pr_meta.get("body") or ""),
                "state": str(pr_meta.get("state") or ""),
                "draft": bool(pr_meta.get("draft", False)),
                "author": str(user.get("login") or ""),
                "base_ref": str(base.get("ref") or ""),
                "head_ref": str(head.get("ref") or ""),
                "head_sha": str(head.get("sha") or ""),
            },
        },
    )
    return path


def clone_seed_repo(*, host: str, owner: str, repo: str, seed: Path) -> None:
    cmd = ["gh", "repo", "clone", repo_id_for_gh(host, owner, repo), str(seed)]
    try:
        run_cmd(cmd)
        return
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if _supports_public_github_fallback(host):
                _eprint(f"`gh` is not authenticated for {host}; falling back to public git clone.")
                run_cmd(
                    [
                        "git",
                        "clone",
                        _public_github_repo_clone_url(host=host, owner=owner, repo=repo),
                        str(seed),
                    ]
                )
                return
            _raise_gh_auth_error(host=host, error=e)
        raise


def checkout_pr_in_repo(*, repo_dir: Path, pr: PullRequestRef) -> None:
    cmd = [
        "gh",
        "pr",
        "checkout",
        str(pr.number),
        "-R",
        pr.gh_repo,
        "--force",
    ]
    try:
        run_cmd(cmd, cwd=repo_dir)
        return
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if _supports_public_github_fallback(pr.host):
                branch = f"reviewflow_pr__{pr.number}"
                _eprint(f"`gh` is not authenticated for {pr.host}; falling back to public git fetch for PR #{pr.number}.")
                run_cmd(
                    [
                        "git",
                        "-C",
                        str(repo_dir),
                        "fetch",
                        "origin",
                        f"refs/pull/{pr.number}/head:{branch}",
                    ]
                )
                run_cmd(["git", "-C", str(repo_dir), "checkout", "-B", branch, branch])
                return
            _raise_gh_auth_error(host=pr.host, error=e)
        raise


@dataclass(frozen=True)
class ReviewflowChunkHoundConfig:
    base_config_path: Path
    indexing_include: tuple[str, ...] | None = None
    indexing_exclude: tuple[str, ...] | None = None
    per_file_timeout_seconds: float | int | None = None
    per_file_timeout_min_size_kb: int | None = None
    research_algorithm: str | None = None


def _chunkhound_config_error(*, reason: str, path: Path) -> ReviewflowError:
    return ReviewflowError(
        f"{reason}\n"
        f"Reviewflow ChunkHound config path: {path}\n"
        "Example:\n"
        f"{CHUNKHOUND_CONFIG_EXAMPLE.rstrip()}"
    )


def _read_chunkhound_json_config(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ReviewflowError(f"ChunkHound base config not found: {path}") from e
    except Exception as e:
        raise ReviewflowError(f"ChunkHound base config is invalid JSON: {path} ({e})") from e
    if not isinstance(raw, dict):
        raise ReviewflowError(f"ChunkHound base config must be a JSON object: {path}")
    return raw


def _parse_chunkhound_numeric_override(
    raw: object, *, field_name: str, allow_float: bool = False
) -> int | float:
    if allow_float and isinstance(raw, (int, float)) and float(raw) > 0:
        return float(raw)
    if isinstance(raw, int) and raw > 0:
        return int(raw)
    raise ReviewflowError(f"Invalid [chunkhound].{field_name}: expected a positive number.")


def load_reviewflow_chunkhound_config(
    *, config_path: Path | None = None, require: bool = True
) -> tuple[ReviewflowChunkHoundConfig | None, dict[str, Any]]:
    path = config_path or default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("chunkhound") if isinstance(raw, dict) else None

    if section is None:
        if require:
            raise _chunkhound_config_error(
                reason="Missing required `[chunkhound]` section.",
                path=path,
            )
        return None, {
            "config_path": str(path),
            "loaded": bool(raw),
            "chunkhound": None,
        }

    if not isinstance(section, dict):
        raise _chunkhound_config_error(
            reason="`[chunkhound]` must be a table.",
            path=path,
        )

    base_config_path_raw = str(section.get("base_config_path") or "").strip()
    if not base_config_path_raw:
        raise _chunkhound_config_error(
            reason="`[chunkhound].base_config_path` is required.",
            path=path,
        )
    base_config_path = Path(base_config_path_raw).expanduser()
    if not base_config_path.is_absolute():
        raise _chunkhound_config_error(
            reason="`[chunkhound].base_config_path` must be an absolute path.",
            path=path,
        )
    base_config_path = base_config_path.resolve(strict=False)
    _ = _read_chunkhound_json_config(base_config_path)

    indexing = section.get("indexing")
    indexing = indexing if isinstance(indexing, dict) else {}
    research = section.get("research")
    research = research if isinstance(research, dict) else {}

    if "include" in indexing and (not isinstance(indexing.get("include"), list)):
        raise ReviewflowError("Invalid [chunkhound].indexing.include: expected an array of strings.")
    if "exclude" in indexing and (not isinstance(indexing.get("exclude"), list)):
        raise ReviewflowError("Invalid [chunkhound].indexing.exclude: expected an array of strings.")

    indexing_include = (
        tuple(_string_list(indexing.get("include"))) if ("include" in indexing) else None
    )
    indexing_exclude = (
        tuple(_string_list(indexing.get("exclude"))) if ("exclude" in indexing) else None
    )
    per_file_timeout_seconds = (
        _parse_chunkhound_numeric_override(
            indexing.get("per_file_timeout_seconds"),
            field_name="indexing.per_file_timeout_seconds",
            allow_float=True,
        )
        if ("per_file_timeout_seconds" in indexing)
        else None
    )
    per_file_timeout_min_size_kb = (
        int(
            _parse_chunkhound_numeric_override(
                indexing.get("per_file_timeout_min_size_kb"),
                field_name="indexing.per_file_timeout_min_size_kb",
                allow_float=False,
            )
        )
        if ("per_file_timeout_min_size_kb" in indexing)
        else None
    )
    if "algorithm" in research and (not isinstance(research.get("algorithm"), str)):
        raise ReviewflowError("Invalid [chunkhound].research.algorithm: expected a non-empty string.")
    research_algorithm = (
        str(research.get("algorithm") or "").strip() if ("algorithm" in research) else None
    )
    if research_algorithm == "":
        raise ReviewflowError("Invalid [chunkhound].research.algorithm: expected a non-empty string.")

    cfg = ReviewflowChunkHoundConfig(
        base_config_path=base_config_path,
        indexing_include=indexing_include,
        indexing_exclude=indexing_exclude,
        per_file_timeout_seconds=per_file_timeout_seconds,
        per_file_timeout_min_size_kb=per_file_timeout_min_size_kb,
        research_algorithm=research_algorithm,
    )
    meta: dict[str, Any] = {
        "config_path": str(path),
        "loaded": bool(raw),
        "chunkhound": {
            "base_config_path": str(base_config_path),
            "base_config_fingerprint": json_fingerprint(base_config_path),
            "indexing": {
                "include": list(indexing_include) if indexing_include is not None else None,
                "exclude": list(indexing_exclude) if indexing_exclude is not None else None,
                "per_file_timeout_seconds": per_file_timeout_seconds,
                "per_file_timeout_min_size_kb": per_file_timeout_min_size_kb,
            },
            "research": {
                "algorithm": research_algorithm,
            },
        },
    }
    return cfg, meta


def resolve_chunkhound_reviewflow_config(cfg: ReviewflowChunkHoundConfig) -> dict[str, Any]:
    base = _read_chunkhound_json_config(cfg.base_config_path)
    resolved = dict(base)

    indexing = base.get("indexing")
    indexing = dict(indexing) if isinstance(indexing, dict) else {}
    if cfg.indexing_include is not None:
        indexing.pop("_include", None)
        indexing["include"] = list(cfg.indexing_include)
    if cfg.indexing_exclude is not None:
        indexing["exclude"] = list(cfg.indexing_exclude)
    if cfg.per_file_timeout_seconds is not None:
        indexing["per_file_timeout_seconds"] = cfg.per_file_timeout_seconds
    if cfg.per_file_timeout_min_size_kb is not None:
        indexing["per_file_timeout_min_size_kb"] = cfg.per_file_timeout_min_size_kb
    if indexing:
        resolved["indexing"] = indexing

    research = base.get("research")
    research = dict(research) if isinstance(research, dict) else {}
    if cfg.research_algorithm is not None:
        research["algorithm"] = cfg.research_algorithm
    if research:
        resolved["research"] = research

    return resolved


def fingerprint_chunkhound_reviewflow_config(meta: dict[str, Any]) -> str:
    chunkhound = meta.get("chunkhound") if isinstance(meta.get("chunkhound"), dict) else {}
    canonical = json.dumps(chunkhound, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_chunkhound_runtime_config(
    *, config_path: Path | None = None, require: bool = True
) -> tuple[ReviewflowChunkHoundConfig, dict[str, Any], dict[str, Any]]:
    cfg, meta = load_reviewflow_chunkhound_config(config_path=config_path, require=require)
    if cfg is None:
        raise ReviewflowError("ChunkHound runtime config is unavailable.")
    resolved = resolve_chunkhound_reviewflow_config(cfg)
    return cfg, meta, resolved


def load_embedding_api_key_from_config(*, source_config_path: Path | None = None) -> str | None:
    if source_config_path is None:
        return None
    try:
        raw = json.loads(source_config_path.read_text(encoding="utf-8"))
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


def migrate_storage_flow(args: argparse.Namespace, *, paths: ReviewflowPaths) -> int:
    _ = args
    _ = paths
    _eprint(
        f"`{PRIMARY_CLI_COMMAND} migrate-storage` is deprecated and no longer performs any migration.\n"
        "Reviewflow now uses generic XDG/home defaults and does not auto-discover legacy workspace paths."
    )
    return 0


def materialize_chunkhound_env_config(
    *,
    resolved_config: dict[str, Any],
    output_config_path: Path,
    database_provider: str,
    database_path: Path,
) -> None:
    """Write a standalone ChunkHound config file for a reviewflow "environment".

    This improves reproducibility by pinning DB location/provider in a session-local config file
    rather than relying on CLI overrides (which can override/replace config lists like indexing.exclude).
    """
    cfg = dict(resolved_config)

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


def chunkhound_env(*, source_config_path: Path | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    if os.environ.get("CHUNKHOUND_EMBEDDING__API_KEY"):
        return env

    # If the user has a provider-specific key in env, map it to what ChunkHound expects.
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if voyage_key:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = voyage_key
        return env

    inferred = load_embedding_api_key_from_config(source_config_path=source_config_path)
    if inferred:
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = inferred
    return env


def ensure_review_config(paths: ReviewflowPaths, *, config_path: Path | None = None) -> None:
    _ = paths
    load_reviewflow_chunkhound_config(
        config_path=(config_path or default_reviewflow_config_path()),
        require=True,
    )


def cache_prime(
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    host: str,
    owner: str,
    repo: str,
    base_ref: str,
    force: bool,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    effective_config_path = config_path or default_reviewflow_config_path()
    ensure_review_config(paths, config_path=effective_config_path)
    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )

    stream = (not quiet) and (not no_stream)

    base_root = base_dir(paths, host, owner, repo, base_ref)
    base_root.mkdir(parents=True, exist_ok=True)
    with file_lock(base_root / ".cache_prime.lock", quiet=quiet):
        seed = seed_dir(paths, host, owner, repo)
        seed.parent.mkdir(parents=True, exist_ok=True)
        with phase(f"cache_seed_sync {owner}/{repo}@{base_ref}", progress=None, quiet=quiet):
            if not seed.exists():
                clone_seed_repo(host=host, owner=owner, repo=repo, seed=seed)
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
            resolved_config=resolved_chunkhound_cfg,
            output_config_path=ch_cfg_path,
            database_provider="duckdb",
            database_path=db_path,
        )

        cfg_fp = fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
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

        env = merged_env(chunkhound_env(source_config_path=chunkhound_cfg.base_config_path))
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
            "chunkhound": chunkhound_meta.get("chunkhound"),
            "chunkhound_version": run_cmd(["chunkhound", "--version"]).stdout.strip(),
            "index_cmd": index_cmd,
            "index_duration_seconds": index_result.duration_seconds,
        }
        write_redacted_json(meta_path, meta)
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
    config_path: Path | None = None,
    pr: PullRequestRef,
    base_ref: str,
    ttl_hours: int,
    refresh: bool,
    quiet: bool = False,
    no_stream: bool = False,
) -> dict[str, Any]:
    effective_config_path = config_path or default_reviewflow_config_path()
    base_root = base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
    meta_path = base_root / "meta.json"
    if refresh or not meta_path.is_file():
        log(f"Base cache refresh: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return cache_prime(
            paths=paths,
            config_path=effective_config_path,
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
        _, chunkhound_meta, _ = load_chunkhound_runtime_config(
            config_path=effective_config_path,
            require=True,
        )
        cfg_fp = fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
    except Exception as e:
        cfg_fp = None
        log(
            f"Base cache config fingerprint failed: {effective_config_path} ({e})",
            quiet=quiet,
        )

    if cfg_fp and meta.get("config_fingerprint") != cfg_fp:
        log(f"Base cache config changed: {pr.owner}/{pr.repo}@{base_ref}", quiet=quiet)
        return cache_prime(
            paths=paths,
            config_path=effective_config_path,
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
            config_path=effective_config_path,
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


def prepare_netrc_for_reviewflow(*, dst_root: Path) -> Path | None:
    src = real_user_home_dir() / ".netrc"
    if not src.is_file():
        return None
    dst_dir = dst_root / "netrc"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / ".netrc"
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


def pr_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    global _ACTIVE_OUTPUT
    effective_config_path = config_path or default_reviewflow_config_path()
    effective_codex_base_config_path = codex_base_config_path or default_codex_base_config_path()
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
    ensure_review_config(paths, config_path=effective_config_path)

    log(f"PR {pr.owner}/{pr.repo}#{pr.number} ({pr.host})", quiet=quiet)

    # PR metadata (base ref name + head SHA).
    with phase("resolve_pr_meta", progress=None, quiet=quiet):
        pr_meta = gh_api_json(
            host=pr.host,
            path=f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}",
            allow_public_fallback=True,
        )
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
    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
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
    pr_context_path = write_pr_context_file(work_dir=work_dir, pr=pr, pr_meta=pr_meta)
    progress.meta["chunkhound"] = chunkhound_meta["chunkhound"]
    progress.meta.setdefault("paths", {})["agent_desc"] = str(agent_desc_path)
    progress.meta.setdefault("paths", {})["pr_context"] = str(pr_context_path)
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
    codex_meta: dict[str, Any] | None = None
    runtime_policy: dict[str, Any] | None = None

    base_cache_meta: dict[str, Any] | None = None
    pr_stats: dict[str, Any] | None = None
    profile_resolved: str | None = None
    profile_reason: str | None = None
    profile_template_name: str | None = None
    use_multipass = False
    review_intelligence_cfg, review_intelligence_meta = load_review_intelligence_config(
        config_path=effective_config_path,
        require_tool_prompt_fragment=False,
    )
    progress.meta["review_intelligence"] = review_intelligence_meta["review_intelligence"]
    multipass_defaults, multipass_defaults_meta = load_reviewflow_multipass_defaults(
        config_path=effective_config_path
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
                    config_path=effective_config_path,
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
                f"Seed clone missing at {seed}. Try `{PRIMARY_CLI_COMMAND} cache prime {pr.owner_repo} --base {base_ref}`."
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
            checkout_pr_in_repo(repo_dir=repo_dir, pr=pr)
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
                profile_template_name = prompt_template_name_for_profile(profile_resolved)
                progress.meta["prompt"] = {
                    "source": "profile",
                    "profile_requested": prompt_profile_requested,
                    "profile_resolved": profile_resolved,
                    "reason": profile_reason,
                    "template_id": builtin_prompt_id(profile_template_name),
                }
                require_builtin_review_intelligence(
                    review_intelligence_cfg, config_path=effective_config_path
                )
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

                env = merged_env(
                    chunkhound_env(source_config_path=chunkhound_cfg.base_config_path)
                )
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
            llm_resolved, llm_resolution_meta = resolve_llm_config_from_args(
                args,
                reviewflow_config_path=effective_config_path,
                base_codex_config_path=effective_codex_base_config_path,
            )
            runtime_policy = prepare_review_agent_runtime(
                args=args,
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                reviewflow_config_path=effective_config_path,
                config_enabled=True,
                repo_dir=repo_dir,
                session_dir=session_dir,
                work_dir=work_dir,
                base_env=chunkhound_env(source_config_path=chunkhound_cfg.base_config_path),
                chunkhound_config_path=chunkhound_cfg_path,
                chunkhound_db_path=chunkhound_db_path,
                chunkhound_cwd=chunkhound_work_dir,
                enable_mcp=(not bool(getattr(args, "no_index", False))),
                interactive=False,
                paths=paths,
            )
            env = dict(runtime_policy["env"])
            adapter_meta: dict[str, Any] = {
                "transport": f"cli-{llm_resolved.get('provider')}",
                "runtime_policy": runtime_policy["metadata"],
            }
            if str(llm_resolved.get("provider") or "") == "codex":
                codex_flags = list(runtime_policy.get("codex_flags") or [])
                codex_overrides = list(runtime_policy.get("codex_config_overrides") or [])
                adapter_meta.update(
                    {
                        "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                            "dangerously_bypass_approvals_and_sandbox"
                        ],
                        "config_overrides": codex_overrides,
                        "flags": codex_flags,
                    }
                )
                progress.meta["codex"] = {
                    "config": build_codex_flags_from_llm_config(
                        resolved=llm_resolved,
                        resolution_meta=llm_resolution_meta,
                        include_sandbox=False,
                    )[1],
                    "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                        "dangerously_bypass_approvals_and_sandbox"
                    ],
                    "config_overrides": codex_overrides,
                    "flags": codex_flags,
                    "env": {
                        "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
                        "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
                        "NETRC": env.get("NETRC"),
                        "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
                    },
                    "helpers": {"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
                }
            progress.meta["agent_runtime"] = runtime_policy["metadata"]
            progress.meta["llm"] = build_llm_meta(
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                env=env,
                adapter_meta=adapter_meta,
                helpers={"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
            )
            progress.flush()

            add_dirs = list(runtime_policy.get("add_dirs") or [])
            if str(llm_resolved.get("provider") or "") == "codex":
                if not args.no_index:
                    log(
                        "Codex MCP: sandbox ChunkHound enabled (daemon; startup_timeout_sec=20)",
                        quiet=quiet,
                    )
                else:
                    log("Codex MCP: sandbox ChunkHound disabled (--no-index)", quiet=quiet)
            else:
                log(
                    f"LLM preset: {llm_resolved.get('preset')} ({llm_resolved.get('provider')})",
                    quiet=quiet,
                )

            if use_multipass:
                templates = multipass_prompt_template_names()

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
                    plan_template = load_builtin_prompt_text(templates["plan"])
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
                        extra_vars={
                            **review_intelligence_prompt_vars(review_intelligence_cfg),
                            "MAX_STEPS": str(multipass_max_steps),
                        },
                    )
                    progress.meta.setdefault("multipass", {}).setdefault("runs", []).append(
                        {
                            "kind": "plan",
                            "template_id": builtin_prompt_id(templates["plan"]),
                            "output_path": str(plan_md_path),
                            "prompt_chars": len(plan_prompt),
                            "prompt_sha256": sha256_text(plan_prompt),
                        }
                    )
                    progress.flush()
                    plan_result = run_llm_exec(
                        repo_dir=repo_dir,
                        resolved=llm_resolved,
                        resolution_meta=llm_resolution_meta,
                        output_path=plan_md_path,
                        prompt=plan_prompt,
                        env=env,
                        stream=stream,
                        progress=progress,
                        add_dirs=add_dirs,
                        codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                        runtime_policy=runtime_policy,
                    )
                    plan_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                    if plan_runs and isinstance(plan_runs[-1], dict) and plan_result.resume is not None:
                        plan_runs[-1]["llm_session_id"] = plan_result.resume.session_id
                        plan_runs[-1]["llm_provider"] = plan_result.resume.provider
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
                            build_abort_review_markdown(reason=reason, include_steps_taken=True),
                            encoding="utf-8",
                        )
                        progress.meta.setdefault("multipass", {})["status"] = "abort"
                        progress.flush()
                        if persist_review_verdicts_from_markdown(
                            meta=progress.meta, markdown_path=review_md_path
                        ) is not None:
                            progress.flush()
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
                            step_template = load_builtin_prompt_text(templates["step"])
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
                                    **review_intelligence_prompt_vars(review_intelligence_cfg),
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
                                    "template_id": builtin_prompt_id(templates["step"]),
                                    "prompt_chars": len(step_prompt),
                                    "prompt_sha256": sha256_text(step_prompt),
                                }
                            )
                            progress.flush()
                            try:
                                step_result = run_llm_exec(
                                    repo_dir=repo_dir,
                                    resolved=llm_resolved,
                                    resolution_meta=llm_resolution_meta,
                                    output_path=out_path,
                                    prompt=step_prompt,
                                    env=env,
                                    stream=stream,
                                    progress=progress,
                                    add_dirs=add_dirs,
                                    codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                                    runtime_policy=runtime_policy,
                                )
                                step_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                                if step_runs and isinstance(step_runs[-1], dict) and step_result.resume is not None:
                                    step_runs[-1]["llm_session_id"] = step_result.resume.session_id
                                    step_runs[-1]["llm_provider"] = step_result.resume.provider
                                    progress.flush()
                            except ReviewflowSubprocessError:
                                _eprint(
                                    f"Multipass step failed. To resume: {PRIMARY_CLI_COMMAND} resume {session_id}"
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
                        synth_template = load_builtin_prompt_text(templates["synth"])
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
                                **review_intelligence_prompt_vars(review_intelligence_cfg),
                                "PLAN_JSON_PATH": str(plan_json_path),
                                "STEP_OUTPUT_PATHS": step_paths_text,
                            },
                        )
                        progress.meta.setdefault("multipass", {}).setdefault("runs", []).append(
                            {
                                "kind": "synth",
                                "template_id": builtin_prompt_id(templates["synth"]),
                                "output_path": str(review_md_path),
                                "prompt_chars": len(synth_prompt),
                                "prompt_sha256": sha256_text(synth_prompt),
                            }
                        )
                        progress.flush()
                        synth_result = run_llm_exec(
                            repo_dir=repo_dir,
                            resolved=llm_resolved,
                            resolution_meta=llm_resolution_meta,
                            output_path=review_md_path,
                            prompt=synth_prompt,
                            env=env,
                            stream=stream,
                            progress=progress,
                            add_dirs=add_dirs,
                            codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                            runtime_policy=runtime_policy,
                        )
                        synth_runs = progress.meta.setdefault("multipass", {}).setdefault("runs", [])
                        if synth_runs and isinstance(synth_runs[-1], dict) and synth_result.resume is not None:
                            synth_runs[-1]["llm_session_id"] = synth_result.resume.session_id
                            synth_runs[-1]["llm_provider"] = synth_result.resume.provider
                        success_resume_command = record_llm_resume(
                            progress.meta.setdefault("llm", {}), synth_result.resume
                        )
                        if codex_meta is not None:
                            codex_resume = (
                                CodexResumeInfo(
                                    session_id=synth_result.resume.session_id,
                                    cwd=synth_result.resume.cwd,
                                    command=synth_result.resume.command,
                                )
                                if synth_result.resume is not None and synth_result.resume.provider == "codex"
                                else None
                            )
                            record_codex_resume(progress.meta.setdefault("codex", {}), codex_resume)
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
                        if profile_template_name is None:
                            profile_resolved, profile_reason = resolve_prompt_profile(
                                requested=prompt_profile_requested,
                                pr_stats=pr_stats if pr_stats and "changed_lines" in pr_stats else None,
                                big_if_files=big_if_files,
                                big_if_lines=big_if_lines,
                            )
                            profile_template_name = prompt_template_name_for_profile(profile_resolved)
                        prompt = load_builtin_prompt_text(profile_template_name)
                        prompt_info.update(
                            {
                                "source": "profile",
                                "profile_requested": prompt_profile_requested,
                                "profile_resolved": profile_resolved,
                                "reason": profile_reason,
                                "template_id": builtin_prompt_id(profile_template_name),
                            }
                        )

                    if not prompt and not args.no_review:
                        raise ReviewflowError("No prompt provided and no prompt template could be loaded.")
                    if prompt:
                        prompt_extra_vars = review_intelligence_prompt_vars(review_intelligence_cfg)
                        prompt_extra_vars["PR_CONTEXT_PATH"] = str(pr_context_path)
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
                            extra_vars=prompt_extra_vars,
                        )
                        prompt_info["prompt_chars"] = len(rendered)
                        prompt_info["prompt_sha256"] = sha256_text(rendered)
                        progress.meta["prompt"] = prompt_info
                        progress.flush()
                        prompt = rendered

                assert prompt is not None
                with phase("codex_review", progress=progress, quiet=quiet):
                    review_result = run_llm_exec(
                        repo_dir=repo_dir,
                        resolved=llm_resolved,
                        resolution_meta=llm_resolution_meta,
                        output_path=review_md_path,
                        prompt=prompt,
                        env=env,
                        stream=stream,
                        progress=progress,
                        add_dirs=add_dirs,
                        codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                        runtime_policy=runtime_policy,
                    )
                    success_resume_command = record_llm_resume(
                        progress.meta.setdefault("llm", {}), review_result.resume
                    )
                    if codex_meta is not None:
                        codex_resume = (
                            CodexResumeInfo(
                                session_id=review_result.resume.session_id,
                                cwd=review_result.resume.cwd,
                                command=review_result.resume.command,
                            )
                            if review_result.resume is not None and review_result.resume.provider == "codex"
                            else None
                        )
                        record_codex_resume(progress.meta.setdefault("codex", {}), codex_resume)
                    progress.flush()

        if persist_review_verdicts_from_markdown(meta=progress.meta, markdown_path=review_md_path) is not None:
            progress.flush()
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
        cleanup_sensitive_staged_paths((runtime_policy or {}).get("staged_paths"))
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


def resume_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    global _ACTIVE_OUTPUT
    effective_config_path = config_path or default_reviewflow_config_path()
    effective_codex_base_config_path = codex_base_config_path or default_codex_base_config_path()
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
            f"Tip: run `{PRIMARY_CLI_COMMAND} list` to find a session id."
        )

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ReviewflowError(f"Failed to parse meta.json: {e}") from e

    session_llm = resolve_meta_llm(meta)
    session_supports_resume = bool(
        ((session_llm.get("capabilities") or {}).get("supports_resume"))
    )
    session_provider = str(session_llm.get("provider") or "unknown").strip() or "unknown"
    if not session_supports_resume:
        raise ReviewflowError(
            f"resume is not supported for provider {session_provider} in v1. "
            "This session is execution-only."
        )

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
    ensure_review_config(paths, config_path=effective_config_path)
    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )
    # Always refresh the session-local ChunkHound config so it tracks updates
    # from the configured base ChunkHound config on every resume run.
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
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
    runtime_policy: dict[str, Any] | None = None

    try:
        agent_desc = ""
        agent_desc_path = Path(str(((meta.get("paths") or {}).get("agent_desc")) or "")).resolve()
        if agent_desc_path.is_file():
            agent_desc = agent_desc_path.read_text(encoding="utf-8")

        base_ref_for_review = str(meta.get("base_ref_for_review") or "").strip()
        if not base_ref_for_review:
            raise ReviewflowError("Session meta missing base_ref_for_review.")

        review_intelligence_cfg, review_intelligence_meta = load_review_intelligence_config(
            config_path=effective_config_path,
            require_tool_prompt_fragment=False,
        )
        require_builtin_review_intelligence(
            review_intelligence_cfg, config_path=effective_config_path
        )
        progress.meta["chunkhound"] = chunkhound_meta["chunkhound"]
        progress.meta["review_intelligence"] = review_intelligence_meta["review_intelligence"]
        progress.flush()

        llm_resolved, llm_resolution_meta = resolve_llm_config_from_args(
            args,
            reviewflow_config_path=effective_config_path,
            base_codex_config_path=effective_codex_base_config_path,
        )
        if not bool(((llm_resolved.get("capabilities") or {}).get("supports_resume"))):
            raise ReviewflowError(
                f"resume is not supported for provider {llm_resolved.get('provider')} in v1. "
                "This provider is execution-only."
            )
        no_index = False
        codex_meta: dict[str, Any] | None = None
        runtime_policy = prepare_review_agent_runtime(
            args=args,
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            reviewflow_config_path=effective_config_path,
            config_enabled=True,
            repo_dir=repo_dir,
            session_dir=session_dir,
            work_dir=work_dir,
            base_env=chunkhound_env(source_config_path=chunkhound_cfg.base_config_path),
            chunkhound_config_path=chunkhound_cfg_path,
            chunkhound_db_path=chunkhound_db_path,
            chunkhound_cwd=chunkhound_work_dir,
            enable_mcp=(not no_index),
            interactive=True,
            paths=paths,
        )
        env = dict(runtime_policy["env"])
        adapter_meta: dict[str, Any] = {
            "transport": f"cli-{llm_resolved.get('provider')}",
            "runtime_policy": runtime_policy["metadata"],
        }
        if str(llm_resolved.get("provider") or "") == "codex":
            codex_flags = list(runtime_policy.get("codex_flags") or [])
            codex_overrides = list(runtime_policy.get("codex_config_overrides") or [])
            codex_meta = build_codex_flags_from_llm_config(
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                include_sandbox=False,
            )[1]
            adapter_meta.update(
                {
                    "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                        "dangerously_bypass_approvals_and_sandbox"
                    ],
                    "config_overrides": codex_overrides,
                    "flags": codex_flags,
                }
            )
            progress.meta["codex"] = {
                "config": codex_meta,
                "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                    "dangerously_bypass_approvals_and_sandbox"
                ],
                "config_overrides": codex_overrides,
                "flags": codex_flags,
                "env": {
                    "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
                    "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
                    "NETRC": env.get("NETRC"),
                    "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
                },
                "helpers": {"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
            }
        progress.meta["agent_runtime"] = runtime_policy["metadata"]
        progress.meta["llm"] = build_llm_meta(
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            env=env,
            adapter_meta=adapter_meta,
            helpers={"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
        )
        progress.flush()

        add_dirs = list(runtime_policy.get("add_dirs") or [])
        if str(llm_resolved.get("provider") or "") == "codex":
            if not no_index:
                log(
                    "Codex MCP: sandbox ChunkHound enabled (daemon; startup_timeout_sec=20)",
                    quiet=quiet,
                )
            else:
                log("Codex MCP: sandbox ChunkHound disabled (--no-index)", quiet=quiet)

        templates = multipass_prompt_template_names()

        # If already complete, no-op.
        if from_phase == "auto" and review_md_path.is_file() and str(meta.get("status")) == "done":
            success_markdown_path = review_md_path
            print(str(session_dir))
            return 0

        multipass_cfg, _ = load_reviewflow_multipass_defaults(
            config_path=effective_config_path
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
                plan_template = load_builtin_prompt_text(templates["plan"])
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
                    extra_vars={
                        **review_intelligence_prompt_vars(review_intelligence_cfg),
                        "MAX_STEPS": str(max_steps),
                    },
                )
                plan_result = run_llm_exec(
                    repo_dir=repo_dir,
                    resolved=llm_resolved,
                    resolution_meta=llm_resolution_meta,
                    output_path=plan_md_path,
                    prompt=plan_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                    codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                    runtime_policy=runtime_policy,
                )
                success_resume_command = record_llm_resume(progress.meta.setdefault("llm", {}), plan_result.resume)
                if codex_meta is not None:
                    codex_resume = (
                        CodexResumeInfo(
                            session_id=plan_result.resume.session_id,
                            cwd=plan_result.resume.cwd,
                            command=plan_result.resume.command,
                        )
                        if plan_result.resume is not None and plan_result.resume.provider == "codex"
                        else None
                    )
                    record_codex_resume(progress.meta.setdefault("codex", {}), codex_resume)
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
                build_abort_review_markdown(reason=reason, include_steps_taken=True),
                encoding="utf-8",
            )
            if persist_review_verdicts_from_markdown(meta=progress.meta, markdown_path=review_md_path) is not None:
                progress.flush()
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
                step_template = load_builtin_prompt_text(templates["step"])
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
                        **review_intelligence_prompt_vars(review_intelligence_cfg),
                        "PLAN_JSON_PATH": str(plan_json_path),
                        "STEP_ID": step_id,
                        "STEP_TITLE": step_title,
                        "STEP_FOCUS": step_focus,
                    },
                )
                step_result = run_llm_exec(
                    repo_dir=repo_dir,
                    resolved=llm_resolved,
                    resolution_meta=llm_resolution_meta,
                    output_path=out_path,
                    prompt=step_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                    codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                    runtime_policy=runtime_policy,
                )
                success_resume_command = record_llm_resume(progress.meta.setdefault("llm", {}), step_result.resume)
                if codex_meta is not None:
                    codex_resume = (
                        CodexResumeInfo(
                            session_id=step_result.resume.session_id,
                            cwd=step_result.resume.cwd,
                            command=step_result.resume.command,
                        )
                        if step_result.resume is not None and step_result.resume.provider == "codex"
                        else None
                    )
                    record_codex_resume(progress.meta.setdefault("codex", {}), codex_resume)
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
                synth_template = load_builtin_prompt_text(templates["synth"])
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
                        **review_intelligence_prompt_vars(review_intelligence_cfg),
                        "PLAN_JSON_PATH": str(plan_json_path),
                        "STEP_OUTPUT_PATHS": step_paths_text,
                    },
                )
                synth_result = run_llm_exec(
                    repo_dir=repo_dir,
                    resolved=llm_resolved,
                    resolution_meta=llm_resolution_meta,
                    output_path=review_md_path,
                    prompt=synth_prompt,
                    env=env,
                    stream=stream,
                    progress=progress,
                    add_dirs=add_dirs,
                    codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                    runtime_policy=runtime_policy,
                )
                success_resume_command = record_llm_resume(
                    progress.meta.setdefault("llm", {}), synth_result.resume
                )
                if codex_meta is not None:
                    codex_resume = (
                        CodexResumeInfo(
                            session_id=synth_result.resume.session_id,
                            cwd=synth_result.resume.cwd,
                            command=synth_result.resume.command,
                        )
                        if synth_result.resume is not None and synth_result.resume.provider == "codex"
                        else None
                    )
                    record_codex_resume(progress.meta.setdefault("codex", {}), codex_resume)
                progress.flush()

        if did_work:
            progress.meta["status"] = "running"
            progress.flush()
        if persist_review_verdicts_from_markdown(meta=progress.meta, markdown_path=review_md_path) is not None:
            progress.flush()
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
        cleanup_sensitive_staged_paths((runtime_policy or {}).get("staged_paths"))
        if _ACTIVE_OUTPUT is out:
            _ACTIVE_OUTPUT = None
        out.stop()
        maybe_print_markdown_after_tui(
            ui_enabled=ui_enabled, stderr=out.stderr, markdown_path=success_markdown_path
        )
        maybe_print_codex_resume_command(stderr=out.stderr, command=success_resume_command)


def followup_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    global _ACTIVE_OUTPUT
    effective_config_path = config_path or default_reviewflow_config_path()
    effective_codex_base_config_path = codex_base_config_path or default_codex_base_config_path()
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
    ensure_review_config(paths, config_path=effective_config_path)

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

    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )
    # Always refresh the session-local ChunkHound config so it tracks updates
    # from the configured base ChunkHound config on every follow-up run.
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
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
    write_redacted_json(meta_path, meta)

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
    runtime_policy: dict[str, Any] | None = None

    try:
        progress = SessionProgress(meta_path, quiet=True)
        progress.meta = meta

        base_ref_for_review = str(meta.get("base_ref_for_review") or "").strip()
        if not base_ref_for_review:
            raise ReviewflowError("Session meta missing base_ref_for_review.")
        base_ref = str(meta.get("base_ref") or "").strip()
        if not base_ref:
            raise ReviewflowError("Session meta missing base_ref.")

        review_intelligence_cfg, review_intelligence_meta = load_review_intelligence_config(
            config_path=effective_config_path,
            require_tool_prompt_fragment=False,
        )
        require_builtin_review_intelligence(
            review_intelligence_cfg, config_path=effective_config_path
        )
        meta["chunkhound"] = chunkhound_meta["chunkhound"]
        meta["review_intelligence"] = review_intelligence_meta["review_intelligence"]

        agent_desc = ""
        agent_desc_path = Path(str(((meta.get("paths") or {}).get("agent_desc")) or "")).resolve()
        if agent_desc_path.is_file():
            agent_desc = agent_desc_path.read_text(encoding="utf-8")

        llm_resolved, llm_resolution_meta = resolve_llm_config_from_args(
            args,
            reviewflow_config_path=effective_config_path,
            base_codex_config_path=effective_codex_base_config_path,
        )
        runtime_policy = prepare_review_agent_runtime(
            args=args,
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            reviewflow_config_path=effective_config_path,
            config_enabled=True,
            repo_dir=repo_dir,
            session_dir=session_dir,
            work_dir=work_dir,
            base_env=chunkhound_env(source_config_path=chunkhound_cfg.base_config_path),
            chunkhound_config_path=chunkhound_cfg_path,
            chunkhound_db_path=chunkhound_db_path,
            chunkhound_cwd=chunkhound_work_dir,
            enable_mcp=True,
            interactive=False,
            paths=paths,
        )
        env = dict(runtime_policy["env"])
        codex_meta: dict[str, Any] | None = None
        codex_flags = list(runtime_policy.get("codex_flags") or [])
        if str(llm_resolved.get("provider") or "") == "codex":
            codex_meta = build_codex_flags_from_llm_config(
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                include_sandbox=False,
            )[1]

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
        followup_template_name = followup_prompt_template_name_for_profile(profile_resolved)
        followup_template = load_builtin_prompt_text(followup_template_name)
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
                **review_intelligence_prompt_vars(review_intelligence_cfg),
                "PREVIOUS_REVIEW_MD": str(review_md_path),
                "HEAD_SHA_BEFORE": head_before,
                "HEAD_SHA_AFTER": head_after,
                "FOLLOWUP_OUTPUT_MD": str(followup_md_path),
            },
        )

        meta["llm"] = build_llm_meta(
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            env=env,
            adapter_meta={
                "transport": f"cli-{llm_resolved.get('provider')}",
                "runtime_policy": runtime_policy["metadata"],
                "config_overrides": list(runtime_policy.get("codex_config_overrides") or []),
                "flags": codex_flags,
            },
            helpers={"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
        )
        meta["agent_runtime"] = runtime_policy["metadata"]
        if codex_meta is not None:
            meta["codex"] = {
                "config": codex_meta,
                "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                    "dangerously_bypass_approvals_and_sandbox"
                ],
                "config_overrides": list(runtime_policy.get("codex_config_overrides") or []),
                "flags": codex_flags,
                "helpers": {"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
            }

        with phase("followup_review", progress=None, quiet=quiet):
            followup_result = run_llm_exec(
                repo_dir=repo_dir,
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                output_path=followup_md_path,
                prompt=followup_prompt,
                env=env,
                stream=stream,
                progress=progress,
                add_dirs=list(runtime_policy.get("add_dirs") or []),
                codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                runtime_policy=runtime_policy,
            )
        success_resume_command = record_llm_resume(meta.setdefault("llm", {}), followup_result.resume)
        if codex_meta is not None:
            codex_resume = (
                CodexResumeInfo(
                    session_id=followup_result.resume.session_id,
                    cwd=followup_result.resume.cwd,
                    command=followup_result.resume.command,
                )
                if followup_result.resume is not None and followup_result.resume.provider == "codex"
                else None
            )
            record_codex_resume(meta.setdefault("codex", {}), codex_resume)

        verdicts = extract_review_verdicts_from_markdown(followup_md_path.read_text(encoding="utf-8"))
        followup_entry: dict[str, Any] = {
            "started_at": followup_started_at,
            "completed_at": _utc_now_iso(),
            "no_update": (not update_enabled),
            "head_sha_before": head_before,
            "head_sha_after": head_after,
            "template_id": builtin_prompt_id(followup_template_name),
            "output_path": str(followup_md_path),
            "verdicts": review_verdicts_to_meta(verdicts) if verdicts is not None else None,
            "llm": {
                "preset": llm_resolved.get("preset"),
                "transport": llm_resolved.get("transport"),
                "provider": llm_resolved.get("provider"),
                "model": llm_resolved.get("model"),
                "reasoning_effort": llm_resolved.get("reasoning_effort"),
                "plan_reasoning_effort": llm_resolved.get("plan_reasoning_effort"),
                "capabilities": llm_resolved.get("capabilities"),
            },
            "helpers": {"rf_jira": runtime_policy["staged_paths"].get("rf_jira")},
            "agent_runtime": runtime_policy["metadata"],
            "review_intelligence": dict(review_intelligence_meta["review_intelligence"]),
        }
        if codex_meta is not None:
            followup_entry["codex"] = {"config": codex_meta, "flags": codex_flags}
            followup_codex_meta = followup_entry.get("codex")
            if isinstance(followup_codex_meta, dict):
                record_codex_resume(followup_codex_meta, codex_resume)
        followup_llm_meta = followup_entry.get("llm")
        if isinstance(followup_llm_meta, dict):
            record_llm_resume(followup_llm_meta, followup_result.resume)
        meta.setdefault("followups", []).append(followup_entry)
        write_redacted_json(meta_path, meta)

        success_markdown_path = followup_md_path
        print(str(followup_md_path))
        return 0
    finally:
        cleanup_sensitive_staged_paths((runtime_policy or {}).get("staged_paths"))
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
    verdicts: ReviewVerdicts | None
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
    verdicts = normalize_review_verdicts(entry.get("verdicts"))
    if verdicts is None:
        legacy = normalize_review_verdict(entry.get("decision"))
        if legacy is not None:
            verdicts = ReviewVerdicts(business=legacy, technical=legacy)
    verdicts_text = format_review_verdicts_compact(verdicts)
    completed_at = str(entry.get("completed_at") or "?").strip() or "?"
    target_head_sha = _short_sha(str(entry.get("target_head_sha") or "").strip(), length=12)
    path = str(entry.get("path") or "?").strip() or "?"
    if markdown:
        return (
            f"- `{session_id}`"
            f" • `{kind}`"
            f" • {verdicts_text}"
            f" • {completed_at}"
            f" • head `{target_head_sha}`"
            f" • `{path}`"
        )
    return (
        f"- {session_id}"
        f" [{kind}]"
        f" {verdicts_text}"
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
        if review_md_path.is_file() and review_head_sha and (review_head_sha == head):
            review_verdicts = _resolve_session_verdicts(
                meta_path=entry / "meta.json",
                meta=meta,
                review_md_path=review_md_path,
            )
            if not review_verdicts_include_reject(review_verdicts):
                cand = ZipSourceArtifact(
                    session_id=session_id,
                    session_dir=session_dir,
                    kind="review",
                    artifact_path=review_md_path,
                    completed_at=review_completed_at,
                    verdicts=review_verdicts,
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
            fu_verdicts = _resolve_artifact_verdicts(meta=fu, artifact_path=fu_path)
            if review_verdicts_include_reject(fu_verdicts):
                continue
            cand = ZipSourceArtifact(
                session_id=session_id,
                session_dir=session_dir,
                kind="followup",
                artifact_path=fu_path,
                completed_at=fu_completed_at,
                verdicts=fu_verdicts,
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


def zip_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    global _ACTIVE_OUTPUT
    effective_config_path = config_path or default_reviewflow_config_path()
    effective_codex_base_config_path = codex_base_config_path or default_codex_base_config_path()
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
            f"zip: no completed non-rejected review artifacts found for PR HEAD {head_sha[:12]}.\n"
            "Run a fresh review or follow-up first:\n"
            f"  {PRIMARY_CLI_COMMAND} pr {pr_url}\n"
            "  # or\n"
            f"  {PRIMARY_CLI_COMMAND} followup <session_id>"
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
                "verdicts": review_verdicts_to_meta(src.verdicts) if src.verdicts is not None else None,
                "target_head_sha": src.target_head_sha,
            }
        )
        when = src.completed_at or ""
        verdicts = format_review_verdicts_compact(src.verdicts)
        inputs_lines.append(
            f"- {src.session_id} ({src.kind}, {when}, {verdicts})  `{src.artifact_path}`"
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
    runtime_policy: dict[str, Any] | None = None
    try:
        llm_resolved, llm_resolution_meta = resolve_llm_config_from_args(
            args,
            reviewflow_config_path=effective_config_path,
            base_codex_config_path=effective_codex_base_config_path,
        )
        runtime_policy = prepare_review_agent_runtime(
            args=args,
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            reviewflow_config_path=effective_config_path,
            config_enabled=True,
            repo_dir=host_repo_dir,
            session_dir=host_session_dir,
            work_dir=host_work_dir,
            base_env={},
            chunkhound_config_path=None,
            chunkhound_db_path=None,
            chunkhound_cwd=None,
            enable_mcp=False,
            interactive=False,
            paths=paths,
        )
        env = dict(runtime_policy["env"])
        codex_flags = list(runtime_policy.get("codex_flags") or [])
        codex_meta: dict[str, Any] | None = None
        if str(llm_resolved.get("provider") or "") == "codex":
            codex_meta = build_codex_flags_from_llm_config(
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                include_sandbox=False,
            )[1]

        template_name = "mrereview_zip.md"
        template_text = load_builtin_prompt_text(template_name)
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
            "template_id": builtin_prompt_id(template_name),
            "prompt_chars": len(rendered),
            "prompt_sha256": sha256_text(rendered),
        }
        zip_progress.meta["llm"] = build_llm_meta(
            resolved=llm_resolved,
            resolution_meta=llm_resolution_meta,
            env=env,
            adapter_meta={
                "transport": f"cli-{llm_resolved.get('provider')}",
                "runtime_policy": runtime_policy["metadata"],
                "config_overrides": list(runtime_policy.get("codex_config_overrides") or []),
                "flags": codex_flags,
            },
        )
        zip_progress.meta["agent_runtime"] = runtime_policy["metadata"]
        if codex_meta is not None:
            zip_progress.meta["codex"] = {
                "config": codex_meta,
                "dangerously_bypass_approvals_and_sandbox": runtime_policy[
                    "dangerously_bypass_approvals_and_sandbox"
                ],
                "config_overrides": list(runtime_policy.get("codex_config_overrides") or []),
                "flags": codex_flags,
                "env": {
                    "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
                },
            }
        zip_progress.flush()

        zip_progress.set_phase("codex_zip")
        with phase("codex_zip", progress=zip_progress, quiet=quiet):
            zip_result = run_llm_exec(
                repo_dir=host_repo_dir,
                resolved=llm_resolved,
                resolution_meta=llm_resolution_meta,
                output_path=output_md_path,
                prompt=rendered,
                env=env,
                stream=stream,
                progress=zip_progress,
                add_dirs=list(runtime_policy.get("add_dirs") or []),
                codex_config_overrides=list(runtime_policy.get("codex_config_overrides") or []),
                runtime_policy=runtime_policy,
            )
        success_resume_command = record_llm_resume(
            zip_progress.meta.setdefault("llm", {}), zip_result.resume
        )
        if codex_meta is not None:
            codex_resume = (
                CodexResumeInfo(
                    session_id=zip_result.resume.session_id,
                    cwd=zip_result.resume.cwd,
                    command=zip_result.resume.command,
                )
                if zip_result.resume is not None and zip_result.resume.provider == "codex"
                else None
            )
            record_codex_resume(zip_progress.meta.setdefault("codex", {}), codex_resume)
        zip_progress.flush()

        normalize_markdown_artifact(markdown_path=output_md_path, session_dir=host_session_dir)
        append_zip_inputs_provenance(markdown_path=output_md_path, inputs_meta=inputs_meta)
        verdicts = persist_review_verdicts_from_markdown(meta=zip_progress.meta, markdown_path=output_md_path)
        if verdicts is not None:
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
            "verdicts": review_verdicts_to_meta(verdicts) if verdicts is not None else None,
            "inputs": inputs_meta,
            "prompt": zip_progress.meta.get("prompt"),
            "llm": {
                "preset": llm_resolved.get("preset"),
                "transport": llm_resolved.get("transport"),
                "provider": llm_resolved.get("provider"),
                "model": llm_resolved.get("model"),
                "reasoning_effort": llm_resolved.get("reasoning_effort"),
                "plan_reasoning_effort": llm_resolved.get("plan_reasoning_effort"),
                "capabilities": llm_resolved.get("capabilities"),
            },
        }
        if codex_meta is not None:
            zip_entry["codex"] = {"config": codex_meta, "flags": codex_flags}
            zip_codex_meta = zip_entry.get("codex")
            if isinstance(zip_codex_meta, dict):
                record_codex_resume(zip_codex_meta, codex_resume)
        zip_llm_meta = zip_entry.get("llm")
        if isinstance(zip_llm_meta, dict):
            record_llm_resume(zip_llm_meta, zip_result.resume)
        host_meta2.setdefault("zips", []).append(zip_entry)
        write_redacted_json(host_meta_path, host_meta2)

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
        cleanup_sensitive_staged_paths((runtime_policy or {}).get("staged_paths"))
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
    verdicts: ReviewVerdicts | None
    codex_summary: str = "codex=?"
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
    verdicts: ReviewVerdicts | None
    codex_summary: str
    resume_command: str
    provider: str = "codex"
    supports_resume: bool = True

    def sort_dt(self) -> datetime:
        return (
            _parse_iso_dt(self.completed_at)
            or _parse_iso_dt(self.created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )


@dataclass(frozen=True)
class CleanupSession:
    session_id: str
    session_dir: Path
    host: str
    owner: str
    repo: str
    number: int
    repo_slug: str
    title: str
    status: str
    created_at: str | None
    completed_at: str | None
    failed_at: str | None
    resumed_at: str | None = None
    verdicts: ReviewVerdicts | None = None
    codex_summary: str = "codex=?"
    size_bytes: int = 0
    path_display: str = ""
    is_running: bool = False
    is_recent: bool = False
    is_risky: bool = False

    def activity_dt(self) -> datetime:
        return (
            _parse_iso_dt(self.completed_at)
            or _parse_iso_dt(self.failed_at)
            or _parse_iso_dt(self.resumed_at)
            or _parse_iso_dt(self.created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )

    def age_td(self, *, now: datetime) -> timedelta:
        delta = now - self.activity_dt()
        if delta.total_seconds() < 0:
            return timedelta(0)
        return delta


CLEANUP_PRESET_ALL = "all"
CLEANUP_PRESET_DONE = "done"
CLEANUP_PRESET_ERROR = "error"
CLEANUP_PRESET_RUNNING = "running"
CLEANUP_PRESET_DONE_OLDER_24H = "done_older_24h"
CLEANUP_PRESET_DONE_OLDER_7D = "done_older_7d"
CLEANUP_PRESET_DONE_OLDER_30D = "done_older_30d"

CLEANUP_PRESET_CHOICES = (
    CLEANUP_PRESET_ALL,
    CLEANUP_PRESET_DONE,
    CLEANUP_PRESET_ERROR,
    CLEANUP_PRESET_RUNNING,
    CLEANUP_PRESET_DONE_OLDER_24H,
    CLEANUP_PRESET_DONE_OLDER_7D,
    CLEANUP_PRESET_DONE_OLDER_30D,
)

CLEANUP_PRESET_LABELS: dict[str, str] = {
    CLEANUP_PRESET_ALL: "1:All",
    CLEANUP_PRESET_DONE: "2:Done",
    CLEANUP_PRESET_ERROR: "3:Error",
    CLEANUP_PRESET_RUNNING: "4:Running",
    CLEANUP_PRESET_DONE_OLDER_24H: "5:Done>24h",
    CLEANUP_PRESET_DONE_OLDER_7D: "6:Done>7d",
    CLEANUP_PRESET_DONE_OLDER_30D: "7:Done>30d",
}

CLEANUP_SORT_NEWEST = "newest"
CLEANUP_SORT_OLDEST = "oldest"
CLEANUP_SORT_LARGEST = "largest"
CLEANUP_SORT_CHOICES = (CLEANUP_SORT_NEWEST, CLEANUP_SORT_OLDEST, CLEANUP_SORT_LARGEST)


def _cleanup_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_age_short(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 3600:
        mins = max(1, seconds // 60) if seconds else 0
        return f"{mins}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _format_size_short(size_bytes: int) -> str:
    size = max(0, int(size_bytes))
    units = ["B", "K", "M", "G", "T"]
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)}{unit}"
    if value >= 10:
        return f"{int(round(value))}{unit}"
    return f"{value:.1f}{unit}"


def _cleanup_session_status(session: CleanupSession) -> str:
    status = str(session.status or "").strip().lower()
    if not status:
        return "unknown"
    return status


def _cleanup_pr_key(session: CleanupSession) -> tuple[str, str, str, int] | None:
    if not session.host or not session.owner or not session.repo or int(session.number) <= 0:
        return None
    return (session.host, session.owner, session.repo, int(session.number))


def resolve_cleanup_pr_states(
    *,
    sessions: list[CleanupSession],
    on_progress: Any | None = None,
) -> tuple[dict[tuple[str, str, str, int], str], dict[tuple[str, str, str, int], str]]:
    states: dict[tuple[str, str, str, int], str] = {}
    skipped: dict[tuple[str, str, str, int], str] = {}
    seen_hosts: set[str] = set()
    unique_keys: list[tuple[str, str, str, int]] = []
    seen_keys: set[tuple[str, str, str, int]] = set()
    for session in sessions:
        key = _cleanup_pr_key(session)
        if key is None or key in seen_keys:
            continue
        seen_keys.add(key)
        unique_keys.append(key)

    total = len(unique_keys)
    for idx, key in enumerate(unique_keys, start=1):
        if on_progress is not None:
            try:
                on_progress(idx, total, key)
            except Exception:
                pass
        host, owner, repo, number = key
        if host not in seen_hosts:
            require_gh_auth(host)
            seen_hosts.add(host)
        try:
            proc = run_cmd(
                [
                    "gh",
                    "api",
                    "--hostname",
                    host,
                    f"repos/{owner}/{repo}/pulls/{number}",
                ]
            )
            payload = json.loads(proc.stdout)
        except Exception as e:
            skipped[key] = str(e)
            continue
        if not isinstance(payload, dict):
            skipped[key] = "invalid gh api payload"
            continue
        merged_at = str(payload.get("merged_at") or "").strip()
        state = str(payload.get("state") or "").strip().lower()
        if merged_at:
            states[key] = "merged"
        elif state == "closed":
            states[key] = "closed"
        elif state == "open":
            states[key] = "open"
        else:
            skipped[key] = f"unknown PR state: {state or '?'}"
    return states, skipped


def _cleanup_session_matches_preset(
    session: CleanupSession, *, preset: str, now: datetime
) -> bool:
    status = _cleanup_session_status(session)
    age = session.age_td(now=now)
    if preset == CLEANUP_PRESET_ALL:
        return True
    if preset == CLEANUP_PRESET_DONE:
        return status == "done"
    if preset == CLEANUP_PRESET_ERROR:
        return status == "error"
    if preset == CLEANUP_PRESET_RUNNING:
        return status == "running"
    if preset == CLEANUP_PRESET_DONE_OLDER_24H:
        return status == "done" and age >= timedelta(days=1)
    if preset == CLEANUP_PRESET_DONE_OLDER_7D:
        return status == "done" and age >= timedelta(days=7)
    if preset == CLEANUP_PRESET_DONE_OLDER_30D:
        return status == "done" and age >= timedelta(days=30)
    return True


def _cleanup_session_matches_query(session: CleanupSession, *, query: str) -> bool:
    needle = str(query or "").strip().lower()
    if not needle:
        return True
    haystacks = [
        session.session_id,
        session.repo_slug,
        session.title,
        session.status,
        session.path_display,
    ]
    if "#" in session.repo_slug:
        haystacks.append(session.repo_slug.split("#", 1)[-1])
    for item in haystacks:
        if needle in str(item or "").lower():
            return True
    return False


def _cleanup_sort_key(session: CleanupSession, *, sort: str) -> tuple[Any, ...]:
    if sort == CLEANUP_SORT_OLDEST:
        return (session.activity_dt(), session.session_id)
    if sort == CLEANUP_SORT_LARGEST:
        return (-int(session.size_bytes), -session.activity_dt().timestamp(), session.session_id)
    return (-session.activity_dt().timestamp(), session.session_id)


def _cleanup_dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    total += int(child.stat().st_size)
            except Exception:
                continue
    except Exception:
        return 0
    return total


@dataclass
class CleanupUiState:
    sessions: list[CleanupSession]
    preset: str = CLEANUP_PRESET_ALL
    query: str = ""
    sort: str = CLEANUP_SORT_NEWEST
    cursor: int = 0
    selected_ids: set[str] = field(default_factory=set)
    message: str = ""

    def visible_sessions(self, *, now: datetime | None = None) -> list[CleanupSession]:
        ref_now = now or _cleanup_now()
        visible = [
            session
            for session in self.sessions
            if _cleanup_session_matches_preset(session, preset=self.preset, now=ref_now)
            and _cleanup_session_matches_query(session, query=self.query)
        ]
        visible.sort(key=lambda s: _cleanup_sort_key(s, sort=self.sort))
        return visible

    def clamp_cursor(self, *, now: datetime | None = None) -> None:
        visible = self.visible_sessions(now=now)
        if not visible:
            self.cursor = 0
            return
        self.cursor = max(0, min(self.cursor, len(visible) - 1))

    def move_cursor(self, delta: int, *, now: datetime | None = None) -> None:
        visible = self.visible_sessions(now=now)
        if not visible:
            self.cursor = 0
            return
        self.cursor = max(0, min(self.cursor + int(delta), len(visible) - 1))

    def current_session(self, *, now: datetime | None = None) -> CleanupSession | None:
        visible = self.visible_sessions(now=now)
        if not visible:
            return None
        self.clamp_cursor(now=now)
        return visible[self.cursor]

    def toggle_current(self, *, now: datetime | None = None) -> None:
        current = self.current_session(now=now)
        if current is None:
            return
        if current.session_id in self.selected_ids:
            self.selected_ids.remove(current.session_id)
        else:
            self.selected_ids.add(current.session_id)

    def select_all_visible(self, *, now: datetime | None = None) -> None:
        for session in self.visible_sessions(now=now):
            self.selected_ids.add(session.session_id)

    def invert_visible_selection(self, *, now: datetime | None = None) -> None:
        visible_ids = {session.session_id for session in self.visible_sessions(now=now)}
        for session_id in visible_ids:
            if session_id in self.selected_ids:
                self.selected_ids.remove(session_id)
            else:
                self.selected_ids.add(session_id)

    def clear_selection(self) -> None:
        self.selected_ids.clear()

    def cycle_sort(self) -> None:
        idx = CLEANUP_SORT_CHOICES.index(self.sort) if self.sort in CLEANUP_SORT_CHOICES else 0
        self.sort = CLEANUP_SORT_CHOICES[(idx + 1) % len(CLEANUP_SORT_CHOICES)]

    def set_preset(self, preset: str, *, now: datetime | None = None) -> None:
        if preset not in CLEANUP_PRESET_CHOICES:
            return
        self.preset = preset
        self.clamp_cursor(now=now)

    def selected_sessions(self) -> list[CleanupSession]:
        by_id = {session.session_id: session for session in self.sessions}
        selected = [by_id[session_id] for session_id in self.selected_ids if session_id in by_id]
        selected.sort(key=lambda s: (-s.activity_dt().timestamp(), s.session_id))
        return selected

    def selected_size_bytes(self) -> int:
        return sum(int(session.size_bytes) for session in self.selected_sessions())

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


def _resolve_session_verdicts(
    *, meta_path: Path, meta: dict[str, Any], review_md_path: Path
) -> ReviewVerdicts | None:
    stored = normalize_review_verdicts(meta.get("verdicts"))
    if stored is not None:
        normalized = review_verdicts_to_meta(stored)
        if meta.get("verdicts") != normalized:
            meta["verdicts"] = normalized
            try:
                write_redacted_json(meta_path, meta)
            except Exception:
                pass
        return stored

    legacy = normalize_review_verdict(meta.get("decision"))
    if legacy is not None:
        verdicts = ReviewVerdicts(business=legacy, technical=legacy)
        meta["verdicts"] = review_verdicts_to_meta(verdicts)
        try:
            write_redacted_json(meta_path, meta)
        except Exception:
            pass
        return verdicts

    extracted = extract_review_verdicts_from_markdown(review_md_path.read_text(encoding="utf-8"))
    if extracted is not None:
        meta["verdicts"] = review_verdicts_to_meta(extracted)
        try:
            write_redacted_json(meta_path, meta)
        except Exception:
            pass
    return extracted


def _resolve_artifact_verdicts(*, meta: dict[str, Any], artifact_path: Path) -> ReviewVerdicts | None:
    stored = normalize_review_verdicts(meta.get("verdicts"))
    if stored is not None:
        return stored
    legacy = normalize_review_verdict(meta.get("decision"))
    if legacy is not None:
        return ReviewVerdicts(business=legacy, technical=legacy)
    try:
        return extract_review_verdicts_from_markdown(artifact_path.read_text(encoding="utf-8"))
    except Exception:
        return None


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

        verdicts = _resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path)
        review_head_sha = _resolve_session_review_head_sha(meta=meta)
        codex_summary = resolve_codex_summary(meta)

        sessions.append(
            HistoricalReviewSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                review_md_path=review_md_path,
                created_at=str(meta.get("created_at") or "").strip() or None,
                completed_at=str(meta.get("completed_at") or "").strip() or None,
                verdicts=verdicts,
                codex_summary=codex_summary,
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

        llm_meta = resolve_meta_llm(meta)
        llm_resume = llm_meta.get("resume") if isinstance(llm_meta.get("resume"), dict) else {}
        resume_command = str((llm_resume or {}).get("command") or "").strip()
        supports_resume = bool(((llm_meta.get("capabilities") or {}).get("supports_resume")))

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
        verdicts = _resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path)
        codex_summary = resolve_codex_summary(meta)
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
                verdicts=verdicts,
                codex_summary=codex_summary,
                resume_command=resume_command,
                provider=str(llm_meta.get("provider") or "unknown").strip() or "unknown",
                supports_resume=supports_resume,
            )
        )

    sessions.sort(key=lambda s: s.sort_dt(), reverse=True)
    return sessions


def scan_cleanup_sessions(*, sandbox_root: Path) -> list[CleanupSession]:
    root = sandbox_root
    if not root.is_dir():
        return []

    now = _cleanup_now()
    sessions: list[CleanupSession] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        meta = _load_session_meta(meta_path)
        if not meta:
            continue

        host = str(meta.get("host") or "").strip() or "?"
        owner = str(meta.get("owner") or "").strip() or "?"
        repo = str(meta.get("repo") or "").strip() or "?"
        raw_number = meta.get("number")
        try:
            number = int(raw_number)
        except Exception:
            number = 0
        repo_slug = f"{owner}/{repo}#{number if number else '?'}"
        if host not in {"", "?", "github.com"}:
            repo_slug = f"{host}:{repo_slug}"

        review_md_path = _resolve_session_review_md_path(session_dir=entry, meta=meta)
        verdicts = None
        if review_md_path is not None:
            verdicts = _resolve_session_verdicts(meta_path=meta_path, meta=meta, review_md_path=review_md_path)

        created_at = str(meta.get("created_at") or "").strip() or None
        completed_at = str(meta.get("completed_at") or "").strip() or None
        failed_at = str(meta.get("failed_at") or "").strip() or None
        resumed_at = str(meta.get("resumed_at") or "").strip() or None
        status = str(meta.get("status") or "").strip().lower() or "unknown"
        activity_dt = (
            _parse_iso_dt(completed_at)
            or _parse_iso_dt(failed_at)
            or _parse_iso_dt(resumed_at)
            or _parse_iso_dt(created_at)
            or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        age = now - activity_dt
        if age.total_seconds() < 0:
            age = timedelta(0)

        sessions.append(
            CleanupSession(
                session_id=str(meta.get("session_id") or entry.name),
                session_dir=entry,
                host=host,
                owner=owner,
                repo=repo,
                number=number,
                repo_slug=repo_slug,
                title=str(meta.get("title") or "").strip(),
                status=status,
                created_at=created_at,
                completed_at=completed_at,
                failed_at=failed_at,
                resumed_at=resumed_at,
                verdicts=verdicts,
                codex_summary=resolve_codex_summary(meta),
                size_bytes=_cleanup_dir_size_bytes(entry),
                path_display=str(entry),
                is_running=(status == "running"),
                is_recent=(age < timedelta(days=1)),
                is_risky=(status == "running" or age < timedelta(days=1)),
            )
        )

    sessions.sort(key=lambda s: (-s.activity_dt().timestamp(), s.session_id))
    return sessions


def _print_historical_sessions(sessions: list[HistoricalReviewSession]) -> None:
    for idx, s in enumerate(sessions, start=1):
        when = s.completed_at or s.created_at or ""
        verdicts = format_review_verdicts_compact(s.verdicts)
        print(f"{idx:02d}  {when}  {verdicts}  {s.codex_summary}  {s.session_id}")


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
            verdicts = format_review_verdicts_compact(session.verdicts)
            lines.append(f"  {idx}) {when}  {verdicts}  {session.codex_summary}  {session.session_id}")
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
        stderr.write("Past review sessions (newest first):\n")
        for idx, s in enumerate(sessions, start=1):
            when = s.completed_at or s.created_at or ""
            verdicts = format_review_verdicts_compact(s.verdicts)
            resumable = "" if s.supports_resume else f"  [exec-only:{s.provider}]"
            stderr.write(
                f"  {idx}) {when}  {verdicts}  {s.codex_summary}  {s.repo_slug}  {s.session_id}{resumable}\n"
            )
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
    *,
    session: InteractiveReviewSession,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
) -> tuple[str, dict[str, str]]:
    effective_config_path = config_path or default_reviewflow_config_path()
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

    ensure_review_config(paths, config_path=effective_config_path)
    chunkhound_cfg, chunkhound_meta, resolved_chunkhound_cfg = load_chunkhound_runtime_config(
        config_path=effective_config_path,
        require=True,
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    work_tmp_dir.mkdir(parents=True, exist_ok=True)
    chunkhound_work_dir.mkdir(parents=True, exist_ok=True)
    materialize_chunkhound_env_config(
        resolved_config=resolved_chunkhound_cfg,
        output_config_path=chunkhound_cfg_path,
        database_provider="duckdb",
        database_path=chunkhound_db_path,
    )
    meta["chunkhound"] = chunkhound_meta["chunkhound"]

    saved_llm_meta = resolve_meta_llm(meta)
    provider = str(saved_llm_meta.get("provider") or "unknown").strip() or "unknown"
    if not bool(((saved_llm_meta.get("capabilities") or {}).get("supports_resume"))):
        raise ReviewflowError(
            f"interactive is not supported for provider {provider} in v1. "
            "This session is execution-only."
        )
    saved_resolution_meta = (
        saved_llm_meta.get("config") if isinstance(saved_llm_meta.get("config"), dict) else {}
    )
    llm_meta = dict(saved_llm_meta)
    llm_resolution_meta = dict(saved_resolution_meta)
    saved_preset_name = (
        str(saved_llm_meta.get("selected_name") or "").strip()
        or str(saved_llm_meta.get("preset") or "").strip()
        or None
    )
    try:
        llm_meta, llm_resolution_meta = resolve_llm_config(
            base_codex_config_path=default_codex_base_config_path(),
            reviewflow_config_path=effective_config_path,
            cli_preset=saved_preset_name,
            cli_model=(str(saved_llm_meta.get("model") or "").strip() or None),
            cli_effort=(str(saved_llm_meta.get("reasoning_effort") or "").strip() or None),
            cli_plan_effort=(str(saved_llm_meta.get("plan_reasoning_effort") or "").strip() or None),
            cli_verbosity=(str(saved_llm_meta.get("text_verbosity") or "").strip() or None),
            cli_max_output_tokens=(
                int(saved_llm_meta.get("max_output_tokens"))
                if isinstance(saved_llm_meta.get("max_output_tokens"), int)
                else None
            ),
            cli_request_overrides={},
            cli_header_overrides={},
            deprecated_codex_model=None,
            deprecated_codex_effort=None,
            deprecated_codex_plan_effort=None,
        )
    except ReviewflowError:
        llm_meta = dict(saved_llm_meta)
        llm_resolution_meta = dict(saved_resolution_meta)

    saved_runtime_meta = meta.get("agent_runtime") if isinstance(meta.get("agent_runtime"), dict) else {}
    runtime_policy = prepare_review_agent_runtime(
        args=argparse.Namespace(
            agent_runtime_profile=(saved_runtime_meta.get("profile") if isinstance(saved_runtime_meta, dict) else None)
        ),
        resolved=llm_meta,
        resolution_meta=llm_resolution_meta,
        reviewflow_config_path=effective_config_path,
        config_enabled=True,
        repo_dir=repo_dir,
        session_dir=session.session_dir,
        work_dir=work_dir,
        base_env=chunkhound_env(source_config_path=chunkhound_cfg.base_config_path),
        chunkhound_config_path=chunkhound_cfg_path,
        chunkhound_db_path=chunkhound_db_path,
        chunkhound_cwd=chunkhound_work_dir,
        enable_mcp=True,
        interactive=True,
        paths=paths,
    )
    env = dict(runtime_policy["env"])

    llm_resume = llm_meta.get("resume") if isinstance(llm_meta.get("resume"), dict) else {}
    resume_session_id = str((llm_resume or {}).get("session_id") or "").strip()
    meta_paths = dict(meta_paths or {})
    meta_paths["work_dir"] = str(work_dir)
    meta_paths["work_tmp_dir"] = str(work_tmp_dir)
    meta_paths["chunkhound_cwd"] = str(chunkhound_work_dir)
    meta_paths["chunkhound_db"] = str(chunkhound_db_path)
    meta_paths["chunkhound_config"] = str(chunkhound_cfg_path)
    meta["paths"] = meta_paths
    meta["llm"] = llm_meta
    meta["agent_runtime"] = runtime_policy["metadata"]

    if provider == "codex":
        codex_meta = meta.get("codex") if isinstance(meta.get("codex"), dict) else {}
        resume_meta = codex_meta.get("resume") if isinstance(codex_meta.get("resume"), dict) else {}
        resume_session_id = str((resume_meta or {}).get("session_id") or "").strip()
        resume_session_id = _resolve_top_level_codex_session_id(
            codex_root=real_user_home_dir() / ".codex",
            session_id=resume_session_id,
            created_at=str(meta.get("created_at") or "").strip() or None,
            completed_at=str(meta.get("completed_at") or "").strip() or None,
        )

        codex_flags = list(runtime_policy.get("codex_flags") or [])
        codex_overrides = list(runtime_policy.get("codex_config_overrides") or [])

        codex_meta["config_overrides"] = codex_overrides
        codex_meta["env"] = {
            "GH_CONFIG_DIR": env.get("GH_CONFIG_DIR"),
            "JIRA_CONFIG_FILE": env.get("JIRA_CONFIG_FILE"),
            "NETRC": env.get("NETRC"),
            "REVIEWFLOW_WORK_DIR": env.get("REVIEWFLOW_WORK_DIR"),
        }
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
            write_redacted_json(meta_path, meta)
            return (fallback_command, env)

        command = build_codex_resume_command(
            repo_dir=repo_dir,
            session_id=resume_session_id,
            env=env,
            codex_flags=codex_flags,
            codex_config_overrides=codex_overrides,
            add_dirs=None,
            approval_policy=(runtime_policy.get("approval_policy") if isinstance(runtime_policy, dict) else None),
            dangerously_bypass_approvals_and_sandbox=bool(
                runtime_policy.get("dangerously_bypass_approvals_and_sandbox", True)
            ),
            include_shell_environment_inherit_all=bool(
                runtime_policy.get("include_shell_environment_inherit_all", False)
            ),
        )
        record_codex_resume(
            codex_meta,
            CodexResumeInfo(session_id=resume_session_id, cwd=repo_dir, command=command),
        )
        record_llm_resume(
            llm_meta,
            LlmResumeInfo(provider="codex", session_id=resume_session_id, cwd=repo_dir, command=command),
        )
        meta["llm"] = llm_meta
        meta["codex"] = codex_meta
        write_redacted_json(meta_path, meta)
        return (command, env)

    if provider == "claude":
        if not resume_session_id:
            fallback_command = str((llm_resume or {}).get("command") or "").strip()
            if not fallback_command:
                raise ReviewflowError(f"Session {session.session_id} is missing llm.resume metadata.")
            write_redacted_json(meta_path, meta)
            return (fallback_command, env)
        command = build_claude_resume_command(
            repo_dir=repo_dir,
            session_id=resume_session_id,
            env=env,
            command="claude",
            runtime_policy=runtime_policy,
        )
        record_llm_resume(
            llm_meta,
            LlmResumeInfo(provider="claude", session_id=resume_session_id, cwd=repo_dir, command=command),
        )
        meta["llm"] = llm_meta
        write_redacted_json(meta_path, meta)
        return (command, env)

    raise ReviewflowError(
        f"interactive is not supported for provider {provider} in v1. This session is execution-only."
    )


def interactive_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
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
                f"No completed review sessions found for {target} under {paths.sandbox_root}."
            )
        raise ReviewflowError(f"No completed review sessions found under {paths.sandbox_root}.")

    selected = _choose_interactive_review_session_tty(sessions, stdin=in_stream, stderr=err_stream)
    if selected is None:
        return 0
    if not selected.supports_resume:
        raise ReviewflowError(
            f"interactive is not supported for provider {selected.provider} in v1. "
            "This session is execution-only."
        )

    resume_command, resume_env = build_interactive_resume_command(
        session=selected,
        paths=paths,
        config_path=config_path,
    )
    try:
        err_stream.write(f"\nLatest review artifact: {selected.latest_artifact_path}\n")
        err_stream.write(f"\nContinuing {selected.repo_slug} ({selected.session_id})...\n")
        err_stream.flush()
    except Exception:
        pass
    try:
        return run_interactive_resume_command(resume_command, env=resume_env)
    finally:
        cleanup_sensitive_staged_paths(
            {
                "gh_config_dir": resume_env.get("GH_CONFIG_DIR"),
                "jira_config_file": resume_env.get("JIRA_CONFIG_FILE"),
                "netrc": resume_env.get("NETRC"),
            }
        )


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
                codex_summary = resolve_codex_summary(data) if isinstance(data, dict) else "codex=?"
                print(
                    f"{data.get('session_id')}  {data.get('owner')}/{data.get('repo')}#{data.get('number')}  "
                    f"{data.get('created_at')}  {codex_summary}"
                )
            except Exception:
                print(entry.name)
        else:
            print(entry.name)
    return 0


def _clean_color_enabled(stream: TextIO) -> bool:
    return _historical_picker_color_enabled(stream)


def _clean_wrap(text: str, code: str, *, color: bool) -> str:
    if not color:
        return text
    return f"{code}{text}\x1b[0m"


def _clean_fit(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _clean_terminal_size(stream: TextIO) -> tuple[int, int]:
    try:
        fd = stream.fileno()
    except Exception:
        fd = None
    if fd is not None:
        try:
            size = os.get_terminal_size(fd)
            return (max(60, int(size.columns)), max(12, int(size.lines)))
        except OSError:
            pass
    fallback = shutil.get_terminal_size(fallback=(120, 32))
    return (max(60, int(fallback.columns)), max(12, int(fallback.lines)))


@contextlib.contextmanager
def _clean_tty_mode(stream: TextIO):
    try:
        fd = stream.fileno()
    except Exception:
        fd = None
    if fd is None:
        yield
        return
    try:
        old_attrs = termios.tcgetattr(fd)
    except Exception:
        yield
        return
    try:
        tty.setcbreak(fd)
        yield
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        except Exception:
            pass


@contextlib.contextmanager
def _clean_fullscreen(*, input_stream: TextIO, output_stream: TextIO):
    try:
        is_tty = bool(output_stream.isatty())
    except Exception:
        is_tty = False
    try:
        if is_tty:
            output_stream.write("\x1b[?1049h\x1b[?25l")
            output_stream.flush()
        with _clean_tty_mode(input_stream):
            yield
    finally:
        try:
            if is_tty:
                output_stream.write("\x1b[?25h\x1b[?1049l")
                output_stream.flush()
        except Exception:
            pass


def _read_cleanup_key(stream: TextIO) -> str | None:
    try:
        fd = stream.fileno()
    except Exception:
        fd = None

    def read_char(*, timeout: float | None = None) -> str:
        if fd is None:
            if timeout is not None and timeout > 0:
                # Non-fd test streams cannot be polled; consume whatever is already buffered.
                try:
                    return stream.read(1)
                except Exception:
                    return ""
            try:
                return stream.read(1)
            except Exception:
                return ""
        if timeout is not None:
            try:
                ready, _, _ = select.select([fd], [], [], timeout)
            except Exception:
                return ""
            if not ready:
                return ""
        try:
            chunk = os.read(fd, 1)
        except Exception:
            return ""
        if not chunk:
            return ""
        return chunk.decode("utf-8", errors="ignore")

    try:
        ch = read_char()
    except KeyboardInterrupt:
        return None
    if ch == "":
        return None
    if ch != "\x1b":
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == "\x7f":
            return "BACKSPACE"
        return ch

    tail = ""
    if fd is None:
        try:
            tail += stream.read(4)
        except Exception:
            pass
    else:
        nxt = read_char(timeout=0.05)
        if nxt:
            tail += nxt
            deadline = time.time() + 0.02
            while time.time() < deadline and len(tail) < 6:
                nxt = read_char(timeout=0.003)
                if not nxt:
                    break
                tail += nxt
                if nxt.isalpha() or nxt == "~":
                    break
    seq = ch + tail
    if seq.startswith("\x1b[A") or seq.startswith("\x1bOA"):
        return "UP"
    if seq.startswith("\x1b[B") or seq.startswith("\x1bOB"):
        return "DOWN"
    if seq.startswith("\x1b[C") or seq.startswith("\x1bOC"):
        return "RIGHT"
    if seq.startswith("\x1b[D") or seq.startswith("\x1bOD"):
        return "LEFT"
    return "ESC"


def _render_clean_screen(
    *,
    stderr: TextIO,
    state: CleanupUiState,
    now: datetime,
    color: bool,
    help_mode: bool = False,
    prompt: str | None = None,
    prompt_value: str = "",
    confirm_lines: list[str] | None = None,
) -> None:
    width, height = _clean_terminal_size(stderr)
    visible = state.visible_sessions(now=now)
    state.clamp_cursor(now=now)
    selected = state.selected_sessions()
    selected_size = _format_size_short(state.selected_size_bytes())
    header = (
        f"{PRIMARY_CLI_COMMAND} clean  preset={CLEANUP_PRESET_LABELS.get(state.preset, state.preset)}  "
        f"sort={state.sort}  visible={len(visible)}/{len(state.sessions)}  "
        f"selected={len(selected)}  reclaim={selected_size}"
    )
    filter_line = "  ".join(CLEANUP_PRESET_LABELS[p] for p in CLEANUP_PRESET_CHOICES)
    if state.query:
        filter_line += f"  /{state.query}/"
    body_lines: list[str] = []

    if help_mode:
        body_lines = [
            "Help",
            "",
            "  j/k or arrows  move",
            "  space          toggle selection",
            "  a              select all visible",
            "  A              invert visible selection",
            "  x              clear selection",
            "  1-7            preset filters",
            "  /              search repo/PR/title/session",
            "  s              cycle sort (newest/oldest/largest)",
            "  d              preview + delete selected",
            "  q              quit",
            "",
            "Visible-only rule: bulk actions apply only to rows shown by the current filter.",
        ]
    elif confirm_lines is not None:
        body_lines = confirm_lines
    else:
        if not visible:
            body_lines = ["", "No sessions match the current filter."]
        else:
            repo_slug = None
            for idx, session in enumerate(visible):
                if session.repo_slug != repo_slug:
                    repo_slug = session.repo_slug
                    body_lines.append(_clean_wrap(f"  {repo_slug}", "\x1b[1;36m", color=color))
                marker = ">" if idx == state.cursor else " "
                selected_marker = "[x]" if session.session_id in state.selected_ids else "[ ]"
                risk_marker = "!" if session.is_risky else " "
                status = _cleanup_session_status(session)[:7].ljust(7)
                age = _format_age_short(session.age_td(now=now)).rjust(4)
                size = _format_size_short(session.size_bytes).rjust(6)
                verdicts = format_review_verdicts_compact(session.verdicts)
                row_plain = (
                    f"{marker} {selected_marker} {risk_marker} {status} {age} {size}  "
                    f"{verdicts}  {session.session_id}"
                )
                row_plain = _clean_fit(row_plain, width)
                if idx == state.cursor:
                    row_plain = _clean_wrap(row_plain, "\x1b[7m", color=color)
                elif session.is_risky:
                    row_plain = _clean_wrap(row_plain, "\x1b[33m", color=color)
                body_lines.append(row_plain)

    footer = "space toggle • a all visible • A invert visible • x clear • / search • s sort • d delete • ? help • q quit"
    lines: list[str] = [
        _clean_wrap(_clean_fit(header, width), "\x1b[1m", color=color),
        _clean_fit(filter_line, width),
    ]
    if state.message:
        lines.append(_clean_fit(state.message, width))
    if prompt is not None:
        lines.append(_clean_fit(f"{prompt}{prompt_value}", width))
    lines.extend(_clean_fit(str(line), width) for line in body_lines)
    lines.append(_clean_wrap(_clean_fit(footer, width), "\x1b[2m", color=color))

    if len(lines) > height:
        fixed_top = 3 if state.message or prompt is not None else 2
        fixed_bottom = 1
        body_start = fixed_top
        body_end = max(body_start, height - fixed_bottom)
        body_capacity = max(1, body_end - body_start)
        current_line = 0
        if not help_mode and confirm_lines is None and visible:
            current_repo_changes = 0
            repo_slug = None
            for idx, session in enumerate(visible):
                if session.repo_slug != repo_slug:
                    repo_slug = session.repo_slug
                    current_repo_changes += 1
                if idx == state.cursor:
                    current_line = current_repo_changes + idx
                    break
        body_lines_only = lines[body_start:-fixed_bottom]
        start = 0
        if len(body_lines_only) > body_capacity:
            start = min(max(0, current_line - (body_capacity // 2)), len(body_lines_only) - body_capacity)
        lines = lines[:body_start] + body_lines_only[start : start + body_capacity] + lines[-fixed_bottom:]
    try:
        stderr.write("\x1b[2J\x1b[H")
        stderr.write("\n".join(lines) + "\n")
        stderr.flush()
    except Exception:
        return


def _read_cleanup_line(
    *,
    stdin: TextIO,
    stderr: TextIO,
    state: CleanupUiState,
    now: datetime,
    color: bool,
    prompt: str,
    initial: str = "",
    confirm_lines: list[str] | None = None,
) -> str | None:
    value = initial
    while True:
        _render_clean_screen(
            stderr=stderr,
            state=state,
            now=now,
            color=color,
            prompt=prompt,
            prompt_value=value,
            confirm_lines=confirm_lines,
        )
        key = _read_cleanup_key(stdin)
        if key is None:
            return None
        if key == "ENTER":
            return value
        if key in {"ESC"}:
            return None
        if key == "BACKSPACE":
            value = value[:-1]
            continue
        if len(key) == 1 and key.isprintable():
            value += key


def _build_clean_confirmation_lines(
    *, selected: list[CleanupSession], now: datetime
) -> list[str]:
    repo_count = len({session.repo_slug for session in selected})
    risky_count = sum(1 for session in selected if session.is_risky)
    lines = [
        f"Delete {len(selected)} session(s) from {repo_count} repo(s)?",
        f"Estimated reclaim: {_format_size_short(sum(int(s.size_bytes) for s in selected))}",
        f"Risky session(s): {risky_count}",
        "",
    ]
    for session in selected[:10]:
        age = _format_age_short(session.age_td(now=now))
        lines.append(
            f"- {session.session_id}  {_cleanup_session_status(session)}  {age}  {session.repo_slug}  {session.path_display}"
        )
    if len(selected) > 10:
        lines.append(f"... and {len(selected) - 10} more")
    lines.append("")
    if risky_count:
        lines.append("Type DELETE to confirm risky session removal:")
    else:
        lines.append("Confirm deletion [y/N]:")
    return lines


def _build_clean_closed_confirmation_lines(
    *,
    matched: list[tuple[CleanupSession, str]],
    skipped: list[tuple[CleanupSession, str]],
    now: datetime,
) -> list[str]:
    selected = [session for session, _ in matched]
    risky_count = sum(1 for session in selected if session.is_risky)
    lines = [
        f"Delete {len(selected)} session(s) for closed or merged PRs?",
        f"Estimated reclaim: {_format_size_short(sum(int(s.size_bytes) for s in selected))}",
        f"Risky session(s): {risky_count}",
        "",
        "Matched:",
    ]
    for session, pr_state in matched[:10]:
        age = _format_age_short(session.age_td(now=now))
        lines.append(
            f"- {pr_state:<6} {session.repo_slug}  {session.session_id}  {age}  {session.path_display}"
        )
    if len(matched) > 10:
        lines.append(f"... and {len(matched) - 10} more matched session(s)")
    if skipped:
        lines.extend(["", f"Skipped {len(skipped)} session(s) with unknown PR state."])
        for session, reason in skipped[:5]:
            lines.append(f"- {session.repo_slug}  {session.session_id}  {reason}")
        if len(skipped) > 5:
            lines.append(f"... and {len(skipped) - 5} more skipped session(s)")
    lines.append("")
    if risky_count:
        lines.append("Type DELETE to confirm risky session removal:")
    else:
        lines.append("Confirm deletion [y/N]:")
    return lines


def _delete_cleanup_sessions(*, session_ids: list[str], paths: ReviewflowPaths) -> int:
    deleted = 0
    for session_id in session_ids:
        root = paths.sandbox_root.resolve()
        target = (paths.sandbox_root / session_id).resolve()
        if root not in target.parents:
            raise ReviewflowError(f"Refusing to delete outside sandbox root: {target}")
        if not target.is_dir():
            continue
        shutil.rmtree(target)
        deleted += 1
    return deleted


def _cleanup_session_json(session: CleanupSession, *, pr_state: str | None = None) -> dict[str, Any]:
    payload = {
        "session_id": session.session_id,
        "status": _cleanup_session_status(session),
        "repo_slug": session.repo_slug,
        "path": str(session.session_dir),
        "size_bytes": int(session.size_bytes),
        "is_risky": bool(session.is_risky),
    }
    if pr_state is not None:
        payload["pr_state"] = pr_state
    return payload


def _cleanup_payload(
    *,
    kind: str,
    requested_target: str,
    matched: list[dict[str, Any]],
    deleted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "requested_target": requested_target,
        "matched": matched,
        "deleted": deleted,
        "skipped": skipped,
        "summary": {
            "matched": len(matched),
            "deleted": len(deleted),
            "skipped": len(skipped),
        },
    }


def _cleanup_confirm_delete(
    *,
    stdin: TextIO,
    stderr: TextIO,
    state: CleanupUiState,
    now: datetime,
    color: bool,
) -> int:
    selected = state.selected_sessions()
    if not selected:
        state.message = "No sessions selected."
        return 0
    confirm_lines = _build_clean_confirmation_lines(selected=selected, now=now)
    risky = any(session.is_risky for session in selected)
    if risky:
        typed = _read_cleanup_line(
            stdin=stdin,
            stderr=stderr,
            state=state,
            now=now,
            color=color,
            prompt="Type DELETE to confirm: ",
            confirm_lines=confirm_lines,
        )
        if typed != "DELETE":
            state.message = "Deletion cancelled."
            return 0
    else:
        _render_clean_screen(
            stderr=stderr,
            state=state,
            now=now,
            color=color,
            confirm_lines=confirm_lines,
        )
        key = _read_cleanup_key(stdin)
        if key is None or str(key).lower() != "y":
            state.message = "Deletion cancelled."
            return 0
    return len(selected)


def clean_closed_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout
    err_stream = stderr or sys.stderr
    json_output = bool(getattr(args, "json_output", False))
    auto_yes = bool(getattr(args, "yes", False))

    def emit(line: str) -> None:
        print(line, file=err_stream, flush=True)

    try:
        is_tty = bool(in_stream.isatty()) and bool(err_stream.isatty())
    except Exception:
        is_tty = False
    if (not json_output) and (not auto_yes) and (not is_tty):
        raise ReviewflowError("clean closed requires a TTY on stdin/stderr for confirmation.")

    sessions = scan_cleanup_sessions(sandbox_root=paths.sandbox_root)
    if not sessions:
        if json_output:
            print(
                json.dumps(
                    _cleanup_payload(
                        kind="reviewflow.clean.preview",
                        requested_target="closed",
                        matched=[],
                        deleted=[],
                        skipped=[],
                    ),
                    indent=2,
                    sort_keys=True,
                ),
                file=out_stream,
            )
            return 0
        emit(f"No review sandboxes found under {paths.sandbox_root}.")
        return 0

    def progress(current: int, total: int, key: tuple[str, str, str, int]) -> None:
        host, owner, repo, number = key
        bar_width = 20
        filled = bar_width if total <= 0 else max(1, int((current / total) * bar_width))
        bar = "#" * filled + "." * max(0, bar_width - filled)
        label = f"{owner}/{repo}#{number}"
        if host not in {"", "github.com"}:
            label = f"{host}:{label}"
        try:
            err_stream.write(f"\rResolving PR states [{bar}] {current}/{total}  {label}")
            err_stream.flush()
        except Exception:
            return

    states, skipped_states = resolve_cleanup_pr_states(sessions=sessions, on_progress=progress)
    try:
        err_stream.write("\n")
        err_stream.flush()
    except Exception:
        pass
    matched: list[tuple[CleanupSession, str]] = []
    skipped: list[tuple[CleanupSession, str]] = []
    for session in sessions:
        key = _cleanup_pr_key(session)
        if key is None:
            skipped.append((session, "missing PR identity"))
            continue
        pr_state = states.get(key)
        if pr_state in {"merged", "closed"}:
            matched.append((session, pr_state))
            continue
        if pr_state == "open":
            continue
        skipped.append((session, skipped_states.get(key, "unknown PR state")))

    matched_json = [_cleanup_session_json(session, pr_state=pr_state) for session, pr_state in matched]
    skipped_json = [{**_cleanup_session_json(session), "reason": reason} for session, reason in skipped]

    if json_output and (not auto_yes):
        print(
            json.dumps(
                _cleanup_payload(
                    kind="reviewflow.clean.preview",
                    requested_target="closed",
                    matched=matched_json,
                    deleted=[],
                    skipped=skipped_json,
                ),
                indent=2,
                sort_keys=True,
            ),
            file=out_stream,
        )
        return 0

    if not matched:
        if json_output:
            print(
                json.dumps(
                    _cleanup_payload(
                        kind="reviewflow.clean.result" if auto_yes else "reviewflow.clean.preview",
                        requested_target="closed",
                        matched=[],
                        deleted=[],
                        skipped=skipped_json,
                    ),
                    indent=2,
                    sort_keys=True,
                ),
                file=out_stream,
            )
            return 0
        emit("No closed or merged PR sessions matched for cleanup.")
        if skipped:
            emit(f"Skipped {len(skipped)} session(s) with unknown PR state.")
        return 0

    now = _cleanup_now()
    if not auto_yes:
        confirm_lines = _build_clean_closed_confirmation_lines(matched=matched, skipped=skipped, now=now)
        risky = any(session.is_risky for session, _ in matched)
        for line in confirm_lines:
            emit(line)
        if risky:
            typed = in_stream.readline()
            if typed.strip() != "DELETE":
                emit("Deletion cancelled.")
                return 0
        else:
            typed = in_stream.readline()
            if typed.strip().lower() != "y":
                emit("Deletion cancelled.")
                return 0

    deleted = _delete_cleanup_sessions(session_ids=[session.session_id for session, _ in matched], paths=paths)
    if json_output:
        deleted_ids = {item["session_id"] for item in matched_json[:deleted]}
        deleted_json = [item for item in matched_json if item["session_id"] in deleted_ids]
        print(
            json.dumps(
                _cleanup_payload(
                    kind="reviewflow.clean.result",
                    requested_target="closed",
                    matched=matched_json,
                    deleted=deleted_json,
                    skipped=skipped_json,
                ),
                indent=2,
                sort_keys=True,
            ),
            file=out_stream,
        )
        return 0
    emit(
        f"Deleted {deleted} session(s), reclaimed "
        f"{_format_size_short(sum(int(session.size_bytes) for session, _ in matched))}."
    )
    return 0


def interactive_clean_flow(
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
        raise ReviewflowError(
            "clean without a session_id requires a TTY on stdin/stderr. "
            f"Use `{PRIMARY_CLI_COMMAND} clean <session_id>` for exact deletion."
        )

    sessions = scan_cleanup_sessions(sandbox_root=paths.sandbox_root)
    if not sessions:
        _eprint(f"No review sandboxes found under {paths.sandbox_root}.")
        return 0

    state = CleanupUiState(sessions=sessions)
    color = _clean_color_enabled(err_stream)

    with _clean_fullscreen(input_stream=in_stream, output_stream=err_stream):
        while True:
            now = _cleanup_now()
            state.clamp_cursor(now=now)
            _render_clean_screen(stderr=err_stream, state=state, now=now, color=color)
            key = _read_cleanup_key(in_stream)
            if key is None or key == "q":
                state.message = ""
                break
            if key in {"DOWN", "j"}:
                state.move_cursor(1, now=now)
                continue
            if key in {"UP", "k"}:
                state.move_cursor(-1, now=now)
                continue
            if key == " ":
                state.toggle_current(now=now)
                continue
            if key == "a":
                state.select_all_visible(now=now)
                continue
            if key == "A":
                state.invert_visible_selection(now=now)
                continue
            if key == "x":
                state.clear_selection()
                continue
            if key == "s":
                state.cycle_sort()
                state.clamp_cursor(now=now)
                continue
            if key == "/":
                query = _read_cleanup_line(
                    stdin=in_stream,
                    stderr=err_stream,
                    state=state,
                    now=now,
                    color=color,
                    prompt="Search: ",
                    initial=state.query,
                )
                if query is not None:
                    state.query = query.strip()
                    state.cursor = 0
                continue
            if key == "?":
                _render_clean_screen(stderr=err_stream, state=state, now=now, color=color, help_mode=True)
                _ = _read_cleanup_key(in_stream)
                continue
            if key == "d":
                expected = _cleanup_confirm_delete(
                    stdin=in_stream,
                    stderr=err_stream,
                    state=state,
                    now=now,
                    color=color,
                )
                if expected <= 0:
                    continue
                selected = state.selected_sessions()
                deleted = _delete_cleanup_sessions(
                    session_ids=[session.session_id for session in selected],
                    paths=paths,
                )
                deleted_ids = {session.session_id for session in selected}
                state.sessions = [session for session in state.sessions if session.session_id not in deleted_ids]
                state.selected_ids.difference_update(deleted_ids)
                state.clamp_cursor(now=now)
                state.message = (
                    f"Deleted {deleted} session(s), reclaimed {_format_size_short(sum(int(s.size_bytes) for s in selected))}."
                )
                continue
            preset = {
                "1": CLEANUP_PRESET_ALL,
                "2": CLEANUP_PRESET_DONE,
                "3": CLEANUP_PRESET_ERROR,
                "4": CLEANUP_PRESET_RUNNING,
                "5": CLEANUP_PRESET_DONE_OLDER_24H,
                "6": CLEANUP_PRESET_DONE_OLDER_7D,
                "7": CLEANUP_PRESET_DONE_OLDER_30D,
            }.get(key)
            if preset is not None:
                state.set_preset(preset, now=now)
                continue

    return 0


def clean_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    session_id = str(getattr(args, "session_id", "") or "").strip()
    json_output = bool(getattr(args, "json_output", False))
    auto_yes = bool(getattr(args, "yes", False))
    out_stream = stdout or sys.stdout
    if (not session_id) and (json_output or auto_yes):
        raise ReviewflowError("clean with no target does not accept --yes or --json.")
    if session_id == "closed":
        return clean_closed_flow(args, paths=paths, stdin=stdin, stdout=out_stream, stderr=stderr)
    if session_id:
        if auto_yes:
            raise ReviewflowError("clean <session_id> does not accept --yes.")
        return clean_session(session_id, paths=paths, stdout=out_stream, json_output=json_output)
    return interactive_clean_flow(args, paths=paths, stdin=stdin, stderr=stderr)


def clean_session(
    session_id: str,
    *,
    paths: ReviewflowPaths,
    stdout: TextIO | None = None,
    json_output: bool = False,
) -> int:
    root = paths.sandbox_root.resolve()
    target = (paths.sandbox_root / session_id).resolve()
    if root not in target.parents:
        raise ReviewflowError(f"Refusing to delete outside sandbox root: {target}")
    if not target.is_dir():
        _eprint(f"Session not found: {target}")
        return 2
    payload = None
    if json_output:
        meta = _load_session_meta(target / "meta.json") or {}
        owner = str(meta.get("owner") or "").strip() or "?"
        repo = str(meta.get("repo") or "").strip() or "?"
        number_text = str(meta.get("number") or "").strip()
        try:
            number = int(number_text)
        except Exception:
            number = 0
        session = CleanupSession(
            session_id=session_id,
            session_dir=target,
            host=str(meta.get("host") or "").strip() or "?",
            owner=owner,
            repo=repo,
            number=number,
            repo_slug=f"{owner}/{repo}#{number if number else '?'}",
            title=str(meta.get("title") or "").strip(),
            status=str(meta.get("status") or "").strip().lower() or "unknown",
            created_at=str(meta.get("created_at") or "").strip() or None,
            completed_at=str(meta.get("completed_at") or "").strip() or None,
            failed_at=str(meta.get("failed_at") or "").strip() or None,
            resumed_at=str(meta.get("resumed_at") or "").strip() or None,
            verdicts=None,
            codex_summary=resolve_codex_summary(meta) if meta else "llm=legacy_codex/?",
            size_bytes=_cleanup_dir_size_bytes(target),
            path_display=str(target),
            is_running=(str(meta.get("status") or "").strip().lower() == "running"),
            is_recent=False,
            is_risky=False,
        )
        session_json = _cleanup_session_json(session)
        payload = _cleanup_payload(
            kind="reviewflow.clean.result",
            requested_target=session_id,
            matched=[session_json],
            deleted=[session_json],
            skipped=[],
        )
    shutil.rmtree(target)
    if json_output and payload is not None:
        print(json.dumps(payload, indent=2, sort_keys=True), file=(stdout or sys.stdout))
    return 0


def jira_smoke_flow(
    args: argparse.Namespace,
    *,
    paths: ReviewflowPaths,
    config_path: Path | None = None,
    codex_base_config_path: Path | None = None,
) -> int:
    effective_config_path = config_path or default_reviewflow_config_path()
    effective_codex_base_config_path = codex_base_config_path or default_codex_base_config_path()
    quiet = bool(getattr(args, "quiet", False))
    no_stream = bool(getattr(args, "no_stream", False))
    stream = (not quiet) and (not no_stream)

    jira_key = str(args.jira_key).strip()
    if not jira_key:
        raise ReviewflowError("jira-smoke requires a Jira key (e.g. PROJ-123).")

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

    codex_flags, _ = resolve_codex_flags(
        base_config_path=effective_codex_base_config_path,
        reviewflow_config_path=effective_config_path,
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

    try:
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
    finally:
        cleanup_sensitive_staged_paths(
            {
                "jira_config_file": env.get("JIRA_CONFIG_FILE"),
                "netrc": env.get("NETRC"),
            }
        )

CHUNKHOUND_GIT_MAIN_INSTALL_SPEC = "git+https://github.com/chunkhound/chunkhound@main"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def build_chunkhound_install_command(*, chunkhound_source: str) -> list[str]:
    if chunkhound_source == "release":
        spec = "chunkhound"
    elif chunkhound_source == "git-main":
        spec = CHUNKHOUND_GIT_MAIN_INSTALL_SPEC
    else:
        raise ReviewflowError(f"Unknown chunkhound install source: {chunkhound_source}")
    uv_path = shutil.which("uv")
    if _running_in_uv_tool_environment(uv_path=uv_path):
        if uv_path:
            return [uv_path, "tool", "install", "--force", spec]
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", "--upgrade", spec]
    if uv_path:
        return [uv_path, "pip", "install", "--python", sys.executable, "--upgrade", spec]
    raise ReviewflowError("ChunkHound install requires either `pip` in the current interpreter or `uv` on PATH.")


def _uv_tool_dir(*, uv_path: str, bin_dir: bool = False) -> Path | None:
    cmd = [uv_path, "tool", "dir"]
    if bin_dir:
        cmd.append("--bin")
    try:
        result = run_cmd(cmd)
    except ReviewflowSubprocessError:
        return None
    raw = result.stdout.strip()
    return Path(raw).resolve(strict=False) if raw else None


def _running_in_uv_tool_environment(*, uv_path: str | None) -> bool:
    if not uv_path:
        return False
    tool_root = _uv_tool_dir(uv_path=uv_path, bin_dir=False)
    if tool_root is None:
        return False
    exe = Path(sys.executable)
    prefix = Path(sys.prefix)
    return (tool_root == exe or tool_root in exe.parents or tool_root == prefix or tool_root in prefix.parents)


def _chunkhound_not_on_path_error(*, uv_path: str | None) -> ReviewflowError:
    detail = "ChunkHound install completed, but `chunkhound` is still not available on PATH."
    if _running_in_uv_tool_environment(uv_path=uv_path) and uv_path:
        tool_bin = _uv_tool_dir(uv_path=uv_path, bin_dir=True)
        extra = f"\nuv tool bin dir: {tool_bin}" if tool_bin is not None else ""
        detail += f"{extra}\nRun `uv tool update-shell` or add that directory to PATH."
    return ReviewflowError(detail)


def install_flow(args: argparse.Namespace) -> int:
    chunkhound_source = str(getattr(args, "chunkhound_source", "release") or "release").strip()
    uv_path = shutil.which("uv")
    cmd = build_chunkhound_install_command(chunkhound_source=chunkhound_source)
    _eprint(f"Installing ChunkHound from source={chunkhound_source}")
    run_cmd(cmd)
    chunkhound_path = shutil.which("chunkhound")
    if not chunkhound_path:
        raise _chunkhound_not_on_path_error(uv_path=uv_path)
    _eprint(f"ChunkHound install complete: {chunkhound_path}")
    return 0


def _doctor_executable_check(name: str) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return DoctorCheck(name=name, status="ok", detail=path)
    return DoctorCheck(name=name, status="fail", detail="not found on PATH")


def _default_jira_config_path() -> Path:
    env_path = _resolve_optional_path(os.environ.get("JIRA_CONFIG_FILE"))
    if env_path is not None:
        return env_path
    return (Path.home() / ".config" / ".jira" / ".config.yml").resolve(strict=False)


def _doctor_gh_auth_check() -> DoctorCheck:
    if shutil.which("gh") is None:
        return DoctorCheck(name="gh-auth", status="fail", detail="`gh` is not installed")
    try:
        run_cmd(["gh", "auth", "status", "--hostname", "github.com"], check=True)
    except ReviewflowSubprocessError as e:
        msg = e.stderr.strip() or e.stdout.strip() or "not authenticated"
        return DoctorCheck(name="gh-auth", status="fail", detail=msg)
    return DoctorCheck(name="gh-auth", status="ok", detail="authenticated for github.com")


def _doctor_path_payload(*, path: Path, source: str, exists: bool, enabled: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "source": source,
        "exists": bool(exists),
    }
    if not enabled:
        payload["enabled"] = False
    return payload


def _resolved_doctor_agent_runtime(
    runtime: ReviewflowRuntime, *, cli_profile: str | None = None
) -> dict[str, Any]:
    profile, profile_source, runtime_cfg, _ = resolve_agent_runtime_profile(
        cli_value=cli_profile,
        config_path=runtime.config_path,
        config_enabled=runtime.config_enabled,
    )
    llm_resolved, _ = resolve_llm_config(
        base_codex_config_path=runtime.codex_base_config_path,
        reviewflow_config_path=runtime.config_path,
        cli_preset=None,
        cli_model=None,
        cli_effort=None,
        cli_plan_effort=None,
        cli_verbosity=None,
        cli_max_output_tokens=None,
        cli_request_overrides=None,
        cli_header_overrides=None,
        deprecated_codex_model=None,
        deprecated_codex_effort=None,
        deprecated_codex_plan_effort=None,
    )
    provider = str(llm_resolved.get("provider") or "").strip().lower()
    transport = str(llm_resolved.get("transport") or "").strip().lower()
    payload: dict[str, Any] = {
        "profile": profile,
        "profile_source": profile_source,
        "provider": provider,
        "transport": transport,
        "command": llm_resolved.get("command"),
    }
    if transport != "cli" or provider not in CLI_LLM_PROVIDERS:
        payload["supported"] = False
        payload["detail"] = "agent runtime profiles apply only to CLI coding-agent providers"
        return payload

    payload["supported"] = True
    gemini_cfg = runtime_cfg.get("gemini")
    gemini_cfg = gemini_cfg if isinstance(gemini_cfg, dict) else {}
    if provider == "codex":
        if profile == "permissive":
            payload.update(
                {
                    "dangerously_bypass_approvals_and_sandbox": True,
                    "sandbox_mode": None,
                    "approval_policy": None,
                }
            )
        else:
            payload.update(
                {
                    "dangerously_bypass_approvals_and_sandbox": False,
                    "sandbox_mode": ("read-only" if profile == "strict" else "workspace-write"),
                    "approval_policy": "never",
                }
            )
    elif provider == "claude":
        payload.update(
            {
                "dangerously_skip_permissions": (profile == "permissive"),
                "permission_mode": (
                    None
                    if profile == "permissive"
                    else ("plan" if profile == "strict" else "dontAsk")
                ),
            }
        )
    elif provider == "gemini":
        sandbox = str(gemini_cfg.get("sandbox") or "").strip() or None
        payload.update(
            {
                "approval_mode": (
                    "plan" if profile == "strict" else ("yolo" if profile == "permissive" else "auto_edit")
                ),
                "sandbox": sandbox,
                "seatbelt_profile": str(gemini_cfg.get("seatbelt_profile") or "").strip() or None,
                "strict_ready": (bool(sandbox) if profile == "strict" else None),
            }
        )
    return payload


def _doctor_runtime_payload(runtime: ReviewflowRuntime, *, cli_profile: str | None = None) -> dict[str, Any]:
    config_exists = runtime.config_path.is_file()
    payload: dict[str, Any] = {
        "reviewflow_config": _doctor_path_payload(
            path=runtime.config_path,
            source=runtime.config_source,
            exists=config_exists,
            enabled=runtime.config_enabled,
        ),
        "sandbox_root": _doctor_path_payload(
            path=runtime.paths.sandbox_root,
            source=runtime.sandbox_root_source,
            exists=runtime.paths.sandbox_root.exists(),
        ),
        "cache_root": _doctor_path_payload(
            path=runtime.paths.cache_root,
            source=runtime.cache_root_source,
            exists=runtime.paths.cache_root.exists(),
        ),
        "codex_base_config": _doctor_path_payload(
            path=runtime.codex_base_config_path,
            source=runtime.codex_base_config_source,
            exists=runtime.codex_base_config_path.is_file(),
        ),
        "agent_runtime": _resolved_doctor_agent_runtime(runtime, cli_profile=cli_profile),
    }

    if not runtime.config_enabled:
        payload["chunkhound_base_config"] = {
            "path": None,
            "source": "disabled",
            "exists": False,
            "enabled": False,
        }
        return payload

    try:
        chunkhound_cfg, _ = load_reviewflow_chunkhound_config(config_path=runtime.config_path, require=True)
    except ReviewflowError as e:
        payload["chunkhound_base_config"] = {
            "path": None,
            "source": "config",
            "exists": False,
            "error": str(e).splitlines()[0],
        }
        return payload

    assert chunkhound_cfg is not None
    payload["chunkhound_base_config"] = _doctor_path_payload(
        path=chunkhound_cfg.base_config_path,
        source="config",
        exists=chunkhound_cfg.base_config_path.is_file(),
    )
    return payload


def _doctor_runtime_checks(runtime: ReviewflowRuntime, *, cli_profile: str | None = None) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    agent_runtime = _resolved_doctor_agent_runtime(runtime, cli_profile=cli_profile)
    config_path = runtime.config_path
    config_prefix = f"{config_path} (source={runtime.config_source})"
    if not runtime.config_enabled:
        checks.append(
            DoctorCheck(
                name="reviewflow-config",
                status="warn",
                detail=f"{config_prefix} (disabled by --no-config)",
            )
        )
    elif config_path.is_file():
        checks.append(DoctorCheck(name="reviewflow-config", status="ok", detail=config_prefix))
    else:
        checks.append(
            DoctorCheck(
                name="reviewflow-config",
                status="fail",
                detail=f"missing: {config_prefix}",
            )
        )

    path_defaults, _ = load_reviewflow_paths_defaults(config_path=config_path)
    sandbox_detail = f"{runtime.paths.sandbox_root} (source={runtime.sandbox_root_source})"
    if runtime.sandbox_root_source == "config" and path_defaults.get("sandbox_root") is not None:
        sandbox_detail += " (configured)"
    if runtime.paths.sandbox_root.exists():
        checks.append(DoctorCheck(name="sandbox-root", status="ok", detail=sandbox_detail))
    else:
        checks.append(
            DoctorCheck(
                name="sandbox-root",
                status="warn",
                detail=f"{sandbox_detail} (will be created on demand)",
            )
        )

    cache_detail = f"{runtime.paths.cache_root} (source={runtime.cache_root_source})"
    if runtime.cache_root_source == "config" and path_defaults.get("cache_root") is not None:
        cache_detail += " (configured)"
    if runtime.paths.cache_root.exists():
        checks.append(DoctorCheck(name="cache-root", status="ok", detail=cache_detail))
    else:
        checks.append(
            DoctorCheck(
                name="cache-root",
                status="warn",
                detail=f"{cache_detail} (will be created on demand)",
            )
        )

    if not runtime.config_enabled:
        checks.append(
            DoctorCheck(
                name="chunkhound-config",
                status="warn",
                detail="disabled by --no-config",
            )
        )
    else:
        try:
            chunkhound_cfg, _ = load_reviewflow_chunkhound_config(config_path=config_path, require=True)
        except ReviewflowError as e:
            checks.append(DoctorCheck(name="chunkhound-config", status="fail", detail=str(e).splitlines()[0]))
        else:
            assert chunkhound_cfg is not None
            chunkhound_detail = f"{chunkhound_cfg.base_config_path} (source=config)"
            if chunkhound_cfg.base_config_path.is_file():
                checks.append(
                    DoctorCheck(
                        name="chunkhound-config",
                        status="ok",
                        detail=chunkhound_detail,
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="chunkhound-config",
                        status="fail",
                        detail=f"missing base_config_path: {chunkhound_detail}",
                    )
                )

    jira_cfg = _default_jira_config_path()
    if jira_cfg.is_file():
        checks.append(DoctorCheck(name="jira-config", status="ok", detail=str(jira_cfg)))
    else:
        checks.append(DoctorCheck(name="jira-config", status="fail", detail=f"missing: {jira_cfg}"))

    if runtime.codex_base_config_path.is_file():
        checks.append(
            DoctorCheck(
                name="codex-config",
                status="ok",
                detail=f"{runtime.codex_base_config_path} (source={runtime.codex_base_config_source})",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="codex-config",
                status="warn",
                detail=f"missing: {runtime.codex_base_config_path} (source={runtime.codex_base_config_source})",
            )
        )

    checks.extend(_doctor_executable_check(name) for name in ("chunkhound", "gh", "jira", "codex"))
    provider = str(agent_runtime.get("provider") or "").strip().lower()
    command = str(agent_runtime.get("command") or "").strip()
    if bool(agent_runtime.get("supported")) and provider and command and (provider != "codex"):
        selected = _doctor_executable_check(command)
        checks.append(
            DoctorCheck(
                name="agent-runtime-command",
                status=selected.status,
                detail=f"{provider}: {selected.detail}",
            )
        )
    if provider == "gemini" and str(agent_runtime.get("profile") or "") == "strict":
        if bool(agent_runtime.get("strict_ready")):
            checks.append(
                DoctorCheck(
                    name="agent-runtime",
                    status="ok",
                    detail="gemini strict runtime backend configured",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="agent-runtime",
                    status="fail",
                    detail="gemini strict runtime requires [agent_runtime.gemini].sandbox",
                )
            )
    checks.append(_doctor_gh_auth_check())
    return checks


def doctor_flow(args: argparse.Namespace, *, runtime: ReviewflowRuntime) -> int:
    checks = _doctor_runtime_checks(runtime, cli_profile=getattr(args, "agent_runtime_profile", None))
    if bool(getattr(args, "json_output", False)):
        ok_count = sum(1 for item in checks if item.status == "ok")
        warn_count = sum(1 for item in checks if item.status == "warn")
        fail_count = sum(1 for item in checks if item.status == "fail")
        payload = _doctor_runtime_payload(runtime, cli_profile=getattr(args, "agent_runtime_profile", None))
        payload["checks"] = [
            {"name": item.name, "status": item.status, "detail": item.detail} for item in checks
        ]
        payload["summary"] = {"ok": ok_count, "warn": warn_count, "fail": fail_count}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if fail_count == 0 else 1

    checks = _doctor_runtime_checks(runtime, cli_profile=getattr(args, "agent_runtime_profile", None))
    ok_count = sum(1 for item in checks if item.status == "ok")
    warn_count = sum(1 for item in checks if item.status == "warn")
    fail_count = sum(1 for item in checks if item.status == "fail")
    for item in checks:
        print(f"[{item.status}] {item.name}: {item.detail}")
    print(f"summary: ok={ok_count} warn={warn_count} fail={fail_count}")
    return 0 if fail_count == 0 else 1


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        dest="config_path",
        default=argparse.SUPPRESS,
        help="Override the CURe config path (`reviewflow.toml`)",
    )
    parser.add_argument(
        "--no-config",
        dest="no_config",
        action="store_true",
        default=False,
        help="Disable reading the `reviewflow.toml` config; CLI/env overrides still apply",
    )
    parser.add_argument(
        "--sandbox-root",
        dest="sandbox_root",
        default=argparse.SUPPRESS,
        help="Override the review sandbox root",
    )
    parser.add_argument(
        "--cache-root",
        dest="cache_root",
        default=argparse.SUPPRESS,
        help="Override the CURe cache root",
    )
    parser.add_argument(
        "--codex-config",
        dest="codex_config_path",
        default=argparse.SUPPRESS,
        help="Override the Codex base config path",
    )


def add_agent_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent-runtime-profile",
        dest="agent_runtime_profile",
        choices=list(AGENT_RUNTIME_PROFILE_CHOICES),
        default=None,
        help="CURe-owned CLI coding-agent runtime posture (balanced, strict, permissive)",
    )


def resolve_cli_invocation_name(argv0: str | None) -> str:
    name = Path(str(argv0 or PRIMARY_CLI_COMMAND)).name.strip().lower()
    if name == DEPRECATED_CLI_ALIAS:
        return DEPRECATED_CLI_ALIAS
    if name == PRIMARY_CLI_COMMAND:
        return PRIMARY_CLI_COMMAND
    return PRIMARY_CLI_COMMAND


def maybe_warn_deprecated_cli_alias(invocation_name: str, *, stderr: TextIO | None = None) -> None:
    if str(invocation_name or "").strip().lower() != DEPRECATED_CLI_ALIAS:
        return
    print(DEPRECATED_ALIAS_WARNING, file=(stderr or sys.stderr))


def build_parser(*, prog: str = PRIMARY_CLI_COMMAND) -> argparse.ArgumentParser:
    runtime_parent = argparse.ArgumentParser(add_help=False)
    add_runtime_args(runtime_parent)
    parser = argparse.ArgumentParser(prog=prog, parents=[runtime_parent])
    sub = parser.add_subparsers(dest="cmd", required=True)
    codex_help = "Override Codex defaults after LLM preset resolution"

    prp = sub.add_parser("pr", help="Create PR sandbox, index, and run review", parents=[runtime_parent])
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
    prp.add_argument("--big-if-files", type=int, default=30, help="Auto-select big prompt if changed files >= N")
    prp.add_argument(
        "--big-if-lines",
        type=int,
        default=1500,
        help="Auto-select big prompt if additions+deletions >= N",
    )
    prp.add_argument("--agent-desc", help="Extra contributor context ($AGENT_DESC)", default=None)
    prp.add_argument("--agent-desc-file", help="Path to file containing extra contributor context", default=None)
    prp.add_argument("--refresh-base", action="store_true", help="Force base cache refresh")
    prp.add_argument("--base-ttl-hours", type=int, default=24, help="Base cache TTL in hours")
    add_llm_override_args(prp)
    add_agent_runtime_args(prp)
    prp.add_argument("--codex-model", dest="codex_model", default=None, help=codex_help)
    prp.add_argument(
        "--codex-effort",
        dest="codex_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help=codex_help,
    )
    prp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help=codex_help,
    )
    mpg = prp.add_mutually_exclusive_group()
    mpg.add_argument("--multipass", dest="multipass", action="store_true", default=None, help="Enable multipass review")
    mpg.add_argument("--no-multipass", dest="multipass", action="store_false", default=None, help="Disable multipass review")
    prp.add_argument("--multipass-max-steps", dest="multipass_max_steps", type=int, default=None)
    prp.add_argument("--no-index", action="store_true", help="Skip ChunkHound indexing")
    prp.add_argument("--no-review", action="store_true", help="Skip running codex review")
    prp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    prp.add_argument("--no-stream", action="store_true", help="Do not stream chunkhound/codex output")
    prp.add_argument("--ui", choices=["auto", "on", "off"], default="auto", help="Terminal UI dashboard mode")
    prp.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")

    cachep = sub.add_parser("cache", help="Manage base cache", parents=[runtime_parent])
    cachesub = cachep.add_subparsers(dest="cache_cmd", required=True)
    prime = cachesub.add_parser("prime", help="Prime/update base cache for a repo/base branch", parents=[runtime_parent])
    prime.add_argument("owner_repo", help="OWNER/REPO or HOST/OWNER/REPO")
    prime.add_argument("--base", required=True, help="Base branch/ref to index")
    prime.add_argument("--force", action="store_true", help="Force reindex of all files")
    prime.add_argument("--quiet", action="store_true", help="Suppress progress output")
    prime.add_argument("--no-stream", action="store_true", help="Do not stream chunkhound output")

    status = cachesub.add_parser("status", help="Show cache metadata JSON", parents=[runtime_parent])
    status.add_argument("owner_repo", help="OWNER/REPO or HOST/OWNER/REPO")
    status.add_argument("--base", required=True, help="Base branch/ref")

    cdp = sub.add_parser("commands", help="Show the curated workflow command catalog", parents=[runtime_parent])
    cdp.add_argument("--json", dest="json_output", action="store_true", help="Print structured command catalog JSON")

    sub.add_parser("list", help="List existing review sandboxes", parents=[runtime_parent])

    ip = sub.add_parser("interactive", help="Pick a past review and resume it when supported", parents=[runtime_parent])
    ip.add_argument("target", nargs="?", help="Optional PR URL to filter the picker")

    cp = sub.add_parser(
        "clean",
        help="Delete one review sandbox session, clean closed/merged PR sessions, or open the interactive cleaner",
        parents=[runtime_parent],
    )
    cp.add_argument("session_id", nargs="?", help="Session id (folder name), or the reserved target `closed`")
    cp.add_argument("--yes", action="store_true", help="Execute bulk closed-session cleanup without confirmation")
    cp.add_argument("--json", dest="json_output", action="store_true", help="Print structured cleanup JSON")

    mp = sub.add_parser(
        "migrate-storage",
        help="Show the storage-migration deprecation notice",
        parents=[runtime_parent],
    )
    mp.add_argument("--apply", action="store_true", help="Accepted for compatibility; no migration is performed")

    rp = sub.add_parser(
        "resume",
        help="Resume a multipass review session (PR URL: runs follow-up if already completed)",
        parents=[runtime_parent],
    )
    rp.add_argument("session_id", help="Session id (folder name) or PR URL")
    rp.add_argument("--from", dest="from_phase", choices=["auto", "plan", "steps", "synth"], default="auto")
    add_llm_override_args(rp)
    add_agent_runtime_args(rp)
    rp.add_argument("--codex-model", dest="codex_model", default=None, help=codex_help)
    rp.add_argument("--codex-effort", dest="codex_effort", choices=CODEX_REASONING_EFFORT_CHOICES, default=None, help=codex_help)
    rp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help=codex_help,
    )
    rp.add_argument("--multipass-max-steps", dest="multipass_max_steps", type=int, default=None)
    rp.add_argument("--no-index", action="store_true", help="Disable ChunkHound MCP for resume")
    rp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    rp.add_argument("--no-stream", action="store_true", help="Do not stream chunkhound/codex output")
    rp.add_argument("--ui", choices=["auto", "on", "off"], default="auto")
    rp.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")

    fup = sub.add_parser("followup", help="Run a follow-up review for an existing session sandbox", parents=[runtime_parent])
    fup.add_argument("session_id", help="Session id (folder name)")
    fup.add_argument("--no-update", action="store_true", help="Do not update the sandbox repo before reviewing")
    add_llm_override_args(fup)
    add_agent_runtime_args(fup)
    fup.add_argument("--codex-model", dest="codex_model", default=None, help=codex_help)
    fup.add_argument("--codex-effort", dest="codex_effort", choices=CODEX_REASONING_EFFORT_CHOICES, default=None, help=codex_help)
    fup.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help=codex_help,
    )
    fup.add_argument("--quiet", action="store_true", help="Suppress progress output")
    fup.add_argument("--no-stream", action="store_true", help="Do not stream chunkhound/codex output")
    fup.add_argument("--ui", choices=["auto", "on", "off"], default="auto")
    fup.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")

    zp = sub.add_parser("zip", help="Synthesize a final review from the latest generated reviews for a PR", parents=[runtime_parent])
    zp.add_argument("pr_url", help="GitHub PR URL")
    add_llm_override_args(zp)
    add_agent_runtime_args(zp)
    zp.add_argument("--codex-model", dest="codex_model", default=None, help=codex_help)
    zp.add_argument("--codex-effort", dest="codex_effort", choices=CODEX_REASONING_EFFORT_CHOICES, default=None, help=codex_help)
    zp.add_argument(
        "--codex-plan-effort",
        dest="codex_plan_effort",
        choices=CODEX_REASONING_EFFORT_CHOICES,
        default=None,
        help=codex_help,
    )
    zp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    zp.add_argument("--no-stream", action="store_true", help="Do not stream codex output")
    zp.add_argument("--ui", choices=["auto", "on", "off"], default="auto")
    zp.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")

    upp = sub.add_parser("ui-preview", help="Render the TUI dashboard from an existing session", parents=[runtime_parent])
    upp.add_argument("session_id", help="Session id (folder name)")
    upp.add_argument("--watch", action="store_true", help="Continuously repaint the dashboard")
    upp.add_argument("--width", type=int, default=None, help="Terminal width")
    upp.add_argument("--height", type=int, default=None, help="Terminal height")
    upp.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")
    upp.add_argument("--no-color", action="store_true", help="Disable ANSI styling")

    sp = sub.add_parser("status", help="Show run status for a session id or PR URL", parents=[runtime_parent])
    sp.add_argument("target", help="Session id (folder name) or PR URL")
    sp.add_argument("--json", dest="json_output", action="store_true", help="Print structured status JSON")

    wp = sub.add_parser("watch", help="Follow run status for a session id or PR URL", parents=[runtime_parent])
    wp.add_argument("target", help="Session id (folder name) or PR URL")
    wp.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds (default: 2.0)")
    wp.add_argument("--verbosity", choices=["quiet", "normal", "debug"], default="normal")
    wp.add_argument("--no-color", action="store_true", help="Disable ANSI styling")

    ins = sub.add_parser(
        "install",
        help="Install or update ChunkHound so the `chunkhound` CLI is available to CURe",
        parents=[runtime_parent],
    )
    ins.add_argument(
        "--chunkhound-source",
        choices=["release", "git-main"],
        default="release",
        help="ChunkHound source to install (default: release)",
    )

    dp = sub.add_parser("doctor", help="Diagnose external tool and config readiness", parents=[runtime_parent])
    add_agent_runtime_args(dp)
    dp.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print structured doctor output as JSON",
    )

    jsp = sub.add_parser("jira-smoke", help="Acceptance smoke test: Jira access via Codex", parents=[runtime_parent])
    jsp.add_argument("jira_key", help="Jira key to fetch (e.g. PROJ-123)")
    jsp.add_argument("--attempts", type=int, default=1, help="How many attempts to run")
    jsp.add_argument("--sleep-seconds", type=float, default=0.0, help="Seconds to wait between attempts")
    jsp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    jsp.add_argument("--no-stream", action="store_true", help="Do not stream codex output")
    return parser


def main(argv: list[str], *, prog: str = PRIMARY_CLI_COMMAND) -> int:
    args = build_parser(prog=prog).parse_args(argv)
    runtime = resolve_runtime(args)
    paths = runtime.paths

    try:
        if args.cmd == "install":
            return install_flow(args)
        if args.cmd == "doctor":
            return doctor_flow(args, runtime=runtime)
        if args.cmd == "commands":
            return commands_flow(args)
        if args.cmd == "pr":
            return pr_flow(
                args,
                paths=paths,
                config_path=runtime.config_path,
                codex_base_config_path=runtime.codex_base_config_path,
            )
        if args.cmd == "ui-preview":
            return ui_preview_flow(args, paths=paths)
        if args.cmd == "status":
            return status_flow(args, paths=paths)
        if args.cmd == "watch":
            return watch_flow(args, paths=paths)
        if args.cmd == "cache":
            host, owner, repo = parse_owner_repo(args.owner_repo)
            if args.cache_cmd == "prime":
                cache_prime(
                    paths=paths,
                    config_path=runtime.config_path,
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
                return cache_status(paths=paths, host=host, owner=owner, repo=repo, base_ref=str(args.base))
        if args.cmd == "list":
            return list_sessions(paths=paths)
        if args.cmd == "interactive":
            return interactive_flow(args, paths=paths, config_path=runtime.config_path)
        if args.cmd == "clean":
            return clean_flow(args, paths=paths)
        if args.cmd == "migrate-storage":
            return migrate_storage_flow(args, paths=paths)
        if args.cmd == "resume":
            return resume_flow(
                args,
                paths=paths,
                config_path=runtime.config_path,
                codex_base_config_path=runtime.codex_base_config_path,
            )
        if args.cmd == "followup":
            return followup_flow(
                args,
                paths=paths,
                config_path=runtime.config_path,
                codex_base_config_path=runtime.codex_base_config_path,
            )
        if args.cmd == "zip":
            return zip_flow(
                args,
                paths=paths,
                config_path=runtime.config_path,
                codex_base_config_path=runtime.codex_base_config_path,
            )
        if args.cmd == "jira-smoke":
            return jira_smoke_flow(
                args,
                paths=paths,
                config_path=runtime.config_path,
                codex_base_config_path=runtime.codex_base_config_path,
            )
    except ReviewflowError as e:
        _eprint(str(e))
        return 2
    except ReviewflowSubprocessError as e:
        _eprint(str(e))
        if e.stderr.strip():
            _eprint(e.stderr.strip())
        return int(e.exit_code) or 2

    raise AssertionError("Unhandled command")


def console_main() -> int:
    invocation_name = resolve_cli_invocation_name(sys.argv[0] if sys.argv else PRIMARY_CLI_COMMAND)
    maybe_warn_deprecated_cli_alias(invocation_name)
    return main(sys.argv[1:], prog=PRIMARY_CLI_COMMAND)


if __name__ == "__main__":
    raise SystemExit(console_main())
