from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import pytest

from .catalog import Catalog, CatalogError
from .gates import ExecutionPlan, build_plan, filter_plan
from .items import ExternalSuiteItem
from .fixtures import FixtureError, FixtureStore, load_default_registry
from .reports import ResultManager
from .resources import apply_xdist_resource_group


DEFAULT_CATALOG = Path("testinfra/catalog.v1.yaml")
DEFAULT_SCHEMA = Path("testinfra/schemas/catalog.v1.schema.json")
_RESULT_MANAGER: ResultManager | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("xverif", "catalog-driven xverif test orchestration")
    group.addoption("--xverif-gate", choices=("fast", "regression", "nightly"))
    group.addoption("--xverif-suite", action="append", default=[])
    group.addoption("--xverif-plan", action="store_true", default=False)
    group.addoption("--xverif-catalog", default=str(DEFAULT_CATALOG))
    group.addoption("--xverif-prepare", action="append", default=[])
    group.addoption("--xverif-fixture-validation", action="store_true", default=False)
    group.addoption("--xverif-all-fixtures", action="store_true", default=False)
    group.addoption("--xverif-changed")
    group.addoption("--rerun-failed", dest="xverif_rerun_failed")
    group.addoption("--xverif-fixture-clean", action="store_true", default=False)
    group.addoption("--xverif-results-clean", action="store_true", default=False)


def _repo_root(config: pytest.Config) -> Path:
    return Path(str(config.rootpath)).resolve()


def _load_catalog(config: pytest.Config) -> Catalog:
    root = _repo_root(config)
    configured = Path(config.getoption("--xverif-catalog"))
    catalog_path = configured if configured.is_absolute() else root / configured
    schema_path = root / DEFAULT_SCHEMA
    return Catalog.load(catalog_path, schema_path)


def _requested_operation(config: pytest.Config) -> str | None:
    operations: list[str] = []
    if config.getoption("--xverif-gate"):
        operations.append("gate")
    if config.getoption("--xverif-prepare"):
        operations.append("prepare")
    if config.getoption("--xverif-fixture-validation"):
        operations.append("fixture-validation")
    if config.getoption("xverif_rerun_failed"):
        operations.append("rerun-failed")
    if config.getoption("--xverif-fixture-clean"):
        operations.append("fixture-clean")
    if config.getoption("--xverif-results-clean"):
        operations.append("results-clean")
    if len(operations) > 1:
        raise pytest.UsageError(
            "xverif operations are mutually exclusive: " + ", ".join(operations)
        )
    return operations[0] if operations else None


def _ensure_xverif_state(config: pytest.Config) -> str | None:
    existing = getattr(config, "_xverif_operation", None)
    if existing is not None:
        return existing
    operation = _requested_operation(config)
    if operation is None:
        return None
    try:
        catalog = _load_catalog(config)
    except CatalogError as exc:
        raise pytest.UsageError(str(exc)) from exc
    config._xverif_catalog = catalog  # type: ignore[attr-defined]
    if operation == "gate":
        gate = config.getoption("--xverif-gate")
        try:
            plan = filter_plan(
                build_plan(catalog, gate),
                list(config.getoption("--xverif-suite")),
            )
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from exc
        config._xverif_plan = plan  # type: ignore[attr-defined]
    elif config.getoption("--xverif-plan"):
        raise pytest.UsageError("--xverif-plan requires --xverif-gate")
    config._xverif_operation = operation  # type: ignore[attr-defined]
    return operation


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    global _RESULT_MANAGER
    operation = _ensure_xverif_state(config)
    if operation is None:
        raise pytest.UsageError(
            "bare pytest is not an xverif test operation; use --xverif-gate "
            "fast|regression|nightly, --xverif-plan with a gate, or an explicit "
            "fixture/results operation"
        )
    if (
        operation == "gate"
        and not config.getoption("--xverif-plan")
        and not config.getoption("collectonly")
        and not hasattr(config, "workerinput")
    ):
        plan: ExecutionPlan = config._xverif_plan  # type: ignore[attr-defined]
        catalog: Catalog = config._xverif_catalog  # type: ignore[attr-defined]
        _RESULT_MANAGER = ResultManager(_repo_root(config), plan.gate, catalog.version)
        config._xverif_results = _RESULT_MANAGER  # type: ignore[attr-defined]
        if getattr(config.option, "xmlpath", None) is None:
            config.option.xmlpath = str(_RESULT_MANAGER.run_dir / "junit.xml")
    elif operation == "gate" and hasattr(config, "workerinput"):
        worker_run_dir = config.workerinput.get("xverif_run_dir")  # type: ignore[attr-defined]
        if worker_run_dir:
            config._xverif_results = ResultManager.attach(  # type: ignore[attr-defined]
                _repo_root(config), Path(worker_run_dir)
            )


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> int | None:
    operation = _ensure_xverif_state(config)
    if operation == "gate" and config.getoption("--xverif-plan"):
        plan: ExecutionPlan = config._xverif_plan  # type: ignore[attr-defined]
        print(plan.render())
        return pytest.ExitCode.OK
    if operation is None:
        return None
    if operation != "gate":
        root = _repo_root(config)
        try:
            store = FixtureStore(root, load_default_registry(root))
            if operation == "prepare":
                requested = list(config.getoption("--xverif-prepare"))
                fixture_ids = (
                    [spec.id for spec in store.registry.fixtures]
                    if requested == ["all-generated"]
                    else requested
                )
                for fixture_id in fixture_ids:
                    path = store.prepare(fixture_id)
                    print(f"prepared {fixture_id}: {path.relative_to(root)}")
                return pytest.ExitCode.OK
            if operation == "fixture-validation":
                if not config.getoption("--xverif-all-fixtures"):
                    raise pytest.UsageError(
                        "fixture-validation currently requires --xverif-all-fixtures"
                    )
                for spec in store.registry.fixtures:
                    path = store.prepare(spec.id, rebuild=True)
                    print(f"validated {spec.id}: {path.relative_to(root)}")
                return pytest.ExitCode.OK
            if operation == "fixture-clean":
                store.clean()
                print("xverif fixture cache removed")
                return pytest.ExitCode.OK
            if operation == "results-clean":
                results = root / ".xverif-test-results"
                if results.exists():
                    shutil.rmtree(results)
                print("xverif test results removed")
                return pytest.ExitCode.OK
        except FixtureError as exc:
            raise pytest.UsageError(str(exc)) from exc
        raise pytest.UsageError(f"xverif operation {operation!r} is not implemented")
    return None


@pytest.fixture
def xverif_fixture_store(request: pytest.FixtureRequest) -> FixtureStore:
    root = _repo_root(request.config)
    return FixtureStore(root, load_default_registry(root))


@pytest.fixture
def xverif_fixture(xverif_fixture_store: FixtureStore) -> Any:
    return xverif_fixture_store.resolve


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    catalog: Catalog = config._xverif_catalog  # type: ignore[attr-defined]
    plan: ExecutionPlan = config._xverif_plan  # type: ignore[attr-defined]
    selected_ids = plan.selected_ids()
    selected_commands = [
        selected.suite
        for selected in plan.suites
        if selected.suite.runner.get("kind") == "command"
    ]
    repo_root = _repo_root(config)
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    unmapped: list[str] = []
    for item in items:
        suite = catalog.owner_for_path(Path(str(item.path)), repo_root)
        if suite is None:
            unmapped.append(item.nodeid)
            continue
        item.user_properties.append(("xverif_suite", suite.id))
        setattr(item, "_xverif_suite_id", suite.id)
        if suite.id in selected_ids:
            apply_xdist_resource_group(item, suite)
            kept.append(item)
        else:
            deselected.append(item)
    if unmapped:
        raise pytest.UsageError(
            "collected pytest items are missing catalog ownership:\n  "
            + "\n  ".join(sorted(unmapped))
        )
    if selected_commands:
        if not items:
            raise pytest.UsageError("cannot attach external suite items without a pytest session")
        parent = items[0].session
        for suite in selected_commands:
            external = ExternalSuiteItem.from_suite(parent, suite)
            apply_xdist_resource_group(external, suite)
            kept.append(external)
    items[:] = kept
    if deselected:
        config.hook.pytest_deselected(items=deselected)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _RESULT_MANAGER is not None:
        _RESULT_MANAGER.record_report(report)


def pytest_configure_node(node: Any) -> None:
    if _RESULT_MANAGER is not None:
        node.workerinput["xverif_run_dir"] = str(_RESULT_MANAGER.run_dir)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _RESULT_MANAGER is not None and not hasattr(session.config, "workerinput"):
        _RESULT_MANAGER.finish(exitstatus)


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    if _RESULT_MANAGER is not None and not hasattr(config, "workerinput"):
        terminalreporter.write_line(
            "xverif results: "
            + _RESULT_MANAGER.run_dir.relative_to(_repo_root(config)).as_posix()
        )
