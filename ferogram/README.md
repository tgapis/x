# ferogram docs generator

Generates the Ferogram raw API reference from a Telegram TL schema.
The output is a static HTML site, published at [Ferogram API](https://tgapis.github.io/x/).

## Generate docs locally

Grab the latest TL schema and run the generator:

```bash
curl -fsSL https://raw.githubusercontent.com/tgapis/x/data/tdesktop.tl -o raw_api.tl
python ferogram/generate.py raw_api.tl /tmp/site/
```

Then open `/tmp/site/index.html` in your browser.

You can also point it at any other TL file:

```bash
python ferogram/generate.py path/to/custom.tl /tmp/site/
```

## How it works

`generate.py` reads the TL schema, parses every constructor and function,
and outputs one HTML page per method, type, and constructor, plus a root index with search.

Themes (dark, bright, AMOLED) and syntax highlighting are all baked in as static CSS and JS.
No build tools, no dependencies beyond Python 3.9+.

## CI

The site rebuilds automatically whenever a new TL schema is detected upstream.
See `.github/workflows/scrape.yml` for the full pipeline.
