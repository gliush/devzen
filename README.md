# DevZen Podcast — Hugo site

Source for [devzen.ru](https://devzen.ru). Built with [Hugo](https://gohugo.io).

---

## Prerequisites

```sh
brew install hugo   # once
```

---

## Local preview

```sh
hugo server -p 1313
# open http://localhost:1313
```

## Production build

```sh
hugo --gc --minify --baseURL https://devzen.ru/
# output in public/
```

---

## Adding a new episode

1. Create `content/episodes/NNNN.md` (zero-padded, e.g. `0540.md`).

   Use the archetype as a starting point:
   ```sh
   hugo new episodes/0540.md
   ```

2. Fill in the frontmatter:

   ```yaml
   ---
   title: "Название выпуска"
   number: 540
   slug: "episode-0540"
   date: 2026-05-21T22:30:00+03:00
   draft: false
   audio_url: "https://devzen.ru/download/2026/devzen-0540-....mp3"
   audio_size_mb: 97.3
   audio_duration: ""
   cover_image: "/uploads/2026/05/dz540.jpg"
   summary: "Краткое описание выпуска."
   guests: []
   sponsors: []
   chat_links:
     telegram: "https://t.me/devzen_live"
     matrix: "https://to.re128.org/#/#devzen-podcast-comments:matrix.org"
   original_post_id: 0
   original_url: "https://devzen.ru/episode-0540/"
   era: "minimal"
   ---
   ```

3. Add show notes as HTML after the frontmatter:

   ```html
   <div class="show-notes">
     <p>Краткое описание выпуска.</p>
     <ul>
       <li><span class="ts" data-t="00:01:23">[00:01:23]</span> Первая тема</li>
       <li><span class="ts" data-t="00:15:00">[00:15:00]</span> Вторая тема</li>
     </ul>
   </div>
   ```

   Timestamps use `<span class="ts" data-t="HH:MM:SS">` — clicking them seeks the audio player.

4. If there's a cover image, copy it to `static/uploads/YYYY/MM/filename.jpg`.

5. Preview locally, then publish:

   ```sh
   hugo server -p 1313
   # check http://localhost:1313/episode-0540/
   git add content/episodes/0540.md static/uploads/...
   git commit -m "ep 540: Название выпуска"
   git push
   ```

   Pushing to `main` triggers the CI/CD deploy automatically.

