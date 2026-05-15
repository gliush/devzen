#!/usr/bin/env python3
"""Extract episode content from mirrored HTML into Hugo markdown files."""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import frontmatter
from bs4 import BeautifulSoup, NavigableString
from dateutil import parser as dateutil_parser
from tqdm import tqdm

MIRROR_DEFAULT = Path("/Users/gliush/projects/devzen/devzen-mirror/devzen.ru")
OUT_DEFAULT = Path("content/episodes")
UPLOADS_OUT_DEFAULT = Path("static/uploads")
LOG_DIR_DEFAULT = Path("scripts/migration_log")

ERA_BOUNDARIES = [(1, 50, "early"), (51, 249, "mid"), (250, 449, "cover"), (450, 9999, "minimal")]


def get_era(number: int) -> str:
    for lo, hi, name in ERA_BOUNDARIES:
        if lo <= number <= hi:
            return name
    return "unknown"


def episode_dir(mirror: Path, number: int) -> Path | None:
    """Return the episode dir path, handling 4-digit vs 3-digit naming."""
    if number <= 406:
        candidate = mirror / f"episode-{number:04d}"
    else:
        candidate = mirror / f"episode-{number}"
    return candidate if candidate.is_dir() else None


def discover_episodes(mirror: Path) -> dict[int, Path]:
    """Find all episode dirs in the mirror, return {number: path}."""
    found = {}
    for d in mirror.iterdir():
        if not d.is_dir():
            continue
        m = re.match(r"^episode-(\d+)$", d.name)
        if m:
            found[int(m.group(1))] = d
    return found


def strip_cruft(soup: BeautifulSoup, entry: BeautifulSoup) -> None:
    """Remove WP/plugin noise from entry-content in-place."""
    for tag in entry.find_all(["style", "script"]):
        tag.decompose()
    for tag in entry.find_all(class_=lambda c: c and "powerpress_player" in c):
        tag.decompose()
    for tag in entry.find_all(id=lambda i: i and i.startswith("mejs_")):
        tag.decompose()
    for tag in entry.find_all(class_=lambda c: c and "powerpress_links" in c):
        tag.decompose()
    # WordPress "Read more" excerpt markers — empty <span id="more-NNNN">.
    for span in entry.find_all("span", id=re.compile(r"^more-\d+$")):
        span.decompose()
    # /themes-NNNN/ pages are dropped (see migration plan). Unwrap the links so
    # the visible text survives but the dead href disappears.
    for a in entry.find_all("a", href=re.compile(r"themes-\d+/")):
        a.unwrap()
    # Remove empty <p> tags
    for p in entry.find_all("p"):
        if not p.get_text(strip=True) and not p.find(["img", "audio", "video"]):
            p.decompose()
    # Strip ?ver=... query strings from remaining attrs
    for tag in entry.find_all(True):
        for attr in ("src", "href"):
            val = tag.get(attr, "")
            if "?ver=" in val:
                tag[attr] = val.split("?ver=")[0]


def wrap_orphan_lis(entry) -> None:
    """Wrap any direct <li> children of entry-content into a synthetic <ul>.
    Episodes 63 and 526 have malformed source HTML that strands <li>s outside
    their parent list; this restores the structure before rendering.
    """
    while True:
        first = None
        for child in entry.children:
            if getattr(child, "name", None) == "li":
                first = child
                break
        if first is None:
            return
        group = [first]
        sib = first.next_sibling
        while sib is not None:
            if getattr(sib, "name", None) == "li":
                group.append(sib)
                sib = sib.next_sibling
            elif isinstance(sib, NavigableString) and not str(sib).strip():
                group.append(sib)
                sib = sib.next_sibling
            else:
                break
        while group and not getattr(group[-1], "name", None):
            group.pop()
        new_ul = BeautifulSoup(features="html.parser").new_tag("ul")
        group[0].insert_before(new_ul)
        for g in group:
            new_ul.append(g.extract())


def normalize_timestamps(entry: BeautifulSoup) -> None:
    """Wrap [HH:MM:SS] / [MM:SS] timestamps in <span class="ts" data-t="...">."""
    ts_re = re.compile(r"\[(\d{2}):(\d{2})(?::(\d{2}))?\]")

    def replace_in_node(node):
        if node.name in ("script", "style"):
            return
        for child in list(node.children):
            if hasattr(child, "children"):
                replace_in_node(child)
            else:
                text = str(child)
                if not ts_re.search(text):
                    continue
                parts = []
                pos = 0
                for m in ts_re.finditer(text):
                    parts.append(text[pos : m.start()])
                    h = m.group(1)
                    mn = m.group(2)
                    s = m.group(3) or "00"
                    data_t = f"{h}:{mn}:{s}"
                    parts.append(f'<span class="ts" data-t="{data_t}">{m.group(0)}</span>')
                    pos = m.end()
                parts.append(text[pos:])
                new_html = "".join(parts)
                new_nodes = BeautifulSoup(new_html, "html.parser")
                for node in list(new_nodes.children):
                    if hasattr(node, "name"):  # Skip text nodes
                        child.insert_before(node)
                child.decompose()

    replace_in_node(entry)


def copy_image(src_attr: str, mirror: Path, uploads_out: Path, warnings: list) -> str:
    """Copy a wp-content/uploads image to static/uploads and return new src."""
    if "/wp-content/uploads/" not in src_attr:
        return src_attr
    rel = src_attr.split("/wp-content/uploads/", 1)[1].split("?")[0]
    src_file = mirror / "wp-content" / "uploads" / rel
    dst_file = uploads_out / rel
    if src_file.exists():
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        if not dst_file.exists():
            shutil.copy2(src_file, dst_file)
    else:
        warnings.append(f"missing image in mirror: {src_file}")
    return f"/uploads/{rel}"


def extract_episode(
    ep_dir: Path,
    number: int,
    mirror: Path,
    uploads_out: Path,
    dry_run: bool,
    out_dir: Path,
    log_dir: Path,
    run_ts: str,
) -> dict:
    """Extract a single episode. Returns a result dict for the run log."""
    html_path = ep_dir / "index.html"
    if not html_path.exists():
        return {"number": number, "status": "missing_html", "warnings": []}

    warnings = []
    t0 = datetime.now()

    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # -- root article --
    article = soup.find("article", class_="hentry")
    if not article:
        warnings.append("no article.hentry found")
        return {"number": number, "status": "no_article", "warnings": warnings}

    # -- title --
    h1 = article.find("h1", class_="entry-title")
    raw_title = h1.get_text(strip=True) if h1 else ""
    title = re.sub(r"\s*[—–-]+\s*Episode\s+\d+\s*$", "", raw_title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^\s*Episode\s+\d+\s*[—–-]+\s*", "", title, flags=re.IGNORECASE).strip()
    if not title:
        title = f"Episode {number:04d}"
        warnings.append("could not extract title, using fallback")

    # -- date --
    time_tag = article.find("time", class_="entry-date")
    date_str = ""
    if time_tag and time_tag.get("datetime"):
        try:
            date_str = dateutil_parser.isoparse(time_tag["datetime"]).isoformat()
        except Exception:
            warnings.append(f"could not parse date: {time_tag.get('datetime')}")
    if not date_str:
        warnings.append("no date found")

    # -- audio URL (primary: <audio> tag, fallback: powerpress_links_mp3 <a>) --
    audio_tag = article.find("audio", class_="powerpress-mejs-audio")
    audio_url = audio_tag.get("src", "") if audio_tag else ""
    if not audio_url:
        mp3_link = article.select_one(".powerpress_links_mp3 a[href]")
        if mp3_link:
            audio_url = mp3_link.get("href", "")
            warnings.append("used fallback audio selector (.powerpress_links_mp3 a[href])")

    # -- audio size --
    audio_size_mb = 0.0
    mp3_block = article.find(class_="powerpress_links_mp3")
    if mp3_block:
        m = re.search(r"\(([\d.]+)MB\)", mp3_block.get_text())
        if m:
            audio_size_mb = float(m.group(1))

    # -- original_post_id from body class --
    original_post_id = 0
    body = soup.find("body")
    if body:
        body_classes = " ".join(body.get("class", []))
        m = re.search(r"postid-(\d+)", body_classes)
        if m:
            original_post_id = int(m.group(1))

    # -- canonical URL --
    canonical = soup.find("link", rel="canonical")
    original_url = canonical.get("href", "") if canonical else f"https://devzen.ru/episode-{number:04d}/"
    # Normalize relative canonical to absolute
    if original_url and not original_url.startswith("http"):
        original_url = f"https://devzen.ru/episode-{number:04d}/"

    # -- cover image (first uploads img in entry-content) --
    cover_image = ""
    entry_content = article.find(class_="entry-content")
    if entry_content:
        img = entry_content.find("img", src=re.compile(r"/wp-content/uploads/"))
        if img:
            cover_image = copy_image(img.get("src", ""), mirror, uploads_out, warnings)
            # Drop the inline cover so it isn't duplicated next to the template-rendered one.
            parent = img.parent
            img.decompose()
            if (
                parent is not None
                and parent.name == "p"
                and not parent.get_text(strip=True)
                and not parent.find(["img", "audio", "video"])
            ):
                parent.decompose()

    # -- chat links --
    telegram_url = ""
    matrix_url = ""
    if entry_content:
        body_text = str(entry_content)
        tm = re.search(r'href="(https://t\.me/[^"]+)"', body_text)
        if tm:
            telegram_url = tm.group(1)
        mm = re.search(r'href="(https://to\.re128\.org/[^"]+)"', body_text)
        if not mm:
            mm = re.search(r'href="(https://matrix\.to/[^"]+)"', body_text)
        if mm:
            matrix_url = mm.group(1)

    # -- summary (first non-empty, non-image <p>, full text — no truncation) --
    summary = ""
    if entry_content:
        for p in entry_content.find_all("p"):
            if p.find("img") and not p.get_text(strip=True):
                continue  # image-only paragraph, skip
            txt = p.get_text(" ", strip=True)
            # Strip "Читать далее" suffix if present (shouldn't appear on single pages, but be safe)
            txt = re.sub(r"\s*Читать далее\s*→.*$", "", txt).strip()
            if txt:
                summary = txt
                break

    # -- clean entry-content --
    if entry_content:
        strip_cruft(soup, entry_content)
        wrap_orphan_lis(entry_content)
        # Copy all remaining upload images
        for img in entry_content.find_all("img", src=re.compile(r"/wp-content/uploads/")):
            new_src = copy_image(img.get("src", ""), mirror, uploads_out, warnings)
            img["src"] = new_src
        # Warn about unexpected direct children
        for child in entry_content.children:
            if hasattr(child, "name") and child.name not in (
                "p", "ul", "ol", "h2", "h3", "h4", "blockquote",
                "pre", "div", "img", "figure", "a", "hr", None,
            ):
                warnings.append(f"unexpected direct child in entry-content: <{child.name}>")
        normalize_timestamps(entry_content)
        content_html = entry_content.decode_contents().strip()
    else:
        content_html = ""
        warnings.append("no .entry-content found")

    slug = f"episode-{number:04d}"
    era = get_era(number)

    fm = {
        "title": title,
        "number": number,
        "slug": slug,
        "date": date_str,
        "draft": False,
        "audio_url": audio_url,
        "audio_size_mb": audio_size_mb,
        "audio_duration": "",
        "cover_image": cover_image,
        "summary": summary,
        "guests": [],
        "sponsors": [],
        "chat_links": {"telegram": telegram_url, "matrix": matrix_url},
        "original_post_id": original_post_id,
        "original_url": original_url,
        "era": era,
    }

    body_html = f'<div class="show-notes">\n{content_html}\n</div>'

    elapsed_ms = int((datetime.now() - t0).total_seconds() * 1000)
    log_entry = {
        "number": number,
        "status": "ok",
        "warnings": warnings,
        "fields": fm,
        "elapsed_ms": elapsed_ms,
    }

    if not dry_run:
        out_path = out_dir / f"{number:04d}.md"
        post = frontmatter.Post(body_html, handler=frontmatter.YAMLHandler(), **fm)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        per_ep_dir = log_dir / f"run-{run_ts}" / "per_episode"
        per_ep_dir.mkdir(parents=True, exist_ok=True)
        with open(per_ep_dir / f"{number:04d}.json", "w", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)

    return log_entry


def main():
    parser = argparse.ArgumentParser(description="Extract DevZen episodes from HTML mirror to Hugo markdown")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Extract all episodes in mirror")
    group.add_argument("--episode", type=int, metavar="N", help="Extract single episode N")
    group.add_argument("--episodes", metavar="N,M,...", help="Comma-separated list of episode numbers")
    group.add_argument("--from", dest="from_ep", type=int, metavar="A")
    parser.add_argument("--to", dest="to_ep", type=int, metavar="B")
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write files")
    parser.add_argument("--mirror", type=Path, default=MIRROR_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--uploads-out", type=Path, default=UPLOADS_OUT_DEFAULT)
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR_DEFAULT)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .md files")
    args = parser.parse_args()

    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    if not args.dry_run:
        args.out.mkdir(parents=True, exist_ok=True)
        args.uploads_out.mkdir(parents=True, exist_ok=True)

    all_episodes = discover_episodes(args.mirror)
    all_numbers = sorted(all_episodes.keys())

    if args.all:
        target_numbers = all_numbers
    elif args.episode:
        target_numbers = [args.episode]
    elif args.episodes:
        target_numbers = [int(x.strip()) for x in args.episodes.split(",")]
    elif args.from_ep:
        to = args.to_ep or max(all_numbers)
        target_numbers = [n for n in all_numbers if args.from_ep <= n <= to]
    else:
        parser.error("specify --all, --episode N, --episodes N,M,..., or --from A [--to B]")

    # Log missing episodes
    if args.all:
        all_expected = set(range(1, max(all_numbers) + 1))
        missing = sorted(all_expected - set(all_numbers))
        if missing:
            missing_path = args.log_dir / f"run-{run_ts}" / "missing.txt"
            missing_path.parent.mkdir(parents=True, exist_ok=True)
            with open(missing_path, "w") as f:
                f.write("\n".join(str(n) for n in missing))
            print(f"Missing {len(missing)} episodes logged to {missing_path}")

    results = []
    skipped = 0
    with tqdm(target_numbers, unit="ep") as bar:
        for number in bar:
            bar.set_description(f"ep {number:04d}")
            if not args.overwrite and not args.dry_run:
                out_path = args.out / f"{number:04d}.md"
                if out_path.exists():
                    skipped += 1
                    continue
            ep_dir = all_episodes.get(number)
            if ep_dir is None:
                results.append({"number": number, "status": "not_in_mirror", "warnings": []})
                continue
            result = extract_episode(
                ep_dir, number, args.mirror, args.uploads_out,
                args.dry_run, args.out, args.log_dir, run_ts,
            )
            results.append(result)

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r for r in results if r["status"] not in ("ok",)]
    warn_count = sum(len(r.get("warnings", [])) for r in results)

    summary = {
        "run": run_ts,
        "dry_run": args.dry_run,
        "parsed": len(results),
        "written": ok,
        "skipped": skipped,
        "not_in_mirror": sum(1 for r in results if r["status"] == "not_in_mirror"),
        "errors": len(errors),
        "total_warnings": warn_count,
    }

    if not args.dry_run:
        summary_path = args.log_dir / f"run-{run_ts}" / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if errors:
        print("\nErrors:")
        for r in errors:
            print(f"  {r['number']:04d}: {r['status']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
