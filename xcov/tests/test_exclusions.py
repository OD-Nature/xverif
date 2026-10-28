"""Pure CSV format checks: no NPI, license or generated VDB dependency."""
from __future__ import annotations
import csv
import io
from pathlib import Path
import pytest
from xcov.errors import XcovError
from xcov.exclusions_csv import format_document, parse_directory, parse_document

def _write_csvs(root: Path, *, code_reason: str = "不可达,恢复路径") -> None:
    """写三份 CSV 文件，scope/file/line 匹配真实 exclusion VDB 数据."""
    root.mkdir()
    # code: scope=top, metric=line, line=72 (en = 1; — 唯一匹配)
    quoted = io.StringIO()
    csv.writer(quoted, lineterminator="\n").writerow(
        ["top", "line", "72", "", "", code_reason]
    )
    (root / "code_exclusions.csv").write_text(
        "# schema_version=xcov-code-exclusions.v1\n"
        "# coverage_kind=code\n"
        "scope,metric,line,object,bin,reason\n\n"
        "# source_file=exclusion_fixture.sv\n"
        + quoted.getvalue(),
        encoding="utf-8",
    )
    # functional: scope=top, line=57, covergroup=top::behavior_cg, coverpoint=sel_cp, bin=other
    (root / "functional_exclusions.csv").write_text(
        "# schema_version=xcov-functional-exclusions.v1\n"
        "# coverage_kind=functional\n"
        "scope,line,covergroup,coverpoint,cross,bin,reason\n\n"
        "# source_file=exclusion_fixture.sv\n"
        "top,57,top::behavior_cg,sel_cp,,other,量产不支持\n",
        encoding="utf-8",
    )
    # assertion: scope=top.u_dut, line=40, assertion=a_no_unknown, assertion_kind=assertion
    (root / "assertion_exclusions.csv").write_text(
        "# schema_version=xcov-assertion-exclusions.v1\n"
        "# coverage_kind=assertion\n"
        "scope,line,assertion,assertion_kind,reason\n\n"
        "# source_file=exclusion_fixture.sv\n"
        "top.u_dut,40,a_no_unknown,assertion,复位阶段不采集\n",
        encoding="utf-8",
    )


def test_csv_parser_preserves_standard_csv_quoting_and_source_groups(tmp_path):
    root = tmp_path / "coverage_exclusions"
    _write_csvs(root, code_reason='不可达,"恢复"路径')
    documents = parse_directory(root)
    code = documents[0]
    assert code.groups[0].rows[0]["reason"] == '不可达,"恢复"路径'
    assert parse_document(root / "functional_exclusions.csv", "functional").row_count == 1


def test_csv_multiline_quote_scan_is_linear(monkeypatch):
    from xcov import exclusions_csv

    physical_lines = 10_000
    text = 'scope,metric,line,object,bin,reason\n"' + (
        "reason line\n" * physical_lines
    ) + 'end"\n'
    scanned = 0
    original = exclusions_csv._advance_quote_state

    def counted(chunk, quoted):
        nonlocal scanned
        scanned += len(chunk)
        return original(chunk, quoted)

    monkeypatch.setattr(exclusions_csv, "_advance_quote_state", counted)
    entries = exclusions_csv._logical_entries(text)
    assert len(entries) == 2
    assert scanned <= len(text)


def test_csv_field_budget_fails_before_resolution(tmp_path, monkeypatch):
    from xcov import exclusions_csv

    monkeypatch.setattr(exclusions_csv, "MAX_CSV_FIELD_CHARS", 8)
    root = tmp_path / "coverage_exclusions"
    _write_csvs(root)
    code = root / "code_exclusions.csv"
    code.write_text(
        code.read_text(encoding="utf-8").replace(
            "不可达,恢复路径", "reason-is-too-long",
        ),
        encoding="utf-8",
    )
    with pytest.raises(XcovError) as caught:
        parse_document(code, "code")
    assert caught.value.code == "RESOURCE_BUDGET_EXCEEDED"
    assert caught.value.detail["resource_kind"] == "csv_field_chars"


def test_csv_parser_rejects_noncontiguous_group_and_unknown_column(tmp_path):
    path = tmp_path / "code_exclusions.csv"
    path.write_text(
        "# schema_version=xcov-code-exclusions.v1\n"
        "# coverage_kind=code\n"
        "scope,metric,line,object,bin,reason\n"
        "# source_file=a.sv\n"
        "top,line,1,,,one\n"
        "# source_file=b.sv\n"
        "top,line,2,,,two\n"
        "# source_file=a.sv\n"
        "top,line,3,,,three\n",
        encoding="utf-8",
    )
    with pytest.raises(XcovError, match="not contiguous"):
        parse_document(path, "code")

    path.write_text(
        "# schema_version=xcov-code-exclusions.v1\n"
        "# coverage_kind=code\n"
        "scope,metric,line,object,bin,reason,unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(XcovError, match="header must be exactly"):
        parse_document(path, "code")


def test_formatter_is_stable_and_check_does_not_write(tmp_path):
    root = tmp_path / "coverage_exclusions"
    _write_csvs(root)
    document = parse_directory(root)[0]
    first = format_document(document)
    formatted_path = root / "code_exclusions.csv"
    formatted_path.write_text(first, encoding="utf-8")
    assert format_document(parse_directory(root)[0]) == first


def test_container_csv_is_optional_and_validates_exact_target_shapes(tmp_path):
    root = tmp_path / "coverage_exclusions"
    _write_csvs(root)
    assert parse_directory(root)[-1].groups == []
    path = root / "container_exclusions.csv"
    path.write_text(
        "# schema_version=xcov-container-exclusions.v1\n"
        "# coverage_kind=container\n"
        "target_kind,scope,covergroup,item,expansion_root,reason\n"
        "instance,top.u_dut,,,top,递归展开目标\n"
        "covergroup,top,top::behavior_cg,,,排除整个组\n"
        "coverpoint,top,top::behavior_cg,sel_cp,,排除整个点\n"
        "cross,top,top::behavior_cg,sel_cross,,排除整个交叉\n",
        encoding="utf-8",
    )
    document = parse_directory(root)[-1]
    assert document.row_count == 4
    assert "# source_file=" not in format_document(document)

    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "covergroup,top,top::behavior_cg,,,排除整个组",
            "covergroup,top,top::behavior_cg,sel_cp,,排除整个组",
        ),
        encoding="utf-8",
    )
    with pytest.raises(XcovError, match="empty item"):
        parse_directory(root)
