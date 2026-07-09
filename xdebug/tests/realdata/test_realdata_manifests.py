from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from runner import (
    ArtifactWriter,
    CliRunner,
    InvariantError,
    assert_invariants,
    load_manifest,
)
from runner.manifests import TestManifest as XdebugManifest


def _manifest_paths(root: Path) -> list[Path]:
    manifest_dir = root / "tests" / "realdata" / "manifests"
    return sorted(manifest_dir.glob("*.yaml"))


def _load_manifests(root: Path) -> list[XdebugManifest]:
    manifests = [load_manifest(path) for path in _manifest_paths(root)]
    if not manifests:
        raise AssertionError("no realdata manifests found")
    return manifests


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "realdata_manifest" not in metafunc.fixturenames:
        return
    xdebug_root = Path(__file__).resolve().parents[2]
    manifests = _load_manifests(xdebug_root)
    metafunc.parametrize(
        "realdata_manifest",
        manifests,
        ids=[manifest.name for manifest in manifests],
    )


def _require_resource(manifest: XdebugManifest) -> None:
    if manifest.fsdb is not None:
        assert manifest.fsdb.is_file(), "missing realdata FSDB: %s" % manifest.fsdb
    if manifest.daidir is not None:
        assert manifest.daidir.is_dir(), "missing realdata daidir: %s" % manifest.daidir


def _query(
    cli_runner: CliRunner,
    request: dict[str, Any],
    *,
    manifest: XdebugManifest,
    case_name: str,
    artifact_root: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = cli_runner.run(
        request,
        timeout_sec=manifest.timeout_sec,
    )
    response = result.response
    if (
        result.returncode == 0
        and not result.timed_out
        and isinstance(response, dict)
    ):
        return response
    artifact_dir = ArtifactWriter(artifact_root).write(
        case_name,
        result,
        manifest=manifest.path,
        extra=extra,
    )
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout:\n%s\nstderr:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


@pytest.mark.realdata
@pytest.mark.smoke
@pytest.mark.slow
def test_realdata_manifest_invariants(
    cli_runner: CliRunner,
    artifact_root: Path,
    realdata_manifest: XdebugManifest,
) -> None:
    manifest = realdata_manifest
    _require_resource(manifest)
    target: dict[str, str] = {}
    if manifest.fsdb is not None:
        target["fsdb"] = str(manifest.fsdb)
    if manifest.daidir is not None:
        target["daidir"] = str(manifest.daidir)

    open_response = _query(
        cli_runner,
        {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": target,
            "args": {"name": manifest.name},
        },
        manifest=manifest,
        case_name=manifest.name + "-session-open",
        artifact_root=artifact_root,
    )
    try:
        assert_invariants(
            open_response,
            {
                "ok": True,
                "required_paths": ["data.session.id", "summary.mode"],
            },
        )
        session = open_response.get("session") or open_response["data"]["session"]
        session_id = session["id"]
        session_target = {"session_id": session_id}

        for query in manifest.queries:
            query_name = query.get("name", query["action"])
            request = {
                "api_version": "xdebug.v1",
                "action": query["action"],
                "target": session_target,
                "args": query.get("args", {}),
            }
            if "limits" in query:
                request["limits"] = query["limits"]
            response = _query(
                cli_runner,
                request,
                manifest=manifest,
                case_name=manifest.name + "-" + query_name,
                artifact_root=artifact_root,
                extra={"query": query},
            )
            try:
                assert_invariants(response, query.get("expect", {"ok": True}))
            except InvariantError as exc:
                result = cli_runner.run(request, timeout_sec=manifest.timeout_sec)
                result.response = response
                result.normalized_response = response
                artifact_dir = ArtifactWriter(artifact_root).write(
                    manifest.name + "-" + query_name + "-invariant",
                    result,
                    manifest=manifest.path,
                    extra={"query": query, "invariant_error": str(exc)},
                )
                pytest.fail(
                    "%s invariant failed: %s; artifacts=%s"
                    % (query_name, exc, artifact_dir)
                )
    finally:
        cli_runner.run(
            {
                "api_version": "xdebug.v1",
                "action": "session.kill",
                "target": {"session_id": manifest.name},
            },
            timeout_sec=60,
        )
