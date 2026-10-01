import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from parse_skills import SkillParseError, build, parse_skill  # noqa: E402

GOOD_SKILL = """---
name: enrich
description: |
  Enrich brain pages
  with tiers.
triggers:
  - "enrich"
  - " who is this person "
---

# Enrich
"""


def write_skill(root: Path, folder: str, text: str) -> Path:
    path = root / "skills" / folder / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def write_rules(root: Path) -> None:
    for name in ("RESOLVER.md", "_brain-filing-rules.md", "_output-rules.md"):
        (root / "skills" / name).write_text(f"# {name}\n")


def test_parse_skill_pulls_name_description_triggers(tmp_path):
    skill = parse_skill(write_skill(tmp_path, "enrich", GOOD_SKILL))
    assert skill == {
        "name": "enrich",
        "description": "Enrich brain pages with tiers.",
        "triggers": ["enrich", "who is this person"],
        "path": "skills/enrich/SKILL.md",
    }


@pytest.mark.parametrize("text, message", [
    ("# no frontmatter\n", "no YAML frontmatter"),
    ("---\nname: [unclosed\n---\n", "bad YAML"),
    ("---\nname: enrich\ndescription: x\n---\n", "missing triggers"),
    ("---\nname: enrich\ndescription: x\ntriggers: enrich\n---\n", "list of strings"),
    ("---\nname: other\ndescription: x\ntriggers: [a]\n---\n", "does not match its folder"),
])
def test_parse_skill_rejects_bad_files(tmp_path, text, message):
    with pytest.raises(SkillParseError, match=message):
        parse_skill(write_skill(tmp_path, "enrich", text))


def test_build_collects_skills_and_rules(tmp_path):
    write_skill(tmp_path, "enrich", GOOD_SKILL)
    (tmp_path / "skills" / "conventions").mkdir()  # folder with no SKILL.md is skipped
    write_rules(tmp_path)

    result = build(tmp_path)

    assert result["skill_count"] == 1
    assert result["trigger_count"] == 2
    assert set(result["rules"]) == {"resolver", "filing_rules", "output_rules"}


def test_build_fails_when_a_rule_file_is_missing(tmp_path):
    write_skill(tmp_path, "enrich", GOOD_SKILL)
    with pytest.raises(SkillParseError, match="RESOLVER.md not found"):
        build(tmp_path)
