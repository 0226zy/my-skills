#!/usr/bin/env python3
"""Render a learning-path Markdown file into a print-quality A4 PDF.

Pipeline: Markdown -> styled HTML (print CSS) -> headless Chrome -> PDF.
No third-party Python packages required.

Usage:
    python3 render.py plan.md [plan.pdf]
    python3 render.py plan.md --keep-html

The Markdown subset is deliberately small: headings, paragraphs, bullet and
ordered lists, pipe tables, blockquotes (rendered as callouts), fenced code,
bold / italic / inline code / links, and `<!-- pagebreak -->`.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
    shutil.which("microsoft-edge") or "",
]

CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")


# ---------------------------------------------------------------- frontmatter


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


# -------------------------------------------------------------------- inline


def inline(s: str) -> str:
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    for index, code in enumerate(codes):
        s = s.replace(f"\x00{index}\x00", f"<code>{html.escape(code)}</code>")
    return s


def smart_join(parts: list[str]) -> str:
    out = parts[0]
    for part in parts[1:]:
        glue = "" if (CJK.search(out[-1]) and CJK.search(part[0])) else " "
        out += glue + part
    return out


# -------------------------------------------------------------------- blocks


def render_table(rows: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = cells(rows[0])
    rest = rows[1:]
    if rest and re.fullmatch(r"[\s|:\-]+", rest[0]):
        rest = rest[1:]
    body = [cells(r) for r in rest if r.strip()]

    parts = ['<table><thead><tr>']
    parts += [f"<th>{inline(c)}</th>" for c in header]
    parts.append("</tr></thead><tbody>")
    for row in body:
        row = (row + [""] * len(header))[: len(header)]
        parts.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_list(lines: list[str], start: int) -> tuple[str, int]:
    items: list[tuple[int, bool, str]] = []
    i = start
    n = len(lines)
    while i < n:
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
        if not m:
            break
        items.append((len(m.group(1)), m.group(2)[0].isdigit(), m.group(3)))
        i += 1

    parts: list[str] = []
    current_tag = ""
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        if tag != current_tag:
            if current_tag:
                parts.append(f"</{current_tag}>")
            parts.append(f"<{tag}>")
            current_tag = tag
        cls = ' class="nested"' if indent else ""
        parts.append(f"<li{cls}>{inline(text)}</li>")
    if current_tag:
        parts.append(f"</{current_tag}>")
    return "".join(parts), i


def md_to_html(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = body.splitlines()
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    i, n, counter = 0, len(lines), 0

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if line.strip() in {"<!-- pagebreak -->", "<!--pagebreak-->"}:
            out.append('<div class="pb"></div>')
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1:
                out.append(f'<h1 class="doc">{inline(text)}</h1>')
            else:
                counter += 1
                hid = f"s{counter}"
                if level in (2, 3):
                    toc.append((level, text, hid))
                out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
            i += 1
            continue

        if line.lstrip().startswith("```"):
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        if line.strip().startswith("|"):
            rows: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
            continue

        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i][1:].strip())
                i += 1
            content = "<br>".join(inline(x) for x in buf if x)
            out.append(f'<div class="callout"><p>{content}</p></div>')
            continue

        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            chunk, i = render_list(lines, i)
            out.append(chunk)
            continue

        buf = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|```|\||>|<!--|\s*([-*]|\d+\.)\s+)", lines[i]
        ):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(smart_join(buf))}</p>")

    return "\n".join(out), toc


# ----------------------------------------------------------------- document


CSS = """
@page {
  size: A4;
  margin: 20mm 18mm 18mm 18mm;
  @top-center {
    content: "%(running)s";
    font-family: "PingFang SC", "Hiragino Sans GB", "STHeiti", "Microsoft YaHei", sans-serif;
    font-size: 8pt;
    color: #9aa4b2;
    margin-bottom: 6mm;
  }
  @bottom-left {
    content: "%(footer)s";
    font-family: "PingFang SC", "Hiragino Sans GB", "STHeiti", sans-serif;
    font-size: 7.5pt;
    color: #b0b8c4;
  }
  @bottom-right {
    content: counter(page) " / " counter(pages);
    font-family: "PingFang SC", "Hiragino Sans GB", "STHeiti", sans-serif;
    font-size: 8pt;
    color: #6b7280;
  }
}
@page :first {
  @top-center { content: none; }
  @bottom-left { content: none; }
  @bottom-right { content: none; }
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0;
  font-family: "PingFang SC", "Hiragino Sans GB", "STHeiti", "Microsoft YaHei", sans-serif;
  font-size: 10.5pt;
  line-height: 1.75;
  color: #1a1d21;
  background: #fff;
}
h1, h2, h3, h4 { line-height: 1.35; break-after: avoid-page; }
main > h2 {
  break-before: page;
}
h2 {
  font-size: 16pt;
  margin: 20pt 0 10pt;
  padding-bottom: 4pt;
  border-bottom: 1.2pt solid #1f4e79;
  color: #12304d;
}
h3 { font-size: 12.5pt; margin: 14pt 0 6pt; color: #1f4e79; }
p { margin: 0 0 7pt; text-align: justify; orphans: 3; widows: 3; }
ul, ol { margin: 4pt 0 9pt; padding-left: 18pt; }
li { margin: 2pt 0; }
li.nested { margin-left: 14pt; }
strong { font-weight: 600; color: #0f2540; }
a { color: #1f4e79; text-decoration: none; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 8.8pt;
  background: #f1f3f5;
  padding: 0 2pt;
  border-radius: 2pt;
}
pre {
  background: #f7f8fa;
  border: 0.5pt solid #e3e7ec;
  border-radius: 3pt;
  padding: 8pt 10pt;
  font-size: 8.4pt;
  line-height: 1.55;
  white-space: pre-wrap;
  break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 8.4pt; }
.callout {
  background: #f4f8fb;
  border-left: 3pt solid #1f4e79;
  padding: 8pt 10pt;
  margin: 10pt 0 12pt;
  break-inside: avoid;
}
.callout p { margin: 0; font-size: 10pt; }
table {
  width: 100%%;
  border-collapse: collapse;
  font-size: 9pt;
  line-height: 1.5;
  margin: 8pt 0 12pt;
}
th, td {
  border: 0.5pt solid #cfd8e3;
  padding: 4pt 6pt;
  vertical-align: top;
  text-align: left;
}
th { background: #eaf1f8; font-weight: 600; color: #12304d; }
tr { break-inside: avoid; }
.pb { break-before: page; }
.cover { padding-top: 42mm; }
.cover .kicker {
  font-size: 9pt;
  letter-spacing: 3pt;
  color: #1f4e79;
  text-transform: uppercase;
  margin-bottom: 10mm;
}
.cover h1 {
  font-size: 30pt;
  font-weight: 700;
  color: #0d1b2a;
  margin: 0 0 6mm;
  border: none;
  padding: 0;
}
.cover .sub { font-size: 13pt; color: #4b5563; line-height: 1.6; }
.cover .rule { width: 28mm; height: 2.5pt; background: #1f4e79; margin: 12mm 0; }
.cover .meta { font-size: 10pt; color: #374151; line-height: 2.1; }
.cover .meta b { color: #111827; font-weight: 600; display: inline-block; width: 22mm; }
.toc-title { border: none; margin-top: 0; }
.toc ul { list-style: none; padding: 0; margin: 6pt 0; }
.toc li { margin: 0; padding: 4pt 0; border-bottom: 0.4pt dotted #d5dbe3; }
.toc li a { display: flex; align-items: baseline; gap: 8pt; }
.toc .t { flex: 1; }
.toc .pg { color: #6b7280; font-size: 9.5pt; font-variant-numeric: tabular-nums; }
.toc a { color: #1a1d21; }
.toc li.l3 a { color: #4b5563; }
"""


def build_document(meta: dict[str, str], body_html: str, toc: list[tuple[int, str, str]]) -> str:
    title = meta.get("title", "学习路径")
    subtitle = meta.get("subtitle", "")
    meta_rows = []
    for key, label in (
        ("level", "档位"),
        ("goal", "目标"),
        ("hours", "预计投入"),
        ("date", "生成日期"),
        ("source", "资料来源"),
    ):
        if meta.get(key):
            meta_rows.append(f'<div><b>{label}</b>{html.escape(meta[key])}</div>')

    top = [(text, hid) for level, text, hid in toc if level == 2]
    numbered = len(top) <= 24
    toc_items = []
    for index, (text, hid) in enumerate(top, start=1):
        page = index + 2 if numbered else ""
        toc_items.append(
            f'<li class="l2"><a href="#{hid}"><span class="t">{inline(text)}</span>'
            f'<span class="pg">{page}</span></a></li>'
        )

    running = html.escape(meta.get("running", title))
    footer = html.escape(meta.get("footer", "learning-path-designer"))

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{CSS % {"running": running, "footer": footer}}</style>
</head><body>
<section class="cover">
  <div class="kicker">{html.escape(meta.get("kicker", "学习路径"))}</div>
  <h1>{inline(title)}</h1>
  <div class="sub">{inline(subtitle)}</div>
  <div class="rule"></div>
  <div class="meta">{''.join(meta_rows)}</div>
</section>
<div class="pb"></div>
<section class="toc">
  <h2 class="toc-title">目录</h2>
  <ul>{''.join(toc_items)}</ul>
</section>
<main>{body_html}</main>
</body></html>"""


# ------------------------------------------------------------------- render


def find_chrome() -> str:
    override = os.environ.get("CHROME_PATH")
    if override and Path(override).exists():
        return override
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit(
        "ERROR: no Chrome/Chromium/Edge found. Set CHROME_PATH, or open the .html "
        "file in a browser and print to PDF manually."
    )


def page_count(pdf: Path) -> int:
    try:
        out = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemNumberOfPages", str(pdf)],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if out.isdigit():
            return int(out)
    except Exception:
        pass
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page[^s]", data)) or 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--keep-html", action="store_true", help="keep the intermediate HTML next to the PDF")
    args = parser.parse_args()

    source: Path = args.source.expanduser().resolve()
    if not source.exists():
        sys.exit(f"ERROR: source not found: {source}")

    output = (args.output or source.with_suffix(".pdf")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    meta, body = split_frontmatter(source.read_text(encoding="utf-8"))
    body_html, toc = md_to_html(body)
    document = build_document(meta, body_html, toc)

    html_path = output.with_suffix(".html")
    html_path.write_text(document, encoding="utf-8")

    chrome = find_chrome()
    profile = tempfile.mkdtemp(prefix="lp-pdf-")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=4000",
        f"--user-data-dir={profile}",
        f"--print-to-pdf={output}",
        html_path.as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    shutil.rmtree(profile, ignore_errors=True)

    if not output.exists():
        sys.exit(f"ERROR: Chrome did not produce {output}\n{result.stderr[-800:]}")

    if not args.keep_html:
        html_path.unlink(missing_ok=True)

    size_kb = output.stat().st_size / 1024
    pages = page_count(output)
    if pages < 2:
        print("WARNING: only 1 page produced; check the Markdown structure.", file=sys.stderr)

    print(f"PDF   {output}")
    print(f"pages {pages}")
    print(f"size  {size_kb:.0f} KB")
    print(f"toc   {len(toc)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
