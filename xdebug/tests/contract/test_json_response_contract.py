import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
XDEBUG = ROOT / "xdebug"
AUDIT = XDEBUG / "tools" / "audit_json_responses.py"


def _response_files(directory: Path) -> list[Path]:
    files: list[Path] = []
    for path in directory.rglob("*.json"):
        if not path.is_file():
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and "action" in obj and "ok" in obj:
            files.append(path)
        elif (
            isinstance(obj, dict)
            and isinstance(obj.get("response"), dict)
            and "action" in obj["response"]
            and "ok" in obj["response"]
        ):
            files.append(path)
    return files


def _action(path: Path) -> str:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if "action" in obj:
        return obj["action"]
    return obj["response"]["action"]


def test_checked_in_json_responses_have_no_public_redundancy() -> None:
    candidates = [
        XDEBUG / "examples" / "responses",
        XDEBUG / "doc" / "json_after_cleanup",
    ]
    existing = [path for path in candidates if path.exists()]
    assert existing
    result = subprocess.run(
        [sys.executable, str(AUDIT), *map(str, existing)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_after_cleanup_contains_all_runtime_action_samples() -> None:
    after_dir = XDEBUG / "doc" / "json_after_cleanup"
    files = _response_files(after_dir)
    actions = {_action(path) for path in files}
    assert len(actions) == 85
    assert "signal.search" not in actions


def test_public_xout_renderer_has_no_action_specific_branches() -> None:
    renderer = XDEBUG / "src" / "api" / "xout_renderer.cpp"
    text = renderer.read_text(encoding="utf-8")
    assert "action ==" not in text
    for sample in XDEBUG.joinpath("doc", "json_after_cleanup").glob("*.json"):
        action = _action(sample)
        assert f'"{action}"' not in text
