import contextlib
import argparse
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cure as rf  # noqa: E402
import cure  # noqa: E402
import cure_commands  # noqa: E402
import cure_flows  # noqa: E402
import cure_llm  # noqa: E402
import cure_output  # noqa: E402
import cure_runtime  # noqa: E402
import chunkhound_summary  # noqa: E402
import ui as rui  # noqa: E402


__all__ = [
    "Any",
    "Path",
    "ROOT",
    "StringIO",
    "_review_intelligence_cfg",
    "_review_intelligence_meta",
    "_sectioned_review_markdown",
    "_verdicts",
    "argparse",
    "chunkhound_summary",
    "contextlib",
    "cure",
    "cure_commands",
    "cure_flows",
    "cure_llm",
    "cure_output",
    "cure_runtime",
    "datetime",
    "inspect",
    "json",
    "mock",
    "os",
    "re",
    "rf",
    "rui",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "timezone",
    "tomllib",
    "unittest",
]


def _verdicts(business: str, technical: str | None = None) -> rf.ReviewVerdicts:
    return rf.ReviewVerdicts(
        business=business,
        technical=(technical if technical is not None else business),
    )


def _sectioned_review_markdown(*, business: str, technical: str) -> str:
    return "\n".join(
        [
            "**Summary**: ok",
            "",
            "## Business / Product Assessment",
            f"**Verdict**: {business}",
            "",
            "### Strengths",
            "- Business strength",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            f"**Verdict**: {technical}",
            "",
            "### Strengths",
            "- Technical strength",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "### Reusability",
            "- None.",
            "",
        ]
    )


def _review_intelligence_cfg(
    *,
    notes: tuple[str, ...] = (),
    github_mode: str | None = "auto",
    jira_mode: str | None = "when-referenced",
    extra_sources: tuple[tuple[str, str], ...] = (),
) -> rf.ReviewIntelligenceConfig:
    sources: list[rf.ReviewIntelligenceSource] = []
    if github_mode is not None:
        sources.append(rf.ReviewIntelligenceSource(name="github", mode=github_mode))
    if jira_mode is not None:
        sources.append(rf.ReviewIntelligenceSource(name="jira", mode=jira_mode))
    for name, mode in extra_sources:
        sources.append(rf.ReviewIntelligenceSource(name=name, mode=mode))
    return rf.ReviewIntelligenceConfig(notes=tuple(notes), sources=tuple(sources))


def _review_intelligence_meta(cfg: rf.ReviewIntelligenceConfig) -> dict[str, object]:
    return {
        "review_intelligence": {
            "notes": list(cfg.notes),
            "sources": [
                {
                    "name": source.name,
                    "mode": source.mode,
                    "notes": list(source.notes),
                }
                for source in cfg.sources
            ],
        }
    }
