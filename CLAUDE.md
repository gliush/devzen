# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Hugo static site for [devzen.ru](https://devzen.ru) — a Russian-language tech podcast. Content is in Russian. Pushing to `main` auto-deploys via GitHub Actions to GitHub Pages.

## Commands

```sh
just serve          # local dev server at http://localhost:1313
just build          # production build → public/
just new 0541       # scaffold new episode from archetype
```

Python scripts use a local venv:
```sh
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

## Adding an episode

1. `just new NNNN` (zero-padded four digits, e.g. `0541`)
2. Fill frontmatter in `content/episodes/NNNN.md` — required fields: `title`, `number`, `slug` (`episode-NNNN`), `date`, `audio_url`, `audio_size_mb`, `cover_image`, `summary`, `era`

   `era` values by episode number: `"early"` (1–50), `"mid"` (51–249), `"cover"` (250–449), `"minimal"` (450+)
3. Copy cover image to `static/uploads/YYYY/MM/filename.jpg`
4. Write show notes as HTML inside `<div class="show-notes">` after the frontmatter
5. Timestamps use `<span class="ts" data-t="HH:MM:SS">[HH:MM:SS]</span>` — clicking seeks the audio player

## Architecture

- **`config.toml`** — baseURL, pagination (10/page), permalink pattern (`/:slug/`), RSS output format, iTunes podcast params
- **`layouts/`** — no theme; all templates are custom
  - `_default/baseof.html` — shell with `<head>`, nav, footer
  - `episodes/single.html` — episode page: cover image, audio player, show notes. Image `src="/uploads/..."` paths in content are rewritten at render time to be baseURL-aware (handles GitHub Pages subpath)
  - `index.html` — paginated episode card list
  - `rss.xml` — iTunes-compatible podcast RSS feed; only episodes with `audio_url` appear; GUID is `https://devzen.ru/?p={{ original_post_id }}`
  - `partials/timestamps.html` — injects the JS + CSS that makes `.ts` spans clickable
- **`content/episodes/`** — one `.md` per episode; show notes are raw HTML (goldmark `unsafe: true`)
- **`content/pages/`** — static pages: `guests.md`, `contact.md`, `live.md`
- **`static/feed/index.html`** — meta-refresh redirect from `/feed/` to `/feed.xml`. Podcast clients subscribe to `/feed/`; do not remove this file.
- **`static/uploads/`** — cover images organized by `YYYY/MM/`
- **`scripts/`** — Python utilities for migration/extraction (use `.venv`)
  - `extract_episodes.py` — bulk-extracts episodes from the HTML mirror at `../devzen-mirror/devzen.ru/` into `content/episodes/`. Run with `--all --overwrite` to regenerate all 539 episodes from source. Early episodes (1–249) use `devzen.ru/download/...` audio URLs; later ones use `download.devzen.ru/...` — both are correct.
