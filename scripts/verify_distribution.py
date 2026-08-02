#!/usr/bin/env python3
"""Inspect built archives without extracting or executing their contents."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
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
EXPECTED_ENTRY_POINT = (
    "requirements-quality-agent = requirements_quality_agent.presentation.cli:main"
)


def validate_names(names: list[str], archive: Path) -> list[str]:
    errors: list[str] = []
    for name in names:
        candidate = PurePosixPath(name)
        payload_parts = candidate.parts[1:] if archive.name.endswith(".tar.gz") else candidate.parts
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"unsafe member path in {archive.name}: {name}")
        if (payload_parts and payload_parts[0] in FORBIDDEN_TOP_LEVEL) or any(
            part in FORBIDDEN_ANY_PARTS for part in payload_parts
        ):
            errors.append(f"runtime/cache member in {archive.name}: {name}")
        if candidate.suffix == ".pyc":
            errors.append(f"compiled Python member in {archive.name}: {name}")
    return errors


def _one_member(names: list[str], suffix: str) -> str | None:
    matches = [name for name in names if name.endswith(suffix)]
    return matches[0] if len(matches) == 1 else None


def inspect_wheel(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(path) as wheel:
            names = wheel.namelist()
            bad_member = wheel.testzip()
            if bad_member is not None:
                errors.append(f"wheel CRC failed for member: {bad_member}")
            metadata_name = _one_member(names, ".dist-info/METADATA")
            wheel_name = _one_member(names, ".dist-info/WHEEL")
            entry_name = _one_member(names, ".dist-info/entry_points.txt")
            record_name = _one_member(names, ".dist-info/RECORD")
            if (
                metadata_name is None
                or wheel_name is None
                or entry_name is None
                or record_name is None
            ):
                errors.append("wheel has an incomplete or ambiguous dist-info directory")
            else:
                metadata = Parser().parsestr(wheel.read(metadata_name).decode("utf-8"))
                if metadata.get("Name") != "requirements-quality-agent":
                    errors.append("wheel metadata project name is invalid")
                if metadata.get("Version") != "0.1.0":
                    errors.append("wheel metadata version is invalid")
                requires_python = (metadata.get("Requires-Python") or "").replace(" ", "")
                if set(requires_python.split(",")) != {">=3.12", "<3.14"}:
                    errors.append("wheel metadata Requires-Python is invalid")
                classifiers = metadata.get_all("Classifier", [])
                if "License :: OSI Approved :: Apache Software License" not in classifiers:
                    errors.append("wheel metadata license classifier is missing")
                entry_points = wheel.read(entry_name).decode("utf-8")
                if (
                    "[console_scripts]" not in entry_points
                    or EXPECTED_ENTRY_POINT not in entry_points
                ):
                    errors.append("wheel console entry point is invalid")
                wheel_metadata = Parser().parsestr(wheel.read(wheel_name).decode("utf-8"))
                if wheel_metadata.get("Root-Is-Purelib") != "true":
                    errors.append("wheel is not marked as pure Python")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
        errors.append("wheel is unreadable or corrupt")

    errors.extend(validate_names(names, path))
    required = {
        "requirements_quality_agent/__init__.py",
        "requirements_quality_agent/py.typed",
    }
    missing = required.difference(names)
    if missing:
        errors.append(f"wheel is missing: {sorted(missing)}")
    if any(name.startswith(("case/", "docs/", "tests/")) for name in names):
        errors.append("wheel unexpectedly contains case, documentation, or test material")
    return errors, names


def inspect_sdist(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    names: list[str] = []
    try:
        with tarfile.open(path, mode="r:gz") as sdist:
            members = sdist.getmembers()
            names = [member.name for member in members]
            for member in members:
                if not (member.isfile() or member.isdir()):
                    errors.append(f"source distribution has unsafe member type: {member.name}")
    except (OSError, tarfile.TarError):
        errors.append("source distribution is unreadable or corrupt")

    errors.extend(validate_names(names, path))
    sdist_root = PurePosixPath(names[0]).parts[0] if names else ""
    required = {
        f"{sdist_root}/LICENSE",
        f"{sdist_root}/NOTICE",
        f"{sdist_root}/README.md",
        f"{sdist_root}/pyproject.toml",
        f"{sdist_root}/uv.lock",
    }
    missing = required.difference(names)
    if missing:
        errors.append(f"source distribution is missing: {sorted(missing)}")
    return errors, names


def main() -> int:
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        print("FAIL: expected exactly one wheel and one source distribution", file=sys.stderr)
        return 1

    wheel_errors, wheel_names = inspect_wheel(wheels[0])
    sdist_errors, sdist_names = inspect_sdist(sdists[0])
    errors = [*wheel_errors, *sdist_errors]

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: inspected {len(wheel_names)} wheel and {len(sdist_names)} sdist members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
