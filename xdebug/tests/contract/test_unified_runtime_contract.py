from __future__ import annotations

import re
from pathlib import Path

import pytest


XDEBUG_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = XDEBUG_ROOT / "src"


REMOVED_STANDALONE_PATHS = [
    "src/backend/engine_request_mapper.cpp",
    "src/backend/engine_request_mapper.h",
    "src/design/commands/cmd_ai.cpp",
    "src/design/commands/cmd_ai.h",
    "src/design/service/router.cpp",
    "src/waveform/main.cpp",
    "src/waveform/commands/cmd_ai.cpp",
    "src/waveform/commands/cmd_ai.h",
    "src/waveform/service/action_registry.cpp",
    "src/waveform/service/action_registry.h",
    "src/waveform/service/router.cpp",
    "src/waveform/service/session_actions.cpp",
    "src/waveform/service/protocol_actions.cpp",
    "src/waveform/server/server.cpp",
    "src/waveform/server/server.h",
]


FORBIDDEN_STANDALONE_SYMBOLS = re.compile(
    r"\b(cmd_ai|handle_request|run_query|action_known|print_actions|"
    r"WaveformActionRegistry|default_waveform_action_registry|base_response|"
    r"error_response|finalize_response|response_verbosity|print_json)\b"
)

LIFECYCLE_APIS = re.compile(
    r"\b(npi_init|npi_load_design|npi_fsdb_open|npi_fsdb_close|npi_end)\b"
)

COMBINED_ENTRYPOINTS = re.compile(
    r"\b(run_engine|ActiveTraceService|ActiveTraceChainService|NpiSessionGuard|FsdbFileGuard)\b"
)


def _source_files(*roots: Path) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        out.extend(
            p
            for p in root.rglob("*")
            if p.suffix in {".cpp", ".h"} and p.is_file()
        )
    return sorted(out)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


@pytest.mark.contract
def test_standalone_design_and_waveform_runtime_sources_are_removed() -> None:
    existing = [rel for rel in REMOVED_STANDALONE_PATHS if (XDEBUG_ROOT / rel).exists()]
    assert existing == []
    assert not any((SRC_ROOT / "waveform/service/actions").glob("*.cpp"))


@pytest.mark.contract
def test_standalone_runtime_symbols_do_not_reappear_in_design_or_waveform() -> None:
    offenders: list[str] = []
    for path in _source_files(SRC_ROOT / "design", SRC_ROOT / "waveform"):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if FORBIDDEN_STANDALONE_SYMBOLS.search(text):
            offenders.append(str(path.relative_to(XDEBUG_ROOT)))
    assert offenders == []


@pytest.mark.contract
def test_npi_lifecycle_is_owned_by_unified_engine_server() -> None:
    offenders: list[str] = []
    allowed = Path("src/engine/server.cpp")
    for path in _source_files(SRC_ROOT / "engine", SRC_ROOT / "design", SRC_ROOT / "waveform", SRC_ROOT / "combined"):
        rel = path.relative_to(XDEBUG_ROOT)
        if rel == allowed:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if LIFECYCLE_APIS.search(text):
            offenders.append(str(rel))
    assert offenders == []


@pytest.mark.contract
def test_combined_code_is_helper_only_not_action_entrypoint() -> None:
    offenders: list[str] = []
    for path in _source_files(SRC_ROOT / "combined"):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if COMBINED_ENTRYPOINTS.search(text):
            offenders.append(str(path.relative_to(XDEBUG_ROOT)))
    assert offenders == []
