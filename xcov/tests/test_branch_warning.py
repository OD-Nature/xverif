"""URG generated-expression warnings retain elaborated branch identities."""
from __future__ import annotations

from pathlib import Path

import pytest

from xcov.code_export import CoverageExportParseError, parse_metric_report


SCOPE = "top.g_tgt[1].u_tgt"
WARNING = "Warning: the following expressions can not be annotated"


def _report(source: Path, blocks: str, missing: int = 1) -> str:
    return f"""===============================================================================
Module : dut
===============================================================================
Source File(s) :

{source}

Module self-instances :

SCORE BRANCH NAME
0.00 0.00 {SCOPE}

===============================================================================
Module Instance : {SCOPE}
===============================================================================
Branch Coverage for Instance : {SCOPE}
Branches {missing} 0 0.00
{blocks}
"""


def _table(body: str, markers: str = "-1-", values: str = "1") -> str:
    return f"{body}\n\nBranches:\n\n{markers} Status\n{values} Not Covered\n\n"


def test_branch_warning_recovers_real_generate_ternary_expressions(tmp_path):
    # Reduced from real URG output: the source annotation line is blank and
    # the warning has the expanded index that does not appear in source.
    source = tmp_path / "dut.sv"
    first = "assign hcmd_mux[m+1] = addr_owner_q[m] ? trans_hcmd_i[m] : hcmd_mux[m];"
    second = "assign hwdata_mux[m+1] = data_owner_q[m] ? mst_hwdata_i[m] : hwdata_mux[m];"
    source.write_text("\n" * 143 + first + "\n" * 9 + second + "\n")
    blocks = _table(f"144 {first}\n    \n {WARNING}\n -1- (addr_owner_q[2]) ? ...;")
    blocks += _table(f"153 {second}\n    \n {WARNING}\n -1- (data_owner_q[2]) ? ...;")

    payload = parse_metric_report(_report(source, blocks, 2), SCOPE, "branch")

    assert payload["analysis_complete"] is True
    assert payload["gap_count"] == payload["coverage"]["missing"] == 2
    decisions = [group["decision_path"][0] for group in payload["decision_groups"]]
    assert [item["expression"] for item in decisions] == ["addr_owner_q[2]", "data_owner_q[2]"]
    assert [item["at"] for item in decisions] == ["dut.sv:144", "dut.sv:153"]
    assert [item["source"] for item in decisions] == [first, second]
    assert all(item["kind"] == "ternary" for item in decisions)


def test_branch_warning_does_not_merge_different_generate_indices(tmp_path):
    source = tmp_path / "dut.sv"
    statement = "assign value[m] = choose[m] ? a[m] : b[m];"
    source.write_text(statement + "\n")
    blocks = "".join(
        _table(f"1 {statement}\n\n {WARNING}\n -1- (choose[{index}]) ? ...;")
        for index in (1, 2)
    )

    payload = parse_metric_report(_report(source, blocks, 2), SCOPE, "branch")

    assert payload["decision_group_count"] == payload["gap_count"] == 2
    assert [group["decision_path"][0]["expression"] for group in payload["decision_groups"]] == [
        "choose[1]", "choose[2]",
    ]
    assert all(len(group["uncovered"]) == 1 for group in payload["decision_groups"])


def test_branch_warning_coexists_with_inline_markers_on_same_source_line(tmp_path):
    source = tmp_path / "dut.sv"
    statement = "assign value = enable ? (choose[m] ? a : b) : c;"
    source.write_text(statement + "\n")
    body = f"1 {statement}\n -1-\n {WARNING}\n -2- (choose[2]) ? ...;"
    blocks = _table(body, "-1- -2-", "1   0")

    payload = parse_metric_report(_report(source, blocks), SCOPE, "branch")

    path = payload["decision_groups"][0]["decision_path"]
    assert [item["expression"] for item in path] == ["enable", "choose[2]"]
    assert [item["marker"] for item in path] == ["-1-", "-2-"]
    assert payload["decision_groups"][0]["uncovered"][0]["values"] == ["1", "0"]


def test_branch_warning_associates_each_warning_with_its_source_line(tmp_path):
    source = tmp_path / "dut.sv"
    statements = ["if (enable) begin", "  value = choose[m] ? a : b;", "end"]
    source.write_text("\n".join(statements) + "\n")
    body = (f"1 {statements[0]}\n -1-\n2 {statements[1]}\n\n {WARNING}\n"
            " -2- (choose[2]) ? ...;\n3 end")

    payload = parse_metric_report(_report(source, _table(body, "-1- -2-", "1   0")), SCOPE, "branch")

    path = payload["decision_groups"][0]["decision_path"]
    assert [(item["kind"], item["at"], item["expression"]) for item in path] == [
        ("if", "dut.sv:1", "enable"), ("ternary", "dut.sv:2", "choose[2]"),
    ]


@pytest.mark.parametrize("body, reason", [
    (f"{WARNING}\n -1- (choose[2]) ? ...;", "warning source is missing"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}", "expression table is empty"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n -1- choose[2] ? ...;",
     "warning expression is unsupported"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n -1- ((choose[2]) ? ...;",
     "condition is incomplete"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n -1- (choose[2]) extra) ? ...;",
     "warning predicate is malformed"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n -1- ( ) ? ...;",
     "warning predicate is malformed"),
    (f"1 assign value = choose[m];\n{WARNING}\n -1- (choose[2]) ? ...;",
     "warning source is unsupported"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n -2- (choose[2]) ? ...;",
     "marker cannot be mapped to source"),
    (f"1 assign value = choose[m] ? a : b;\n -1-\n{WARNING}\n -1- (choose[2]) ? ...;",
     "marker has conflicting source mappings"),
    (f"1 assign value = choose[m] ? a : b;\n{WARNING}\n"
     " -1- (choose[1]) ? ...;\n -1- (choose[2]) ? ...;",
     "marker has conflicting source mappings"),
])
def test_branch_warning_rejects_missing_unsupported_or_conflicting_mappings(tmp_path, body, reason):
    source = tmp_path / "dut.sv"
    source.write_text("assign value = choose[m] ? a : b;\n")

    with pytest.raises(CoverageExportParseError, match=reason):
        parse_metric_report(_report(source, _table(body)), SCOPE, "branch")


def test_branch_warning_mapping_cannot_leak_into_the_next_status_table(tmp_path):
    source = tmp_path / "dut.sv"
    statement = "assign value[m] = choose[m] ? a[m] : b[m];"
    source.write_text(statement + "\n")
    blocks = _table(f"1 {statement}\n\n {WARNING}\n -1- (choose[1]) ? ...;")
    blocks += _table(f"1 {statement}\n")

    with pytest.raises(CoverageExportParseError, match="marker cannot be mapped to source"):
        parse_metric_report(_report(source, blocks, 2), SCOPE, "branch")


@pytest.mark.parametrize("markers, values", [("-1-", "1"), ("-1- -1-", "1   1")])
def test_branch_warning_rejects_extra_source_markers_and_repeated_status_markers(tmp_path, markers, values):
    source = tmp_path / "dut.sv"
    statement = "assign value = choose[m] ? a : b;"
    source.write_text(statement + "\n")
    body = (f"1 {statement}\n{WARNING}\n"
            " -1- (choose[1]) ? ...;\n -2- (choose[2]) ? ...;")

    with pytest.raises(CoverageExportParseError, match="source markers do not match status header"):
        parse_metric_report(_report(source, _table(body, markers, values)), SCOPE, "branch")
