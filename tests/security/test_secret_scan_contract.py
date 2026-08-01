from __future__ import annotations

import secrets
import shutil
import subprocess  # nosec B404
from pathlib import Path


def test_secret_hook_rejects_runtime_canary_without_echoing_value(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    hook = shutil.which("detect-secrets-hook")
    assert hook is not None
    token = "sk-" + secrets.token_hex(10) + "T3Bl" + "bkFJ" + secrets.token_hex(10)
    candidate = tmp_path / "canary.txt"
    candidate.write_text(token, encoding="utf-8")

    result = subprocess.run(  # noqa: S603  # nosec B603
        [hook, "--baseline", str(project_root / ".secrets.baseline"), str(candidate)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    rendered = result.stdout + result.stderr
    assert result.returncode != 0
    assert token not in rendered
