"""Strict run-manifest validation for coverage database inputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from .errors import XcovError

Json = Dict[str, Any]


def _canonical(path: str) -> Path:
    try:
        return Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise XcovError("RESOURCE_PROVENANCE_MISMATCH",
                        "run manifest is missing or cannot be resolved") from exc


def _hash_file(path: Path, digest: "hashlib._Hash") -> None:
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)


def resource_sha256(path: Path) -> str:
    """Return the content digest used by ``xcov.run-manifest.v1``.

    Files hash their bytes. Directories use a deterministic, sorted tree hash
    over relative names, entry types, and file bytes, so a VDB directory is
    represented by its content rather than by volatile metadata.
    """
    digest = hashlib.sha256()
    if path.is_file():
        _hash_file(path, digest)
        return digest.hexdigest()
    if not path.is_dir():
        raise OSError(f"resource is neither a file nor a directory: {path}")
    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        dirs.sort()
        files.sort()
        for name in dirs:
            relative = (root_path / name).relative_to(path).as_posix()
            digest.update(b"D\\0" + relative.encode("utf-8") + b"\\0")
        for name in files:
            resource = root_path / name
            relative = resource.relative_to(path).as_posix()
            digest.update(b"F\\0" + relative.encode("utf-8") + b"\\0")
            _hash_file(resource, digest)
    return digest.hexdigest()


def _mismatch(message: str, manifest: Json) -> XcovError:
    return XcovError("RESOURCE_PROVENANCE_MISMATCH", message, manifest=manifest)


def validate_run_manifest(target: Json) -> Json | None:
    """Validate optional ``xcov.run-manifest.v1`` against ``target.vdb``.

    The declared resource path is relative to the manifest file.  A mismatch
    raises before the caller opens the VDB/NPI backend.
    """
    run_manifest = target.get("run_manifest")
    if run_manifest is None:
        return None
    if not isinstance(run_manifest, str) or not run_manifest:
        raise _mismatch("target.run_manifest must be a non-empty path", {})
    manifest_path = _canonical(run_manifest)
    try:
        details: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _mismatch("run manifest is not valid JSON", {}) from exc
    if not isinstance(details, dict):
        raise _mismatch("run manifest must be a JSON object", {})
    if (details.get("schema_version") != "xcov.run-manifest.v1" or
            details.get("state") != "published"):
        raise _mismatch("run manifest must be xcov.run-manifest.v1 in published state", details)

    resources = details.get("resources")
    declared = resources.get("vdb") if isinstance(resources, dict) else None
    if not isinstance(declared, dict):
        raise _mismatch("run manifest does not declare resource: vdb", details)
    relative = declared.get("path")
    size = declared.get("size_bytes")
    expected_sha = declared.get("sha256")
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute() or
            not isinstance(size, int) or size < 0 or
            not isinstance(expected_sha, str) or len(expected_sha) != 64):
        raise _mismatch("run manifest has incomplete resource declaration: vdb", details)

    vdb = target.get("vdb")
    if not isinstance(vdb, str) or not vdb:
        raise _mismatch("target.vdb is required when run_manifest is provided", details)
    expected_path = _canonical(str(manifest_path.parent / relative))
    actual_path = _canonical(vdb)
    if expected_path != actual_path:
        details.update({"resource": "vdb", "expected_path": relative})
        raise _mismatch("run manifest resource path does not match target: vdb", details)
    actual_size = actual_path.stat().st_size
    if actual_size != size:
        details.update({"resource": "vdb", "expected_size_bytes": size,
                        "actual_size_bytes": actual_size})
        raise _mismatch("run manifest resource size does not match target: vdb", details)
    try:
        actual_sha = resource_sha256(actual_path)
    except OSError as exc:
        raise _mismatch("run manifest resource cannot be hashed: vdb", details) from exc
    if actual_sha != expected_sha:
        details.update({"resource": "vdb", "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha})
        raise _mismatch("run manifest resource SHA-256 does not match target: vdb", details)
    details["manifest_path"] = str(manifest_path)
    return details
