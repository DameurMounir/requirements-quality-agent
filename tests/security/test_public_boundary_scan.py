from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "scan_public_boundary.py"
SPEC = importlib.util.spec_from_file_location("public_boundary_scanner_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the public-boundary scanner")
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


def _repository(path: Path) -> Path:
    path.mkdir()
    scanner._git(path, "init", "-q")  # noqa: SLF001
    scanner._git(path, "config", "user.name", "Synthetic Test")  # noqa: SLF001
    scanner._git(  # noqa: SLF001
        path,
        "config",
        "user.email",
        "synthetic" + "@" + "invalid.example",
    )
    return path


def _track(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    scanner._git(root, "add", relative)  # noqa: SLF001
    return path


def test_confidential_denylist_match_is_detected_without_echoing_term(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    term = "private" + "-customer-codename"
    _track(root, "notes.md", f"This mentions {term}.")
    denylist_path = tmp_path / "denylist.txt"
    denylist_path.write_text(term, encoding="utf-8")

    errors = scanner.scan_current(root, scanner.load_denylist(denylist_path))

    assert any("confidential denylist match" in error for error in errors)
    assert term not in "\n".join(errors)


def test_generic_pii_patterns_are_reported_without_echoing_values(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    email = "person" + "@" + "example.com"
    phone = "+" + "212" + " " + "612" + " " + "345" + " " + "678"
    public_ip = ".".join(("8", "8", "8", "8"))
    _track(root, "contact.md", f"{email}\n{phone}\n{public_ip}\n")

    errors = scanner.scan_current(root)
    joined = "\n".join(errors)

    assert "possible email address" in joined
    assert "possible phone number" in joined
    assert "possible public IP address" in joined
    assert email not in joined
    assert phone not in joined
    assert public_ip not in joined


def test_unmanifested_binary_asset_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _track(root, "assets/example.png", b"\x89PNG\r\n\x1a\n\x00binary")

    errors = scanner.scan_current(root)

    assert any("binary asset lacks matching provenance" in error for error in errors)


def test_deleted_secret_in_reachable_history_is_detected_and_redacted(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    current_branch = (  # noqa: SLF001
        scanner._git(root, "branch", "--show-current").decode("utf-8").strip()
    )
    _track(root, "README.md", "clean\n")
    scanner._git(root, "commit", "-qm", "clean")  # noqa: SLF001
    token = "sk-" + "A" * 28
    _track(root, "temporary.txt", token)
    scanner._git(root, "commit", "-qm", "add synthetic canary")  # noqa: SLF001
    (root / "temporary.txt").unlink()
    scanner._git(root, "add", "-u")  # noqa: SLF001
    scanner._git(root, "commit", "-qm", "remove synthetic canary")  # noqa: SLF001
    scanner._git(root, "checkout", "-qb", "future-only")  # noqa: SLF001
    _track(root, "future-only.pem", "unreachable branch fixture\n")
    scanner._git(root, "commit", "-qm", "add unreachable branch fixture")  # noqa: SLF001
    scanner._git(root, "checkout", "-q", current_branch)  # noqa: SLF001

    errors = scanner.scan_history(root)
    joined = "\n".join(errors)

    assert "possible OpenAI-style key" in joined
    assert token not in joined
    assert "future-only.pem" not in joined
