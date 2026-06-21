"""GitHub API helpers for CURe CLI integration."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from cure_errors import ReviewflowError
from cure_output import _eprint
from run import ReviewflowSubprocessError, run_cmd


__all__ = [
    "require_gh_auth",
    "gh_api_json",
    "gh_api_list",
    "_decode_gh_api_list_stdout",
    "_looks_like_gh_auth_error",
    "_public_github_repo_clone_url",
    "_raise_gh_auth_error",
    "_supports_public_github_fallback",
]


def require_gh_auth(host: str) -> None:
    try:
        run_cmd(["gh", "auth", "status", "--hostname", host], check=True)
    except ReviewflowSubprocessError as e:
        _raise_gh_auth_error(host=host, error=e)


def _gh_error_text(error: ReviewflowSubprocessError) -> str:
    return (error.stderr or error.stdout or str(error)).strip()


def _looks_like_gh_auth_error(error: ReviewflowSubprocessError) -> bool:
    text = _gh_error_text(error).lower()
    needles = (
        "gh auth login",
        "not logged into any github hosts",
        "not authenticated",
        "populate the gh_token",
        "please run:  gh auth login",
        "please run gh auth login",
    )
    return any(needle in text for needle in needles)


def _raise_gh_auth_error(*, host: str, error: ReviewflowSubprocessError) -> None:
    msg = _gh_error_text(error) or str(error)
    raise ReviewflowError(
        f"`gh` is not authenticated for {host}.\n"
        f"- Try: gh auth login -h {host}\n"
        f"- Details: {msg}"
    ) from error


def _supports_public_github_fallback(host: str) -> bool:
    return host == "github.com"


def _public_github_repo_clone_url(*, host: str, owner: str, repo: str) -> str:
    if not _supports_public_github_fallback(host):
        raise ReviewflowError(
            f"Unauthenticated public clone fallback is only supported for github.com, got: {host}"
        )
    return f"https://github.com/{owner}/{repo}.git"


def _github_public_api_json(*, path: str) -> dict[str, Any]:
    normalized = path if path.startswith("/") else f"/{path}"
    req = urllib.request.Request(
        f"https://api.github.com{normalized}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "cure/0.1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ReviewflowError(
            f"Public GitHub API request failed ({getattr(e, 'code', '?')}): {normalized}\n{body}"
        ) from e
    except urllib.error.URLError as e:
        raise ReviewflowError(f"Public GitHub API request failed: {normalized}\n{e}") from e
    try:
        payload = json.loads(body)
    except Exception as e:
        raise ReviewflowError(f"Public GitHub API returned invalid JSON for {normalized}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"Public GitHub API returned unexpected payload for {normalized}")
    return payload


def gh_api_json(*, host: str, path: str, allow_public_fallback: bool = False) -> dict[str, Any]:
    cmd = ["gh", "api", "--hostname", host, path]
    try:
        result = run_cmd(cmd)
    except ReviewflowSubprocessError as e:
        if _looks_like_gh_auth_error(e):
            if allow_public_fallback and _supports_public_github_fallback(host):
                _eprint(f"`gh` is not authenticated for {host}; falling back to the public GitHub API.")
                return _github_public_api_json(path=path)
            _raise_gh_auth_error(host=host, error=e)
        raise
    try:
        payload = json.loads(result.stdout)
    except Exception as e:
        raise ReviewflowError(f"`gh api` returned invalid JSON for {path}: {e}") from e
    if not isinstance(payload, dict):
        raise ReviewflowError(f"`gh api` returned unexpected payload for {path}")
    return payload


_GH_API_SLURP_SUPPORTED: bool | None = None


def _decode_gh_api_list_stdout(*, stdout: str, path: str) -> list[Any]:
    text = stdout.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    values: list[Any] = []
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        try:
            value, end = decoder.raw_decode(text, idx)
        except Exception as e:
            raise ReviewflowError(f"`gh api` returned invalid JSON for {path}: {e}") from e
        values.append(value)
        idx = end
    payload: Any = values[0] if len(values) == 1 else values
    if all(isinstance(page, list) for page in payload) if isinstance(payload, list) else False:
        flattened: list[Any] = []
        for page in payload:
            flattened.extend(page)
        return flattened
    if not isinstance(payload, list):
        raise ReviewflowError(f"`gh api` returned unexpected list payload for {path}")
    return payload


def _run_gh_api_list(*, host: str, path: str, use_slurp: bool) -> list[Any]:
    cmd = ["gh", "api", "--hostname", host, path, "--paginate"]
    if use_slurp:
        cmd.append("--slurp")
    result = run_cmd(cmd)
    return _decode_gh_api_list_stdout(stdout=result.stdout, path=path)


def _classify_gh_api_list_error(error: ReviewflowSubprocessError) -> str:
    text = f"{error.stderr}\n{error.stdout}\n{error}".lower()
    if "unknown flag" in text or "unknown option" in text or "invalid option" in text:
        return "cli_unsupported_flag"
    return "subprocess"


def _github_public_api_list(*, path: str) -> list[Any]:
    normalized = path.lstrip("/")
    url = f"https://api.github.com/{normalized}"
    items: list[Any] = []
    while url:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"}, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                link_header = resp.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ReviewflowError(
                f"Public GitHub API request failed ({getattr(e, 'code', '?')}): {normalized}\n{body}"
            ) from e
        except urllib.error.URLError as e:
            raise ReviewflowError(f"Public GitHub API request failed: {normalized}\n{e}") from e
        try:
            payload = json.loads(body)
        except Exception as e:
            raise ReviewflowError(f"Public GitHub API returned invalid JSON for {normalized}: {e}") from e
        if not isinstance(payload, list):
            raise ReviewflowError(f"Public GitHub API returned unexpected list payload for {normalized}")
        items.extend(payload)
        next_url = ""
        for part in link_header.split(","):
            if 'rel="next"' in part:
                start = part.find("<")
                end = part.find(">", start + 1)
                if start >= 0 and end > start:
                    next_url = part[start + 1 : end]
        url = next_url
    return items


def gh_api_list(*, host: str, path: str, allow_public_fallback: bool = False) -> list[Any]:
    global _GH_API_SLURP_SUPPORTED

    use_slurp = _GH_API_SLURP_SUPPORTED is not False
    try:
        payload = _run_gh_api_list(host=host, path=path, use_slurp=use_slurp)
    except ReviewflowSubprocessError as e:
        if use_slurp and _classify_gh_api_list_error(e) == "cli_unsupported_flag":
            _GH_API_SLURP_SUPPORTED = False
            try:
                return _run_gh_api_list(host=host, path=path, use_slurp=False)
            except ReviewflowSubprocessError as retry_error:
                e = retry_error
        if allow_public_fallback and _looks_like_gh_auth_error(e) and _supports_public_github_fallback(host):
            _eprint(f"`gh` is not authenticated for {host}; falling back to the public GitHub API.")
            return _github_public_api_list(path=path)
        raise
    else:
        if use_slurp:
            _GH_API_SLURP_SUPPORTED = True
        return payload
