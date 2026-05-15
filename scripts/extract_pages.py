#!/usr/bin/env python3
"""
extract_pages.py — extract static pages from the DevZen WordPress mirror
and write them as Hugo content files.

Pages extracted: guests, contact, live
"""

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
import frontmatter

PAGES = [
    {"slug": "guests",  "url": "/guests/"},
    {"slug": "contact", "url": "/contact/"},
    {"slug": "live",    "url": "/live/"},
]

STRIP_TAGS = {"script", "style"}
STRIP_CLASSES = {"powerpress_player"}


def strip_cruft(content_tag):
    """Remove scripts, styles, empty <p>s and powerpress elements — same rules as episode extractor."""
    for tag in content_tag.find_all(STRIP_TAGS):
        tag.decompose()
    for tag in content_tag.find_all(class_=lambda c: c and any(cls in c for cls in STRIP_CLASSES)):
        tag.decompose()
    # Remove empty <p> tags
    for p in content_tag.find_all("p"):
        if not p.get_text(strip=True) and not p.find():
            p.decompose()
    # Strip ?ver=X.X.X from any remaining attrs
    for tag in content_tag.find_all(True):
        for attr in ("src", "href"):
            val = tag.get(attr, "")
            if "?ver=" in val:
                tag[attr] = val.split("?ver=")[0]
    return content_tag


def rewrite_paths(content_tag, mirror_dir: Path, uploads_out: Path, dry_run: bool):
    """Rewrite relative image srcs to /uploads/... and copy images; fix internal relative links."""
    # Rewrite img src: ../wp-content/uploads/YEAR/MO/file.jpg → /uploads/YEAR/MO/file.jpg
    for img in content_tag.find_all("img"):
        src = img.get("src", "")
        if "../wp-content/uploads/" in src:
            rel = src.split("../wp-content/uploads/", 1)[1].split("?")[0]
            img["src"] = f"/uploads/{rel}"
            src_file = mirror_dir / "wp-content" / "uploads" / rel
            dst_file = uploads_out / rel
            if src_file.exists():
                if not dry_run:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(src_file, dst_file)
                print(f"    image: {rel}")
            else:
                print(f"    WARN: image not in mirror: {rel}", file=sys.stderr)

    # Rewrite internal relative links: ../PAGE/index.html → /PAGE/
    for a in content_tag.find_all("a", href=True):
        href = a["href"]
        m = re.match(r"\.\./([^/]+)/index\.html", href)
        if m:
            a["href"] = f"/{m.group(1)}/"


def extract_page(mirror_dir: Path, slug: str, url: str, out_dir: Path, uploads_out: Path, dry_run: bool) -> bool:
    src = mirror_dir / slug / "index.html"
    if not src.exists():
        print(f"  ERROR: {src} not found", file=sys.stderr)
        return False

    with open(src, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    article = soup.find("article", class_="hentry")
    if not article:
        print(f"  ERROR: no article.hentry in {src}", file=sys.stderr)
        return False

    h1 = article.find("h1", class_="entry-title")
    title = h1.get_text(strip=True) if h1 else slug.capitalize()

    content_tag = article.find(class_="entry-content")
    if not content_tag:
        print(f"  ERROR: no .entry-content in {src}", file=sys.stderr)
        return False

    strip_cruft(content_tag)
    rewrite_paths(content_tag, mirror_dir, uploads_out, dry_run)
    body_html = content_tag.decode_contents().strip()

    post = frontmatter.Post(
        body_html,
        handler=frontmatter.YAMLHandler(),
        title=title,
        url=url,
    )

    out_path = out_dir / f"{slug}.md"
    print(f"  {'[dry-run] would write' if dry_run else 'writing'}: {out_path}")
    print(f"    title: {title}")
    print(f"    url:   {url}")
    print(f"    body:  {len(body_html)} chars")

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            frontmatter.dump(post, f, default_flow_style=False, allow_unicode=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Extract static pages from WP mirror to Hugo content files.")
    parser.add_argument("--mirror", default="/Users/gliush/projects/devzen/devzen-mirror/devzen.ru",
                        help="Path to mirrored site root")
    parser.add_argument("--out", default="content/pages",
                        help="Output directory for .md files (relative to CWD or absolute)")
    parser.add_argument("--uploads-out", default="static/uploads",
                        help="Output directory for copied images")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report without writing files")
    args = parser.parse_args()

    mirror_dir = Path(args.mirror)
    out_dir = Path(args.out)
    uploads_out = Path(args.uploads_out)

    if not mirror_dir.exists():
        print(f"ERROR: mirror dir not found: {mirror_dir}", file=sys.stderr)
        sys.exit(1)

    ok = 0
    fail = 0
    for page in PAGES:
        print(f"\n[{page['slug']}]")
        if extract_page(mirror_dir, page["slug"], page["url"], out_dir, uploads_out, args.dry_run):
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} written, {fail} failed.")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
