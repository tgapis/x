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
        item = TLItem(name, int(cid_hex, 16), parse_fields(fields_raw), ret, in_functions)
        (funcs if in_functions else types).append(item)
    return types, funcs


def parse_layer(path: Path) -> int:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^//\s*LAYER\s+(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return 0



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
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def url_slug(tl_name: str) -> str:
    return camel_to_snake(tl_base(tl_name)) + ".html"


def constructor_url(item: TLItem, depth: str = "") -> str:
    ns = tl_ns(item.tl_name)
    slug = url_slug(item.tl_name)
    return f"{depth}constructors/{ns}/{slug}" if ns != "_base" else f"{depth}constructors/{slug}"


def abstract_type_url(abstract: str, depth: str = "") -> str:
    ns = tl_ns(abstract)
    slug = camel_to_snake(tl_base(abstract)) + ".html"
    return f"{depth}types/{ns}/{slug}" if ns != "_base" else f"{depth}types/{slug}"


def method_url(item: TLItem, depth: str = "") -> str:
    ns = tl_ns(item.tl_name)
    slug = url_slug(item.tl_name)
    return f"{depth}methods/{ns}/{slug}" if ns != "_base" else f"{depth}methods/{slug}"


def import_type(item: TLItem) -> str:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    return f"from ferogram.raw.types.{ns} import {cls}" if ns != "_base" else f"from ferogram.raw.types import {cls}"


def import_func(item: TLItem) -> str:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    return f"from ferogram.raw.functions.{ns} import {cls}" if ns != "_base" else f"from ferogram.raw.functions import {cls}"



PRIMITIVES = {
    "int", "long", "double", "string", "bytes", "Bool",
    "int128", "int256", "true", "True", "Int", "Long", "bool", "date",
}


def link_type(ftype: str, known_types: set[str], depth: str) -> str:
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        return f'<a href="{depth}index.html#vector">Vector</a>&lt;{link_type(inner, known_types, depth)}&gt;'
    if ftype in PRIMITIVES:
        return f'<a href="{depth}index.html#{ftype.lower()}">{html.escape(ftype)}</a>'
    if ftype in known_types:
        return f'<a href="{abstract_type_url(ftype, depth)}">{html.escape(ftype)}</a>'
    return html.escape(ftype)


def render_tl_def(item: TLItem, known_types: set[str], depth: str) -> str:
    header = "---functions---" if item.is_function else "---types---"
    cid_hex = f"{item.cid:08x}"
    name_part = html.escape(item.tl_name)
    cid_part = f'<span style="color:var(--tl-cid)">#{cid_hex}</span>'
    parts = [f"{name_part}{cid_part}"]
    for f in item.fields:
        if f.flag_bit is not None:
            parts.append(f" {html.escape(f.name)}:flags.{f.flag_bit}?{link_type(f.ftype, known_types, depth)}")
        else:
            parts.append(f" {html.escape(f.name)}:{link_type(f.ftype, known_types, depth)}")
    ret_linked = link_type(item.ret, known_types, depth)
    header_html = f'<span style="color:var(--muted)">{header}</span>'
    return f"{header_html}\n{''.join(parts)} = {ret_linked}"



KNOWN_NAMED = {
    ("message", "string"): "'Hello there!'",
    ("title", "string"): "'My title'",
    ("hash", "int"): "0",
    ("hash", "long"): "0",
    ("limit", "int"): "100",
    ("offset", "int"): "0",
    ("min_id", "int"): "0",
    ("max_id", "int"): "0",
    ("min_id", "long"): "0",
    ("max_id", "long"): "0",
    ("add_offset", "int"): "0",
    ("random_id", "long"): "random.randrange(-2**63, 2**63)",
}

# Primitive types used in proxy-style (minimal) examples.
KNOWN_TYPED_PROXY = {
    "int": "42",
    "long": "-12398745604826",
    "string": "'some string here'",
    "bytes": "b'arbitrary\\x7f data'",
    "Bool": "False",
    "true": "True",
    "bool": "False",
    "double": "7.13",
    "int128": "int.from_bytes(os.urandom(16), 'big')",
    "int256": "int.from_bytes(os.urandom(32), 'big')",
    "date": "int(__import__('time').time())",
    # Proxy auto-resolves these from strings:
    "InputPeer": "'username'",
    "InputUser": "'username'",
    "InputChannel": "'username'",
}

# In callable-style (full) examples InputPeer fields must be real TL objects.
KNOWN_TYPED_CALLABLE = {
    **KNOWN_TYPED_PROXY,
    "InputPeer": "raw.types.InputPeerSelf()",
    "InputUser": "raw.types.InputUserSelf()",
    "InputChannel": "raw.types.InputChannelEmpty()",
}

# Simplest concrete constructor for abstract TL types not covered above.
CONCRETE_DEFAULTS: dict[str, str] = {
    "InputMedia":              "raw.types.InputMediaEmpty()",
    "InputReplyTo":            "raw.types.InputReplyToMessage(reply_to_msg_id=42)",
    "ReplyMarkup":             "raw.types.ReplyKeyboardHide()",
    "InputQuickReplyShortcut": "raw.types.InputQuickReplyShortcutId(shortcut_id=0)",
    "SuggestedPost":           "raw.types.SuggestedPost(date=0)",
    "MessageEntity":           "raw.types.MessageEntityUnknown(offset=0, length=1)",
    "InputPhoto":              "raw.types.InputPhotoEmpty()",
    "InputDocument":           "raw.types.InputDocumentEmpty()",
    "InputGeoPoint":           "raw.types.InputGeoPointEmpty()",
    "InputNotifyPeer":         "raw.types.InputNotifyUsers()",
    "InputCheckPasswordSRP":   "raw.types.InputCheckPasswordEmpty()",
    "InputPrivacyKey":         "raw.types.InputPrivacyKeyStatusTimestamp()",
    "InputPrivacyRule":        "raw.types.InputPrivacyValueAllowAll()",
    "EmojiGroup":              "raw.types.EmojiGroupGreeting()",
}

SYNONYMS = {
    "InputUser": "InputPeer",
    "InputChannel": "InputPeer",
    "InputDialogPeer": "InputPeer",
    "InputNotifyPeer": "InputPeer",
    "InputMessage": "int",
}

_PEER_PROXY_TYPES = {"InputPeer", "InputUser", "InputChannel",
                     "InputDialogPeer", "InputNotifyPeer"}


def example_value(fname: str, ftype: str, *, proxy: bool) -> str:
    """Return a Python expression for a field value in a code example.

    proxy=True  -> minimal/proxy style (peer strings OK, no raw. prefix needed)
    proxy=False -> callable style (all TL objects must be concrete raw.types.X())
    """
    key = (fname, ftype)
    if key in KNOWN_NAMED:
        return KNOWN_NAMED[key]

    typed = KNOWN_TYPED_PROXY if proxy else KNOWN_TYPED_CALLABLE
    ftype2 = SYNONYMS.get(ftype, ftype)
    if ftype2 in typed:
        return typed[ftype2]
    if ftype in typed:
        return typed[ftype]

    # Abstract TL type: use concrete default if known, else raw.types.X()
    if ftype in CONCRETE_DEFAULTS:
        return CONCRETE_DEFAULTS[ftype]
    if ftype2 in CONCRETE_DEFAULTS:
        return CONCRETE_DEFAULTS[ftype2]

    cls = py_class(ftype) if ftype and ftype[0].isupper() else ftype
    return f"raw.types.{cls}()"


def _needs_random(args: list) -> bool:
    return any(
        KNOWN_NAMED.get((f.name, f.ftype), "").startswith("random.")
        for f in args
    )


def _needs_os(args: list) -> bool:
    return any(
        f.ftype in ("int128", "int256")
        for f in args
    )


def build_example(item: TLItem, required_only: bool) -> str:
    ns = tl_ns(item.tl_name)
    mod = f"functions.{ns}" if ns != "_base" else "functions"
    cls = py_class(item.tl_name)

    if required_only:
        args = [f for f in item.fields if not f.optional and f.name != "flags"]
    else:
        args = [f for f in item.fields if f.name != "flags"]

    need_random = _needs_random(args)
    need_os     = _needs_os(args)

    if required_only:
        # Minimal: raw proxy style (way 4). Proxy auto-resolves peer strings.
        proxy_ns = f"raw.{ns}" if ns != "_base" else "raw"
        imports = ["import asyncio"]
        if need_random:
            imports.append("import random")
        if need_os:
            imports.append("import os")
        imports.append("from ferogram import Client, raw")

        if not args:
            call_line = f"    result = await app.{proxy_ns}.{cls}()"
        else:
            call_lines = [f"    result = await app.{proxy_ns}.{cls}("]
            for i, f in enumerate(args):
                comma = "," if i < len(args) - 1 else ""
                call_lines.append(
                    f"        {f.name}={example_value(f.name, f.ftype, proxy=True)}{comma}"
                )
            call_lines.append("    )")
            call_line = "\n".join(call_lines)

        lines = imports + [
            "",
            'app = Client("my_session", api_id=12345, api_hash="0123456789abcdef0123456789abcdef")',
            "",
            "async def main():",
            "    await app.start()",
            call_line,
            "    print(result)",
            "",
            "asyncio.run(main())",
        ]
    else:
        # Full: callable style (way 1). All TL objects must be concrete types.
        imports = ["import asyncio"]
        if need_random:
            imports.append("import random")
        if need_os:
            imports.append("import os")
        imports.append("from ferogram import Client, raw")

        if not args:
            call_line = f"    result = await app(raw.{mod}.{cls}())"
        else:
            call_lines = [f"    result = await app(raw.{mod}.{cls}("]
            for i, f in enumerate(args):
                comma = "," if i < len(args) - 1 else ""
                call_lines.append(
                    f"        {f.name}={example_value(f.name, f.ftype, proxy=False)}{comma}"
                )
            call_lines.append("    ))")
            call_line = "\n".join(call_lines)

        lines = imports + [
            "",
            'app = Client("my_session", api_id=12345, api_hash="0123456789abcdef0123456789abcdef")',
            "",
            "async def main():",
            "    await app.start()",
            call_line,
            "    print(result)",
            "",
            "asyncio.run(main())",
        ]
    return "\n".join(lines)



CSS_COMMON = """\
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
    font-family: 'Nunito', system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
    padding: 0;
    transition: background 0.2s, color 0.2s;
}
a { text-decoration: none; }
a:hover { text-decoration: underline; }
#main_div {
    max-width: 900px;
    margin: 0 auto;
    padding: 24px 20px 60px;
}
h1 { font-size: 1.8rem; font-weight: 700; margin: 12px 0 20px; }
h3 {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 28px 0 10px;
}
pre {
    font-family: 'Source Code Pro', monospace;
    font-size: 13px;
    padding: 14px 16px;
    border-radius: 6px;
    overflow-x: auto;
    border-width: 1px;
    border-style: solid;
    line-height: 1.6;
}
code { font-family: 'Source Code Pro', monospace; font-size: 13px; }
table { width: 100%; border-collapse: collapse; margin: 0; }
table td {
    border-top-width: 1px;
    border-top-style: solid;
    padding: 9px 12px;
    vertical-align: top;
    font-size: 14px;
}
table td:first-child { font-weight: 600; font-family: monospace; font-size: 13px; }
ul.horizontal {
    list-style: none;
    padding: 8px 14px;
    margin: 0 0 20px;
    border-radius: 6px;
    border-width: 1px;
    border-style: solid;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    flex-wrap: wrap;
}
ul.horizontal li { display: inline; }
.sep { user-select: none; }
button.copy-btn {
    display: inline-block;
    margin: 12px 0 20px;
    padding: 7px 14px;
    border-width: 1px;
    border-style: solid;
    border-radius: 5px;
    font-size: 13px;
    font-family: 'Source Code Pro', monospace;
    cursor: pointer;
    transition: background 0.15s;
}
.tag-opt { border-radius: 3px; padding: 1px 5px; font-size: 11px; font-family: monospace; }
.tag-req { border-radius: 3px; padding: 1px 5px; font-size: 11px; font-family: monospace; }
#theme-btn {
    position: fixed; top: 14px; right: 16px;
    padding: 5px 12px; border-radius: 20px;
    border-width: 1px; border-style: solid;
    font-size: 12px; cursor: pointer; z-index: 999;
    font-family: 'Nunito', sans-serif;
    transition: background 0.2s, color 0.2s;
}
#searchBox {
    width: 100%; padding: 11px 14px;
    border-radius: 6px; border-width: 1px; border-style: solid;
    font-size: 15px; font-family: 'Nunito', sans-serif;
    margin-bottom: 18px; outline: none;
}
#searchDiv details { margin-bottom: 16px; }
#searchDiv summary.title {
    font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; font-size: 12px;
    cursor: pointer; user-select: none; padding: 6px 0; list-style: none;
}
#searchDiv summary.title::-webkit-details-marker { display: none; }
ul.together {
    list-style: none; padding: 0; margin: 6px 0 0;
    column-count: 2; column-gap: 16px;
}
ul.together li { padding: 2px 0; font-size: 13px; break-inside: avoid; }
#exactMatch { border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; border-width: 1px; border-style: solid; }
.invisible { position: absolute; left: -9999px; top: -9999px; }
details.example > summary { cursor: pointer; font-size: 13px; user-select: none; margin-bottom: 6px; font-family: 'Source Code Pro', monospace; list-style: none; }
details.example > summary::-webkit-details-marker { display: none; }
details.example > summary::marker { display: none; }
details.example { margin-bottom: 12px; }
.example-note { font-size: 13px; color: var(--muted); margin: 6px 0 14px; font-family: 'Source Code Pro', monospace; }
.example-note strong { color: var(--accent-light); }
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; margin-bottom: 0; }
.tab { padding: 7px 14px; font-size: 12px; cursor: pointer; font-family: 'Source Code Pro', monospace; color: var(--muted); border: none; background: none; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color .15s, border-color .15s; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.way-content { display: none; }
.way-content.active { display: block; }
.way-content pre { border-top: none; border-radius: 0 0 8px 8px; margin-top: 0; }
@media (max-width: 600px) {
    ul.together { column-count: 1; }
    h1 { font-size: 1.3rem; }
    #theme-btn { top: 8px; right: 8px; }
}
.pill {
    padding: 5px 13px; border-radius: 20px;
    border-width: 1px; border-style: solid;
    font-size: 13px; text-decoration: none;
    display: inline-block; transition: background .15s, border-color .15s;
}
.pill:hover { text-decoration: none; }
.links-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 22px; }
pre { position: relative; }
.copy-icon {
    position: absolute; top: 8px; right: 8px;
    opacity: 0; transition: opacity .15s;
    border-radius: 4px; padding: 2px 8px; font-size: 11px;
    cursor: pointer; border-width: 1px; border-style: solid;
    font-family: 'Source Code Pro', monospace; line-height: 1.6;
}
pre:hover .copy-icon { opacity: 1; }
details.example > summary .arrow {
    display: inline-block; transition: transform .18s; margin-right: 4px;
}
details.example[open] > summary .arrow { transform: rotate(90deg); }
.hint {
    font-size: 11px; margin-bottom: 18px;
    font-family: 'Source Code Pro', monospace;
    padding: 5px 10px; border-radius: 6px; display: inline-block;
}
.py-k { color: var(--hl-kw); }
.py-s { color: var(--hl-str); }
.py-c { color: var(--hl-cmt); font-style: italic; }
.py-n { color: var(--hl-num); }
"""

CSS_DARK_VARS = """\
:root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e2e4f0; --muted: #8b8fa8; --accent: #7c6af7;
    --accent-light: #a99ff8; --code-bg: #161923; --code-text: #c9d1e0;
    --link: #7c6af7; --link-hover: #a99ff8;
    --tag-opt-bg: #1a3040; --tag-opt-text: #5db8e8;
    --tag-req-bg: #1a2e1a; --tag-req-text: #6ecb6e;
    --btn-bg: #251f4a; --btn-border: #7c6af7; --btn-text: #a99ff8; --btn-hover: #321f7a;
    --tl-cid: #c08858;
    --hl-kw: #bb8af7; --hl-str: #7ec898; --hl-cmt: #5c6380; --hl-num: #e8a87c;
}
"""

CSS_DARK_RULES = """\
body { background: var(--bg); color: var(--text); }
a { color: var(--link); } a:hover { color: var(--link-hover); }
pre { background: var(--code-bg); color: var(--code-text); border-color: var(--border); }
table td { border-top-color: var(--border); }
table td:first-child { color: var(--text); }
table td:nth-child(2) { color: var(--accent-light); }
table td:last-child { color: var(--muted); font-size: 13px; }
ul.horizontal { background: var(--surface); border-color: var(--border); }
ul.horizontal li { color: var(--muted); } ul.horizontal li a { color: var(--link); }
.sep { color: var(--border); }
button.copy-btn { background: var(--btn-bg); color: var(--btn-text); border-color: var(--btn-border); }
button.copy-btn:hover { background: var(--btn-hover); }
.tag-opt { background: var(--tag-opt-bg); color: var(--tag-opt-text); }
.tag-req { background: var(--tag-req-bg); color: var(--tag-req-text); }
#theme-btn { background: var(--surface); border-color: var(--border); color: var(--muted); }
#theme-btn:hover { border-color: var(--accent); color: var(--accent-light); }
#searchBox { background: var(--surface); border-color: var(--border); color: var(--text); }
#searchBox:focus { border-color: var(--accent); }
#searchDiv summary.title { color: var(--muted); }
#exactMatch { background: var(--surface); border-color: var(--accent); }
h3 { color: var(--muted); }
.pill { background: var(--surface); border-color: var(--border); color: var(--link); }
.pill:hover { background: var(--btn-bg); border-color: var(--accent); }
.copy-icon { background: var(--surface); border-color: var(--border); color: var(--muted); }
.copy-icon:hover { border-color: var(--accent); color: var(--accent-light); }
.hint { background: var(--surface); color: var(--muted); }
"""

CSS_LIGHT_VARS = """\
:root {
    --bg: #ffffff; --surface: #f5f6fa; --border: #d0d3e0;
    --text: #1a1c2e; --muted: #6b6f87; --accent: #5b4fcf;
    --accent-light: #7c6af7; --code-bg: #f0f1f8; --code-text: #2a2d4a;
    --link: #5b4fcf; --link-hover: #7c6af7;
    --tag-opt-bg: #dbeafe; --tag-opt-text: #1d4ed8;
    --tag-req-bg: #dcfce7; --tag-req-text: #166534;
    --btn-bg: #ede9ff; --btn-border: #7c6af7; --btn-text: #5b4fcf; --btn-hover: #ddd6ff;
    --tl-cid: #a0560a;
    --hl-kw: #7335b8; --hl-str: #267f56; --hl-cmt: #8b8fa8; --hl-num: #b5520a;
}
"""

CSS_LIGHT_RULES = """\
body { background: var(--bg); color: var(--text); }
a { color: var(--link); } a:hover { color: var(--link-hover); }
pre { background: var(--code-bg); color: var(--code-text); border-color: var(--border); }
table td { border-top-color: var(--border); }
table td:first-child { color: var(--text); }
table td:nth-child(2) { color: var(--accent); }
table td:last-child { color: var(--muted); font-size: 13px; }
ul.horizontal { background: var(--surface); border-color: var(--border); }
ul.horizontal li { color: var(--muted); } ul.horizontal li a { color: var(--link); }
.sep { color: var(--border); }
button.copy-btn { background: var(--btn-bg); color: var(--btn-text); border-color: var(--btn-border); }
button.copy-btn:hover { background: var(--btn-hover); }
.tag-opt { background: var(--tag-opt-bg); color: var(--tag-opt-text); }
.tag-req { background: var(--tag-req-bg); color: var(--tag-req-text); }
#theme-btn { background: var(--surface); border-color: var(--border); color: var(--muted); }
#theme-btn:hover { border-color: var(--accent); color: var(--accent); }
#searchBox { background: var(--surface); border-color: var(--border); color: var(--text); }
#searchBox:focus { border-color: var(--accent); }
#searchDiv summary.title { color: var(--muted); }
#exactMatch { background: var(--surface); border-color: var(--accent); }
h3 { color: var(--muted); }
.pill { background: var(--surface); border-color: var(--border); color: var(--link); }
.pill:hover { background: var(--btn-bg); border-color: var(--accent); }
.copy-icon { background: var(--surface); border-color: var(--border); color: var(--muted); }
.copy-icon:hover { border-color: var(--accent); color: var(--accent); }
.hint { background: var(--surface); color: var(--muted); }
"""

CSS_AMOLED_VARS = """\
:root {
    --bg: #000000; --surface: #0a0a0a; --border: #1a1a1a;
    --text: #e8eaf6; --muted: #7a7e9a; --accent: #a78bfa;
    --accent-light: #c4b5fd; --code-bg: #050505; --code-text: #d0d4e8;
    --link: #a78bfa; --link-hover: #c4b5fd;
    --tag-opt-bg: #0d1020; --tag-opt-text: #60a5fa;
    --tag-req-bg: #0a1a0a; --tag-req-text: #4ade80;
    --btn-bg: #150e2a; --btn-border: #a78bfa; --btn-text: #c4b5fd; --btn-hover: #1e1040;
    --tl-cid: #d4a06a;
    --hl-kw: #d4a4fc; --hl-str: #86d0aa; --hl-cmt: #3a3e5a; --hl-num: #f0b478;
}
"""

CSS_AMOLED_RULES = """\
body { background: var(--bg); color: var(--text); }
a { color: var(--link); } a:hover { color: var(--link-hover); }
pre { background: var(--code-bg); color: var(--code-text); border-color: var(--border); }
table td { border-top-color: var(--border); }
table td:first-child { color: var(--text); }
table td:nth-child(2) { color: var(--accent-light); }
table td:last-child { color: var(--muted); font-size: 13px; }
ul.horizontal { background: var(--surface); border-color: var(--border); }
ul.horizontal li { color: var(--muted); } ul.horizontal li a { color: var(--link); }
.sep { color: var(--border); }
button.copy-btn { background: var(--btn-bg); color: var(--btn-text); border-color: var(--btn-border); }
button.copy-btn:hover { background: var(--btn-hover); }
.tag-opt { background: var(--tag-opt-bg); color: var(--tag-opt-text); }
.tag-req { background: var(--tag-req-bg); color: var(--tag-req-text); }
#theme-btn { background: var(--surface); border-color: var(--border); color: var(--muted); }
#theme-btn:hover { border-color: var(--accent); color: var(--accent-light); }
#searchBox { background: var(--surface); border-color: var(--border); color: var(--text); }
#searchBox:focus { border-color: var(--accent); }
#searchDiv summary.title { color: var(--muted); }
#exactMatch { background: var(--surface); border-color: var(--accent); }
h3 { color: var(--muted); }
.pill { background: var(--surface); border-color: var(--border); color: var(--link); }
.pill:hover { background: var(--btn-bg); border-color: var(--accent); }
.copy-icon { background: var(--surface); border-color: var(--border); color: var(--muted); }
.copy-icon:hover { border-color: var(--accent); color: var(--accent-light); }
.hint { background: var(--surface); color: var(--muted); }
"""

CSS_DARK   = CSS_DARK_VARS   + CSS_COMMON + CSS_DARK_RULES
CSS_LIGHT  = CSS_LIGHT_VARS  + CSS_COMMON + CSS_LIGHT_RULES
CSS_AMOLED = CSS_AMOLED_VARS + CSS_COMMON + CSS_AMOLED_RULES


FONTS = '<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=Source+Code+Pro&display=swap" rel="stylesheet">'

THEME_INIT = """\
<script>
(function(){
  var labels={'dark':'\u2600 Bright','light':'\u25c9 Amoled','amoled':'\u263e Dark'};
  var t=localStorage.getItem('theme')||'dark';
  document.getElementById('style').href=document.getElementById('style').href.replace(/(dark|light|amoled)\\.css/,t+'.css');
  document.getElementById('theme-btn').textContent=labels[t]||labels['dark'];
})();
</script>"""

THEME_BTN = """<button id="theme-btn" onclick="(function(){
  var themes=['dark','light','amoled'];
  var labels={'dark':'\u2600 Bright','light':'\u25c9 Amoled','amoled':'\u263e Dark'};
  var s=document.getElementById('style');
  var cur=themes.find(function(x){return s.href.includes('/'+x+'.css');})||'dark';
  var next=themes[(themes.indexOf(cur)+1)%themes.length];
  s.href=s.href.replace('/'+cur+'.css','/'+next+'.css');
  localStorage.setItem('theme',next);
  document.getElementById('theme-btn').textContent=labels[next];
})()">&#9728; Bright</button>"""

CP_SCRIPT = """<textarea id="c" class="invisible"></textarea>
<script>
function cp(t){var c=document.getElementById("c");c.value=t;c.select();try{document.execCommand("copy")}catch(e){}}
/* Python syntax highlighter */
function hlPy(t){
  var K='import|from|as|async|def|await|return|class|if|elif|else|for|in|not|and|or|None|True|False|pass|with|try|except|raise|yield|lambda'.split('|');
  function e(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  var o='',i=0,n=t.length;
  while(i<n){
    var c=t[i];
    if(c==='#'){var j=t.indexOf('\\n',i);j=j<0?n:j;o+='<span class="py-c">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    if(c==='"'||c==="'"){var q=c,j=i+1;while(j<n&&t[j]!==q){if(t[j]==='\\\\')j++;j++;}j++;o+='<span class="py-s">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    if(/[a-zA-Z_]/.test(c)){var j=i;while(j<n&&/[a-zA-Z0-9_]/.test(t[j]))j++;var w=t.slice(i,j);o+=K.indexOf(w)>=0?'<span class="py-k">'+w+'</span>':e(w);i=j;continue;}
    if(/[0-9]/.test(c)&&(i===0||!/[a-zA-Z_]/.test(t[i-1]))){var j=i;while(j<n&&/[0-9a-fA-FxXbBoO._]/.test(t[j]))j++;o+='<span class="py-n">'+t.slice(i,j)+'</span>';i=j;continue;}
    o+=e(c);i++;
  }
  return o;
}
function toast(){
  var d=document.createElement('div');
  d.textContent='Copied!';
  d.style.cssText='position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-family:monospace;z-index:9999;pointer-events:none;opacity:1;transition:opacity .4s';
  document.body.appendChild(d);
  setTimeout(function(){d.style.opacity='0';setTimeout(function(){d.remove();},400);},1200);
}
(function(){
  var _lpt=null;
  function attachLongPress(el){
    el.addEventListener('touchstart',function(){
      _lpt=setTimeout(function(){cp(el.innerText||el.textContent);toast();},600);
    },{passive:true});
    el.addEventListener('touchend',function(){clearTimeout(_lpt);});
    el.addEventListener('touchmove',function(){clearTimeout(_lpt);});
  }
  function addCopyIcon(pre){
    var btn=document.createElement('button');
    btn.className='copy-icon';btn.textContent='copy';
    btn.addEventListener('click',function(ev){
      ev.stopPropagation();
      cp(pre.textContent||pre.innerText);
      btn.textContent='\\u2713';toast();
      setTimeout(function(){btn.textContent='copy';},1300);
    });
    pre.appendChild(btn);
  }
  function init(){
    document.querySelectorAll('pre.python').forEach(function(p){p.innerHTML=hlPy(p.textContent);});
    document.querySelectorAll('pre').forEach(function(el){addCopyIcon(el);attachLongPress(el);});
  }
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',init);}else{init();}
})();
var _wayTabs=null,_wayCon=null;
function switchWayTab(n){
  if(!_wayTabs){_wayTabs=document.querySelectorAll('.tabs .tab');_wayCon=document.querySelectorAll('.way-content');}
  _wayTabs.forEach(function(t,i){t.classList.toggle('active',i===n);});
  _wayCon.forEach(function(c,i){c.classList.toggle('active',i===n);});
}
</script>"""


def page(title: str, depth: str, body: str, *, show_search: bool = True) -> str:
    search_script = (
        f'<script>prependPath="{depth}";</script>'
        f'<script src="{depth}js/search.js"></script>'
    ) if show_search else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)} - ferogram API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link id="style" rel="stylesheet" href="{depth}css/dark.css">
{FONTS}
</head>
<body>
{THEME_BTN}
{THEME_INIT}
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
        badge = '<span class="tag-opt">optional</span>' if f.optional else '<span class="tag-req">required</span>'
        rows += f"<tr><td>{html.escape(f.name)}</td><td>{link_type(f.ftype, known_types, depth)}</td><td>{badge}</td></tr>\n"
    return f"<table>{rows}</table>"


def item_table(items: list[TLItem], url_fn, depth: str) -> str:
    rows = ""
    for item in sorted(items, key=lambda i: py_class(i.tl_name)):
        url = url_fn(item, depth)
        rows += f'<tr><td><a href="{url}">{html.escape(py_class(item.tl_name))}</a></td></tr>\n'
    return f"<table>{rows}</table>" if rows else ""


def maybe_section(heading: str, items: list[TLItem], url_fn, depth: str) -> str:
    if not items:
        return f"<h3>{heading}</h3><p>None.</p>"
    return f"<h3>{heading}</h3>{item_table(items, url_fn, depth)}"



def gen_constructor_page(
    item: TLItem,
    known_types: set[str],
    funcs_accepting: list[TLItem],
    out: Path,
) -> None:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Constructors", f"{depth}constructors/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}constructors/{ns}/index.html"))
    crumbs.append((cls, None))

    imp = html.escape(import_type(item))
    ret_url = abstract_type_url(item.ret, depth)
    using = f"<h3>Used by</h3>{item_table(funcs_accepting, method_url, depth)}" if funcs_accepting else ""

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<pre class="tl">{render_tl_def(item, known_types, depth)}</pre>
<button class="copy-btn" onclick="cp('{imp}')">Copy import</button>
<h3>Belongs to</h3>
<table><tr><td><a href="{ret_url}">{html.escape(item.ret)}</a></td></tr></table>
<h3>Members</h3>
{fields_table(item, known_types, depth)}
{using}
"""
    dest = out / constructor_url(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(cls, depth, body), encoding="utf-8")


def gen_abstract_type_page(
    abstract: str,
    constructors: list[TLItem],
    funcs_returning: list[TLItem],
    funcs_accepting: list[TLItem],
    types_with_member: list[TLItem],
    out: Path,
) -> None:
    ns = tl_ns(abstract)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Types", f"{depth}types/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}types/{ns}/index.html"))
    crumbs.append((abstract, None))

    cons_rows = "".join(
        f'<tr><td><a href="{constructor_url(c, depth)}">{html.escape(py_class(c.tl_name))}</a></td></tr>\n'
        for c in sorted(constructors, key=lambda c: py_class(c.tl_name))
    )

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(abstract)}</h1>
<h3>Constructors</h3>
<p>This type can be an instance of:</p>
<table>{cons_rows}</table>
{maybe_section("Requests returning this type", funcs_returning, method_url, depth)}
{maybe_section("Requests accepting this type as input", funcs_accepting, method_url, depth)}
{maybe_section("Other types containing this type", types_with_member, constructor_url, depth)}
"""
    dest = out / abstract_type_url(abstract)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(abstract, depth, body), encoding="utf-8")


def gen_method_page(item: TLItem, known_types: set[str], out: Path) -> None:
    ns = tl_ns(item.tl_name)
    cls = py_class(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Methods", f"{depth}methods/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}methods/{ns}/index.html"))
    crumbs.append((cls, None))

    imp = html.escape(import_func(item))
    ret_linked = link_type(item.ret, known_types, depth)

    ex_min = html.escape(build_example(item, required_only=True))
    ex_full = html.escape(build_example(item, required_only=False))
    has_optional = any(f.optional for f in item.fields if f.name != "flags")

    note_html = """<p class="example-note">Minimal uses the raw proxy shorthand. To see the full method signature with all parameters, expand <strong>Full API</strong> below.</p>"""

    if has_optional:
        examples_html = f"""<h3>Example</h3>
<details class="example" open>
  <summary><span class="arrow">&#9654;</span> Minimal</summary>
  <pre class="python">{ex_min}</pre>
</details>
{note_html}
<details class="example">
  <summary><span class="arrow">&#9654;</span> Full API</summary>
  <pre class="python">{ex_full}</pre>
</details>"""
    else:
        examples_html = f"""<h3>Example</h3>
<details class="example" open>
  <summary><span class="arrow">&#9654;</span> Example</summary>
  <pre class="python">{ex_min}</pre>
</details>"""

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<p>Both users and bots can use this request.</p>
<pre class="tl">{render_tl_def(item, known_types, depth)}</pre>
<button class="copy-btn" onclick="cp('{imp}')">Copy import</button>
<h3>Returns</h3>
<table><tr><td>{ret_linked}</td></tr></table>
<h3>Parameters</h3>
{fields_table(item, known_types, depth)}
{examples_html}
"""
    dest = out / method_url(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(cls, depth, body), encoding="utf-8")


def gen_ns_index(section: str, ns: str, items: list, out: Path) -> None:
    depth = "../../"
    rows = ""
    for item in sorted(items, key=lambda i: tl_base(i.tl_name if hasattr(i, "tl_name") else i[0])):
        if hasattr(item, "tl_name"):
            cls = py_class(item.tl_name)
            url = (constructor_url if section == "constructors" else method_url)(item, depth)
        else:
            abstract, _ = item
            cls = abstract
            url = abstract_type_url(abstract, depth)
        rows += f'<li><a href="{url}">{html.escape(cls)}</a></li>\n'
    crumbs = [("API", f"{depth}index.html"), (section.title(), f"{depth}{section}/index.html"), (ns.title(), None)]
    body = f"{breadcrumb(crumbs)}\n<h1>{html.escape(ns.title())}</h1>\n<ul class='together'>\n{rows}</ul>"
    dest = out / section / ns / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page(f"{ns.title()} - {section.title()}", depth, body), encoding="utf-8")


def gen_section_index(section: str, ns_map: dict, out: Path) -> None:
    depth = "../"
    ns_list = sorted(ns for ns in ns_map if ns != "_base")
    base_items = ns_map.get("_base", [])

    ns_rows = "".join(
        f'<li><a href="{depth}{section}/{ns}/index.html">{html.escape(ns)}</a>'
        f' <span style="color:var(--muted)">({len(ns_map[ns])})</span></li>\n'
        for ns in ns_list
    )
    base_rows = ""
    for item in sorted(base_items, key=lambda i: tl_base(i.tl_name if hasattr(i, "tl_name") else i[0])):
        if hasattr(item, "tl_name"):
            cls = py_class(item.tl_name)
            url = (constructor_url if section == "constructors" else method_url)(item, depth)
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



def gen_search_js(types_list: list, funcs_list: list, abstract_types: list, out: Path) -> None:
    requests = json.dumps([py_class(f.tl_name) for f in funcs_list])
    requestsu = json.dumps([method_url(f) for f in funcs_list])
    type_names = json.dumps(abstract_types)
    typesu = json.dumps([abstract_type_url(t) for t in abstract_types])
    constructors = json.dumps([py_class(t.tl_name) for t in types_list])
    constructorsu = json.dumps([constructor_url(t) for t in types_list])

    js = f"""/* ferogram API search - auto-generated */
root = document.getElementById("main_div");
root.innerHTML = `
<input id="searchBox" type="text" onkeyup="updateSearch(event)"
       placeholder="Search methods and types\u2026  (press / to focus)" />
<div id="searchDiv" style="display:none">
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
var methodsList = document.getElementById("methodsList");
var methodsCount = document.getElementById("methodsCount");
var typesList = document.getElementById("typesList");
var typesCount = document.getElementById("typesCount");
var constructorsList = document.getElementById("constructorsList");
var constructorsCount = document.getElementById("constructorsCount");
var exactMatch = document.getElementById("exactMatch");
var exactList  = document.getElementById("exactList");

var requests     = {requests};
var types        = {type_names};
var constructors = {constructors};
var requestsu    = {requestsu};
var typesu       = {typesu};
var constructorsu = {constructorsu};

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

    var exact = [], mList = [], tList = [], cList = [];
    for (var i = 0; i < requests.length; i++) {{
        var n = requests[i], lower = n.toLowerCase();
        if (lower === q) exact.push(makeLink(n, requestsu[i]));
        else if (lower.includes(q)) mList.push(makeLink(n, requestsu[i]));
    }}
    for (var i = 0; i < types.length; i++) {{
        var n = types[i], lower = n.toLowerCase();
        if (lower === q) exact.push(makeLink(n, typesu[i]));
        else if (lower.includes(q)) tList.push(makeLink(n, typesu[i]));
    }}
    for (var i = 0; i < constructors.length; i++) {{
        var n = constructors[i], lower = n.toLowerCase();
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

document.addEventListener('keydown', function(e) {{
  if (e.key === '/' && document.activeElement !== searchBox) {{
    e.preventDefault(); searchBox.focus();
  }}
  if (e.key === 'Escape' && document.activeElement === searchBox) {{
    searchBox.blur(); searchBox.value = ''; updateSearch({{}});
  }}
}});
"""
    (out / "js").mkdir(parents=True, exist_ok=True)
    (out / "js" / "search.js").write_text(js, encoding="utf-8")



def gen_root_index(layer: int, n_types: int, n_constructors: int, n_methods: int, out: Path) -> None:
    body = f"""\
<h1>ferogram API <span style="color:var(--muted);font-size:1rem">Layer {layer}</span></h1>
<p style="color:var(--muted)">
  Raw Telegram MTProto API reference, generated from the TL schema at Layer {layer}.
  Use the search box above or browse by section.
</p>
<div class="links-row">
  <a class="pill" href="methods/index.html">Methods ({n_methods})</a>
  <a class="pill" href="types/index.html">Types ({n_types})</a>
  <a class="pill" href="constructors/index.html">Constructors ({n_constructors})</a>
</div>

<h3>What is ferogram?</h3>
<p>
  <strong>ferogram</strong> is a modern Telegram MTProto library written in Rust, designed for speed,
  reliability, and handling complex tasks with ease, while providing full access to Telegram's protocol.
</p>
<p>
  <strong>ferogram-py</strong>, a Python wrapper for ferogram, lets you build Telegram bots and userbots
  using a clean and easy high-level API, while still giving you direct access to raw TL functions for
  advanced features and complete MTProto control whenever needed.
</p>
<div class="links-row">
  <a class="pill" href="https://github.com/ankit-chaubey/ferogram" target="_blank">ferogram (Rust)</a>
  <a class="pill" href="https://github.com/ankit-chaubey/ferogram-py" target="_blank">ferogram-py (Python)</a>
</div>

<h3>5 ways to call a raw method</h3>
<div class="tabs">
  <button class="tab active" onclick="switchWayTab(0)">1. Callable</button>
  <button class="tab" onclick="switchWayTab(1)">2. invoke()</button>
  <button class="tab" onclick="switchWayTab(2)">3. ns import</button>
  <button class="tab" onclick="switchWayTab(3)">4. raw proxy</button>
  <button class="tab" onclick="switchWayTab(4)">5. handler</button>
</div>
<div class="way-content active" id="w0"><pre class="python"># Recommended: call the client directly
from ferogram import Client, raw
app = Client("my_session", api_id=12345, api_hash="...")
result = await app(raw.functions.messages.GetHistory(peer=..., limit=100))</pre></div>
<div class="way-content" id="w1"><pre class="python"># Explicit invoke() - same result
from ferogram import Client, raw
app = Client("my_session", api_id=12345, api_hash="...")
result = await app.invoke(raw.functions.messages.GetHistory(peer=..., limit=100))</pre></div>
<div class="way-content" id="w2"><pre class="python"># Namespace import - shorter call site
from ferogram import Client
from ferogram.raw.functions.messages import GetHistory
app = Client("my_session", api_id=12345, api_hash="...")
result = await app(GetHistory(peer=..., limit=100))</pre></div>
<div class="way-content" id="w3"><pre class="python"># Raw proxy: resolves peer strings automatically
from ferogram import Client
app = Client("my_session", api_id=12345, api_hash="...")
result = await app.raw.messages.GetHistory(peer="@username", limit=5)</pre></div>
<div class="way-content" id="w4"><pre class="python"># Inside an update handler
from ferogram import Client, filters, raw
app = Client("my_session", api_id=12345, api_hash="...")

@app.on(filters.text)
async def handler(client, message):
    result = await client(raw.functions.messages.GetHistory(
        peer=message.chat_id, limit=10
    ))
    print(result)</pre></div>

<h3 id="int">Core types</h3>
<table>
<tr><td><b>int</b></td><td>32-bit signed integer.</td></tr>
<tr><td><b id="long">long</b></td><td>64-bit signed integer.</td></tr>
<tr><td><b id="bool">bool</b> / <b id="true">true</b></td><td>Boolean value.</td></tr>
<tr><td><b id="string">string</b></td><td>UTF-8 string.</td></tr>
<tr><td><b id="bytes">bytes</b></td><td>Arbitrary binary data.</td></tr>
<tr><td><b id="double">double</b></td><td>64-bit float.</td></tr>
<tr><td><b id="date">date</b></td><td>Unix timestamp stored as int.</td></tr>
<tr><td><b id="vector">Vector&lt;T&gt;</b></td><td>List of T.</td></tr>
</table>
"""
    (out / "index.html").write_text(page("ferogram API", "", body), encoding="utf-8")


def gen_404(out: Path) -> None:
    body = '<h1>404</h1><p>Page not found. <a href="index.html">Go home</a>.</p>'
    (out / "404.html").write_text(page("404", "", body, show_search=False), encoding="utf-8")



def main() -> None:
    tl_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ferogram/raw_api.tl")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/site")

    if not tl_path.exists():
        print(f"ERROR: TL file not found: {tl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {tl_path} ...")
    types_list, funcs_list = parse_tl(tl_path)
    layer = parse_layer(tl_path)
    print(f"  Layer {layer}: {len(types_list)} constructors, {len(funcs_list)} functions")

    abstract_types_map: dict[str, list[TLItem]] = defaultdict(list)
    for t in types_list:
        abstract_types_map[t.ret].append(t)
    abstract_types_sorted = sorted(abstract_types_map.keys())
    known_types: set[str] = set(abstract_types_map.keys())

    type_to_funcs_ret: dict[str, list[TLItem]] = defaultdict(list)
    for f in funcs_list:
        type_to_funcs_ret[f.ret].append(f)

    type_to_funcs_acc: dict[str, list[TLItem]] = defaultdict(list)
    for f in funcs_list:
        seen = set()
        for field in f.fields:
            if field.ftype in known_types and field.ftype not in seen:
                type_to_funcs_acc[field.ftype].append(f)
                seen.add(field.ftype)

    type_to_types_member: dict[str, list[TLItem]] = defaultdict(list)
    for t in types_list:
        seen = set()
        for field in t.fields:
            if field.ftype in known_types and field.ftype not in seen:
                type_to_types_member[field.ftype].append(t)
                seen.add(field.ftype)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    css_dir = out_dir / "css"
    css_dir.mkdir()
    (css_dir / "dark.css").write_text(CSS_DARK, encoding="utf-8")
    (css_dir / "light.css").write_text(CSS_LIGHT, encoding="utf-8")
    (css_dir / "amoled.css").write_text(CSS_AMOLED, encoding="utf-8")

    gen_search_js(types_list, funcs_list, abstract_types_sorted, out_dir)

    cons_ns_map: dict[str, list[TLItem]] = defaultdict(list)
    for t in types_list:
        gen_constructor_page(t, known_types, type_to_funcs_acc.get(t.ret, []), out_dir)
        cons_ns_map[tl_ns(t.tl_name)].append(t)
    for ns, items in cons_ns_map.items():
        if ns != "_base":
            gen_ns_index("constructors", ns, items, out_dir)
    gen_section_index("constructors", cons_ns_map, out_dir)
    print(f"  {len(types_list)} constructor pages")

    for abstract, constructors in abstract_types_map.items():
        gen_abstract_type_page(
            abstract, constructors,
            type_to_funcs_ret.get(abstract, []),
            type_to_funcs_acc.get(abstract, []),
            type_to_types_member.get(abstract, []),
            out_dir,
        )
    types_ns_map: dict[str, list] = defaultdict(list)
    for abstract in abstract_types_sorted:
        types_ns_map[tl_ns(abstract)].append((abstract, abstract_types_map[abstract]))
    for ns, items in types_ns_map.items():
        if ns != "_base":
            gen_ns_index("types", ns, items, out_dir)
    gen_section_index("types", types_ns_map, out_dir)
    print(f"  {len(abstract_types_map)} type pages")

    method_ns_map: dict[str, list[TLItem]] = defaultdict(list)
    for f in funcs_list:
        gen_method_page(f, known_types, out_dir)
        method_ns_map[tl_ns(f.tl_name)].append(f)
    for ns, items in method_ns_map.items():
        if ns != "_base":
            gen_ns_index("methods", ns, items, out_dir)
    gen_section_index("methods", method_ns_map, out_dir)
    print(f"  {len(funcs_list)} method pages")

    gen_root_index(layer, len(abstract_types_map), len(types_list), len(funcs_list), out_dir)
    gen_404(out_dir)

    print(f"\nDone -> {out_dir}/")


if __name__ == "__main__":
    main()
