from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import pytest


DOC_PATH = Path("docs/XDEBUG_TIME_HANDLING_REVIEW_AND_TEST_MATRIX.md")
FORBIDDEN_NUMERIC_TIME_KEYS = {"time_value"}
FORBIDDEN_NUMERIC_TIME_SUFFIXES = ("_ps",)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_json(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{path}[{index}]")


def _forbidden_numeric_time_paths(example: Any) -> list[str]:
    offenders: list[str] = []
    for path, value in _walk_json(example):
        key = path.rsplit(".", 1)[-1]
        if key in FORBIDDEN_NUMERIC_TIME_KEYS or key.endswith(
            FORBIDDEN_NUMERIC_TIME_SUFFIXES
        ):
            if isinstance(value, (int, float)):
                offenders.append(path)
    return offenders


@pytest.mark.contract
def test_time_handling_review_doc_exists_and_names_output_contract(
    xdebug_root: Path,
) -> None:
    text = (xdebug_root / DOC_PATH).read_text(encoding="utf-8")
    required_phrases = [
        "同一个逻辑时间只输出一份 canonical 时间字符串",
        "禁止 `*_ps` 数字字段",
        "JSON 与 xout",
        "默认无单位时间范围按 ns",
        "默认输出渲染单位按 ns",
        "args.time_unit",
        "本阶段已进入实现",
    ]
    for phrase in required_phrases:
        assert phrase in text


@pytest.mark.contract
def test_response_examples_publish_only_one_canonical_time_string(
    xdebug_root: Path,
) -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted((xdebug_root / "examples" / "responses").glob("*.json")):
        fields = _forbidden_numeric_time_paths(_load_json(path))
        if fields:
            offenders[path.name] = fields
    assert not offenders


@pytest.mark.contract
def test_time_parsing_has_single_contract_entrypoint(xdebug_root: Path) -> None:
    source_root = xdebug_root / "src"
    allowed = {
        source_root / "core" / "npi" / "time_contract.cpp",
        source_root / "waveform" / "common" / "time_spec.cpp",
    }
    offenders: dict[str, list[str]] = {}
    pattern = re.compile(
        r"\bstrtod\s*\(|npi_fsdb_convert_time_in\s*\(|npi_fsdb_convert_time_out\s*\("
    )
    for path in sorted(source_root.rglob("*.cpp")):
        if path in allowed:
            continue
        matches = [
            f"{index}: {line.strip()}"
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if pattern.search(line)
        ]
        if matches:
            offenders[str(path.relative_to(xdebug_root))] = matches
    assert not offenders


@pytest.mark.contract
def test_time_formatting_and_default_units_are_centralized(xdebug_root: Path) -> None:
    risky_patterns = {
        "src/waveform/server/service/context.cpp": [
            'snprintf(buf, sizeof(buf), "%.6g", value)',
            "npi_fsdb_convert_time_out",
            "npi_fsdb_convert_time_in",
        ],
        "src/combined/active_trace_common.h": [
            "std::setprecision(15) << value",
            "fsdb_time_to_precise_text",
        ],
    }
    offenders: dict[str, list[str]] = {}
    for rel_path, patterns in risky_patterns.items():
        text = (xdebug_root / rel_path).read_text(encoding="utf-8")
        hits = [pattern for pattern in patterns if pattern in text]
        if hits:
            offenders[rel_path] = hits
    assert not offenders


@pytest.mark.contract
def test_time_unit_is_render_only_and_defaults_to_ns(xdebug_root: Path) -> None:
    header = (xdebug_root / "src/core/npi/time_contract.h").read_text(encoding="utf-8")
    assert "TimeRenderUnit::Ns" in header
    assert 'std::string default_unit = "ns"' in header

    allowed = {
        Path("src/core/npi/time_contract.cpp"),
        Path("src/core/npi/time_contract.h"),
        Path("src/engine/server.cpp"),
        Path("src/waveform/server/service/query_actions.cpp"),
    }
    offenders: dict[str, list[str]] = {}
    for path in sorted((xdebug_root / "src").rglob("*")):
        if path.suffix not in {".cpp", ".h"}:
            continue
        rel = path.relative_to(xdebug_root)
        if rel in allowed:
            continue
        matches = [
            f"{index}: {line.strip()}"
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if '"time_unit"' in line or "args.time_unit" in line
        ]
        if matches:
            offenders[str(rel)] = matches
    assert not offenders
