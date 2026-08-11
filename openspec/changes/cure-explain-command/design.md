# Design: cure-explain-command

## Command surface

```
cure explain <PR_URL> [--explain-prompt <TEXT>]
             [--llm-* overrides] [--codex-model ...] [--quiet] [--no-stream] [--verbosity ...]
```

- Visible command; the `pr_url` positional is required (same argument shape as
  `cure pr`); no TTY requirement.
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
8. **Prompt assembly** (additive contract: the builtin template is always the
   base; a user question is appended as a `## User's question` block and lands
   last):
   - inline mode: `template + "\n\n## Final synthesized review\n\n" + review_text`
     `+ question_block`
   - resume-fork mode: `resume note + template + question_block` (the fork
     already holds the review in context; the question still lands last)
   - template = `load_builtin_prompt_text("explain.md")` always
     (`prompt_source` = `user:explain_prompt` when a question was given,
     `builtin:explain.md` otherwise)
9. `run_llm_exec(..., resume_session_id=fork_id)`:
   - fork mode → `build_codex_exec_cmd` emits
     `codex exec resume <fork-id> <flags> --json -o <artifact> <prompt>`
     (no `-C`, no `--add-dir`, prompt as trailing positional — resume subcommand
     surface)
   - inline mode → existing one-shot `codex exec` path (unchanged)
10. Append `explains[]` entry with per-explanation provenance
    (provider/model/preset/transport, normalized usage, timestamps, prompt_source,
    output_path, optional `resume: {mode: "fork", base_session_id,
    fork_session_id}`); write meta under `file_lock` with a fresh reload.
    `meta.llm` / `meta.llm.resume` / `meta.codex.resume` are read-only for explain.
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
| base rollout not found / fork read/write/decode failure | inline (silent, entry without `resume` key) |

Fork read/write/decoding failures (`OSError`/`UnicodeError`) are converted to
`ReviewflowError` inside `fork_codex_session` so the flow's single fallback catch
handles them.

## Read-only runtime (PR #37 review)

- The flow passes `runtime_policy={dangerously_bypass_approvals_and_sandbox: False,
  approval_policy: None}` and `sandbox_mode="read-only"` to `run_llm_exec`.
- `build_codex_exec_cmd`: inline path adds `--sandbox read-only` (stripping any
  config `--sandbox`/`--search`); resume path adds `-c sandbox_mode="read-only"`
  and filters flags to the resume-compatible subset (`-m`/`-c` only), honoring
  `--skip-git-repo-check` on the trusted-directory retry.
- `run_llm_exec` passes `approval_policy` through as-is (None) instead of forcing
  `"never"` — codex 0.144.6 has no `-a` flag, so the `-a` branch must not fire.

## Streaming (PR #37 review)

- The flow registers a `ReviewflowOutput` (ui disabled, `stderr`, session
  `logs_dir`, verbosity) via `set_active_output`/`start`/`stop`/`clear_active_output`
  around the LLM run — `run_logged_cmd` then streams codex display lines to stderr
  (`also_to`) while the model generates; the completed artifact is still printed
  on stdout at the end.

## Concurrency and cleanup (PR #37 review)

- Artifact names: `explain-<ts>-<uuid8>.md` (no same-second collisions).
- Meta append: `file_lock(meta_path)` + fresh `_load_session_meta` reload inside
  the lock, then `write_redacted_json`.
- Cleanup span: `cleanup_sensitive_staged_paths` covers the whole post-staging
  span; `_stage_review_auth_support` (both cure.py and cure_llm.py copies)
  rolls back already-staged paths if a later staging step fails.
- Failure-scoped fork rollback: the fork rollout is deleted when the run does not
  complete (kept on success — referenced by the explains entry).

## Metadata contract (`meta.json`)

```json
"explains": [{
  "started_at": "...", "completed_at": "...",
  "prompt_source": "builtin:explain.md | user:explain_prompt",
  "output_path": ".../explain/explain-<ts>.md",
  "resume": {"mode": "fork", "base_session_id": "...", "fork_session_id": "..."}  // fork mode only
}]
```

- The review's top-level `llm` block is never mutated by explain — each
  `explains[]` entry records its own provider/model/preset/transport and
  normalized usage (`usage: {input_tokens, output_tokens, total_tokens}`).
- `meta.llm.resume` and `meta.codex.resume` are never modified — `interactive`
  continues to resume the pristine base session.
- Progress flushes use `SessionProgress(merge_under_lock=True)`: overlay only
  progress-owned keys on a fresh on-disk reload under `file_lock` so concurrent
  explain runs cannot erase each other's `explains[]` appends.

## Verification design

- 31 unit obligations in `tests/_reviewflow_unittest_explain.py`:
  inline happy path / custom prompt / streaming / error paths / parser / catalog /
  wrapper / fork+resume (base byte-identical, ids rewritten, no review append,
  resume pointers untouched) / three fallback cases / fork helper unit tests.
- PR #37 remediation obligations (8 more): resume flag whitelist + read-only cmd
  shape (both branches), flow runtime policy, early-failure credential cleanup,
  unique artifact names, meta file_lock usage, fork deletion on LLM failure,
  fork I/O failure → ReviewflowError.
- PR #37 re-review obligations (9 more): rf-jira staging skipped for explain;
  `normalize_artifact=False` plumbing (flow + run_codex_exec skip); per-entry
  provenance (no top-level llm merge); session-path containment (repo_dir,
  review_md outside session rejected); merge-under-lock progress preserves
  concurrent explains appends; fork partial-rollout cleanup; sink `Codex notice:`
  rendering for codex error items.
- Full suite regression, ruff, py_compile; Story 26 smoke against an editable
  install venv; real-run proof (write/gh probes denied, live stderr streaming,
  base sha unchanged).
