---
name: md-preview
description: Open a local Markdown file in a browser with pandoc and a lightweight Python server, then keep the page refreshed as the file changes. Use this skill whenever the user wants to see a rendered Markdown file, asks for a preview, mentions live reload while editing docs, or wants to inspect headings/code blocks/images in a browser. Trigger phrases include "markdown preview", "md preview", "마크다운 미리보기", "브라우저에서 markdown 열어줘", "md 파일 열어줘", or anything implying "show me this file rendered". Always prefer this skill over manually constructing an HTML server when the user is working with .md files.
allowed-tools: Bash(uv:*)
argument-hint: "<file.md>"
---

# Md Preview

## Overview

Open a single local Markdown file in a browser as rendered HTML. Keep the preview updated by polling the source file, rebuilding the HTML with `pandoc`, and reloading the page when the version changes.

## File Resolution

Resolve the target Markdown file first. Prefer an absolute path when the file is outside the current working directory.

**When no file argument is provided:** Look back through the current conversation for the most recently created, edited, or mentioned `.md` file and use that. Do NOT search the filesystem — use only session context. If no markdown file can be found in the conversation, ask the user which file to preview.

Run live preview:

```bash
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py start <file.md>
```

Build only (no server):

```bash
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py build <file.md>
```

Restart the running preview (file is optional — omit to reuse the current one):

```bash
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py restart [file.md]
```

Inspect status or stop the running preview:

```bash
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py status
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py stop
```

## Workflow

Prefer `start` when the user wants a browser preview that updates during editing.

Prefer `build` when the user only wants the rendered HTML file and does not need a running server.

Keep the generated preview HTML in the same directory as the source Markdown file so relative images and local asset links continue to resolve.

Use `--no-open` when validating or automating the skill without launching a browser window.

Use `--base-url "http://127.0.0.1:{port}"` when the local `*.kit.test` proxy is unavailable and the browser should open a plain localhost URL instead.

Auto-close is on by default: the server shuts itself down automatically after the browser tab is closed. The browser sends an unload beacon on tab close; the server then waits up to 10 seconds for polling to resume before shutting down. Without a beacon, a 30-second idle fallback applies. Pass `--no-auto-close` to keep the server running indefinitely regardless of browser state.

## Command Notes

Run `start <file.md>` to build the preview, launch the local server, watch the Markdown file for changes, and open the browser. If the default port (8000) is already in use, the server automatically picks the next free port. The server shuts down automatically when the browser tab is closed (pass `--no-auto-close` to disable this).

Run `build <file.md>` to generate `.<name>.preview.html` next to the source Markdown file without starting a server.

Run `restart [file.md]` to stop the running preview and immediately start a fresh one. Omit the file argument to reuse whichever file the current server is already watching.

Run `status` to report whether a managed preview server is running, which file it serves, and which URL it uses.

Run `stop` to terminate the managed preview server and remove the saved state file.

## Platform Notes

### Windows

`pandoc` 설치:
```powershell
winget install JohnMacFarlane.Pandoc
# 또는: choco install pandoc / scoop install pandoc
```

브라우저 열기는 Python `os.startfile()` 을 사용하므로 별도 명령 불필요.

경로에 공백이 있으면 따옴표로 감싸거나 백슬래시(`\`)를 포워드슬래시(`/`)로 대체:
```bash
uv run python ~/.claude/skills/md-preview/scripts/md_preview.py start "C:/Users/me/docs/readme.md"
```

`--no-auto-close` 없이 사용하면 탭 닫기 감지 후 자동 종료 — Windows에서도 동일하게 동작한다.

## Known Limitations

- Relative images resolve correctly because the preview file is written next to the source file.
- `.md` hyperlinks are not rewritten to preview URLs — they remain as-is.
- Neovim cursor sync, scroll sync, Mermaid, KaTeX, and PlantUML are not supported.
- `pandoc` must be installed before using the skill (`brew install pandoc` on macOS, `winget install JohnMacFarlane.Pandoc` on Windows). If it is missing, stop and report the dependency gap rather than guessing.

## Resources

Use [md_preview.py](./scripts/md_preview.py) as the main entrypoint for build, restart, stop, and status operations. (`serve` is an internal subcommand spawned by `start` — invoke `start` instead.)

Use [preview.css](./assets/preview.css) for the injected reading layout and rendered element styling.

Use [preview_reload.js](./assets/preview_reload.js) for the browser-side polling and automatic reload behavior.

Use [agents/openai.yaml](./agents/openai.yaml) for the OpenAI-compatible agent interface metadata (display name, short description, default prompt). This file is consumed by external agent integrations and does not affect the core skill workflow.
