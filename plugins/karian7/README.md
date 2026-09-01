# karian7 plugin

karian7 의 통합 스킬 플러그인.

## 포함된 스킬

- **md-preview** — 로컬 Markdown 파일을 pandoc 으로 HTML 변환 후 브라우저에 띄우고 라이브 리로드
- **md-to-html** — Markdown 을 pandoc 으로 HTML 변환. 다크모드·반응형·콜아웃·목차 자동 생성, S3 업로드 공유 지원
- **daum-mail** — Daum/Hanmail IMAP (목록·읽기·검색·초안·휴지통·브리핑). SUBJECT ASCII 서버 검색 ✅, 한글 클라이언트 매칭
- **naver-mail** — Naver Mail IMAP (목록·읽기·검색·초안·휴지통·브리핑). 모든 키워드 클라이언트 매칭 (SUBJECT 서버 검색 ❌)
- **netlify** — 현재 디렉토리 정적 파일을 Netlify CLI로 배포, 사이트명 입력 후 브라우저 자동 오픈
- **agent-browser** — agent-browser CLI(Chrome via CDP)로 웹사이트 폼 입력·클릭·데이터 추출·스크린샷 등 브라우저 자동화 수행. macOS/Linux/Windows 설치 가이드 포함
- **websearch-enhanced** — 네이버 검색(뉴스·웹문서 탭)과 내장 웹 검색을 병행해 국내 보도·공고·공식 1차 소스를 교차 조사. 브라우저·API 키 없이 동봉 스크립트로 SERP 수집·기사 본문 추출. 네이버를 명시 지정할 때만 트리거

## 호출

- Claude Code: `/karian7:md-preview`, `/karian7:md-to-html`, `/karian7:daum-mail`, `/karian7:naver-mail`, `/karian7:netlify`, `/karian7:agent-browser`, `/karian7:websearch-enhanced`
- Codex: skill list 에서 `karian7:md-preview`, `karian7:md-to-html`, `karian7:daum-mail`, `karian7:naver-mail`, `karian7:netlify`, `karian7:agent-browser`, `karian7:websearch-enhanced`
