---
name: netlify
description: |
  현재 디렉토리의 정적 웹 파일을 Netlify CLI로 배포하는 스킬. 배포 전 사이트 이름(닉네임)을 사용자에게 묻고,
  배포 완료 후 브라우저를 자동으로 연다. 이미 로그인된 Netlify 계정 사용 가정.
  URL 형식: `https://my-first-<닉네임>.netlify.app` 또는 `https://<사이트명>.netlify.app`
  Triggers: "netlify 배포", "netlify deploy", "netlify에 올려줘", "정적 사이트 배포", "netlify 사이트 만들어줘"
allowed-tools:
  - Bash
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

### 1. 사이트 이름 확인

배포 전 사용자에게 묻는다 (verbatim):
> 닉네임이 무엇입니까? `https://my-first-<닉네임>.netlify.app` 으로 배포됩니다.
> (또는 원하는 사이트 이름을 직접 입력해주세요)

### 2. 배포 실행

```bash
# 신규 사이트 배포 (사이트 이름 지정)
netlify deploy --prod --dir . --site-name "my-first-<닉네임>"

# 이미 연결된 사이트 재배포
netlify deploy --prod --dir .
```

`--dir .` 는 현재 디렉토리 기준. 빌드 결과물이 `dist/` 또는 `build/` 에 있으면 해당 경로로 변경.

### 3. 배포 후 브라우저 열기

OS를 감지해 적합한 명령을 사용한다:

```bash
# macOS
open "https://my-first-<닉네임>.netlify.app"

# Linux
xdg-open "https://my-first-<닉네임>.netlify.app"

# Windows (PowerShell)
Start-Process "https://my-first-<닉네임>.netlify.app"

# Windows (CMD)
start "" "https://my-first-<닉네임>.netlify.app"
```

OS 감지: `uname -s` 가 `Darwin` → macOS, `Linux` → Linux. Windows는 `$env:OS`가 `Windows_NT` 또는 `uname` 명령 없음.

## 전체 흐름 예시

### macOS / Linux

```bash
SITE_NAME="my-first-kitkat"
netlify deploy --prod --dir . --site-name "$SITE_NAME"
open "https://${SITE_NAME}.netlify.app"
```

### Windows (PowerShell)

```powershell
$SITE_NAME = "my-first-kitkat"
netlify deploy --prod --dir . --site-name $SITE_NAME
Start-Process "https://$SITE_NAME.netlify.app"
```

## 기존 사이트 재배포

`netlify.toml` 이 있거나 `.netlify/state.json` 에 사이트 ID가 있으면 `--site-name` 없이 실행:

```bash
netlify deploy --prod --dir .
```

## 주의

- `netlify login` 은 사용자가 직접 수행해야 하는 단계 (브라우저 OAuth 필요).
- 배포 대상은 항상 현재 디렉토리 기준. 다른 경로 배포 시 `--dir <path>` 명시.
- `--prod` 없으면 Draft URL로 배포됨 — 운영 배포 시 반드시 포함.
- Windows에서 경로에 공백이 있으면 `--dir` 인수를 따옴표로 감쌀 것.
