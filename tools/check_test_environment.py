#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from testinfra.xverif_test.dependencies import (  # noqa: E402
    DependencyError,
    load_default_dependency_registry,
    probe_dependencies,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check xverif suite and fixture dependencies")
    parser.add_argument("--python-only", action="store_true")
    parser.add_argument("--gate", choices=("fast", "regression", "nightly"))
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--prepare", action="append", default=[])
    parser.add_argument("--fixture-validation", action="store_true")
    parser.add_argument("--all-fixtures", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    registry = load_default_dependency_registry(ROOT)
    statuses = probe_dependencies(["python_test_runtime"], ROOT, registry=registry)
    required_errors: list[str] = []
    consumers: dict[str, list[str]] = {"python_test_runtime": ["test infrastructure"]}
    required_dependencies = {"python_test_runtime"}
    if not statuses["python_test_runtime"].available:
        required_errors.append("python_test_runtime: " + statuses["python_test_runtime"].reason)
    if not args.python_only and not required_errors:
        from testinfra.xverif_test.catalog import Catalog
        from testinfra.xverif_test.fixtures import (
            FixtureError,
            FixtureStore,
            load_default_registry,
        )
        from testinfra.xverif_test.gates import build_plan, filter_plan

        catalog = Catalog.load(ROOT / "testinfra/catalog.v1.yaml", ROOT / "testinfra/schemas/catalog.v1.schema.json")
        store = FixtureStore(ROOT, load_default_registry(ROOT))
        if args.gate:
            plan = filter_plan(build_plan(catalog, args.gate), args.suite)
            host_dependencies = {"npi", "mcp_process", "real_lsf"}
            if any(host_dependencies & set(selected.suite.capabilities) for selected in plan.suites) and os.environ.get("XVERIF_TEST_EXECUTION_ENV") != "host":
                required_errors.append("selected suites require XVERIF_TEST_EXECUTION_ENV=host")
            for selected in plan.suites:
                result = probe_dependencies(selected.suite.capabilities, ROOT, registry=registry)
                statuses.update(result)
                for name in result:
                    consumers.setdefault(name, []).append(selected.suite.id)
                    if selected.required:
                        required_dependencies.add(name)
                reasons = [f"{name}: {status.reason}" for name, status in result.items() if not status.available]
                for fixture_id in selected.suite.fixtures:
                    try:
                        store.resolve(fixture_id)
                    except FixtureError as exc:
                        reasons.append(str(exc))
                if reasons and selected.required:
                    required_errors.append(selected.suite.id + ": " + "; ".join(reasons))
        if args.prepare or args.fixture_validation:
            fixture_ids = [spec.id for spec in store.registry.fixtures] if args.all_fixtures or args.prepare == ["all-generated"] else args.prepare
            for fixture_id in fixture_ids:
                spec = store.registry.by_id(fixture_id)
                env = store.effective_builder_env(spec)
                result = probe_dependencies(spec.build_capabilities, ROOT, registry=registry, effective_env=env)
                statuses.update(result)
                for name in result:
                    consumers.setdefault(name, []).append(fixture_id)
                    required_dependencies.add(name)
                required_errors.extend(f"{fixture_id}: {name}: {status.reason}" for name, status in result.items() if not status.available)
    payload = {
        "ok": not required_errors,
        "dependencies": [
            {
                "name": name,
                "available": status.available,
                "outcome": "ok" if status.available else ("error" if name in required_dependencies else "skip"),
                "reason": status.reason,
                "source": status.source,
                "consumers": sorted(set(consumers.get(name, []))),
            }
            for name, status in sorted(statuses.items())
        ],
        "errors": required_errors,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for row in payload["dependencies"]:
            print(f"{row['outcome'].upper()} {row['name']}: {row['reason']}")
        for error in required_errors:
            print("ERROR " + error, file=sys.stderr)
    return 0 if not required_errors else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DependencyError as exc:
        print(f"dependency contract error: {exc}", file=sys.stderr)
        raise SystemExit(2)
