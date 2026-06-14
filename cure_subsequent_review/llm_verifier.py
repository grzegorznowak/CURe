"""LLM-backed source verifier for subsequent-review prior findings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cure_subsequent_review.contracts import SourceState
from cure_subsequent_review.source_truth import FindingVerificationRequest, FindingVerificationResult

VerifierLlm = Callable[[str], str | dict[str, Any]]
ChunkhoundResearch = Callable[[str], str]

_REF_RE = re.compile(r"(?P<path>[^\s:]+):(?P<line>\d+)")
_CONTEXT_RADIUS = 20


def _strip_fenced_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(_strip_fenced_json(str(raw)))
    if not isinstance(parsed, dict):
        raise ValueError("finding verifier response must be a JSON object")
    return parsed


def _source_state(value: object, *, final_pass: bool = False) -> SourceState | str:
    text = str(value or "").strip().lower()
    if text == "need_more_context" and not final_pass:
        return "need_more_context"
    try:
        state = SourceState(text)
    except ValueError:
        return SourceState.STILL_OPEN if final_pass else SourceState.SOURCE_UNKNOWN
    if final_pass and state in {SourceState.SOURCE_UNKNOWN, SourceState.NOT_VERIFIABLE}:
        return SourceState.STILL_OPEN
    return state


def _citations(value: object, *, source_contexts: tuple[dict[str, Any], ...] = ()) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    citations: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        citation: dict[str, Any] = {"path": path}
        line = item.get("line")
        if isinstance(line, int):
            citation["line"] = line
        elif str(line or "").strip().isdigit():
            citation["line"] = int(str(line).strip())
        if source_contexts and not _citation_in_contexts(citation, source_contexts):
            continue
        summary = str(item.get("summary") or "").strip()
        if summary:
            citation["summary"] = summary
        citations.append(citation)
    return tuple(citations)


def _citation_in_contexts(citation: dict[str, Any], contexts: tuple[dict[str, Any], ...]) -> bool:
    path = str(citation.get("path") or "").strip()
    line = citation.get("line")
    if not isinstance(line, int):
        return False
    for context in contexts:
        if str(context.get("path") or "").strip() != path:
            continue
        start = int(context.get("start_line") or context.get("line") or 0)
        end = int(context.get("end_line") or context.get("line") or 0)
        if start <= line <= end:
            return True
    return False


def _normalize_verifier_result(
    *,
    payload: dict[str, Any],
    contexts: tuple[dict[str, Any], ...],
    final_pass: bool = False,
) -> tuple[SourceState | str, tuple[dict[str, Any], ...], tuple[str, ...]]:
    state = _source_state(payload.get("source_state"), final_pass=final_pass)
    citations = _citations(payload.get("citations"), source_contexts=contexts)
    if isinstance(state, SourceState) and state is SourceState.RESOLVED_FROM_SOURCE and not citations:
        return SourceState.NOT_VERIFIABLE if not final_pass else SourceState.STILL_OPEN, (), ("unsupported_verifier_citations",)
    return state, citations, ()


def _safe_child(root: Path, raw_path: str) -> Path | None:
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def _imported_names(raw_names: str, *, lines: list[str], start_index: int) -> tuple[set[str], int]:
    names_fragments: list[str] = []
    text = raw_names
    index = start_index
    if "(" in text:
        text = text.split("(", 1)[1]
        while True:
            before_close, separator, _after_close = text.partition(")")
            names_fragments.append(before_close)
            if separator:
                break
            index += 1
            if index >= len(lines):
                break
            text = lines[index]
    else:
        names_fragments.append(text)

    imported: set[str] = set()
    for fragment in ",".join(names_fragments).split(","):
        name = fragment.split("#", 1)[0].strip().strip("()")
        if not name:
            continue
        imported.add(name.rsplit(" as ", 1)[-1].strip())
    return imported, index


def _inactive_binding_reason(*, repo_dir: Path, path_text: str, line: int, lines: list[str]) -> str | None:
    definition_name: str | None = None
    definition_line = 0
    for index in range(min(line, len(lines)), 0, -1):
        match = re.match(
            r"\s*(?:async\s+def|def|class)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b",
            lines[index - 1],
        )
        if match is not None:
            definition_name = match.group("name")
            definition_line = index
            break
    if not definition_name:
        return None
    import_pattern = re.compile(r"^\s*from\s+(?P<module>[A-Za-z_][A-Za-z0-9_\.]+)\s+import\s+(?P<names>.*)$")
    index = definition_line
    while index < len(lines):
        match = import_pattern.match(lines[index])
        if match is None:
            index += 1
            continue
        imported_names, index = _imported_names(match.group("names"), lines=lines, start_index=index)
        if definition_name in imported_names:
            module_path = repo_dir.joinpath(*match.group("module").split(".")).with_suffix(".py")
            if module_path.is_file() and module_path.name != Path(path_text).name:
                return f"inactive_source_reference_active_binding:{definition_name}:{module_path.relative_to(repo_dir)}"
            return f"inactive_source_reference_active_binding:{definition_name}"
        index += 1
    return None


def _read_context(repo_dir: Path, ref: str) -> tuple[dict[str, Any] | None, str | None]:
    match = _REF_RE.search(ref)
    if match is None:
        return None, "evidence_reference_unparseable"
    path_text = match.group("path")
    line = int(match.group("line"))
    path = _safe_child(repo_dir, path_text)
    if path is None or not path.is_file():
        return None, "evidence_reference_missing"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if line < 1 or line > len(lines):
        return None, "evidence_reference_missing"
    inactive_reason = _inactive_binding_reason(repo_dir=repo_dir, path_text=path_text, line=line, lines=lines)
    if inactive_reason is not None:
        return None, inactive_reason
    start = max(1, line - _CONTEXT_RADIUS)
    end = min(len(lines), line + _CONTEXT_RADIUS)
    context_lines = []
    for number in range(start, end + 1):
        prefix = ">" if number == line else " "
        context_lines.append(f"{prefix}{number}: {lines[number - 1]}")
    return {
        "ref": ref,
        "path": path_text,
        "line": line,
        "start_line": start,
        "end_line": end,
        "context": "\n".join(context_lines),
    }, None


def _prompt(
    *,
    request: FindingVerificationRequest,
    source_contexts: tuple[dict[str, Any], ...],
    chunkhound_research: str | None = None,
    final_pass: bool = False,
) -> str:
    allowed_states = "resolved_from_source or still_open" if final_pass else "resolved_from_source, still_open, or need_more_context"
    payload = {
        "group_id": request.group_id,
        "canonical_id": request.canonical_id,
        "finding_ids": list(request.finding_ids),
        "title": request.title,
        "severity": request.severity,
        "section": request.section,
        "source_evidence_snippets": list(request.source_evidence_snippets),
        "reviewed_heads": list(request.reviewed_heads),
        "pr_files_changed": list(getattr(request, "pr_files_changed", ()) or ()),
        "discussion_signals": list(getattr(request, "discussion_signals", ()) or ()),
        "source_contexts": list(source_contexts),
    }
    if chunkhound_research is not None:
        payload["chunkhound_research"] = chunkhound_research
    return (
        "Verify whether a prior PR review finding is resolved in the current source. "
        "Use only current source evidence as source truth; discussion/human claims are context only. "
        f"Return strict JSON with source_state ({allowed_states}), rationale, and citations array "
        "with path, line, summary.\n\n"
        f"Verification input JSON:\n{json.dumps(payload, indent=2, sort_keys=True)}\n"
    )


@dataclass(frozen=True)
class LlmFindingVerifier:
    """Production ``FindingVerifier`` using direct source context plus optional research."""

    repo_dir: Path
    llm: VerifierLlm
    chunkhound_research: ChunkhoundResearch | None = None

    def __call__(self, request: FindingVerificationRequest) -> FindingVerificationResult:
        contexts: list[dict[str, Any]] = []
        missing_reasons: list[str] = []
        for ref in request.source_evidence_snippets:
            context, reason = _read_context(self.repo_dir, ref)
            if context is None:
                if reason is not None:
                    missing_reasons.append(reason)
                continue
            contexts.append(context)
        if not contexts:
            return FindingVerificationResult(
                source_state=SourceState.NOT_VERIFIABLE,
                unavailable_reasons=tuple(dict.fromkeys(missing_reasons or ["evidence_reference_missing"])),
                rationale="no source evidence references could be read from the current repository",
                provenance={"verifier": "llm_finding_verifier"},
            )

        source_contexts = tuple(contexts)
        first_payload = _payload(self.llm(_prompt(request=request, source_contexts=source_contexts)))
        first_state, first_citations, first_unavailable = _normalize_verifier_result(
            payload=first_payload,
            contexts=source_contexts,
        )
        if first_state != "need_more_context":
            assert isinstance(first_state, SourceState)
            return FindingVerificationResult(
                source_state=first_state,
                current_source_citations=first_citations,
                unavailable_reasons=first_unavailable,
                rationale=str(first_payload.get("rationale") or "").strip(),
                provenance={"verifier": "llm_finding_verifier", "chunkhound_research": "not_needed"},
            )

        research_text = ""
        if self.chunkhound_research is not None:
            query = f"Verify subsequent-review finding {request.group_id} {request.title or ''} against current source"
            research_text = self.chunkhound_research(query)
        second_payload = _payload(
            self.llm(
                _prompt(
                    request=request,
                    source_contexts=source_contexts,
                    chunkhound_research=research_text,
                    final_pass=True,
                )
            )
        )
        second_state, second_citations, second_unavailable = _normalize_verifier_result(
            payload=second_payload,
            contexts=source_contexts,
            final_pass=True,
        )
        assert isinstance(second_state, SourceState)
        return FindingVerificationResult(
            source_state=second_state,
            current_source_citations=second_citations,
            unavailable_reasons=second_unavailable,
            rationale=str(second_payload.get("rationale") or first_payload.get("rationale") or "").strip(),
            provenance={
                "verifier": "llm_finding_verifier",
                "chunkhound_research": "used" if self.chunkhound_research is not None else "unavailable",
            },
        )


__all__ = ["ChunkhoundResearch", "LlmFindingVerifier", "VerifierLlm"]
