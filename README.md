# skills

Koasu(karian7) 의 개인 스킬 마켓플레이스. **Claude Code** 와 **Codex CLI** 양쪽 호환.

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
            └── md-preview/SKILL.md   ← 첫 스킬
```

## 설치

### Claude Code

```
/plugin marketplace add karian7/skills
/plugin install karian7@skills
```

호출: `/karian7:md-preview`

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
> 이후 Codex 재시작. skill list 에 `karian7:md-preview` 노출 확인.

## 포함된 플러그인

| Plugin | 설명 | 스킬 수 |
|---|---|---|
| `karian7` | Koasu 의 통합 스킬 플러그인 | 1 (md-preview) |

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
