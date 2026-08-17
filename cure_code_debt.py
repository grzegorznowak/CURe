"""Bounded, isolated code-debt analysis for CURe review flows."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import tomllib
from typing import Callable, Mapping, Sequence

DEFAULT_CODE_DEBT_MODEL = "gpt-5.6-terra"
DEFAULT_CODE_DEBT_PRESET = "codex-cli"
DEFAULT_MAX_TOKEN_BUDGET = 4_000
DEFAULT_TIMEOUT_SECONDS = 300
MAX_WORKERS = 20

TIER_1_METRICS = (
    "debt_ratio",
    "severity_counts",
    "cyclomatic_complexity",
    "duplication_density",
    "comment_todo_density",
    "test_gap",
    "dependency_debt",
)
TIER_2_METRICS = (
    "design_architecture",
    "semantic_smells",
    "documentation_quality",
    "test_quality",
    "fowler_quadrant",
)
METRIC_CLUSTERS = (
    "static-computable metrics and hotspot ranking",
    "design, architecture, semantic, and documentation debt",
    "test quality, dependency debt, and remediation prioritization",
)
_CODE_CATEGORIES = {
    "code",
    "security",
    "reliability",
    "maintainability",
    "architecture",
    "design",
    "documentation",
    "test",
    "testing",
    "dependency",
}
_SEVERITIES = {"critical", "high", "medium", "low", "info"}


@dataclass(frozen=True)
class CodeDebtConfig:
    enabled: bool = False
    model_preset: str = DEFAULT_CODE_DEBT_PRESET
    model: str = DEFAULT_CODE_DEBT_MODEL
    max_token_budget: int = DEFAULT_MAX_TOKEN_BUDGET
    metrics: tuple[str, ...] = TIER_1_METRICS
    hotspot_threshold: float = 0.0
    report_output: str = "file"
    subagent_mode: str = "stage"
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
        lines = ["## Dedicated Code-Debt Analysis", ""]
        if self.notice:
            lines.extend([f"> {self.notice}", ""])
        lines.extend(["### Code-Related Findings"])
        if not self.findings:
            lines.append("- None.")
        for finding in self.findings:
            lines.append(
                "- [{severity}] {signal} ({metric}; {estimate}; {quadrant}). "
                "Sources: `{path}:{line}`".format(
                    severity=str(finding.get("severity", "info")).upper(),
                    signal=finding.get("signal", "unspecified debt"),
                    metric=finding.get("metric", "unspecified"),
                    estimate=finding.get("remediation_estimate", "unknown effort"),
                    quadrant=finding.get("fowler_quadrant", "unclassified"),
                    path=finding.get("path", ""),
                    line=finding.get("line", 0),
                )
            )
        lines.extend(["", "### Summary", f"- {json.dumps(self.summary, sort_keys=True)}", ""])
        return "\n".join(lines)


def _env_bool(value: str, default: bool) -> bool:
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def load_code_debt_config(path: Path, *, env: Mapping[str, str] | None = None) -> CodeDebtConfig:
    """Resolve ``[code_debt]`` plus focused ``CURE_CODE_DEBT_*`` overrides."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    section = raw.get("code_debt", {}) if isinstance(raw, dict) else {}
    section = section if isinstance(section, dict) else {}
    values = env if env is not None else os.environ

    metrics_raw = section.get("metrics", TIER_1_METRICS)
    metrics = tuple(str(item).strip() for item in metrics_raw if str(item).strip()) if isinstance(metrics_raw, list) else TIER_1_METRICS
    configured_enabled = section.get("enabled")
    cfg = CodeDebtConfig(
        enabled=configured_enabled if isinstance(configured_enabled, bool) else False,
        model_preset=str(section.get("model_preset") or DEFAULT_CODE_DEBT_PRESET).strip(),
        model=str(section.get("model") or DEFAULT_CODE_DEBT_MODEL).strip(),
        max_token_budget=max(1, int(section.get("max_token_budget", DEFAULT_MAX_TOKEN_BUDGET))),
        metrics=metrics,
        hotspot_threshold=float(section.get("hotspot_threshold", 0.0)),
        report_output=str(section.get("report_output") or "file").strip().lower(),
        subagent_mode=str(section.get("subagent_mode") or "stage").strip().lower(),
        timeout_seconds=max(1, int(section.get("timeout", DEFAULT_TIMEOUT_SECONDS))),
        grounding_mode=str(section.get("grounding_mode") or "strict").strip().lower(),
    )
    return replace(
        cfg,
        enabled=(
            _env_bool(values["CURE_CODE_DEBT_ENABLED"], cfg.enabled)
            if "CURE_CODE_DEBT_ENABLED" in values
            else cfg.enabled
        ),
        model_preset=values.get("CURE_CODE_DEBT_PRESET", "").strip() or cfg.model_preset,
        model=values.get("CURE_CODE_DEBT_MODEL", "").strip() or cfg.model,
        report_output=values.get("CURE_CODE_DEBT_REPORT_OUTPUT", "").strip() or cfg.report_output,
        subagent_mode=values.get("CURE_CODE_DEBT_SUBAGENT_MODE", "").strip() or cfg.subagent_mode,
        grounding_mode=values.get("CURE_CODE_DEBT_GROUNDING_MODE", "").strip() or cfg.grounding_mode,
        max_token_budget=(
            max(1, int(values["CURE_CODE_DEBT_MAX_TOKEN_BUDGET"]))
            if values.get("CURE_CODE_DEBT_MAX_TOKEN_BUDGET", "").strip()
            else cfg.max_token_budget
        ),
        timeout_seconds=(
            max(1, int(values["CURE_CODE_DEBT_TIMEOUT"]))
            if values.get("CURE_CODE_DEBT_TIMEOUT", "").strip()
            else cfg.timeout_seconds
        ),
    )


def code_debt_stage_mode(*, config: CodeDebtConfig, multipass: bool) -> str:
    if not config.enabled:
        return "disabled"
    return "multipass-stage" if multipass else "single-stage-subagent"


def _extract_json(text: str) -> dict[str, object]:
    candidate = text.strip()
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
    try:
        value = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def validate_code_debt_findings(
    findings: Sequence[dict[str, object]], *, repo_dir: Path, mode: str
) -> list[dict[str, object]]:
    validated: list[dict[str, object]] = []
    normalized_mode = mode if mode in {"strict", "warn", "off"} else "strict"
    for original in findings:
        finding = dict(original)
        if normalized_mode == "off" or _grounding_valid(finding, repo_dir):
            validated.append(finding)
        elif normalized_mode == "warn":
            finding["grounding"] = "warning"
            validated.append(finding)
    return validated


def _is_code_finding(finding: Mapping[str, object]) -> bool:
    category = str(finding.get("category") or "").strip().lower()
    severity = str(finding.get("severity") or "").strip().lower()
    metric = str(finding.get("metric") or "").strip()
    signal = str(finding.get("signal") or "").strip()
    return category in _CODE_CATEGORIES and severity in _SEVERITIES and bool(metric and signal)


def _estimate_tokens(value: object) -> int:
    return max(1, (len(json.dumps(value, sort_keys=True, ensure_ascii=False)) + 3) // 4)


def build_code_debt_report(
    outputs: Sequence[str], *, repo_dir: Path, grounding_mode: str, max_token_budget: int
) -> CodeDebtReport:
    findings: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for output in outputs:
        payload = _extract_json(output)
        raw_summary = payload.get("summary")
        if isinstance(raw_summary, dict):
            summaries.append(dict(raw_summary))
        raw_findings = payload.get("findings")
        if not isinstance(raw_findings, list):
            continue
        candidates = [dict(item) for item in raw_findings if isinstance(item, dict) and _is_code_finding(item)]
        for finding in validate_code_debt_findings(candidates, repo_dir=repo_dir, mode=grounding_mode):
            key = (finding.get("path"), finding.get("line"), finding.get("metric"), finding.get("signal"))
            if key not in seen:
                seen.add(key)
                findings.append(finding)

    def _line_sort_value(item: Mapping[str, object]) -> int:
        value = item.get("line")
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    findings.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(str(item.get("severity")).lower(), 5), str(item.get("path")), _line_sort_value(item)))
    summary: dict[str, object] = {"worker_summaries": summaries}
    budget = max(1, max_token_budget)
    truncated = False
    while findings and _estimate_tokens({"findings": findings, "summary": summary}) > budget:
        findings.pop()
        truncated = True
    if _estimate_tokens({"findings": findings, "summary": summary}) > budget:
        summary = {"status": "summary omitted to honor token budget"}
        truncated = True
    notice = "Code-debt output truncated at the configured token budget." if truncated else ""
    estimate = min(budget, _estimate_tokens({"findings": findings, "summary": summary, "notice": notice}))
    return CodeDebtReport(
        findings=findings,
        summary=summary,
        estimated_tokens=estimate,
        truncated=truncated,
        notice=notice,
    )


def _prompt_text() -> str:
    return (Path(__file__).with_name("prompts") / "code_debt_analysis.md").read_text(encoding="utf-8")


def _request(
    *, config: CodeDebtConfig, stage: str, cluster: str, plan: Mapping[str, object] | None, token_budget: int
) -> CodeDebtRequest:
    prompt = _prompt_text().replace("$METRIC_CLUSTER", cluster).replace("$TOKEN_BUDGET", str(token_budget))
    prompt = prompt.replace("$REVIEW_PLAN", json.dumps(plan or {}, sort_keys=True))
    prompt = prompt.replace("$HOTSPOT_THRESHOLD", str(config.hotspot_threshold))
    prompt = prompt.replace("$ENABLED_METRICS", ", ".join(config.metrics))
    return CodeDebtRequest(
        stage=stage,
        metric_cluster=cluster,
        prompt=prompt,
        model_preset=config.model_preset,
        model=config.model,
        token_budget=token_budget,
        timeout_seconds=config.timeout_seconds,
    )


def run_code_debt_stage(
    *,
    config: CodeDebtConfig,
    repo_dir: Path,
    plan: Mapping[str, object],
    analyzer: Callable[[CodeDebtRequest], str],
    worker_count: int = 4,
) -> CodeDebtReport:
    """Run isolated metric clusters in parallel; worker errors fail open after one retry."""
    clusters = METRIC_CLUSTERS
    workers = min(max(1, worker_count), len(clusters), MAX_WORKERS)
    share = max(1, config.max_token_budget // len(clusters))
    requests = [_request(config=config, stage="multipass-code-debt", cluster=cluster, plan=plan, token_budget=share) for cluster in clusters]
    outputs: list[str] = []
    failures: list[str] = []

    def run_with_retry(request: CodeDebtRequest) -> str:
        try:
            return analyzer(request)
        except Exception:
            return analyzer(request)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cure-code-debt") as executor:
        futures = {executor.submit(run_with_retry, request): request for request in requests}
        for future in as_completed(futures):
            try:
                outputs.append(future.result())
            except Exception as exc:
                failures.append(f"{futures[future].metric_cluster}: {exc}")
    report = build_code_debt_report(outputs, repo_dir=repo_dir, grounding_mode=config.grounding_mode, max_token_budget=config.max_token_budget)
    return replace(report, worker_count=workers, worker_failures=tuple(failures))


def run_code_debt_subagent(
    *, config: CodeDebtConfig, repo_dir: Path, analyzer: Callable[[CodeDebtRequest], str]
) -> CodeDebtReport:
    request = _request(
        config=config,
        stage="single-stage-subagent",
        cluster="all enabled code-debt metrics; report code-related issues only",
        plan=None,
        token_budget=config.max_token_budget,
    )
    failures: tuple[str, ...] = ()
    try:
        output = analyzer(request)
    except Exception as exc:
        try:
            output = analyzer(request)
        except Exception as retry_exc:
            output = "{}"
            failures = (f"subagent failed: {exc}; retry failed: {retry_exc}",)
    report = build_code_debt_report([output], repo_dir=repo_dir, grounding_mode=config.grounding_mode, max_token_budget=config.max_token_budget)
    return replace(report, worker_count=1, worker_failures=failures)
