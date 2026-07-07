"""github_sync.py

Best-effort persistence of new template sites to GitHub, so additions made
via the admin "Add Site" dialog survive Render redeploys instead of only
living in the current ephemeral container.

Requires a GITHUB_TOKEN environment variable — a fine-grained PAT scoped to
Contents: Read and write on this repo only, tied to whichever GitHub account
should legitimately own commits to this repo (confirm this has been moved
off any legacy personal-account credential before relying on this).

If GITHUB_TOKEN is not set, is_configured() returns False and callers should
skip GitHub sync entirely — this module intentionally has no fallback
credential and never fails silently; commit_site() raises on any API error
so the caller can surface it rather than pretend the commit succeeded.
"""

from __future__ import annotations

import ast
import base64
import os
from typing import Dict, List, Optional, Tuple

import requests

GITHUB_API = "https://api.github.com"
REPO = "phoebegawk/mockup-machine"
BRANCH = "main"
COORDS_PATH = "template_coordinates.py"
TEMPLATE_DIR_PATH = "Templates/Digital"

_TIMEOUT = 20


def is_configured() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN"))


def _headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _get_file(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (text_content, sha) for a file at `path` on BRANCH, or (None, None) if it doesn't exist."""
    url = f"{GITHUB_API}/repos/{REPO}/contents/{path}"
    resp = requests.get(url, headers=_headers(), params={"ref": BRANCH}, timeout=_TIMEOUT)
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def _put_file(path: str, content_bytes: bytes, message: str, sha: Optional[str]) -> None:
    url = f"{GITHUB_API}/repos/{REPO}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()


def format_entry(filename: str, quad: list) -> str:
    """
    Renders a single-panel TEMPLATE_COORDINATES entry as source text,
    matching the existing file's formatting exactly (e.g. the "Ararat"
    entry). Multi-panel entries are out of scope for the admin tool —
    see template_detect.py's module docstring for why.
    """
    lines = [f'    "{filename}": {{']
    lines.append('        "split_ratio": [1.0],')
    lines.append('        "LHS": [')
    for pt in quad:
        lines.append(f"            {pt!r},")
    lines.append("        ]")
    lines.append("    },")
    return "\n".join(lines)


def insert_entry(source_text: str, entry_text: str) -> str:
    """
    Inserts a new entry just before the final closing brace of
    TEMPLATE_COORDINATES. Validates the result is syntactically valid
    Python (via ast.parse) before returning — raises rather than ever
    writing a broken file.
    """
    trimmed = source_text.rstrip()
    if not trimmed.endswith("}"):
        raise ValueError("template_coordinates.py does not end with the expected closing brace.")

    insertion_point = trimmed.rfind("\n}")
    if insertion_point == -1:
        raise ValueError("Could not locate the TEMPLATE_COORDINATES closing brace.")

    new_text = trimmed[:insertion_point] + "\n" + entry_text + trimmed[insertion_point:] + "\n"

    ast.parse(new_text)  # raises SyntaxError if malformed
    return new_text


def commit_site(filename: str, quad: list, png_bytes: bytes) -> None:
    """
    Commits the new template PNG and its template_coordinates.py entry to
    GitHub in two sequential commits. Raises on any failure — callers must
    surface the error rather than assume success. Single-panel only.
    """
    if not is_configured():
        raise RuntimeError("GITHUB_TOKEN is not set; cannot commit to GitHub.")

    source_text, coords_sha = _get_file(COORDS_PATH)
    if source_text is None:
        raise RuntimeError(f"Could not read {COORDS_PATH} from {REPO}@{BRANCH}.")

    entry_text = format_entry(filename, quad)
    new_source = insert_entry(source_text, entry_text)

    _put_file(
        f"{TEMPLATE_DIR_PATH}/{filename}",
        png_bytes,
        message=f"Add site template: {filename}",
        sha=None,  # new file; if it already exists this will 422 rather than silently overwrite
    )
    _put_file(
        COORDS_PATH,
        new_source.encode("utf-8"),
        message=f"Add coordinates for {filename}",
        sha=coords_sha,
    )
