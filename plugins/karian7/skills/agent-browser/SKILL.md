---
name: agent-browser
description: Use when the user asks to interact with a website, fill a form, click something, extract data, take a screenshot, log into a site, test a web app, or automate any browser task. Delegates to the agent-browser CLI which uses Chrome via CDP and accessibility-tree snapshots with compact @eN refs.
allowed-tools:
  - Bash(agent-browser:*)
  - Bash(npx agent-browser:*)
  - Bash(pnpm dlx agent-browser:*)
---

# agent-browser

Fast browser automation CLI for AI agents. Chrome/Chromium via CDP, no Playwright or Puppeteer dependency. Accessibility-tree snapshots with compact `@eN` refs let agents interact with pages in ~200-400 tokens instead of parsing raw HTML.

## Install

Prerequisite: Node.js `>=24`.

### macOS / Linux

```bash
pnpm add -g agent-browser        # 우선, 없으면: npm i -g agent-browser
agent-browser install            # Chrome/Chromium 바이너리 다운로드
agent-browser doctor             # 환경, Chrome, daemon 진단
```

Linux에서 시스템 의존성까지 함께 설치하려면:

```bash
agent-browser install --with-deps    # Linux 전용, 실패 시 에러
```

설치 없이 1회성으로 실행하려면 `npx agent-browser <command>` 또는 `pnpm dlx agent-browser <command>`.

`doctor`가 실패를 보고하면 `agent-browser doctor --fix`로 파괴적 복구(Chrome 재설치, 오래된 상태 파일 정리, 암호화 키 생성)까지 수행. 자동화 스크립트에서는 `--json`으로 결과를 파싱.

### Windows (PowerShell / CMD)

```powershell
pnpm add -g agent-browser        # 우선, 없으면: npm i -g agent-browser
agent-browser install
agent-browser doctor
```

`--with-deps`는 Linux 전용이므로 Windows에서는 붙이지 않는다. 그 외 install/doctor 동작은 macOS/Linux와 동일.

## Core loop

```bash
agent-browser open <url>        # 1. Open a page
agent-browser snapshot -i       # 2. See interactive elements
agent-browser click @e3         # 3. Act on refs from the snapshot
agent-browser snapshot -i       # 4. Re-snapshot after any page change
```

Refs (`@e1`, `@e2`, …) go stale the moment the page changes. Always re-snapshot before the next ref interaction.

## Concurrency & session isolation

agent-browser runs a **background daemon** that persists between commands and is shared across processes. Commands with **no `--session`** all attach to one global *default* session — so two agents running in parallel without `--session` share a single browser context: cookies, storage, tabs, and navigation bleed across them. This is the top cause of cross-run contamination.

Rules for any skill that may run concurrently:

1. **Always pass a unique `--session`.** Never rely on the default session for parallel work.
2. **Derive a stable id once, reuse it on every command** in the run:
   ```bash
   SESSION="$(agent-browser session id --scope worktree --prefix my-skill)"
   agent-browser --session "$SESSION" open https://app.example.com
   agent-browser --session "$SESSION" snapshot -i
   ```
   `--scope worktree` keys the id to the Git worktree (falls back to git root, then cwd) — ideal when each parallel run has its own worktree.
3. **Same worktree, multiple parallel agents → still collide.** `session id` returns the *same* id for the same worktree + prefix. When several sub-agents share one checkout, add a per-agent discriminator to `--prefix`:
   ```bash
   SESSION="$(agent-browser session id --scope worktree --prefix "my-skill-$AGENT_ID")"
   ```
4. **For full daemon-level isolation** (separate sockets + restore dirs), also set `--namespace`:
   ```bash
   agent-browser --namespace "$AGENT_ID" --session "$SESSION" open https://app.example.com
   ```
5. **Clean up when done** so a stale session/daemon doesn't leak into the next run:
   ```bash
   agent-browser --session "$SESSION" close
   ```

> `AGENT_BROWSER_SESSION_NAME` does **not** isolate sessions — it is a legacy name for the persisted *state file* only. Use `--session` / `AGENT_BROWSER_SESSION` for isolation, `--namespace` / `AGENT_BROWSER_NAMESPACE` for daemon isolation, and `--restore` for persistence.

Windows (env var 문법이 달라짐):
```powershell
# PowerShell — capture the id, then reuse it
$SESSION = agent-browser session id --scope worktree --prefix "my-skill-$AgentId"
agent-browser --session $SESSION open https://app.example.com

# CMD
for /f %i in ('agent-browser session id --scope worktree --prefix my-skill-1') do set SESSION=%i
agent-browser --session %SESSION% open https://app.example.com
```

## Reading a page

```bash
agent-browser snapshot -i               # interactive elements only (preferred)
agent-browser snapshot -i -u            # include href urls on links
agent-browser snapshot -i -c            # compact (no empty structural nodes)
agent-browser snapshot -s "#main"       # scope to a CSS selector
agent-browser snapshot -i --json        # machine-readable

agent-browser get text @e1              # visible text
agent-browser get attr @e1 href         # any attribute
agent-browser get url                   # current URL
```

## Interacting

```bash
agent-browser fill @e2 "hello"          # clear then type
agent-browser type @e2 " world"         # type without clearing
agent-browser click @e1
agent-browser press Enter
agent-browser check @e3
agent-browser select @e4 "option-value"
agent-browser upload @e5 file.pdf
agent-browser scroll down 500
```

When refs don't work, use semantic locators:

```bash
agent-browser find role button click --name "Submit"
agent-browser find text "Sign In" click
agent-browser find label "Email" fill "user@test.com"
```

## Waiting (agents fail here most)

```bash
agent-browser wait @e1                  # until element appears
agent-browser wait --text "Success"     # until text appears
agent-browser wait --url "**/dashboard" # until URL matches glob
agent-browser wait --load networkidle   # catch-all for SPA navigation
```

Avoid bare `wait 2000` — it makes scripts slow and flaky.

## Common workflows

### Log in
```bash
agent-browser open https://app.example.com/login
agent-browser snapshot -i
agent-browser fill @e3 "user@example.com"
agent-browser fill @e4 "password"
agent-browser click @e5
agent-browser wait --url "**/dashboard"
```

### Save / restore session

macOS / Linux:
```bash
# Explicit portable state file
agent-browser state save ./auth.json
agent-browser --state ./auth.json open https://app.example.com

# Or auto-save/restore keyed to a stable, isolated session (preferred for reusable runs)
SESSION="$(agent-browser session id --scope worktree --prefix my-app)"
agent-browser --session "$SESSION" --restore open https://app.example.com
```

`--restore` persists and reloads state for the given `--session`; state lives under `~/.agent-browser/sessions/`. Do not use `AGENT_BROWSER_SESSION_NAME` for this — it is a legacy state-file name that does not isolate the browser context (see [Concurrency & session isolation](#concurrency--session-isolation)).

Windows (인라인 env var 문법이 달라짐):
```powershell
# PowerShell
$SESSION = agent-browser session id --scope worktree --prefix my-app
agent-browser --session $SESSION --restore open https://app.example.com

# CMD
for /f %i in ('agent-browser session id --scope worktree --prefix my-app') do set SESSION=%i
agent-browser --session %SESSION% --restore open https://app.example.com
```

### Screenshot
```bash
agent-browser screenshot page.png
agent-browser screenshot --full full.png
agent-browser screenshot --annotate map.png   # numbered labels keyed to @eN refs
```

### Extract data (arbitrary JS)

macOS / Linux (heredoc):
```bash
cat <<'EOF' | agent-browser eval --stdin
Array.from(document.querySelectorAll("table tbody tr")).map(r => ({
  name: r.cells[0].innerText,
  price: r.cells[1].innerText,
}))
EOF
```

Windows (heredoc 미지원 — 파일로 작성 후 stdin 리다이렉트):
```powershell
@'
Array.from(document.querySelectorAll("table tbody tr")).map(r => ({
  name: r.cells[0].innerText,
  price: r.cells[1].innerText,
}))
'@ | Set-Content extract.js
Get-Content extract.js | agent-browser eval --stdin
```

### Tabs
```bash
agent-browser tab                       # list tabs
agent-browser tab new https://docs...   # open new tab
agent-browser tab t2                    # switch to tab t2
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Ref not found" | Page changed — re-snapshot |
| Element not in snapshot | Scroll down, then re-snapshot |
| Click does nothing | Overlay blocking — find + dismiss it first |
| Fill doesn't work | `agent-browser focus @e1` then `keyboard inserttext "text"` |
| Chrome/daemon 관련 오류 | `agent-browser doctor --fix` |

## Platform Notes

### Windows

- Bash 스타일 인라인 env var (`VAR=value cmd`)는 동작하지 않는다 — PowerShell은 `$env:VAR = "value"`, CMD는 `set VAR=value && cmd` 사용.
- Bash 스타일 heredoc(`<<'EOF'`)은 지원되지 않는다 — PowerShell here-string(`@'...'@`)으로 파일을 만들거나 `Get-Content`로 stdin에 넘긴다.
- 경로에 공백이 있으면 따옴표로 감싸거나 백슬래시(`\`)를 포워드슬래시(`/`)로 대체.
- 그 외 명령어(`open`, `snapshot`, `click`, `fill` 등)는 macOS/Linux와 100% 동일.

## Full reference
```bash
agent-browser skills get core --full
```
Pulls in commands.md, snapshot-refs.md, authentication.md, session-management.md, and more.
