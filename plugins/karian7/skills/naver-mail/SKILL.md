---
name: naver-mail
description: |
  Naver Mail(imap.naver.com) 메일을 IMAP으로 다루는 스킬. 6가지 기능 지원:
  (1) 메일 목록 조회 — INBOX·보낸메일함·임시편지함·휴지통의 최근 N통/안 읽은 메일
  (2) 특정 메일 읽기 — UID로 헤더+전체 본문 출력
  (3) 메일 검색 — 발신자·날짜·읽음상태 서버 필터 + 키워드 클라이언트 매칭
  (4) 초안 저장 — 임시편지함에 저장, 발송 불가
  (5) 휴지통 이동 — 영구 삭제 없음, 복구 가능
  (6) 브리핑 — 받은편지함 요약, 보낸메일함 교차 참조로 회신 완료 표시
  Triggers: "네이버 메일 확인", "Naver 메일 읽어줘", "네이버 받은편지함", "오늘 네이버 메일", "최근 네이버 메일 N개", "안 읽은 네이버 메일", "메일 검색", "메일 작성", "초안 저장", "휴지통 이동"
allowed-tools:
  - Bash
---

# naver-mail

Naver Mail 메일을 IMAP4_SSL로 다루는 스킬.

## Prerequisites

**1단계** — IMAP 활성화 및 앱 비밀번호 발급: <https://mail.naver.com/v2/settings/smtp/imap>

**2단계** — 자격증명 저장 (keyring 권장, 환경변수 폴백):

```bash
# 권장: macOS Keychain / Windows Credential Manager
uv run --with keyring python3 -c "
import keyring
keyring.set_password('naver-mail', 'email', 'you@naver.com')
keyring.set_password('naver-mail', 'app-password', '앱비밀번호')
"

# 대안: 환경변수
export NAVER_EMAIL="you@naver.com"
export NAVER_APP_PASSWORD="앱비밀번호"
```

자세한 설정 안내: `references/setup.md`

## 기능별 실행

```bash
SCRIPTS="${CLAUDE_PLUGIN_ROOT}/skills/naver-mail/scripts"

# (1) 메일 목록 — 최근 30통
RECENT_COUNT=30 uv run "$SCRIPTS/fetch_inbox.py"

# (1) 다른 폴더 (보낸메일함 / 임시편지함 / 휴지통)
MAILBOX=보낸메일함 RECENT_COUNT=20 uv run "$SCRIPTS/fetch_inbox.py"

# (2) 특정 메일 읽기
uv run "$SCRIPTS/read_mail.py" <UID>
# 또는: UID=12345 uv run "$SCRIPTS/read_mail.py"

# (3) 메일 검색
QUERY="회의 일정" SEARCH_SINCE=2026-06-01 uv run "$SCRIPTS/search_mail.py"
SEARCH_FROM="someone@example.com" SEARCH_UNSEEN=1 uv run "$SCRIPTS/search_mail.py"

# (4) 초안 저장 (발송 안 함)
DRAFT_TO="to@example.com" DRAFT_SUBJECT="제목" DRAFT_BODY="본문" \
  uv run "$SCRIPTS/compose_draft.py"

# (5) 휴지통 이동
uv run "$SCRIPTS/move_to_trash.py" <UID> [UID2 ...]

# (6) 브리핑 (보낸메일함 교차 참조 포함)
BRIEFING_REPLIED=1 RECENT_COUNT=30 uv run "$SCRIPTS/fetch_inbox.py"
```

## 검색 가이드

`QUERY`에 키워드를 주면 서버에서 발신자·날짜·읽음상태로 후보를 좁힌 뒤, 클라이언트에서 MIME 디코딩 후 제목·발신자에 키워드를 매칭한다 (ASCII·한글 모두 동작).

| 환경변수 | 설명 |
|----------|------|
| `QUERY="키워드"` | 공백 구분 AND 매칭. CLI 인자로도 가능 |
| `SEARCH_FROM` / `SEARCH_TO` | 발신자/수신자 필터 |
| `SEARCH_SINCE` / `SEARCH_BEFORE` | `YYYY-MM-DD` 날짜 범위 |
| `SEARCH_UNSEEN=1` | 안 읽은 메일만 |
| `SEARCH_BODY=1` | 본문까지 매칭 (느림) |
| `SEARCH_LIMIT` | 결과 최대 건수 (기본 20) |
| `SCAN_LIMIT` | 스캔 상한 (기본 200). `scan_truncated:true` 시 늘리거나 날짜 필터로 좁힐 것 |

> **참고**: Naver IMAP은 `SUBJECT` 서버 검색이 동작하지 않고 `BODY`/`TEXT`도 항상 0건. 모든 키워드는 클라이언트 매칭으로 처리된다.

## 브리핑 형식

`BRIEFING_REPLIED=1` 로 실행하면 보낸메일함을 교차 참조해 이미 회신한 항목을 표시한다. JSON 출력을 받아 LLM이 직접 요약 — `replied:true` 항목 → ✅, 미처리 → ⬜.

## 보안

- 읽기 전용: `readonly=True` + `BODY.PEEK[]` — `\Seen` 플래그 변경 없음
- 쓰기는 사용자 명시 요청 시만 (초안 저장 / 휴지통 이동)
- `NAVER_APP_PASSWORD` 절대 출력 금지
- 초안 저장만 가능 — SMTP 발송 경로 없음

## Troubleshooting

| 증상 | 원인 / 해결 |
|------|-------------|
| `AUTHENTICATIONFAILED` | 앱 비밀번호 필요 (일반 비밀번호 불가) |
| `환경변수 ... 가 필요합니다` | `~/.secrets` 미로딩 |
| 키워드 검색 결과 없음 | `QUERY=` 환경변수 사용 확인. 서버 SUBJECT 검색 미지원 — 클라이언트 매칭으로 동작 |
| Connection timeout | 네트워크 문제 또는 서버 일시 장애 |
