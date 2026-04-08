#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
_ABSOLUTE_PATH_ROOTS = ("tmp", "home", "workspaces", "opt", "usr", "var", "private", "Users", "nix", "etc")
_ABSOLUTE_PATH_RE = re.compile(
    rf"(?<![A-Za-z0-9_.<>:-])/(?:{'|'.join(_ABSOLUTE_PATH_ROOTS)})(?:/[^/\s\"'<>]+)*"
)
_CHUNKHOUND_QUERY_RE = re.compile(r'("?\$CURE_CHUNKHOUND_HELPER"?\s+(?:search|research)\s+")([^"]+)(")')
_BACKGROUND_TASK_ID_RE = re.compile(r"\bID: [A-Za-z0-9]+\b")
_BACKGROUND_OUTPUT_RE = re.compile(r"(Output is being written to: )/[^ ]+")
_NO_RELEVANT_CODE_CONTEXT_RE = re.compile(r"(No relevant code context found for: )'[^']+'")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the real Claude CLI transport used by CURe.")
    parser.add_argument(
        "--prompt",
        default="Reply with two short lines: line one says OK, line two says STREAM TEST.",
        help="Prompt to send to Claude.",
    )
    parser.add_argument("--model", default="", help="Optional Claude model override.")
    parser.add_argument("--budget", type=float, default=0.05, help="Max budget in USD for each probe.")
    parser.add_argument(
        "--mode",
        choices=("json", "stream-json", "both"),
        default="both",
        help="Which Claude transport(s) to probe.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra environment assignment to pass through to Claude. May be repeated.",
    )
    parser.add_argument(
        "--save-stream-json",
        default="",
        help="Optional path to save a sanitized NDJSON copy of the captured stream-json stdout.",
    )
    parser.add_argument(
        "--stage-chunkhound-helper",
        action="store_true",
        help="Generate a temporary staged ChunkHound helper and export CURE_CHUNKHOUND_HELPER for the probe.",
    )
    parser.add_argument(
        "--helper-repo-dir",
        default=str(REPO_ROOT),
        help="Repo path embedded into the staged ChunkHound helper when --stage-chunkhound-helper is used.",
    )
    parser.add_argument(
        "--helper-cwd",
        default=str(REPO_ROOT),
        help="ChunkHound working directory embedded into the staged helper when --stage-chunkhound-helper is used.",
    )
    return parser.parse_args()


def build_cmd(*, mode: str, prompt: str, model: str, budget: float) -> list[str]:
    cmd = ["claude", "--print", "--dangerously-skip-permissions", "--max-budget-usd", str(budget)]
    if model:
        cmd.extend(["--model", model])
    if mode == "json":
        cmd.extend(["--output-format", "json"])
    elif mode == "stream-json":
        cmd.extend(
            [
                "--verbose",
                "--output-format",
                "stream-json",
                "--include-partial-messages",
            ]
        )
    else:
        raise ValueError(f"unsupported probe mode: {mode}")
    cmd.append(prompt)
    return cmd


def _parse_env_assignments(assignments: list[str]) -> dict[str, str]:
    env_overrides: dict[str, str] = {}
    for raw in assignments:
        text = str(raw or "").strip()
        if not text:
            continue
        key, sep, value = text.partition("=")
        ensure(bool(sep) and bool(key.strip()), f"invalid --env assignment: {raw!r}")
        env_overrides[key.strip()] = value
    return env_overrides


def _sanitize_text_value(
    text: str,
    *,
    key: str | None,
    path: tuple[str, ...],
    replacements: dict[str, str],
) -> str:
    for old, new in replacements.items():
        if old and text == old:
            return new
    if key == "partial_json" and text:
        return "<PARTIAL_JSON_DELTA>"
    if key == "backgroundTaskId" and text:
        return "<BACKGROUND_TASK_ID>"
    if key == "task_id" and text:
        return "<BACKGROUND_TASK_ID>"
    if key == "description" and text:
        return "<DESCRIPTION>"
    if key == "query" and text:
        return "<QUERY>"
    if key == "summary" and text:
        return "<SUMMARY>"
    if key == "statement" and text:
        return "<STATEMENT>"
    if key == "signature" and text:
        return "<SIGNATURE>"
    if key == "helper_path" and text:
        return "<CURE_CHUNKHOUND_HELPER>"
    if path[-3:] == ("result", "results", "content") and text:
        return "<RESULT_CONTENT>"
    if key and (key.endswith("_path") or key in {"cwd", "chunkhound_path", "chunkhound_runtime_python", "chunkhound_module_path"}):
        if text.startswith("/"):
            return "<ABS_PATH>"
    for old, new in replacements.items():
        if old:
            text = text.replace(old, new)
    if key == "prompt" and text:
        return "<PROMPT>"
    text = _CHUNKHOUND_QUERY_RE.sub(r"\1<QUERY>\3", text)
    text = _NO_RELEVANT_CODE_CONTEXT_RE.sub(r"\1'<QUERY>'", text)
    text = _BACKGROUND_TASK_ID_RE.sub("ID: <BACKGROUND_TASK_ID>", text)
    text = _BACKGROUND_OUTPUT_RE.sub(r"\1<ABS_PATH>", text)
    text = _ABSOLUTE_PATH_RE.sub("<ABS_PATH>", text)
    return text


def _sanitize_value(
    value: Any,
    *,
    replacements: dict[str, str],
    key: str | None = None,
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _sanitize_value(v, replacements=replacements, key=str(k), path=path + (str(k),))
            for k, v in value.items()
            if str(k) != "apiKeySource"
        }
    if isinstance(value, list):
        return [_sanitize_value(item, replacements=replacements, key=key, path=path) for item in value]
    if not isinstance(value, str):
        return value
    text = str(value)
    if key == "uuid" and text:
        return "<UUID>"
    if key == "tool_use_id" and text:
        return "<CLAUDE_TOOL_USE_ID>"
    if key == "session_id" and text:
        return "<CLAUDE_SESSION_ID>"
    if key == "id" and text.startswith("msg_"):
        return "<CLAUDE_MESSAGE_ID>"
    if key == "id" and text.startswith("toolu_"):
        return "<CLAUDE_TOOL_USE_ID>"
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            nested = json.loads(text)
        except Exception:
            pass
        else:
            sanitized_nested = _sanitize_value(nested, replacements=replacements, key=key, path=path)
            return json.dumps(sanitized_nested, sort_keys=True)
    return _sanitize_text_value(text, key=key, path=path, replacements=replacements)


def _sanitize_stream_lines(*, stdout_lines: list[str], replacements: dict[str, str]) -> list[str]:
    sanitized: list[str] = []
    for raw in stdout_lines:
        try:
            payload = json.loads(raw)
        except Exception:
            text = str(raw)
            for old, new in replacements.items():
                if old:
                    text = text.replace(old, new)
            sanitized.append(text)
            continue
        sanitized.append(json.dumps(_sanitize_value(payload, replacements=replacements), sort_keys=True))
    return sanitized


def _write_stream_fixture(*, output_path: Path, stdout_lines: list[str], replacements: dict[str, str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_stream_lines(stdout_lines=stdout_lines, replacements=replacements)
    output_path.write_text("\n".join(sanitized) + ("\n" if sanitized else ""), encoding="utf-8")


def _stage_chunkhound_helper(*, helper_repo_dir: Path, helper_cwd: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    import cure_llm

    temp_root = tempfile.TemporaryDirectory(prefix="cure_real_claude_probe_")
    helper = cure_llm.write_chunkhound_helper(
        work_dir=Path(temp_root.name) / "work",
        repo_dir=helper_repo_dir,
        chunkhound_config_path=None,
        chunkhound_db_path=None,
        chunkhound_cwd=helper_cwd,
    )
    return temp_root, helper


def run_probe(
    *,
    mode: str,
    prompt: str,
    model: str,
    budget: float,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    cmd = build_cmd(mode=mode, prompt=prompt, model=model, budget=budget)
    env = os.environ.copy()
    if isinstance(env_overrides, dict):
        env.update({str(k): str(v) for k, v in env_overrides.items()})
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    first_stdout_at: float | None = None
    first_stderr_at: float | None = None

    while True:
        line = proc.stdout.readline()
        if line:
            if first_stdout_at is None:
                first_stdout_at = time.monotonic()
            stdout_lines.append(line.rstrip("\n"))
            continue
        err_line = proc.stderr.readline()
        if err_line:
            if first_stderr_at is None:
                first_stderr_at = time.monotonic()
            stderr_lines.append(err_line.rstrip("\n"))
            continue
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    stdout_tail = proc.stdout.read()
    stderr_tail = proc.stderr.read()
    if stdout_tail:
        if first_stdout_at is None:
            first_stdout_at = time.monotonic()
        stdout_lines.extend(line for line in stdout_tail.splitlines())
    if stderr_tail:
        if first_stderr_at is None:
            first_stderr_at = time.monotonic()
        stderr_lines.extend(line for line in stderr_tail.splitlines())

    rc = proc.wait()
    duration = time.monotonic() - started
    result: dict[str, Any] = {
        "mode": mode,
        "cmd": cmd,
        "exit_code": rc,
        "duration_seconds": round(duration, 3),
        "stdout_line_count": len(stdout_lines),
        "stderr_line_count": len(stderr_lines),
        "stdout_preview": stdout_lines[:8],
        "stderr_preview": stderr_lines[:8],
        "first_stdout_after_seconds": (round(first_stdout_at - started, 3) if first_stdout_at is not None else None),
        "first_stderr_after_seconds": (round(first_stderr_at - started, 3) if first_stderr_at is not None else None),
        "stdout_lines": stdout_lines,
        "stderr_lines": stderr_lines,
    }

    if mode == "stream-json":
        delta_texts: list[str] = []
        result_text = ""
        for raw in stdout_lines:
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("type") or "") == "stream_event":
                event = payload.get("event")
                event = event if isinstance(event, dict) else {}
                if str(event.get("type") or "") == "content_block_delta":
                    delta = event.get("delta")
                    delta = delta if isinstance(delta, dict) else {}
                    if str(delta.get("type") or "") == "text_delta":
                        text = str(delta.get("text") or "")
                        if text:
                            delta_texts.append(text)
            if str(payload.get("type") or "") == "result":
                result_text = str(payload.get("result") or "").strip()
        result["stream_delta_count"] = len(delta_texts)
        result["stream_delta_preview"] = delta_texts[:8]
        result["result_text"] = result_text
        result["has_incremental_output"] = len(delta_texts) > 0
    else:
        final_payload: dict[str, Any] | None = None
        for raw in reversed(stdout_lines):
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                final_payload = parsed
                break
        result["result_text"] = str((final_payload or {}).get("result") or "").strip()

    return result


def main() -> int:
    args = parse_args()
    ensure(shutil.which("claude") is not None, "claude is not on PATH")
    env_overrides = _parse_env_assignments(list(args.env or []))
    helper_temp: tempfile.TemporaryDirectory[str] | None = None
    helper_path: Path | None = None
    helper_repo_dir = Path(args.helper_repo_dir).resolve(strict=False)
    helper_cwd = Path(args.helper_cwd).resolve(strict=False)
    if args.stage_chunkhound_helper:
        helper_temp, helper_path = _stage_chunkhound_helper(
            helper_repo_dir=helper_repo_dir,
            helper_cwd=helper_cwd,
        )
        env_overrides.setdefault("CURE_CHUNKHOUND_HELPER", str(helper_path))
        env_overrides.setdefault("PYTHONSAFEPATH", "1")

    try:
        modes = [args.mode] if args.mode != "both" else ["json", "stream-json"]
        results = [
            run_probe(
                mode=mode,
                prompt=args.prompt,
                model=args.model,
                budget=args.budget,
                env_overrides=env_overrides,
            )
            for mode in modes
        ]
        if args.save_stream_json:
            stream_result = next((item for item in results if str(item.get("mode")) == "stream-json"), None)
            ensure(stream_result is not None, "--save-stream-json requires a stream-json probe result")
            assert stream_result is not None
            replacements = {
                str(REPO_ROOT): "<CURE_REPO_ROOT>",
                str(helper_repo_dir): "<HELPER_REPO_DIR>",
                str(helper_cwd): "<HELPER_CWD>",
            }
            if helper_path is not None:
                replacements[str(helper_path)] = "<CURE_CHUNKHOUND_HELPER>"
            if helper_temp is not None:
                replacements[str(Path(helper_temp.name).resolve(strict=False))] = "<PROBE_TMP_ROOT>"
            _write_stream_fixture(
                output_path=Path(args.save_stream_json),
                stdout_lines=[str(line) for line in stream_result.get("stdout_lines") or []],
                replacements=replacements,
            )

        if args.json:
            print(json.dumps({"results": results}, indent=2, sort_keys=True))
        else:
            for result in results:
                print(f"{result['mode']}: rc={result['exit_code']} duration={result['duration_seconds']}s")
                print(
                    "  first_output="
                    f"stdout:{result['first_stdout_after_seconds']}s stderr:{result['first_stderr_after_seconds']}s"
                )
                print(
                    "  lines="
                    f"stdout:{result['stdout_line_count']} stderr:{result['stderr_line_count']}"
                )
                if "has_incremental_output" in result:
                    print(f"  incremental={result['has_incremental_output']} deltas={result['stream_delta_count']}")
                if result.get("result_text"):
                    print(f"  result={result['result_text']!r}")
    finally:
        if helper_temp is not None:
            helper_temp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
