# Design: story-05-subsequent-review-runtime-hardening-after-live-audit

## Decisions

- DA row coverage is still required for provenance, report-governor audit, and debugging.
- Ordinary review consumers should not be forced to read a top-level `### Internal DA coverage` section. The preferred shape is human issue history in the visible report plus DA coverage in an audit artifact, appendix, metadata, comment, or hidden/collapsible audit-only block.
- Cache replay must be conservative: stable identity mismatch or missing identity proof means re-run the verifier/linker.
- Source truth requires inspected source-context citations; LLM-returned paths are not trusted unless constrained to inspected contexts.
- Authority classification must not derive trusted roles from untrusted comment body text.

## Open Design Questions

- Should DA coverage be artifact-only, appendix, or collapsible markdown in `review.md`? Product preference currently favors removing it from the ordinary visible body while preserving audit access.
- What is the minimal stable identity digest that can be shared by memory replay and linker cache replay: origin key, fingerprint, source refs, corpus entry, or a combined group digest?
- Should planner abort with prior-review context publish a synthetic guarded review, or fail/degrade before publication?


## Superseded design note

The design decisions above are preserved as historical live-audit notes. They are not a standalone active design contract after the remap. Runtime/report/memory/linker design belongs to Story 04; intake/path/parser identity support belongs to Story 01; source-truth and authority invariants belong to Story 03.
