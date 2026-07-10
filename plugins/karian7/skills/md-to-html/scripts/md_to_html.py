#!/usr/bin/env python3
"""Markdown to HTML conversion skill helper script.

Subcommands:
    convert <directory> [--lang=ko] [--css=style.css] [--base-url=URL]
    gen-index <directory> [--title="목차"] [--lang=ko] [--base-url=URL]
"""

import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATE = ASSETS_DIR / "template.html"
NAV_HTML = ASSETS_DIR / "nav.html"
DEFAULT_CSS = ASSETS_DIR / "style.css"
CALLOUT_LUA = ASSETS_DIR / "callout.lua"


def _extract_h1(md_path: Path) -> str:
    """Extract the first # heading from a markdown file."""
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^#\s+(.+)", line.strip())
            if m:
                return m.group(1).strip()
    return md_path.stem


def _extract_description(md_path: Path, max_length: int = 200) -> str:
    """Extract the first paragraph text from a markdown file as description."""
    lines: list[str] = []
    found_heading = False
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not found_heading:
                if re.match(r"^#\s+", stripped):
                    found_heading = True
                continue
            if not stripped and not lines:
                continue
            if not stripped and lines:
                break
            if re.match(r"^#{1,6}\s+", stripped) or re.match(r"^[-*_]{3,}$", stripped):
                break
            lines.append(stripped)
    text = " ".join(lines)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."
    return text


_LOCALE_MAP: dict[str, str] = {
    "ko": "ko_KR",
    "en": "en_US",
    "ja": "ja_JP",
    "zh": "zh_CN",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
}


def _lang_to_locale(lang: str) -> str:
    """Convert a 2-letter lang code to an OG locale string."""
    return _LOCALE_MAP.get(lang, lang)


def _make_nav(md_file: Path) -> str:
    """Create nav HTML with filename substituted."""
    template = NAV_HTML.read_text(encoding="utf-8")
    return template.replace("{{FILENAME}}", md_file.name)


DEFAULT_PANDOC_FROM = "markdown+lists_without_preceding_blankline"
"""Default pandoc input format.

`lists_without_preceding_blankline` lets pandoc recognize a list even when
the previous line is plain text (no blank line in between). Common Korean
writing pattern ("...영향: \\n- ..." with no blank line) was being rendered
as one paragraph with literal dashes before this was enabled.
"""


def _run_pandoc(
    md_file: Path, html_file: Path, *, lang: str, css: str, base_url: str = "", pandoc_from: str = ""
) -> None:
    import tempfile

    title = _extract_h1(md_file)
    description = _extract_description(md_file)
    locale = _lang_to_locale(lang)
    from_arg = pandoc_from or DEFAULT_PANDOC_FROM

    nav_content = _make_nav(md_file)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(nav_content)
        tmp_nav = tmp.name

    try:
        cmd = [
            "pandoc",
            str(md_file),
            "-o", str(html_file),
            "--standalone",
            "--from", from_arg,
            f"--template={TEMPLATE}",
            f"--lua-filter={CALLOUT_LUA}",
            f"--css={css}",
            "-B", tmp_nav,
            f"--metadata=title:{title}",
            f"--metadata=lang:{lang}",
            f"--metadata=og-type:article",
            f"--metadata=og-locale:{locale}",
        ]
        if description:
            cmd.append(f"--metadata=description:{description}")
        if base_url:
            og_url = base_url.rstrip("/") + "/" + quote(html_file.name)
            cmd.append(f"--metadata=og-url:{og_url}")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    finally:
        Path(tmp_nav).unlink(missing_ok=True)


# ── convert ──────────────────────────────────────────────────────────────────


def cmd_convert(
    directory: str, *, lang: str = "ko", css: str = "style.css", base_url: str = "", pandoc_from: str = ""
) -> None:
    target = Path(directory).resolve()
    if not target.is_dir():
        print(f"ERROR: {directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(target.glob("*.md"))
    if not md_files:
        print(f"ERROR: no .md files found in {directory}", file=sys.stderr)
        sys.exit(1)

    css_dest = target / css
    if not css_dest.exists():
        shutil.copy2(DEFAULT_CSS, css_dest)
        print(f"Copied {css} to {target}")

    count = 0
    for md in md_files:
        html_out = md.with_suffix(".html")
        _run_pandoc(md, html_out, lang=lang, css=css, base_url=base_url, pandoc_from=pandoc_from)
        count += 1
        print(f"  {md.name} -> {html_out.name}")

    print(f"\nConverted {count} files in {target}")


# ── gen-index ────────────────────────────────────────────────────────────────


class TitleExtractor(HTMLParser):
    """Extract text from <title> tag."""

    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def _extract_html_title(html_path: Path) -> str:
    """Extract <title> content from an HTML file."""
    parser = TitleExtractor()
    with open(html_path, encoding="utf-8") as f:
        # Read only first 4KB to find <title>
        parser.feed(f.read(4096))
    return parser.title.strip() or html_path.stem


INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes" />
  <meta name="description" content="{title} - {count}개 문서 목차" />
  <title>{title}</title>
  <!-- OpenGraph -->
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{title} - {count}개 문서 목차" />
  <meta property="og:type" content="website" />
  <meta property="og:locale" content="{og_locale}" />
{og_url_meta}  <link rel="stylesheet" href="{css}" />
  <style>
    .toc-list {{ list-style: none; margin-left: 0; padding-left: 0; }}
    .toc-list li {{ margin-bottom: 0.4rem; padding: 0.4rem 0.6rem; border-radius: 6px; transition: background 0.15s; }}
    .toc-list li:hover {{ background: var(--accent-light); }}
    .toc-list a {{ display: block; border-bottom: none; }}
    .file-count {{ color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="file-count">총 {count}개 문서</p>
  <ul class="toc-list">
{items}
  </ul>
</body>
</html>
"""


def cmd_gen_index(
    directory: str,
    *,
    title: str = "목차",
    lang: str = "ko",
    css: str = "style.css",
    base_url: str = "",
) -> None:
    target = Path(directory).resolve()
    if not target.is_dir():
        print(f"ERROR: {directory} is not a directory", file=sys.stderr)
        sys.exit(1)

    html_files = sorted(
        f for f in target.glob("*.html") if f.name != "index.html"
    )

    if not html_files:
        print(f"ERROR: no .html files found in {directory}", file=sys.stderr)
        sys.exit(1)

    items: list[str] = []
    for f in html_files:
        doc_title = _extract_html_title(f)
        href = quote(f.name)
        items.append(f'    <li><a href="{href}">{doc_title}</a></li>')

    og_locale = _lang_to_locale(lang)
    og_url_meta = ""
    if base_url:
        og_url = base_url.rstrip("/") + "/index.html"
        og_url_meta = f'  <meta property="og:url" content="{og_url}" />\n'

    html = INDEX_TEMPLATE.format(
        lang=lang,
        title=title,
        css=css,
        count=len(html_files),
        items="\n".join(items),
        og_locale=og_locale,
        og_url_meta=og_url_meta,
    )

    out = target / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Generated {out} ({len(html_files)} entries)")


# ── main ─────────────────────────────────────────────────────────────────────


def _parse_kwarg(args: list[str], prefix: str, default: str) -> str:
    for a in args:
        if a.startswith(prefix):
            return a[len(prefix):]
    return default


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd == "convert":
        if not rest or rest[0].startswith("--"):
            print("Usage: md_to_html.py convert <directory> [--lang=ko] [--css=style.css] [--base-url=URL]", file=sys.stderr)
            sys.exit(1)
        directory = rest[0]
        lang = _parse_kwarg(rest[1:], "--lang=", "ko")
        css = _parse_kwarg(rest[1:], "--css=", "style.css")
        base_url = _parse_kwarg(rest[1:], "--base-url=", "")
        pandoc_from = _parse_kwarg(rest[1:], "--from=", "")
        cmd_convert(directory, lang=lang, css=css, base_url=base_url, pandoc_from=pandoc_from)

    elif cmd == "gen-index":
        if not rest or rest[0].startswith("--"):
            print('Usage: md_to_html.py gen-index <directory> [--title="목차"] [--lang=ko] [--base-url=URL]', file=sys.stderr)
            sys.exit(1)
        directory = rest[0]
        title = _parse_kwarg(rest[1:], "--title=", "목차")
        lang = _parse_kwarg(rest[1:], "--lang=", "ko")
        css = _parse_kwarg(rest[1:], "--css=", "style.css")
        base_url = _parse_kwarg(rest[1:], "--base-url=", "")
        cmd_gen_index(directory, title=title, lang=lang, css=css, base_url=base_url)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
