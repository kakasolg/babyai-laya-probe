# AGENTS.md

여러 머신(Windows PC·맥 미니·클라우드)과 여러 도구(Claude Code·Codex CLI·Antigravity)가
같은 저장소를 만진다. 브랜치가 말없이 갈라지거나 커밋 주체를 못 알아보는 일을 막기 위한 규칙.

## 규칙 1: 커밋마다 `Co-authored-by:`(도구) + `Host:`(머신) 트레일러

| 도구 | Co-authored-by | Host |
|---|---|---|
| Claude Code | 자동 (`Claude ... <noreply@anthropic.com>`) | 수동: `Host: <hostname>` |
| Codex CLI | `~/.codex/config.toml`의 `commit_attribution` (기본값 존재) | 수동 |
| Antigravity | 자동 없음 → `Co-authored-by: Google Antigravity <noreply@google.com>` 직접 추가 | 수동 |

author 이름(`moka`/`kakasolg`)은 머신마다 우연히 다를 뿐 규칙이 아니니
머신 구분은 `Host:`로만 한다.

## 규칙 2: 작업 전 항상 `git fetch --all` + `git log --oneline --all --graph`

다른 머신/도구가 만든 미병합 브랜치·중복 작업부터 확인한다.
`git log main..origin/main` 같은 비교를 로컬 ref로만 하면 로컬이 뒤처진 걸 놓친다.
비교는 항상 `origin/...` ref로 한다.

## 규칙 3: 정본 브랜치는 `main`

새 작업은 `main`에서 시작한다.

## 확인: 누가 뭘 했는지

```bash
git log --all --format="%h %ad %an — %s%n  tool: %(trailers:key=Co-authored-by,valueonly)%n  host: %(trailers:key=Host,valueonly)" --date=short
```

## 이 저장소에 넣지 않는 것

체크포인트·학습 산출물·venv·시범 덤프(`data/`)는 git에 넣지 않는다.
venv는 WSL `~/babyai-laya-venv`, 체크포인트는 저장소 밖(예: WSL `~/babyai-laya-ft/`)에 둔다.
