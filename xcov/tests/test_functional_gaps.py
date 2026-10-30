"""Functional gap table boundaries from real VCS/URG AHB reports."""
from __future__ import annotations

import pytest

from xcov.errors import XcovError
from xcov.gap_export import parse_urg_gap_report


# Reduced from the same full64 URG expand_bins report produced for five real
# AHB parameter environments. The static ignore bins follow the uncovered
# cross table without a dashed separator between the two tables.
CAPTURED_CROSS = """Group : ahb_matrix_pkg::ahb_matrix_coverage::cg_data
Summary for Cross size_lane_rw

Samples crossed: cp_size cp_lane cp_rw
CATEGORY                           EXPECTED UNCOVERED COVERED PERCENT MISSING
TOTAL                              14       12        2       14.29   12
Automatically Generated Cross Bins 14       12        2       14.29   12
User Defined Cross Bins            0        0         0

Decompressed uncovered bins for size_lane_rw

cp_size     cp_lane cp_rw COUNT AT LEAST
halfword    lane_0  write 0     1
halfword    lane_0  read  0     1
halfword    lane_2  write 0     1
halfword    lane_2  read  0     1
byte_access lane_0  write 0     1
byte_access lane_0  read  0     1
byte_access lane_1  write 0     1
byte_access lane_1  read  0     1
byte_access lane_2  write 0     1
byte_access lane_2  read  0     1
byte_access lane_3  write 0     1
byte_access lane_3  read  0     1

User Defined Cross Bins for size_lane_rw

Excluded/Illegal bins

NAME           COUNT STATUS
half_unaligned 0     Excluded
word_unaligned 0     Excluded

-------------------------------------------------------------------------------
"""


def test_functional_cross_excluded_bin_table_does_not_become_gaps(tmp_path):
    report = tmp_path / "grpinfo.txt"
    report.write_text(CAPTURED_CROSS)
    rows = parse_urg_gap_report("functional", report)

    assert len(rows) == 12
    assert {row["bin"] for row in rows} == {
        f"[{size}] [lane_{lane}] [{direction}]"
        for size, lanes in (("halfword", (0, 2)), ("byte_access", (0, 1, 2, 3)))
        for lane in lanes
        for direction in ("write", "read")
    }
    assert all(row["cross"] == "size_lane_rw" for row in rows)
    assert all(row["count"] == 0 and row["coverable"] == 1 for row in rows)


@pytest.mark.parametrize("change,expected_count,parsed", [
    (lambda text: text.replace("halfword    lane_0  write 0     1\n", ""), 12, 11),
    (lambda text: text.replace(
        "User Defined Cross Bins            0        0         0",
        "User Defined Cross Bins            1        1         0",
    ), 13, 12),
])
def test_functional_cross_table_boundary_keeps_total_validation(tmp_path, change, expected_count, parsed):
    report = tmp_path / "grpinfo.txt"
    report.write_text(change(CAPTURED_CROSS))
    with pytest.raises(XcovError, match="gap count does not match") as caught:
        parse_urg_gap_report("functional", report)
    assert caught.value.code == "URG_DETAIL_PARSE_INCOMPLETE"
    assert caught.value.detail["expected_count"] == expected_count
    assert caught.value.detail["parsed"] == parsed


@pytest.mark.parametrize("replacement", [
    "Unknown report section\nUser Defined Cross Bins for size_lane_rw",
    "User Defined Cross Bins for another_cross",
])
def test_functional_cross_unknown_trailing_text_fails_closed(tmp_path, replacement):
    report = tmp_path / "grpinfo.txt"
    report.write_text(CAPTURED_CROSS.replace("User Defined Cross Bins for size_lane_rw", replacement))
    with pytest.raises(XcovError, match="compressed or unsupported"):
        parse_urg_gap_report("functional", report)
