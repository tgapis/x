# x

Scrapes and publishes Telegram API schemas, docs, and diffs automatically. Runs every 5 hours via GitHub Actions. On any change, commits and pushes to the `data` branch.

## What it does

**Schema fetching**

Pulls the raw TL schemas from multiple sources on every run:

- `core.tl` from core.telegram.org
- `corefork.tl` from corefork.telegram.org
- `blogfork.tl` from blogfork.telegram.org
- `tdesktop.tl` from the tdesktop source tree (dev branch)
- `tdlib.tl` from the TDLib source tree

Each TL file is also converted to JSON using the bundled `bin.js` / `index.js` converter.

**Bot API docs**

`scrape.py` scrapes the official Telegram Bot API page and outputs structured JSON (`botapi.json` and `botapi.min.json`) covering all methods, types, and their fields.

**Telethon-style docs**

Feeds the latest `tdesktop.tl` into Telethon v1's doc generator to produce a browsable raw API reference under `telethon/`.

**TL diff viewer**

`get-all-tl.py` walks the full tdesktop git history, extracts every historical TL schema, and generates a diff timeline. Runs twice - once for tDesktop, once for TDLib. Output lives under `TL/diff/`.

**ferogram raw API docs**

`ferogram/generate.py` reads `tdesktop.tl` and builds a static HTML site with `ferogram.raw` import snippets, served at `tl.ferogram.dev`. Output is committed to the root of the `data` branch.

## data branch layout

```
tdesktop.tl / tdesktop.json     - tDesktop MTProto schema
core.tl / core.json             - Official core schema
corefork.tl / corefork.json     - Corefork schema
blogfork.tl / blogfork.json     - Blogfork schema
tdlib.tl / tdlib.json           - TDLib schema
botapi.json / botapi.min.json   - Bot API docs
telethon/                       - Telethon-style raw API docs
TL/diff/                        - TL diff viewer (tDesktop + TDLib)
constructors/                   - ferogram raw API docs
types/
methods/
```

## main branch layout

```
scrape.py        - Bot API scraper
schema.py        - TL schema fetcher
deploy.sh        - Full pipeline
bin.js / index.js - TL to JSON converter
get-all-tl.py    - TL diff generator
requirements.txt
ferogram/
  generate.py    - ferogram raw API doc generator
```

## Credits

- [Lonami](https://github.com/LonamiWebs) - [Telethon](https://github.com/LonamiWebs/Telethon) doc generator and [tl-differ](https://codeberg.org/Lonami/tl-differ)
- [SpEcHiDe](https://github.com/SpEcHiDe) - [TG-APIs](https://github.com/TelegramPlayground/TG-APIs) which this builds on
