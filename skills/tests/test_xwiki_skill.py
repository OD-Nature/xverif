from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from skill_test_utils import assert_markdown_links


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "xwiki"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_xwiki_links_and_prompt_sets() -> None:
    assert_markdown_links(SKILL)
    expected = {"bt", "it", "st", "soc"}
    actual = {path.name for path in (SKILL / "references/prompts").iterdir() if path.is_dir()}
    assert actual == expected
    assert all(list((SKILL / "references/prompts" / level / "prompts").glob("*.md"))
               for level in expected)


def test_xwiki_initializer_and_validator_round_trip(tmp_path: Path) -> None:
    init = _load("xwiki_init", SKILL / "scripts/init_xwiki.py")
    validate = _load("xwiki_validate", SKILL / "scripts/validate_xwiki.py")
    wiki = tmp_path / "wiki"
    assert init.main(["--wiki-dir", str(wiki), "--format", "json"]) == 0
    assert validate.validate_wiki(wiki) == []
    sentinel = wiki / "dv/index.md"
    original = sentinel.read_text(encoding="utf-8")
    assert init.main(["--wiki-dir", str(wiki), "--format", "json"]) == 0
    assert sentinel.read_text(encoding="utf-8") == original


def test_xwiki_validator_reports_schema_link_and_log_errors(tmp_path: Path) -> None:
    init = _load("xwiki_init_bad", SKILL / "scripts/init_xwiki.py")
    validate = _load("xwiki_validate_bad", SKILL / "scripts/validate_xwiki.py")
    wiki = tmp_path / "wiki"
    assert init.main(["--wiki-dir", str(wiki)]) == 0
    page = wiki / "dv/bad.md"
    page.write_text(
        "---\ntype: Topic\ntitle: Bad\ndescription: bad\nobject_type: wrong\n---\n"
        "[missing](missing.md)\n",
        encoding="utf-8",
    )
    log = wiki / "dv/log.md"
    log.write_text(log.read_text(encoding="utf-8") + "\n## not-a-date\n", encoding="utf-8")
    codes = {finding.code for finding in validate.validate_wiki(wiki)}
    assert {"OBJECT_TYPE_INVALID", "LINK_BROKEN", "LOG_DATE_HEADING_INVALID"} <= codes


def test_xwiki_dry_run_does_not_create_directory(tmp_path: Path) -> None:
    init = _load("xwiki_init_dry", SKILL / "scripts/init_xwiki.py")
    wiki = tmp_path / "dry"
    assert init.main(["--wiki-dir", str(wiki), "--dry-run", "--format", "json"]) == 0
    assert not wiki.exists()
