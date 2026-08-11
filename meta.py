from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SECRET_KEYS = {
    "api_key",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "private_key",
    "cookie",
    "netrc",
}

SECRET_SUFFIXES = (
    "_api_key",
    "_token",
    "_access_token",
    "_refresh_token",
    "_authorization",
    "_password",
    "_passwd",
    "_secret",
    "_client_secret",
    "_private_key",
    "_cookie",
)


def _normalize_secret_key(key: object) -> str:
    text = str(key or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _is_secret_key(key: object) -> bool:
    normalized = _normalize_secret_key(key)
    if not normalized:
        return False
    if normalized in SECRET_KEYS:
        return True
    if any(normalized.endswith(suffix) for suffix in SECRET_SUFFIXES):
        return True
    return ("bearer" in normalized) or ("private_key" in normalized)


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner_value in value.items():
            if _is_secret_key(key):
                redacted[key] = "REDACTED"
            else:
                redacted[key] = _redact_secrets(inner_value)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def redact_secrets(value: Any) -> Any:
    return _redact_secrets(value)


def json_fingerprint(path: Path) -> str:
    raw = json.loads(path.read_text(encoding="utf-8"))
    redacted = redact_secrets(raw)
    canonical = json.dumps(redacted, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    # Unique temp file per write: concurrent processes must never share a temp
    # name (a fixed `.tmp` lets one process truncate another's pending write),
    # and os.replace is atomic — readers always see the old or the new
    # content, never a torn write.
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_redacted_json(path: Path, data: dict[str, Any]) -> None:
    write_json(path, redact_secrets(data))
