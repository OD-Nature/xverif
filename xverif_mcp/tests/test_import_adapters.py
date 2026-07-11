from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stateless_adapters_do_not_use_cli_runner(monkeypatch, tmp_path):
    from xverif_mcp.runner import StatelessCliRunner

    def fail_run_raw(self, tool, argv, input_text=None, timeout_sec=None,
                     extra_env=None, cwd=None):
        raise AssertionError(f"unexpected CLI runner call: {tool} {argv}")

    monkeypatch.setattr(StatelessCliRunner, "_run_raw", fail_run_raw)

    from xverif_mcp.adapters.xbit import bit_eval
    from xverif_mcp.adapters.xentry import entry_decode
    from xverif_mcp.adapters.xloc import loc_resolve
    from xverif_mcp.adapters.xsva import sva_list

    bit = bit_eval("2 + 3", output_format="json")
    assert bit["ok"] is True
    assert bit["result"]["unsigned"] == 5

    entry = entry_decode(
        config_path=str(ROOT / "xentry/examples/entry.yaml"),
        input_path=str(ROOT / "xentry/examples/fragments.jsonl"),
        output_format="json",
    )
    assert entry["ok"] is True
    assert entry["api_version"] == "xentry.v1"

    map_path = tmp_path / "sim.log.xloc.jsonl"
    map_path.write_text(
        '{"loc_id":"L_00000001","file":"tb/test.sv","line":15,"msg_id":"TEST"}\n',
        encoding="utf-8",
    )
    loc = loc_resolve(
        "L_00000001",
        str(map_path),
        output_format="json",
    )
    assert loc["ok"] is True
    assert loc["line"] == 15

    sva = sva_list(str(ROOT / "xsva/tests/golden_ir/simple_impl/input.sva"),
                   output_format="json")
    assert sva["ok"] is True
    assert sva["items"][0]["name"] == "p_simple"
