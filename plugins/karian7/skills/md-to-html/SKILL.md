---
name: md-to-html
description: >
  Converts markdown files to HTML using pandoc. Auto-generates mobile-responsive CSS, dark mode, and table-of-contents index.html.
  Also supports S3 upload for sharing — converts in /tmp, uploads via s3-upload skill, and cleans up automatically.
  Triggers: "마크다운 HTML 변환", "md to html", "HTML 변환", "pandoc 변환",
  "HTML로 공유", "html 파일로 바꿔서 공유하자", "md 공유", "마크다운 공유", "HTML로 올려줘", "변환해서 공유"
argument-hint: [directory or file]
allowed-tools: Bash(python3:*), Bash(pandoc:*), Bash(ls:*), Bash(cp:*), Bash(mv:*), Bash(rm:*), Bash(mkdir:*), Bash(echo:*)
---

# Markdown to HTML

Converts markdown files to HTML using pandoc.

- **Custom template**: pandoc HTML5 template with title-block deduplication
- **Responsive CSS**: dark mode, mobile-optimized, D2Coding / Pretendard fonts
- **Navigation**: auto-inserts "← 목차" back link on each page
- **Table of contents**: auto-generates index.html (sorted by filename, Korean URL-encoded). If a hand-written `index.md` already exists in the directory, `convert` produces `index.html` from it — `gen-index` is then optional and would overwrite.
- **OpenGraph**: auto-generates og:title, og:description, og:type, og:locale (description extracted from first paragraph)
- **Robust list parsing**: pandoc input format defaults to `markdown+lists_without_preceding_blankline` so lists are recognized even when the previous line is plain text without a blank line in between (common Korean writing pattern: "...영향: \n- 항목"). Override via `--from=...` if needed.
- **Callouts**: Obsidian/GitHub Alerts (`> [!note] 제목` ~ `> [!warning]`) 지원. 16종(note/tip/important/warning/caution/info/success/question/example/quote/abstract/todo/failure/danger/bug/hint) 인식, 유형별 색상·아이콘 적용. Lua 필터는 `assets/callout.lua`.
- **Script**: `${CLAUDE_PLUGIN_ROOT}/skills/md-to-html/scripts/md_to_html.py`

## Prerequisites

- pandoc installed (`brew install pandoc`)
- Python 3.10+

## Workflow

### Step 1: Check .md files in target directory

Verify the directory containing markdown files to convert.

```bash
ls <directory>/*.md
```

If the user doesn't specify a directory, search for .md files in CWD.

### Step 2: Convert markdown to HTML

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/md-to-html/scripts/md_to_html.py convert <directory> [--lang=ko] [--css=style.css] [--base-url=URL]
```

**Behavior:**
1. Collects `*.md` files from the directory
2. Copies the skill's default CSS if `style.css` doesn't exist
3. Extracts the first `# heading` from each .md file for `<title>`
4. Extracts the first paragraph for `<meta name="description">` and `og:description`
5. Converts with pandoc (custom template + navigation + CSS + OpenGraph)

**Options:**
- `--lang=ko` : HTML lang attribute (default: ko)
- `--css=style.css` : CSS filename (default: style.css)
- `--base-url=URL` : Base URL for og:url (optional, e.g., https://example.com/docs)
- `--from=FORMAT` : Pandoc input format. Default: `markdown+lists_without_preceding_blankline`. Override to e.g. `gfm` or `commonmark_x` for stricter behavior.

### Step 3: Generate table-of-contents index.html

If the source directory has its own hand-written `index.md`, prefer that as the entry point and **skip this step** — `convert` already produced `index.html`. Run `gen-index` only when you want an automatic file-listing index (and you don't have a hand-written one, or you're OK overwriting).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/md-to-html/scripts/md_to_html.py gen-index <directory> [--title="목차"] [--lang=ko] [--base-url=URL]
```

**Behavior:**
1. Scans `*.html` files in the directory (excluding index.html)
2. Extracts titles from each file's `<title>` tag
3. Generates a table-of-contents HTML sorted by filename
4. Korean filenames are encoded with `urllib.parse.quote()`

**Options:**
- `--title="목차"` : `<h1>` title for index.html (default: 목차)
- `--lang=ko` : HTML lang attribute (default: ko)
- `--css=style.css` : CSS filename (default: style.css)
- `--base-url=URL` : Base URL for og:url (optional, e.g., https://example.com/docs)

### Step 4: Completion report

Report the number of converted files and index.html generation result.

---

## Share Mode (S3 Upload)

When the user wants to **share** the converted HTML (triggers: "공유", "올려줘", "공유하자"), convert in `/tmp` to avoid polluting the source directory, upload to S3 via the s3-upload skill, then clean up.

### When to activate

Activate share mode when the user's intent includes sharing/uploading, not just local conversion. Examples:
- "html 파일로 바꿔서 공유하자" → share mode
- "HTML로 공유" → share mode
- "md to html" → local mode (no upload)

### Share workflow

The input can be a **single .md file** or a **directory of .md files**.

**Step 1: Create temp workspace**

```bash
mkdir -p /tmp/md-to-html-share-<timestamp>
```

If the input is a single file, copy it into the temp directory.
If the input is a directory, copy all .md files into the temp directory.

**Step 2: Convert in /tmp**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/md-to-html/scripts/md_to_html.py convert /tmp/md-to-html-share-<timestamp> --lang=ko
```

For a single file, rename the output HTML to `index.html`.
For multiple files, also generate index.html with gen-index.

**Step 3: Upload via s3-upload skill**

Follow the s3-upload skill workflow:
1. Determine subdirectory name (from `.s3-upload` file in source directory, or derive from filename/directory name)
2. Check existing S3 path
3. Upload the temp directory contents
4. Write metadata (title from the document's `# heading`, description from first paragraph)
5. CloudFront invalidation
6. Copy URL to clipboard
7. KakaoTalk notification

**Step 4: Clean up**

```bash
rm -rf /tmp/md-to-html-share-<timestamp>
```

**Step 5: Report**

Show the S3 URL to the user. Confirm temp files were cleaned up.

---

## Error Handling

| Situation | Action |
|-----------|--------|
| pandoc not installed | Guide: `brew install pandoc` |
| No .md files | Request correct directory |
| pandoc conversion error | Print error message, skip that file |
| Not a directory | Request correct path |
| S3 upload fails | Show error, keep temp files for retry |
