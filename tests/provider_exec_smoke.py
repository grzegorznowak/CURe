#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import cure as rf  # noqa: E402
import cure_output  # noqa: E402
import cure_runtime  # noqa: E402
import ui as rui  # noqa: E402


def _sectioned_review_markdown(*, business: str, technical: str) -> str:
    return "\n".join(
        [
            "**Summary**: smoke ok",
            "",
            "## Business / Product Assessment",
            f"**Verdict**: {business}",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            f"**Verdict**: {technical}",
            "",
            "### In Scope Issues",
            "- None.",
            "",
        ]
    )


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def build_env(*, tmp_root: Path, fake_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_root / "home")
    env["XDG_CONFIG_HOME"] = str(tmp_root / "xdg_config")
    env["XDG_STATE_HOME"] = str(tmp_root / "xdg_state")
    env["XDG_CACHE_HOME"] = str(tmp_root / "xdg_cache")
    env["TERM"] = "dumb"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env.pop("CURE_CONFIG", None)
    env.pop("REVIEWFLOW_CONFIG", None)
    return env


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def write_fake_codex(bin_dir: Path, review_text: str) -> None:
    body = f"""#!/usr/bin/env python3
from __future__ import annotations
import json
import sys

review = {review_text!r}
events = [
    {{"type": "thread.started", "thread_id": "smoke-thread"}},
    {{"type": "turn.started"}},
    {{"type": "item.completed", "item": {{"type": "agent_message", "text": review}}}},
    {{"type": "turn.completed", "usage": {{"output_tokens": 77}}}},
]
for event in events:
    print(json.dumps(event), flush=True)
"""
    _write_executable(bin_dir / "codex", body)


class _ResponseHandler(BaseHTTPRequestHandler):
    review_text = _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES")

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        payload = json.loads(body)
        response = {
            "id": "resp-smoke",
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": self.review_text,
                        }
                    ]
                }
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
            "echo_model": payload.get("model"),
        }
        response_bytes = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format: str, *args: object) -> None:
        return None


class LocalResponsesServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _ResponseHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


def _init_progress(*, session_dir: Path, logs_dir: Path, review_md: Path, provider: str) -> rf.SessionProgress:
    meta_path = session_dir / "meta.json"
    progress = rf.SessionProgress(meta_path, quiet=True)
    progress.init(
        {
            "session_id": f"smoke-{provider}",
            "status": "running",
            "phase": f"{provider}_review",
            "phases": {f"{provider}_review": {"status": "running"}},
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": f"{provider} smoke",
            "paths": {
                "repo_dir": str(session_dir / "repo"),
                "work_dir": str(session_dir / "work"),
                "logs_dir": str(logs_dir),
                "review_md": str(review_md),
            },
            "logs": {
                "cure": str(logs_dir / "cure.log"),
                "chunkhound": str(logs_dir / "chunkhound.log"),
                "codex": str(logs_dir / "codex.log"),
            },
            "llm": {"provider": provider},
        }
    )
    return progress


def _build_cli_runtime_policy(
    *,
    provider: str,
    resolved: dict[str, Any],
    resolution_meta: dict[str, Any],
    repo_dir: Path,
    session_dir: Path,
    work_dir: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    args = argparse.Namespace(agent_runtime_profile="permissive")
    return rf.prepare_review_agent_runtime(
        args=args,
        resolved=resolved,
        resolution_meta=resolution_meta,
        reviewflow_config_path=work_dir / "runtime.toml",
        config_enabled=False,
        repo_dir=repo_dir,
        session_dir=session_dir,
        work_dir=work_dir,
        base_env=env,
        chunkhound_config_path=work_dir / "chunkhound.json",
        chunkhound_db_path=work_dir / ".chunkhound.db",
        chunkhound_cwd=work_dir / "chunkhound",
        enable_mcp=False,
        interactive=False,
        paths=rf.DEFAULT_PATHS,
    )


def run_provider_smoke(
    *,
    provider: str,
    tmp_root: Path,
    fake_bin: Path,
    base_env: dict[str, str],
    responses_base_url: str,
) -> dict[str, Any]:
    session_dir = tmp_root / f"session-{provider}"
    repo_dir = session_dir / "repo"
    work_dir = session_dir / "work"
    logs_dir = work_dir / "logs"
    output_path = session_dir / "review.md"
    repo_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    progress = _init_progress(session_dir=session_dir, logs_dir=logs_dir, review_md=output_path, provider=provider)
    stderr = StringIO()
    output = cure_output.ReviewflowOutput(
        ui_enabled=True,
        no_stream=False,
        stderr=stderr,
        meta_path=session_dir / "meta.json",
        logs_dir=logs_dir,
        verbosity=rui.Verbosity.normal,
    )
    output.start()
    cure_output.set_active_output(output)
    try:
        prompt = "Smoke test review this PR."
        resolution_meta: dict[str, Any] = {"base_codex_config": {}, "reviewflow_defaults": {}, "resolved": {}}
        runtime_policy: dict[str, Any] | None = None

        if provider in cure_runtime.CLI_LLM_PROVIDERS:
            preset_name = f"{provider}-cli"
            resolved = dict(cure_runtime.builtin_llm_presets()[preset_name])
            resolved["preset"] = preset_name
            resolved["command"] = str(fake_bin / provider)
            runtime_policy = _build_cli_runtime_policy(
                provider=provider,
                resolved=resolved,
                resolution_meta=resolution_meta,
                repo_dir=repo_dir,
                session_dir=session_dir,
                work_dir=work_dir,
                env=base_env,
            )
            env = dict(runtime_policy["env"])
        elif provider == "openai":
            resolved = {
                "preset": "openai-responses",
                "transport": "http",
                "provider": "openai",
                "endpoint": "responses",
                "base_url": responses_base_url,
                "api_key": "smoke-openai-key",  # pragma: allowlist secret
                "model": "gpt-5-mini",
                "headers": {},
                "request": {},
                "metadata": {},
                "include": [],
            }
            env = dict(base_env)
        elif provider == "openrouter":
            resolved = {
                "preset": "openrouter-responses",
                "transport": "http",
                "provider": "openrouter",
                "endpoint": "responses",
                "base_url": responses_base_url,
                "api_key": "smoke-openrouter-key",  # pragma: allowlist secret
                "model": "openai/gpt-5-mini",
                "headers": {
                    "HTTP-Referer": "https://example.test",
                    "X-OpenRouter-Title": "provider-smoke",
                },
                "request": {},
                "metadata": {},
                "include": [],
            }
            env = dict(base_env)
        else:
            raise SystemExit(f"unsupported smoke provider: {provider}")

        result = rf.run_llm_exec(
            repo_dir=repo_dir,
            resolved=resolved,
            resolution_meta=resolution_meta,
            output_path=output_path,
            prompt=prompt,
            env=env,
            stream=True,
            progress=progress,
            runtime_policy=runtime_policy,
        )
        meta = dict(progress.meta)
        review_text = output_path.read_text(encoding="utf-8")
        ensure("## Technical Assessment" in review_text, f"{provider}: review artifact missing expected content")
        dashboard_lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=output.tails["codex"].tail(400),
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        dashboard_joined = "\n".join(dashboard_lines)

        live = meta.get("live_progress")
        live = live if isinstance(live, dict) else {}
        current_text = (
            str((live.get("current") or {}).get("text") or "").strip()
            if isinstance(live.get("current"), dict)
            else ""
        )
        current_excerpt = current_text[:48]
        summary = {
            "provider": provider,
            "transport": result.adapter_meta.get("transport"),
            "output_ok": True,
            "review_excerpt": review_text.splitlines()[0],
            "live_progress_provider": live.get("provider"),
            "live_progress_current": (current_text or None),
            "log_tail": output.tails["codex"].tail(6),
            "dashboard_contains_live_progress": "─ Live Progress" in dashboard_joined,
            "dashboard_contains_current": bool(current_excerpt and current_excerpt in dashboard_joined),
        }
        if provider == "codex":
            ensure(summary["transport"] == f"cli-{provider}", f"{provider}: unexpected transport {summary['transport']!r}")
            ensure(summary["live_progress_provider"] == provider, f"{provider}: live progress missing provider tag")
            ensure(summary["dashboard_contains_live_progress"], f"{provider}: dashboard did not render Live Progress")
            ensure(summary["dashboard_contains_current"], f"{provider}: dashboard did not render current provider output")
        else:
            ensure(summary["transport"] == "http-responses", f"{provider}: unexpected transport {summary['transport']!r}")
        return summary
    finally:
        cure_output.clear_active_output(output)
        output.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test provider execution through CURe's real dispatch path.")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["codex", "openai", "openrouter"],
        help="Providers to smoke test.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human-readable output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_text = _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES")

    with tempfile.TemporaryDirectory(prefix="cure-provider-smoke-") as tmp:
        tmp_root = Path(tmp)
        fake_bin = tmp_root / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        write_fake_codex(fake_bin, review_text)
        base_env = build_env(tmp_root=tmp_root, fake_bin=fake_bin)

        server = LocalResponsesServer()
        server.start()
        try:
            results = [
                run_provider_smoke(
                    provider=provider,
                    tmp_root=tmp_root,
                    fake_bin=fake_bin,
                    base_env=base_env,
                    responses_base_url=server.base_url,
                )
                for provider in args.providers
            ]
        finally:
            server.stop()

    if args.json:
        print(json.dumps({"results": results}, indent=2, sort_keys=True))
    else:
        for result in results:
            print(f"{result['provider']}: transport={result['transport']} live={result['live_progress_provider']}")
            print(f"  now={result['live_progress_current']}")
            print(f"  review={result['review_excerpt']}")
            print(
                "  dashboard="
                f"live_progress={result['dashboard_contains_live_progress']}"
                f" current={result['dashboard_contains_current']}"
            )
            if result["log_tail"]:
                print(f"  log_tail={result['log_tail'][-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
