"""CLI smoke tests for user-facing xsva commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(tmp_path, source: str, *args: str):
    path = tmp_path / "input.sva"
    path.write_text(source)
    return subprocess.run(
        [sys.executable, "-m", "xsva", *args, "--file", str(path)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


SOURCE = """
property p_req_ack;
  @(posedge clk) disable iff (!rst_n)
  req |-> ##[1:4] ack;
endproperty

a_req_ack: assert property (p_req_ack);
"""


def test_list_and_scan(tmp_path):
    result = _run(tmp_path, SOURCE, "list")
    assert result.returncode == 0, result.stderr
    assert "p_req_ack" in result.stdout
    assert "a_req_ack" in result.stdout

    result = _run(tmp_path, SOURCE, "scan")
    assert result.returncode == 0, result.stderr
    assert "Property blocks: 1" in result.stdout
    assert "##N" in result.stdout


def test_parse_emit_modes(tmp_path):
    for emit in ("surface-ir", "sequence-ir", "timeline-ir"):
        result = _run(tmp_path, SOURCE, "parse", "--property", "p_req_ack", "--emit", emit)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload
        assert "lowering_status" not in result.stdout
        assert "is_partial" not in result.stdout


def test_explain_markdown(tmp_path):
    result = _run(tmp_path, SOURCE, "explain", "--property", "p_req_ack")
    assert result.returncode == 0, result.stderr
    assert "Property: p_req_ack" in result.stdout
    assert "ack must be true at cycle +1 to +4" in result.stdout
    assert "Lowering" not in result.stdout
    assert "partial lowering" not in result.stdout

    result = _run(tmp_path, SOURCE, "explain", "--property", "p_req_ack", "--markdown")
    assert result.returncode == 0, result.stderr
    assert "# Property: p_req_ack" in result.stdout
    assert "Lowering" not in result.stdout


def test_advanced_sequence_semantic_notes_cli(tmp_path):
    source = """
property p_first;
  req |-> first_match(##[1:4] ack) ##1 done;
endproperty
"""
    result = _run(tmp_path, source, "parse", "--property", "p_first", "--emit", "timeline-ir")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "lowering_status" not in result.stdout
    assert "is_partial" not in result.stdout
    assert payload["semantic_notes"]
    assert "first match at cycle +1 to +4" in payload["semantic_notes"][0]["text"]

    result = _run(tmp_path, source, "explain", "--property", "p_first")
    assert result.returncode == 0, result.stderr
    assert "Semantic notes" in result.stdout
    assert "first match at cycle +1 to +4" in result.stdout
    assert "done must be true 1 clk after that first ack" in result.stdout
    assert "Lowering" not in result.stdout
    assert "partial" not in result.stdout


def test_user_facing_summaries_do_not_expand_paths(tmp_path):
    source = """
property p_path;
  req |-> ##[1:3] ack ##1 done;
endproperty

property p_intersect;
  req |-> (a ##1 b) intersect (c ##1 d);
endproperty
"""
    result = _run(tmp_path, source, "explain", "--property", "p_path")
    assert result.returncode == 0, result.stderr
    assert "ack must be true at cycle +1 to +3" in result.stdout
    assert "done must be true 1 clk after ack" in result.stdout
    assert "Obligations (3 paths)" not in result.stdout
    assert "Path 0" not in result.stdout

    result = _run(tmp_path, source, "explain", "--property", "p_intersect")
    assert result.returncode == 0, result.stderr
    assert "Sequence 1: a must be true; b must be true 1 clk after a." in result.stdout
    assert "Sequence 2: c must be true; d must be true 1 clk after c." in result.stdout
    assert "Relation: sequence 1 and sequence 2 must start on the same clk and end on the same clk." in result.stdout
