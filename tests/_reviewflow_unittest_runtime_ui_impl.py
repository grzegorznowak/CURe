# ruff: noqa: F403, F405
from _reviewflow_unittest_shared import *  # noqa: F401, F403


class CodexCommandTests(unittest.TestCase):
    def test_build_codex_exec_cmd_includes_bypass_flag(self) -> None:
        repo = ROOT
        cmd = rf.build_codex_exec_cmd(
            repo_dir=repo,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
        )
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertIn("shell_environment_policy.inherit=all", cmd)

    def test_build_codex_exec_cmd_does_not_duplicate_approval_flag(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=ROOT,
            codex_flags=["--sandbox", "workspace-write", "-a", "never"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
            approval_policy="never",
            dangerously_bypass_approvals_and_sandbox=False,
        )
        self.assertEqual(cmd.count("-a"), 1)

    def test_build_codex_exec_cmd_can_enable_json_events(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=ROOT,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
            json_output=True,
        )
        self.assertIn("--json", cmd)
        self.assertLess(cmd.index("--json"), cmd.index("--output-last-message"))

    def test_codex_mcp_overrides_only_disable_global_chunkhound_server(self) -> None:
        repo = ROOT
        ch_cfg = ROOT / ".tmp_test_chunkhound_env.json"
        overrides = rf.codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=True,
            sandbox_repo_dir=repo,
            chunkhound_config_path=ch_cfg,
            paths=rf.DEFAULT_PATHS,
        )
        self.assertTrue(
            any(o.startswith("mcp_servers.chunk-hound.command=") for o in overrides)
        )
        self.assertTrue(
            any(o == "mcp_servers.chunk-hound.enabled=false" for o in overrides)
        )
        self.assertFalse(any(o.startswith("mcp_servers.chunkhound.") for o in overrides))
        cmd = rf.build_codex_exec_cmd(
            repo_dir=repo,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=overrides,
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
        )
        joined = " ".join(cmd)
        self.assertIn("mcp_servers.chunk-hound.enabled=false", joined)
        self.assertIn(str(repo), joined)
        self.assertNotIn("--no-daemon", joined)


class ChunkHoundAccessPreflightTests(unittest.TestCase):
    def test_generated_chunkhound_helper_reports_dynamic_daemon_metadata_on_timeout_failure(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_dynamic_metadata"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()
            runtime_dir = (root / "runtime-state").resolve()
            derived_lock = (repo_dir / "derived-state" / "daemon.lock").resolve()
            derived_log = derived_lock.with_name("daemon.log")
            derived_registry = (runtime_dir / "registry" / "repo.json").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "from pathlib import Path",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        f"    runtime_dir = Path({json.dumps(str(runtime_dir))})",
                        f"    derived_lock = Path({json.dumps(str(derived_lock))})",
                        f"    derived_log = Path({json.dumps(str(derived_log))})",
                        f"    derived_registry = Path({json.dumps(str(derived_registry))})",
                        "    payload = {",
                        f"        'daemon_lock_path': {json.dumps(str(derived_lock))},",
                        f"        'daemon_log_path': {json.dumps(str(derived_log))},",
                        "        'daemon_socket_path': '/tmp/chunkhound-timeout.sock',",
                        "        'daemon_pid': 777,",
                        f"        'daemon_runtime_dir': {json.dumps(str(runtime_dir))},",
                        f"        'daemon_registry_entry_path': {json.dumps(str(derived_registry))},",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    sys.stderr.write('ChunkHound daemon did not start within 30.0s while waiting for IPC readiness\\n')",
                        "    raise SystemExit(1)",
                        "raise SystemExit(2)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("did not start within 30.0s", payload["error"])
            self.assertEqual(payload["preflight_stage"], "initialize")
            self.assertEqual(payload["preflight_stage_status"], "error")
            self.assertEqual(payload["chunkhound_path"], str(fake_chunkhound))
            self.assertEqual(payload["chunkhound_runtime_python"], str(fake_runtime))
            self.assertEqual(payload["daemon_lock_path"], str(derived_lock))
            self.assertEqual(payload["daemon_log_path"], str(derived_log))
            self.assertEqual(payload["daemon_socket_path"], "/tmp/chunkhound-timeout.sock")
            self.assertEqual(payload["daemon_pid"], 777)
            self.assertEqual(payload["daemon_runtime_dir"], str(runtime_dir))
            self.assertEqual(payload["daemon_registry_entry_path"], str(derived_registry))
            trace = payload.get("stage_trace")
            self.assertIsInstance(trace, list)
            self.assertEqual(trace[-1]["stage"], "initialize")
            self.assertEqual(trace[-1]["status"], "error")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_times_out_during_initialize(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_initialize_timeout"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-init/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-init/daemon.log',",
                        "        'daemon_socket_path': '',",
                        "        'daemon_pid': None,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-init',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-init/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    time.sleep(60)",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = helper_path.read_text(encoding="utf-8").replace('"initialize": 10.0', '"initialize": 0.2')
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["preflight_stage"], "initialize")
            self.assertEqual(payload["preflight_stage_status"], "timeout")
            self.assertIn("timed out after 0.2s", payload["error"])
            trace = payload.get("stage_trace")
            self.assertIsInstance(trace, list)
            self.assertEqual(trace[-1]["stage"], "initialize")
            self.assertEqual(trace[-1]["status"], "timeout")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_search_supports_newline_delimited_proxy_transport(
        self,
    ) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_json_line_search"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    raw = sys.stdin.buffer.readline()",
                        "    if not raw:",
                        "        raise SystemExit(0)",
                        "    return json.loads(raw.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    sys.stdout.write(json.dumps(payload) + '\\n')",
                        "    sys.stdout.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-json-line/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-json-line/daemon.log',",
                        "        'daemon_socket_path': '/tmp/chunkhound-json-line.sock',",
                        "        'daemon_pid': 321,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-json-line',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-json-line/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {'tools': {}}}})",
                        "    _ = read_message()",
                        "    tools_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': tools_msg.get('id'), 'result': {'tools': [{'name': 'search'}, {'name': 'code_research'}]}})",
                        "    call_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': call_msg.get('id'), 'result': {'content': [{'type': 'text', 'text': '{\"results\": [{\"file_path\": \"demo.py\", \"content\": \"needle\"}]}'}]}})",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "search", "needle"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["tool_name"], "search")
            self.assertEqual(payload["mcp_transport"], "json_line")
            self.assertEqual(payload["result"]["results"][0]["file_path"], "demo.py")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_uses_tool_specific_tools_call_timeouts(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_call_timeouts"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    raw = sys.stdin.buffer.readline()",
                        "    if not raw:",
                        "        raise SystemExit(0)",
                        "    return json.loads(raw.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    sys.stdout.write(json.dumps(payload) + '\\n')",
                        "    sys.stdout.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-tool-call/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-tool-call/daemon.log',",
                        "        'daemon_socket_path': '/tmp/chunkhound-tool-call.sock',",
                        "        'daemon_pid': 321,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-tool-call',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-tool-call/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {'tools': {}}}})",
                        "    _ = read_message()",
                        "    tools_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': tools_msg.get('id'), 'result': {'tools': [{'name': 'search'}, {'name': 'code_research'}]}})",
                        "    call_msg = read_message()",
                        "    tool_name = call_msg.get('params', {}).get('name')",
                        "    if tool_name == 'search':",
                        "        time.sleep(0.1)",
                        "        write_message({'jsonrpc': '2.0', 'id': call_msg.get('id'), 'result': {'content': [{'type': 'text', 'text': '{\"results\": [{\"file_path\": \"demo.py\", \"content\": \"needle\"}], \"pagination\": {\"offset\": 0, \"total_results\": 1}}'}]}})",
                        "        raise SystemExit(0)",
                        "    time.sleep(0.35)",
                        "    write_message({'jsonrpc': '2.0', 'id': call_msg.get('id'), 'result': {'content': [{'type': 'text', 'text': 'slow research'}]}})",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = (
                helper_path.read_text(encoding="utf-8")
                .replace('"search": 15.0', '"search": 0.4')
                .replace('"code_research": 1200.0', '"code_research": 0.2')
            )
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            search_result = subprocess.run(
                [str(helper_path), "search", "needle"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            research_result = subprocess.run(
                [str(helper_path), "research", "cross-file question"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(search_result.returncode, 0)
            search_payload = json.loads(search_result.stdout)
            self.assertTrue(search_payload["ok"])
            self.assertEqual(search_payload["execution_stage"], "tools/call")
            self.assertEqual(search_payload["execution_stage_status"], "ok")
            self.assertEqual(search_payload["execution_timeout_seconds"], 0.4)
            self.assertEqual(search_payload["stage_trace"][-1]["stage"], "tools/call")
            self.assertEqual(search_payload["stage_trace"][-1]["status"], "ok")

            self.assertEqual(research_result.returncode, 1)
            research_payload = json.loads(research_result.stdout)
            self.assertFalse(research_payload["ok"])
            self.assertEqual(research_payload["tool_name"], "code_research")
            self.assertEqual(research_payload["execution_stage"], "tools/call")
            self.assertEqual(research_payload["execution_stage_status"], "timeout")
            self.assertEqual(research_payload["execution_timeout_seconds"], 0.2)
            self.assertIn("timed out after 0.2s waiting for stage tools/call", research_payload["error"])
            self.assertEqual(research_payload["stage_trace"][-1]["stage"], "tools/call")
            self.assertEqual(research_payload["stage_trace"][-1]["status"], "timeout")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_falls_back_to_framed_transport(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_transport_fallback"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    headers = {}",
                        "    while True:",
                        "        line = sys.stdin.buffer.readline()",
                        "        if line in (b'\\r\\n', b'\\n', b''):",
                        "            break",
                        "        key, _, value = line.decode('utf-8', errors='replace').partition(':')",
                        "        headers[key.strip().lower()] = value.strip()",
                        "    length = int(headers.get('content-length', '0'))",
                        "    body = sys.stdin.buffer.read(length)",
                        "    return json.loads(body.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    raw = json.dumps(payload).encode('utf-8')",
                        "    sys.stdout.buffer.write(f'Content-Length: {len(raw)}\\r\\n\\r\\n'.encode('utf-8') + raw)",
                        "    sys.stdout.buffer.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-fallback/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-fallback/daemon.log',",
                        "        'daemon_socket_path': '/tmp/chunkhound-fallback.sock',",
                        "        'daemon_pid': 654,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-fallback',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-fallback/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {'tools': {}}}})",
                        "    _ = read_message()",
                        "    tools_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': tools_msg.get('id'), 'result': {'tools': [{'name': 'search'}, {'name': 'code_research'}]}})",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = helper_path.read_text(encoding="utf-8").replace('"initialize": 10.0', '"initialize": 0.2')
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mcp_transport"], "mcp_framed")
            self.assertEqual(payload["preflight_stage"], "complete")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_times_out_during_tools_list(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tools_list_timeout"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    headers = {}",
                        "    while True:",
                        "        line = sys.stdin.buffer.readline()",
                        "        if line in (b'\\r\\n', b'\\n', b''):",
                        "            break",
                        "        key, _, value = line.decode('utf-8', errors='replace').partition(':')",
                        "        headers[key.strip().lower()] = value.strip()",
                        "    length = int(headers.get('content-length', '0'))",
                        "    body = sys.stdin.buffer.read(length)",
                        "    return json.loads(body.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    raw = json.dumps(payload).encode('utf-8')",
                        "    sys.stdout.buffer.write(f'Content-Length: {len(raw)}\\r\\n\\r\\n'.encode('utf-8') + raw)",
                        "    sys.stdout.buffer.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-tools/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-tools/daemon.log',",
                        "        'daemon_socket_path': '',",
                        "        'daemon_pid': None,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-tools',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-tools/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {}}})",
                        "    _ = read_message()",
                        "    _ = read_message()",
                        "    time.sleep(60)",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = helper_path.read_text(encoding="utf-8")
            helper_text = helper_text.replace('_TRANSPORT_MODES = ("json_line", "mcp_framed")', '_TRANSPORT_MODES = ("mcp_framed",)')
            helper_text = helper_text.replace('"tools/list": 10.0', '"tools/list": 0.2')
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["preflight_stage"], "tools/list")
            self.assertEqual(payload["preflight_stage_status"], "timeout")
            self.assertIn("timed out after 0.2s", payload["error"])
            trace = payload.get("stage_trace")
            self.assertIsInstance(trace, list)
            self.assertEqual(trace[-1]["stage"], "tools/list")
            self.assertEqual(trace[-1]["status"], "timeout")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_tools_list_timeout_ignores_repeated_nonmatching_messages(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tools_list_nonmatching_timeout"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    headers = {}",
                        "    while True:",
                        "        line = sys.stdin.buffer.readline()",
                        "        if line in (b'\\r\\n', b'\\n', b''):",
                        "            break",
                        "        key, _, value = line.decode('utf-8', errors='replace').partition(':')",
                        "        headers[key.strip().lower()] = value.strip()",
                        "    length = int(headers.get('content-length', '0'))",
                        "    body = sys.stdin.buffer.read(length)",
                        "    return json.loads(body.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    raw = json.dumps(payload).encode('utf-8')",
                        "    sys.stdout.buffer.write(f'Content-Length: {len(raw)}\\r\\n\\r\\n'.encode('utf-8') + raw)",
                        "    sys.stdout.buffer.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-tools-nonmatching/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-tools-nonmatching/daemon.log',",
                        "        'daemon_socket_path': '',",
                        "        'daemon_pid': None,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-tools-nonmatching',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-tools-nonmatching/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {}}})",
                        "    _ = read_message()",
                        "    tools_msg = read_message()",
                        "    for idx in range(8):",
                        "        write_message({'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'seq': idx, 'requested_id': tools_msg.get('id')}})",
                        "        time.sleep(0.05)",
                        "    time.sleep(60)",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = helper_path.read_text(encoding="utf-8")
            helper_text = helper_text.replace('_TRANSPORT_MODES = ("json_line", "mcp_framed")', '_TRANSPORT_MODES = ("mcp_framed",)')
            helper_text = helper_text.replace('"tools/list": 10.0', '"tools/list": 0.2')
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["preflight_stage"], "tools/list")
            self.assertEqual(payload["preflight_stage_status"], "timeout")
            self.assertIn("timed out after 0.2s", payload["error"])
            trace = payload.get("stage_trace")
            self.assertIsInstance(trace, list)
            self.assertEqual(trace[-1]["stage"], "tools/list")
            self.assertEqual(trace[-1]["status"], "timeout")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_generated_chunkhound_helper_drains_noisy_stderr_without_deadlock(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_noisy_stderr"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            work_dir = root / "work"
            helper_cwd = root / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            helper_cwd.mkdir(parents=True, exist_ok=True)

            fake_runtime = (root / "fake-python").resolve()
            fake_chunkhound_dir = root / "fake-bin"
            fake_chunkhound_dir.mkdir(parents=True, exist_ok=True)
            fake_chunkhound = (fake_chunkhound_dir / "chunkhound").resolve()

            fake_runtime.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "import sys",
                        "from pathlib import Path",
                        "",
                        "def read_message():",
                        "    headers = {}",
                        "    while True:",
                        "        line = sys.stdin.buffer.readline()",
                        "        if line in (b'\\r\\n', b'\\n', b''):",
                        "            break",
                        "        key, _, value = line.decode('utf-8', errors='replace').partition(':')",
                        "        headers[key.strip().lower()] = value.strip()",
                        "    length = int(headers.get('content-length', '0'))",
                        "    body = sys.stdin.buffer.read(length)",
                        "    return json.loads(body.decode('utf-8'))",
                        "",
                        "def write_message(payload):",
                        "    raw = json.dumps(payload).encode('utf-8')",
                        "    sys.stdout.buffer.write(f'Content-Length: {len(raw)}\\r\\n\\r\\n'.encode('utf-8') + raw)",
                        "    sys.stdout.buffer.flush()",
                        "",
                        "if len(sys.argv) > 1 and sys.argv[1] == '-c':",
                        "    payload = {",
                        "        'daemon_lock_path': '/tmp/chunkhound-noisy/daemon.lock',",
                        "        'daemon_log_path': '/tmp/chunkhound-noisy/daemon.log',",
                        "        'daemon_socket_path': '/tmp/chunkhound-noisy.sock',",
                        "        'daemon_pid': 888,",
                        "        'daemon_runtime_dir': '/tmp/chunkhound-noisy',",
                        "        'daemon_registry_entry_path': '/tmp/chunkhound-noisy/registry/repo.json',",
                        f"        'chunkhound_runtime_python': {json.dumps(str(fake_runtime))},",
                        f"        'chunkhound_module_path': {json.dumps('/opt/chunkhound/site-packages/chunkhound/__init__.py')},",
                        "    }",
                        "    print(json.dumps(payload, sort_keys=True))",
                        "    raise SystemExit(0)",
                        "",
                        "script_name = Path(sys.argv[1]).name if len(sys.argv) > 1 else ''",
                        "if script_name == 'chunkhound' and len(sys.argv) > 2 and sys.argv[2] == 'mcp':",
                        "    sys.stderr.write('NOISY-' * 20000)",
                        "    sys.stderr.flush()",
                        "    init_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': init_msg.get('id'), 'result': {'serverInfo': {'name': 'fake', 'version': '1'}, 'capabilities': {}}})",
                        "    _ = read_message()",
                        "    tools_msg = read_message()",
                        "    write_message({'jsonrpc': '2.0', 'id': tools_msg.get('id'), 'result': {'tools': [{'name': 'search'}, {'name': 'code_research'}]}})",
                        "    raise SystemExit(0)",
                        "raise SystemExit(2)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_runtime.chmod(0o755)
            fake_chunkhound.write_text(f"#!{fake_runtime}\n", encoding="utf-8")
            fake_chunkhound.chmod(0o755)

            helper_path = cure_llm.write_chunkhound_helper(
                work_dir=work_dir,
                repo_dir=repo_dir,
                chunkhound_config_path=helper_cwd / "chunkhound.json",
                chunkhound_db_path=helper_cwd / ".chunkhound.db",
                chunkhound_cwd=helper_cwd,
            )
            helper_text = helper_path.read_text(encoding="utf-8").replace(
                '_TRANSPORT_MODES = ("json_line", "mcp_framed")',
                '_TRANSPORT_MODES = ("mcp_framed",)',
            )
            helper_path.write_text(helper_text, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = f"{fake_chunkhound_dir}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(helper_path), "preflight"],
                cwd=repo_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["preflight_stage"], "complete")
            self.assertIn("search", payload["available_tools"])
            self.assertIn("code_research", payload["available_tools"])
            self.assertIn("NOISY-", payload["stderr_tail"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunkhound_access_preflight_records_success_metadata(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_access_preflight_success"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            helper_path = root / "work" / "bin" / "cure-chunkhound"
            helper_path.parent.mkdir(parents=True, exist_ok=True)
            helper_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "payload = {",
                        '    "ok": True,',
                        '    "command": "preflight",',
                        '    "available_tools": ["search", "code_research"],',
                        f'    "helper_path": {json.dumps(str(helper_path))},',
                        f'    "daemon_lock_path": {json.dumps(str((repo_dir / ".chunkhound" / "daemon.lock").resolve()))},',
                        f'    "daemon_socket_path": {json.dumps("/tmp/chunkhound-test.sock")},',
                        f'    "daemon_log_path": {json.dumps(str((repo_dir / ".chunkhound" / "daemon.log").resolve()))},',
                        '    "daemon_pid": 4242,',
                        "}",
                        'print(json.dumps(payload, sort_keys=True))',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            helper_path.chmod(0o755)
            runtime_policy = {
                "metadata": {"provider": "codex", "chunkhound_access_mode": "cli_helper_daemon"},
                "staged_paths": {"chunkhound_helper": str(helper_path)},
            }
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            env = {"CURE_CHUNKHOUND_HELPER": str(helper_path)}

            access = rf._run_chunkhound_access_preflight(
                repo_dir=repo_dir,
                env=env,
                runtime_policy=runtime_policy,
                stream=False,
                meta=meta,
            )

            assert access is not None
            self.assertEqual(access["mode"], "cli_helper_daemon")
            self.assertEqual(access["helper_env_var"], "CURE_CHUNKHOUND_HELPER")
            self.assertEqual(access["helper_path"], str(helper_path))
            self.assertEqual(access["daemon_socket_path"], "/tmp/chunkhound-test.sock")
            self.assertEqual(access["daemon_pid"], 4242)
            self.assertTrue(meta["chunkhound"]["access"]["preflight_ok"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunkhound_access_preflight_rejects_malformed_json_and_persists_error(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_access_preflight_bad_json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            helper_path = root / "work" / "bin" / "cure-chunkhound"
            helper_path.parent.mkdir(parents=True, exist_ok=True)
            helper_path.write_text("#!/usr/bin/env sh\nprintf 'not-json\\n'\n", encoding="utf-8")
            helper_path.chmod(0o755)
            runtime_policy = {
                "metadata": {"provider": "codex", "chunkhound_access_mode": "cli_helper_daemon"},
                "staged_paths": {"chunkhound_helper": str(helper_path)},
            }
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            env = {"CURE_CHUNKHOUND_HELPER": str(helper_path)}

            with self.assertRaisesRegex(rf.ReviewflowError, "malformed JSON"):
                rf._run_chunkhound_access_preflight(
                    repo_dir=repo_dir,
                    env=env,
                    runtime_policy=runtime_policy,
                    stream=False,
                    meta=meta,
                )

            self.assertEqual(meta["chunkhound"]["access"]["helper_path"], str(helper_path))
            self.assertIn("malformed JSON", meta["chunkhound"]["access"]["error"])
            self.assertFalse(meta["chunkhound"]["access"]["preflight_ok"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunkhound_access_preflight_persists_timeout_diagnostics(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_access_preflight_timeout"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            helper_path = root / "work" / "bin" / "cure-chunkhound"
            helper_path.parent.mkdir(parents=True, exist_ok=True)
            helper_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import json",
                        "payload = {",
                        '    "ok": False,',
                        '    "command": "preflight",',
                        '    "error": "ChunkHound daemon did not start within 30.0s while waiting for IPC readiness",',
                        f'    "helper_path": {json.dumps(str(helper_path))},',
                        f'    "chunkhound_path": {json.dumps("/usr/bin/chunkhound")},',
                        f'    "chunkhound_runtime_python": {json.dumps("/usr/bin/python3")},',
                        f'    "chunkhound_module_path": {json.dumps("/opt/chunkhound/site-packages/chunkhound/__init__.py")},',
                        f'    "daemon_lock_path": {json.dumps("/tmp/chunkhound-runtime/daemon.lock")},',
                        f'    "daemon_socket_path": {json.dumps("/tmp/chunkhound-runtime.sock")},',
                        f'    "daemon_log_path": {json.dumps("/tmp/chunkhound-runtime/daemon.log")},',
                        '    "daemon_pid": 5150,',
                        f'    "daemon_runtime_dir": {json.dumps("/tmp/chunkhound-runtime")},',
                        f'    "daemon_registry_entry_path": {json.dumps("/tmp/chunkhound-runtime/registry/repo.json")},',
                        '    "preflight_stage": "initialize",',
                        '    "preflight_stage_status": "timeout",',
                        '    "stage_trace": [{"stage": "spawn", "status": "ok", "elapsed_seconds": 0.01}, {"stage": "initialize", "status": "timeout", "elapsed_seconds": 0.25}],',
                        '    "elapsed_seconds": 0.25,',
                        '    "stderr_tail": "daemon stalled during initialize",',
                        "}",
                        'print(json.dumps(payload, sort_keys=True))',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            helper_path.chmod(0o755)
            runtime_policy = {
                "metadata": {"provider": "codex", "chunkhound_access_mode": "cli_helper_daemon"},
                "staged_paths": {"chunkhound_helper": str(helper_path)},
            }
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            env = {"CURE_CHUNKHOUND_HELPER": str(helper_path), "PYTHONSAFEPATH": "1"}

            with self.assertRaisesRegex(rf.ReviewflowError, "did not start within 30.0s"):
                rf._run_chunkhound_access_preflight(
                    repo_dir=repo_dir,
                    env=env,
                    runtime_policy=runtime_policy,
                    stream=False,
                    meta=meta,
                )

            access = meta["chunkhound"]["access"]
            self.assertEqual(access["chunkhound_path"], "/usr/bin/chunkhound")
            self.assertEqual(access["chunkhound_runtime_python"], "/usr/bin/python3")
            self.assertEqual(access["daemon_lock_path"], "/tmp/chunkhound-runtime/daemon.lock")
            self.assertEqual(access["daemon_log_path"], "/tmp/chunkhound-runtime/daemon.log")
            self.assertEqual(access["daemon_runtime_dir"], "/tmp/chunkhound-runtime")
            self.assertEqual(access["daemon_registry_entry_path"], "/tmp/chunkhound-runtime/registry/repo.json")
            self.assertEqual(access["preflight_stage"], "initialize")
            self.assertEqual(access["preflight_stage_status"], "timeout")
            self.assertEqual(access["stage_trace"][-1]["stage"], "initialize")
            self.assertEqual(access["stderr_tail"], "daemon stalled during initialize")
            self.assertFalse(access["preflight_ok"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_chunkhound_access_preflight_outer_timeout_uses_last_reported_stage(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_access_preflight_outer_timeout"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            helper_path = root / "work" / "bin" / "cure-chunkhound"
            helper_path.parent.mkdir(parents=True, exist_ok=True)
            helper_path.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import sys",
                        "import time",
                        "sys.stderr.write('preflight stage=spawn status=ok\\n')",
                        "sys.stderr.write('preflight stage=initialize status=ok\\n')",
                        "sys.stderr.write('preflight stage=tools/list status=running\\n')",
                        "sys.stderr.flush()",
                        "time.sleep(5)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            helper_path.chmod(0o755)
            runtime_policy = {
                "metadata": {"provider": "codex", "chunkhound_access_mode": "cli_helper_daemon"},
                "staged_paths": {"chunkhound_helper": str(helper_path)},
            }
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            env = {"CURE_CHUNKHOUND_HELPER": str(helper_path)}

            with mock.patch.object(rf, "_CHUNKHOUND_HELPER_PREFLIGHT_TIMEOUT_SECONDS", 0.2):
                with self.assertRaisesRegex(rf.ReviewflowError, "timed out after 0.2s while waiting for stage tools/list"):
                    rf._run_chunkhound_access_preflight(
                        repo_dir=repo_dir,
                        env=env,
                        runtime_policy=runtime_policy,
                        stream=False,
                        meta=meta,
                    )

            access = meta["chunkhound"]["access"]
            self.assertEqual(access["preflight_stage"], "tools/list")
            self.assertEqual(access["preflight_stage_status"], "timeout")
            self.assertEqual(access["stage_trace"][-1]["stage"], "tools/list")
            self.assertEqual(access["stage_trace"][-1]["status"], "running")
            self.assertAlmostEqual(access["outer_timeout_seconds"], 0.2)
            self.assertIn("tools/list", access["helper_stderr_tail"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class CodexJsonProgressTests(unittest.TestCase):
    def test_codex_review_artifact_heuristic_prefers_real_review_markdown(self) -> None:
        review_text = "\n".join(
            [
                "### Steps taken",
                "- inspected diff",
                "",
                "**Summary**: Found two regressions.",
                "",
                "## Business / Product Assessment",
                "**Verdict**: REQUEST CHANGES",
                "",
                "## Technical Assessment",
                "**Verdict**: REQUEST CHANGES",
            ]
        )
        self.assertTrue(cure_llm._looks_like_codex_review_artifact(review_text))
        self.assertFalse(
            cure_llm._looks_like_codex_review_artifact(
                "Subagent shutdown notifications received; the review findings and verdicts above are unchanged."
            )
        )

    def test_codex_json_event_sink_preserves_raw_events_and_emits_readable_progress(self) -> None:
        raw = StringIO()
        display = StringIO()
        tail = rui.TailBuffer(max_lines=10)
        events: list[dict[str, object]] = []
        long_message = "Checking changed files " + ("and narrowing scope " * 20)
        sink = cure_output.CodexJsonEventSink(
            raw_file=raw,
            display_file=display,
            tail=tail,
            on_event=events.append,
        )

        sink.write('{"type":"thread.started","thread_id":"abc"}\n')
        sink.write(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_1", "type": "agent_message", "text": long_message},
                }
            )
            + "\n"
        )
        sink.flush()

        self.assertIn('"type":"thread.started"', raw.getvalue())
        self.assertIn("Codex session started.", display.getvalue())
        self.assertIn("Checking changed files", display.getvalue())
        self.assertEqual(events[-1]["type"], "agent_message")
        self.assertEqual(events[-1]["raw_text"], long_message)
        self.assertEqual(events[-1]["text"], cure_output._compact_codex_text(long_message))
        self.assertEqual(tail.tail(2)[-1], cure_output._compact_codex_text(long_message))

    def test_watch_line_for_payload_appends_live_progress_summary(self) -> None:
        payload = {
            "session_id": "session-123",
            "status": "running",
            "phase": "codex_review",
            "pr": {"owner": "acme", "repo": "repo", "number": 12},
            "llm": {"summary": "llm=default/gpt-5/?"},
            "live_progress": {
                "current": {"type": "agent_message", "text": "Checking changed files and narrowing scope"},
            },
        }
        line = cure_commands._watch_line_for_payload(payload)
        self.assertIn("current=Checking changed files and narrowing scope", line)

    def test_watch_line_for_payload_appends_chunkhound_preflight_summary(self) -> None:
        payload = {
            "session_id": "session-456",
            "status": "running",
            "phase": "chunkhound_access_preflight",
            "pr": {"owner": "acme", "repo": "repo", "number": 12},
            "chunkhound": {
                "access": {
                    "preflight_stage": "tools/list",
                    "preflight_stage_status": "timeout",
                    "elapsed_seconds": 12.4,
                    "error": "helper preflight timed out after 12.4s while waiting for stage tools/list",
                    "preflight_ok": False,
                }
            },
        }
        line = cure_commands._watch_line_for_payload(payload)
        self.assertIn("chunkhound=tools/list timeout 12.4s", line)

    def test_run_codex_exec_json_mode_keeps_review_artifact_when_final_message_is_status_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp) / "review.md"
            review_text = "\n".join(
                [
                    "### Steps taken",
                    "- inspected diff",
                    "",
                    "**Summary**: Found two regressions.",
                    "",
                    "## Business / Product Assessment",
                    "**Verdict**: REQUEST CHANGES",
                    "",
                    "## Technical Assessment",
                    "**Verdict**: REQUEST CHANGES",
                ]
            )

            class _DummyProgress:
                def __init__(self, root: Path) -> None:
                    self.meta = {
                        "logs": {"codex_events": str(root / "codex.events.jsonl")},
                        "live_progress": {},
                    }

                def record_cmd(self, cmd: list[str]) -> None:
                    self.last_cmd = list(cmd)

                def flush(self) -> None:
                    return None

            progress = _DummyProgress(Path(tmp))
            out = mock.Mock()
            out.ui_enabled = True

            def fake_run_logged_cmd(*args: object, **kwargs: object) -> None:
                callback = kwargs["codex_event_callback"]
                assert callback is not None
                callback({"type": "agent_message", "text": review_text, "ts": "2026-03-17T07:35:02+00:00"})
                callback(
                    {
                        "type": "agent_message",
                        "text": "Subagent shutdown notifications received; the review findings and verdicts above are unchanged.",
                        "ts": "2026-03-17T07:35:18+00:00",
                    }
                )
                output_path.write_text(
                    "Subagent shutdown notifications received; the review findings and verdicts above are unchanged.\n",
                    encoding="utf-8",
                )

            out.run_logged_cmd.side_effect = fake_run_logged_cmd

            with mock.patch.object(cure_llm, "active_output", return_value=out), mock.patch.object(
                cure_llm, "find_codex_resume_info", return_value=None
            ):
                rf.run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=["-m", "gpt-5.2"],
                    codex_config_overrides=[],
                    output_path=output_path,
                    prompt="hello",
                    env={},
                    stream=True,
                    progress=progress,
                )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("**Summary**: Found two regressions.", rendered)
            self.assertNotIn("Subagent shutdown notifications received", rendered)

    def test_run_codex_exec_json_mode_uses_raw_review_text_for_artifact_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp) / "review.md"
            review_text = "\n".join(
                [
                    "### Steps taken",
                    "- inspected diff",
                    "",
                    "**Summary**: Found two regressions and one follow-up risk.",
                    "",
                    "## Business / Product Assessment",
                    "**Verdict**: APPROVE",
                    "",
                    "### Strengths",
                    "- " + " ".join(["Business strength"] * 20),
                    "",
                    "## Technical Assessment",
                    "**Verdict**: REQUEST CHANGES",
                    "",
                    "### In Scope Issues",
                    "- " + " ".join(["Technical issue"] * 20),
                ]
            )
            compact_preview = cure_output._compact_codex_text(review_text)

            class _DummyProgress:
                def __init__(self, root: Path) -> None:
                    self.meta = {
                        "logs": {"codex_events": str(root / "codex.events.jsonl")},
                        "live_progress": {},
                    }

                def record_cmd(self, cmd: list[str]) -> None:
                    self.last_cmd = list(cmd)

                def flush(self) -> None:
                    return None

            progress = _DummyProgress(Path(tmp))
            out = mock.Mock()
            out.ui_enabled = True

            def fake_run_logged_cmd(*args: object, **kwargs: object) -> None:
                callback = kwargs["codex_event_callback"]
                assert callback is not None
                callback(
                    {
                        "type": "agent_message",
                        "text": compact_preview,
                        "raw_text": review_text,
                        "ts": "2026-03-17T08:08:41+00:00",
                    }
                )
                output_path.write_text(review_text + "\n", encoding="utf-8")

            out.run_logged_cmd.side_effect = fake_run_logged_cmd

            with mock.patch.object(cure_llm, "active_output", return_value=out), mock.patch.object(
                cure_llm, "find_codex_resume_info", return_value=None
            ):
                rf.run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=["-m", "gpt-5.2"],
                    codex_config_overrides=[],
                    output_path=output_path,
                    prompt="hello",
                    env={},
                    stream=True,
                    progress=progress,
                )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertEqual(rendered, review_text + "\n")
            self.assertNotEqual(rendered, compact_preview + "\n")
            verdicts = rf.extract_review_verdicts_from_markdown(rendered)
            assert verdicts is not None
            self.assertEqual(verdicts.business, "APPROVE")
            self.assertEqual(verdicts.technical, "REQUEST CHANGES")

    def test_run_logged_cmd_persists_codex_events_even_when_ui_off_and_no_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            meta_path.write_text("{}", encoding="utf-8")
            logs_dir = root / "logs"
            events_path = logs_dir / "codex.events.jsonl"
            output = cure_output.ReviewflowOutput(
                ui_enabled=False,
                no_stream=True,
                stderr=StringIO(),
                meta_path=meta_path,
                logs_dir=logs_dir,
                verbosity=rui.Verbosity.normal,
            )
            try:
                def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                    self.assertTrue(bool(kwargs["stream"]))
                    self.assertIsNone(kwargs["stream_label"])
                    sink = kwargs["stream_to"]
                    assert sink is not None
                    sink.write('{"type":"thread.started","thread_id":"abc"}\n')
                    sink.flush()
                    return mock.Mock(
                        stdout="",
                        stderr="",
                        exit_code=0,
                        duration_seconds=0.0,
                        cmd=cmd,
                        cwd=kwargs.get("cwd"),
                    )

                with mock.patch.object(cure_output, "run_cmd", side_effect=fake_run_cmd):
                    output.run_logged_cmd(
                        ["codex", "exec", "--json", "hello"],
                        kind="codex",
                        cwd=root,
                        env={},
                        check=True,
                        stream_requested=False,
                        codex_json_events_path=events_path,
                    )
            finally:
                output.stop()

            self.assertTrue(events_path.is_file())
            self.assertIn('"type":"thread.started"', events_path.read_text(encoding="utf-8"))

    def test_build_status_payload_includes_live_progress_and_codex_events_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-123"
            repo_dir = session_dir / "repo"
            logs_dir = session_dir / "work" / "logs"
            review_md = session_dir / "review.md"
            repo_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            review_md.write_text("# Review\n", encoding="utf-8")
            for name in ("cure.log", "chunkhound.log", "codex.log", "codex.events.jsonl"):
                (logs_dir / name).write_text(name + "\n", encoding="utf-8")
            meta = {
                "session_id": "session-123",
                "status": "running",
                "phase": "codex_review",
                "phases": {"codex_review": {"status": "running"}},
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 12,
                "created_at": "2026-03-17T12:00:00+00:00",
                "paths": {
                    "repo_dir": str(repo_dir),
                    "work_dir": str(session_dir / "work"),
                    "logs_dir": str(logs_dir),
                    "review_md": str(review_md),
                },
                "logs": {
                    "cure": str(logs_dir / "cure.log"),
                    "chunkhound": str(logs_dir / "chunkhound.log"),
                    "codex": str(logs_dir / "codex.log"),
                    "codex_events": str(logs_dir / "codex.events.jsonl"),
                },
                "live_progress": {
                    "source": "codex_exec_json",
                    "provider": "codex",
                    "current": {"type": "agent_message", "text": "Checking changed files"},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            payload = rf.build_status_payload("session-123", sandbox_root=root)

        self.assertIn("live_progress", payload)
        self.assertIn("codex_events", payload["logs"])

    def test_build_status_payload_includes_chunkhound_access_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-456"
            repo_dir = session_dir / "repo"
            logs_dir = session_dir / "work" / "logs"
            review_md = session_dir / "review.md"
            repo_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            review_md.write_text("# Review\n", encoding="utf-8")
            for name in ("cure.log", "chunkhound.log", "codex.log"):
                (logs_dir / name).write_text(name + "\n", encoding="utf-8")
            meta = {
                "session_id": "session-456",
                "status": "error",
                "phase": "chunkhound_access_preflight",
                "phases": {"chunkhound_access_preflight": {"status": "error"}},
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 12,
                "created_at": "2026-03-17T12:00:00+00:00",
                "paths": {
                    "repo_dir": str(repo_dir),
                    "work_dir": str(session_dir / "work"),
                    "logs_dir": str(logs_dir),
                    "review_md": str(review_md),
                },
                "logs": {
                    "cure": str(logs_dir / "cure.log"),
                    "chunkhound": str(logs_dir / "chunkhound.log"),
                    "codex": str(logs_dir / "codex.log"),
                },
                "chunkhound": {
                    "access": {
                        "preflight_stage": "initialize",
                        "preflight_stage_status": "timeout",
                        "preflight_ok": False,
                    }
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            payload = rf.build_status_payload("session-456", sandbox_root=root)

        self.assertIn("chunkhound", payload)
        self.assertIn("access", payload["chunkhound"])
        self.assertEqual(payload["chunkhound"]["access"]["preflight_stage"], "initialize")

    def test_build_status_payload_includes_chunkhound_last_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-idx"
            repo_dir = session_dir / "repo"
            logs_dir = session_dir / "work" / "logs"
            review_md = session_dir / "review.md"
            repo_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            review_md.write_text("# Review\n", encoding="utf-8")
            for name in ("cure.log", "chunkhound.log", "codex.log"):
                (logs_dir / name).write_text(name + "\n", encoding="utf-8")
            meta = {
                "session_id": "session-idx",
                "status": "running",
                "phase": "index_topup",
                "phases": {"index_topup": {"status": "running"}},
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 12,
                "created_at": "2026-03-17T12:00:00+00:00",
                "paths": {
                    "repo_dir": str(repo_dir),
                    "work_dir": str(session_dir / "work"),
                    "logs_dir": str(logs_dir),
                    "review_md": str(review_md),
                },
                "logs": {
                    "cure": str(logs_dir / "cure.log"),
                    "chunkhound": str(logs_dir / "chunkhound.log"),
                    "codex": str(logs_dir / "codex.log"),
                },
                "chunkhound": {
                    "last_index": {
                        "scope": "topup",
                        "processed_files": 4,
                        "skipped_files": 1,
                        "error_files": 0,
                        "total_chunks": 84,
                        "embeddings": 84,
                        "duration_text": "17.23s",
                    }
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            payload = rf.build_status_payload("session-idx", sandbox_root=root)

        self.assertIn("chunkhound", payload)
        self.assertEqual(payload["chunkhound"]["last_index"]["embeddings"], 84)


class GitStatsTests(unittest.TestCase):
    def test_compute_pr_stats_on_tiny_repo(self) -> None:
        repo = ROOT / ".tmp_test_git_repo"
        try:
            repo.mkdir(parents=True, exist_ok=True)
            rf.run_cmd(["git", "-C", str(repo), "init"], check=True)
            rf.run_cmd(["git", "-C", str(repo), "config", "user.email", "test@example.com"])
            rf.run_cmd(["git", "-C", str(repo), "config", "user.name", "Test User"])

            (repo / "a.txt").write_text("one\n", encoding="utf-8")
            rf.run_cmd(["git", "-C", str(repo), "add", "a.txt"])
            rf.run_cmd(["git", "-C", str(repo), "commit", "-m", "base"])
            base_sha = rf.run_cmd(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()

            (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
            (repo / "b.txt").write_text("b\n", encoding="utf-8")
            rf.run_cmd(["git", "-C", str(repo), "add", "a.txt", "b.txt"])
            rf.run_cmd(["git", "-C", str(repo), "commit", "-m", "change"])

            stats = rf.compute_pr_stats(repo_dir=repo, base_ref=base_sha, head_ref="HEAD")
            self.assertEqual(stats["changed_files"], 2)
            self.assertGreater(stats["additions"], 0)
            self.assertGreaterEqual(stats["deletions"], 0)
            self.assertGreater(stats["changed_lines"], 0)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class TuiDashboardTests(unittest.TestCase):
    def test_parse_chunkhound_index_summary_extracts_full_run_metrics(self) -> None:
        summary = chunkhound_summary.parse_chunkhound_index_summary(
            "\n".join(
                [
                    "Initial stats: 0 files, 0 chunks, 0 embeddings",
                    "Processing Complete",
                    "Processed: 1 files",
                    "Skipped: 0 files",
                    "Errors: 0 files",
                    "Total chunks: 1",
                    "Embeddings: 0",
                    "Time: 0.07s",
                ]
            ),
            scope="topup",
        )
        assert summary is not None
        self.assertEqual(summary["scope"], "topup")
        self.assertEqual(summary["initial_files"], 0)
        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["total_chunks"], 1)
        self.assertEqual(summary["embeddings"], 0)
        self.assertEqual(summary["duration_text"], "0.07s")

    def test_parser_accepts_if_reviewed_and_followup_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/1",
                "--if-reviewed",
                "latest",
            ]
        )
        self.assertEqual(args.if_reviewed, "latest")

        args2 = p.parse_args(["followup", "session-123", "--no-update"])
        self.assertEqual(args2.session_id, "session-123")
        self.assertTrue(args2.no_update)

        args3 = p.parse_args(["interactive", "https://github.com/acme/repo/pull/1"])
        self.assertEqual(args3.target, "https://github.com/acme/repo/pull/1")

        args4 = p.parse_args(["clean"])
        self.assertIsNone(args4.session_id)

        args5 = p.parse_args(["clean", "session-123"])
        self.assertEqual(args5.session_id, "session-123")

        args6 = p.parse_args(["commands", "--json"])
        self.assertTrue(args6.json_output)

        args7 = p.parse_args(["status", "session-123", "--json"])
        self.assertEqual(args7.target, "session-123")
        self.assertTrue(args7.json_output)

        args8 = p.parse_args(
            [
                "watch",
                "https://github.com/acme/repo/pull/1",
                "--interval",
                "5",
                "--verbosity",
                "quiet",
                "--no-color",
            ]
        )
        self.assertEqual(args8.target, "https://github.com/acme/repo/pull/1")
        self.assertEqual(args8.interval, 5.0)
        self.assertEqual(args8.verbosity, "quiet")
        self.assertTrue(args8.no_color)

        args9 = p.parse_args(["clean", "closed", "--yes", "--json"])
        self.assertEqual(args9.session_id, "closed")
        self.assertTrue(args9.yes)
        self.assertTrue(args9.json_output)

    def test_parser_help_marks_pr_no_index_as_advanced_and_hides_resume_no_index(self) -> None:
        parser = rf.build_parser()
        subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        pr_help = subparsers.choices["pr"].format_help()
        resume_help = subparsers.choices["resume"].format_help()

        self.assertIn("--no-index", pr_help)
        self.assertIn("Advanced opt-out for custom prompt flows", pr_help)
        self.assertRegex(pr_help, r"not\s+recommended")
        self.assertNotIn("--no-index", resume_help)

        resume_args = parser.parse_args(["resume", "session-123", "--no-index"])
        self.assertTrue(resume_args.no_index)

    def test_parser_accepts_runtime_overrides_before_and_after_subcommand(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(["--config", "/tmp/reviewflow.toml", "doctor"])
        self.assertEqual(args.config_path, "/tmp/reviewflow.toml")

        args2 = p.parse_args(
            [
                "doctor",
                "--config",
                "/tmp/reviewflow.toml",
                "--agent-runtime-profile",
                "strict",
                "--sandbox-root",
                "/tmp/sandboxes",
                "--cache-root",
                "/tmp/cache",
                "--codex-config",
                "/tmp/codex.toml",
            ]
        )
        self.assertEqual(args2.config_path, "/tmp/reviewflow.toml")
        self.assertFalse(args2.no_config)
        self.assertEqual(args2.agent_runtime_profile, "strict")
        self.assertEqual(args2.sandbox_root, "/tmp/sandboxes")
        self.assertEqual(args2.cache_root, "/tmp/cache")
        self.assertEqual(args2.codex_config_path, "/tmp/codex.toml")
        args3 = p.parse_args(["doctor", "--no-config", "--json"])
        self.assertTrue(args3.no_config)
        self.assertTrue(args3.json_output)
        args4 = p.parse_args(["doctor", "--pr-url", "https://github.com/acme/repo/pull/1", "--json"])
        self.assertEqual(args4.pr_url, "https://github.com/acme/repo/pull/1")
        self.assertTrue(args4.json_output)
        args5 = p.parse_args(["init", "--config", "/tmp/cure.toml", "--sandbox-root", "/tmp/sandboxes", "--force"])
        self.assertEqual(args5.config_path, "/tmp/cure.toml")
        self.assertEqual(args5.sandbox_root, "/tmp/sandboxes")
        self.assertTrue(args5.force)

    def test_parser_accepts_install_command(self) -> None:
        p = rf.build_parser()
        self.assertEqual(p.prog, "cure")
        args = p.parse_args(["install", "--chunkhound-source", "git-main"])
        self.assertEqual(args.chunkhound_source, "git-main")

    def test_console_main_dispatches_without_alias_warning(self) -> None:
        stderr = StringIO()
        with mock.patch.object(rf.sys, "argv", ["reviewflow", "commands"]), mock.patch.object(
            rf, "main", return_value=9
        ) as main_mock, contextlib.redirect_stderr(stderr):
            rc = rf.console_main()

        self.assertEqual(rc, 9)
        self.assertEqual(stderr.getvalue(), "")
        main_mock.assert_called_once_with(["commands"], prog="cure")

    def test_parser_accepts_zip_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "zip",
                "https://github.com/acme/repo/pull/9",
                "--llm-preset",
                "openrouter_grok",
                "--llm-model",
                "x-ai/grok-4.1-fast",
                "--llm-effort",
                "high",
                "--llm-plan-effort",
                "xhigh",
                "--llm-verbosity",
                "low",
                "--llm-max-output-tokens",
                "9000",
                "--llm-set",
                "top_p=0.9",
                "--llm-header",
                "HTTP-Referer=https://example.com",
                "--codex-model",
                "gpt-5.3-codex-spark",
                "--codex-effort",
                "low",
                "--ui",
                "off",
                "--verbosity",
                "debug",
            ]
        )
        self.assertEqual(args.pr_url, "https://github.com/acme/repo/pull/9")
        self.assertEqual(args.llm_preset, "openrouter_grok")
        self.assertEqual(args.llm_model, "x-ai/grok-4.1-fast")
        self.assertEqual(args.llm_effort, "high")
        self.assertEqual(args.llm_plan_effort, "xhigh")
        self.assertEqual(args.llm_verbosity, "low")
        self.assertEqual(args.llm_max_output_tokens, 9000)
        self.assertEqual(args.llm_set, ["top_p=0.9"])
        self.assertEqual(args.llm_header, ["HTTP-Referer=https://example.com"])
        self.assertEqual(args.codex_model, "gpt-5.3-codex-spark")
        self.assertEqual(args.codex_effort, "low")
        self.assertEqual(args.ui, "off")
        self.assertEqual(args.verbosity, "debug")

    def test_parser_accepts_ui_and_verbosity_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/1",
                "--ui",
                "off",
                "--verbosity",
                "debug",
            ]
        )
        self.assertEqual(args.ui, "off")
        self.assertEqual(args.verbosity, "debug")

        args2 = p.parse_args(["resume", "session-123", "--ui", "auto", "--verbosity", "normal"])
        self.assertEqual(args2.ui, "auto")
        self.assertEqual(args2.verbosity, "normal")

        args3 = p.parse_args(
            [
                "ui-preview",
                "session-123",
                "--watch",
                "--width",
                "100",
                "--height",
                "30",
                "--verbosity",
                "debug",
                "--no-color",
            ]
        )
        self.assertEqual(args3.session_id, "session-123")
        self.assertTrue(args3.watch)
        self.assertEqual(args3.width, 100)
        self.assertEqual(args3.height, 30)
        self.assertEqual(args3.verbosity, "debug")
        self.assertTrue(args3.no_color)


class RuntimeResolutionTests(unittest.TestCase):
    def _runtime_args(self, **overrides: object) -> argparse.Namespace:
        payload = {
            "config_path": None,
            "no_config": False,
            "agent_runtime_profile": None,
            "sandbox_root": None,
            "cache_root": None,
            "codex_config_path": None,
        }
        payload.update(overrides)
        return argparse.Namespace(**payload)

    def test_resolve_reviewflow_config_path_prefers_cli_then_env(self) -> None:
        args = self._runtime_args(config_path="/tmp/cli.toml")
        with mock.patch.dict(
            os.environ,
            {"CURE_CONFIG": "/tmp/cure-env.toml"},
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/cli.toml"), "cli", True),
            )
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {"CURE_CONFIG": "/tmp/cure-env.toml"},
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/cure-env.toml"), "env", True),
            )

    def test_resolve_reviewflow_config_path_uses_xdg_default(self) -> None:
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
            },
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/xdg-config/cure/cure.toml"), "default", True),
            )

    def test_resolve_reviewflow_config_path_marks_selected_file_disabled(self) -> None:
        args = self._runtime_args(config_path="/tmp/cli.toml", no_config=True)
        self.assertEqual(
            rf.resolve_reviewflow_config_path(args),
            (Path("/tmp/cli.toml"), "cli", False),
        )

    def test_resolve_reviewflow_config_path_rejects_legacy_env(self) -> None:
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {"REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml"},
            clear=False,
        ):
            with self.assertRaisesRegex(rf.ReviewflowError, "REVIEWFLOW_CONFIG is no longer supported. Use CURE_CONFIG instead."):
                rf.resolve_reviewflow_config_path(args)

    def test_resolve_reviewflow_config_path_ignores_legacy_default_if_present(self) -> None:
        root = ROOT / ".tmp_test_legacy_config_default"
        cure_cfg = root / "cure" / "cure.toml"
        legacy_cfg = root / "reviewflow" / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            legacy_cfg.parent.mkdir(parents=True, exist_ok=True)
            legacy_cfg.write_text("", encoding="utf-8")
            args = self._runtime_args()
            with mock.patch.object(rf, "default_reviewflow_config_path", return_value=cure_cfg):
                self.assertEqual(
                    rf.resolve_reviewflow_config_path(args),
                    (cure_cfg, "default", True),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_uses_xdg_defaults_when_unset(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "CURE_SANDBOX_ROOT": "",
                "CURE_CACHE_ROOT": "",
                "CURE_CODEX_CONFIG": "",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
                "XDG_STATE_HOME": "/tmp/xdg-state",
                "XDG_CACHE_HOME": "/tmp/xdg-cache",
            },
            clear=False,
        ):
            runtime = rf.resolve_runtime(args)
        self.assertEqual(runtime.config_path, Path("/tmp/xdg-config/cure/cure.toml"))
        self.assertEqual(runtime.config_source, "default")
        self.assertTrue(runtime.config_enabled)
        self.assertEqual(runtime.paths.sandbox_root, Path("/tmp/xdg-state/cure/sandboxes"))
        self.assertEqual(runtime.sandbox_root_source, "default")
        self.assertEqual(runtime.paths.cache_root, Path("/tmp/xdg-cache/cure"))
        self.assertEqual(runtime.cache_root_source, "default")
        self.assertEqual(runtime.codex_base_config_path, Path("/home/tester/.codex/config.toml"))
        self.assertEqual(runtime.codex_base_config_source, "default")

    def test_resolve_runtime_rejects_legacy_envs(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "/tmp/cure-env.toml",
                "CURE_SANDBOX_ROOT": "/tmp/cure-sandboxes",
                "CURE_CACHE_ROOT": "/tmp/cure-cache",
                "CURE_CODEX_CONFIG": "/tmp/cure-codex.toml",
                "REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml",
                "REVIEWFLOW_SANDBOX_ROOT": "/tmp/legacy-sandboxes",
                "REVIEWFLOW_CACHE_ROOT": "/tmp/legacy-cache",
                "REVIEWFLOW_CODEX_CONFIG": "/tmp/legacy-codex.toml",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(rf.ReviewflowError, "REVIEWFLOW_CONFIG is no longer supported. Use CURE_CONFIG instead."):
                rf.resolve_runtime(args)

    def test_resolve_runtime_rejects_legacy_work_dir_env(self) -> None:
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {"REVIEWFLOW_WORK_DIR": "/tmp/legacy-work"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                rf.ReviewflowError,
                "REVIEWFLOW_WORK_DIR is no longer supported. Use CURE_WORK_DIR instead.",
            ):
                rf.resolve_runtime(args)


class CanonicalShellOwnershipTests(RuntimeResolutionTests):
    def test_cure_is_the_canonical_shell_surface(self) -> None:
        self.assertIs(cure.init_flow, cure_commands.init_flow)
        self.assertIs(cure.render_prompt, cure_flows.render_prompt)
        self.assertIs(cure.run_llm_exec, cure_llm.run_llm_exec)
        self.assertIs(cure.commands_flow, cure_commands.commands_flow)
        self.assertIs(cure.status_flow, cure_commands.status_flow)
        self.assertIs(cure.watch_flow, cure_commands.watch_flow)

    def test_reviewflow_reexports_active_extracted_owners(self) -> None:
        self.assertIs(rf.resolve_runtime, cure_runtime.resolve_runtime)
        self.assertIs(rf.init_flow, cure_commands.init_flow)
        self.assertIs(rf.render_prompt, cure_flows.render_prompt)
        self.assertIs(rf.run_llm_exec, cure_llm.run_llm_exec)
        self.assertIs(rf.commands_flow, cure_commands.commands_flow)
        self.assertIs(rf.status_flow, cure_commands.status_flow)
        self.assertIs(rf.watch_flow, cure_commands.watch_flow)

    def test_cure_main_uses_canonical_build_parser(self) -> None:
        args = argparse.Namespace(cmd="commands", json_output=True)
        parser = mock.Mock()
        parser.parse_args.return_value = args
        runtime = self._runtime()
        with mock.patch.object(cure, "build_parser", return_value=parser) as build_parser, mock.patch.object(
            cure_runtime, "resolve_runtime", return_value=runtime
        ) as resolve_runtime, mock.patch.object(
            cure_commands, "commands_flow", return_value=13
        ) as commands_flow:
            rc = cure.main(["commands", "--json"])

        self.assertEqual(rc, 13)
        build_parser.assert_called_once_with(prog="cure")
        resolve_runtime.assert_called_once_with(args)
        commands_flow.assert_called_once_with(args)

    def test_reviewflow_main_forwards_to_cure_main(self) -> None:
        with mock.patch.object(cure, "main", return_value=19) as cure_main:
            rc = rf.main(["commands", "--json"])

        self.assertEqual(rc, 19)
        cure_main.assert_called_once()
        self.assertEqual(cure_main.call_args.args[0], ["commands", "--json"])
        self.assertEqual(cure_main.call_args.kwargs, {})

    def test_pyproject_points_public_package_to_cure_console_main(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["project"]["name"], "cureview")
        self.assertEqual(pyproject["project"]["scripts"]["cure"], "cure:console_main")
        self.assertNotIn("reviewflow", pyproject["project"]["scripts"])
        self.assertIn("cure", pyproject["tool"]["setuptools"]["py-modules"])

    def _runtime(self) -> rf.ReviewflowRuntime:
        return rf.ReviewflowRuntime(
            config_path=Path("/tmp/reviewflow.toml"),
            config_source="cli",
            config_enabled=True,
            paths=rf.ReviewflowPaths(
                sandbox_root=Path("/tmp/sandboxes"),
                cache_root=Path("/tmp/cache"),
            ),
            sandbox_root_source="cli",
            cache_root_source="cli",
            codex_base_config_path=Path("/tmp/codex.toml"),
            codex_base_config_source="cli",
        )

    def test_main_dispatches_pr_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "pr_flow", return_value=17
        ) as pr_flow:
            rc = rf.main(["pr", "https://github.com/acme/repo/pull/1"])

        self.assertEqual(rc, 17)
        resolve_runtime.assert_called_once()
        pr_flow.assert_called_once()

    def test_main_dispatches_status_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "status_flow", return_value=3
        ) as status_flow:
            rc = rf.main(["status", "session-123"])

        self.assertEqual(rc, 3)
        resolve_runtime.assert_called_once()
        status_flow.assert_called_once()

    def test_main_dispatches_doctor_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "doctor_flow", return_value=5
        ) as doctor_flow:
            rc = rf.main(["doctor"])

        self.assertEqual(rc, 5)
        resolve_runtime.assert_called_once()
        doctor_flow.assert_called_once_with(mock.ANY, runtime=runtime)

    def test_main_dispatches_init_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "init_flow", return_value=7
        ) as init_flow:
            rc = rf.main(["init", "--force"])

        self.assertEqual(rc, 7)
        resolve_runtime.assert_called_once()
        self.assertEqual(init_flow.call_count, 1)
        self.assertTrue(init_flow.call_args.args[0].force)
        self.assertIs(init_flow.call_args.kwargs["runtime"], runtime)

    def test_console_main_dispatches_for_reviewflow_argv_without_warning_in_owner_tests(self) -> None:
        stderr = StringIO()
        with mock.patch.object(sys, "argv", ["reviewflow", "commands", "--json"]), contextlib.redirect_stderr(
            stderr
        ), mock.patch.object(rf, "main", return_value=9) as main_mock:
            rc = rf.console_main()

        self.assertEqual(rc, 9)
        self.assertEqual(stderr.getvalue(), "")
        main_mock.assert_called_once_with(["commands", "--json"], prog="cure")

    def test_resolve_runtime_ignores_relative_xdg_roots(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "CURE_SANDBOX_ROOT": "",
                "CURE_CACHE_ROOT": "",
                "CURE_CODEX_CONFIG": "",
                "XDG_CONFIG_HOME": "relative-config",
                "XDG_STATE_HOME": "relative-state",
                "XDG_CACHE_HOME": "relative-cache",
            },
            clear=False,
        ), mock.patch.object(rf, "default_reviewflow_config_path", return_value=Path("/home/tester/.config/cure/cure.toml")), mock.patch.object(
            rf,
            "default_sandbox_root",
            return_value=Path("/home/tester/.local/state/cure/sandboxes"),
        ), mock.patch.object(
            rf,
            "default_cache_root",
            return_value=Path("/home/tester/.cache/cure"),
        ):
            runtime = rf.resolve_runtime(args)
        self.assertEqual(runtime.config_path, Path("/home/tester/.config/cure/cure.toml"))
        self.assertEqual(runtime.paths.sandbox_root, Path("/home/tester/.local/state/cure/sandboxes"))
        self.assertEqual(runtime.paths.cache_root, Path("/home/tester/.cache/cure"))

    def test_resolve_runtime_prefers_cli_over_env_and_config(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_cli"
        cfg = root / "reviewflow.toml"
        codex_cfg = root / "codex.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            codex_cfg.write_text("", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                        "[codex]",
                        'base_config_path = "codex.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(
                config_path=str(cfg),
                sandbox_root=str(root / "cli-sandboxes"),
                cache_root=str(root / "cli-cache"),
                codex_config_path=str(root / "cli-codex.toml"),
            )
            runtime = rf.resolve_runtime(args)
            self.assertEqual(runtime.config_path, cfg)
            self.assertEqual(runtime.config_source, "cli")
            self.assertEqual(runtime.paths.sandbox_root, (root / "cli-sandboxes").resolve())
            self.assertEqual(runtime.sandbox_root_source, "cli")
            self.assertEqual(runtime.paths.cache_root, (root / "cli-cache").resolve())
            self.assertEqual(runtime.cache_root_source, "cli")
            self.assertEqual(runtime.codex_base_config_path, (root / "cli-codex.toml").resolve())
            self.assertEqual(runtime.codex_base_config_source, "cli")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_prefers_env_over_config_for_paths(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_env"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(config_path=str(cfg))
            with mock.patch.dict(
                os.environ,
                {
                    "CURE_SANDBOX_ROOT": str(root / "env-sandboxes"),
                    "CURE_CACHE_ROOT": str(root / "env-cache"),
                },
                clear=False,
            ):
                runtime = rf.resolve_runtime(args)
            self.assertEqual(runtime.paths.sandbox_root, (root / "env-sandboxes").resolve())
            self.assertEqual(runtime.sandbox_root_source, "env")
            self.assertEqual(runtime.paths.cache_root, (root / "env-cache").resolve())
            self.assertEqual(runtime.cache_root_source, "env")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_no_config_ignores_reviewflow_toml(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_no_config"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                        "[codex]",
                        'base_config_path = "cfg-codex.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(config_path=str(cfg), no_config=True)
            with mock.patch.object(rf, "default_sandbox_root", return_value=root / "default-sandboxes"), mock.patch.object(
                rf,
                "default_cache_root",
                return_value=root / "default-cache",
            ), mock.patch.object(
                rf,
                "default_codex_base_config_path",
                return_value=root / "default-codex.toml",
            ):
                runtime = rf.resolve_runtime(args)
            self.assertFalse(runtime.config_enabled)
            self.assertEqual(runtime.config_path, cfg)
            self.assertEqual(runtime.paths.sandbox_root, (root / "default-sandboxes").resolve())
            self.assertEqual(runtime.paths.cache_root, (root / "default-cache").resolve())
            self.assertEqual(runtime.codex_base_config_path, (root / "default-codex.toml").resolve())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class InstallAndDoctorTests(unittest.TestCase):
    def _runtime_args(self, **overrides: object) -> argparse.Namespace:
        payload = {
            "config_path": None,
            "no_config": False,
            "agent_runtime_profile": None,
            "sandbox_root": None,
            "cache_root": None,
            "codex_config_path": None,
        }
        payload.update(overrides)
        return argparse.Namespace(**payload)

    def test_build_chunkhound_install_command_uses_expected_specs(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=False), mock.patch.object(
            rf.importlib.util, "find_spec", return_value=object()
        ):
            self.assertEqual(
                rf.build_chunkhound_install_command(chunkhound_source="release"),
                [sys.executable, "-m", "pip", "install", "--upgrade", "chunkhound"],
            )
            self.assertEqual(
                rf.build_chunkhound_install_command(chunkhound_source="git-main"),
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "git+https://github.com/chunkhound/chunkhound@main",
                ],
            )

    def test_build_chunkhound_install_command_uses_uv_tool_when_running_inside_uv_tool(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=True), mock.patch.object(
            shutil, "which", return_value="/usr/bin/uv"
        ):
            cmd = rf.build_chunkhound_install_command(chunkhound_source="git-main")
        self.assertEqual(
            cmd,
            [
                "/usr/bin/uv",
                "tool",
                "install",
                "--force",
                "git+https://github.com/chunkhound/chunkhound@main",
            ],
        )

    def test_running_in_uv_tool_environment_detects_uv_tool_python_without_resolving_symlink(self) -> None:
        with mock.patch.object(rf, "_uv_tool_dir", return_value=Path("/home/vscode/.local/share/uv/tools")), mock.patch.object(
            rf.sys,
            "executable",
            "/home/vscode/.local/share/uv/tools/reviewflow/bin/python",
        ), mock.patch.object(
            rf.sys,
            "prefix",
            "/home/vscode/.local/share/uv/tools/reviewflow",
        ):
            self.assertTrue(rf._running_in_uv_tool_environment(uv_path="/usr/bin/uv"))

    def test_build_chunkhound_install_command_falls_back_to_uv_pip_when_pip_missing_outside_uv_tool(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=False), mock.patch.object(
            rf.importlib.util, "find_spec", return_value=None
        ), mock.patch.object(shutil, "which", return_value="/usr/bin/uv"):
            cmd = rf.build_chunkhound_install_command(chunkhound_source="git-main")
        self.assertEqual(
            cmd,
            [
                "/usr/bin/uv",
                "pip",
                "install",
                "--python",
                sys.executable,
                "--upgrade",
                "git+https://github.com/chunkhound/chunkhound@main",
            ],
        )

    def test_readme_documents_uv_tool_install_flow(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        jira_reference_url = "https://github.com/grzegorznowak/CURe/blob/main/JIRA.md"
        self.assertIn("use <CURE_REPO_URL> to review <PR_URL>", readme)
        self.assertIn("use https://github.com/grzegorznowak/CURe to review https://github.com/chunkhound/chunkhound/pull/220", readme)
        self.assertIn("start with [SKILL.md](SKILL.md)", readme)
        self.assertIn(jira_reference_url, readme)
        self.assertIn("uv tool install cureview", readme)
        self.assertIn("uvx --from cureview cure init", readme)
        self.assertIn("Secondary Standalone Install", readme)
        self.assertIn("Use the standalone GitHub Release assets only when the package path is unavailable or inconvenient.", readme)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh", readme)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.4", readme)
        self.assertIn("cure init", readme)
        self.assertIn("cure doctor --pr-url <PR_URL> --json", readme)
        self.assertIn("reuses an existing `chunkhound` already on `PATH` by default", readme)
        self.assertIn("`--chunkhound-source release` or `--chunkhound-source git-main`", readme)
        self.assertIn("cure commands --json", readme)
        self.assertIn("cure status <session_id|PR_URL> --json", readme)
        self.assertIn("cure watch <session_id|PR_URL>", readme)
        self.assertIn("cure pr <PR_URL> --if-reviewed new", readme)
        self.assertIn("That sentence is the kickoff contract, not a promise that every sandbox can finish setup unattended.", readme)
        self.assertIn("The operator should not need to provide a local checkout path", readme)
        self.assertIn("It should not do a manual review outside CURe.", readme)
        self.assertIn("XDG_CONFIG_HOME", readme)
        self.assertIn("XDG_STATE_HOME", readme)
        self.assertIn("XDG_CACHE_HOME", readme)
        self.assertIn("~/.config/cure/cure.toml", readme)
        self.assertIn("~/.config/cure/chunkhound-base.json", readme)
        self.assertIn("[[review_intelligence.sources]]", readme)
        self.assertIn('name = "github"', readme)
        self.assertIn('mode = "when-referenced"', readme)
        self.assertNotIn("tool_prompt_fragment", readme)
        self.assertIn("VOYAGE_API_KEY", readme)
        self.assertIn("OPENAI_API_KEY", readme)
        self.assertIn("`available`, `unavailable`, or `unknown`", readme)
        self.assertIn("Only `mode = \"required\"` sources are preflighted", readme)
        self.assertIn("the project checkout stays untouched", readme)
        self.assertIn("./selftest.sh", readme)
        self.assertIn("fresh or partially configured environments", readme)
        self.assertIn('fresh install or existing local setup to "review in progress"', readme)
        self.assertIn("inspect the active local setup before creating a fresh one", readme)
        self.assertIn("repo-root `chunkhound.json` and `.chunkhound.json` as ask-first ChunkHound setup hints", readme)
        self.assertIn("Do not silently adopt it in this public contract.", readme)
        self.assertIn("`repo_local_chunkhound` payload", readme)
        self.assertIn("`repo-local-chunkhound` check", readme)
        self.assertIn("`executor-network` advisory check", readme)
        self.assertIn("Codex and Claude executor paths need internet / network access", readme)
        self.assertIn("Hard Rule", skill)
        self.assertIn("When To Use CURe", skill)
        self.assertIn("Primary Inputs", skill)
        self.assertIn("Bootstrap From A Fresh Or Existing Local Setup", skill)
        self.assertIn("What Success Looks Like", skill)
        self.assertIn("When To Stop And Ask", skill)
        self.assertIn("Canonical Agent Prompt", skill)
        self.assertIn("Use CURe from <CURE_REPO_URL> to review <PR_URL>.", skill)
        self.assertIn("If the operator asked to use CURe, do not perform a manual review outside CURe.", skill)
        self.assertIn("[JIRA.md](JIRA.md)", skill)
        self.assertIn("curl -LsSf https://astral.sh/uv/install.sh | sh", skill)
        self.assertIn("https://docs.astral.sh/uv/getting-started/installation/", skill)
        self.assertIn("uv tool install cureview", skill)
        self.assertIn("uvx --from cureview cure --help", skill)
        self.assertIn("uvx --from cureview cure init", skill)
        self.assertIn("Secondary standalone fallback only when the package path is unavailable:", skill)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh", skill)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.4", skill)
        self.assertIn("The standalone path is a secondary fallback for Linux x86_64, macOS x86_64, and macOS arm64 only.", skill)
        self.assertIn("uv tool install /path/to/cure", skill)
        self.assertIn("uv tool install --editable /path/to/cure", skill)
        self.assertIn("--config /tmp/cure-public/cure.toml", skill)
        self.assertIn("XDG_CONFIG_HOME", skill)
        self.assertIn("cure install", skill)
        self.assertIn("`cure install` provisions ChunkHound only", skill)
        self.assertIn("reuses an existing `chunkhound` already on `PATH` by default", skill)
        self.assertIn("`--chunkhound-source release` or `--chunkhound-source git-main`", skill)
        self.assertIn("Run `cure init` before `cure install` or `cure doctor`.", skill)
        self.assertIn("[[review_intelligence.sources]]", skill)
        self.assertIn('name = "github"', skill)
        self.assertIn('mode = "when-referenced"', skill)
        self.assertNotIn("tool_prompt_fragment", skill)
        self.assertIn("If `VOYAGE_API_KEY` exists, `cure init` writes:", skill)
        self.assertIn("If `VOYAGE_API_KEY` is missing but `OPENAI_API_KEY` exists, `cure init` writes:", skill)
        self.assertIn("`available`, `unavailable`, or `unknown`", skill)
        self.assertIn("Only `required` sources are preflighted", skill)
        self.assertIn("If a required embedding secret is still missing", skill)
        self.assertIn("fresh or partially configured environment with explicit readiness checks", skill)
        self.assertIn("inspect the active local setup before creating fresh config files", skill)
        self.assertIn("repo-root `chunkhound.json` and `.chunkhound.json` as ask-first ChunkHound setup hints", skill)
        self.assertIn("Do not silently adopt it.", skill)
        self.assertIn("`repo_local_chunkhound` payload", skill)
        self.assertIn("`repo-local-chunkhound` check", skill)
        self.assertIn("`executor-network` checks", skill)
        self.assertIn("Codex and Claude executor paths need internet / network access", skill)
        self.assertNotIn("pip install", readme)

    def test_skill_documents_proactive_secret_and_config_remediation(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cure.toml", skill)
        self.assertIn("chunkhound-base.json", skill)
        self.assertIn("Bootstrap everything non-secret before you stop:", skill)
        self.assertIn("run `cure init`", skill)
        self.assertIn("create `~/.config/cure/cure.toml` only when `cure init` is unavailable", skill)
        self.assertIn("create `~/.config/cure/chunkhound-base.json` only when `cure init` is unavailable", skill)
        self.assertIn("auto-wire embeddings if `VOYAGE_API_KEY` or `OPENAI_API_KEY` already exists", skill)
        self.assertIn("prefer a current-shell export for the immediate retry", skill)
        self.assertIn("shell profile or existing local secret manager for persistence", skill)
        self.assertIn("VOYAGE_API_KEY", skill)
        self.assertIn("OPENAI_API_KEY", skill)
        self.assertIn("never ask the operator to paste a secret into chat", skill)
        self.assertIn("If `chunkhound index ...` or `cure doctor --pr-url <PR_URL> --json` fails because neither `VOYAGE_API_KEY` nor `OPENAI_API_KEY` is present", skill)
        self.assertIn("I checked ~/.config/cure/cure.toml", skill)
        self.assertIn("\"provider\": \"voyage\"", skill)
        self.assertIn("\"model\": \"voyage-code-3\"", skill)
        self.assertIn("rerun `cure init --force`", skill)
        self.assertIn("\"provider\": \"openai\"", skill)
        self.assertIn("\"model\": \"text-embedding-3-small\"", skill)
        self.assertIn("cure pr <PR_URL> --if-reviewed new", skill)
        self.assertIn("if repo-root `chunkhound.json` or `.chunkhound.json` exists, summarize it as a setup hint", skill)
        self.assertIn("ask the operator whether it should be reused; do not silently adopt it", skill)
        self.assertIn("Read the `repo_local_chunkhound` payload plus the `repo-local-chunkhound` and `executor-network` checks", skill)
        self.assertIn("the active executor path is Codex or Claude", skill)
        self.assertIn("the required internet / network access for code-under-review context", skill)

    def test_docs_mark_no_index_as_advanced_opt_out(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("That indexed ChunkHound-backed path is the default and recommended public review workflow.", readme)
        self.assertIn("Once the first run is active, continue the same indexed session with `cure resume <session_id|PR_URL>`.", readme)
        self.assertIn("`cure pr --no-index` remains available only as an advanced opt-out", readme)
        self.assertIn("It is not the normal or recommended path.", readme)
        self.assertLess(readme.index("cure doctor --pr-url <PR_URL> --json"), readme.index("cure pr <PR_URL> --if-reviewed new"))
        self.assertLess(readme.index("cure pr <PR_URL> --if-reviewed new"), readme.index("cure resume <session_id|PR_URL>"))

        self.assertIn("That indexed ChunkHound-backed path is the default and recommended review workflow:", skill)
        self.assertIn("`cure pr --no-index` remains available only as an advanced opt-out", skill)
        self.assertIn("It is not the normal or recommended path.", skill)
        self.assertLess(skill.index("cure doctor --pr-url <PR_URL> --json"), skill.index("cure pr <PR_URL> --if-reviewed new"))
        self.assertLess(skill.index("cure pr <PR_URL> --if-reviewed new"), skill.index("cure resume <session_id|PR_URL>"))

    def test_docs_explain_chunkhound_helper_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for text in (readme, skill):
            self.assertIn("staged CURe-managed ChunkHound helper", text)
            self.assertIn("`CURE_CHUNKHOUND_HELPER`", text)
            self.assertIn('`"$CURE_CHUNKHOUND_HELPER" search ...`', text)
            self.assertIn('`"$CURE_CHUNKHOUND_HELPER" research ...`', text)
            self.assertIn("helper `research` satisfies the `code_research` requirement", text)
            self.assertIn("Historical sessions may still report legacy `mcp_tool_call` evidence.", text)
            self.assertIn("`PYTHONSAFEPATH=1`", text)
            self.assertIn("helper preflight times out", text)

    def test_docs_reset_agent_local_setup_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertNotIn("pristine environment", readme)
        self.assertNotIn('"nothing installed"', readme)
        self.assertNotIn("That should be enough to start the CURe system.", readme)
        self.assertNotIn("pristine environment", skill)

        for text in (readme, skill):
            self.assertIn("chunkhound.json", text)
            self.assertIn(".chunkhound.json", text)
            self.assertIn("ask the operator whether it should be reused", text)
            self.assertIn("Codex and Claude executor paths need internet / network access", text)

    def test_jira_docs_extracted_from_readme(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        jira = (ROOT / "JIRA.md").read_text(encoding="utf-8")
        jira_reference_url = "https://github.com/grzegorznowak/CURe/blob/main/JIRA.md"

        self.assertIn("## Jira CLI", readme)
        self.assertIn("Normal public GitHub PR review flows do not require Jira.", readme)
        self.assertIn(jira_reference_url, readme)
        self.assertNotIn("[JIRA.md](JIRA.md)", readme)
        self.assertIn("JIRA_CONFIG_FILE", readme)
        self.assertLess(readme.index("## Core Commands"), readme.index("## Jira CLI"))

        for text in [
            "### Jira Site Details",
            "### Install",
            "### Auth",
            "### Configure `jira-cli`",
            "### Common Queries",
            "### Troubleshooting",
            "read:board-scope.admin:jira-software",
        ]:
            self.assertNotIn(text, readme)

        self.assertIn("[JIRA.md](JIRA.md)", skill)

        for text in [
            "Use this only when the workflow actually needs Jira context.",
            "## Jira Site Details",
            "## Install",
            "## Auth",
            "### Token Scopes",
            "## Configure `jira-cli`",
            "## Common Queries",
            "## Security Notes",
            "## Troubleshooting",
            "machine api.atlassian.com",
            "JIRA_CONFIG_FILE=/absolute/path/to/.config.yml",
            "env -u JIRA_API_TOKEN jira serverinfo",
        ]:
            self.assertIn(text, jira)

    def test_init_flow_writes_public_bootstrap_files(self) -> None:
        root = ROOT / ".tmp_test_cure_init"
        config_path = root / "config" / "cure.toml"
        base_path = root / "config" / "chunkhound-base.json"
        runtime = rf.ReviewflowRuntime(
            config_path=config_path,
            config_source="cli",
            config_enabled=True,
            paths=rf.ReviewflowPaths(
                sandbox_root=root / "state" / "sandboxes",
                cache_root=root / "cache",
            ),
            sandbox_root_source="cli",
            cache_root_source="cli",
            codex_base_config_path=root / ".codex" / "config.toml",
            codex_base_config_source="default",
        )
        stdout = StringIO()
        try:
            shutil.rmtree(root, ignore_errors=True)
            with mock.patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage"}, clear=False), contextlib.redirect_stdout(  # pragma: allowlist secret
                stdout
            ):
                rc = rf.init_flow(argparse.Namespace(force=False), runtime=runtime)

            self.assertEqual(rc, 0)
            self.assertTrue(config_path.is_file())
            self.assertTrue(base_path.is_file())
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn(str(runtime.paths.sandbox_root), config_text)
            self.assertIn(str(runtime.paths.cache_root), config_text)
            self.assertIn(str(base_path), config_text)
            self.assertIn("[review_intelligence]", config_text)
            self.assertIn("[[review_intelligence.sources]]", config_text)
            self.assertNotIn("tool_prompt_fragment", config_text)
            base_payload = json.loads(base_path.read_text(encoding="utf-8"))
            self.assertEqual(base_payload["embedding"]["provider"], "voyage")
            self.assertEqual(base_payload["embedding"]["model"], "voyage-code-3")
            output = stdout.getvalue()
            self.assertIn("Wrote CURe config", output)
            self.assertIn("Wrote ChunkHound base config", output)
            self.assertIn("Next: cure install", output)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_facing_contract_text_has_no_workspace_hardcoding(self) -> None:
        cure_src = (ROOT / "cure.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        selftest = (ROOT / "selftest.sh").read_text(encoding="utf-8")
        for text in (cure_src, readme, selftest):
            self.assertNotIn("reviewflow.py jira-smoke", text)
            self.assertNotIn("reviewflow.py clean", text)
            self.assertNotIn("reviewflow.py list", text)

    def test_install_flow_runs_constructed_command(self) -> None:
        with mock.patch.object(rf, "run_cmd") as run_cmd, mock.patch.object(
            shutil, "which", return_value="/usr/bin/chunkhound"
        ):
            rc = rf.install_flow(argparse.Namespace(chunkhound_source="git-main"))
        self.assertEqual(rc, 0)
        self.assertEqual(
            run_cmd.call_args.args[0],
            rf.build_chunkhound_install_command(chunkhound_source="git-main"),
        )

    def test_install_flow_reuses_existing_chunkhound_on_path_by_default(self) -> None:
        with mock.patch.object(rf, "run_cmd") as run_cmd, mock.patch.object(
            shutil,
            "which",
            side_effect=lambda name: "/usr/bin/uv" if name == "uv" else "/usr/bin/chunkhound",
        ):
            rc = rf.install_flow(argparse.Namespace())
        self.assertEqual(rc, 0)
        run_cmd.assert_not_called()

    def test_install_flow_errors_when_chunkhound_still_missing_from_path(self) -> None:
        calls: list[list[str]] = []

        def fake_run_cmd(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(list(cmd))
            if cmd[:3] == ["/usr/bin/uv", "tool", "dir"]:
                stdout = "/home/vscode/.local/share/uv/tools\n"
            elif cmd[:4] == ["/usr/bin/uv", "tool", "dir", "--bin"]:
                stdout = "/home/vscode/.local/bin\n"
            else:
                stdout = ""
            return mock.Mock(stdout=stdout, stderr="", exit_code=0)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd), mock.patch.object(
            shutil,
            "which",
            side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None,
        ), mock.patch.object(
            rf,
            "_running_in_uv_tool_environment",
            return_value=True,
        ), mock.patch.object(
            rf,
            "_uv_tool_dir",
            side_effect=[
                Path("/home/vscode/.local/share/uv/tools"),
                Path("/home/vscode/.local/bin"),
            ],
        ), mock.patch.object(
            rf.importlib.util,
            "find_spec",
            return_value=None,
        ), mock.patch.object(
            rf.sys,
            "executable",
            "/home/vscode/.local/share/uv/tools/reviewflow/bin/python",
        ):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.install_flow(argparse.Namespace(chunkhound_source="release"))
        self.assertIn("still not available on PATH", str(ctx.exception))
        self.assertIn("uv tool bin dir", str(ctx.exception))
        self.assertIn(["/usr/bin/uv", "tool", "install", "--force", "chunkhound"], calls)

    def test_doctor_runtime_checks_report_healthy_state(self) -> None:
        root = ROOT / ".tmp_test_doctor_ok"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        codex_cfg = root / "codex.toml"
        jira_cfg = root / ".jira.yml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            codex_cfg.write_text("", encoding="utf-8")
            jira_cfg.write_text("endpoint: https://example.atlassian.net\n", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[codex]",
                        f'base_config_path = "{codex_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            with mock.patch.dict(os.environ, {"JIRA_CONFIG_FILE": str(jira_cfg)}, clear=False), mock.patch.object(
                shutil,
                "which",
                side_effect=lambda name: f"/usr/bin/{name}",
            ), mock.patch.object(cure_runtime, "run_cmd", return_value=mock.Mock(stdout="", stderr="", exit_code=0)):
                checks = rf._doctor_runtime_checks(runtime)
            by_name = {item.name: item for item in checks}
            self.assertEqual(by_name["cure-config"].status, "ok")
            self.assertEqual(by_name["chunkhound-config"].status, "ok")
            self.assertEqual(by_name["jira-config"].status, "ok")
            self.assertEqual(by_name["codex-config"].status, "ok")
            self.assertEqual(by_name["gh-auth"].status, "ok")
            self.assertEqual(by_name["chunkhound"].status, "ok")
            self.assertIn("source=cli", by_name["cure-config"].detail)
            self.assertIn("source=config", by_name["chunkhound-config"].detail)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_reports_missing_state(self) -> None:
        runtime = rf.ReviewflowRuntime(
            config_path=ROOT / ".tmp_missing_reviewflow.toml",
            config_source="default",
            config_enabled=True,
            paths=rf.DEFAULT_PATHS,
            sandbox_root_source="default",
            cache_root_source="default",
            codex_base_config_path=ROOT / ".tmp_missing_codex.toml",
            codex_base_config_source="default",
        )
        stdout = StringIO()
        with mock.patch.object(shutil, "which", return_value=None), mock.patch.object(
            rf,
            "_default_jira_config_path",
            return_value=ROOT / ".tmp_missing_jira.yml",
        ), mock.patch("sys.stdout", stdout):
            rc = rf.doctor_flow(argparse.Namespace(), runtime=runtime)
        self.assertEqual(rc, 1)
        text = stdout.getvalue()
        self.assertIn("[fail] cure-config", text)
        self.assertIn("[fail] chunkhound", text)
        self.assertIn("[warn] jira-config", text)
        self.assertIn("[warn] codex-config", text)

    def test_doctor_flow_json_reports_sources(self) -> None:
        root = ROOT / ".tmp_test_doctor_json"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[agent_runtime]",
                        'profile = "strict"',
                        "",
                        "[llm]",
                        'default_preset = "claude_default"',
                        "",
                        "[llm_presets.claude_default]",
                        'preset = "claude-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()
            with mock.patch.object(shutil, "which", return_value=None), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(argparse.Namespace(json_output=True), runtime=runtime)
            self.assertEqual(rc, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["cure_config"]["source"], "cli")
            self.assertTrue(payload["cure_config"]["exists"])
            self.assertEqual(payload["chunkhound_base_config"]["source"], "config")
            self.assertEqual(payload["sandbox_root"]["source"], "config")
            self.assertEqual(payload["agent_runtime"]["profile"], "strict")
            self.assertEqual(payload["agent_runtime"]["provider"], "claude")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_json_reports_review_intelligence_capabilities(self) -> None:
        root = ROOT / ".tmp_test_doctor_review_intelligence_json"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        jira_cfg = root / "jira.yml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            jira_cfg.write_text("jira", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[review_intelligence]",
                        "[[review_intelligence.sources]]",
                        'name = "github"',
                        'mode = "auto"',
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "jira"',
                        'mode = "required"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": f"/usr/bin/{name}",
                    "gh": f"/usr/bin/{name}",
                    "jira": f"/usr/bin/{name}",
                    "codex": f"/usr/bin/{name}",
                    "git": f"/usr/bin/{name}",
                }.get(name)

            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = json.dumps({"title": "Public PR"}).encode("utf-8")

            def fake_runtime_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:4] == ["gh", "auth", "status", "--hostname"]:
                    return mock.Mock(stdout="", stderr="", exit_code=0)
                raise AssertionError(f"unexpected runtime command: {cmd}")

            with mock.patch.dict(os.environ, {"JIRA_CONFIG_FILE": str(jira_cfg)}, clear=False), mock.patch.object(
                shutil,
                "which",
                side_effect=fake_which,
            ), mock.patch.object(
                cure_runtime,
                "run_cmd",
                side_effect=fake_runtime_run_cmd,
            ), mock.patch.object(
                rf.urllib.request,
                "urlopen",
                return_value=response,
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(
                    argparse.Namespace(
                        json_output=True,
                        pr_url="https://github.com/acme/repo/pull/1",
                    ),
                    runtime=runtime,
                )

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            review_intelligence = payload["review_intelligence"]
            capability_sources = {
                source["name"]: source for source in review_intelligence["capabilities"]["sources"]
            }
            self.assertEqual(capability_sources["github"]["status"], "available")
            self.assertEqual(capability_sources["jira"]["status"], "available")
            self.assertEqual(review_intelligence["capabilities"]["required_sources"], ["jira"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_json_includes_repo_local_chunkhound_payload(self) -> None:
        root = ROOT / ".tmp_test_doctor_repo_local_chunkhound"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound-base.json"
        repo_root = root / "repo"
        invocation_cwd = repo_root / "src"
        repo_local_cfg = repo_root / "chunkhound.json"
        repo_local_db = repo_root / ".chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_local_db.mkdir(parents=True, exist_ok=True)
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir(parents=True, exist_ok=True)
            (root / "cache").mkdir(parents=True, exist_ok=True)
            base_cfg.write_text(
                json.dumps(
                    {
                        "indexing": {"include": ["**/*.py"], "exclude": ["**/.git/**"]},
                        "research": {"algorithm": "hybrid"},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (repo_local_db / "chunks.db").write_text("db", encoding="utf-8")
            repo_local_cfg.write_text(
                json.dumps(
                    {
                        "database": {"provider": "duckdb", "path": ".chunkhound"},
                        "indexing": {"include": ["**/*.py"], "exclude": ["**/.git/**"]},
                        "research": {"algorithm": "hybrid"},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": f"/usr/bin/{name}",
                    "gh": f"/usr/bin/{name}",
                    "jira": f"/usr/bin/{name}",
                    "codex": f"/usr/bin/{name}",
                }.get(name)

            def fake_runtime_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:4] == ["gh", "auth", "status", "--hostname"]:
                    return mock.Mock(stdout="", stderr="", exit_code=0)
                raise AssertionError(f"unexpected runtime command: {cmd}")

            def fake_rf_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", exit_code=0)
                raise AssertionError(f"unexpected reviewflow command: {cmd}")

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch.object(cure_runtime, "run_cmd", side_effect=fake_runtime_run_cmd), mock.patch.object(
                rf,
                "run_cmd",
                side_effect=fake_rf_run_cmd,
            ), mock.patch.object(
                cure_runtime.Path,
                "cwd",
                return_value=invocation_cwd,
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(argparse.Namespace(json_output=True), runtime=runtime)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            candidate = payload["repo_local_chunkhound"]
            self.assertEqual(candidate["candidate_state"], "candidate")
            self.assertEqual(candidate["config_path"], str(repo_local_cfg.resolve()))
            self.assertEqual(candidate["repo_root"], str(repo_root.resolve()))
            self.assertEqual(candidate["db_provider"], "duckdb")
            self.assertEqual(candidate["db_path"], str(repo_local_db.resolve()))
            self.assertEqual(candidate["runtime_match_state"], "compatible")
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["repo-local-chunkhound"]["status"], "warn")
            self.assertIn("ask-first repo-local ChunkHound candidate", by_name["repo-local-chunkhound"]["detail"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_adds_executor_network_advisory_for_claude(self) -> None:
        root = ROOT / ".tmp_test_doctor_executor_network_claude"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[llm]",
                        'default_preset = "claude_default"',
                        "",
                        "[llm_presets.claude_default]",
                        'preset = "claude-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": f"/usr/bin/{name}",
                    "gh": f"/usr/bin/{name}",
                    "jira": f"/usr/bin/{name}",
                    "codex": f"/usr/bin/{name}",
                    "claude": f"/usr/bin/{name}",
                }.get(name)

            def fake_runtime_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:4] == ["gh", "auth", "status", "--hostname"]:
                    return mock.Mock(stdout="", stderr="", exit_code=0)
                raise AssertionError(f"unexpected runtime command: {cmd}")

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch.object(cure_runtime, "run_cmd", side_effect=fake_runtime_run_cmd), mock.patch.object(
                rf,
                "run_cmd",
                side_effect=RuntimeError("not a git worktree"),
            ), mock.patch.object(
                cure_runtime.Path,
                "cwd",
                return_value=root,
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(argparse.Namespace(json_output=True), runtime=runtime)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["executor-network"]["status"], "warn")
            self.assertIn("claude executor needs internet / network access", by_name["executor-network"]["detail"])
            self.assertIn("does not prove external sandbox access", by_name["executor-network"]["detail"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_skips_executor_network_advisory_for_gemini(self) -> None:
        root = ROOT / ".tmp_test_doctor_executor_network_gemini"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[agent_runtime]",
                        'profile = "balanced"',
                        "",
                        "[llm]",
                        'default_preset = "gemini_default"',
                        "",
                        "[llm_presets.gemini_default]",
                        'preset = "gemini-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": f"/usr/bin/{name}",
                    "gh": f"/usr/bin/{name}",
                    "jira": f"/usr/bin/{name}",
                    "codex": f"/usr/bin/{name}",
                    "gemini": f"/usr/bin/{name}",
                }.get(name)

            def fake_runtime_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:4] == ["gh", "auth", "status", "--hostname"]:
                    return mock.Mock(stdout="", stderr="", exit_code=0)
                raise AssertionError(f"unexpected runtime command: {cmd}")

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch.object(cure_runtime, "run_cmd", side_effect=fake_runtime_run_cmd), mock.patch.object(
                rf,
                "run_cmd",
                side_effect=RuntimeError("not a git worktree"),
            ), mock.patch.object(
                cure_runtime.Path,
                "cwd",
                return_value=root,
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(argparse.Namespace(json_output=True), runtime=runtime)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            check_names = {item["name"] for item in payload["checks"]}
            self.assertNotIn("executor-network", check_names)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_runtime_checks_warn_when_config_disabled(self) -> None:
        root = ROOT / ".tmp_test_doctor_no_config"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(root / "reviewflow.toml"), no_config=True))
            checks = rf._doctor_runtime_checks(runtime)
            by_name = {item.name: item for item in checks}
            self.assertEqual(by_name["cure-config"].status, "warn")
            self.assertEqual(by_name["chunkhound-config"].status, "warn")
            self.assertIn("disabled by --no-config", by_name["cure-config"].detail)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_public_pr_allows_missing_gh_auth_and_jira(self) -> None:
        root = ROOT / ".tmp_test_doctor_public_pr"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = json.dumps({"title": "Public PR"}).encode("utf-8")

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": "/usr/bin/chunkhound",
                    "codex": "/usr/bin/codex",
                    "git": "/usr/bin/git",
                }.get(name)

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch.object(rf.urllib.request, "urlopen", return_value=response), mock.patch(
                "sys.stdout",
                stdout,
            ):
                rc = rf.doctor_flow(
                    argparse.Namespace(
                        json_output=True,
                        pr_url="https://github.com/acme/repo/pull/1",
                    ),
                    runtime=runtime,
                )

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["gh"]["status"], "ok")
            self.assertEqual(by_name["gh-auth"]["status"], "ok")
            self.assertEqual(by_name["jira-config"]["status"], "warn")
            self.assertEqual(by_name["jira"]["status"], "warn")
            self.assertEqual(by_name["git"]["status"], "ok")
            self.assertEqual(by_name["github-pr-access"]["status"], "ok")
            self.assertEqual(payload["summary"]["fail"], 0)
            self.assertTrue(payload["target"]["public_pr_metadata_reachable"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_private_host_still_requires_authenticated_gh(self) -> None:
        root = ROOT / ".tmp_test_doctor_private_host"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": "/usr/bin/chunkhound",
                    "codex": "/usr/bin/codex",
                    "git": "/usr/bin/git",
                }.get(name)

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(
                    argparse.Namespace(
                        json_output=True,
                        pr_url="https://git.example.com/acme/repo/pull/1",
                    ),
                    runtime=runtime,
                )

            self.assertEqual(rc, 1)
            payload = json.loads(stdout.getvalue())
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["gh"]["status"], "fail")
            self.assertEqual(by_name["gh-auth"]["status"], "fail")
            self.assertEqual(by_name["github-pr-access"]["status"], "fail")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dashboard_renders_multipass_step_x_of_y(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "acme-repo-pr1-20260304-000000-abcd",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "codex_step_03",
            "phases": {"codex_step_03": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
            "multipass": {
                "enabled": True,
                "current": {
                    "stage": "step",
                    "step_index": 3,
                    "step_count": 7,
                    "step_title": "Authentication checks",
                },
            },
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["x"],
            codex_tail=["y"],
            no_stream=False,
            width=120,
            height=40,
        )
        joined = "\n".join(lines)
        self.assertIn("step 3/7", joined)
        self.assertIn("Authentication checks", joined)

    def test_dashboard_hides_tails_in_quiet(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "init",
            "phases": {},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        quiet_lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.quiet, show_help=False),
            chunkhound_tail=["x"],
            codex_tail=["y"],
            no_stream=False,
            width=120,
            height=30,
        )
        self.assertNotIn("chunkhound tail:", "\n".join(quiet_lines))

    def test_dashboard_status_bar_packs_right_side_without_ellipsis(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",  # stable elapsed="?"
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0000000000000000000000000000000000000000",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        for w in (80, 120):
            lines = rui.build_dashboard_lines(
                meta=meta,
                snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
                chunkhound_tail=[],
                codex_tail=[],
                no_stream=False,
                width=w,
                height=25,
            )
            bar = lines[0]
            self.assertIn("RUN", bar)
            self.assertIn("phase 1/1: Checkout PR", bar)
            if w < 100:
                self.assertNotIn("v:normal", bar)
            else:
                self.assertIn("v:normal", bar)

    def test_dashboard_narrow_header_moves_verdicts_to_context(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "done",
            "completed_at": "2026-03-04T00:05:00+00:00",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "done", "duration_seconds": 10.0}},
            "verdicts": {"business": "REQUEST CHANGES", "technical": "REQUEST CHANGES"},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=90,
            height=25,
        )
        self.assertNotIn("biz=REQUEST CHANGES", lines[0])
        self.assertNotIn("v:normal", lines[0])
        self.assertIn("phase 1/1: Generate review", lines[0])
        joined = "\n".join(lines)
        self.assertIn("Verdict: biz=REQUEST CHANGES tech=REQUEST CHANGES", joined)

    def test_dashboard_narrow_layout_uses_single_column_sections(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0000000000000000000000000000000000000000",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=90,
            height=30,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Phases", joined)
        self.assertIn("─ Context", joined)
        self.assertNotIn(" │ ", joined)

    def test_dashboard_error_current_phase_uses_error_marker_and_failure_summary(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "error",
            "phase": "review_intelligence_preflight",
            "phases": {"review_intelligence_preflight": {"status": "error", "duration_seconds": 0.1}},
            "error": {"message": "Jira context is expected but JIRA_CONFIG_FILE is unavailable."},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["jira me failed"],
            codex_tail=[],
            no_stream=False,
            width=120,
            height=30,
        )
        joined = "\n".join(lines)
        self.assertIn("✖ Context preflight", joined)
        self.assertIn("Failure:", joined)
        self.assertIn("JIRA_CONF", joined)
        self.assertIn("Preflight:", joined)
        self.assertIn("Failure Detail", joined)

    def test_dashboard_color_mode_emits_ansi_and_preserves_width_math(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}, "resolve_pr_meta": {"status": "done"}},
            "base_ref": "main",
            "head_sha": "0000000000000000000000000000000000000000",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        width = 80
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=width,
            height=25,
            color=True,
        )
        joined = "\n".join(lines)
        self.assertIn("\x1b[", joined)

        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for line in lines:
            visible = ansi.sub("", line)
            self.assertLessEqual(len(visible), width)

    def test_dashboard_renders_zip_inputs_in_context(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 9,
            "title": "Zip PR",
            "session_id": "zip-run",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "codex_zip",
            "kind": "zip",
            "phases": {"codex_zip": {"status": "running"}},
            "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "zip": {
                "display_inputs": [
                    "- host-session [review] biz=APPROVE tech=REQUEST CHANGES 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb /tmp/host/review.md",
                    "- other-session [followup] biz=REQUEST CHANGES tech=REJECT 2026-03-05T01:00:00+00:00 head bbbbbbbbbbbb /tmp/other/followup.md",
                ],
                "selected_input_count": 2,
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["cx-1"],
            no_stream=False,
            width=160,
            height=35,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Zip:", joined)
        self.assertIn("Inputs:", joined)
        self.assertIn("host-session [review] biz=APPROVE tech=REQUEST CHANGES", joined)
        self.assertIn("other-session [followup] biz=REQUEST CHANGES tech=REJECT", joined)

    def test_dashboard_footer_is_dimmed_in_color_mode(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["ch-1"],
            codex_tail=["cx-1"],
            no_stream=False,
            width=120,
            height=25,
            color=True,
        )
        # Footer/help is styled as ANSI "dim" to keep focus on logs.
        self.assertIn("\x1b[2m", lines[-1])
        # Footer uses a subtle full-width bar framing.
        self.assertIn("┄", lines[-1])

    def test_dashboard_strips_hash_delimiter_from_codex_tail(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["line-1", "####", "line-2"],
            no_stream=False,
            width=120,
            height=25,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("line-1", joined)
        self.assertIn("line-2", joined)
        self.assertNotIn("\n####\n", "\n" + joined + "\n")

    def test_dashboard_expands_logs_when_vertical_space_available(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0000000000000000000000000000000000000000",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        ch_tail = [f"ch-{i}" for i in range(1, 201)]
        cx_tail = [f"cx-{i}" for i in range(1, 401)]
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.debug, show_help=False),
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=False,
            width=160,
            height=80,
            color=False,
        )
        joined = "\n".join(lines)
        m1 = re.search(r"Support \(last (\d+)\):", joined)
        m2 = re.search(r"Codex \(last (\d+)\):", joined)
        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)
        assert m1 is not None
        assert m2 is not None
        self.assertGreater(int(m1.group(1)), 8)
        self.assertGreater(int(m2.group(1)), 12)

    def test_dashboard_small_terminal_still_shows_log_lines(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        ch_tail = [f"ch-{i}" for i in range(1, 201)]
        cx_tail = [f"cx-{i}" for i in range(1, 401)]
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=False,
            width=160,
            height=18,
            color=False,
        )
        joined = "\n".join(lines)
        # Ensure at least one actual tail line makes it on screen at short heights.
        self.assertIn("─ Activity", joined)
        self.assertIn("cx-400", joined)

    def test_dashboard_empty_logs_render_stream_specific_placeholder(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=120,
            height=20,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Activity", joined)
        self.assertIn("(agent is working)", joined)

    def test_dashboard_context_summarizes_support_signals(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[
                "Processed: 4 files",
                "Skipped: 1 files",
                "Errors: 0 files",
                "Total chunks: 84",
                "Embeddings: 84",
                "Time: 17.23s",
                "greg@academypl.us",
            ],
            codex_tail=["mcp: chunkhound ready"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Index", joined)
        self.assertIn("Run: 4 proc · 1 skip · 0 err", joined)
        self.assertIn("Output: 84 chunks · 84 emb · 17.23s", joined)
        self.assertIn("Preflight: Jira OK as greg@academypl.us", joined)
        self.assertIn("─ Activity", joined)
        self.assertIn("mcp: chunkhound ready", joined)

    def test_dashboard_context_prefers_structured_chunkhound_summary(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "chunkhound": {
                "last_index": {
                    "scope": "followup",
                    "initial_files": 120,
                    "initial_chunks": 4091,
                    "initial_embeddings": 4091,
                    "processed_files": 4,
                    "skipped_files": 1,
                    "error_files": 0,
                    "total_chunks": 84,
                    "embeddings": 84,
                    "duration_text": "17.23s",
                }
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["mcp: chunkhound ready"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Index: follow-up", joined)
        self.assertIn("Run: 4 proc · 1 skip · 0 err", joined)
        self.assertIn("Output: 84 chunks · 84 emb · 17.23s", joined)
        self.assertIn("Before: 120 files · 4091 chunks · 4091 emb", joined)

    def test_dashboard_running_prefers_structured_live_progress_over_raw_activity(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "live_progress": {
                "current": {
                    "type": "agent_message",
                    "text": "Checking changed files",
                    "ts": "2026-03-17T12:00:02+00:00",
                },
                "timeline": [
                    {
                        "type": "thread_started",
                        "text": "Codex session started.",
                        "ts": "2026-03-17T12:00:00+00:00",
                    },
                    {
                        "type": "turn_started",
                        "text": "Review turn started.",
                        "ts": "2026-03-17T12:00:01+00:00",
                    },
                    {
                        "type": "agent_message",
                        "text": "Checking changed files",
                        "ts": "2026-03-17T12:00:02+00:00",
                    },
                ],
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["raw-codex-tail"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Live Progress", joined)
        self.assertIn("Phase: Generate review", joined)
        self.assertIn("Now: Checking changed files", joined)
        self.assertIn("[12:00:00] Codex session started.", joined)
        self.assertNotIn("─ Activity", joined)

    def test_dashboard_shows_chunkhound_preflight_stage_summary(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "chunkhound_access_preflight",
            "phases": {"chunkhound_access_preflight": {"status": "running"}},
            "chunkhound": {
                "access": {
                    "preflight_stage": "tools/list",
                    "preflight_stage_status": "timeout",
                    "elapsed_seconds": 8.2,
                    "error": "helper preflight timed out while waiting for tools/list",
                    "preflight_ok": False,
                }
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("ChunkHound:", joined)
        self.assertIn("tools/list timeout 8.2s", joined)

    def test_dashboard_done_uses_review_snapshot_in_primary_pane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "### Steps taken",
                        "- inspected diff",
                        "",
                        "**Summary**: Ticket ABAU-1026 aligns with the empty-state wording update.",
                        "",
                        "## Business / Product Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "### In Scope Issues",
                        "- CTA copy is inconsistent with the approved wording.",
                        "",
                        "## Technical Assessment",
                        "**Verdict**: APPROVE",
                        "### In Scope Issues",
                        "- None.",
                        "####",
                    ]
                ),
                encoding="utf-8",
            )
            meta = {
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 1,
                "title": "Test PR",
                "session_id": "s",
                "created_at": "",
                "status": "done",
                "completed_at": "2026-03-04T00:05:00+00:00",
                "phase": "codex_review",
                "phases": {"codex_review": {"status": "done", "duration_seconds": 10.0}},
                "paths": {"session_dir": tmp, "review_md": str(review_md)},
            }
            lines = rui.build_dashboard_lines(
                meta=meta,
                snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
                chunkhound_tail=[],
                codex_tail=["### In Scope Issues", "- stale tail"],
                no_stream=False,
                width=140,
                height=30,
                color=False,
            )
        joined = "\n".join(lines)
        self.assertIn("─ Review Snapshot", joined)
        self.assertIn("Summary: Ticket ABAU-1026 aligns with the empty-state wording update.", joined)
        self.assertIn("Business: REQUEST CHANGES", joined)
        self.assertIn("Business issue: CTA copy is inconsistent with the approved wording.", joined)


class TuiPrintFinalMarkdownTests(unittest.TestCase):
    class _FakeTtyStderr:
        def __init__(self, *, is_tty: bool) -> None:
            self._is_tty = bool(is_tty)
            self._parts: list[str] = []

        def isatty(self) -> bool:  # pragma: no cover
            return self._is_tty

        def write(self, s: str) -> int:  # pragma: no cover
            self._parts.append(str(s))
            return len(s)

        def flush(self) -> None:  # pragma: no cover
            return None

        def getvalue(self) -> str:
            return "".join(self._parts)

    def test_maybe_print_markdown_after_tui_noop_when_ui_disabled(self) -> None:
        md = ROOT / ".tmp_test_tui_print.md"
        try:
            md.write_text("hello", encoding="utf-8")
            err = self._FakeTtyStderr(is_tty=True)
            rf.maybe_print_markdown_after_tui(ui_enabled=False, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "")
        finally:
            md.unlink(missing_ok=True)

    def test_maybe_print_markdown_after_tui_prints_clear_and_full_body(self) -> None:
        md = ROOT / ".tmp_test_tui_print2.md"
        try:
            md.write_text("line1\nline2", encoding="utf-8")  # no trailing newline
            err = self._FakeTtyStderr(is_tty=True)
            rf.maybe_print_markdown_after_tui(ui_enabled=True, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "\x1b[2J\x1b[H" + "line1\nline2\n")
        finally:
            md.unlink(missing_ok=True)

    def test_maybe_print_markdown_after_tui_noop_when_stderr_not_tty(self) -> None:
        md = ROOT / ".tmp_test_tui_print3.md"
        try:
            md.write_text("hello\n", encoding="utf-8")
            err = self._FakeTtyStderr(is_tty=False)
            rf.maybe_print_markdown_after_tui(ui_enabled=True, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "")
        finally:
            md.unlink(missing_ok=True)
