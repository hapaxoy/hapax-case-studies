"""
check_parity.py - check that the prompt document and the skills library carry the same facts.

Usage:
    conda run -n <env> python check_parity.py [--world PATH_TO_WORLD_FOLDER]

Checks:
    1. Fact IDs (<!-- facts: ID, ID -->) in prompt_doc.md, in the library's markdown, and in world/:
       the two artefacts must carry the same set, and every ID must exist in world/.
    2. Source markers (<!-- source: ... -->) for material without a fact ID (schema, request history):
       the same set in both artefacts.
    3. Fact IDs named in template headers (-- facts: ...) must exist in world/ and in the library markdown.
    4. Each skill folder has a SKILL.md whose front matter has name = folder name and a one-line description,
       and every SKILL.md points at query-check (the shared check script).
    5. Word count of the prompt document.
Exit code 1 if any check fails.
"""

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent
LIBRARY = OUTPUT / "library"
PROMPT_DOC = OUTPUT / "prompt_doc.md"

FACT_MARKER = re.compile(r"<!--\s*facts:\s*(.*?)\s*-->")
SOURCE_MARKER = re.compile(r"<!--\s*source:\s*(.*?)\s*-->")


def ids_from(text, pattern):
    found = set()
    for match in pattern.finditer(text):
        for item in match.group(1).split(","):
            if item.strip():
                found.add(item.strip())
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", default=str(OUTPUT.parent / "world"))
    args = parser.parse_args()
    world = Path(args.world)
    problems = []

    world_ids = set()
    for path in world.rglob("*.md"):
        world_ids |= ids_from(path.read_text(encoding="utf-8"), FACT_MARKER)

    doc_text = PROMPT_DOC.read_text(encoding="utf-8")
    doc_ids = ids_from(doc_text, FACT_MARKER)
    doc_sources = ids_from(doc_text, SOURCE_MARKER)

    library_md = sorted(LIBRARY.rglob("*.md"))
    lib_text = "\n".join(p.read_text(encoding="utf-8") for p in library_md)
    lib_ids = ids_from(lib_text, FACT_MARKER)
    lib_sources = ids_from(lib_text, SOURCE_MARKER)

    # 1. fact IDs
    print(f"world/ fact IDs:          {len(world_ids)}")
    print(f"prompt_doc.md fact IDs:   {len(doc_ids)}")
    print(f"library fact IDs:         {len(lib_ids)}  ({len(library_md)} markdown files)")
    if doc_ids != lib_ids:
        problems.append(f"fact IDs differ: only in prompt doc {sorted(doc_ids - lib_ids)}, only in library {sorted(lib_ids - doc_ids)}")
    unknown = (doc_ids | lib_ids) - world_ids
    if unknown:
        problems.append(f"fact IDs not in world/: {sorted(unknown)}")
    unused = world_ids - (doc_ids | lib_ids)
    print(f"world IDs used in both:   {len(world_ids & doc_ids & lib_ids)}; not used: {sorted(unused) or 'none'}")

    # 2. source markers
    print(f"source markers: prompt doc {len(doc_sources)}, library {len(lib_sources)}")
    if doc_sources != lib_sources:
        problems.append(f"source markers differ: only in prompt doc {sorted(doc_sources - lib_sources)}, "
                        f"only in library {sorted(lib_sources - doc_sources)}")

    # 3. template headers
    template_ids = set()
    for path in LIBRARY.glob("*/templates/*.sql"):
        # the header's "-- facts:" line and its indented continuation lines
        header_lines = path.read_text(encoding="utf-8").splitlines()
        collecting = False
        for line in header_lines:
            if line.startswith("-- facts:"):
                collecting = True
            elif not line.startswith("--   "):
                collecting = False
            if collecting:
                template_ids |= set(re.findall(r"\b(?:CAL|DEF|REG|TEAM)-[A-Z0-9-]*[A-Z0-9]\b", line))
    bad = template_ids - world_ids
    if bad:
        problems.append(f"template headers name IDs not in world/: {sorted(bad)}")
    missing = template_ids - lib_ids
    if missing:
        problems.append(f"template headers name IDs not in the library markdown: {sorted(missing)}")
    print(f"template header IDs:      {len(template_ids)} (all in world/ and in the library markdown: {not bad and not missing})")

    # 4. skill folders
    skills = sorted(p for p in LIBRARY.iterdir() if p.is_dir())
    for folder in skills:
        skill_md = folder / "SKILL.md"
        if not skill_md.exists():
            problems.append(f"{folder.name}: no SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        front = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
        if not front:
            problems.append(f"{folder.name}: front matter must be name + one-line description")
            continue
        if front.group(1).strip() != folder.name:
            problems.append(f"{folder.name}: name in front matter is {front.group(1)!r}")
        if "query-check" not in text and "query_check" not in text:
            problems.append(f"{folder.name}: SKILL.md does not reference query-check")
    print(f"skills: {len(skills)} ({', '.join(f.name for f in skills)})")

    # 5. word count
    words_all = len(doc_text.split())
    words_content = len(re.sub(r"<!--.*?-->", " ", doc_text).split())
    print(f"prompt_doc.md words: {words_all} including markers, {words_content} without")

    if problems:
        print("\nPROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("\nParity: OK - same fact IDs and same source markers in both artefacts.")


if __name__ == "__main__":
    main()
