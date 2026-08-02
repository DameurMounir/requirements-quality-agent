from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from requirements_quality_agent.adapters.models.openai_responses import OpenAIResponsesAdapter
from requirements_quality_agent.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_openai_result.py"
SPEC = importlib.util.spec_from_file_location("openai_result_builder_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the OpenAI result builder")
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def test_committed_not_run_record_is_generated_from_current_configuration() -> None:
    expected = builder.build_record(PROJECT_ROOT)
    json_path = PROJECT_ROOT / "evaluation" / "results" / "openai-adapter.json"
    markdown_path = PROJECT_ROOT / "evaluation" / "results" / "openai-adapter.md"
    committed = json.loads(json_path.read_text(encoding="utf-8"))

    assert committed == expected
    assert markdown_path.read_text(encoding="utf-8") == builder.render_markdown(expected)
    assert committed["status"] == "NOT_RUN"
    assert committed["metrics"] is None
    assert committed["is_ai_accuracy"] is False

    settings = Settings(repository_root=PROJECT_ROOT)
    adapter = OpenAIResponsesAdapter(
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        client=object(),
    )
    assert committed["configuration"]["model"] == settings.model
    assert committed["configuration"]["reasoning_effort"] == settings.reasoning_effort
    assert committed["configuration"]["adapter_configuration"] == adapter.configuration
    assert committed["planned_evaluation_digests"]["prompt_sha256"] == adapter.prompt_sha256
