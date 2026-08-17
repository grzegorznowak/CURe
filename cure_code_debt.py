"""Bounded, isolated code-debt analysis for CURe review flows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
import html
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Callable, Mapping, Sequence

DEFAULT_CODE_DEBT_MODEL = "gpt-5.6-terra"
DEFAULT_CODE_DEBT_PRESET = "codex-cli"
DEFAULT_MAX_TOKEN_BUDGET = 4_000
DEFAULT_TIMEOUT_SECONDS = 300
MAX_TOKEN_BUDGET = 100_000
MAX_TIMEOUT_SECONDS = 3_600
MAX_WORKERS = 20

TIER_1_METRICS = (
    "debt_ratio", "severity_counts", "cyclomatic_complexity", "duplication_density",
    "comment_todo_density", "test_gap", "dependency_debt",
)
TIER_2_METRICS = (
    "design_architecture", "semantic_smells", "documentation_quality", "test_quality",
    "fowler_quadrant",
)
METRIC_CLUSTERS = (
    "static-computable metrics and hotspot ranking",
    "design, architecture, semantic, and documentation debt",
    "test quality, dependency debt, and remediation prioritization",
)
_CODE_CATEGORIES = {
    "code", "security", "reliability", "maintainability", "architecture", "design",
    "documentation", "test", "testing", "dependency",
}
_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_METRIC_ALIASES = {
    "security": "severity_counts",
    "reliability": "severity_counts",
    "maintainability": "severity_counts",
    "architecture": "design_architecture",
    "design": "design_architecture",
    "documentation": "documentation_quality",
    "test": "test_quality",
    "testing": "test_quality",
    "dependency": "dependency_debt",
}
_FOWLER_QUADRANTS = {
    "deliberate-prudent", "deliberate-reckless",
    "inadvertent-prudent", "inadvertent-reckless",
}
_CODE_FILE_SUFFIXES = {
    ".c", ".cc", ".clj", ".cpp", ".cs", ".css", ".ex", ".exs", ".go", ".h", ".hpp",
    ".html", ".java", ".js", ".jsx", ".kt", ".kts", ".lua", ".m", ".php", ".proto",
    ".py", ".pyi", ".rb", ".rs", ".scala", ".sh", ".sql", ".swift", ".ts", ".tsx",
    ".vue", ".xml", ".yaml", ".yml",
}
_CODE_FILE_NAMES = {"Dockerfile", "Makefile", "CMakeLists.txt"}


@dataclass(frozen=True)
class CodeDebtConfig:
    model_preset: str = DEFAULT_CODE_DEBT_PRESET
    model: str = DEFAULT_CODE_DEBT_MODEL
    max_token_budget: int = DEFAULT_MAX_TOKEN_BUDGET
    metrics: tuple[str, ...] = TIER_1_METRICS
    hotspot_threshold: float = 0.0
    report_output: str = "file"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    grounding_mode: str = "strict"


@dataclass(frozen=True)
class CodeDebtRequest:
    stage: str
    metric_cluster: str
    prompt: str
    model_preset: str
    model: str
    token_budget: int
    timeout_seconds: int
    isolated: bool = True


@dataclass(frozen=True)
class CodeDebtReport:
    findings: list[dict[str, object]] = field(default_factory=list)
    summary: dict[str, object] = field(default_factory=dict)
    estimated_tokens: int = 0
    truncated: bool = False
    notice: str = ""
    worker_count: int = 0
    worker_failures: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        """Render the validated data as an operator-facing report, never a JSON dump."""
        counts = {severity: 0 for severity in _SEVERITY_ORDER}
        quadrants: dict[str, int] = {}
        for finding in self.findings:
            severity = str(finding.get("severity") or "info").lower()
            if severity in counts:
                counts[severity] += 1
            quadrant = str(finding.get("fowler_quadrant") or "").lower()
            if quadrant in _FOWLER_QUADRANTS:
                quadrants[quadrant] = quadrants.get(quadrant, 0) + 1

        summaries = self.summary.get("worker_summaries")
        worker_summaries = [item for item in summaries if isinstance(item, dict)] if isinstance(summaries, list) else []
        debt_ratios = sorted(
            (str(item["debt_ratio_estimate"]) for item in worker_summaries if item.get("debt_ratio_estimate")),
            key=_debt_ratio_sort_key,
            reverse=True,
        )
        hotspots: list[str] = []
        for item in worker_summaries:
            raw_hotspots = item.get("hotspot_top_n")
            if isinstance(raw_hotspots, list):
                for hotspot in raw_hotspots:
                    text = str(hotspot)
                    if text not in hotspots:
                        hotspots.append(text)
        overall_quadrant = "not derivable"
        if quadrants:
            ordered = sorted(quadrants.items(), key=lambda item: (-item[1], item[0]))
            overall_quadrant = ordered[0][0] if len(ordered) == 1 or ordered[0][1] > ordered[1][1] else "mixed"

        lines = ["## Dedicated Code-Debt Analysis", "", "### Overall assessment"]
        if self.worker_failures and not self.findings:
            lines.append(
                "Code-debt analysis failed to produce validated findings; this is not evidence that the codebase is debt-free."
            )
        elif self.findings:
            lines.append(
                f"The analysis identified **{len(self.findings)}** validated code-debt "
                f"finding{'s' if len(self.findings) != 1 else ''}, ordered by severity."
            )
        else:
            lines.append("The analysis completed successfully and found no validated code-debt findings.")
        lines.append(f"- Debt ratio estimate: **{_safe_markdown_inline(debt_ratios[0] if debt_ratios else 'unknown')}**")
        histogram = ", ".join(f"{name.title()}: {counts[name]}" for name in _SEVERITY_ORDER)
        lines.append(f"- Severity histogram: {histogram}")
        lines.append(f"- Overall Fowler classification: **{_safe_markdown_inline(overall_quadrant)}**")
        if hotspots:
            lines.append("- Hotspots:")
            for hotspot in hotspots:
                rationale = next(
                    (str(finding.get("signal")) for finding in self.findings
                     if f"{finding.get('path')}:{finding.get('line')}" == hotspot),
                    "reported by a debt-analysis worker as a priority inspection point",
                )
                lines.append(f"  - `{_safe_markdown_code(hotspot)}` — {_safe_markdown_inline(rationale)}")
        else:
            lines.append("- Hotspots: none validated.")
        if self.notice:
            lines.extend(["", f"> **Notice:** {_safe_markdown_inline(self.notice)}"])
        if self.worker_failures:
            lines.extend(["", "> **Worker failures:**"])
            lines.extend(f"> - {_safe_markdown_inline(failure)}" for failure in self.worker_failures)

        lines.extend(["", "### Code-Related Findings"])
        if not self.findings:
            if self.worker_failures:
                lines.append("- No findings were rendered because the analysis failed or was incomplete.")
            else:
                lines.append("- No validated code-debt findings.")
        for severity in _SEVERITY_ORDER:
            grouped = [item for item in self.findings if str(item.get("severity") or "").lower() == severity]
            if not grouped:
                continue
            lines.extend(["", f"#### {severity.title()}"])
            for finding in grouped:
                path = _safe_markdown_code(finding.get("path", ""))
                line = _safe_markdown_inline(finding.get("line", 0))
                warning = (
                    " ⚠ **Unverified citation (warn mode).**"
                    if finding.get("grounding") == "warning" else ""
                )
                lines.extend(
                    [
                        f"##### `{path}:{line}` — {_safe_markdown_inline(finding.get('signal', 'unspecified debt'))}",
                        f"- Metric: {_safe_markdown_inline(finding.get('metric', 'unspecified'))}",
                        f"- Evidence: {_safe_markdown_inline(finding.get('evidence', 'No evidence supplied.'))}",
                        f"- Remediation estimate: {_safe_markdown_inline(finding.get('remediation_estimate', 'unknown effort'))}",
                        f"- Fowler quadrant: {_safe_markdown_inline(finding.get('fowler_quadrant', 'unclassified'))}",
                        f"- Citation: `{path}:{line}`{warning}",
                    ]
                )
        lines.append("")
        return "\n".join(lines)


def _safe_markdown_inline(value: object) -> str:
    text = re.sub(r"[\r\n\t]+", " ", str(value)).strip()
    escaped = html.escape(text.replace("`", "'"), quote=False)
    for delimiter, entity in (("!", "&#33;"), ("[", "&#91;"), ("]", "&#93;"), ("(", "&#40;"), (")", "&#41;")):
        escaped = escaped.replace(delimiter, entity)
    return escaped


def _debt_ratio_sort_key(value: str) -> tuple[float, str]:
    match = re.match(r"~?(\d+(?:\.\d+)?)%", value)
    return (float(match.group(1)) if match else -1.0, value)


def _safe_markdown_code(value: object) -> str:
    return re.sub(r"[\r\n\t`]+", " ", str(value)).strip()


def _config_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid [code_debt].{name}: expected an integer")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid [code_debt].{name}: expected an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"Invalid [code_debt].{name}: expected {minimum}..{maximum}")
    return parsed


def _config_metrics(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Invalid [code_debt].metrics: expected a non-empty list of Tier 1 metric IDs")
    metrics: list[str] = []
    for item in value:
        if not isinstance(item, str) or item != item.strip() or item not in TIER_1_METRICS:
            raise ValueError("Invalid [code_debt].metrics: entries must be canonical Tier 1 metric IDs")
        if item not in metrics:
            metrics.append(item)
    return tuple(metrics)


def _config_string(value: object, *, name: str, default: str) -> str:
    candidate = default if value is None else value
    if not isinstance(candidate, str) or not candidate.strip() or candidate != candidate.strip():
        raise ValueError(f"Invalid [code_debt].{name}: expected a non-empty single-line string")
    if "\n" in candidate or "\r" in candidate:
        raise ValueError(f"Invalid [code_debt].{name}: expected a non-empty single-line string")
    return candidate


def load_code_debt_config(path: Path, *, env: Mapping[str, str] | None = None) -> CodeDebtConfig:
    """Resolve and strictly validate the always-on ``[code_debt]`` settings."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Invalid code-debt configuration {path}: {exc}") from exc
    section_raw = raw.get("code_debt", {}) if isinstance(raw, dict) else {}
    if not isinstance(section_raw, dict):
        raise ValueError("Invalid [code_debt]: expected a TOML table")
    section = section_raw
    values = env if env is not None else os.environ
    metrics = _config_metrics(section.get("metrics", list(TIER_1_METRICS)))
    budget_raw: object = values.get("CURE_CODE_DEBT_MAX_TOKEN_BUDGET") or section.get(
        "max_token_budget", DEFAULT_MAX_TOKEN_BUDGET
    )
    timeout_raw: object = values.get("CURE_CODE_DEBT_TIMEOUT") or section.get("timeout", DEFAULT_TIMEOUT_SECONDS)
    hotspot_raw = section.get("hotspot_threshold", 0.0)
    if isinstance(hotspot_raw, bool):
        raise ValueError("Invalid [code_debt].hotspot_threshold: expected a number")
    try:
        hotspot = float(hotspot_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid [code_debt].hotspot_threshold: expected a number") from exc
    if not 0.0 <= hotspot <= 1_000_000.0:
        raise ValueError("Invalid [code_debt].hotspot_threshold: expected 0..1000000")
    report_output = str(values.get("CURE_CODE_DEBT_REPORT_OUTPUT") or section.get("report_output") or "file").strip().lower()
    if report_output not in {"file", "stdout"}:
        raise ValueError("Invalid [code_debt].report_output: expected file or stdout")
    grounding_mode = str(values.get("CURE_CODE_DEBT_GROUNDING_MODE") or section.get("grounding_mode") or "strict").strip().lower()
    if grounding_mode != "strict":
        raise ValueError("Invalid [code_debt].grounding_mode: dedicated analysis requires strict")
    budget_name = "CURE_CODE_DEBT_MAX_TOKEN_BUDGET" if values.get("CURE_CODE_DEBT_MAX_TOKEN_BUDGET") else "max_token_budget"
    timeout_name = "CURE_CODE_DEBT_TIMEOUT" if values.get("CURE_CODE_DEBT_TIMEOUT") else "timeout"
    try:
        budget = _config_int(budget_raw, name=budget_name, minimum=1, maximum=MAX_TOKEN_BUDGET)
        timeout = _config_int(timeout_raw, name=timeout_name, minimum=1, maximum=MAX_TIMEOUT_SECONDS)
    except ValueError as exc:
        if str(exc).startswith("Invalid [code_debt].CURE_"):
            raise ValueError(str(exc).replace("Invalid [code_debt].", "Invalid ", 1)) from exc
        raise
    return CodeDebtConfig(
        model_preset=_config_string(
            values.get("CURE_CODE_DEBT_PRESET") or section.get("model_preset"),
            name="model_preset", default=DEFAULT_CODE_DEBT_PRESET,
        ),
        model=_config_string(
            values.get("CURE_CODE_DEBT_MODEL") or section.get("model"),
            name="model", default=DEFAULT_CODE_DEBT_MODEL,
        ),
        max_token_budget=budget,
        metrics=metrics,
        hotspot_threshold=hotspot,
        report_output=report_output,
        timeout_seconds=timeout,
        grounding_mode=grounding_mode,
    )


def code_debt_stage_mode(*, multipass: bool) -> str:
    return "multipass-stage" if multipass else "single-stage-subagent"


def _extract_json(text: str) -> dict[str, object]:
    candidate = text.strip()
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
    try:
        value = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"invalid worker JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        raise ValueError("invalid worker JSON: expected an object with a findings list")
    return value


def _grounding_valid(finding: Mapping[str, object], repo_dir: Path) -> bool:
    path_text = str(finding.get("path") or "").strip()
    line = finding.get("line")
    if not path_text or isinstance(line, bool) or not isinstance(line, int) or line < 1:
        return False
    path = Path(path_text)
    if path.is_absolute():
        return False
    root = repo_dir.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    if not resolved.is_file():
        return False
    try:
        with resolved.open(encoding="utf-8") as stream:
            return any(index == line for index, _ in enumerate(stream, start=1))
    except (OSError, UnicodeError):
        return False


def _is_code_path(path_value: object) -> bool:
    path = Path(str(path_value or ""))
    return path.name in _CODE_FILE_NAMES or path.suffix.lower() in _CODE_FILE_SUFFIXES


def validate_code_debt_findings(
    findings: Sequence[dict[str, object]], *, repo_dir: Path, mode: str,
    enabled_metrics: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    validated: list[dict[str, object]] = []
    normalized_mode = mode if mode in {"strict", "warn"} else "strict"
    allowed = set(enabled_metrics or (*TIER_1_METRICS, *TIER_2_METRICS))
    for original in findings:
        finding = dict(original)
        raw_metric = str(finding.get("metric") or "").strip().lower()
        metric = _METRIC_ALIASES.get(raw_metric, raw_metric)
        if metric not in allowed or not _is_code_path(finding.get("path")):
            continue
        finding["metric"] = metric
        if _grounding_valid(finding, repo_dir):
            validated.append(finding)
        elif normalized_mode == "warn":
            finding["grounding"] = "warning"
            validated.append(finding)
    return validated


def _is_code_finding(finding: Mapping[str, object]) -> bool:
    category = str(finding.get("category") or "").strip().lower()
    severity = str(finding.get("severity") or "").strip().lower()
    metric = str(finding.get("metric") or "").strip()
    raw_signal = finding.get("signal")
    signal = raw_signal.strip() if isinstance(raw_signal, str) else ""
    evidence_raw = finding.get("evidence")
    evidence = evidence_raw.strip() if isinstance(evidence_raw, str) else ""
    quadrant = str(finding.get("fowler_quadrant") or "").strip().lower()
    return (
        category in _CODE_CATEGORIES and severity in _SEVERITIES
        and bool(metric and signal and evidence) and quadrant in _FOWLER_QUADRANTS
    )


def _estimate_tokens(value: object) -> int:
    return max(1, (len(json.dumps(value, sort_keys=True, ensure_ascii=False)) + 3) // 4)


def _validated_worker_summary(raw: object, *, repo_dir: Path, findings: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    hotspots: list[str] = []
    raw_hotspots = raw.get("hotspot_top_n")
    if isinstance(raw_hotspots, list):
        for item in raw_hotspots:
            text = str(item).strip()
            path_text, separator, line_text = text.rpartition(":")
            try:
                line = int(line_text)
            except ValueError:
                continue
            if separator and _grounding_valid({"path": path_text, "line": line}, repo_dir):
                hotspots.append(f"{path_text}:{line}")
    counts = {severity: 0 for severity in _SEVERITIES}
    for finding in findings:
        severity = str(finding.get("severity") or "").lower()
        if severity in counts:
            counts[severity] += 1
    summary: dict[str, object] = {"severity_counts": {k: v for k, v in sorted(counts.items()) if v}}
    if hotspots:
        summary["hotspot_top_n"] = hotspots
    ratio = str(raw.get("debt_ratio_estimate") or "").strip()
    if ratio == "unknown" or re.fullmatch(
        r"~?\d+(?:\.\d+)?%(?: of \d+ changed NCLOC, SQALE [A-E])?", ratio
    ):
        summary["debt_ratio_estimate"] = ratio
    return summary


def build_code_debt_report(
    outputs: Sequence[str], *, repo_dir: Path, grounding_mode: str, max_token_budget: int,
    enabled_metrics: Sequence[str] | None = None,
) -> CodeDebtReport:
    candidates_by_key: dict[tuple[str, ...], list[dict[str, object]]] = {}
    summaries: list[dict[str, object]] = []
    parse_failures: list[str] = []
    allowed = tuple(enabled_metrics or (*TIER_1_METRICS, *TIER_2_METRICS))
    for index, output in enumerate(outputs, start=1):
        try:
            payload = _extract_json(output)
        except ValueError as exc:
            parse_failures.append(f"worker {index}: {exc}")
            continue
        raw_findings = payload.get("findings")
        assert isinstance(raw_findings, list)
        candidates = [
            dict(item) for item in raw_findings if isinstance(item, dict) and _is_code_finding(item)
        ]
        worker_findings = validate_code_debt_findings(
            candidates, repo_dir=repo_dir, mode=grounding_mode, enabled_metrics=allowed
        )
        summary = _validated_worker_summary(payload.get("summary"), repo_dir=repo_dir, findings=worker_findings)
        if summary:
            summaries.append(summary)
        for finding in worker_findings:
            key = tuple(str(finding.get(field) or "") for field in ("path", "line", "metric", "signal"))
            candidates_by_key.setdefault(key, []).append(finding)

    def conflict_rank(item: Mapping[str, object]) -> tuple[object, ...]:
        return (
            -_SEVERITY_ORDER.get(str(item.get("severity") or "").lower(), 5),
            len(str(item.get("evidence") or "")),
            json.dumps(item, sort_keys=True, ensure_ascii=False),
        )

    findings = [max(group, key=conflict_rank) for _, group in sorted(candidates_by_key.items())]
    summaries.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))

    def line_value(item: Mapping[str, object]) -> int:
        value = item.get("line")
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    findings.sort(key=lambda item: (
        _SEVERITY_ORDER.get(str(item.get("severity")).lower(), 5), str(item.get("path")), line_value(item)
    ))
    summary_payload: dict[str, object] = {"worker_summaries": summaries}
    budget = max(1, max_token_budget)
    truncated = False
    while summaries and _estimate_tokens({"findings": findings, "summary": summary_payload}) > budget:
        summaries.pop()
        truncated = True
    while findings and _estimate_tokens({"findings": findings, "summary": summary_payload}) > budget:
        findings.pop()
        truncated = True
    if _estimate_tokens({"findings": findings, "summary": summary_payload}) > budget:
        summary_payload = {"status": "summary omitted to honor token budget"}
        truncated = True
    notice = "Code-debt output truncated at the configured token budget." if truncated else ""
    estimate = min(budget, _estimate_tokens({"findings": findings, "summary": summary_payload, "notice": notice}))
    return CodeDebtReport(
        findings=findings, summary=summary_payload, estimated_tokens=estimate,
        truncated=truncated, notice=notice, worker_failures=tuple(sorted(parse_failures)),
    )


def _prompt_text() -> str:
    return (Path(__file__).with_name("prompts") / "code_debt_analysis.md").read_text(encoding="utf-8")


def _request(
    *, config: CodeDebtConfig, stage: str, cluster: str,
    plan: Mapping[str, object] | None, token_budget: int,
) -> CodeDebtRequest:
    prompt = _prompt_text().replace("$METRIC_CLUSTER", cluster).replace("$TOKEN_BUDGET", str(token_budget))
    prompt = prompt.replace("$REVIEW_PLAN", json.dumps(plan or {}, sort_keys=True))
    prompt = prompt.replace("$HOTSPOT_THRESHOLD", str(config.hotspot_threshold))
    prompt = prompt.replace("$ENABLED_METRICS", ", ".join(config.metrics))
    return CodeDebtRequest(
        stage=stage, metric_cluster=cluster, prompt=prompt, model_preset=config.model_preset,
        model=config.model, token_budget=token_budget, timeout_seconds=config.timeout_seconds,
    )


def _run_with_bounded_retry(request: CodeDebtRequest, analyzer: Callable[[CodeDebtRequest], str]) -> str:
    allocation = max(1, request.token_budget)
    first_budget = max(1, allocation // 2)
    first = replace(request, token_budget=first_budget)
    try:
        return analyzer(first)
    except Exception:
        retry_budget = allocation - first_budget
        if retry_budget < 1:
            raise
        return analyzer(replace(request, token_budget=retry_budget))


def run_code_debt_stage(
    *, config: CodeDebtConfig, repo_dir: Path, plan: Mapping[str, object],
    analyzer: Callable[[CodeDebtRequest], str], worker_count: int = 4,
) -> CodeDebtReport:
    """Run isolated metric clusters in parallel; errors fail open after one bounded retry."""
    active_count = min(len(METRIC_CLUSTERS), config.max_token_budget)
    clusters = METRIC_CLUSTERS[:active_count]
    workers = min(max(1, worker_count), len(clusters), MAX_WORKERS)
    quotient, remainder = divmod(config.max_token_budget, len(clusters))
    allocations = [quotient + (1 if index < remainder else 0) for index in range(len(clusters))]
    requests = [
        _request(config=config, stage="multipass-code-debt", cluster=cluster, plan=plan, token_budget=allocation)
        for cluster, allocation in zip(clusters, allocations, strict=True)
    ]
    indexed_outputs: dict[int, str] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cure-code-debt") as executor:
        futures = {
            executor.submit(_run_with_bounded_retry, request, analyzer): (index, request)
            for index, request in enumerate(requests)
        }
        for future in as_completed(futures):
            index, request = futures[future]
            try:
                indexed_outputs[index] = future.result()
            except Exception as exc:
                failures.append(f"{request.metric_cluster}: {exc}")
    outputs = [indexed_outputs[index] for index in sorted(indexed_outputs)]
    report = build_code_debt_report(
        outputs, repo_dir=repo_dir, grounding_mode=config.grounding_mode,
        max_token_budget=config.max_token_budget,
        enabled_metrics=(*config.metrics, *TIER_2_METRICS),
    )
    return replace(
        report, worker_count=workers,
        worker_failures=tuple(sorted((*report.worker_failures, *failures))),
    )


def run_code_debt_subagent(
    *, config: CodeDebtConfig, repo_dir: Path, analyzer: Callable[[CodeDebtRequest], str]
) -> CodeDebtReport:
    request = _request(
        config=config, stage="single-stage-subagent",
        cluster="all enabled code-debt metrics; report code-related issues only",
        plan=None, token_budget=config.max_token_budget,
    )
    failures: tuple[str, ...] = ()
    try:
        output = _run_with_bounded_retry(request, analyzer)
    except Exception as exc:
        output = "{}"
        failures = (f"subagent failed after bounded retry: {exc}",)
    report = build_code_debt_report(
        [output], repo_dir=repo_dir, grounding_mode=config.grounding_mode,
        max_token_budget=config.max_token_budget,
        enabled_metrics=(*config.metrics, *TIER_2_METRICS),
    )
    return replace(report, worker_count=1, worker_failures=tuple(sorted((*report.worker_failures, *failures))))
