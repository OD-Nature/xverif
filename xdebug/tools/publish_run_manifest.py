#!/usr/bin/env python3
"""Atomically publish an xdebug.run-manifest.v1 for completed run artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                h.update(block)
    elif path.is_dir():
        for member in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
            relative = member.relative_to(path).as_posix()
            if member.is_dir():
                h.update(f"D\n{relative}\n".encode())
            elif member.is_file():
                h.update(f"F\n{relative}\n".encode())
                with member.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        h.update(block)
            else:
                raise ValueError(f"directory contains unsupported member: {member}")
    else:
        raise ValueError(f"resource is neither regular file nor directory: {path}")
    return h.hexdigest()


def resource(path: Path, manifest: Path) -> dict[str, object]:
    return {"path": os.path.relpath(path.resolve(), manifest.parent.resolve()),
            "size_bytes": path.stat().st_size, "sha256": digest(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fsdb", required=True)
    parser.add_argument("--daidir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        payload: dict[str, object] = {"schema_version": "xdebug.run-manifest.v1",
                                      "state": "published",
                                      "resources": {"fsdb": resource(Path(args.fsdb), output)}}
        if args.daidir:
            payload["resources"]["daidir"] = resource(Path(args.daidir), output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as dest:
            json.dump(payload, dest, indent=2, sort_keys=True)
            dest.write("\n")
            dest.flush(); os.fsync(dest.fileno())
        os.replace(tmp, output)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
