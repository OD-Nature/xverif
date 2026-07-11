from pathlib import Path

from testinfra.xverif_test.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


def test_all_declared_pytest_paths_exist() -> None:
    catalog = Catalog.load(
        ROOT / "testinfra/catalog.v1.yaml",
        ROOT / "testinfra/schemas/catalog.v1.schema.json",
    )
    missing = [
        path
        for suite in catalog.suites
        for path in suite.pytest_paths()
        if not (ROOT / path).exists()
    ]
    assert missing == []
