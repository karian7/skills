---
name: netlify
description: |
  현재 디렉토리의 정적 웹 파일을 Netlify CLI로 배포하는 스킬. 배포 전 배포 대상의 맥락(디렉토리명·title·package.json 등)에서
  사이트 이름 후보를 뽑아 AskUserQuestion 으로 고르게 하고, 배포 완료 후 브라우저를 자동으로 연다.
  이미 로그인된 Netlify 계정 사용 가정. URL 형식: `https://<사이트명>.netlify.app`
  Triggers: "netlify 배포", "netlify deploy", "netlify에 올려줘", "정적 사이트 배포", "netlify 사이트 만들어줘"
allowed-tools:
  - Bash
  - AskUserQuestion
---

# netlify

현재 디렉토리의 정적 웹 파일(HTML, CSS, JS 등)을 Netlify CLI로 배포한다.
macOS/Linux와 Windows(PowerShell/CMD) 모두 지원.

## Prerequisites

### macOS / Linux

```bash
netlify --version || brew install netlify-cli
netlify status  # 로그인 상태 확인
```

### Windows

```powershell
netlify --version
# 미설치 시:
npm install -g netlify-cli
# 또는: winget install Netlify.netlify-cli

netlify status
```

로그인이 안 된 경우 사용자에게 아래를 실행하도록 안내한다:
- macOS/Linux: `! netlify login`
- Windows: 터미널에서 직접 `netlify login` 실행 (브라우저 OAuth 필요)

## 배포 절차

### 1. 사이트 이름 제안 및 확인

`my-first-<닉네임>` 같은 고정 템플릿을 쓰지 않는다. 배포 대상을 먼저 읽어 **맥락에 맞는 이름**을 제안한다.

**맥락 수집** (있는 것만, 실패는 무시):

```bash
basename "$PWD"
sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' index.html 2>/dev/null | head -1
sed -n 's/.*<h1[^>]*>\(.*\)<\/h1>.*/\1/p' index.html 2>/dev/null | head -1
grep -m1 '"name"' package.json 2>/dev/null
git remote get-url origin 2>/dev/null
```

**슬러그 규칙** — Netlify 사이트 이름은 전역 유니크하며 소문자 영숫자와 하이픈만 허용한다:

- 소문자 영숫자 + 하이픈, 63자 이내. 공백·언더스코어·`.` 은 하이픈으로, 한글은 영문으로 옮긴다
- `portfolio`, `demo` 처럼 흔한 한 단어는 이미 선점돼 있다 — 2~3 단어를 조합한다
- 세션 맥락에 사용자·팀·행사 이름이 있으면 한 토큰으로 섞는다 (`kit-hackathon-demo`)

**AskUserQuestion 으로 확정** — 후보 3개를 제시한다:

- `header`: `사이트 이름`
- `question`: `어떤 주소로 배포할까요? 최종 URL은 https://<이름>.netlify.app 입니다. 직접 정하려면 Other 를 선택해 원하는 이름을 입력하세요.`
- `options`: 후보 3개. `label` 은 슬러그 그대로, `description` 은 근거와 전체 URL
  (예: label `kit-hackathon-demo` / description `index.html title 기반 · https://kit-hackathon-demo.netlify.app`)
- 임의 입력은 AskUserQuestion 이 자동으로 붙이는 **Other** 로 받는다 — 직접 입력용 옵션을 따로 만들지 않는다

받은 값(Other 포함)은 위 슬러그 규칙으로 정규화한 뒤 `SITE_NAME` 으로 쓴다.
정규화로 값이 바뀌면 배포 전에 최종 이름을 한 줄로 알린다.

### 2. 배포 실행

```bash
# 신규 사이트 배포 (사이트 이름 지정)
netlify deploy --prod --dir . --site-name "$SITE_NAME"

# 이미 연결된 사이트 재배포
netlify deploy --prod --dir .
```

`--dir .` 는 현재 디렉토리 기준. 빌드 결과물이 `dist/` 또는 `build/` 에 있으면 해당 경로로 변경.

**이름 충돌** — `site name is already taken` 으로 실패하면 접미사를 붙인 새 후보 3개
(`-app`, `-web`, 연도·조직명 등)로 AskUserQuestion 을 다시 띄운다. 임의로 이름을 바꿔 재시도하지 않는다.

### 3. 배포 후 브라우저 열기

OS를 감지해 적합한 명령을 사용한다:

```bash
# macOS
open "https://$SITE_NAME.netlify.app"

# Linux
xdg-open "https://$SITE_NAME.netlify.app"

# Windows (PowerShell)
Start-Process "https://$SITE_NAME.netlify.app"

# Windows (CMD)
start "" "https://%SITE_NAME%.netlify.app"
```

OS 감지: `uname -s` 가 `Darwin` → macOS, `Linux` → Linux. Windows는 `$env:OS`가 `Windows_NT` 또는 `uname` 명령 없음.

## 전체 흐름 예시

### macOS / Linux

```bash
SITE_NAME="kit-hackathon-demo"   # AskUserQuestion 으로 확정한 값
netlify deploy --prod --dir . --site-name "$SITE_NAME"
open "https://${SITE_NAME}.netlify.app"
```

### Windows (PowerShell)

```powershell
$SITE_NAME = "kit-hackathon-demo"
netlify deploy --prod --dir . --site-name $SITE_NAME
Start-Process "https://$SITE_NAME.netlify.app"
```

## 기존 사이트 재배포

`netlify.toml` 이 있거나 `.netlify/state.json` 에 사이트 ID가 있으면 이름을 묻지 않고 `--site-name` 없이 실행:

```bash
netlify deploy --prod --dir .
```

## 주의

- `netlify login` 은 사용자가 직접 수행해야 하는 단계 (브라우저 OAuth 필요).
- 배포 대상은 항상 현재 디렉토리 기준. 다른 경로 배포 시 `--dir <path>` 명시.
- `--prod` 없으면 Draft URL로 배포됨 — 운영 배포 시 반드시 포함.
- Windows에서 경로에 공백이 있으면 `--dir` 인수를 따옴표로 감쌀 것.
