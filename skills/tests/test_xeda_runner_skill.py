from pathlib import Path

from skill_test_utils import assert_markdown_links


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/xeda-runner"


def test_execution_skill_is_explicit_and_linked() -> None:
    assert_markdown_links(SKILL)
    text = (SKILL / "SKILL.md").read_text()
    assert "明确需要执行" in text
    assert "不用于普通" in text
    assert "不自动" in text
