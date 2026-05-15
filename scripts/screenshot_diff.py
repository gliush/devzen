#!/usr/bin/env python3
"""
screenshot_diff.py — side-by-side visual diff of mirrored WP site vs Hugo site.

The script starts both servers itself and shuts them down when done.

Usage:
  python scripts/screenshot_diff.py \\
      --episodes 1,15,50,100,250,350,450,500,538 \\
      --mirror /path/to/devzen-mirror/devzen.ru \\
      --hugo-root /path/to/devzen-hugo \\
      --out scripts/migration_log/screenshots \\
      --diff

Output per episode:
  <out>/NNNN_old.png    — full-page screenshot from mirror
  <out>/NNNN_new.png    — full-page screenshot from Hugo
  <out>/NNNN_diff.png   — pixel difference image (amplified, only with --diff)
  <out>/summary.csv     — episode, pixel_delta_pct, status
"""

import argparse
import csv
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DEFAULT_EPISODES = "1,15,50,100,250,350,450,500,538"
OLD_PORT = 8001
NEW_PORT = 8002


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def mirror_episode_path(number: int) -> str:
    """Mirror uses episode-NNNN (4-digit) for <=406, episode-NNN (3-digit) for 407+."""
    if number <= 406:
        return f"episode-{number:04d}"
    return f"episode-{number}"

def hugo_episode_path(number: int) -> str:
    """Hugo always uses episode-NNNN (4-digit zero-padded slugs)."""
    return f"episode-{number:04d}"


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------

def wait_for_port(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def start_python_server(directory: Path, port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(directory),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_for_port(port):
        proc.terminate()
        raise RuntimeError(f"Python http.server on port {port} did not start in time")
    print(f"  ✓ python http.server :{port}  ({directory.name}/)")
    return proc


def start_hugo_server(hugo_root: Path, port: int) -> subprocess.Popen:
    hugo_bin = shutil.which("hugo")
    if not hugo_bin:
        raise RuntimeError("hugo binary not found in PATH — cannot start Hugo server")
    proc = subprocess.Popen(
        [hugo_bin, "server", "-p", str(port), "--bind", "127.0.0.1",
         "--disableFastRender", "--navigateToChanged=false"],
        cwd=str(hugo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_for_port(port, timeout=20.0):
        proc.terminate()
        raise RuntimeError(f"Hugo server on port {port} did not start in time")
    print(f"  ✓ hugo server :{port}  ({hugo_root.name}/)")
    return proc


def start_new_server(hugo_root: Path, port: int) -> subprocess.Popen:
    """Start Hugo server if hugo is available, otherwise fall back to serving public/."""
    if shutil.which("hugo"):
        return start_hugo_server(hugo_root, port)
    public_dir = hugo_root / "public"
    if not public_dir.exists():
        raise RuntimeError(
            "hugo not in PATH and public/ dir not found — run 'hugo' first or install Hugo"
        )
    print("  hugo not in PATH — falling back to serving public/ with http.server")
    return start_python_server(public_dir, port)


# ---------------------------------------------------------------------------
# Screenshot + diff
# ---------------------------------------------------------------------------

def take_screenshot(page, url: str, out_path: Path, viewport_width: int, timeout: int) -> bool:
    try:
        page.set_viewport_size({"width": viewport_width, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=timeout)
        page.screenshot(path=str(out_path), full_page=True)
        return True
    except PlaywrightTimeout:
        print(f"    TIMEOUT: {url}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"    ERROR: {url}: {e}", file=sys.stderr)
        return False


def pixel_delta(img_a: Path, img_b: Path) -> float:
    """Return mean per-pixel difference as a percentage (0–100)."""
    a = Image.open(img_a).convert("RGB")
    b = Image.open(img_b).convert("RGB")
    w, h = min(a.width, b.width), min(a.height, b.height)
    a, b = a.crop((0, 0, w, h)), b.crop((0, 0, w, h))
    diff = ImageChops.difference(a, b)
    pixels = list(diff.getdata())
    mean = sum(sum(p) / 3 for p in pixels) / len(pixels) / 255 * 100
    return round(mean, 2)


def save_diff_image(img_a: Path, img_b: Path, out_path: Path):
    a = Image.open(img_a).convert("RGB")
    b = Image.open(img_b).convert("RGB")
    w, h = min(a.width, b.width), min(a.height, b.height)
    a, b = a.crop((0, 0, w, h)), b.crop((0, 0, w, h))
    diff = ImageChops.difference(a, b)
    diff.point(lambda x: min(255, x * 10)).save(str(out_path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Screenshot diff: WP mirror vs Hugo site")
    parser.add_argument("--episodes", default=DEFAULT_EPISODES,
                        help="Comma-separated episode numbers")
    parser.add_argument("--mirror",
                        default="/Users/gliush/projects/devzen/devzen-mirror/devzen.ru",
                        help="Path to mirrored WP site root")
    parser.add_argument("--hugo-root",
                        default="/Users/gliush/projects/devzen/devzen-hugo",
                        help="Path to devzen-hugo repo root (hugo server runs here)")
    parser.add_argument("--old-port", default=OLD_PORT, type=int)
    parser.add_argument("--new-port", default=NEW_PORT, type=int)
    parser.add_argument("--viewport", default=1280, type=int,
                        help="Viewport width in pixels")
    parser.add_argument("--out", default="scripts/migration_log/screenshots",
                        help="Output directory for screenshots")
    parser.add_argument("--diff", action="store_true",
                        help="Compute pixel diff and save diff images")
    parser.add_argument("--timeout", default=30000, type=int,
                        help="Page load timeout in ms")
    args = parser.parse_args()

    episodes = [int(e.strip()) for e in args.episodes.split(",")]
    mirror_dir = Path(args.mirror)
    hugo_root = Path(args.hugo_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not mirror_dir.exists():
        print(f"ERROR: mirror dir not found: {mirror_dir}", file=sys.stderr)
        sys.exit(1)

    procs = []
    results = []

    try:
        print("\nStarting servers...")
        procs.append(start_python_server(mirror_dir, args.old_port))
        procs.append(start_new_server(hugo_root, args.new_port))

        print(f"\nRunning screenshots ({len(episodes)} episodes)...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for ep in episodes:
                old_slug = mirror_episode_path(ep)
                new_slug = hugo_episode_path(ep)
                old_url = f"http://127.0.0.1:{args.old_port}/{old_slug}/"
                new_url = f"http://127.0.0.1:{args.new_port}/{new_slug}/"

                old_png = out_dir / f"{ep:04d}_old.png"
                new_png = out_dir / f"{ep:04d}_new.png"
                diff_png = out_dir / f"{ep:04d}_diff.png"

                print(f"\n[ep {ep:04d}]  mirror:{old_slug}/  hugo:{new_slug}/")
                old_ok = take_screenshot(page, old_url, old_png, args.viewport, args.timeout)
                new_ok = take_screenshot(page, new_url, new_png, args.viewport, args.timeout)

                delta, status = None, "ok"

                if old_ok and new_ok:
                    if args.diff:
                        delta = pixel_delta(old_png, new_png)
                        save_diff_image(old_png, new_png, diff_png)
                        status = "ok" if delta < 10 else "review"
                        print(f"    pixel delta: {delta}%  [{status}]")
                    else:
                        print(f"    screenshots saved")
                else:
                    status = "error"

                results.append({
                    "episode": ep, "old_ok": old_ok, "new_ok": new_ok,
                    "pixel_delta_pct": delta if delta is not None else "",
                    "status": status,
                })

            browser.close()

    finally:
        print("\nStopping servers...")
        for proc in procs:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # Write CSV summary
    csv_path = out_dir / "summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["episode", "old_ok", "new_ok", "pixel_delta_pct", "status"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'='*50}")
    errors  = [r for r in results if r["status"] == "error"]
    reviews = [r for r in results if r["status"] == "review"]
    oks     = [r for r in results if r["status"] == "ok"]
    print(f"OK:     {len(oks)}")
    print(f"Review: {len(reviews)}  (pixel delta ≥ 10%)")
    print(f"Error:  {len(errors)}")
    if reviews:
        print(f"Episodes needing review: {[r['episode'] for r in reviews]}")
    if errors:
        print(f"Failed episodes: {[r['episode'] for r in errors]}")
    print(f"\nScreenshots → {out_dir}/")
    print(f"Summary CSV → {csv_path}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
