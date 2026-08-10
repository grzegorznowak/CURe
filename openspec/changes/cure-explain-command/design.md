# Design: cure-explain-command

## Command surface

```
cure explain --pr <PR_URL> [--explain-prompt <TEXT>]
             [--llm-* overrides] [--codex-model ...] [--quiet] [--no-stream] [--verbosity ...]
```

- Visible command (unlike hidden `followup`); `--pr` required; no TTY requirement.
- Registered via the standard three touch points: `build_parser` subparser (after
  the `followup` block), `main()` dispatch (after `followup`), `explain_flow`
  wrapper in cure_commands.py delegating to `_explain_flow_impl`. Catalog entry in
  `build_commands_catalog_payload`.

## Flow (`cure.py::_explain_flow_impl`)

1. Resolve verbosity → `stream = (not quiet) and (not no_stream)`.
2. `parse_pr_url(args.pr)` (raises ReviewflowError on invalid input).
3. `scan_completed_sessions_for_pr(sandbox_root=paths.sandbox_root, pr=pr)`; take
   `[0]` (newest completed); empty → ReviewflowError. Session meta loaded from
   `meta.json`; `repo_dir`/`work_dir` from `meta.paths` with session-dir defaults.
4. Read `review_md_path` (from the session record, honoring `meta.paths.review_md`);
   missing → ReviewflowError.
5. Stage auth env via `_stage_review_auth_support(work_dir, repo_dir, env)` —
   GH_CONFIG_DIR / JIRA / NETRC / CURE_WORK_DIR; staged paths cleaned in `finally`.
6. `resolve_llm_config_from_args` (config + codex base config paths).
7. **Fork decision** (only when `provider == "codex"`):
   - `_recorded_resume_session_id(meta)` reads `meta.llm.resume.session_id` then
     `meta.codex.resume.session_id`.
   - `fork_codex_session(codex_root, base_id, created_at, completed_at)` copies the
     base rollout into `CODEX_HOME/sessions/<today>/rollout-<ts>-<new-uuid>.jsonl`
     with every occurrence of the base uuid rewritten to the new uuid.
   - Fork failure → silent inline fallback (resume ids reset to None).
8. **Prompt assembly**:
   - inline mode: `template + "\n\n## Final synthesized review\n\n" + review_text`
   - resume-fork mode: template only (the fork already holds the review in context)
   - template = `--explain-prompt` text (`user:explain_prompt`) or
     `load_builtin_prompt_text("explain.md")` (`builtin:explain.md`)
9. `run_llm_exec(..., resume_session_id=fork_id)`:
   - fork mode → `build_codex_exec_cmd` emits
     `codex exec resume <fork-id> <flags> --json -o <artifact> <prompt>`
     (no `-C`, no `--add-dir`, prompt as trailing positional — resume subcommand
     surface)
   - inline mode → existing one-shot `codex exec` path (unchanged)
10. Record `record_llm_usage` + append `explains[]` entry with optional
    `resume: {mode: "fork", base_session_id, fork_session_id}`; write meta.
    `meta.llm.resume` / `meta.codex.resume` are read-only for explain.
11. Print explanation text (if artifact non-empty) then the artifact path; return 0.

## Fork mechanics (`cure_llm.py::fork_codex_session`)

- codex 0.144.6 has no `--fork`; sessions are single rollout JSONL files.
- Locate base via existing `_find_codex_session_log_by_id` (date windows from
  created/completed timestamps).
- New id = `uuid4()`; destination date dir = today; filename follows the codex
  `rollout-<ts>-<uuid>.jsonl` convention.
- Content = byte-copy with `text.replace(base_id, new_id)` (the id appears in the
  `session_meta` line and event lines).
- `ReviewflowError` if base missing or id absent from content.

## Fallback rules

| condition | mode |
|---|---|
| provider != codex | inline |
| no `meta.llm.resume`/`codex.resume` session id | inline |
| base rollout not found / fork write error | inline (silent, entry without `resume` key) |

## Metadata contract (`meta.json`)

```json
"explains": [{
  "started_at": "...", "completed_at": "...",
  "prompt_source": "builtin:explain.md | user:explain_prompt",
  "output_path": ".../explain/explain-<ts>.md",
  "resume": {"mode": "fork", "base_session_id": "...", "fork_session_id": "..."}  // fork mode only
}]
```

- `llm` block gains usage/provider info via `record_llm_usage` (as in other flows).
- `meta.llm.resume` and `meta.codex.resume` are never modified — `interactive`
  continues to resume the pristine base session.

## Verification design

- 16 unit obligations in `tests/_reviewflow_unittest_explain.py`:
  inline happy path / custom prompt / streaming / error paths / parser / catalog /
  wrapper / fork+resume (base byte-identical, ids rewritten, no review append,
  resume pointers untouched) / three fallback cases / fork helper unit tests.
- Full suite regression, ruff, py_compile.
- Real-run proof: fork resume against the completed PR21 session with
  `sha256sum` of the base rollout before/after.
