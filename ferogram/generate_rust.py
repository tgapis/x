#!/usr/bin/env python3
"""
generate_tl_rust.py
Reads a Telegram TL schema and produces a themed static HTML reference site
with Rust code examples for the ferogram Rust library.

Usage:
    python generate_tl_rust.py raw_api.tl /tmp/rust-tl-docs/

Grab the schema first:
    curl -fsSL https://raw.githubusercontent.com/tgapis/x/data/tdesktop.tl -o raw_api.tl

Then open /tmp/rust-tl-docs/index.html in your browser.
"""

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
_VECTOR_RE = re.compile(r"[Vv]ector<(.+)>")


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


def rust_struct_name(tl_name: str) -> str:
    """PascalCase struct name matching ferogram-tl-gen's to_pascal()."""
    name = tl_base(tl_name)
    out = []
    next_upper = True
    prev_upper = False
    for ch in name:
        if ch == "_":
            next_upper = True
            prev_upper = False
            continue
        if next_upper:
            out.append(ch.upper())
            next_upper = False
            prev_upper = ch.isupper()
        elif ch.isupper():
            if prev_upper:
                out.append(ch.lower())
            else:
                out.append(ch)
            prev_upper = True
        else:
            out.append(ch)
            prev_upper = False
    return "".join(out)


# Keep py_class as alias; used by URL/search helpers that haven't changed
py_class = rust_struct_name


def rust_field_name(name: str) -> str:
    """Rust field name; handles reserved keywords matching param_attr_name()."""
    reserved = {
        "final": "r#final",
        "loop": "r#loop",
        "self": "is_self",
        "static": "r#static",
        "type": "r#type",
    }
    return reserved.get(name.lower(), name.lower())


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


def use_type(item: TLItem) -> str:
    """Rust use statement for a constructor type."""
    ns = tl_ns(item.tl_name)
    cls = rust_struct_name(item.tl_name)
    if ns != "_base":
        return f"use ferogram::tl::types::{ns}::{cls};"
    return f"use ferogram::tl::types::{cls};"


def use_func(item: TLItem) -> str:
    """Rust use statement for a function type."""
    ns = tl_ns(item.tl_name)
    cls = rust_struct_name(item.tl_name)
    if ns != "_base":
        return f"use ferogram::tl::functions::{ns}::{cls};"
    return f"use ferogram::tl::functions::{cls};"


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


# Rust value generation

RUST_PRIMITIVES = {
    "int":    "0_i32",
    "long":   "0_i64",
    "double": "0.0_f64",
    "string": '"".to_string()',
    "bytes":  "vec![]",
    "Bool":   "false",
    "bool":   "false",
    "true":   "false",   # flags.N?true → bool in Rust
    "int128": "[0u8; 16]",
    "int256": "[0u8; 32]",
    "date":   "0_i32",
}

RUST_NAMED: dict[tuple[str, str], str] = {
    ("message",     "string"): '"Hello there!".to_string()',
    ("title",       "string"): '"My title".to_string()',
    ("first_name",  "string"): '"First".to_string()',
    ("last_name",   "string"): '"Last".to_string()',
    ("phone",       "string"): '"+1234567890".to_string()',
    ("username",    "string"): '"username".to_string()',
    ("about",       "string"): '"".to_string()',
    ("slug",        "string"): '"".to_string()',
    ("hash",        "int"):    "0_i32",
    ("hash",        "long"):   "0_i64",
    ("limit",       "int"):    "100_i32",
    ("offset",      "int"):    "0_i32",
    ("offset_id",   "int"):    "0_i32",
    ("offset_date", "int"):    "0_i32",
    ("add_offset",  "int"):    "0_i32",
    ("min_id",      "int"):    "0_i32",
    ("max_id",      "int"):    "0_i32",
    ("min_id",      "long"):   "0_i64",
    ("max_id",      "long"):   "0_i64",
    ("random_id",   "long"):   "0_i64",
    ("id",          "long"):   "0_i64",
    ("id",          "int"):    "0_i32",
    ("access_hash", "long"):   "0_i64",
}

# Common abstract TL types → their simplest valid Rust enum variant.
# Unit variants have no parens. Tuple variants wrap the concrete struct.
# Based on ferogram-tl-gen's def_variant_name() rules.
RUST_ENUM_DEFAULTS: dict[str, str] = {
    "InputPeer":               "enums::InputPeer::Empty",
    "InputUser":               "enums::InputUser::Empty",
    "InputChannel":            "enums::InputChannel::Empty",
    "InputMedia":              "enums::InputMedia::Empty",
    "InputPhoto":              "enums::InputPhoto::Empty",
    "InputDocument":           "enums::InputDocument::Empty",
    "InputFile":               "enums::InputFile::Empty",
    "InputGeoPoint":           "enums::InputGeoPoint::Empty",
    "InputEncryptedFile":      "enums::InputEncryptedFile::Empty",
    "InputChatPhoto":          "enums::InputChatPhoto::Empty",
    "InputStickerSet":         "enums::InputStickerSet::Empty",
    "ReplyMarkup":             "enums::ReplyMarkup::Hide",
    "MessagesFilter":          "enums::MessagesFilter::Empty",
    "InputNotifyPeer":         "enums::InputNotifyPeer::NotifyUsers",
    "InputPrivacyKey":         "enums::InputPrivacyKey::StatusTimestamp",
    "InputPrivacyRule":        "enums::InputPrivacyRule::AllowAll",
    "InputCheckPasswordSrp":   "enums::InputCheckPasswordSrp::Empty",
    "EmojiStatus":             "enums::EmojiStatus::Empty",
    "ChannelMessagesFilter":   "enums::ChannelMessagesFilter::Empty",
    "ChannelParticipantsFilter": "enums::ChannelParticipantsFilter::Recent",
    "ChatReactions":           "enums::ChatReactions::None",
    "Reaction":                "enums::Reaction::Empty",
    "SendMessageAction":       "enums::SendMessageAction::TypingAction",
    "ReportReason":            "enums::ReportReason::Spam",
    "TopPeerCategory":         "enums::TopPeerCategory::BotsPm",
    "BotCommandScope":         "enums::BotCommandScope::Default",
    "BotMenuButton":           "enums::BotMenuButton::Default",
    "InputTheme":              "enums::InputTheme::Slug(types::InputThemeSlug { slug: \"\".to_string() })",
    "InputWallPaper":          "enums::InputWallPaper::Slug(types::InputWallPaperSlug { slug: \"\".to_string() })",
    "InputChatlist":           "enums::InputChatlist::DialogFilter(types::InputChatlistDialogFilter { filter_id: 0 })",
    "InputInvoice":            "enums::InputInvoice::Slug(types::InputInvoiceSlug { slug: \"\".to_string() })",
    "EmailVerifyPurpose":      "enums::EmailVerifyPurpose::LoginChange",
}

SYNONYMS: dict[str, str] = {
    "InputUser":       "InputPeer",
    "InputChannel":    "InputPeer",
    "InputDialogPeer": "InputPeer",
    "InputNotifyPeer": "InputPeer",
    "InputMessage":    "int",
}


def rust_value(fname: str, ftype: str, optional: bool) -> str:
    """Return a Rust expression for a field in a code example."""
    # flags.N?true → bool field in Rust (not Option)
    if optional and ftype == "true":
        return "false"
    # All other optional fields → Option<T>
    if optional:
        return "None"

    key = (fname, ftype)
    if key in RUST_NAMED:
        return RUST_NAMED[key]

    ftype2 = SYNONYMS.get(ftype, ftype)

    if ftype in RUST_PRIMITIVES:
        return RUST_PRIMITIVES[ftype]
    if ftype2 in RUST_PRIMITIVES:
        return RUST_PRIMITIVES[ftype2]

    vec_m = _VECTOR_RE.match(ftype)
    if vec_m:
        return "vec![]"

    if ftype in RUST_ENUM_DEFAULTS:
        return RUST_ENUM_DEFAULTS[ftype]
    if ftype2 in RUST_ENUM_DEFAULTS:
        return RUST_ENUM_DEFAULTS[ftype2]

    # Fallback: abstract type as todo!() with type hint
    if ftype and ftype[0].isupper():
        return f"todo!() /* enums::{ftype} */"
    return "todo!()"


def _needs_enums(fields: list[Field]) -> bool:
    for f in fields:
        if f.name == "flags":
            continue
        val = rust_value(f.name, f.ftype, f.optional)
        if "enums::" in val or "todo!()" in val:
            return True
    return False


def _needs_types(fields: list[Field]) -> bool:
    for f in fields:
        if f.name == "flags":
            continue
        if rust_value(f.name, f.ftype, f.optional).startswith("types::"):
            return True
    return False


def build_rust_example(item: TLItem) -> str:
    """Build a complete Rust code example for invoking a TL function."""
    ns = tl_ns(item.tl_name)
    cls = rust_struct_name(item.tl_name)
    fn_path = f"functions::{ns}::{cls}" if ns != "_base" else f"functions::{cls}"

    fields = [f for f in item.fields if f.name != "flags"]

    needs_enums = _needs_enums(fields)
    needs_types = _needs_types(fields)

    use_parts = ["use ferogram::tl::functions;"]
    if needs_enums:
        use_parts.append("use ferogram::tl::enums;")
    if needs_types:
        use_parts.append("use ferogram::tl::types;")
    imports = "\n".join(use_parts)

    if not fields:
        struct_body = f"        &{fn_path} {{}}"
    else:
        lines = [f"        &{fn_path} {{"]
        for f in fields:
            fname = rust_field_name(f.name)
            val = rust_value(f.name, f.ftype, f.optional)
            lines.append(f"            {fname}: {val},")
        lines.append("        }")
        struct_body = "\n".join(lines)

    return f"""{imports}

#[tokio::main]
async fn main() -> anyhow::Result<()> {{
    let (client, _) = ferogram::Client::quick_connect(
        "my.session",
        12345,
        "0123456789abcdef0123456789abcdef",
    )
    .await?;

    let result = client
        .invoke(
{struct_body},
        )
        .await?;

    println!("{{result:?}}");
    Ok(())
}}"""


def build_rust_example_handler(item: TLItem) -> str:
    """Handler-style example: invoke inside a stream_updates loop."""
    ns = tl_ns(item.tl_name)
    cls = rust_struct_name(item.tl_name)
    fn_path = f"functions::{ns}::{cls}" if ns != "_base" else f"functions::{cls}"

    fields = [f for f in item.fields if f.name != "flags"]

    needs_enums = _needs_enums(fields)
    needs_types = _needs_types(fields)

    use_parts = [
        "use ferogram::tl::functions;",
        "use ferogram::update::Update;",
    ]
    if needs_enums:
        use_parts.append("use ferogram::tl::enums;")
    if needs_types:
        use_parts.append("use ferogram::tl::types;")
    imports = "\n".join(use_parts)

    if not fields:
        struct_body = f"            &{fn_path} {{}}"
    else:
        lines = [f"            &{fn_path} {{"]
        for f in fields:
            fname = rust_field_name(f.name)
            val = rust_value(f.name, f.ftype, f.optional)
            lines.append(f"                {fname}: {val},")
        lines.append("            }")
        struct_body = "\n".join(lines)

    return f"""{imports}

#[tokio::main]
async fn main() -> anyhow::Result<()> {{
    let (client, _) = ferogram::Client::quick_connect(
        "my.session",
        12345,
        "0123456789abcdef0123456789abcdef",
    )
    .await?;

    let mut stream = client.stream_updates();
    while let Some(upd) = stream.next().await {{
        if let Update::NewMessage(_msg) = upd {{
            let result = client
                .invoke(
{struct_body},
                )
                .await?;
            println!("{{result:?}}");
        }}
    }}
    Ok(())
}}"""


# CSS

CSS_COMMON = """\
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
    font-family: 'Nunito', system-ui, sans-serif;
    font-size: 16px;
    line-height: 1.7;
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
h1 { font-size: 2rem; font-weight: 700; margin: 12px 0 20px; }
h3 {
    font-size: 0.85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 28px 0 10px;
}
pre {
    font-family: 'JetBrains Mono', 'Source Code Pro', monospace;
    font-size: 14px;
    padding: 14px 16px;
    border-radius: 6px;
    overflow-x: auto;
    border-width: 1px;
    border-style: solid;
    line-height: 1.6;
}
code { font-family: 'JetBrains Mono', 'Source Code Pro', monospace; font-size: 14px; }
table { width: 100%; border-collapse: collapse; margin: 0; }
table td {
    border-top-width: 1px;
    border-top-style: solid;
    padding: 10px 12px;
    vertical-align: top;
    font-size: 15px;
}
table td:first-child { font-weight: 600; font-family: monospace; font-size: 14px; }
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
    font-size: 14px;
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
    font-size: 14px;
    font-family: 'JetBrains Mono', 'Source Code Pro', monospace;
    cursor: pointer;
    transition: background 0.15s;
}
.tag-opt { border-radius: 3px; padding: 1px 5px; font-size: 12px; font-family: monospace; }
.tag-req { border-radius: 3px; padding: 1px 5px; font-size: 12px; font-family: monospace; }
#theme-btn {
    position: fixed; top: 14px; right: 16px;
    padding: 5px 12px; border-radius: 20px;
    border-width: 1px; border-style: solid;
    font-size: 13px; cursor: pointer; z-index: 999;
    font-family: 'Nunito', sans-serif;
    transition: background 0.2s, color 0.2s;
}
#searchBox {
    width: 100%; padding: 12px 16px;
    border-radius: 6px; border-width: 1px; border-style: solid;
    font-size: 16px; font-family: 'Nunito', sans-serif;
    margin-bottom: 18px; outline: none;
}
#searchDiv details { margin-bottom: 16px; }
#searchDiv summary.title {
    font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; font-size: 13px;
    cursor: pointer; user-select: none; padding: 6px 0; list-style: none;
}
#searchDiv summary.title::-webkit-details-marker { display: none; }
ul.together {
    list-style: none; padding: 0; margin: 6px 0 0;
    column-count: 2; column-gap: 16px;
}
ul.together li { padding: 2px 0; font-size: 14px; break-inside: avoid; }
#exactMatch { border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; border-width: 1px; border-style: solid; }
.invisible { position: absolute; left: -9999px; top: -9999px; }
details.example > summary { cursor: pointer; font-size: 14px; user-select: none; margin-bottom: 6px; font-family: 'JetBrains Mono', 'Source Code Pro', monospace; list-style: none; }
details.example > summary::-webkit-details-marker { display: none; }
details.example > summary::marker { display: none; }
details.example { margin-bottom: 12px; }
.example-note { font-size: 14px; color: var(--muted); margin: 6px 0 14px; font-family: 'JetBrains Mono', 'Source Code Pro', monospace; }
.example-note strong { color: var(--accent-light); }
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; margin-bottom: 0; }
.tab { padding: 7px 14px; font-size: 13px; cursor: pointer; font-family: 'JetBrains Mono', 'Source Code Pro', monospace; color: var(--muted); border: none; background: none; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color .15s, border-color .15s; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.way-content { display: none; }
.way-content.active { display: block; }
.way-content pre { border-top: none; border-radius: 0 0 8px 8px; margin-top: 0; }
@media (max-width: 600px) {
    ul.together { column-count: 1; }
    h1 { font-size: 1.5rem; }
    #theme-btn { top: 8px; right: 8px; }
}
.pill {
    padding: 5px 13px; border-radius: 20px;
    border-width: 1px; border-style: solid;
    font-size: 14px; text-decoration: none;
    display: inline-block; transition: background .15s, border-color .15s;
}
.pill:hover { text-decoration: none; }
.links-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 22px; }
pre { position: relative; }
.copy-icon {
    position: absolute; top: 8px; right: 8px;
    opacity: 0; transition: opacity .15s;
    border-radius: 4px; padding: 2px 8px; font-size: 12px;
    cursor: pointer; border-width: 1px; border-style: solid;
    font-family: 'JetBrains Mono', 'Source Code Pro', monospace; line-height: 1.6;
}
pre:hover .copy-icon { opacity: 1; }
details.example > summary .arrow {
    display: inline-block; transition: transform .18s; margin-right: 4px;
}
details.example[open] > summary .arrow { transform: rotate(90deg); }
.hint {
    font-size: 12px; margin-bottom: 18px;
    font-family: 'JetBrains Mono', 'Source Code Pro', monospace;
    padding: 5px 10px; border-radius: 6px; display: inline-block;
}
/* Rust syntax highlight classes */
.rs-kw  { color: var(--hl-kw); }
.rs-str { color: var(--hl-str); }
.rs-cmt { color: var(--hl-cmt); font-style: italic; }
.rs-num { color: var(--hl-num); }
.rs-mac { color: var(--hl-kw); }
.badge {
    display: inline-block; border-radius: 4px; padding: 2px 8px;
    font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
    font-family: 'JetBrains Mono', 'Source Code Pro', monospace; white-space: nowrap;
}
.badge-rec  { background: var(--tag-req-bg);  color: var(--tag-req-text); }
.badge-ok   { background: var(--tag-opt-bg);  color: var(--tag-opt-text); }
.cmp-table { width: 100%; border-collapse: collapse; margin: 0 0 24px; font-size: 14px; }
.cmp-table th {
    text-align: left; padding: 8px 12px;
    border-bottom: 2px solid var(--border);
    font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--muted);
}
.cmp-table td {
    padding: 10px 12px; vertical-align: top;
    border-top: 1px solid var(--border);
}
.cmp-table td:first-child { font-weight: 700; font-family: 'JetBrains Mono', 'Source Code Pro', monospace; color: var(--accent-light); font-size: 13px; white-space: nowrap; }
.cmp-table td code { font-size: 13px; font-family: 'JetBrains Mono', 'Source Code Pro', monospace; }
.cmp-table tr:hover td { background: var(--surface); }
.cmp-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 24px; }
.cmp-table-wrap .cmp-table { margin-bottom: 0; min-width: 640px; }
.tab-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    margin-right: 5px; vertical-align: middle; position: relative; top: -1px;
}
.tab-dot-rec  { background: var(--tag-req-text); }
.tab-dot-ok   { background: var(--tag-opt-text); }
"""

CSS_DARK_VARS = """\
:root {
    --bg: #0f1117; --surface: #181b24; --border: #2b3040;
    --text: #e2e4f0; --muted: #8b8fa8; --accent: #7c6af7;
    --accent-light: #a99ff8; --code-bg: #141720; --code-text: #cfd5e6;
    --link: #7c6af7; --link-hover: #a99ff8;
    --tag-opt-bg: #1b3042; --tag-opt-text: #66bdf0;
    --tag-req-bg: #1a3122; --tag-req-text: #72d572;
    --btn-bg: #251f4a; --btn-border: #7c6af7; --btn-text: #b3a8ff; --btn-hover: #32285e;
    --tl-cid: #d19a66;
    --hl-kw: #c792ea; --hl-str: #8bd49c; --hl-cmt: #66708a; --hl-num: #f0b27a;
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
    --bg: #f7f8fc; --surface: #ffffff; --border: #d8dceb;
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
h3 { color: #35384a; }
.pill { background: var(--surface); border-color: var(--border); color: var(--link); }
.pill:hover { background: var(--btn-bg); border-color: var(--accent); }
.copy-icon { background: var(--surface); border-color: var(--border); color: var(--muted); }
.copy-icon:hover { border-color: var(--accent); color: var(--accent); }
.hint { background: var(--surface); color: var(--muted); }
"""

CSS_AMOLED_VARS = """\
:root {
    --bg: #000000; --surface: #0a0a0a; --border: #1c1c1c;
    --text: #eceffb; --muted: #7f859d; --accent: #a78bfa;
    --accent-light: #c4b5fd; --code-bg: #050505; --code-text: #d7dcef;
    --link: #a78bfa; --link-hover: #c4b5fd;
    --tag-opt-bg: #0d1526; --tag-opt-text: #6cbcff;
    --tag-req-bg: #0d1b12; --tag-req-text: #59d98e;
    --btn-bg: #140f28; --btn-border: #a78bfa; --btn-text: #d0c4ff; --btn-hover: #21163f;
    --tl-cid: #d8a46d;
    --hl-kw: #d4a4fc; --hl-str: #92d9a8; --hl-cmt: #50566f; --hl-num: #f3bc84;
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

FONTS = '<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'

THEME_INIT = """\
<script>
(function(){
  var labels={'dark':'\u2600 Bright','light':'\u25c9 Amoled','amoled':'\u263e Dark'};
  var t=localStorage.getItem('theme')||'dark';
  document.getElementById('style').href=document.getElementById('style').href.replace(/(dark|light|amoled)\.css/,t+'.css');
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
})()">&#9790; Dark</button>"""

CP_HTML = '<textarea id="c" class="invisible"></textarea>'

# Rust syntax highlighter (JS, applied to pre.rust blocks)
APP_JS = r"""function cp(t){var c=document.getElementById("c");c.value=t;c.select();try{document.execCommand("copy")}catch(e){}}
function hlRs(t){
  var K='use|pub|async|fn|await|let|mut|struct|enum|impl|trait|type|const|static|if|else|match|for|in|loop|while|return|true|false|self|Self|super|crate|mod|where|as|move|ref|unsafe|Ok|Err|Some|None|Box|Vec|Option|Result|String|tokio|main|anyhow'.split('|');
  function e(s){return s.replace(/&/g,'&amp;').replace(/\x3c/g,'&lt;').replace(/\x3e/g,'&gt;');}
  var o='',i=0,n=t.length;
  while(i<n){
    var c2=t[i];
    // line comment
    if(c2==='/'&&t[i+1]==='/'){var j=t.indexOf('\n',i);j=j<0?n:j;o+='<span class="rs-cmt">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // block comment
    if(c2==='/'&&t[i+1]==='*'){var j=t.indexOf('*/',i+2);j=j<0?n:j+2;o+='<span class="rs-cmt">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // string
    if(c2==='"'){var j=i+1;while(j<n&&t[j]!=='"'){if(t[j]==='\\')j++;j++;}j++;o+='<span class="rs-str">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    // macro call (word followed by !)
    if(/[a-zA-Z_]/.test(c2)){var j=i;while(j<n&&/[a-zA-Z0-9_]/.test(t[j]))j++;var w=t.slice(i,j);
      if(t[j]==='!'){o+='<span class="rs-mac">'+e(w)+'!</span>';i=j+1;continue;}
      o+=K.indexOf(w)>=0?'<span class="rs-kw">'+w+'</span>':e(w);i=j;continue;}
    // number (including type suffixes like 0_i32)
    if(/[0-9]/.test(c2)&&(i===0||!/[a-zA-Z_]/.test(t[i-1]))){var j=i;while(j<n&&/[0-9a-fA-FxXbBoO._]/.test(t[j]))j++;
      if(/[iuf]/.test(t[j])){while(j<n&&/[a-z0-9]/.test(t[j]))j++;}
      o+='<span class="rs-num">'+e(t.slice(i,j))+'</span>';i=j;continue;}
    o+=e(c2);i++;
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
  function attachLongPress(el){
    var _lpt=null;
    el.addEventListener('touchstart',function(){
      _lpt=setTimeout(function(){cp(el.innerText||el.textContent);toast();},600);
    },{passive:true});
    el.addEventListener('touchend',function(){clearTimeout(_lpt);});
    el.addEventListener('touchmove',function(){clearTimeout(_lpt);});
  }
  function addCopyIcon(pre){
    var code=(pre.textContent||pre.innerText).replace(/\n$/,'');
    var btn=document.createElement('button');
    btn.className='copy-icon';btn.textContent='copy';
    btn.addEventListener('click',function(ev){
      ev.stopPropagation();
      cp(code);
      btn.textContent='\u2713';toast();
      setTimeout(function(){btn.textContent='copy';},1300);
    });
    pre.appendChild(btn);
  }
  function init(){
    document.querySelectorAll('pre.rust').forEach(function(p){p.innerHTML=hlRs(p.textContent);});
    document.querySelectorAll('pre').forEach(function(el){addCopyIcon(el);attachLongPress(el);});
    document.querySelectorAll('.tabs .tab').forEach(function(btn,i){
      btn.addEventListener('touchend',function(e){e.preventDefault();switchWayTab(i);});
    });
  }
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',init);}else{init();}
})();
function switchWayTab(n){
  document.querySelectorAll('.tabs .tab').forEach(function(t,i){t.classList.toggle('active',i===n);});
  document.querySelectorAll('.way-content').forEach(function(c,i){c.classList.toggle('active',i===n);});
}"""


def page(title: str, depth: str, body: str, *, show_search: bool = True) -> str:
    search_script = (
        f'<script>prependPath="{depth}";</script>'
        f'<script src="{depth}js/search.js"></script>'
    ) if show_search else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)} - Ferogram Rust API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link id="style" rel="stylesheet" href="{depth}css/dark.css">
{FONTS}
</head>
<body>
{THEME_BTN}
{THEME_INIT}
<div id="main_div">
{body}
{CP_HTML}
<script src="{depth}js/app.js"></script>
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
    return f'<div class="cmp-table-wrap"><table>{rows}</table></div>'


def item_table(items: list[TLItem], url_fn, depth: str) -> str:
    rows = ""
    for item in sorted(items, key=lambda i: rust_struct_name(i.tl_name)):
        url = url_fn(item, depth)
        rows += f'<tr><td><a href="{url}">{html.escape(rust_struct_name(item.tl_name))}</a></td></tr>\n'
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
    cls = rust_struct_name(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Constructors", f"{depth}constructors/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}constructors/{ns}/index.html"))
    crumbs.append((cls, None))

    use_stmt = html.escape(use_type(item))
    enum_name = html.escape(item.ret)
    ret_url = abstract_type_url(item.ret, depth)
    using = f"<h3>Used by</h3>{item_table(funcs_accepting, method_url, depth)}" if funcs_accepting else ""

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<pre class="tl">{render_tl_def(item, known_types, depth)}</pre>
<button class="copy-btn" onclick="cp('{use_stmt}')">Copy use statement</button>
<h3>Belongs to</h3>
<table><tr><td><a href="{ret_url}">{enum_name}</a></td></tr></table>
<p style="color:var(--muted);font-size:14px;">
In Rust this constructor is a variant of the <code>enums::{enum_name}</code> enum.<br>
Match on it with: <code>if let enums::{enum_name}::{cls}(v) = result {{ ... }}</code>
</p>
<h3>Parameters</h3>
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
        f'<tr><td><a href="{constructor_url(c, depth)}">{html.escape(rust_struct_name(c.tl_name))}</a></td></tr>\n'
        for c in sorted(constructors, key=lambda c: rust_struct_name(c.tl_name))
    )

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(abstract)}</h1>
<p style="color:var(--muted);font-size:14px;">
Rust type: <code>enums::{html.escape(abstract)}</code>
</p>
<h3>Constructors</h3>
<p>This is an abstract type. At runtime it will be one of the following variants:</p>
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
    cls = rust_struct_name(item.tl_name)
    depth = "../../" if ns != "_base" else "../"

    crumbs = [("API", f"{depth}index.html"), ("Methods", f"{depth}methods/index.html")]
    if ns != "_base":
        crumbs.append((ns.title(), f"{depth}methods/{ns}/index.html"))
    crumbs.append((cls, None))

    use_stmt = html.escape(use_func(item))
    ret_linked = link_type(item.ret, known_types, depth)

    ex_invoke  = html.escape(build_rust_example(item))
    ex_handler = html.escape(build_rust_example_handler(item))

    disclaimer = '<p class="example-note">Replace placeholder values with real data before running.</p>'

    examples_html = f"""<h3>Example</h3>
{disclaimer}
<div class="tabs">
  <button class="tab active" onclick="switchWayTab(0)"><span class="tab-dot tab-dot-rec"></span>invoke()</button>
  <button class="tab" onclick="switchWayTab(1)"><span class="tab-dot tab-dot-ok"></span>handler</button>
</div>
<div class="way-content active"><pre class="rust">{ex_invoke}</pre></div>
<div class="way-content"><pre class="rust">{ex_handler}</pre></div>"""

    body = f"""
{breadcrumb(crumbs)}
<h1>{html.escape(cls)}</h1>
<pre class="tl">{render_tl_def(item, known_types, depth)}</pre>
<button class="copy-btn" onclick="cp('{use_stmt}')">Copy use statement</button>
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
            cls = rust_struct_name(item.tl_name)
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
            cls = rust_struct_name(item.tl_name)
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
    requests      = json.dumps([rust_struct_name(f.tl_name) for f in funcs_list])
    requestsu     = json.dumps([method_url(f) for f in funcs_list])
    type_names    = json.dumps(abstract_types)
    typesu        = json.dumps([abstract_type_url(t) for t in abstract_types])
    constructors  = json.dumps([rust_struct_name(t.tl_name) for t in types_list])
    constructorsu = json.dumps([constructor_url(t) for t in types_list])

    js = f"""/* ferogram Rust API search - auto-generated */
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
<h1>Ferogram Rust API <span style="color:var(--muted);font-size:1rem">Layer {layer}</span></h1>
<p>
  Raw Telegram MTProto API reference for Layer {layer},
  with Rust code examples using <strong>ferogram</strong>.
  Use the search box above or browse by section.
</p>
<div class="links-row">
  <a class="pill" href="methods/index.html">Methods ({n_methods})</a>
  <a class="pill" href="types/index.html">Types ({n_types})</a>
  <a class="pill" href="constructors/index.html">Constructors ({n_constructors})</a>
</div>

<h3>What is ferogram?</h3>
<p>
  <strong>ferogram</strong> is an async Rust Telegram MTProto client.
  It talks to Telegram directly over MTProto with no Bot API proxy,
  works for both bots and user accounts, and gives you full access to
  the raw TL API through <code>client.invoke()</code>.
</p>
<div class="links-row">
  <a class="pill" href="https://github.com/ankit-chaubey/ferogram" target="_blank">ferogram on GitHub</a>
  <a class="pill" href="https://crates.io/crates/ferogram" target="_blank">crates.io</a>
</div>

<h3>How to invoke a raw method</h3>
<div class="tabs">
  <button class="tab active" onclick="switchWayTab(0)"><span class="tab-dot tab-dot-rec"></span>invoke()</button>
  <button class="tab" onclick="switchWayTab(1)"><span class="tab-dot tab-dot-ok"></span>handler</button>
</div>
<div class="way-content active" id="w0"><pre class="rust">use ferogram::tl::{{enums, functions}};

#[tokio::main]
async fn main() -> anyhow::Result<()> {{
    let (client, _) = ferogram::Client::quick_connect(
        "my.session", 12345, "0123456789abcdef0123456789abcdef",
    ).await?;

    let result = client.invoke(&functions::messages::GetHistory {{
        peer: enums::InputPeer::Empty,
        offset_id: 0,
        offset_date: 0,
        add_offset: 0,
        limit: 100,
        max_id: 0,
        min_id: 0,
        hash: 0,
    }}).await?;

    println!("{{result:?}}");
    Ok(())
}}</pre></div>
<div class="way-content" id="w1"><pre class="rust">use ferogram::{{Client, update::Update}};
use ferogram::tl::{{enums, functions}};

#[tokio::main]
async fn main() -> anyhow::Result<()> {{
    let (client, _) = ferogram::Client::quick_connect(
        "my.session", 12345, "0123456789abcdef0123456789abcdef",
    ).await?;

    let mut stream = client.stream_updates();
    while let Some(upd) = stream.next().await {{
        if let Update::NewMessage(msg) = upd {{
            // Use client inside the handler loop
            let result = client.invoke(&functions::messages::GetHistory {{
                peer: enums::InputPeer::Empty,
                offset_id: 0, offset_date: 0, add_offset: 0,
                limit: 10, max_id: 0, min_id: 0, hash: 0,
            }}).await?;
            println!("{{result:?}}");
        }}
    }}
    Ok(())
}}</pre></div>

<h3 id="core">Core types</h3>
<p>TL primitives map to Rust types as follows:</p>
<table>
<tr><td><strong id="int">int</strong></td><td><code>i32</code></td><td>32-bit signed integer.</td></tr>
<tr><td><strong id="long">long</strong></td><td><code>i64</code></td><td>64-bit signed integer.</td></tr>
<tr><td><strong id="int128">int128</strong></td><td><code>[u8; 16]</code></td><td>128-bit value as a byte array.</td></tr>
<tr><td><strong id="int256">int256</strong></td><td><code>[u8; 32]</code></td><td>256-bit value as a byte array.</td></tr>
<tr><td><strong id="double">double</strong></td><td><code>f64</code></td><td>64-bit float.</td></tr>
<tr><td><strong id="string">string</strong></td><td><code>String</code></td><td>UTF-8 owned string.</td></tr>
<tr><td><strong id="bytes">bytes</strong></td><td><code>Vec&lt;u8&gt;</code></td><td>Arbitrary binary data.</td></tr>
<tr><td><strong id="bool">Bool</strong> / <strong id="true">true</strong></td><td><code>bool</code></td><td><code>flags.N?true</code> fields are plain <code>bool</code> in Rust. Other optional fields are <code>Option&lt;T&gt;</code>.</td></tr>
<tr><td><strong id="date">date</strong></td><td><code>i32</code></td><td>Unix timestamp.</td></tr>
<tr><td><strong id="vector">Vector&lt;T&gt;</strong></td><td><code>Vec&lt;T&gt;</code></td><td>Rust <code>Vec</code> of the element type.</td></tr>
</table>

<h3>Module layout</h3>
<p>All generated types live under <code>ferogram::tl</code> (re-exported from <code>ferogram-tl-types</code>):</p>
<table>
<tr><td><code>ferogram::tl::functions</code></td><td>RPC function structs implementing <code>RemoteCall</code>. Pass a reference to <code>client.invoke()</code>.</td></tr>
<tr><td><code>ferogram::tl::types</code></td><td>Concrete constructor structs (bare types). Used as enum variant payloads.</td></tr>
<tr><td><code>ferogram::tl::enums</code></td><td>Boxed abstract types as Rust enums. Pattern-match on these to get the inner <code>types::*</code> struct.</td></tr>
</table>
"""
    (out / "index.html").write_text(page("ferogram Rust API", "", body), encoding="utf-8")


def gen_404(out: Path) -> None:
    body = '<h1>404</h1><p>Page not found. <a href="index.html">Go home</a>.</p>'
    (out / "404.html").write_text(page("404", "", body, show_search=False), encoding="utf-8")


def main() -> None:
    tl_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("raw_api.tl")
    out_dir  = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("rust-tl-docs")

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
        seen: set[str] = set()
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
    (out_dir / "js").mkdir(parents=True, exist_ok=True)
    (out_dir / "js" / "app.js").write_text(APP_JS, encoding="utf-8")

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

    print(f"\nDone -> {out_dir}/index.html")


if __name__ == "__main__":
    main()
