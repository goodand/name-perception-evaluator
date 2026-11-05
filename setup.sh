#!/usr/bin/env bash
# 이름 검증 하네스 설치·확인 (Claude 모델만으로 동작). 사용: bash setup.sh
# - 가상환경(.venv) 만들고 의존성 설치(uv가 있으면 uv sync, 없으면 venv+pip)
# - claude CLI 확인(답변자·생성자. 각자 계정으로 로그인해 두면 된다)
# - 오프라인 시험(pytest): 네트워크·로그인 없이 가짜 답변자로 전 과정을 돌린다
# 선택: gpt-6-luna(OMP 실행기), LM Studio(로컬 LLM) — 있으면 `namecheck doctor`가 OK로 표시, run --answerers로 시도
set -euo pipefail
cd "$(dirname "$0")"

if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; elif [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=""; fi
if [ -z "$PY" ]; then
  if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then uv sync
  else python -m venv .venv; fi
  if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi
fi
if ! command -v uv >/dev/null 2>&1 || [ ! -f uv.lock ]; then "$PY" -m pip install -q pyyaml pytest; fi
echo "python: $("$PY" --version)"

if command -v claude >/dev/null 2>&1; then
  echo "claude CLI: $(claude --version 2>/dev/null | head -1)  (로그인 안 했으면: claude 실행 후 로그인)"
else
  echo "claude CLI 없음: https://docs.claude.com/claude-code 에서 설치 후 로그인하세요 (수집·생성에 필요, 시험에는 불필요)"
fi

if [ -n "${NAME_HARNESS_RUNNER:-}" ]; then echo "실행기: NAME_HARNESS_RUNNER=$NAME_HARNESS_RUNNER"
else echo "실행기: scripts/vendor/workflow_runner (동봉본, PROVENANCE.json)"; fi

"$PY" -m pytest tests -q
"$PY" scripts/namecheck.py doctor
cat <<'EOF'

설치 확인 끝. 다음 단계는 docs/harness/NAMING_GUIDE.md:
  1) docs/harness/briefs/name-harness.json 을 복사해 새 주제 브리프 작성
  2) 후보 생성(격리):   python scripts/namecheck.py generate haiku,haiku,sonnet <out>/gen --brief <brief>
  3) 한 번에 검증:      python scripts/namecheck.py run <brief> <후보.txt|a,b,c> <out> [--human] [--review claude:sonnet]
  4) <out>/report.md 확인 후 설명문을 직접 읽어 교차 확인
EOF
