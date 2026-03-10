from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


SECRET_KEYS = {
    "api_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
}


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner_value in value.items():
            if key in SECRET_KEYS:
                redacted[key] = "REDACTED"
            else:
                redacted[key] = _redact_secrets(inner_value)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def json_fingerprint(path: Path) -> str:
    raw = json.loads(path.read_text(encoding="utf-8"))
    redacted = _redact_secrets(raw)
    canonical = json.dumps(redacted, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
