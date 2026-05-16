# ferogram

Generates raw Telegram API docs for ferogram-py.

Reads any `.tl` schema and outputs a static HTML site
with `ferogram.raw` import snippets, served at `tl.ferogram.dev`.

## Run locally

```bash
curl -fsSL https://raw.githubusercontent.com/ankit-chaubey/x/data/tdesktop.tl -o api.tl
python ferogram/generate.py api.tl /tmp/site/
# open /tmp/site/index.html
```
