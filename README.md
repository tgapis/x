# tgapis/x

Scrapes Telegram API schemas every 5 hours via GitHub Actions and generates docs for a few libraries. Everything generated lands on the `data` branch, so `main` stays clean with just the scripts.

Live at: https://tgapis.github.io/x/

## What's on the data branch

Raw TL schemas and parsed JSON for tDesktop, TDLib, core, corefork, and blogfork. `botapi.json` covers the Bot API. There's also a layer-by-layer TL diff viewer for both tDesktop and TDLib, Telethon HTML docs built from the tDesktop schema, and raw API references for ferogram (Rust) and ferogram-py.

## How it works

`deploy.sh` is the main entry point that CI runs. It calls `scrape.py` to pull the Bot API docs, `schema.py` to grab TL schemas from telegram.org, and `get-all-tl.py` to build the diff viewer. Parsing `.tl` files into JSON is handled by `bin.js` and `index.js`. The ferogram doc generators live in `ferogram/generate.py` for Python and `ferogram/generate_rust.py` for Rust.

When the `data` branch changes, a dispatch is sent to `tgapis/pipeline` and `ankit-chaubey/ferobot` to kick off any downstream builds.

## Running locally

```bash
pip install -r requirements.txt

# grab the latest schema and generate ferogram docs
curl -fsSL https://raw.githubusercontent.com/tgapis/x/data/tdesktop.tl -o tdesktop.tl
python ferogram/generate.py tdesktop.tl /tmp/site/
```

## Lineage

This is part of a longer line of projects doing the same thing. Worth checking out [TelegramPlayground/TG-APIs](https://github.com/TelegramPlayground/TG-APIs) and [PaulSonOfLars/telegram-bot-api-spec](https://github.com/PaulSonOfLars/telegram-bot-api-spec) if you're into this space.

---

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey).
