# Tasks: simple-pr-context

## Setup & Prerequisites
- [x] Crear directorio `cure_pr_context/` con `__init__.py` vacío
- [x] Crear directorio `tests/cure_pr_context/` (sin `__init__.py` para no sombrear el package real durante pytest)
- [x] Añadir `cure_pr_context` a `pyproject.toml` (`[tool.setuptools].packages`) para install/wheel
- [x] Leer viejo `github_history.py` / old branch `cure.py` del branch `cure-subsequent-pr-review/story-01-intake` — extraer `collect_pr_discussion`, endpoints, `gh_api_list`, paginación y normalización
- [x] Leer viejo `prior_corpus.py` del mismo branch — extraer footer detection oficial (`CURE_REVIEW_FOOTER_START/END`), `sha`, `session`, scan de sesiones locales; adaptar a compatibilidad explícita con `head_sha` live

## Core Implementation
- [x] Implementar/portar `cure.py::gh_api_list()` — helper list-capable para `gh api --paginate [--slurp]` con fallback sin `--slurp`
- [x] Implementar `fetcher.py::fetch_pr_discussion()` — 3 endpoints, `gh_fetch` list-capable, normalizar a dicts planos
- [x] Implementar `corpus.py::find_past_reviews(..., head_sha)` — scan local bajo `sandbox_root` + footers remotos oficiales en issue comments y review bodies con compatibilidad de head por prefijo
- [x] Implementar `corpus.py::deduplicate()` — char n-grams + Jaccard ≥ 0.85; retener `past_reviews` y devolver `discussion` pruned sin eventos duplicados
- [x] Implementar `orient.py::build_orientation_brief()` — prompt del scanner + LLM call → secciones fijas + instrucciones inline
- [x] Implementar `__init__.py::build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` — orquestar fetch → corpus/head-SHA check → retained-side dedup → orient → escribir debug artifacts pruned/retained → retornar dict
- [x] Añadir `$PRIOR_CONTEXT` a los 5 templates built-in con documentación de uso: normal singlepass, big singlepass, multipass plan/step/synth
- [x] Inyectar `build_pr_context()` en `cure.py::_pr_flow_impl` después de `compute_pr_stats`, pasando `head_sha` efectivo (`review_head_sha` si existe, si no PR API `head_sha`)
- [x] Pasar `PRIOR_CONTEXT` siempre (brief o `""`) en `extra_vars` de normal singlepass, big singlepass y multipass plan/step/synth
- [x] Registrar `pr_context` meta en `progress.meta` y abortar antes de prompt rendering ante errores GitHub/LLM/session scan

## Verification & Proof
- [x] `tests/cure_pr_context/test_fetcher.py` — unit tests con mock de `gh_fetch`/`gh_api_list` retornando arrays (TAP-01)
- [x] `tests/cure_pr_context/test_corpus.py` — unit tests con tmp `sandbox_root` session dirs + discussion en memoria con footer oficial; probar `head_sha` compatible/incompatible y que `past_reviews` es el lado retenido mientras `discussion` se prunea (TAP-02)
- [x] `tests/cure_pr_context/test_orient.py` — unit tests con mock `run_llm` (TAP-03)
- [x] `tests/cure_pr_context/test_init.py` — unit tests de `build_pr_context` con `pr_stats` + `head_sha` fixtures, mock `gh_fetch`, mock `run_llm`, tmp `sandbox_root` y tmp `work_dir`; assert debug artifacts usan discussion pruned/past_reviews retained (TAP-04)
- [x] `tests/cure_pr_context/test_integration.py` — end-to-end con fixtures JSON para los 3 endpoints, footer SHA compatible/incompatible, retained-side dedup y output discussion pruned (TAP-05)
- [x] `tests/cure_pr_context/test_templates.py` — verificar `$PRIOR_CONTEXT` en 5 templates renderizados, con brief y con `""`, sin tokens crudos (TAP-06)
- [x] `tests/test_cure_pr_flow.py` — verificar punto de inyección, `head_sha` efectivo pasado a `build_pr_context`, y `extra_vars` siempre con `PRIOR_CONTEXT` en normal singlepass, big singlepass, multipass plan/step/synth; fallback con helper seams/monkeypatch, no `--dry-run` genérico (TAP-07)
- [x] Packaging smoke — construir wheel/install target y `import cure_pr_context` desde instalación (TAP-09)

## Integration & Cleanup
- [x] Ruff check + mypy clean en `cure_pr_context/` (TAP-08)
- [x] Correr full CURe test suite — verificar cero regresiones
- [x] `git status` — confirmar solo archivos del scope creados/modificados
