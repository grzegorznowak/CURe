"""GitHub API helpers for CURe CLI integration."""

from __future__ import annotations

import json
import posixpath
import re
import urllib.error
import urllib.parse
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
        raise ReviewflowError(f"`gh api` returned zero JSON documents for {path}")
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
    if any(not isinstance(document, list) for document in values):
        raise ReviewflowError(f"`gh api` returned unexpected non-array document for {path}")
    if len(values) > 1:
        return [item for document in values for item in document]

    payload = values[0]
    if payload and any(isinstance(item, list) for item in payload):
        if not all(isinstance(page, list) for page in payload):
            raise ReviewflowError(f"`gh api` returned mixed page shapes for {path}")
        return [item for page in payload for item in page]
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


_PUBLIC_LIST_TIMEOUT_SECONDS = 30.0
_PUBLIC_LIST_MAX_PAGES = 100
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise ReviewflowError(f"Public GitHub API redirect rejected ({code}): {req.full_url}")


def _decode_unreserved_escapes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else f"%{match.group(1).upper()}"

    return re.sub(r"%([0-9A-Fa-f]{2})", replace, value)


def _canonical_public_list_url(url: str) -> tuple[str, str]:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ReviewflowError(f"Public GitHub API returned malformed next URL: {url}") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "api.github.com"
        or (port not in {None, 443})
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.fragment)
    ):
        raise ReviewflowError(f"Public GitHub API returned unsafe next URL origin: {url}")
    raw_path = parsed.path or "/"
    normalized_path = posixpath.normpath(_decode_unreserved_escapes(raw_path))
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    canonical_query = _decode_unreserved_escapes(parsed.query)
    canonical = urllib.parse.urlunsplit(
        ("https", "api.github.com:443", normalized_path, canonical_query, "")
    )
    request_url = urllib.parse.urlunsplit(
        ("https", "api.github.com", parsed.path or "/", parsed.query, "")
    )
    return request_url, canonical


def _next_link(link_header: str) -> str:
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">", start + 1)
        if start >= 0 and end > start:
            return part[start + 1 : end]
    return ""


def _github_public_api_list(*, path: str) -> list[Any]:
    normalized = path.lstrip("/")
    current_url = f"https://api.github.com/{normalized}"
    opener = urllib.request.build_opener(_RejectRedirects())
    items: list[Any] = []
    requested: set[str] = set()
    page = 0
    while current_url:
        request_url, canonical = _canonical_public_list_url(current_url)
        if canonical in requested:
            raise ReviewflowError(f"Public GitHub API pagination cycle rejected: {request_url}")
        if page >= _PUBLIC_LIST_MAX_PAGES:
            raise ReviewflowError("Public GitHub API pagination exceeded 100 pages")
        requested.add(canonical)
        page += 1
        req = urllib.request.Request(
            request_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "cure/0.1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with opener.open(req, timeout=_PUBLIC_LIST_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                link_header = resp.headers.get("Link", "")
        except ReviewflowError:
            raise
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ReviewflowError(
                f"Public GitHub API request failed ({getattr(exc, 'code', '?')}): {normalized}\n{body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ReviewflowError(f"Public GitHub API request failed: {normalized}\n{exc}") from exc
        try:
            payload = json.loads(body)
        except Exception as exc:
            raise ReviewflowError(
                f"Public GitHub API returned invalid JSON for {normalized}: {exc}"
            ) from exc
        if not isinstance(payload, list):
            raise ReviewflowError(
                f"Public GitHub API returned unexpected list payload for {normalized}"
            )
        items.extend(payload)
        next_value = _next_link(link_header)
        if not next_value:
            current_url = ""
            continue
        if page >= _PUBLIC_LIST_MAX_PAGES:
            raise ReviewflowError("Public GitHub API pagination exceeded 100 pages")
        try:
            current_url = urllib.parse.urljoin(request_url, next_value)
        except (TypeError, ValueError) as exc:
            raise ReviewflowError(
                f"Public GitHub API returned malformed next URL: {next_value}"
            ) from exc
        # Validate before the next request, including cycle/origin checks.
        _, next_canonical = _canonical_public_list_url(current_url)
        if next_canonical in requested:
            raise ReviewflowError(f"Public GitHub API pagination cycle rejected: {current_url}")
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
