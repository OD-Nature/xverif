#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


BINARIES = (
    "test_core_types",
    "test_env_config",
    "test_unique_resource",
    "test_action_log",
    "test_file_exchange",
    "test_process_runner",
    "test_session_catalog",
    "test_action_registry",
    "test_request_contract",
    "test_text_response_builder",
    "test_protocol_statistics_filter",
    "test_trace_source_path_formatter",
    "test_common_blocks",
    "test_logic_value",
    "test_event_expr",
    "test_expression",
    "test_rc_generator",
    "test_reset_config",
    "test_sha256",
    "test_axi_transaction_tracker",
)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    xdebug_root = root / "xdebug"
    subprocess.run(["make", "-C", "xdebug", "cpp-unit-binaries"], cwd=root, check=True)
    for name in BINARIES:
        subprocess.run([str(xdebug_root / "build/tests" / name)], cwd=xdebug_root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
