# Proposal: simple-pr-context

## Goal / Context

`cure pr` currently reviews PRs blind to discussion history — it sees only the PR description and the diff. This change adds a `cure_pr_context` package that fetches all PR discussion (comments, reviews, review comments) and past CURe reviews, deduplicates them, and runs a single LLM orientation scan. The resulting structured brief is injected as `$PRIOR_CONTEXT` into every built-in review prompt path (normal singlepass, big singlepass, and multipass), guiding the review agent toward unresolved problem areas and away from already-addressed ones. The feature runs automatically on `cure pr` review runs with no operator flags required.

## Story Candidates

Single story — this change workspace is the full scope of the `simple-pr-context` initiative.

## Decisions & Constraints

Un solo package `cure_pr_context/` con 4 archivos. La API pública es `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` que retorna un dict con el orientation brief, los datos deduplicados para debug, y metadata. `head_sha` es el SHA efectivo de la PR/review pasado explícitamente desde `_pr_flow_impl` para verificar compatibilidad de footers remotos; `gh_fetch` es list-capable (`gh_api_list`), `sandbox_root` es el root real de sesiones/sandboxes, `work_dir` es el `work/` de la sesión actual, y `pr_stats` es el resultado ya computado por `compute_pr_stats`. El brief es producido por un solo LLM scan con secciones fijas e instrucciones de uso inline; se inyecta como `$PRIOR_CONTEXT` en los 5 templates built-in de review. `PRIOR_CONTEXT` se pasa siempre como extra var (`""` o contenido) para evitar tokens crudos. La deduplicación de past reviews usa char n-grams + Jaccard sin dependencias externas; `past_reviews` es el lado retenido y los eventos duplicados se eliminan del `discussion` retornado/escrito/pasado al LLM. El LLM se recibe como `Callable` inyectado desde `cure.py`. Cualquier error aborta la review. Sin cache, sin flags CLI nuevos, sin cambios a `cure_flows.py`.

## External Resources

- Old initiative branch (historical reference): `cure-subsequent-pr-review/story-01-intake` (38 commits, preserved in this repo)
