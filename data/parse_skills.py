"""C1: read GBrain's skills and rule files into data/skills.json.

Every later data step (routing pairs, behavior pairs) reads this one file,
so it must be complete: a skill that fails to parse stops the build instead
of silently dropping out of the training labels.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

RULE_FILES = {
    "resolver": "RESOLVER.md",
    "filing_rules": "_brain-filing-rules.md",
    "output_rules": "_output-rules.md",
}
REQUIRED_FIELDS = ("name", "description", "triggers")
FRONTMATTER = re.compile(r"---\n(.*?)\n---(?:\n|$)", re.DOTALL)


class SkillParseError(Exception):
    pass


def parse_skill(path: Path) -> dict:
    match = FRONTMATTER.match(path.read_text())
    if not match:
        raise SkillParseError(f"{path}: no YAML frontmatter")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillParseError(f"{path}: bad YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillParseError(f"{path}: frontmatter is not a mapping")

    missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
    if missing:
        raise SkillParseError(f"{path}: missing {', '.join(missing)}")
    triggers = meta["triggers"]
    if not isinstance(triggers, list) or not all(isinstance(t, str) for t in triggers):
        raise SkillParseError(f"{path}: triggers must be a list of strings")
    if meta["name"] != path.parent.name:
        raise SkillParseError(f"{path}: name '{meta['name']}' does not match its folder")

    return {
        "name": meta["name"],
        "description": " ".join(meta["description"].split()),
        "triggers": [t.strip() for t in triggers],
        "path": f"skills/{path.parent.name}/SKILL.md",
    }


def gbrain_commit(gbrain_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(gbrain_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def build(gbrain_dir: Path) -> dict:
    skills_dir = gbrain_dir / "skills"
    if not skills_dir.is_dir():
        raise SkillParseError(f"{skills_dir} not found. Set GBRAIN_DIR to a GBrain checkout.")

    skills = [parse_skill(p) for p in sorted(skills_dir.glob("*/SKILL.md"))]
    rules = {}
    for key, filename in RULE_FILES.items():
        rule_path = skills_dir / filename
        if not rule_path.is_file():
            raise SkillParseError(f"{rule_path} not found")
        rules[key] = rule_path.read_text()

    return {
        "gbrain_commit": gbrain_commit(gbrain_dir),
        "skill_count": len(skills),
        "trigger_count": sum(len(s["triggers"]) for s in skills),
        "skills": skills,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gbrain", type=Path, default=Path(os.environ.get("GBRAIN_DIR", "vendor/gbrain")))
    parser.add_argument("--out", type=Path, default=Path("data/skills.json"))
    args = parser.parse_args()

    try:
        result = build(args.gbrain)
    except SkillParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}: {result['skill_count']} skills, {result['trigger_count']} triggers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
