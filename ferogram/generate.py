#!/usr/bin/env python3

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

# --- TL Parser

TL_LINE = re.compile(
    r"^([\w.][\w.]*)"
    r"#([0-9a-fA-F]+)"
    r"((?:\s+[\w.]+:[^\s=]+)*)"
    r"\s*=\s*([\w.<>]+);"
)
FIELD_RE = re.compile(r"([\w.]+):([\w?.<>]+)")
FLAG_FIELD = re.compile(r"flags\.(\d+)\?(.+)")


class Field(NamedTuple):
    name: str
    ftype: str
    flag_bit: int | None
    optional: bool


class TLItem(NamedTuple):
    tl_name: str
    cid: int
    fields: list[Field]
    ret: str
    is_function: bool


def parse_fields(raw: str) -> list[Field]:
    fields = []
    for fname, ftype in FIELD_RE.findall(raw):
        if fname == "flags" and ftype == "#":
            continue
        m = FLAG_FIELD.match(ftype)
        if m:
            fields.append(Field(fname, m.group(2), int(m.group(1)), True))
        else:
            fields.append(Field(fname, ftype, None, False))
    return fields


def parse_tl(path: Path) -> tuple[list[TLItem], list[TLItem]]:
    types, funcs = [], []
    in_functions = False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line == "---functions---":
            in_functions = True
            continue
        if line.startswith("//") or not line:
            continue
        m = TL_LINE.match(line)
        if not m:
            continue
        name, cid_hex, fields_raw, ret = m.groups()
        cid = int(cid_hex, 16)
        fields = parse_fields(fields_raw)
        item = TLItem(name, cid, fields, ret, in_functions)
        (funcs if in_functions else types).append(item)
    return types, funcs


def parse_layer(path: Path) -> int:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^//\s*LAYER\s+(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return 0


# --- Naming helpers

def tl_ns(tl_name: str) -> str:
    parts = tl_name.split(".")
    return parts[0] if len(parts) > 1 else "_base"


def tl_base(tl_name: str) -> str:
    return tl_name.split(".")[-1]


def py_class(tl_name: str) -> str:
    base = tl_base(tl_name)
    return base[0].upper() + base[1:]


def camel_to_snake(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def url_slug(tl_name: str) -> str:
    return camel_to_snake(tl_base(tl_name)) + ".html"


def constructor_url(item: TLItem, depth: str = "") -> str:
    ns = tl_ns(item.tl_name)
    slug = url_slug(item.tl_name)
    if ns == "_base":
        return f"{depth}constructors/{slug}"
    return f"{depth}constructors/{ns}/{slug}"


def abstract_type_url(abstract: str, depth: str = "") -> str:
    ns = tl_ns(abstract)
    slug = camel_to_snake(tl_base(abstract)) + ".html"
    if ns == "_base":
        return f"{depth}types/{slug}"
    return f"{depth}types/{ns}/{slug}"


def method_url(item: TLItem, depth: str = "") -> str:
    ns = tl_ns(item.tl_name)
    slug = url_slug(item.tl_name)
    if ns == "_base":
        return f"{depth}methods/{slug}"
    return f"{depth}methods/{ns}/{slug}"


def import_type(item: TLItem) -> str:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    if ns == "_base":
        return f"from ferogram.raw.types import {cls}"
    return f"from ferogram.raw.types.{ns} import {cls}"


def import_func(item: TLItem) -> str:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    if ns == "_base":
        return f"from ferogram.raw.functions import {cls}"
    return f"from ferogram.raw.functions.{ns} import {cls}"


# --- Field type linkifier

PRIMITIVES = {
    "int", "long", "double", "string", "bytes", "Bool",
    "int128", "int256", "true", "True", "Int", "Long", "bool",
}


def link_type(ftype: str, known_types: set[str], depth: str) -> str:
    """Return HTML with linked type names."""
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        return f'<a href="{depth}index.html#vector">Vector</a>&lt;{link_type(inner, known_types, depth)}&gt;'
    if ftype in PRIMITIVES:
        return f'<a href="{depth}index.html#{ftype.lower()}">{html.escape(ftype)}</a>'
    # Could be an abstract type
    if ftype in known_types:
        url = abstract_type_url(ftype, depth)
        return f'<a href="{url}">{html.escape(ftype)}</a>'
    return html.escape(ftype)


def render_tl_def(item: TLItem, known_types: set[str], depth: str) -> str:
    header = "---functions---" if item.is_function else "---types---"
    cid_hex = f"{item.cid:08x}"
    parts = [html.escape(f"{item.tl_name}#{cid_hex}")]
    for f in item.fields:
        if f.flag_bit is not None:
            ftype_raw = f"flags.{f.flag_bit}?{f.ftype}"
            linked = f" {html.escape(f.name)}:flags.{f.flag_bit}?{link_type(f.ftype, known_types, depth)}"
        else:
            linked = f" {html.escape(f.name)}:{link_type(f.ftype, known_types, depth)}"
        parts.append(linked)
    ret_linked = link_type(item.ret, known_types, depth)
    return f"{header}\n{''.join(parts)} = {ret_linked}"


# --- CSS

CSS = """\
:root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e2e4f0;
    --muted: #8b8fa8;
    --accent: #7c6af7;
    --accent-light: #a99ff8;
    --code-bg: #161923;
    --code-text: #c9d1e0;
    --link: #7c6af7;
    --link-hover: #a99ff8;
    --tag-bg: #251f4a;
    --tag-opt: #1a3040;
    --tag-opt-text: #5db8e8;
}
body {
    font-family: 'Nunito', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
    padding: 0;
}
a { color: var(--link); text-decoration: none; }
a:hover { color: var(--link-hover); text-decoration: underline; }
#main_div {
    max-width: 900px;
    margin: 0 auto;
    padding: 24px 20px 60px;
}
h1 {
    font-size: 1.8rem;
    color: var(--text);
    font-weight: 700;
    margin: 12px 0 20px;
}
h3 {
    font-size: 1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin: 28px 0 10px;
}
pre {
    font-family: 'Source Code Pro', monospace;
    font-size: 13px;
    background: var(--code-bg);
    color: var(--code-text);
    padding: 14px 16px;
    border-radius: 6px;
    overflow-x: auto;
    border: 1px solid var(--border);
    line-height: 1.6;
}
code { font-family: 'Source Code Pro', monospace; font-size: 13px; }
table { width: 100%; border-collapse: collapse; margin: 0; }
table td {
    border-top: 1px solid var(--border);
    padding: 9px 12px;
    vertical-align: top;
    font-size: 14px;
}
table td:first-child { color: var(--text); font-weight: 600; font-family: monospace; font-size: 13px; }
table td:nth-child(2) { color: var(--accent-light); }
table td:last-child { color: var(--muted); font-size: 13px; }
.horizontal {
    list-style: none;
    padding: 8px 14px;
    margin: 0 0 20px;
    background: var(--surface);
    border-radius: 6px;
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    flex-wrap: wrap;
}
.horizontal li { display: inline; color: var(--muted); }
.horizontal li a { color: var(--link); }
.sep { color: var(--border); user-select: none; }
button.copy-btn {
    display: inline-block;
    margin: 12px 0 20px;
    padding: 7px 14px;
    background: var(--tag-bg);
    color: var(--accent-light);
    border: 1px solid var(--accent);
    border-radius: 5px;
    font-size: 13px;
    font-family: 'Source Code Pro', monospace;
    cursor: pointer;
    transition: background 0.15s;
}
button.copy-btn:hover { background: #321f7a; }
.invisible { position: absolute; left: -9999px; top: -9999px; }
/* Search UI */
#searchBox {
    width: 100%;
    box-sizing: border-box;
    padding: 11px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 15px;
    font-family: 'Nunito', sans-serif;
    margin-bottom: 18px;
    outline: none;
}
#searchBox:focus { border-color: var(--accent); }
#searchDiv details { margin-bottom: 16px; }
#searchDiv summary.title {
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 12px;
    color: var(--muted);
    cursor: pointer;
    user-select: none;
    padding: 6px 0;
    list-style: none;
}
#searchDiv summary.title::-webkit-details-marker { display: none; }
ul.together {
    list-style: none;
    padding: 0;
    margin: 6px 0 0;
    column-count: 2;
    column-gap: 16px;
}
ul.together li { padding: 2px 0; font-size: 13px; break-inside: avoid; }
#exactMatch {
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 16px;
}
.tag-opt {
    background: var(--tag-opt);
    color: var(--tag-opt-text);
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 11px;
    font-family: monospace;
}
@media (max-width: 600px) {
    ul.together { column-count: 1; }
    h1 { font-size: 1.3rem; }
}
"""

# --- HTML helpers

FONTS = '<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=Source+Code+Pro&display=swap" rel="stylesheet">'

CP_SCRIPT = """<textarea id="c" class="invisible"></textarea>
<script>function cp(t){var c=document.getElementById("c");c.value=t;c.select();try{document.execCommand("copy")}catch(e){}}</script>"""


def page(title: str, depth: str, body: str, *, show_search: bool = True) -> str:
    search_script = f'<script>prependPath="{depth}";</script><script src="{depth}js/search.js"></script>' if show_search else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)} - ferogram API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="{depth}css/docs.css">
{FONTS}
</head>
<body>
<div id="main_div">
{body}
{CP_SCRIPT}
</div>
{search_script}
</body>
</html>"""


def breadcrumb(items: list[tuple[str, str | None]]) -> str:
    parts = []
    for i, (label, url) in enumerate(items):
        if url:
            parts.append(f'<li><a href="{url}">{html.escape(label)}</a></li>')
        else:
            parts.append(f'<li>{html.escape(label)}</li>')
        if i < len(items) - 1:
            parts.append('<span class="sep">›</span>')
    return f'<ul class="horizontal">{"".join(parts)}</ul>'


def fields_table(item: TLItem, known_types: set[str], depth: str) -> str:
    if not item.fields:
        return "<p>This item has no parameters.</p>"
    rows = ""
    for f in item.fields:
        note = '<span class="tag-opt">optional</span>' if f.optional else "Required."
        rows += f"<tr><td>{html.escape(f.name)}</td><td>{link_type(f.ftype, known_types, depth)}</td><td>{note}</td></tr>\n"
    return f"<table>{rows}</table>"


def type_link_row(abstract: str, depth: str) -> str:
    url = abstract_type_url(abstract, depth)
    return f'<tr><td><a href="{url}">{html.escape(abstract)}</a></td></tr>'


# --- Page generators

def gen_constructor_page(
    item: TLItem,
    known_types: set[str],
    out: Path,
) -> None:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Constructors", f"{depth}constructors/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}constructors/{ns}/index.html"))
    crumbs.append((cls, None))

    tl_def = render_tl_def(item, known_types, depth)
    imp = html.escape(import_type(item))
    fields_html = fields_table(item, known_types, depth)
    ret_row = type_link_row(item.ret, depth)

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<pre>{tl_def}</pre>
<button class="copy-btn" onclick="cp('{imp}')">Copy import</button>
<h3>Belongs to</h3>
<table>{ret_row}</table>
<h3>Members</h3>
{fields_html}
"""
    dest = out / constructor_url(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(cls, depth, body), encoding="utf-8")


def gen_abstract_type_page(
    abstract: str,
    constructors: list[TLItem],
    out: Path,
) -> None:
    ns = tl_ns(abstract)
    base = tl_base(abstract)
    cls = py_class(abstract)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Types", f"{depth}types/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}types/{ns}/index.html"))
    crumbs.append((abstract, None))

    rows = ""
    for c in constructors:
        url = constructor_url(c, depth)
        rows += f'<tr><td><a href="{url}">{html.escape(py_class(c.tl_name))}</a></td></tr>\n'

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(abstract)}</h1>
<h3>Constructors</h3>
<p>This type can be an instance of:</p>
<table>{rows}</table>
"""
    dest = out / abstract_type_url(abstract)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(abstract, depth, body), encoding="utf-8")


def gen_method_page(
    item: TLItem,
    known_types: set[str],
    out: Path,
) -> None:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Methods", f"{depth}methods/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}methods/{ns}/index.html"))
    crumbs.append((cls, None))

    tl_def = render_tl_def(item, known_types, depth)
    imp = html.escape(import_func(item))
    fields_html = fields_table(item, known_types, depth)
    ret_linked = link_type(item.ret, known_types, depth)

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<pre>{tl_def}</pre>
<button class="copy-btn" onclick="cp('{imp}')">Copy import</button>
<h3>Returns</h3>
<table><tr><td>{ret_linked}</td></tr></table>
<h3>Parameters</h3>
{fields_html}
"""
    dest = out / method_url(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(cls, depth, body), encoding="utf-8")


def gen_ns_index(
    section: str,
    ns: str,
    items: list[TLItem | tuple],
    out: Path,
    depth: str = "../../",
    label_fn=None,
    url_fn=None,
) -> None:
    rows = ""
    for item in sorted(items, key=lambda i: tl_base(i.tl_name if hasattr(i, "tl_name") else i[0])):
        if hasattr(item, "tl_name"):
            cls = py_class(item.tl_name)
            if section == "constructors":
                url = constructor_url(item, depth)
            else:
                url = method_url(item, depth)
        else:
            abstract, _ = item
            cls = abstract
            url = abstract_type_url(abstract, depth)
        rows += f'<li><a href="{url}">{html.escape(cls)}</a></li>\n'

    title = f"{ns.title()} - {section.title()}"
    crumbs = [
        ("API", f"{depth}index.html"),
        (section.title(), f"{depth}{section}/index.html"),
        (ns.title(), None),
    ]
    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(ns.title())}</h1>
<ul class="together">
{rows}
</ul>
"""
    dest = out / section / ns / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(title, depth, body), encoding="utf-8")


def gen_section_index(
    section: str,
    ns_map: dict[str, list],
    out: Path,
    depth: str = "../",
    url_fn=None,
) -> None:
    ns_list = sorted(ns for ns in ns_map if ns != "_base")
    base_items = ns_map.get("_base", [])

    ns_rows = "".join(
        f'<li><a href="{depth}{section}/{ns}/index.html">{html.escape(ns)}</a> '
        f'<span style="color:var(--muted)">({len(ns_map[ns])})</span></li>\n'
        for ns in ns_list
    )
    base_rows = ""
    for item in sorted(base_items, key=lambda i: tl_base(i.tl_name if hasattr(i, "tl_name") else i[0])):
        if hasattr(item, "tl_name"):
            cls = py_class(item.tl_name)
            if section == "constructors":
                url = constructor_url(item, depth)
            elif section == "methods":
                url = method_url(item, depth)
            else:
                url = abstract_type_url(item.tl_name, depth)
        else:
            abstract, _ = item
            cls = abstract
            url = abstract_type_url(abstract, depth)
        base_rows += f'<li><a href="{url}">{html.escape(cls)}</a></li>\n'

    total = sum(len(v) for v in ns_map.values())
    crumbs = [("API", f"{depth}index.html"), (section.title(), None)]
    body = f"""
{breadcrumb(crumbs)}
<h1>{section.title()} <span style="color:var(--muted);font-size:1rem">({total})</span></h1>
{"<h3>Namespaces</h3><ul class='together'>" + ns_rows + "</ul>" if ns_rows else ""}
{"<h3>Base</h3><ul class='together'>" + base_rows + "</ul>" if base_rows else ""}
"""
    dest = out / section / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(section.title(), depth, body), encoding="utf-8")


# --- search.js

def gen_search_js(
    types_list: list[TLItem],
    funcs_list: list[TLItem],
    abstract_types: list[str],
    out: Path,
) -> None:
    requests = json.dumps([py_class(f.tl_name) for f in funcs_list])
    requestsu = json.dumps([method_url(f) for f in funcs_list])
    types_names = json.dumps(abstract_types)
    typesu_list = json.dumps([abstract_type_url(t) for t in abstract_types])
    constructors = json.dumps([py_class(t.tl_name) for t in types_list])
    constructorsu = json.dumps([constructor_url(t) for t in types_list])

    js = f"""/* ferogram API search - auto-generated, do not edit */
root = document.getElementById("main_div");
root.innerHTML = `
<input id="searchBox" type="text" onkeyup="updateSearch(event)"
       placeholder="Search methods and types…" />
<div id="searchDiv">
  <div id="exactMatch" style="display:none">
    <b>Exact match:</b>
    <ul id="exactList" class="together"></ul>
  </div>
  <details id="methods" open><summary class="title">Methods (<span id="methodsCount">0</span>)</summary>
    <ul id="methodsList" class="together"></ul>
  </details>
  <details id="types" open><summary class="title">Types (<span id="typesCount">0</span>)</summary>
    <ul id="typesList" class="together"></ul>
  </details>
  <details id="constructors"><summary class="title">Constructors (<span id="constructorsCount">0</span>)</summary>
    <ul id="constructorsList" class="together"></ul>
  </details>
</div>
<div id="contentDiv">
` + root.innerHTML + "</div>";

var contentDiv = document.getElementById("contentDiv");
var searchDiv  = document.getElementById("searchDiv");
var searchBox  = document.getElementById("searchBox");

var methodsDetails     = document.getElementById("methods");
var methodsList        = document.getElementById("methodsList");
var methodsCount       = document.getElementById("methodsCount");

var typesDetails  = document.getElementById("types");
var typesList     = document.getElementById("typesList");
var typesCount    = document.getElementById("typesCount");

var constructorsDetails = document.getElementById("constructors");
var constructorsList    = document.getElementById("constructorsList");
var constructorsCount   = document.getElementById("constructorsCount");

var exactMatch = document.getElementById("exactMatch");
var exactList  = document.getElementById("exactList");

try {{
    var requests     = {requests};
    var types        = {types_names};
    var constructors = {constructors};
    var requestsu    = {requestsu};
    var typesu       = {typesu_list};
    var constructorsu = {constructorsu};
}} catch(e) {{}}

var prependPath = (typeof prependPath !== "undefined") ? prependPath : "";

function makeLink(name, url) {{
    return '<a href="' + prependPath + url + '">' + name + '</a>';
}}

function updateSearch(event) {{
    var q = searchBox.value.trim().toLowerCase();
    if (!q) {{
        contentDiv.style.display = "";
        searchDiv.style.display  = "none";
        return;
    }}
    contentDiv.style.display = "none";
    searchDiv.style.display  = "";

    var exact = [];
    var mList = [], tList = [], cList = [];

    for (var i = 0; i < requests.length; i++) {{
        var n = requests[i]; var lower = n.toLowerCase();
        if (lower === q) exact.push(makeLink(n, requestsu[i]));
        else if (lower.includes(q)) mList.push(makeLink(n, requestsu[i]));
    }}
    for (var i = 0; i < types.length; i++) {{
        var n = types[i]; var lower = n.toLowerCase();
        if (lower === q) exact.push(makeLink(n, typesu[i]));
        else if (lower.includes(q)) tList.push(makeLink(n, typesu[i]));
    }}
    for (var i = 0; i < constructors.length; i++) {{
        var n = constructors[i]; var lower = n.toLowerCase();
        if (lower === q) exact.push(makeLink(n, constructorsu[i]));
        else if (lower.includes(q)) cList.push(makeLink(n, constructorsu[i]));
    }}

    exactMatch.style.display = exact.length ? "" : "none";
    exactList.innerHTML = exact.map(function(x){{return "<li>"+x+"</li>";}}).join("");

    methodsList.innerHTML = mList.map(function(x){{return "<li>"+x+"</li>";}}).join("");
    methodsCount.textContent = mList.length;

    typesList.innerHTML = tList.map(function(x){{return "<li>"+x+"</li>";}}).join("");
    typesCount.textContent = tList.length;

    constructorsList.innerHTML = cList.map(function(x){{return "<li>"+x+"</li>";}}).join("");
    constructorsCount.textContent = cList.length;
}}

var qParam = new URLSearchParams(window.location.search).get("q");
if (qParam) {{ searchBox.value = qParam; updateSearch({{}}); }}
"""

    (out / "js").mkdir(parents=True, exist_ok=True)
    (out / "js" / "search.js").write_text(js, encoding="utf-8")


# --- Root index

def gen_root_index(
    layer: int,
    n_types: int,
    n_constructors: int,
    n_methods: int,
    out: Path,
) -> None:
    body = f"""
<h1>ferogram API <span style="color:var(--muted);font-size:1rem">Layer {layer}</span></h1>
<p>Raw Telegram MTProto API reference, auto-generated from <code>raw_api.tl</code> (Layer {layer}).
Use the search box below or browse by section.</p>
<p>
  <a href="methods/index.html">Methods</a> ({n_methods}) ·
  <a href="types/index.html">Types</a> ({n_types}) ·
  <a href="constructors/index.html">Constructors</a> ({n_constructors})
</p>
<h3>Usage</h3>
<pre># namespace style
from ferogram.raw.functions.messages import GetHistory
result = await client(GetHistory(peer=..., limit=100, ...))

# flat style
from ferogram import raw
result = await client(raw.functions.messages.GetHistory(peer=..., limit=100, ...))</pre>

<h3 id="vector">Core types</h3>
<table>
<tr><td><b id="int">int</b></td><td>A 32-bit integer.</td></tr>
<tr><td><b id="long">long</b></td><td>A 64-bit integer.</td></tr>
<tr><td><b>bool</b> / <b>true</b></td><td>A boolean value.</td></tr>
<tr><td><b>string</b></td><td>A UTF-8 string.</td></tr>
<tr><td><b>bytes</b></td><td>Arbitrary binary data.</td></tr>
<tr><td><b>double</b></td><td>A 64-bit float.</td></tr>
<tr><td><b id="vector">Vector&lt;T&gt;</b></td><td>A list of T.</td></tr>
</table>
"""
    (out / "index.html").write_text(page("ferogram API", "", body), encoding="utf-8")


def gen_404(out: Path) -> None:
    body = """<h1>404</h1><p>Page not found. <a href="index.html">Go home</a>.</p>"""
    (out / "404.html").write_text(page("404", "", body, show_search=False), encoding="utf-8")


# --- Main

def main() -> None:
    tl_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ferogram/raw_api.tl")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/site")

    if not tl_path.exists():
        print(f"ERROR: TL file not found: {tl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {tl_path} …")
    types_list, funcs_list = parse_tl(tl_path)
    layer = parse_layer(tl_path)
    print(f"  Layer {layer}: {len(types_list)} constructors, {len(funcs_list)} functions")

    # Build set of all abstract type names (ret values of types)
    abstract_types_map: dict[str, list[TLItem]] = defaultdict(list)
    for t in types_list:
        abstract_types_map[t.ret].append(t)
    abstract_types_sorted = sorted(abstract_types_map.keys())
    known_types: set[str] = set(abstract_types_map.keys())

    # Output dir
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    # CSS
    (out_dir / "css").mkdir()
    (out_dir / "css" / "docs.css").write_text(CSS, encoding="utf-8")

    # search.js
    gen_search_js(types_list, funcs_list, abstract_types_sorted, out_dir)

    # Constructor pages
    cons_ns_map: dict[str, list[TLItem]] = defaultdict(list)
    for t in types_list:
        gen_constructor_page(t, known_types, out_dir)
        cons_ns_map[tl_ns(t.tl_name)].append(t)
    print(f"  {len(types_list)} constructor pages")

    # Constructor ns indexes
    for ns, items in cons_ns_map.items():
        if ns != "_base":
            gen_ns_index("constructors", ns, items, out_dir)
    gen_section_index("constructors", cons_ns_map, out_dir)

    # Abstract type pages
    for abstract, constructors in abstract_types_map.items():
        gen_abstract_type_page(abstract, constructors, out_dir)
    types_ns_map: dict[str, list] = defaultdict(list)
    for abstract in abstract_types_sorted:
        types_ns_map[tl_ns(abstract)].append((abstract, abstract_types_map[abstract]))
    for ns, items in types_ns_map.items():
        if ns != "_base":
            gen_ns_index("types", ns, items, out_dir)
    gen_section_index("types", types_ns_map, out_dir)
    print(f"  {len(abstract_types_map)} type pages")

    # Method pages
    method_ns_map: dict[str, list[TLItem]] = defaultdict(list)
    for f in funcs_list:
        gen_method_page(f, known_types, out_dir)
        method_ns_map[tl_ns(f.tl_name)].append(f)
    for ns, items in method_ns_map.items():
        if ns != "_base":
            gen_ns_index("methods", ns, items, out_dir)
    gen_section_index("methods", method_ns_map, out_dir)
    print(f"  {len(funcs_list)} method pages")

    # Root index + 404
    gen_root_index(layer, len(abstract_types_map), len(types_list), len(funcs_list), out_dir)
    gen_404(out_dir)

    print(f"\nDone → {out_dir}/")


if __name__ == "__main__":
    main()
