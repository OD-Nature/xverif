from __future__ import annotations

import sys
from pathlib import Path

from skill_test_utils import assert_markdown_links


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "x-npi"
sys.path.insert(0, str(SKILL / "scripts"))

from x_npi.coverage import coverage_summary  # noqa: E402
from x_npi.jsonio import split_limited  # noqa: E402
from x_npi.protocol import apb_summary, axi_summary, stream_summary  # noqa: E402
from x_npi.wave import active, known  # noqa: E402


def test_x_npi_links_and_examples_exist() -> None:
    assert_markdown_links(SKILL)
    examples = {path.name for path in (SKILL / "scripts/examples").glob("*.py")}
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert examples
    assert all(name in text for name in examples)


def test_apb_summary_counts_one_completion_per_access() -> None:
    cfg = {"psel": "sel", "penable": "en", "pready": "rdy", "pwrite": "wr",
           "paddr": "addr", "pwdata": "wdata", "prdata": "rdata"}
    rows = [
        {"time": 1, "values": {"sel": "1", "en": "1", "rdy": "1", "wr": "1",
                                "addr": "10", "wdata": "aa"}},
        {"time": 2, "values": {"sel": "1", "en": "1", "rdy": "1", "wr": "1",
                                "addr": "10", "wdata": "aa"}},
        {"time": 3, "values": {"sel": "0", "en": "0", "rdy": "1", "wr": "0"}},
    ]
    result = apb_summary(rows, cfg)
    assert result["summary"] == {"total": 1, "writes": 1, "reads": 0, "errors": 0}


def test_axi_summary_tracks_write_latency_and_outstanding() -> None:
    cfg = {key: key for key in (
        "awvalid", "awready", "awaddr", "awid", "wvalid", "wready", "wdata",
        "wlast", "bvalid", "bready", "bid", "bresp",
    )}
    rows = [
        {"time": 10, "values": {"awvalid": "1", "awready": "1", "awaddr": "20",
                                  "awid": "1", "wvalid": "1", "wready": "1",
                                  "wdata": "ab", "wlast": "1"}},
        {"time": 14, "values": {"bvalid": "1", "bready": "1", "bid": "1",
                                  "bresp": "0"}},
    ]
    result = axi_summary(rows, cfg)
    assert result["summary"]["writes"] == 1
    assert result["summary"]["max_latency"] == 4
    assert result["summary"]["max_write_outstanding"] == 1


def test_stream_summary_tracks_transfer_stall_and_packet() -> None:
    cfg = {"valid": "v", "ready": "r", "data": "d", "sop": "s", "eop": "e"}
    rows = [
        {"time": 1, "values": {"v": "1", "r": "0", "d": "a"}},
        {"time": 2, "values": {"v": "1", "r": "1", "d": "a", "s": "1"}},
        {"time": 3, "values": {"v": "1", "r": "1", "d": "b", "e": "1"}},
    ]
    result = stream_summary(rows, cfg)
    assert result["summary"] == {"transfers": 2, "stalls": 1, "packets": 1}


def test_coverage_summary_uses_score_rows_and_functional_group_average() -> None:
    rows = [
        {"metric": "line", "type": "npiCovStmtBin", "covered": 3,
         "coverable": 4, "missing": 1},
        {"metric": "functional", "covergroup": "cg", "type": "npiCovCoverpoint",
         "coverage_pct": 50.0},
        {"metric": "functional", "covergroup": "cg", "type": "npiCovCross",
         "coverage_pct": 100.0},
    ]
    result = coverage_summary(rows)
    assert result["metrics"][0]["coverage_pct"] == 75.0
    assert result["functional_groups"][0]["coverage_pct"] == 75.0


def test_value_and_json_helpers_are_deterministic() -> None:
    assert active("1") is True
    assert active("X") is False
    assert known("10xz") is False
    assert split_limited([1, 2, 3], 2) == ([1, 2], True)
