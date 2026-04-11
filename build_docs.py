#!/usr/bin/env python3
"""
Build a single HTML docs viewer from all top-level Markdown files.

Usage:
    python build_docs.py

Output:
    docs.html
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs.html"

PREFERRED_ORDER = [
    "README.md",
    "DATA_TABLE_GUIDE.md",
    "TECHNICAL_DOCUMENTATION.md",
]


def discover_markdowns() -> list[Path]:
    by_name = {p.name: p for p in ROOT.glob("*.md")}
    ordered = [by_name[name] for name in PREFERRED_ORDER if name in by_name]
    remaining = sorted([p for p in by_name.values() if p.name not in PREFERRED_ORDER], key=lambda p: p.name.lower())
    return ordered + remaining


def title_for(path: Path) -> str:
    if path.name == "README.md":
        return "Overview"
    if path.name == "DATA_TABLE_GUIDE.md":
        return "Data Table Guide"
    if path.name == "TECHNICAL_DOCUMENTATION.md":
        return "Technical Documentation"
    return path.stem.replace("_", " ").replace("-", " ").title()


def build_html(docs: list[dict[str, str]]) -> str:
    docs_json = json.dumps(docs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PriceRadar Docs</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
*{{box-sizing:border-box}}
:root{{
  --bg:#f5f2eb;--surface:#fffdf8;--panel:#f1ece2;--border:#ddd4c4;--text:#1f1a14;
  --muted:#6f665b;--accent:#185fa5;--accent-soft:#e7f1fb;--code:#f7f4ee;
  --shadow:0 16px 40px rgba(38,28,18,.08);
}}
body{{margin:0;background:linear-gradient(180deg,#f7f2ea 0%,#f3efe7 100%);color:var(--text);font:14px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}}
.layout{{display:grid;grid-template-columns:280px minmax(0,1fr);min-height:100vh}}
.sidebar{{border-right:1px solid var(--border);background:rgba(255,253,248,.82);backdrop-filter:blur(10px);padding:24px 18px;position:sticky;top:0;height:100vh;overflow:auto}}
.brand{{font-size:18px;font-weight:800;letter-spacing:-.03em;margin-bottom:6px}}
.sub{{color:var(--muted);font-size:12px;margin-bottom:20px}}
.nav{{display:flex;flex-direction:column;gap:8px}}
.nav button{{all:unset;display:block;padding:12px 14px;border:1px solid transparent;border-radius:12px;cursor:pointer;color:var(--muted);background:transparent;font-weight:600}}
.nav button:hover{{border-color:var(--border);background:var(--surface)}}
.nav button.active{{background:var(--accent-soft);border-color:#c9ddf2;color:var(--accent)}}
.main{{padding:28px}}
.toolbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap}}
.toolbar h1{{margin:0;font-size:24px;letter-spacing:-.03em}}
.toolbar .meta{{color:var(--muted);font-size:12px}}
.article{{background:var(--surface);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow);padding:32px;max-width:1000px}}
.article h1,.article h2,.article h3{{letter-spacing:-.03em;line-height:1.2}}
.article h1{{font-size:32px;margin:0 0 18px}}
.article h2{{font-size:24px;margin:34px 0 14px;padding-top:6px;border-top:1px solid #eee4d6}}
.article h3{{font-size:18px;margin:24px 0 10px}}
.article p,.article ul,.article ol{{margin:0 0 14px}}
.article ul,.article ol{{padding-left:22px}}
.article li{{margin:4px 0}}
.article a{{color:var(--accent);text-decoration:none}}
.article a:hover{{text-decoration:underline}}
.article code{{background:var(--code);padding:2px 6px;border-radius:6px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.95em}}
.article pre{{background:#161a20;color:#edf3fb;padding:16px 18px;border-radius:14px;overflow:auto;margin:14px 0}}
.article pre code{{background:transparent;padding:0;color:inherit}}
.article table{{width:100%;border-collapse:collapse;margin:16px 0;display:block;overflow:auto}}
.article th,.article td{{border:1px solid var(--border);padding:9px 10px;text-align:left;vertical-align:top;white-space:nowrap}}
.article th{{background:var(--panel);font-size:12px}}
.article blockquote{{margin:14px 0;padding:8px 14px;border-left:4px solid #d8cbb5;background:#faf6ef;color:#5d5448}}
.article hr{{border:none;border-top:1px solid var(--border);margin:24px 0}}
@media (max-width:900px){{
  .layout{{grid-template-columns:1fr}}
  .sidebar{{position:static;height:auto}}
  .main{{padding:16px}}
  .article{{padding:20px}}
}}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">PriceRadar Docs</div>
    <div class="sub">Readable HTML view for the repo markdown files.</div>
    <nav class="nav" id="nav"></nav>
  </aside>
  <main class="main">
    <div class="toolbar">
      <div>
        <h1 id="doc-title">Docs</h1>
        <div class="meta" id="doc-meta"></div>
      </div>
    </div>
    <article class="article markdown-body" id="content"></article>
  </main>
</div>
<script>
const DOCS = {docs_json};
marked.setOptions({{
  gfm: true,
  breaks: false,
  headerIds: true,
  mangle: false
}});

const nav = document.getElementById('nav');
const title = document.getElementById('doc-title');
const meta = document.getElementById('doc-meta');
const content = document.getElementById('content');

function renderDoc(index) {{
  const doc = DOCS[index];
  if (!doc) return;
  title.textContent = doc.title;
  meta.textContent = doc.file;
  content.innerHTML = marked.parse(doc.markdown);
  [...nav.querySelectorAll('button')].forEach((btn, i) => btn.classList.toggle('active', i === index));
  location.hash = doc.file.replace(/\\.md$/i, '').toLowerCase();
}}

DOCS.forEach((doc, i) => {{
  const btn = document.createElement('button');
  btn.textContent = doc.title;
  btn.addEventListener('click', () => renderDoc(i));
  nav.appendChild(btn);
}});

const initial = Math.max(0, DOCS.findIndex(d => '#' + d.file.replace(/\\.md$/i, '').toLowerCase() === location.hash));
renderDoc(initial);
</script>
</body>
</html>
"""


def main() -> None:
    docs = []
    for path in discover_markdowns():
        docs.append(
            {
                "title": title_for(path),
                "file": path.name,
                "markdown": path.read_text(encoding="utf-8"),
            }
        )
    OUT.write_text(build_html(docs), encoding="utf-8")
    print(f"Built {OUT.name} from {len(docs)} markdown files.")


if __name__ == "__main__":
    main()
