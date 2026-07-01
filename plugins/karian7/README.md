# karian7 plugin

karian7 의 통합 스킬 플러그인.

## 포함된 스킬

- **md-preview** — 로컬 Markdown 파일을 pandoc 으로 HTML 변환 후 브라우저에 띄우고 라이브 리로드
- **daum-mail** — Daum/Hanmail IMAP (목록·읽기·검색·초안·휴지통·브리핑). SUBJECT ASCII 서버 검색 ✅, 한글 클라이언트 매칭
- **naver-mail** — Naver Mail IMAP (목록·읽기·검색·초안·휴지통·브리핑). 모든 키워드 클라이언트 매칭 (SUBJECT 서버 검색 ❌)
- **netlify** — 현재 디렉토리 정적 파일을 Netlify CLI로 배포, 사이트명 입력 후 브라우저 자동 오픈

## 호출

- Claude Code: `/karian7:md-preview`, `/karian7:daum-mail`, `/karian7:naver-mail`, `/karian7:netlify`
- Codex: skill list 에서 `karian7:md-preview`, `karian7:daum-mail`, `karian7:naver-mail`, `karian7:netlify`
