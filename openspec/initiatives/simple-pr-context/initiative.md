# Simple PR Context — Discussion & Past Review Orientation

source_of_truth: internal

## Goal / Context

*Second take on the PR-context problem — this time much simpler. The prior `cure-subsequent-pr-review` initiative built a heavy multi-stage pipeline (18 files, semantic pipeline, finding reconciliation, disposition arbitration). This initiative replaces it with a single lightweight orientation scan.*

When `cure pr` runs, the review agent currently sees only the PR description and the diff. It has no awareness of PR discussion (comments, reviews, review comments) or past CURe reviews on the same PR. This leads to repeated analysis of already-resolved areas and missed signals from prior feedback. The `simple-pr-context` initiative adds a lightweight orientation scan: fetch all PR discussion and past CURe reviews, deduplicate them, and pass them through a single LLM call that produces a structured orientation brief. The brief guides the review agent toward problematic areas and away from already-resolved ones — without overwhelming the prompt with raw discussion. "Done" means `cure pr` on any PR produces reviews informed by full discussion context and prior review history, with zero operator flags required.

### Risks / unknowns

- **LLM scan quality**: si el modelo de orientación produce briefs de baja calidad (secciones vacías cuando sí hay señales, o al revés), la feature puede degradar la review en vez de mejorarla. Mitigación: las instrucciones de uso dentro de `$PRIOR_CONTEXT` le dicen al review agent que ignore secciones vacías o irrelevantes.
- **Token budget**: si la discussion es muy larga, el scan de orientación puede ser costoso o exceder la ventana de contexto. Mitigación futura: truncar por cantidad de eventos o longitud total.
- **Falsos positivos en dedup**: el Jaccard ≥ 0.85 puede marcar como duplicado contenido que es similar pero distinto. Mitigación: umbral configurable; `past_reviews` es el lado retenido y el peor caso es prunear un evento de discussion que queda contabilizado en `meta.n_deduped`.

## Story Candidates

1. **`fetcher`** — `fetcher.py`: fetch de 3 endpoints GitHub (issue comments, PR reviews, review comments), normalizar a dicts planos. Simplificar desde el viejo `github_history.py`.
2. **`corpus`** — `corpus.py`: scan de sesiones locales + detección de footers CURe remotos con compatibilidad `head_sha` + retained-side dedup por char n-grams/Jaccard. Basado en el viejo `prior_corpus.py`.
3. **`orient`** — `orient.py`: LLM scan que produce el orientation brief con secciones fijas (Áreas resueltas, Problemáticas, Pendientes, Patrones, Decisiones) + instrucciones de uso inline.
4. **`init + integration`** — `__init__.py` con `build_pr_context(..., head_sha, ...)`, inyección en `cure.py` después de `compute_pr_stats`, fail-hard en errores. Escribir debug artifacts deduplicados a `work/`.
5. **`prompt templates`** — añadir `$PRIOR_CONTEXT` a los 5 templates built-in: normal singlepass, big singlepass, multipass plan, step, synth.
6. **`tests`** — unitarios por módulo + integración del pipeline completo con fixtures deterministas.

## Decisions & Constraints

**Locked-in:**
- Package de 4 archivos bajo `cure_pr_context/` (no 18 archivos como la iniciativa anterior)
- API: `build_pr_context(pr, sandbox_root, work_dir, pr_stats, head_sha, gh_fetch, run_llm) -> dict`; `gh_fetch` es list-capable (`gh_api_list`), no `gh_api_json`
- `head_sha` se pasa explícitamente desde `_pr_flow_impl` (`review_head_sha` si existe, si no PR API `head_sha`) para verificar footers remotos por prefijo
- `$PRIOR_CONTEXT` en los 5 templates built-in de review (normal singlepass, big singlepass, multipass plan, step, synth)
- Fail hard ante cualquier error (GitHub, LLM, archivos corruptos)
- LLM inyectado como `Callable[[str], str]` — sin acoplamiento a configs de `cure.py`
- Sin cache en esta iteración
- Dedup: char n-grams + Jaccard ≥ 0.85, puro stdlib; `past_reviews` retenido, duplicate discussion pruned

**Explícitamente NO parte de esta iniciativa:**
- Multi-stage pipeline, semantic pipeline, disposition arbitration (del viejo subsequent-review)
- Cache o almacenamiento persistente
- Evidencia trusted/untrusted, clasificación de señales
- Cambios de UX o flags nuevos de CLI
- Cambios en `cure_flows.py` más allá de añadir `$PRIOR_CONTEXT` a los templates

## External Resources

- Old initiative branch (historical reference): `cure-subsequent-pr-review/story-01-intake` (38 commits, preserved in this repo)
