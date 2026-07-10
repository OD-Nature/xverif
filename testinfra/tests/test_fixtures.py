import os
from pathlib import Path

from testinfra.xverif_test.fixtures import (
    FixtureOutput,
    FixtureRegistry,
    FixtureSpec,
    FixtureStore,
    _compatibility_identity,
)


def make_store(root: Path) -> tuple[FixtureStore, FixtureSpec]:
    source = root / "fixture"
    source.mkdir()
    (source / "input.sv").write_text("module top; endmodule\n", encoding="utf-8")
    spec = FixtureSpec(
        id="demo.fixture",
        source_dir="fixture",
        inputs=("*.sv",),
        builder={
            "argv": [
                "python3",
                "-c",
                (
                    "import pathlib; "
                    "p=pathlib.Path(r'{resources}/out.txt'); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_text('ok')"
                ),
            ]
        },
        outputs=(FixtureOutput("text", "out.txt", "file", 1),),
        tool_env=(),
    )
    return FixtureStore(root, FixtureRegistry("xverif-fixture-registry.v1", (spec,))), spec


def test_fingerprint_uses_content_not_mtime(tmp_path: Path) -> None:
    store, spec = make_store(tmp_path)
    first, _ = store.fingerprint(spec)
    input_path = tmp_path / "fixture/input.sv"
    os.utime(input_path, None)
    second, _ = store.fingerprint(spec)
    assert second == first
    input_path.write_text("module changed; endmodule\n", encoding="utf-8")
    third, _ = store.fingerprint(spec)
    assert third != first


def test_prepare_publishes_and_reuses_fixture(tmp_path: Path) -> None:
    store, spec = make_store(tmp_path)
    first = store.prepare(spec.id)
    assert (first / "out.txt").read_text(encoding="utf-8") == "ok"
    second = store.prepare(spec.id)
    assert second == first
    assert store.resolve(spec.id) == first


def test_tool_identity_uses_compatible_major_minor() -> None:
    assert _compatibility_identity("/tools/verdi/V-2023.12-SP2") == "V-2023.12"
    assert _compatibility_identity("") == "unset"
