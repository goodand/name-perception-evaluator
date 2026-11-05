# name-perception-evaluator

새로 지은 이름(저장소·화면 유형·템플릿 칸 이름 등)이 **처음 보는 사람에게 의도한 뜻으로 읽히는지** 미리 확인하는 하네스.
후보를 맥락 없는 별도 모델에게 이름만 보여 주고, 받아들여진 뜻을 규칙으로 판정해 고른다.

## 설치
    bash setup.sh
가상환경·의존성·`claude` CLI 확인·오프라인 시험(pytest)·답변자 백엔드 점검(`namecheck doctor`)까지 한 번에 한다.
필수: Python 3.12+, `claude` CLI 로그인. 선택: gpt(OMP 실행기), LM Studio(로컬 LLM).

## 사용
    python scripts/namecheck.py brief-check docs/harness/briefs/<주제>.json
    python scripts/namecheck.py generate haiku,haiku,sonnet <out>/gen --brief <brief>
    python scripts/namecheck.py run <brief> <후보,…> <out> [--human] [--review claude:sonnet] [--no-local]
    python scripts/namecheck.py overlap --rules <rules.json> --samples <out>/*/*.jsonl
결과는 `<out>/report.md`. 결과 폴더는 저장소 밖이나 `out/`(무시됨)에 둔다. 명령 전체는 docs/harness/NAMING_GUIDE.md.

## 문서
- 안내: docs/harness/NAMING_GUIDE.md (네 주체, 스크립트/스킬 구분, 명령표)
- 정의: docs/harness/REPO_DEFINITION.md (어떤 조건의 용어를 고르는가, 필수·선택 조건, 달성 전략)
- 결정·질문 기록: docs/harness/DECISION_LOG.md
- 설계: docs/harness/name_harness_v2.md · 정리 계획: docs/harness/CLEANUP_PLAN.md
- 옛 후보 기록: docs/harness/history/

## 원칙(요약)
- 답변자에게는 이름만, 생성자에게는 하는 일·사람 행동만. 지시문에 개발·SW 단어를 넣지 않는다(`scripts/prompt_check.py`가 경고).
- 판정은 규칙. LLM 평가자(`--review`)는 경고만 낸다. 한 번이라도 오독된 후보는 뺀다(모두 빠지면 오독률 최저에서 예비 선택).
- 이름은 `[대상]-[역할]`, 키워드 3개 이하. 이름 충돌은 참고 정보. 사용자 후보를 먼저 돌린다.
- 동봉 실행기(`scripts/vendor/workflow_runner`)와 수정 프로토콜(`skills/modification-protocol`)은 원문 복사이며 고치지 않는다(PROVENANCE.json).
