# skills

karian7 의 개인 스킬 마켓플레이스. **Claude Code** 와 **Codex CLI** 양쪽 호환.

## 구조

```
skills/                              ← 마켓플레이스 (이름: "skills")
├── .claude-plugin/marketplace.json   ← Claude Code 매니페스트
├── .agents/plugins/marketplace.json  ← Codex 매니페스트
└── plugins/
    └── karian7/                      ← 플러그인 (이름: "karian7")
        ├── .claude-plugin/plugin.json
        ├── .codex-plugin/plugin.json
        └── skills/
            ├── md-preview/
            ├── daum-mail/
            ├── naver-mail/
            ├── netlify/
            └── agent-browser/
```

## 설치

### Claude Code

```
/plugin marketplace add karian7/skills
/plugin install karian7@skills
```

### Codex

```bash
codex plugin marketplace add karian7/skills
```

> **현재 미해결**: marketplace 등록 후 plugin 단위 정식 enable 명령이 CLI 표면에서 명확하지 않음. `~/.codex/config.toml` 에 다음 블록을 수동 추가하는 것이 현재까지 확보된 경로:
>
> ```toml
> [plugins."karian7@skills"]
> enabled = true
> ```
>
> 이후 Codex 재시작.

## 포함된 스킬

| 스킬 | 설명 |
|------|------|
| `karian7:md-preview` | 로컬 Markdown 파일을 pandoc으로 렌더링해 브라우저에서 라이브 프리뷰 |
| `karian7:daum-mail` | Daum/Hanmail IMAP — 목록·읽기·검색·초안·휴지통·브리핑. keyring 자격증명 지원 |
| `karian7:naver-mail` | Naver Mail IMAP — 목록·읽기·검색·초안·휴지통·브리핑. keyring 자격증명 지원 |
| `karian7:netlify` | 현재 디렉토리 정적 파일을 Netlify CLI로 배포, 완료 후 브라우저 자동 오픈 |
| `karian7:agent-browser` | agent-browser CLI(Chrome via CDP)로 브라우저 자동화 — 폼 입력, 클릭, 데이터 추출, 스크린샷 |

## 업데이트

### Claude Code

```
/plugin marketplace update skills
/plugin update karian7@skills
```

### Codex

```bash
codex plugin marketplace upgrade skills
```

## 라이선스

MIT
