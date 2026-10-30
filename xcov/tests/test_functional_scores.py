"""TYPE scores checked against captured VCS/URG reports, without EDA execution."""
from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from xcov.actions import _functional_summary_rows, _metrics_from_urg
from xcov.backend import _canonical_scope_metric
from xcov.errors import XcovError
from xcov.urg_summary import _parse_xml


REFERENCE = Path(__file__).resolve().parents[1] / "fixtures/functional_scores/reference"
EXPECTED = {
    "weighted_cg": (66.6667, 1, 3),
    "goals_cg": (25.0, 1, 4),
    "cross_goals_cg": (37.5, 3, 8),
    "type_only_cg": (50.0, 1, 2),
    "instances::cg": (100.0, 2, 2),
    "merged_instances::cg": (100.0, 2, 2),
}


def _index():
    return _parse_xml(REFERENCE / "session.xml", ())


def _changed_index(tmp_path, change):
    root = ET.parse(REFERENCE / "session.xml")
    change(root)
    path = tmp_path / "session.xml"
    root.write(path, encoding="unicode")
    return _parse_xml(path, ())


def _variant(root, suffix):
    return root.find(f".//scope[@type='Covergroup Variant'][@name='functional_scores::{suffix}']")


def test_real_capture_type_scores_match_ordinary_urg_and_unweighted_bin_counts():
    index = _index()
    groups = {row["full_name"]: row for row in index.functional_rows if row["type"] == "npiCovCovergroup"}
    ordinary = {}
    for line in (REFERENCE / "groups.txt").read_text().splitlines():
        fields = line.split()
        if fields and fields[-1].startswith("functional_scores::"):
            ordinary[fields[-1]] = None if fields[0] == "--" else float(fields[0])
    for name, (score, covered, coverable) in EXPECTED.items():
        group = groups[f"functional_scores::{name}"]
        assert group["coverage_pct"] == score
        assert group["coverage_pct"] == pytest.approx(ordinary[group["full_name"]], abs=0.005)
        assert (group["covered"], group["coverable"]) == (covered, coverable)
        assert group["instance"] is None
        assert group["analysis_complete"] is True
    # XML cross group raw Score is 33.3333%, ordinary URG TYPE score is 37.50%.
    xml = ET.parse(REFERENCE / "session.xml")
    cross = _variant(xml, "cross_goals_cg")
    assert cross.find("attr[@name='Score']").get("value") == "33.3333%"
    assert cross.find("metric[@name='Group']").get("value") == "4/12"


def test_zero_weight_bins_count_but_do_not_change_type_score_and_goal_does_not_rescale():
    rows = {row["full_name"]: row for row in _index().functional_rows}
    zero = rows["functional_scores::weighted_cg::zero_weight"]
    assert (zero["weight"], zero["covered"], zero["coverable"]) == (0, 0, 1)
    assert rows["functional_scores::goals_cg::reached"]["coverage_pct"] == 50.0
    assert rows["functional_scores::cross_goals_cg::pair"]["coverage_pct"] == 25.0


def test_empty_xml_type_counts_remain_unknown_without_hiding_normal_groups():
    index = _index()
    rows = {row["full_name"]: row for row in _functional_summary_rows(list(index.functional_rows), "covergroup")}
    for name in ("zero_weight_cg", "empty_cg"):
        row = rows[f"functional_scores::{name}"]
        assert row["analysis_complete"] is False
        assert all(row[field] is None for field in ("coverage_pct", "covered", "coverable", "missing"))
    assert rows["functional_scores::weighted_cg"]["coverage_pct"] == 66.6667
    metric = index.scope_metrics["functional_scores"]["functional"]
    assert metric["analysis_complete"] is False
    assert metric["pct"] is metric["covered"] is metric["coverable"] is None


def test_type_point_names_never_merge_across_covergroups():
    points = _functional_summary_rows(list(_index().functional_rows), "coverpoint")
    matching = [row for row in points if row["coverpoint"].endswith("::cp")]
    assert {row["coverpoint"] for row in matching} == {
        "functional_scores::type_only_cg::cp",
        "functional_scores::instances::cg::cp",
        "functional_scores::merged_instances::cg::cp",
    }
    assert len(matching) == 3


def test_missing_type_weight_is_not_assumed_one(tmp_path):
    def change(root):
        group = _variant(root, "weighted_cg")
        group.remove(group.find("attr[@name='weight']"))
    with pytest.raises(XcovError, match="TYPE weight is missing"):
        _changed_index(tmp_path, change)


def test_missing_type_does_not_fall_back_to_instance(tmp_path):
    def change(root):
        group = _variant(root, "weighted_cg")
        group.set("type", "Cover Group")
    with pytest.raises(XcovError, match="TYPE"):
        _changed_index(tmp_path, change)


def test_scope_type_score_uses_group_weights_once_and_propagates_to_ancestors(tmp_path):
    def change(root):
        for container in root.findall(".//scope[@type='Cover Group']"):
            if container.get("name") in {"functional_scores::empty_cg", "functional_scores::zero_weight_cg"}:
                for child in list(container):
                    container.remove(child)
        _variant(root, "weighted_cg").find("attr[@name='weight']").set("value", "2")
        # Dotted names synthesize their ancestor; each group is counted once.
        for element in root.findall(".//scope"):
            name = element.get("name", "")
            if name == "functional_scores" or name.startswith("functional_scores::"):
                element.set("name", "top." + name)
    index = _changed_index(tmp_path, change)
    leaf = index.scope_metrics["top.functional_scores"]["functional"]
    assert leaf["covered"] == 10
    assert leaf["coverable"] == 21
    assert leaf["pct"] == pytest.approx((25 + 37.5 + 50 + 2 * 66.6667 + 100 + 100) / 7, abs=0.0001)
    assert index.scope_metrics["top"]["functional"] == leaf


def _scope_metric(score_sum, score_weight, covered=1, coverable=2):
    return _canonical_scope_metric("top", "functional", {
        "covered": covered, "coverable": coverable, "missing": coverable - covered,
        "pct": round(score_sum / score_weight, 4) if score_weight else None,
        "analysis_complete": True, "score_sum": score_sum, "score_weight": score_weight,
    })


def test_multiple_roots_use_type_weights_without_double_counting_descendants():
    left = _scope_metric(50.0, 1)
    right = _scope_metric(300.0, 3, covered=2)
    result = _metrics_from_urg({
        "top_a": {"functional": left}, "top_a.deep.block": {"functional": left},
        "top_b": {"functional": right},
    })
    assert result == [{
        "metric": "functional", "covered": 3, "coverable": 4, "missing": 1,
        "coverage_pct": 87.5,
    }]


def test_multiple_roots_round_only_the_final_weighted_score():
    rows = _metrics_from_urg({
        "a": {"functional": _scope_metric(50, 1)},
        "b": {"functional": _scope_metric(4 * 100 / 3, 4)},
        "zero": {"functional": _scope_metric(0, 0, covered=0, coverable=1)},
    })
    assert rows[0]["coverage_pct"] == 36.6667
    assert (rows[0]["covered"], rows[0]["coverable"]) == (2, 5)


def test_unknown_root_propagates_null_without_hiding_known_root():
    unknown = _canonical_scope_metric("unknown", "functional", {
        "covered": None, "coverable": None, "missing": None, "pct": None,
        "analysis_complete": False, "score_sum": None, "score_weight": None,
    })
    rows = _metrics_from_urg({
        "a": {"functional": _scope_metric(50, 1)}, "b": {"functional": unknown},
    })
    assert rows == [{
        "metric": "functional", "covered": None, "coverable": None, "missing": None,
        "coverage_pct": None, "analysis_complete": False,
    }]


@pytest.mark.parametrize("values", [
    {"covered": None, "coverable": None, "missing": None, "pct": None},
    {"covered": 1, "coverable": 2, "missing": 1, "pct": 50, "analysis_complete": False},
    {"covered": 1, "coverable": 2, "missing": 1, "pct": 50, "score_weight": 1},
])
def test_invalid_functional_metric_contract_stays_rejected(values):
    with pytest.raises(XcovError, match="BACKEND_CONTRACT_VIOLATION|scope metric|unverified|numerator"):
        _canonical_scope_metric("top", "functional", values)


@pytest.mark.parametrize("pct,score_sum,score_weight", [(25, 75, 1), (50, 0, 0)])
def test_type_weighted_numerator_must_agree_with_published_score(pct, score_sum, score_weight):
    with pytest.raises(XcovError, match="pct disagrees with TYPE score weights"):
        _canonical_scope_metric("top", "functional", {
            "covered": 1, "coverable": 2, "missing": 1, "pct": pct,
            "score_sum": score_sum, "score_weight": score_weight,
        })


def test_type_and_scope_scores_round_only_when_published(tmp_path):
    def change(root):
        groups = root.find(".//scope[@type='Groups']")
        keep = {"functional_scores::weighted_cg", "functional_scores::goals_cg"}
        for container in groups.findall("scope[@type='Cover Group']"):
            if container.get("name") not in keep:
                groups.remove(container)
        first = _variant(root, "weighted_cg")
        first.find("scope[@name='hit']/attr[@name='weight']").set("value", "1")
        second = _variant(root, "goals_cg")
        second.find("attr[@name='weight']").set("value", "4")
        # Two points at 100% and 0%, weights 1:2, produce an unrounded 100/3.
        second.find("scope[@name='reached']/metric").set("value", "1/1")
        second.find("scope[@name='reached']/attr[@name='Score']").set("value", "100%")
        second.find("scope[@name='unreached']/attr[@name='weight']").set("value", "2")
    index = _changed_index(tmp_path, change)
    groups = {row["full_name"]: row for row in index.functional_rows if row["type"] == "npiCovCovergroup"}
    second = groups["functional_scores::goals_cg"]
    assert second["coverage_pct"] == 33.3333
    assert second["score_value"] == pytest.approx(100 / 3)
    total = index.scope_metrics["functional_scores"]["functional"]
    assert total["score_weight"] == 5
    assert total["score_sum"] == pytest.approx(50 + 4 * (100 / 3))
    assert total["pct"] == 36.6667


def test_rounded_point_score_is_not_reused_as_exact_input(tmp_path):
    def change(root):
        group = _variant(root, "weighted_cg")
        group.find("scope[@name='hit']/metric").set("value", "1/3")
        group.find("scope[@name='hit']/attr[@name='Score']").set("value", "33.3333%")
        group.find("scope[@name='hit']/attr[@name='weight']").set("value", "4")
        group.find("scope[@name='miss']/metric").set("value", "1/2")
        group.find("scope[@name='miss']/attr[@name='Score']").set("value", "50%")
    index = _changed_index(tmp_path, change)
    group = next(row for row in index.functional_rows if row["full_name"] == "functional_scores::weighted_cg")
    assert group["coverage_pct"] == 36.6667


def test_empty_instance_does_not_replace_its_complete_type_counts(tmp_path):
    def change(root):
        group = _variant(root, "weighted_cg")
        instance = group.find("scope[@type='Coverage Instance']")
        for child in list(instance):
            instance.remove(child)
    index = _changed_index(tmp_path, change)
    group = next(row for row in index.functional_rows if row["full_name"] == "functional_scores::weighted_cg")
    assert (group["coverage_pct"], group["covered"], group["coverable"]) == (66.6667, 1, 3)
    assert group["analysis_complete"] is True
    assert all(row["instance"] is None for row in index.functional_rows)


def test_partial_instance_missing_metric_is_still_an_error(tmp_path):
    def change(root):
        group = _variant(root, "weighted_cg")
        instance = group.find("scope[@type='Coverage Instance']")
        instance.remove(instance.find("metric[@name='Group']"))
    with pytest.raises(XcovError, match="missing its score metric"):
        _changed_index(tmp_path, change)


def test_package_and_named_block_type_scopes_do_not_create_design_instances(tmp_path):
    def change(root):
        groups = root.find(".//scope[@type='Groups']")
        keep = {"functional_scores::weighted_cg", "functional_scores::goals_cg", "functional_scores::type_only_cg"}
        for container in groups.findall("scope[@type='Cover Group']"):
            if container.get("name") not in keep:
                groups.remove(container)
        _variant(root, "weighted_cg").set("name", "coverage_pkg::coverage_class::cg")
        _variant(root, "goals_cg").set("name", "functional_scores.middle.coverage::goals_cg")
        _variant(root, "type_only_cg").set("name", "functional_scores.middle.coverage.nested::type_only_cg")
    index = _changed_index(tmp_path, change)
    assert index.xml_instances == ("functional_scores",)
    assert [row["full_name"] for row in index.scopes] == ["functional_scores"]
    assert set(index.scope_metrics) == {
        "functional_scores", "coverage_pkg",
        "functional_scores.middle.coverage", "functional_scores.middle.coverage.nested",
    }
    package = index.scope_metrics["coverage_pkg"]["functional"]
    assert (package["covered"], package["coverable"], package["pct"]) == (1, 3, 66.6667)
    block = index.scope_metrics["functional_scores.middle.coverage"]["functional"]
    assert (block["covered"], block["coverable"], block["pct"]) == (2, 6, 37.5)
    assert block["score_weight"] == 2
    assert index.scope_metrics["functional_scores"]["functional"] == block
    assert {row["scope"] for row in index.functional_rows} == {
        "coverage_pkg", "functional_scores.middle.coverage", "functional_scores.middle.coverage.nested",
    }
