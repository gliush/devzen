#!/usr/bin/env python3
"""
Re-extract summaries from the WordPress mirror for episodes with truncated summaries.
Truncation happened because single-quoted YAML strings were broken by ' chars in the text.
"""
import re
import glob
import sys
from pathlib import Path
from bs4 import BeautifulSoup

EPISODES_DIR = Path(__file__).parent.parent / "content" / "episodes"
MIRROR_DIR = Path(__file__).parent.parent.parent / "devzen-mirror" / "devzen.ru"


def mirror_path(number: int) -> Path:
    """Return the mirror HTML path for an episode number."""
    # Episodes 407+ use 3-digit slug in mirror; 1-406 use 4-digit
    if number <= 406:
        slug = f"episode-{number:04d}"
    else:
        slug = f"episode-{number}"
    return MIRROR_DIR / slug / "index.html"


def extract_summary_from_mirror(number: int) -> str | None:
    path = mirror_path(number)
    if not path.exists():
        return None
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    # WordPress puts the summary text in .entry-content
    content_div = soup.find(class_="entry-content")
    if not content_div:
        return None
    # Take only the first non-empty, non-image paragraph — that's the episode summary/excerpt
    for p in content_div.find_all("p"):
        # Skip image-only paragraphs
        if p.find("img") and not p.get_text(strip=True):
            continue
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        # Strip "Читать далее" link suffix if present
        text = re.sub(r'\s*Читать далее\s*→.*$', '', text).strip()
        if text:
            return text
    return None


def is_truncated(summary: str) -> bool:
    """Return True if summary ends mid-word (letter immediately before closing quote)."""
    return bool(re.search(r"[а-яёa-zА-ЯЁA-Z]'$", summary))


def fix_summary_in_file(md_path: Path, new_summary: str) -> bool:
    """Replace the summary value in the frontmatter, using block scalar to avoid quoting issues."""
    text = md_path.read_text(encoding="utf-8")

    # Match the existing summary: value (possibly multi-line YAML flow scalar)
    # Pattern covers: summary: 'text\n  continuation'  OR  summary: text
    pattern = re.compile(
        r"^(summary:\s*)('(?:[^']|'')*'|\"(?:[^\"]|\\.)*\"|[^\n]+(?:\n  [^\n]+)*)",
        re.MULTILINE
    )
    m = pattern.search(text)
    if not m:
        print(f"  WARNING: could not find summary field in {md_path.name}")
        return False

    # Escape any single quotes in new summary by doubling them (YAML single-quote escaping)
    escaped = new_summary.replace("'", "''")
    replacement = f"summary: '{escaped}'"

    new_text = text[:m.start()] + replacement + text[m.end():]
    md_path.write_text(new_text, encoding="utf-8")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    fixed = 0
    skipped = 0
    errors = 0

    md_files = sorted(EPISODES_DIR.glob("*.md"))
    print(f"Scanning {len(md_files)} episode files...")

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")

        # Extract raw summary block
        m = re.search(r"^summary: (.+?)(?=\n[a-z])", text, re.M | re.S)
        if not m:
            continue
        raw = m.group(1).strip()

        if not is_truncated(raw):
            continue

        # Get episode number
        num_m = re.search(r"number: (\d+)", text)
        if not num_m:
            print(f"  SKIP {md_path.name}: no number field")
            skipped += 1
            continue
        number = int(num_m.group(1))

        new_summary = extract_summary_from_mirror(number)
        if not new_summary:
            print(f"  SKIP ep{number}: mirror not found or empty")
            skipped += 1
            continue

        print(f"  ep{number} {md_path.name}: ...{raw[-25:]!r} → ...{new_summary[-25:]!r}")

        if not dry_run:
            ok = fix_summary_in_file(md_path, new_summary)
            if ok:
                fixed += 1
            else:
                errors += 1
        else:
            fixed += 1

    print(f"\nDone. Fixed: {fixed}, Skipped: {skipped}, Errors: {errors}")
    if dry_run:
        print("(dry run — no files written)")


if __name__ == "__main__":
    main()
