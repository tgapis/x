# x

Scrapes and tracks Telegram API schemas. Runs every 5 hours via GitHub Actions.

## Data branch

All generated files live on the `data` branch:

- `botapi.json` / `botapi.min.json`: Bot API docs
- `core.tl` / `corefork.tl` / `blogfork.tl`: TL schemas from core.telegram.org
- `tdesktop.tl` / `tdlib.tl`: TL schemas from tdesktop / tdlib
- `*.json`: parsed TL schemas
- `telethon/`: Telethon HTML docs generated from tdesktop.tl
- `TL/diff/`: TL diff viewer (tdesktop + TDLib)
- `constructors/` `types/` `methods/`: ferogram raw API docs (`tl.ferogram.dev`)

## Scripts (main branch)

| File | Purpose |
|------|---------|
| `deploy.sh` | Main deploy script run by CI |
| `scrape.py` | Scrapes Bot API docs |
| `schema.py` | Scrapes TL schema from telegram.org |
| `get-all-tl.py` | Builds TL diff viewer (tdesktop + TDLib modes via env vars) |
| `bin.js` / `index.js` | TL → JSON parser |
| `ferogram/generate.py` | Generates ferogram raw API docs site |

## Secrets required

| Secret | Used for |
|--------|---------|
| `TGAPIS_PAT` | Dispatch to `tgapis/pipeline` |
| `AC_PAT` | Dispatch to `ankit-chaubey/tgbotrs` |
