from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib
from typing import Any
import urllib.error
import urllib.request

from cure_errors import ReviewflowError
from cure_sessions import PullRequestRef, parse_pr_url
from meta import json_fingerprint
from paths import (
    ReviewflowPaths,
    default_cache_root,
    default_codex_base_config_path,
    default_reviewflow_config_path,
    default_sandbox_root,
)
from run import ReviewflowSubprocessError, run_cmd
from ui import Verbosity


DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE = "cure_first_unrestricted"
CODEX_REASONING_EFFORT_CHOICES = ("minimal", "low", "medium", "high", "xhigh")
LLM_TRANSPORT_CHOICES = ("http", "cli")
HTTP_LLM_PROVIDERS = ("openai", "openrouter")
CLI_LLM_PROVIDERS = ("codex", "claude", "gemini")
LLM_RESUME_PROVIDERS = ("codex", "claude")
DEFAULT_LEGACY_CODEX_PRESET = "legacy_codex"
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

REVIEW_INTELLIGENCE_CONFIG_EXAMPLE = """[review_intelligence]
tool_prompt_fragment = \"\"\"
Preferred review-intelligence tools:
- Use GitHub MCP for PR context when available.
- Otherwise use gh CLI / gh api.
- Use any additional tools or sources that materially improve understanding of the code under review.
\"\"\"
"""

CHUNKHOUND_CONFIG_EXAMPLE = """[chunkhound]
base_config_path = "/absolute/path/to/chunkhound-base.json"

[chunkhound.indexing]
# Optional: when set, these replace the corresponding lists in the base config.
include = ["**/*.py", "**/*.ts"]
exclude = ["**/.claude/**", "**/openspec/**"]
per_file_timeout_seconds = 6
per_file_timeout_min_size_kb = 128

[chunkhound.research]
algorithm = "hybrid"
"""

_DISABLED_REVIEWFLOW_CONFIG_PATH: Path | None = None


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


@dataclass(frozen=True)
class ReviewIntelligenceConfig:
    tool_prompt_fragment: str
    policy_mode: str = DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE


@dataclass(frozen=True)
class ReviewflowChunkHoundConfig:
    base_config_path: Path
    indexing_include: tuple[str, ...] | None = None
    indexing_exclude: tuple[str, ...] | None = None
    per_file_timeout_seconds: float | int | None = None
    per_file_timeout_min_size_kb: int | None = None
    research_algorithm: str | None = None


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorTargetContext:
    pr_url: str
    pr: PullRequestRef
    public_fallback_supported: bool
    public_pr_metadata_reachable: bool
    public_pr_metadata_detail: str


def _set_disabled_reviewflow_config_path(path: Path | None) -> None:
    global _DISABLED_REVIEWFLOW_CONFIG_PATH
    _DISABLED_REVIEWFLOW_CONFIG_PATH = path.resolve(strict=False) if path is not None else None


def _loaded_shell_module():
    import sys as _sys

    # Prefer the legacy shim when present so existing reviewflow.* monkeypatches
    # remain effective; otherwise fall back to the canonical cure shell.
    return _sys.modules.get("reviewflow") or _sys.modules.get("cure")


def _default_reviewflow_config_path() -> Path:
    rf = _loaded_shell_module()
    return rf.default_reviewflow_config_path() if rf is not None else default_reviewflow_config_path()


def _default_codex_base_config_path() -> Path:
    rf = _loaded_shell_module()
    return rf.default_codex_base_config_path() if rf is not None else default_codex_base_config_path()


def _default_sandbox_root() -> Path:
    rf = _loaded_shell_module()
    return rf.default_sandbox_root() if rf is not None else default_sandbox_root()


def _default_cache_root() -> Path:
    rf = _loaded_shell_module()
    return rf.default_cache_root() if rf is not None else default_cache_root()


def load_toml(path: Path) -> dict[str, Any]:
    disabled = _DISABLED_REVIEWFLOW_CONFIG_PATH
    if disabled is not None and path.resolve(strict=False) == disabled:
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as e:
        raise ReviewflowError(f"Failed to read TOML at {path}: {e}") from e
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ReviewflowError(f"Failed to parse TOML at {path}: {e}") from e


def toml_string(value: str) -> str:
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
    path = config_path or _default_reviewflow_config_path()
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
    path = config_path or _default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("codex", {}) if isinstance(raw, dict) else {}
    section = section if isinstance(section, dict) else {}
    return _resolve_optional_path(section.get("base_config_path"), base_dir=path.parent)


def resolve_reviewflow_config_path(args: argparse.Namespace) -> tuple[Path, str, bool]:
    config_path, config_source = _select_path_with_source(
        cli_value=getattr(args, "config_path", None),
        env_value=os.environ.get("REVIEWFLOW_CONFIG"),
        config_value=None,
        default_value=_default_reviewflow_config_path(),
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
        default_value=_default_sandbox_root(),
    )
    cache_root, cache_root_source = _select_path_with_source(
        cli_value=getattr(args, "cache_root", None),
        env_value=os.environ.get("REVIEWFLOW_CACHE_ROOT"),
        config_value=path_defaults.get("cache_root"),
        default_value=_default_cache_root(),
    )
    return ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root), sandbox_root_source, cache_root_source


def resolve_codex_base_config_path(args: argparse.Namespace, *, config_path: Path) -> tuple[Path, str]:
    return _select_path_with_source(
        cli_value=getattr(args, "codex_config_path", None),
        env_value=os.environ.get("REVIEWFLOW_CODEX_CONFIG"),
        config_value=load_reviewflow_codex_base_config_path(config_path=config_path),
        default_value=_default_codex_base_config_path(),
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


def resolve_llm_config_from_args(
    args: argparse.Namespace,
    *,
    reviewflow_config_path: Path | None = None,
    base_codex_config_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return resolve_llm_config(
        base_codex_config_path=(base_codex_config_path or _default_codex_base_config_path()),
        reviewflow_config_path=(reviewflow_config_path or _default_reviewflow_config_path()),
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
    path = config_path or _default_reviewflow_config_path()
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
    path = config_path or _default_reviewflow_config_path()
    raw = load_toml(path)
    wanted_keys = ("model", "model_reasoning_effort", "plan_mode_reasoning_effort")

    source_table = "codex"
    codex = raw.get("codex", {}) if isinstance(raw, dict) else {}
    codex = codex if isinstance(codex, dict) else {}
    if not any(isinstance(codex.get(key), str) and codex.get(key).strip() for key in wanted_keys):
        root_defaults = raw if isinstance(raw, dict) else {}
        if any(isinstance(root_defaults.get(key), str) and root_defaults.get(key).strip() for key in wanted_keys):
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


def _merge_builtin_preset(*, preset_id: str, raw_preset: dict[str, Any], source_mode: str) -> dict[str, Any]:
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
    path = config_path or _default_reviewflow_config_path()
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
    path = config_path or _default_reviewflow_config_path()
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

    def _pick(*, field: str, generic_value: Any, deprecated_value: Any = None, allow_deprecated: bool = False, base_value: Any = None) -> tuple[Any, str]:
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
        deprecated_value=(str(deprecated_codex_plan_effort).strip() if deprecated_codex_plan_effort else None),
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

    for key, val in (("reasoning_effort", reasoning_effort), ("plan_reasoning_effort", plan_reasoning_effort)):
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
            "deprecated_codex_model": (str(deprecated_codex_model).strip() if deprecated_codex_model else None),
            "deprecated_codex_effort": (str(deprecated_codex_effort).strip() if deprecated_codex_effort else None),
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
    base_cfg = load_toml(base_config_path)
    base_meta: dict[str, Any] = {"path": str(base_config_path), "loaded": bool(base_cfg)}

    base_model = base_cfg.get("model") if isinstance(base_cfg.get("model"), str) else None
    base_sandbox_mode = base_cfg.get("sandbox_mode") if isinstance(base_cfg.get("sandbox_mode"), str) else None
    base_web_search = base_cfg.get("web_search") if isinstance(base_cfg.get("web_search"), str) else None
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
    plan_effort, plan_effort_src = _pick("plan_mode_reasoning_effort", base_plan_effort, cli_plan_effort)

    for key, val in (("model_reasoning_effort", effort), ("plan_mode_reasoning_effort", plan_effort)):
        if val is None:
            continue
        if val not in CODEX_REASONING_EFFORT_CHOICES:
            raise ReviewflowError(
                f"Invalid {key}: {val!r}. Expected one of: {', '.join(CODEX_REASONING_EFFORT_CHOICES)}"
            )

    flags: list[str] = []
    if model:
        flags.extend(["-m", model])
    if isinstance(base_sandbox_mode, str) and base_sandbox_mode in {"read-only", "workspace-write", "danger-full-access"}:
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
    path = config_path or _default_reviewflow_config_path()
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
    raise _resolve_review_intelligence_config_error(path=(config_path or _default_reviewflow_config_path()))


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


def _parse_chunkhound_numeric_override(raw: object, *, field_name: str, allow_float: bool = False) -> int | float:
    if allow_float and isinstance(raw, (int, float)) and float(raw) > 0:
        return float(raw)
    if isinstance(raw, int) and raw > 0:
        return int(raw)
    raise ReviewflowError(f"Invalid [chunkhound].{field_name}: expected a positive number.")


def load_reviewflow_chunkhound_config(
    *, config_path: Path | None = None, require: bool = True
) -> tuple[ReviewflowChunkHoundConfig | None, dict[str, Any]]:
    path = config_path or _default_reviewflow_config_path()
    raw = load_toml(path)
    section = raw.get("chunkhound") if isinstance(raw, dict) else None

    if section is None:
        if require:
            raise _chunkhound_config_error(reason="Missing required `[chunkhound]` section.", path=path)
        return None, {"config_path": str(path), "loaded": bool(raw), "chunkhound": None}

    if not isinstance(section, dict):
        raise _chunkhound_config_error(reason="`[chunkhound]` must be a table.", path=path)

    base_config_path_raw = str(section.get("base_config_path") or "").strip()
    if not base_config_path_raw:
        raise _chunkhound_config_error(reason="`[chunkhound].base_config_path` is required.", path=path)
    base_config_path = Path(base_config_path_raw).expanduser()
    if not base_config_path.is_absolute():
        raise _chunkhound_config_error(reason="`[chunkhound].base_config_path` must be an absolute path.", path=path)
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

    indexing_include = tuple(_string_list(indexing.get("include"))) if ("include" in indexing) else None
    indexing_exclude = tuple(_string_list(indexing.get("exclude"))) if ("exclude" in indexing) else None
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
    research_algorithm = str(research.get("algorithm") or "").strip() if ("algorithm" in research) else None
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
            "research": {"algorithm": research_algorithm},
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


def _doctor_executable_check(name: str) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return DoctorCheck(name=name, status="ok", detail=path)
    return DoctorCheck(name=name, status="fail", detail="not found on PATH")


def _default_jira_config_path() -> Path:
    rf = _loaded_shell_module()
    if rf is not None:
        candidate = getattr(rf, "_default_jira_config_path", None)
        if callable(candidate) and candidate is not _default_jira_config_path:
            return candidate()
    env_path = _resolve_optional_path(os.environ.get("JIRA_CONFIG_FILE"))
    if env_path is not None:
        return env_path
    return (Path.home() / ".config" / ".jira" / ".config.yml").resolve(strict=False)


def _doctor_gh_auth_check(*, host: str = "github.com") -> DoctorCheck:
    if shutil.which("gh") is None:
        return DoctorCheck(name="gh-auth", status="fail", detail="`gh` is not installed")
    try:
        run_cmd(["gh", "auth", "status", "--hostname", host], check=True)
    except ReviewflowSubprocessError as e:
        msg = e.stderr.strip() or e.stdout.strip() or "not authenticated"
        return DoctorCheck(name="gh-auth", status="fail", detail=msg)
    return DoctorCheck(name="gh-auth", status="ok", detail=f"authenticated for {host}")


def _supports_public_github_fallback(host: str) -> bool:
    return host == "github.com"


def _doctor_public_pr_probe(pr: PullRequestRef) -> tuple[bool, str]:
    if not _supports_public_github_fallback(pr.host):
        return False, f"anonymous public fallback is not supported for {pr.host}"
    path = f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}"
    req = urllib.request.Request(
        f"https://api.github.com{path}",
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
        return False, f"anonymous public PR metadata probe failed ({e.code}): {body.strip() or path}"
    except urllib.error.URLError as e:
        return False, f"anonymous public PR metadata probe failed: {e}"
    try:
        payload = json.loads(body)
    except Exception as e:
        return False, f"anonymous public PR metadata probe returned invalid JSON: {e}"
    if not isinstance(payload, dict):
        return False, "anonymous public PR metadata probe returned an unexpected payload"
    return True, "anonymous public GitHub PR metadata is reachable"


def _resolve_doctor_target_context(pr_url: str | None) -> DoctorTargetContext | None:
    text = str(pr_url or "").strip()
    if not text:
        return None
    pr = parse_pr_url(text)
    public_fallback_supported = _supports_public_github_fallback(pr.host)
    public_reachable = False
    public_detail = f"anonymous public fallback is not supported for {pr.host}"
    if public_fallback_supported:
        public_reachable, public_detail = _doctor_public_pr_probe(pr)
    return DoctorTargetContext(
        pr_url=text,
        pr=pr,
        public_fallback_supported=public_fallback_supported,
        public_pr_metadata_reachable=public_reachable,
        public_pr_metadata_detail=public_detail,
    )


def _doctor_optional_check(*, name: str, detail: str) -> DoctorCheck:
    return DoctorCheck(name=name, status="warn", detail=detail)


def _doctor_acknowledged_sources(*, target: DoctorTargetContext | None) -> dict[str, Any]:
    gh = _doctor_executable_check("gh")
    git = _doctor_executable_check("git")
    jira = _doctor_executable_check("jira")
    target_host = (target.pr.host if target is not None else "github.com")
    gh_auth = _doctor_gh_auth_check(host=target_host)
    jira_cfg = _default_jira_config_path()
    payload: dict[str, Any] = {
        "github": {
            "host": target_host,
            "gh_cli": {"status": gh.status, "detail": gh.detail},
            "gh_auth": {"status": gh_auth.status, "detail": gh_auth.detail},
            "git": {"status": git.status, "detail": git.detail},
        },
        "jira": {
            "required_for_pr_reviews": False,
            "config": {
                "status": ("ok" if jira_cfg.is_file() else "warn"),
                "detail": (str(jira_cfg) if jira_cfg.is_file() else f"missing: {jira_cfg}"),
            },
            "cli": {
                "status": ("ok" if jira.status == "ok" else "warn"),
                "detail": jira.detail,
            },
        },
    }
    if target is not None:
        payload["github"]["public_fallback"] = {
            "supported": target.public_fallback_supported,
            "status": ("ok" if target.public_pr_metadata_reachable else "warn"),
            "detail": target.public_pr_metadata_detail,
        }
    return payload


def _doctor_path_payload(*, path: Path, source: str, exists: bool, enabled: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "source": source, "exists": bool(exists)}
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
                    None if profile == "permissive" else ("plan" if profile == "strict" else "dontAsk")
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


def _doctor_runtime_payload(
    runtime: ReviewflowRuntime,
    *,
    cli_profile: str | None = None,
    pr_url: str | None = None,
) -> dict[str, Any]:
    target = _resolve_doctor_target_context(pr_url)
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
        "acknowledged_sources": _doctor_acknowledged_sources(target=target),
    }
    if target is not None:
        payload["target"] = {
            "kind": "pull_request",
            "pr_url": target.pr_url,
            "host": target.pr.host,
            "owner": target.pr.owner,
            "repo": target.pr.repo,
            "number": target.pr.number,
            "public_fallback_supported": target.public_fallback_supported,
            "public_pr_metadata_reachable": target.public_pr_metadata_reachable,
            "public_pr_metadata_detail": target.public_pr_metadata_detail,
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


def _doctor_runtime_checks(
    runtime: ReviewflowRuntime,
    *,
    cli_profile: str | None = None,
    pr_url: str | None = None,
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    target = _resolve_doctor_target_context(pr_url)
    agent_runtime = _resolved_doctor_agent_runtime(runtime, cli_profile=cli_profile)
    config_path = runtime.config_path
    config_prefix = f"{config_path} (source={runtime.config_source})"
    if not runtime.config_enabled:
        checks.append(DoctorCheck(name="reviewflow-config", status="warn", detail=f"{config_prefix} (disabled by --no-config)"))
    elif config_path.is_file():
        checks.append(DoctorCheck(name="reviewflow-config", status="ok", detail=config_prefix))
    else:
        checks.append(DoctorCheck(name="reviewflow-config", status="fail", detail=f"missing: {config_prefix}"))

    path_defaults, _ = load_reviewflow_paths_defaults(config_path=config_path)
    sandbox_detail = f"{runtime.paths.sandbox_root} (source={runtime.sandbox_root_source})"
    if runtime.sandbox_root_source == "config" and path_defaults.get("sandbox_root") is not None:
        sandbox_detail += " (configured)"
    if runtime.paths.sandbox_root.exists():
        checks.append(DoctorCheck(name="sandbox-root", status="ok", detail=sandbox_detail))
    else:
        checks.append(DoctorCheck(name="sandbox-root", status="warn", detail=f"{sandbox_detail} (will be created on demand)"))

    cache_detail = f"{runtime.paths.cache_root} (source={runtime.cache_root_source})"
    if runtime.cache_root_source == "config" and path_defaults.get("cache_root") is not None:
        cache_detail += " (configured)"
    if runtime.paths.cache_root.exists():
        checks.append(DoctorCheck(name="cache-root", status="ok", detail=cache_detail))
    else:
        checks.append(DoctorCheck(name="cache-root", status="warn", detail=f"{cache_detail} (will be created on demand)"))

    if not runtime.config_enabled:
        checks.append(DoctorCheck(name="chunkhound-config", status="warn", detail="disabled by --no-config"))
    else:
        try:
            chunkhound_cfg, _ = load_reviewflow_chunkhound_config(config_path=config_path, require=True)
        except ReviewflowError as e:
            checks.append(DoctorCheck(name="chunkhound-config", status="fail", detail=str(e).splitlines()[0]))
        else:
            assert chunkhound_cfg is not None
            chunkhound_detail = f"{chunkhound_cfg.base_config_path} (source=config)"
            if chunkhound_cfg.base_config_path.is_file():
                checks.append(DoctorCheck(name="chunkhound-config", status="ok", detail=chunkhound_detail))
            else:
                checks.append(DoctorCheck(name="chunkhound-config", status="fail", detail=f"missing base_config_path: {chunkhound_detail}"))

    if target is not None:
        checks.append(
            DoctorCheck(
                name="review-target",
                status="ok",
                detail=f"{target.pr.owner}/{target.pr.repo}#{target.pr.number} ({target.pr.host})",
            )
        )

    jira_cfg = _default_jira_config_path()
    if jira_cfg.is_file():
        checks.append(DoctorCheck(name="jira-config", status="ok", detail=str(jira_cfg)))
    elif target is not None:
        checks.append(
            _doctor_optional_check(
                name="jira-config",
                detail=f"missing: {jira_cfg} (optional for normal PR review lifecycle flows; only needed for Jira-driven workflows)",
            )
        )
    else:
        checks.append(
            _doctor_optional_check(
                name="jira-config",
                detail=f"missing: {jira_cfg} (target-dependent; not required for all review flows)",
            )
        )

    if runtime.codex_base_config_path.is_file():
        checks.append(DoctorCheck(name="codex-config", status="ok", detail=f"{runtime.codex_base_config_path} (source={runtime.codex_base_config_source})"))
    else:
        checks.append(DoctorCheck(name="codex-config", status="warn", detail=f"missing: {runtime.codex_base_config_path} (source={runtime.codex_base_config_source})"))

    checks.append(_doctor_executable_check("chunkhound"))
    gh_check = _doctor_executable_check("gh")
    jira_check = _doctor_executable_check("jira")
    codex_check = _doctor_executable_check("codex")
    if target is not None:
        git_check = _doctor_executable_check("git")
        checks.append(git_check)
        public_ok = target.public_fallback_supported and target.public_pr_metadata_reachable
        if gh_check.status == "ok":
            checks.append(gh_check)
        elif public_ok and git_check.status == "ok":
            checks.append(
                DoctorCheck(
                    name="gh",
                    status="ok",
                    detail=f"{gh_check.detail} (not required for public github.com PR lifecycle flows such as `pr`, `resume`, `followup`, and `zip`; anonymous fallback confirmed)",
                )
            )
        else:
            checks.append(gh_check)

        if jira_check.status == "ok":
            checks.append(jira_check)
        else:
            checks.append(
                _doctor_optional_check(
                    name="jira",
                    detail=f"{jira_check.detail} (optional for normal PR review lifecycle flows; only needed for Jira-driven workflows)",
                )
            )

        gh_auth = _doctor_gh_auth_check(host=target.pr.host)
        if gh_auth.status == "ok":
            checks.append(gh_auth)
        elif public_ok and git_check.status == "ok":
            checks.append(
                DoctorCheck(
                    name="gh-auth",
                    status="ok",
                    detail=f"{gh_auth.detail} (anonymous public github.com fallback confirmed)",
                )
            )
        else:
            checks.append(gh_auth)

        if git_check.status != "ok":
            checks.append(
                DoctorCheck(
                    name="github-pr-access",
                    status="fail",
                    detail="`git` is required for PR clone/checkout.",
                )
            )
        elif gh_auth.status == "ok":
            checks.append(
                DoctorCheck(
                    name="github-pr-access",
                    status="ok",
                    detail=f"authenticated GitHub access is available for {target.pr.host}",
                )
            )
        elif public_ok:
            checks.append(
                DoctorCheck(
                    name="github-pr-access",
                    status="ok",
                    detail=target.public_pr_metadata_detail,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="github-pr-access",
                    status="fail",
                    detail=f"no usable GitHub PR source of truth for {target.pr.owner}/{target.pr.repo}#{target.pr.number}",
                )
            )
    else:
        checks.append(
            gh_check
            if gh_check.status == "ok"
            else _doctor_optional_check(
                name="gh",
                detail=f"{gh_check.detail} (target-dependent; public github.com PR lifecycle flows can use fallback)",
            )
        )
        checks.append(
            jira_check
            if jira_check.status == "ok"
            else _doctor_optional_check(
                name="jira",
                detail=f"{jira_check.detail} (target-dependent; only needed for Jira-driven workflows)",
            )
        )
    checks.append(codex_check)
    provider = str(agent_runtime.get("provider") or "").strip().lower()
    command = str(agent_runtime.get("command") or "").strip()
    if bool(agent_runtime.get("supported")) and provider and command and (provider != "codex"):
        selected = _doctor_executable_check(command)
        checks.append(DoctorCheck(name="agent-runtime-command", status=selected.status, detail=f"{provider}: {selected.detail}"))
    if provider == "gemini" and str(agent_runtime.get("profile") or "") == "strict":
        if bool(agent_runtime.get("strict_ready")):
            checks.append(DoctorCheck(name="agent-runtime", status="ok", detail="gemini strict runtime backend configured"))
        else:
            checks.append(DoctorCheck(name="agent-runtime", status="fail", detail="gemini strict runtime requires [agent_runtime.gemini].sandbox"))
    if target is None:
        gh_auth = _doctor_gh_auth_check()
        checks.append(
            gh_auth
            if gh_auth.status == "ok"
            else _doctor_optional_check(
                name="gh-auth",
                detail=f"{gh_auth.detail} (target-dependent; public github.com PR lifecycle flows can use fallback)",
            )
        )
    return checks


__all__ = [
    "AGENT_RUNTIME_PROFILE_CHOICES",
    "BUILTIN_LLM_PRESET_IDS",
    "CHUNKHOUND_CONFIG_EXAMPLE",
    "CLI_LLM_PROVIDERS",
    "CODEX_REASONING_EFFORT_CHOICES",
    "CURATED_ENV_INHERIT_KEYS",
    "DEFAULT_AGENT_RUNTIME_PROFILE",
    "DEFAULT_LEGACY_CODEX_PRESET",
    "DEFAULT_MULTIPASS_ENABLED",
    "DEFAULT_MULTIPASS_MAX_STEPS",
    "DEFAULT_REVIEW_INTELLIGENCE_POLICY_MODE",
    "DoctorCheck",
    "HTTP_LLM_PROVIDERS",
    "LLM_RESUME_PROVIDERS",
    "LLM_TRANSPORT_CHOICES",
    "MULTIPASS_MAX_STEPS_HARD_CAP",
    "REVIEW_INTELLIGENCE_CONFIG_EXAMPLE",
    "ReviewIntelligenceConfig",
    "ReviewflowChunkHoundConfig",
    "ReviewflowRuntime",
    "_default_jira_config_path",
    "_dedupe_paths",
    "_doctor_runtime_checks",
    "_doctor_runtime_payload",
    "_plain_dict",
    "_set_disabled_reviewflow_config_path",
    "_string_dict",
    "_string_list",
    "apply_llm_env",
    "build_curated_subprocess_env",
    "build_http_response_request",
    "build_llm_meta",
    "build_review_intelligence_guidance",
    "builtin_llm_presets",
    "fingerprint_chunkhound_reviewflow_config",
    "load_chunkhound_runtime_config",
    "load_review_intelligence_config",
    "load_reviewflow_agent_runtime_config",
    "load_reviewflow_chunkhound_config",
    "load_reviewflow_codex_base_config_path",
    "load_reviewflow_codex_defaults",
    "load_reviewflow_llm_config",
    "load_reviewflow_multipass_defaults",
    "load_reviewflow_paths_defaults",
    "load_toml",
    "parse_llm_header_overrides",
    "parse_llm_key_value",
    "parse_llm_request_overrides",
    "require_builtin_review_intelligence",
    "resolve_agent_runtime_profile",
    "resolve_chunkhound_reviewflow_config",
    "resolve_codex_base_config_path",
    "resolve_codex_flags",
    "resolve_llm_config",
    "resolve_llm_config_from_args",
    "resolve_reviewflow_config_path",
    "resolve_runtime",
    "resolve_runtime_paths",
    "resolve_ui_enabled",
    "resolve_verbosity",
    "toml_string",
]
