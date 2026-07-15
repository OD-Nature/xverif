#!/usr/bin/env python3
"""Validate xdebug JSON examples against local schema files.

The validator implements the small JSON Schema subset used by xdebug contract
schemas: type, enum, required, properties, additionalProperties, items, and
basic anyOf/oneOf/allOf. It is dependency-free by design.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft7Validator, Draft202012Validator, ValidationError as JsonSchemaValidationError


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate(value: Any, schema: Dict[str, Any], path: str = "$") -> None:
    for key in ("allOf",):
        if key in schema:
            for child in schema[key]:
                validate(value, child, path)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            errors = []
            ok_count = 0
            for child in schema[key]:
                try:
                    validate(value, child, path)
                    ok_count += 1
                except ValidationError as exc:
                    errors.append(str(exc))
            if key == "anyOf" and ok_count == 0:
                raise ValidationError(f"{path}: no anyOf schema matched: {errors}")
            if key == "oneOf" and ok_count != 1:
                raise ValidationError(f"{path}: expected exactly one oneOf match, got {ok_count}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: {value!r} not in enum {schema['enum']!r}")

    if "type" in schema:
        expected = schema["type"]
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(type_ok(value, t) for t in expected_types):
            raise ValidationError(f"{path}: expected type {expected}, got {type(value).__name__}")

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                raise ValidationError(f"{path}: missing required property {name!r}")
        props = schema.get("properties", {})
        if not isinstance(props, dict):
            props = {}
        for name, child in props.items():
            if name in value:
                validate(value[name], child, f"{path}.{name}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                raise ValidationError(f"{path}: additional properties not allowed: {sorted(extra)}")

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for idx, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{idx}]")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        fail(f"{path}: cannot parse JSON: {exc}")


def action_schema_path(schemas: Path, action: str, kind: str) -> Path:
    candidate = schemas / "actions" / f"{action}.{kind}.schema.json"
    if candidate.exists():
        return candidate
    fail(f"missing action-specific {kind} schema for {action}: {candidate}")


def validate_file(path: Path, schemas: Path) -> None:
    doc = load_json(path)
    if path.parent.name == "errors":
        schema_path = schemas / "xdebug.error.schema.json"
        kind = "response"
    else:
        if not isinstance(doc, dict) or not isinstance(doc.get("action"), str):
            fail(f"{path}: example must contain string action")
        kind = "request" if path.parent.name == "requests" else "response"
        schema_path = action_schema_path(schemas, doc["action"], kind)
    schema = load_json(schema_path)
    validator = Draft7Validator(schema) if kind == "request" else Draft202012Validator(schema)
    try:
        validator.validate(doc)
    except JsonSchemaValidationError as exc:
        fail(f"{path}: does not match {schema_path}: {exc}")


def main(argv: List[str]) -> int:
    examples = Path(argv[1]) if len(argv) > 1 else Path("xdebug/examples")
    schemas = Path(argv[2]) if len(argv) > 2 else Path("xdebug/schemas/v1")
    if not examples.exists():
        fail(f"examples root does not exist: {examples}")
    if not schemas.exists():
        fail(f"schemas root does not exist: {schemas}")
    files = sorted(examples.rglob("*.json"))
    if not files:
        fail(f"no examples found under {examples}")
    for path in files:
        validate_file(path, schemas)
    print(f"validated {len(files)} examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
