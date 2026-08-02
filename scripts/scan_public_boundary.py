#!/usr/bin/env python3
"""Fail when current or reachable files cross the public-data boundary."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_BYTES = 5 * 1024 * 1024
MAX_DENYLIST_BYTES = 64 * 1024
ASSET_MANIFEST = Path("assets/provenance.json")
BINARY_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
FORBIDDEN_TOP_LEVEL = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "dist",
    "htmlcov",
    "output",
    "run-state",
}
FORBIDDEN_ANY_PARTS = {"__pycache__"}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".faiss",
    ".key",
    ".p12",
    ".pem",
    ".pickle",
    ".pkl",
    ".pyc",
    ".sqlite",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:EC |OPENSSH |RSA )?PRIVATE KEY-----"),
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(
    r"(?<![\w])(?:\+\d{1,3}[\s.-])?(?:\(\d{2,4}\)[\s.-]|\d{2,4}[\s.-])"
    r"\d{3,4}[\s.-]\d{3,4}(?![\w])"
)
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ANSWER_KEY_REFERENCES = ("case/expected", "requirements-labels.jsonl")
ANSWER_KEY_CONTROL = Path("src/requirements_quality_agent/controls/input_policy.py")


class BoundaryConfigurationError(ValueError):
    """Raised when the scanner itself has an unsafe or invalid configuration."""


def _git(root: Path, *arguments: str) -> bytes:
    git = shutil.which("git")
    if git is None:
        raise BoundaryConfigurationError("git executable is unavailable")
    # The executable is absolute and arguments are application/test-owned values.
    result = subprocess.run(  # noqa: S603  # nosec B603
        [git, *arguments],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def tracked_paths(root: Path = ROOT) -> tuple[Path, ...]:
    output = _git(root, "ls-files", "-z")
    return tuple(Path(item.decode("utf-8")) for item in output.split(b"\0") if item)


def load_denylist(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DENYLIST_BYTES:
            raise BoundaryConfigurationError("confidential denylist is missing or unsafe")
        lines = tuple(
            line.strip().casefold()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise BoundaryConfigurationError("confidential denylist is unreadable") from exc
    if len(lines) > 200 or any(len(line) < 3 or len(line) > 200 for line in lines):
        raise BoundaryConfigurationError("confidential denylist has invalid entries")
    return lines


def _asset_records(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = root / ASSET_MANIFEST
    if not path.exists():
        return {}
    try:
        raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        if raw.get("schema_version") != "1.0.0" or not isinstance(raw.get("assets"), list):
            raise BoundaryConfigurationError("asset provenance manifest is invalid")
        records: dict[tuple[str, str], dict[str, str]] = {}
        for item in raw["assets"]:
            if not isinstance(item, dict):
                raise BoundaryConfigurationError("asset provenance record is invalid")
            required = {"path", "sha256", "origin", "licence"}
            if not required <= set(item) or any(
                not isinstance(item[field], str) or not item[field] for field in required
            ):
                raise BoundaryConfigurationError("asset provenance record is invalid")
            digest = item["sha256"]
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise BoundaryConfigurationError("asset provenance digest is invalid")
            key = (item["path"], digest)
            if key in records:
                raise BoundaryConfigurationError("asset provenance record is duplicated")
            records[key] = {field: item[field] for field in required}
        return records
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise BoundaryConfigurationError("asset provenance manifest is unreadable") from exc


def _path_errors(relative: Path, *, context: str) -> list[str]:
    errors: list[str] = []
    if (relative.parts and relative.parts[0] in FORBIDDEN_TOP_LEVEL) or any(
        part in FORBIDDEN_ANY_PARTS for part in relative.parts
    ):
        errors.append(f"{context} runtime or cache path: {relative}")
    if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
        errors.append(f"{context} unsafe artifact type: {relative}")
    if relative.name.startswith(".env") and relative.name != ".env.example":
        errors.append(f"{context} environment file: {relative}")
    return errors


def _text_errors(
    text: str,
    relative: Path,
    *,
    context: str,
    denylist: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"{context} possible {label}: {relative}")
    if EMAIL_PATTERN.search(text):
        errors.append(f"{context} possible email address: {relative}")
    if PHONE_PATTERN.search(text):
        errors.append(f"{context} possible phone number: {relative}")
    for candidate in IPV4_PATTERN.findall(text):
        try:
            if ipaddress.ip_address(candidate).is_global:
                errors.append(f"{context} possible public IP address: {relative}")
                break
        except ValueError:
            continue
    folded = text.casefold()
    if any(term in folded for term in denylist):
        errors.append(f"{context} confidential denylist match: {relative}")
    if (
        relative.parts
        and relative.parts[0] == "src"
        and relative != ANSWER_KEY_CONTROL
        and any(marker in text for marker in ANSWER_KEY_REFERENCES)
    ):
        errors.append(f"{context} answer-key reference in runtime source: {relative}")
    return errors


def _content_errors(
    content: bytes,
    relative: Path,
    *,
    context: str,
    denylist: tuple[str, ...],
    asset_records: dict[tuple[str, str], dict[str, str]],
) -> list[str]:
    if len(content) > MAX_TRACKED_BYTES:
        return [f"{context} file exceeds {MAX_TRACKED_BYTES} bytes: {relative}"]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        digest = hashlib.sha256(content).hexdigest()
        if relative.suffix.lower() not in BINARY_SUFFIXES:
            return [f"{context} unexpected binary file: {relative}"]
        if (relative.as_posix(), digest) not in asset_records:
            return [f"{context} binary asset lacks matching provenance: {relative}"]
        return []
    if relative.suffix.lower() in BINARY_SUFFIXES:
        return [f"{context} image extension contains unexpected text data: {relative}"]
    return _text_errors(text, relative, context=context, denylist=denylist)


def scan_current(
    root: Path = ROOT,
    denylist: tuple[str, ...] = (),
) -> list[str]:
    root = root.resolve(strict=True)
    assets = _asset_records(root)
    errors: list[str] = []
    observed_assets: set[tuple[str, str]] = set()
    for relative in tracked_paths(root):
        path = root / relative
        if path.is_symlink():
            errors.append(f"current tracked symlink: {relative}")
            continue
        if not path.is_file():
            errors.append(f"current tracked path is not a regular file: {relative}")
            continue
        errors.extend(_path_errors(relative, context="current"))
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if relative.suffix.lower() in BINARY_SUFFIXES:
            observed_assets.add((relative.as_posix(), digest))
        errors.extend(
            _content_errors(
                content,
                relative,
                context="current",
                denylist=denylist,
                asset_records=assets,
            )
        )
    unobserved = set(assets).difference(observed_assets)
    for asset_path, _ in sorted(unobserved):
        errors.append(f"asset provenance has no matching current file: {asset_path}")
    return errors


def _history_blobs(root: Path) -> tuple[tuple[str, Path, bytes], ...]:
    commits = tuple(item.decode("ascii") for item in _git(root, "rev-list", "HEAD").splitlines())
    blobs: dict[tuple[str, Path], bytes] = {}
    for commit in commits:
        tree = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            _, kind, object_id = metadata.decode("ascii").split(" ", 2)
            if kind != "blob":
                continue
            relative = Path(raw_path.decode("utf-8"))
            key = (object_id, relative)
            if key not in blobs:
                blobs[key] = _git(root, "cat-file", "blob", object_id)
    return tuple((object_id, path, content) for (object_id, path), content in blobs.items())


def scan_history(
    root: Path = ROOT,
    denylist: tuple[str, ...] = (),
) -> list[str]:
    root = root.resolve(strict=True)
    assets = _asset_records(root)
    errors: list[str] = []
    for object_id, relative, content in _history_blobs(root):
        context = f"history object {object_id[:12]}"
        errors.extend(_path_errors(relative, context=context))
        errors.extend(
            _content_errors(
                content,
                relative,
                context=context,
                denylist=denylist,
                asset_records=assets,
            )
        )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="scan every reachable Git blob")
    parser.add_argument(
        "--denylist",
        type=Path,
        default=None,
        help="untracked local file containing confidential terms, one per line",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configured_path = args.denylist
    if configured_path is None and os.getenv("PUBLIC_BOUNDARY_DENYLIST"):
        configured_path = Path(os.environ["PUBLIC_BOUNDARY_DENYLIST"])
    try:
        denylist = load_denylist(configured_path)
        errors = scan_history(ROOT, denylist) if args.history else scan_current(ROOT, denylist)
    except (BoundaryConfigurationError, OSError, subprocess.SubprocessError):
        print("FAIL: public-boundary scan could not complete safely", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    scope = "reachable history" if args.history else f"{len(tracked_paths(ROOT))} tracked files"
    print(f"PASS: {scope} satisfies the public boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
