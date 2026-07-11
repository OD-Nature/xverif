from pathlib import Path

from skill_test_utils import assert_markdown_links


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/xverif-admin"


def test_admin_links_and_scope() -> None:
    assert_markdown_links(SKILL)
    text = "\n".join(path.read_text() for path in SKILL.rglob("*.md"))
    for term in ("SDK-free", "LSF", "transport", "session", "不自动"):
        assert term in text
    assert "action-reference.md" not in text
