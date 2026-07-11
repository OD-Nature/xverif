from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from skill_test_utils import assert_markdown_links, fenced_json
from xcov.schemas import schema_for_action


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "xverif-cli"


def test_xverif_cli_links_and_reference_reachability() -> None:
    assert_markdown_links(SKILL)
    text = "\n".join(path.read_text(encoding="utf-8") for path in SKILL.rglob("*.md"))
    for reference in sorted((SKILL / "references").rglob("*.md")):
        assert reference.name in text or str(reference.relative_to(SKILL)) in text, reference


def test_xdebug_action_reference_matches_request_schemas() -> None:
    documented = set(re.findall(
        r"^\| `([^`]+)` \|", (SKILL / "references/xdebug/action-reference.md").read_text(),
        re.MULTILINE,
    ))
    schemas = {
        path.name.removesuffix(".request.schema.json")
        for path in (ROOT / "xdebug/schemas/v1/actions").glob("*.request.schema.json")
    }
    assert documented == schemas
    assert len(schemas) == 70


def test_native_request_examples_validate_against_current_schemas() -> None:
    validated = 0
    for path, payload in fenced_json(SKILL):
        api_version = payload.get("api_version")
        action = payload.get("action")
        if not isinstance(action, str):
            continue
        if api_version == "xdebug.v1":
            schema_path = ROOT / "xdebug/schemas/v1/actions" / f"{action}.request.schema.json"
            assert schema_path.exists(), f"unknown xdebug action in {path}: {action}"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        elif api_version == "xcov.v1":
            schema = schema_for_action(action, "request")
        else:
            continue
        jsonschema.Draft202012Validator(schema).validate(payload)
        validated += 1
    assert validated >= 20


def test_cli_prompt_does_not_restore_native_output_envelope() -> None:
    prompt = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    assert "api_version/action/target/args/limits/output" not in prompt
    assert "--json" in prompt
