#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def run_probe(*, mode: str, prompt: str, model: str, budget: float) -> dict[str, Any]:
    cmd = build_cmd(mode=mode, prompt=prompt, model=model, budget=budget)
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
        payload: dict[str, Any] | None = None
        for raw in reversed(stdout_lines):
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break
        result["result_text"] = str((payload or {}).get("result") or "").strip()

    return result


def main() -> int:
    args = parse_args()
    ensure(shutil.which("claude") is not None, "claude is not on PATH")

    modes = [args.mode] if args.mode != "both" else ["json", "stream-json"]
    results = [run_probe(mode=mode, prompt=args.prompt, model=args.model, budget=args.budget) for mode in modes]

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
