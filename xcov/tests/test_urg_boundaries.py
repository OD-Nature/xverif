"""Closed URG artifact and version-probe boundaries, without EDA processes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from xcov import urg_cache
from xcov.errors import XcovError, error_response
from xcov.schemas import validate_response
from xcov.urg_summary import parse_urg_summary, validate_summary_artifacts


# Shape produced by VCS/URG 2023.12-SP2 for fixtures/no_functional/design.sv.
CODE_ONLY_XML = """<session version="1.1">
  <hvp><datadef>
    <metdef name="Line" type="ratio" aggregator="average" builtin="1" />
    <metdef name="Toggle" type="ratio" aggregator="average" builtin="1" />
  </datadef></hvp>
  <old_coverage>
    <scope type="instance" name="code_only">
      <metric name="Line" value="13/13" excl="0" />
      <metric name="Toggle" value="8/10" excl="0" />
    </scope>
    <scope type="Groups" name="top" />
    <scope type="Asserts" name="top" />
    <scope type="assert" name="Statistics" />
  </old_coverage>
</session>
"""
CORE_ARTIFACTS = {"session.xml", "tests.txt", "dashboard.txt", "modlist.txt"}


def _report(path: Path, xml: str = CODE_ONLY_XML) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "session.xml").write_text(xml, encoding="utf-8")
    (path / "tests.txt").write_text(
        "Tests\nTotal tests in report: 1\n"
        "Data from the following tests was used to generate this report\n"
        "code_only/code_only\n",
        encoding="utf-8",
    )
    for name in ("dashboard.txt", "modlist.txt"):
        (path / name).write_text("code_only summary\n", encoding="utf-8")
    return path


def _assert_public_error(exc: XcovError) -> None:
    response = error_response("session.open", "boundary-test", exc.code, exc.message, **exc.detail)
    validate_response("session.open", response)
    assert response["error"]["code"] == exc.code
    assert response["error"]["message"] == exc.message


def test_code_only_summary_allows_absent_group_and_assert_reports(tmp_path):
    report = _report(tmp_path / "report")
    index = parse_urg_summary(report)
    assert index.functional_rows == ()
    assert index.assertion_rows == ()
    assert index.scope_metrics["code_only"]["line"]["covered"] == 13
    assert index.scope_metrics["code_only"]["toggle"]["coverable"] == 10
    assert set(validate_summary_artifacts(report)) == CORE_ARTIFACTS


@pytest.mark.parametrize("filename", ["groups.txt", "asserts.txt"])
@pytest.mark.parametrize("kind", ["empty", "directory", "symlink", "dangling_symlink"])
def test_optional_report_if_present_must_be_regular_nonempty(tmp_path, filename, kind):
    report = _report(tmp_path / "report")
    optional = report / filename
    if kind == "empty":
        optional.touch()
    elif kind == "directory":
        optional.mkdir()
    else:
        target = tmp_path / "outside.txt"
        if kind == "symlink":
            target.write_text("not an owned URG artifact\n", encoding="utf-8")
        optional.symlink_to(target)
    with pytest.raises(XcovError) as raised:
        parse_urg_summary(report)
    assert raised.value.code == "URG_SUMMARY_INCOMPLETE"
    _assert_public_error(raised.value)


@pytest.mark.parametrize("metric", ["Group", "Assert"])
def test_declared_metrics_cannot_hide_missing_reports(tmp_path, metric):
    xml = CODE_ONLY_XML.replace(
        "</datadef>", f'<metdef name="{metric}" type="ratio" builtin="1" /></datadef>',
    )
    if metric == "Group":
        xml = xml.replace(
            '<scope type="Groups" name="top" />',
            '<scope type="Groups" name="top"><attr type="Group Summary" value="0/0" /></scope>',
        )
    report = _report(tmp_path / "report", xml)
    with pytest.raises(XcovError) as raised:
        parse_urg_summary(report)
    assert raised.value.code == "URG_SUMMARY_INCOMPLETE"
    assert raised.value.detail["missing"] == ["groups.txt" if metric == "Group" else "asserts.txt"]
    _assert_public_error(raised.value)


@pytest.mark.parametrize("kind", ["functional", "assertion"])
def test_typed_objects_require_report_even_without_metric_definition(tmp_path, kind):
    if kind == "functional":
        replacement = """<scope type="Groups" name="top">
          <attr type="Group Summary" value="0/1" />
          <scope type="Cover Group" name="code_only::cg">
            <scope type="Covergroup Variant" name="code_only::cg">
              <metric name="Group" value="0/1" excl="0" />
              <attr name="Score" value="0%" />
              <attr name="weight" value="1" />
              <scope type="Coverage Point" name="cp">
                <metric name="Point" value="0/1" excl="0" />
                <attr name="Score" value="0%" /><attr name="weight" value="1" />
              </scope>
            </scope>
          </scope>
        </scope>"""
        xml = CODE_ONLY_XML.replace('<scope type="Groups" name="top" />', replacement)
        missing = "groups.txt"
    else:
        replacement = """<scope type="Asserts" name="top">
          <scope type="Assertion" name="code_only.a">
            <attr type="attempt" value="1" /><attr type="success" value="0" />
          </scope>
        </scope>"""
        xml = CODE_ONLY_XML.replace('<scope type="Asserts" name="top" />', replacement)
        missing = "asserts.txt"
    with pytest.raises(XcovError) as raised:
        parse_urg_summary(_report(tmp_path / "report", xml))
    assert raised.value.code == "URG_SUMMARY_INCOMPLETE"
    assert raised.value.detail["missing"] == [missing]


def test_undeclared_assert_instance_metric_still_requires_assert_report(tmp_path):
    xml = CODE_ONLY_XML.replace(
        '<metric name="Line" value="13/13" excl="0" />',
        '<metric name="Line" value="13/13" excl="0" /><metric name="Assert" value="0/1" excl="0" />',
    )
    with pytest.raises(XcovError) as raised:
        parse_urg_summary(_report(tmp_path / "report", xml))
    assert raised.value.code == "URG_SUMMARY_INCOMPLETE"
    assert raised.value.detail["missing"] == ["asserts.txt"]


@pytest.mark.parametrize("mutation", ["malformed", "no_old_coverage", "empty_declared_groups", "missing_group_summary"])
def test_absent_reports_do_not_relax_xml_validation(tmp_path, mutation):
    xml = CODE_ONLY_XML
    if mutation == "malformed":
        xml = xml.replace("</session>", "")
    elif mutation == "no_old_coverage":
        xml = xml.replace("old_coverage", "unrelated_container")
    elif mutation == "empty_declared_groups":
        xml = xml.replace("</datadef>", '<metdef name="Group" builtin="1" /></datadef>')
    else:
        xml = xml.replace(
            '<scope type="Groups" name="top" />',
            '<scope type="Groups" name="top"><attr type="Group Instance Summary" value="0/1" /></scope>',
        )
    with pytest.raises(XcovError) as raised:
        validate_summary_artifacts(_report(tmp_path / "report", xml))
    assert raised.value.code in {"URG_XML_PARSE_FAILED", "URG_XML_CONTRACT_ERROR"}
    _assert_public_error(raised.value)


def test_code_only_cache_tracks_exact_artifacts_and_rebuilds_tampering(monkeypatch, tmp_path):
    monkeypatch.setattr(urg_cache, "_urg_identity", lambda: {"path": "test-urg", "release": "test"})
    vdb = tmp_path / "sample.vdb"
    vdb.mkdir()
    (vdb / "data").write_text("immutable-vdb", encoding="utf-8")

    class Runner:
        calls = 0

        def run(self, argv, timeout):
            self.calls += 1
            _report(Path(argv[argv.index("-report") + 1]))
            return subprocess.CompletedProcess(argv, 0, "", "")

    runner = Runner()
    options = {"cache_root": tmp_path / "cache", "runner": runner}
    cold, cold_meta = urg_cache.load_cached_urg_summary(str(vdb), **options)
    warm, warm_meta = urg_cache.load_cached_urg_summary(str(vdb), **options)
    assert runner.calls == 1 and not cold_meta["hit"] and warm_meta["hit"]
    assert cold == warm
    entry = Path(cold_meta["entry"])
    manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["artifacts"]) == CORE_ARTIFACTS
    assert manifest["identity"]["parser_schema"] == urg_cache.PARSER_SCHEMA_VERSION
    # Adding an optional report must change the manifest, not escape integrity checks.
    (entry / "report" / "groups.txt").write_text("injected artifact\n", encoding="utf-8")
    _, repaired = urg_cache.load_cached_urg_summary(str(vdb), **options)
    assert not repaired["hit"] and runner.calls == 2
    assert not (Path(repaired["entry"]) / "report" / "groups.txt").exists()
    assert list((tmp_path / "cache" / "quarantine").iterdir())


@pytest.fixture
def version_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    urg_cache._probe_urg.cache_clear()
    binary = tmp_path / "urg"
    binary.write_bytes(b"test vendor launcher")
    try:
        yield str(binary), binary.stat().st_size, binary.stat().st_mtime_ns
    finally:
        urg_cache._probe_urg.cache_clear()


def test_version_probe_uses_full64_and_caches_success(monkeypatch, version_probe):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["timeout"] == 20.0
        return subprocess.CompletedProcess(argv, 0, "URG Version V-test Copyright\n  CovDB version: 1.2\n", "")

    monkeypatch.setattr(urg_cache.subprocess, "run", run)
    first = urg_cache._probe_urg(*version_probe)
    assert urg_cache._probe_urg(*version_probe) == first
    assert calls == [[version_probe[0], "-full64", "-version"]]
    assert first["release"] == "V-test" and first["covdb_version"] == "1.2"


@pytest.mark.parametrize("returncode,stdout,missing", [
    (1, "", ["URG Version", "CovDB version"]),
    (-9, "URG Version V-test\nCovDB version: 1.2\n", []),
    (0, "URG Version V-test\n", ["CovDB version"]),
    (0, "URG Version Copyright\nCovDB version:\n", ["URG Version", "CovDB version"]),
])
def test_version_failure_preserves_exit_status_and_missing_markers(monkeypatch, version_probe, returncode, stdout, missing):
    monkeypatch.setattr(
        urg_cache.subprocess, "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, returncode, stdout, "launcher failed\n"),
    )
    with pytest.raises(XcovError) as raised:
        urg_cache._probe_urg(*version_probe)
    error = raised.value
    assert error.code == "EDA_PROVENANCE_INVALID"
    assert error.detail["returncode"] == returncode
    assert error.detail["missing"] == missing
    assert error.detail["stderr_tail"] == "launcher failed"
    assert error.detail["operation"] == "urg.version"
    _assert_public_error(error)


@pytest.mark.parametrize("failure", ["timeout", "oserror"])
def test_version_probe_exceptions_are_diagnostic_and_schema_valid(monkeypatch, version_probe, failure):
    def run(argv, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 20.0, output=b"partial output\n", stderr=b"partial stderr\n")
        raise OSError("launcher cannot execute")

    monkeypatch.setattr(urg_cache.subprocess, "run", run)
    with pytest.raises(XcovError) as raised:
        urg_cache._probe_urg(*version_probe)
    error = raised.value
    assert error.detail["cause_type"] == ("TimeoutExpired" if failure == "timeout" else "OSError")
    if failure == "timeout":
        assert error.detail["failure_kind"] == "timeout"
        assert error.detail["stdout_tail"] == "partial output"
    _assert_public_error(error)


def test_version_diagnostics_are_bounded_and_redact_credentials(monkeypatch, version_probe):
    monkeypatch.setenv("XCOV_TEST_ACCESS_TOKEN", "sensitive-token-value")
    monkeypatch.setenv("LM_LICENSE_FILE", "27000@private-server:/private/secret.dat")
    output = "x" * 9000 + "\n" + "\n".join([
        "authorization: bearer do-not-publish", "license checkout failed 27000@private-server",
        "sensitive-token-value", "/private/secret.dat", "last ordinary diagnostic",
    ])
    monkeypatch.setattr(
        urg_cache.subprocess, "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, output, output),
    )
    with pytest.raises(XcovError) as raised:
        urg_cache._probe_urg(*version_probe)
    for key in ("stdout_tail", "stderr_tail"):
        detail = raised.value.detail[key]
        assert len(detail) <= urg_cache.VERSION_DIAGNOSTIC_MAX_CHARS
        assert detail.endswith("last ordinary diagnostic")
        for secret in ("sensitive-token-value", "private-server", "secret.dat", "do-not-publish"):
            assert secret not in detail
    _assert_public_error(raised.value)
