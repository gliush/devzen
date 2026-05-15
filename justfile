# DevZen Hugo — task runner
# Usage: just <recipe>

# Start local dev server
serve:
    hugo server -p 1313

# Production build
build:
    hugo --gc --minify --baseURL https://devzen.ru/

# Create a new episode (usage: just new 0541)
new n:
    hugo new episodes/{{n}}.md
