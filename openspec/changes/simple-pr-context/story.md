Plan: 🟢 PLAN APPROVED
Status: ✅ DONE

## Purpose

`cure pr` currently reviews PRs blind to discussion history — it sees only the PR description and the diff. This change adds a `cure_pr_context` package that fetches all PR discussion (comments, reviews, review comments) and past CURe reviews, deduplicates them, and runs a single LLM orientation scan. The resulting structured brief is injected as `$PRIOR_CONTEXT` into every built-in review prompt (normal singlepass, big singlepass, and multipass), guiding the review agent toward unresolved problem areas and away from already-addressed ones. The feature runs automatically on `cure pr` review runs with no operator flags required.

## Actors

- **Primary:** CURe operator running `cure pr` — recibe reviews informadas por discussion context sin flags adicionales
- **Secondary:** Review agent (LLM) — consume `$PRIOR_CONTEXT` como guía de orientación
- **Affected:** PR author / reviewers — sus comments y reviews pasados ahora influyen en futuras reviews automáticas
- **Reviewer:** CURe maintainer — verifica que el package no rompa el flow existente y que los tests pasan

## Triggering Need

La iniciativa `cure-subsequent-pr-review` (38 commits) construyó un pipeline de 18 archivos que resultó sobre-ingeniería para el problema real. Los usuarios reportaron que lo que necesitan es orientación simple sobre la discusión del PR, no un sistema multi-etapa de clasificación y verificación. Este story implementa la versión simplificada desde cero, portando solo el código reutilizable del viejo branch.

## Expected Prerequisites

None. Este es el primer y único story de la iniciativa. El viejo branch `cure-subsequent-pr-review/story-01-intake` es referencia histórica, no un prerequisite vivo.

## Scope

- Crear `cure_pr_context/` package con 4 archivos: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- Registrar `cure_pr_context` en `pyproject.toml` para que installs/wheels incluyan el package
- Añadir `gh_api_list`/`gh_fetch` list-capable en `cure.py`; no reutilizar `gh_api_json` para endpoints que devuelven arrays
- `fetch_pr_discussion()`: 3 endpoints GitHub → dicts planos
- `find_past_reviews(..., head_sha)`: sesiones locales bajo `sandbox_root` + footers CURe remotos actuales + compatibilidad de head + dedup Jaccard
- `build_orientation_brief()`: LLM scan → secciones fijas con instrucciones inline
- `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)`: orquestación, retorna dict con `orientation_brief`, `discussion`, `past_reviews`, `meta`; `discussion` ya viene sin eventos duplicados contra `past_reviews`
- Inyectar llamada en `cure.py::_pr_flow_impl` después de `compute_pr_stats`, pasando `head_sha` efectivo
- `$PRIOR_CONTEXT` en los 5 templates built-in de review: normal singlepass, big singlepass, multipass plan, multipass step, multipass synth
- Debug artifacts: `work/pr_context_discussion.json`, `work/pr_context_past_reviews.json`
- Tests unitarios + integración con fixtures deterministas
- Fail hard en cualquier error

## Out of Scope

- Cache o almacenamiento persistente
- Flags CLI nuevos
- Cambios en `cure_flows.py` más allá del template variable `$PRIOR_CONTEXT`
- UI/TUI changes
- Truncamiento de discussion larga
- Modelo separado para el scan (usa el mismo LLM que la review)
- Garantizar que prompts custom (`--prompt` / `--prompt-file`) contengan `$PRIOR_CONTEXT`; el `extra_vars` seguro puede estar disponible, pero templates de usuario son responsabilidad del operador
- Templates de follow-up/resume que no forman parte del nuevo review prompt path de `cure pr`

## Scenarios / Behavior Examples

### S1 — Baseline: PR sin discussion ni past reviews
- Given: PR nuevo, 0 comments, 0 reviews, 0 sesiones locales previas
- When: `cure pr` corre
- Then: `build_pr_context()` retorna `orientation_brief = ""`. `extra_vars["PRIOR_CONTEXT"]` se pasa como `""` y `render_prompt` reemplaza `$PRIOR_CONTEXT` sin dejar tokens crudos. La review corre semánticamente como hoy.
- Covers: A6

### S2 — PR con discussion activa, sin past CURe reviews
- Given: PR con 15 comments de 3 autores, 2 reviews (CHANGES_REQUESTED + APPROVED), 8 review comments inline. Sin sesiones locales previas.
- When: `cure pr` corre
- Then: `$PRIOR_CONTEXT` contiene briefing basado en los 25 eventos. Secciones "Problemáticas" y "Pendientes" reflejan los review comments que pidieron cambios. Sección "Resueltas" refleja threads marcados como resueltos.
- Covers: A5

### S3 — PR con past CURe review (sesión local + footer remoto), dedup
- Given: PR con una review CURe anterior (sesión local + comment/review body con footer CURe oficial). El footer CURe aparece también como comment en la discussion. Otros 5 comments normales.
- When: `cure pr` corre
- Then: El footer CURe se detecta como past review. La past review es el lado retenido: el comment duplicado se elimina de `discussion` output/debug/LLM input (quedan la past review + los 5 comments normales). `meta.n_deduped = 1`.
- Covers: A4

### S4 — Error: GitHub API falla
- Given: PR sin acceso a GitHub API (sin conexión, o token inválido)
- When: `cure pr` corre
- Then: `build_pr_context()` lanza excepción. La review aborta con mensaje de error. No se crean debug artifacts parciales.
- Covers: A2

### S5 — Multipass review recibe `$PRIOR_CONTEXT`
- Given: PR grande que dispara el perfil `big` y multipass está habilitado
- When: `cure pr` corre en modo multipass
- Then: Los prompts multipass (plan, cada step renderizado desde el step template, synth) contienen `$PRIOR_CONTEXT` con el mismo orientation brief
- Covers: A8

### S6 — Big singlepass review recibe `$PRIOR_CONTEXT`
- Given: PR grande que dispara el perfil `big`, pero multipass está deshabilitado por config o CLI
- When: `cure pr` corre en modo singlepass con `prompts/mrereview_gh_local_big.md`
- Then: El prompt big singlepass contiene `$PRIOR_CONTEXT` con el mismo orientation brief o `""` seguro
- Covers: A8

## Acceptance

- **A1:** `cure_pr_context/` package existe con 4 archivos: `__init__.py`, `fetcher.py`, `corpus.py`, `orient.py`
- **A2:** `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm)` retorna dict con keys `orientation_brief`, `discussion`, `past_reviews`, `meta`, o lanza excepción en error; `head_sha` es el SHA actual de la PR/review para verificar compatibilidad de footers remotos; `gh_fetch` es list-capable (`gh_api_list`/bound callable), no `gh_api_json`
- **A3:** `fetch_pr_discussion()` llama a 3 endpoints GitHub vía `gh_fetch` y retorna lista de dicts planos con keys `kind`, `author`, `body`, `created_at`, `url`, `path`, `line`, `review_state`
- **A4:** `find_past_reviews()` detecta sesiones locales (`review.md`) bajo `sandbox_root` y footers CURe remotos oficiales (en issue comments y review bodies) delimitados por `CURE_REVIEW_FOOTER_START` / `CURE_REVIEW_FOOTER_END` con token `sha <short>`, verifica compatibilidad por prefijo contra `head_sha` cuando footer y head son conocidos, y deduplica vs discussion con Jaccard ≥ 0.85 reteniendo `past_reviews` y removiendo los eventos duplicados de `discussion`
- **A5:** `build_orientation_brief()` produce un string con secciones fijas (Áreas resueltas, Problemáticas, Pendientes, Patrones, Decisiones) e instrucciones de uso inline
- **A6:** Cuando no hay discussion ni past reviews, `orientation_brief` es `""` y `PRIOR_CONTEXT` se añade igualmente a `extra_vars` como `""`; ningún `$PRIOR_CONTEXT` crudo queda en prompts renderizados
- **A7:** `build_pr_context()` se llama desde `_pr_flow_impl` después de `compute_pr_stats`, antes de la decisión multipass/singlepass final, y recibe `head_sha` efectivo (`review_head_sha` si existe, si no PR API `head_sha`)
- **A8:** `$PRIOR_CONTEXT` aparece en los 5 templates built-in de review: normal singlepass, big singlepass, multipass plan, multipass step, multipass synth; custom prompts y follow-up/resume templates quedan excluidos explícitamente
- **A9:** Debug artifacts `work/pr_context_discussion.json` (discussion pruned) y `work/pr_context_past_reviews.json` (past reviews retained) se escriben incluso cuando `orientation_brief` es `""` (siempre que haya datos)
- **A10:** Tests unitarios por módulo (`fetcher`, `corpus`, `orient`) + test de integración end-to-end con fixtures deterministas
- **A11:** `pyproject.toml` incluye `cure_pr_context` en la metadata explícita de setuptools y un install/wheel smoke puede importar `cure_pr_context`

## Verification

### Fail-open Checks

#### Prompt/template substitution (risk lens: prompt/template substitution)

- **No raw `$PRIOR_CONTEXT` tokens leak:** `render_prompt` (`cure_flows.py:1437`) replaces `$KEY` and `${KEY}` only for values present in `extra_vars`. When `PRIOR_CONTEXT` is missing, the literal `$PRIOR_CONTEXT` remains. The implementation must always add `extra_vars["PRIOR_CONTEXT"]` (either `""` or content), making the missing-var path dead for built-in review prompts. TAP-06/TAP-07 verify.
- **Empty-string path (baseline):** When `orientation_brief == ""`, `extra_vars["PRIOR_CONTEXT"] = ""`. `render_prompt` replaces `$PRIOR_CONTEXT` with `""` — the agent sees a blank line or nothing. Template rendering completion is semantically identical to current behavior. TAP-06 covers.
- **Enabled path (activation):** When `orientation_brief` is non-empty, `extra_vars["PRIOR_CONTEXT"]` contains the full orientation brief. `render_prompt` substitutes it in all 5 built-in review templates. The agent sees the structured brief. TAP-06/TAP-07 cover.
- **Degraded path (API/LLM failure):** `build_pr_context()` raises, the review aborts before prompt rendering. No partial `$PRIOR_CONTEXT` is ever rendered. TAP-04 and TAP-05 verify fail-hard behavior.

### Input Boundary Shape Risk

| Boundary | Source shape | Strict assumption / risk | Required mitigation | Proof |
|----------|--------------|--------------------------|---------------------|-------|
| GitHub discussion endpoints | JSON arrays from comments/reviews/review-comments endpoints | Existing `gh_api_json` rejects non-dict payloads | Add/port `gh_api_list`; `fetch_pr_discussion` accepts only list-capable `gh_fetch` and normalizes arrays | TAP-01, TAP-04, TAP-05 |
| PR metadata endpoint | JSON object | Existing `gh_api_json` remains appropriate for PR metadata | Do not replace metadata fetch with list helper | TAP-07 code review |
| Local prior sessions | Directories under `sandbox_root` / `~/.local/state/cure/sandboxes` | A nonexistent `sessions_root` would miss completed sessions | Pass the real `sandbox_root` into `find_past_reviews` | TAP-02, TAP-04 |
| Remote CURe footers | Markdown bodies with current official footer block and `sha <short>` token | Old `CURe-pr-footer reviewed_head=` contract would miss live footers; no current head signal would make compatibility unprovable | Parse `CURE_REVIEW_FOOTER_START`/`END`, `sha`, and `session` metadata; pass current `head_sha` from `_pr_flow_impl` and compare by prefix when both values are known | TAP-02, TAP-05, TAP-07 |
| Prompt templates | Missing `extra_vars` key leaves raw `$PRIOR_CONTEXT` | Fail-open raw token leak | Always pass `PRIOR_CONTEXT` as `""` or brief | TAP-06, TAP-07 |
| Packaging metadata | Explicit setuptools package list | New package omitted from installs | Add `cure_pr_context` to `pyproject.toml` and run import smoke | TAP-09 |

### Surface / Branch Proof Matrix

| Surface / branch | In scope? | `$PRIOR_CONTEXT` obligation | Proof |
|------------------|-----------|-----------------------------|-------|
| Normal singlepass built-in review (`prompts/mrereview_gh_local.md`) | Yes | Template contains `$PRIOR_CONTEXT`; render uses always-present `extra_vars["PRIOR_CONTEXT"]` | TAP-06, TAP-07 |
| Big singlepass built-in review (`prompts/mrereview_gh_local_big.md`) | Yes | Same as normal singlepass, including when multipass is disabled | TAP-06, TAP-07 |
| Multipass plan (`prompts/mrereview_gh_local_big_plan.md`) | Yes | Plan prompt receives same brief/string | TAP-06, TAP-07 |
| Multipass step (`prompts/mrereview_gh_local_big_step.md`) | Yes | Every rendered step receives same brief/string | TAP-06, TAP-07 |
| Multipass synth (`prompts/mrereview_gh_local_big_synth.md`) | Yes | Synthesis prompt receives same brief/string | TAP-06, TAP-07 |
| Custom prompt files / inline prompts | No template insertion guarantee | If a user includes `$PRIOR_CONTEXT`, safe `extra_vars` can substitute it; user-owned text is out of scope | Explicit exclusion in A8 |
| Follow-up/resume templates | No | Not part of this story's new `cure pr` review prompt path | Explicit exclusion in A8 |

### Risk Lens Inventory

| Risk lens | Activated? | Coverage / exclusion |
|-----------|------------|----------------------|
| External services / subprocess I/O | Yes | GitHub API helper and failure paths covered by TAP-01/TAP-04/TAP-05 |
| Filesystem / generated artifacts | Yes | `sandbox_root` scanning and `work/pr_context_*.json` artifacts covered by TAP-02/TAP-04/TAP-05 |
| Prompt/template substitution | Yes | Fail-open Checks + TAP-06/TAP-07 |
| Packaging/install surface | Yes | A11 + TAP-09 |
| Persistence/cache/migrations | No | Cache/persistent storage is explicitly out of scope |
| UI/TUI behavior | No | UI/TUI changes are out of scope; progress meta only |

### Design Sources

| Source | Status | Use |
|--------|--------|-----|
| Live CURe code anchors in Discovery Notes (`cure.py`, `cure_flows.py`, `cure_output.py`, `cure_sessions.py`, `paths.py`, `pyproject.toml`, `prompts/`) | normative | Source-fit contracts for API shape, injection point, footer parsing, session root, packaging, and prompt branch coverage |
| Old branch `cure-subsequent-pr-review/story-01-intake` (`github_history.py`, `prior_corpus.py`, old `cure.py`) | orientation only | Porting hints for list helper, discussion normalization, and footer parsing; verify against live code before implementation |

### Design Element Trace

| Design element | Status | Scenario → Acceptance → Verification trace |
|----------------|--------|--------------------------------------------|
| List-capable GitHub discussion fetch via `gh_fetch`/`gh_api_list` | required | S2/S4 → A2/A3 → TAP-01/TAP-04/TAP-05 |
| Real prior-review corpus sources (`sandbox_root`, official footer markers, current `head_sha`) | required | S3 → A4 → TAP-02/TAP-05/TAP-07 |
| Always-safe prompt variable substitution | required | S1/S5/S6 → A6/A8 → TAP-06/TAP-07 |
| Package installability | required | Implementation/install surface → A11 → TAP-09 |
| Custom/follow-up prompt exclusion | flexible (bounded) | A8 explicit exclusion → Surface / Branch Proof Matrix |

### Verification Commands

```bash
# Unit tests
python -m pytest tests/cure_pr_context/ -v

# Integration test (fixtures deterministas, sin GitHub real)
python -m pytest tests/cure_pr_context/test_integration.py -v

# Template + flow branch proof
python -m pytest tests/cure_pr_context/test_templates.py tests/test_cure_pr_flow.py -v

# Ruff + mypy
ruff check cure_pr_context/
mypy cure_pr_context/

# Packaging smoke (no install into repo environment)
rm -rf .tmp_package_smoke
python -m pip wheel . -w .tmp_package_smoke/wheelhouse
python -m pip install --no-deps --target .tmp_package_smoke/install .tmp_package_smoke/wheelhouse/cureview-*.whl
PYTHONPATH=.tmp_package_smoke/install python -c "import cure_pr_context"

# Full CURe test suite (asegurar no regresión)
python -m pytest tests/ -x --timeout=120
```

### Test Architecture Plan

| Row ID | Layer / Scope | Behavior / Acceptance Slice | Owning Suite / File(s) | Boundary Exercised | Assertions / Observability | Fixture / Test Data Strategy | CI Lane / Command | Fallback Plan | Split / Merge Rationale |
|--------|--------------|---------------------------|----------------------|-------------------|--------------------------|----------------------------|-------------------|---------------|------------------------|
| TAP-01 | Unit | `fetch_pr_discussion` — 3 endpoints, normalización, list-capable caller | `tests/cure_pr_context/test_fetcher.py` | GitHub API boundary (mocked `gh_fetch`/`gh_api_list`) | dict keys, event count, field types, caller paths, array handling | Mock `gh_fetch` returning list payloads por endpoint | `pytest tests/cure_pr_context/test_fetcher.py` | Si mock se vuelve frágil, usar respuestas grabadas | Un test por endpoint + test de fallo |
| TAP-02 | Unit | `find_past_reviews` + `deduplicate` — local sandbox sessions + remote official footers; retained side is `past_reviews`, duplicate discussion events are pruned | `tests/cure_pr_context/test_corpus.py` | Filesystem (`sandbox_root` session dirs) + discusión en memoria + current `head_sha` | past review count, footer detection, SHA/session metadata, head-SHA compatibility, retained-side/pruned-discussion, dedup count | Directorios temporales con `review.md` fake; discussion events en memoria con `CURE_REVIEW_FOOTER_START/END`; compatible and incompatible footer SHA fixtures | `pytest tests/cure_pr_context/test_corpus.py` | Si el scan de sesiones es lento, reducir fixtures sin eliminar retained-side/head-SHA cases | Tests separados: local, remote, dedup/head compatibility |
| TAP-03 | Unit | `build_orientation_brief` — LLM scan con secciones fijas | `tests/cure_pr_context/test_orient.py` | LLM boundary (mocked) | Output contiene las 5 secciones, instrucciones de uso presentes | Mock `run_llm` que retorna brief predefinido | `pytest tests/cure_pr_context/test_orient.py` | Si el formato cambia, actualizar mock | Un test por sección + test de prompt construction |
| TAP-04 | Unit | `build_pr_context` — integración interna de los 3 módulos | `tests/cure_pr_context/test_init.py` | API pública completa, including explicit `head_sha` parameter | Dict keys, meta values, `head_sha` propagated to corpus, fail-hard en errores, debug artifact paths, `PRIOR_CONTEXT` empty path | `pr_stats` fixture + `head_sha` fixture + mock `gh_fetch` + mock `run_llm` + tmp sandbox/work dirs | `pytest tests/cure_pr_context/test_init.py` | Convertir a integración real si mock se vuelve frágil | Cubre A2, A6, A7 |
| TAP-05 | Integration | Pipeline end-to-end con fixtures deterministas | `tests/cure_pr_context/test_integration.py` | End-to-end: fetch → corpus/head-SHA check → retained-side dedup → orient → build | A1-A10 verificables sin GitHub real, including pruned discussion output and retained past review | Fixtures JSON para las 3 API responses; compatible/incompatible footer SHA bodies; mock LLM; tmp sandbox dirs | `pytest tests/cure_pr_context/test_integration.py` | Añadir más escenarios si fallan en live | Cubre todos los S1-S5 con fixtures |
| TAP-06 | Integration | `$PRIOR_CONTEXT` presente y renderizado en 5 templates built-in | `tests/cure_pr_context/test_templates.py` | `render_prompt` con `extra_vars` | `$PRIOR_CONTEXT` reemplazado correctamente con brief y con `""`; no raw token queda en 5 templates | Templates built-in reales, `extra_vars` siempre con `PRIOR_CONTEXT` | `pytest tests/cure_pr_context/test_templates.py` | Si templates se mueven, actualizar paths | Cubre A6, A8 |
| TAP-07 | Integration | `cure.py` llama `build_pr_context` en el punto correcto y propaga extra vars | `tests/test_cure_pr_flow.py` | `_pr_flow_impl` flow + multipass step helper | Runtime test monkeypatches `compute_pr_stats` and `build_pr_context` and stops after render, proving call order, effective `review_head_sha`, and rendered `PRIOR_CONTEXT`; helper tests cover multipass plan/synth/step extra vars | Mock `build_pr_context`, PR URL sintético, prompt-profile/multipass branch fixtures | `pytest tests/test_cure_pr_flow.py` | Helper seams/monkeypatch cover the flow without a nonexistent generic `--dry-run` (only `--dry-run-chunkhound` exists) | Cubre A7, A8 |
| TAP-08 | Lint/Type | Ruff formatting + mypy type checking | `cure_pr_context/` | Estilo y tipos | Ruff clean, mypy clean | N/A | `ruff check cure_pr_context/ && mypy cure_pr_context/` | N/A | Calidad |
| TAP-09 | Packaging | Installed package contains/imports `cure_pr_context` | `pyproject.toml` + packaging smoke command | setuptools explicit package list / wheel install | `pyproject.toml` includes `cure_pr_context`; `python -c "import cure_pr_context"` succeeds from wheel target | Local wheel built into `.tmp_package_smoke/` | packaging smoke commands above | If wheel tooling unavailable, `pip install -e .` smoke in disposable env | Cubre A11 |

### Acceptance Proof Matrix

| Acceptance ID | Proof Maturity | Proof Method | Reviewer Action | Expected Evidence | Relevant Surfaces | Open Detail |
|--------------|---------------|-------------|-----------------|------------------|------------------|-------------|
| A1 | final | `ls cure_pr_context/` + TAP-05 | Verificar 4 archivos y ejecutar tests | Listado de archivos, tests pasan | `cure_pr_context/` | — |
| A2 | final | TAP-04 + TAP-05 | Ejecutar tests, revisar signature | Tests pasan, dict keys verificados, signature incluye `head_sha`, `gh_fetch` list-capable usado | `__init__.py`, `cure.py` | — |
| A3 | final | TAP-01 | Ejecutar tests + revisar código | Tests de fetch pasan, 3 llamadas mock verificadas | `fetcher.py` | — |
| A4 | final | TAP-02 | Ejecutar tests | Tests de corpus pasan, `sandbox_root` y footer oficial verificados, compatibilidad `head_sha` probada, `past_reviews` retenido y duplicate discussion pruned con fixtures | `corpus.py`, `cure_sessions.py`, `cure_output.py`, `cure.py` | — |
| A5 | final | TAP-03 | Ejecutar tests | Mocked LLM output contiene secciones e instrucciones | `orient.py` | — |
| A6 | final | TAP-04 + TAP-06 | Ejecutar tests | `orientation_brief=""` → `PRIOR_CONTEXT` es `""` y no queda `$PRIOR_CONTEXT` raw | `__init__.py`, templates, `cure_flows.py` | — |
| A7 | final | TAP-07 | Ejecutar tests de flow + revisión de código | Runtime mocked `_pr_flow_impl` proof shows `build_pr_context` called after `compute_pr_stats`, before prompt render, with effective `review_head_sha`; prompt receives rendered `PRIOR_CONTEXT` | `cure.py`, `tests/test_cure_pr_flow.py` | — |
| A8 | final | TAP-06 + TAP-07 + Surface / Branch Proof Matrix | Ejecutar tests + revisar templates | 5 templates built-in contienen `$PRIOR_CONTEXT`; custom/follow-up exclusions documentadas | templates, `cure.py` | — |
| A9 | final | TAP-04 + TAP-05 | Ejecutar tests, verificar archivos escritos | `work/pr_context_discussion.json` existe con discussion pruned y `work/pr_context_past_reviews.json` existe con past reviews retained | `__init__.py`, `work/` | — |
| A10 | final | TAP-01..TAP-05 | Ejecutar `pytest tests/cure_pr_context/` | Todos los tests pasan, coverage ≥ 80% | `tests/cure_pr_context/` | — |
| A11 | final | TAP-09 | Revisar `pyproject.toml`, ejecutar smoke | Package incluido en wheel/install e importable | `pyproject.toml`, wheel smoke | — |

## Critical Files

**Nuevos:**
| Path | Role |
|------|------|
| `cure_pr_context/__init__.py` (new) | API pública `build_pr_context(..., head_sha, ...)`, orquestación de módulos |
| `cure_pr_context/fetcher.py` (new) | `fetch_pr_discussion()` — 3 endpoints GitHub vía `gh_fetch`/`gh_api_list` |
| `cure_pr_context/corpus.py` (new) | `find_past_reviews(..., head_sha)` + dedup Jaccard, usando `sandbox_root`, footers oficiales CURe, compatibilidad de head por prefijo y pruning de discussion duplicada |
| `cure_pr_context/orient.py` (new) | `build_orientation_brief()` — LLM scan |
| `tests/cure_pr_context/test_fetcher.py` (new) | Unit tests fetcher |
| `tests/cure_pr_context/test_corpus.py` (new) | Unit tests corpus |
| `tests/cure_pr_context/test_orient.py` (new) | Unit tests orient |
| `tests/cure_pr_context/test_init.py` (new) | Unit tests `build_pr_context` |
| `tests/cure_pr_context/test_integration.py` (new) | Integration end-to-end |
| `tests/cure_pr_context/test_templates.py` (new) | Template variable injection |

**Modificados:**
| Path | Role |
|------|------|
| `pyproject.toml` | Añadir `cure_pr_context` a `packages` explícitos y habilitar packaging smoke |
| `cure.py` | Insertar `build_pr_context()` call después de `compute_pr_stats`, pasar `head_sha` efectivo, inyectar `$PRIOR_CONTEXT` siempre en `extra_vars`, añadir helper `gh_api_list` |
| `prompts/mrereview_gh_local.md` | Añadir `$PRIOR_CONTEXT` (normal singlepass) |
| `prompts/mrereview_gh_local_big.md` | Añadir `$PRIOR_CONTEXT` (big singlepass cuando multipass está deshabilitado) |
| `prompts/mrereview_gh_local_big_plan.md` | Añadir `$PRIOR_CONTEXT` (multipass plan) |
| `prompts/mrereview_gh_local_big_step.md` | Añadir `$PRIOR_CONTEXT` (multipass step) |
| `prompts/mrereview_gh_local_big_synth.md` | Añadir `$PRIOR_CONTEXT` (multipass synth) |

**Referencia (solo lectura):**
| Path | Role |
|------|------|
| `cure_subsequent_review/github_history.py` (old branch) | Portar lógica de fetch/list helper como orientación |
| `cure_subsequent_review/prior_corpus.py` (old branch) | Portar detección de footers oficiales y scan de sesiones como orientación |

## Implementation Notes

**Orden de implementación (dependencias):**
1. `cure.py::gh_api_list` — portar/ajustar helper list-capable antes de implementar fetcher live
2. `fetcher.py` — usa `gh_fetch`, no tiene dependencias internas, testable aislado
3. `corpus.py` — depende de `fetcher` para recibir discussion events; usa `sandbox_root`, `head_sha` efectivo y footers oficiales actuales
4. `orient.py` — depende de `fetcher` + `corpus` para recibir datos → LLM
5. `__init__.py` — integra los 3, orquesta `build_pr_context(..., head_sha, ...)` y escribe debug artifacts deduplicados en `work_dir`
6. `pyproject.toml` — añadir `cure_pr_context` al package list explícito
7. Templates — añadir `$PRIOR_CONTEXT` a los 5 built-in review templates (paralelo a 1-6)
8. `cure.py` — inyectar la llamada y pasar `head_sha` efectivo (último, cuando el package está listo)

**Red-first seam más pequeño:** `fetcher.py` con mock de `gh_fetch`/`gh_api_list` que retorna arrays.

**Phases:**
- Phase 0: `gh_api_list` + packaging metadata smoke (TAP-09 setup)
- Phase 1: `fetcher.py` + tests (TAP-01) — RED → GREEN
- Phase 2: `corpus.py` + tests (TAP-02) — RED → GREEN
- Phase 3: `orient.py` + tests (TAP-03) — RED → GREEN
- Phase 4: `__init__.py` + tests (TAP-04) — RED → GREEN
- Phase 5: Integration + 5 templates + `cure.py` (TAP-05, TAP-06, TAP-07)
- Phase 6: Ruff + mypy clean (TAP-08), packaging smoke (TAP-09), full test suite

**Constraints:**
- El viejo `github_history.py` usa `DiscussionEvent` dataclass con 15 campos; simplificar a dicts con 6-8 keys
- El viejo `prior_corpus.py` tiene lógica de footer detection ya probada, pero la fuente normativa es el footer actual de CURe (`CURE_REVIEW_FOOTER_START/END` + `sha <short>`)
- `render_prompt` en `cure_flows.py:1437` ya soporta `extra_vars` — no requiere cambios, pero `PRIOR_CONTEXT` debe estar siempre presente en `extra_vars`

## Locked Decisions

Un solo package `cure_pr_context/` con 4 archivos. La API pública es `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm) -> dict`; `sandbox_root` es el root real de sandboxes/sesiones completadas (`paths.sandbox_root`), `work_dir` es el directorio `work/` de la sesión actual para debug artifacts, `pr_stats` es el resultado ya computado por `compute_pr_stats`, `head_sha` es el SHA efectivo de la PR/review que `_pr_flow_impl` pasa explícitamente para compatibilidad de footers remotos, y `gh_fetch` es un callable list-capable basado en `gh_api_list` (no `gh_api_json`). El brief es producido por un solo LLM scan con secciones fijas e instrucciones de uso inline; se inyecta como `$PRIOR_CONTEXT` en los 5 templates built-in de review. `PRIOR_CONTEXT` se pasa siempre en `extra_vars` como `""` o contenido para evitar leaks de tokens crudos. La deduplicación de past reviews usa char n-grams + Jaccard sin dependencias externas; `past_reviews` es el lado retenido y los eventos duplicados se eliminan del `discussion` retornado/escrito/pasado al LLM. El LLM se recibe como `Callable` inyectado desde `cure.py`. Cualquier error aborta la review. Sin cache, sin flags CLI nuevos, sin cambios a `cure_flows.py`.

## Discovery Notes

- El viejo `github_history.py` en `cure-subsequent-pr-review/story-01-intake` tiene ~300 líneas. `collect_pr_discussion()` usa `gh_api_list` (no `gh_api_json`) para los 3 endpoints porque GitHub retorna arrays. El manejo de paginación está en `PaginationMarker`.
- El `gh_api_json` existente (`cure.py:7401-7418`) valida `isinstance(payload, dict)` y falla con arrays. Las 3 APIs de discusión retornan arrays. Se debe crear/portar `gh_api_list` usando el patrón del old branch (`cure.py:7613-7634` en `cure-subsequent-pr-review/story-01-intake`): `gh api --paginate [--slurp]`, fallback sin `--slurp`, flattening de páginas.
- `render_prompt` en `cure_flows.py:1437-1491` soporta `extra_vars: dict[str, str]`, pero solo reemplaza keys presentes; si falta `PRIOR_CONTEXT`, `$PRIOR_CONTEXT` queda literal.
- `_pr_flow_impl` en `cure.py:9334` resuelve `head_sha` desde la API de PR (`cure.py:9371-9375`), `review_head_sha` desde el checkout local (`cure.py:9730-9734`), y computa `pr_stats` en `compute_pr_stats` (`cure.py:4162`). El punto de inyección en `_pr_flow_impl` es después de `progress.flush()` en `detect_pr_size` (~`cure.py:9754-9767`), antes de la selección/routing final singlepass/multipass; debe pasar `review_head_sha or head_sha` como `head_sha` efectivo a `build_pr_context()`.
- CURe escribe footers de review actuales como bloque `<!-- CURE_REVIEW_FOOTER_START -->` / `<!-- CURE_REVIEW_FOOTER_END -->` con línea que incluye `· sha <short>` (`cure_output.py:22`, `cure_output.py:1547-1549`). No usar el formato viejo hipotético `CURe-pr-footer reviewed_head=`.
- `scan_completed_sessions_for_pr` recibe `sandbox_root` (`cure_sessions.py:954-980`) y los defaults viven en `paths.py` como `~/.local/state/cure/sandboxes` (`paths.py:37-38`, `paths.py:75-77`). No diseñar un `sessions_root` separado.
- Los templates built-in de review están en `prompts/`: `mrereview_gh_local.md` (normal singlepass), `mrereview_gh_local_big.md` (big singlepass), `mrereview_gh_local_big_plan.md`, `_big_step.md`, `_big_synth.md`.
- Live code puede usar big singlepass cuando el perfil resuelto es `big` y multipass está deshabilitado (`cure.py:9847-9867`); `prompt_template_name_for_profile` retorna `mrereview_gh_local_big.md` para el perfil `big` (`cure.py:4240`).
- `pyproject.toml:16-18` usa listas explícitas de setuptools (`py-modules = [...]`, `packages = ["prompts"]`), por lo que `cure_pr_context` debe agregarse explícitamente a `packages`.
- `write_pr_context_file` en `cure.py` ya escribe a `work/pr_context.json` — seguir ese patrón para los debug artifacts.
- `PullRequestRef` (`cure.py:2953-2962`) no contiene SHA, y `compute_pr_stats` (`cure.py:4162-4197`) devuelve `head_ref` pero no SHA; por eso `head_sha` debe ser un parámetro explícito de `build_pr_context()` en vez de inferirse desde `pr` o `pr_stats`.
- Live CLI no tiene un `--dry-run` genérico para `cure pr`; el flag relacionado es `--dry-run-chunkhound` (`cure.py:14882`). TAP-07 debe usar monkeypatch/helper seams si necesita un fallback sin ejecutar un review real.

## Implementation Log

- 2026-06-20T08:20:00Z Story claimed and implemented in worktree `/home/vscode/add-worktrees/CURe-simple-pr-context-impl`.
  - Added `cure_pr_context` package (`fetcher`, `corpus`, `orient`, public `build_pr_context`) and setuptools package metadata.
  - Added `cure.py::gh_api_list`, `_pr_flow_impl` context build phase after `compute_pr_stats`, effective `head_sha=review_head_sha or head_sha`, and always-present `PRIOR_CONTEXT` prompt vars for singlepass and multipass plan/step/synth.
  - Added `$PRIOR_CONTEXT` to all 5 built-in review templates and tests for module behavior, templates, flow seams, gh-list decoding, packaging smoke, lint/type checks, and full suite.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (15 passed), `python -m pytest tests/test_reviewflow_unittest.py -q` (433 passed, 13 subtests), `python -m pytest tests/ -q` (635 passed, 13 subtests), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py tests/_reviewflow_unittest_grounding_impl.py`, `mypy cure_pr_context`, and wheel/install import smoke.

- 2026-06-20T17:45:00Z Story resumed after implementation review request-changes.
  - Fixed A4 remote footer trust: `parse_footer_metadata()` now requires a valid non-empty `sha` token inside official footer markers before an event can become a past review; added marker-only footer regression coverage.
  - Fixed fail-hard local session handling: corpus scan validates local `meta.json` parseability/object shape before delegating to `scan_completed_sessions_for_pr`, so corrupt session metadata aborts PR context build.
  - Fixed TAP-07 proof maturity: added a runtime `_pr_flow_impl` monkeypatch test proving `compute_pr_stats` -> `build_pr_context` order, effective `review_head_sha` propagation, and rendered `PRIOR_CONTEXT`; A7 proof row is final.
  - Fixed meta shape: `build_pr_context().meta` now includes `n_comments`, `n_reviews`, and `n_review_comments` alongside aggregate counts; unit/integration tests assert the split.
  - Verification passed: `python -m pytest tests/cure_pr_context tests/test_cure_pr_flow.py -q` (18 passed), `ruff check cure_pr_context tests/cure_pr_context tests/test_cure_pr_flow.py`, and `mypy cure_pr_context`.

## Plan Review Log

- 2026-06-20T06:57:37Z Plan feedback addressed and log compressed by `/openspec-story-plan-resume`
  - Original plan review entries: 2026-06-20T00:00:00Z, 2026-06-20T06:38:04Z, 2026-06-20T06:54:21Z
  - Sections edited: story.md (Scope, Scenarios, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes), proposal.md, design.md, tasks.md, initiative.md
  - Plan lane transition: 🟠 PLAN CHANGES REQUESTED -> 🟡 PLAN DRAFT
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Changes: normalized discussion fetching to list-capable `gh_fetch`/`gh_api_list`; kept `PRIOR_CONTEXT` always present across 5 built-in review templates; clarified dedup ownership so `past_reviews` is retained and duplicate discussion events are pruned from output/debug/LLM input; added explicit `head_sha` to `build_pr_context()` and `_pr_flow_impl` wiring for remote footer compatibility; updated TAP-02/TAP-05/TAP-07 proof obligations and replaced the nonexistent generic `--dry-run` fallback with helper/monkeypatch seams; refreshed initiative-level decisions from the old `sessions_root`/`gh_api_json`/4-template contract.
  - Evidence anchors preserved: `cure.py:7401-7418` (`gh_api_json` dict-only), `cure.py:2953-2962` (`PullRequestRef` has no SHA), `cure.py:4162-4197` (`compute_pr_stats` has no SHA), `cure.py:9371-9375` + `cure.py:9730-9734` (`head_sha`/`review_head_sha` available in `_pr_flow_impl`), `cure.py:4240`/`cure.py:9847-9867` (big singlepass), `cure.py:14882` (`--dry-run-chunkhound` only), `cure_flows.py:1437-1491` (extra-vars replacement only for present keys), `cure_output.py:22`/`cure_output.py:1547-1549` (current footer markers), `cure_sessions.py:954-980` and `paths.py:37-38,75-77` (`sandbox_root`), `pyproject.toml:16-18` (explicit packages list).

- 2026-06-20T07:09:45Z Plan review run by fresh maintainer session
  - Verdict: approve
  - Plan lane transition: 🟡 PLAN DRAFT -> 🟢 PLAN APPROVED
  - Status transition: unchanged: ⚪ TODO -> ⚪ TODO
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative `openspec/initiatives/simple-pr-context/initiative.md`; old branch `cure-subsequent-pr-review/story-01-intake` snippets for `gh_api_list`, `collect_pr_discussion`, and `prior_corpus`; no GitHub/Jira ticket anchor found
  - Traceability: forward complete; backward complete
  - Design trace: complete
  - Code surfaces searched: `cure.py`, `cure_flows.py`, `cure_output.py`, `cure_sessions.py`, `paths.py`, `pyproject.toml`, `prompts/mrereview_gh_local*.md`, `tests/`, old branch `cure_subsequent_review/{github_history.py,prior_corpus.py}`
  - Risk lenses reviewed: external GitHub/subprocess I/O, filesystem/generated artifacts, prompt/template substitution, packaging/install, LLM scan boundary; persistence/cache and UI/TUI excluded by scope
  - Evidence quality: confirmed live source anchors and scaffold shape; inferred none material; unknown no external ticket beyond the recorded old branch reference; provisional A7 live-PR proof remains bounded to implementation review
  - Finding closure: prior plan blockers verified addressed in the active contract (`gh_fetch` list-capable, explicit `head_sha`, retained-side dedup, five-template prompt coverage, TAP-07 helper/monkeypatch fallback)
  - Key findings:
    - No blocking findings. Acceptance A1-A11 are atomic enough for this feature and every A-id maps to TAP/APM proof (`story.md:89-99`, `story.md:193-217`).
    - TAP-07 remains the main implementation hotspot because multipass step prompts are built through `_build_multipass_step_entries` before execution (`cure.py:6417-6451`), but the plan names the branch proof and fallback seam (`story.md:199`).
    - Non-blocking source-fit note: `cure.py` imports the live `compute_pr_stats`, `prompt_template_name_for_profile`, and `render_prompt` bindings from `cure_flows.py` (`cure.py:14712-14723`; `cure_flows.py:316`, `cure_flows.py:388`, `cure_flows.py:1437`); the plan already references `cure_flows.py` in verification/discovery, so no contract edit is required before implementation.
  - Hypothesis triage: none material after source checks
  - Debt Friction: none
  - Next action: `/openspec-story-claim simple-pr-context simple-pr-context` from a fresh session
