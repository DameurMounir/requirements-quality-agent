from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_distribution.py"
SPEC = importlib.util.spec_from_file_location("distribution_verifier_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the distribution verifier")
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def _write_minimal_wheel(path: Path, *, valid_metadata: bool = True) -> None:
    name = "requirements_quality_agent-0.1.0.dist-info"
    project_name = "requirements-quality-agent" if valid_metadata else "wrong-project"
    entry = verifier.EXPECTED_ENTRY_POINT if valid_metadata else "wrong = target:main"
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {project_name}\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.12,<3.14\n"
        "Classifier: License :: OSI Approved :: Apache Software License\n"
    )
    with zipfile.ZipFile(path, mode="w") as wheel:
        wheel.writestr("requirements_quality_agent/__init__.py", "")
        wheel.writestr("requirements_quality_agent/py.typed", "")
        wheel.writestr(f"{name}/METADATA", metadata)
        wheel.writestr(f"{name}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n")
        wheel.writestr(f"{name}/entry_points.txt", f"[console_scripts]\n{entry}\n")
        wheel.writestr(f"{name}/RECORD", "")


def test_wheel_path_traversal_is_rejected(tmp_path: Path) -> None:
    wheel_path = tmp_path / "unsafe.whl"
    _write_minimal_wheel(wheel_path)
    with zipfile.ZipFile(wheel_path, mode="a") as wheel:
        wheel.writestr("../escape.py", "")

    errors, _ = verifier.inspect_wheel(wheel_path)

    assert any("unsafe member path" in error for error in errors)


def test_invalid_wheel_metadata_and_entry_point_are_rejected(tmp_path: Path) -> None:
    wheel_path = tmp_path / "invalid.whl"
    _write_minimal_wheel(wheel_path, valid_metadata=False)

    errors, _ = verifier.inspect_wheel(wheel_path)

    assert "wheel metadata project name is invalid" in errors
    assert "wheel console entry point is invalid" in errors


def test_corrupt_wheel_crc_is_rejected(tmp_path: Path) -> None:
    wheel_path = tmp_path / "corrupt.whl"
    _write_minimal_wheel(wheel_path)
    content = bytearray(wheel_path.read_bytes())
    marker = content.find(b"Metadata-Version")
    assert marker >= 0
    content[marker] ^= 1
    wheel_path.write_bytes(content)

    errors, _ = verifier.inspect_wheel(wheel_path)

    assert any("CRC" in error or "corrupt" in error for error in errors)


def test_tar_link_member_is_rejected(tmp_path: Path) -> None:
    sdist_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(sdist_path, mode="w:gz") as archive:
        regular = tarfile.TarInfo("project/README.md")
        payload = b"readme"
        regular.size = len(payload)
        archive.addfile(regular, io.BytesIO(payload))
        linked = tarfile.TarInfo("project/link")
        linked.type = tarfile.SYMTYPE
        linked.linkname = "README.md"
        archive.addfile(linked)

    errors, _ = verifier.inspect_sdist(sdist_path)

    assert any("unsafe member type" in error for error in errors)
