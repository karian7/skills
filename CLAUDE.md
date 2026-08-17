# skills — repo conventions

karian7 개인 스킬 마켓플레이스. Claude Code / Codex 양쪽에서 동일하게 동작한다.
`~/workspace/CLAUDE.md` 규약(TDD·tidy-first·품질 게이트·커밋 제목 50자)이 그대로 적용된다.

## 릴리스 워크플로우

스킬 내용을 고쳤으면 **push 전에** 버전을 올린다. `version` 필드가 없으면 Claude Code 는
git SHA 로 폴백하는데(`a3971fa1380a` 같은), 그러면 설치측에서 무엇이 바뀌었는지 알 수 없고
marketplace 에서 버전 제약도 걸 수 없다.

1. **버전 결정** — 스킬 추가·기능 확장은 minor, 문서·버그 수정은 patch,
   스킬 제거·이름 변경처럼 기존 호출이 깨지면 major
2. **매니페스트 3개를 같은 값으로 수정**
   - `plugins/<plugin>/.claude-plugin/plugin.json`
   - `plugins/<plugin>/.codex-plugin/plugin.json`
   - `.claude-plugin/marketplace.json` — 해당 `plugins[]` 항목
3. **커밋** — 변경과 같은 커밋에 담거나, 여러 커밋을 묶어 릴리스할 땐 `chore` 커밋 하나로
4. **push**
5. **검증** — `claude plugin update <plugin>@skills` 가 SHA 가 아니라 semver 를 보고하는지 확인.
   실제 적용은 Claude Code 재시작 후.

`.agents/plugins/marketplace.json` 은 라우팅·정책 전용이라 `version` 필드를 받지 않는다. 건드리지 않는다.

세 매니페스트가 어긋나면 Claude 와 Codex 가 서로 다른 버전을 보고한다. 커밋 전 확인:

```bash
rg -H '"version"' .claude-plugin/marketplace.json plugins/*/.claude-plugin/plugin.json plugins/*/.codex-plugin/plugin.json
```

## 매니페스트는 전부 dot 디렉토리에 있다

`.claude-plugin/`, `.codex-plugin/`, `.agents/` — `fd` 는 `-H`, `ls` 는 `-a` 없이는 못 찾는다.
"매니페스트가 없다"고 판단하기 전에 숨김 포함으로 다시 확인할 것.

## AGENTS.md

`plugins/karian7/AGENTS.md` 는 `CLAUDE.md` 를 가리키는 심볼릭 링크(Codex 호환).
내용은 `CLAUDE.md` 만 고치면 양쪽에 반영된다.

## 스킬 동시성

브라우저·데몬처럼 프로세스 밖 상태를 잡는 스킬은 세션 격리를 문서에 명시한다.
여러 Claude 세션과 병렬 서브에이전트가 같은 스킬을 동시에 호출한다고 가정할 것.
선례: `skills/agent-browser/SKILL.md` 의 "Concurrency & session isolation".
