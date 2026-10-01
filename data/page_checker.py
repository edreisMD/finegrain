"""Check that a teacher-written GBrain page is good enough to train on.

A bad example teaches bad behavior, so a page is kept only if all checks
pass. The rules come from GBrain's _brain-filing-rules.md, _output-rules.md
and docs/guides/compiled-truth.md.
"""

import re

import yaml

PATH_LINE = re.compile(r"^File: ([a-z0-9-]+(?:/[a-z0-9.-]+)+\.md)\s*$")
FRONTMATTER = re.compile(r"---\n(.*?)\n---\n", re.DOTALL)
TIMELINE_SPLIT = re.compile(r"^(?:<!-- timeline -->|---)\s*$", re.MULTILINE)
TIMELINE_ENTRY = re.compile(r"^- \*\*\d{4}-\d{2}-\d{2}\*\* \|")
CITATION = re.compile(r"\[Source: [^\]]+\]")
LINK = re.compile(r"\[[^\]]+\]\([a-z0-9-]+/[a-z0-9.-]+\.md\)|\[\[[a-z0-9-]+/[a-z0-9.-]+\]\]")
PLACEHOLDER = re.compile(r"YYYY-MM-DD|\{[a-z_ ]+\}|TODO|lorem ipsum", re.IGNORECASE)


def blocks(body: str) -> list[str]:
    """Split markdown into facts: paragraphs and list items (with their wrapped lines)."""
    out, current = [], []

    def flush():
        if current:
            out.append(" ".join(current))
            current.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or TIMELINE_SPLIT.match(stripped):
            flush()
            continue
        if stripped.startswith(("- ", "* ", "> ")) or re.match(r"\d+\. ", stripped):
            flush()
        current.append(stripped)
    flush()
    return out


def link_only(block: str) -> bool:
    """A 'See also' item like '- [Dana](people/dana.md)' is navigation, not a fact."""
    return not re.search(r"\w", LINK.sub("", block).lstrip("-*> "))


def check_page(output: str) -> list[str]:
    """Return a list of problems. An empty list means the page passes."""
    first, _, page = output.partition("\n")
    path = PATH_LINE.match(first.strip())
    if not path:
        return ["first line must be 'File: <folder>/<slug>.md'"]
    problems = []
    if len(re.findall(r"^File: ", output, re.MULTILINE)) > 1:
        problems.append("more than one page in the reply")
    if path.group(1).startswith("sources/"):
        problems.append("filed in sources/, which is for raw bulk data only")

    page = page.lstrip("\n")
    match = FRONTMATTER.match(page)
    if not match:
        return problems + ["no YAML frontmatter between --- lines"]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return problems + ["frontmatter is not valid YAML"]
    if not isinstance(meta, dict) or not meta.get("type") or not meta.get("title"):
        problems.append("frontmatter needs type and title")

    body = page[match.end():]
    parts = TIMELINE_SPLIT.split(body, maxsplit=1)
    if len(parts) != 2:
        return problems + ["no split between compiled truth and timeline"]
    truth, timeline = parts
    if not blocks(truth):
        problems.append("compiled truth is empty")
    if not any(TIMELINE_ENTRY.match(b) for b in blocks(timeline)):
        problems.append("timeline has no '- **YYYY-MM-DD** |' entry")

    uncited = [b for b in blocks(body) if not CITATION.search(b) and not link_only(b)]
    if uncited:
        problems.append(f"{len(uncited)} fact(s) without [Source: ...], first: {uncited[0][:80]}")
    if not LINK.search(body):
        problems.append("no link to another brain page")
    if PLACEHOLDER.search(page):
        problems.append("contains a placeholder")
    return problems
