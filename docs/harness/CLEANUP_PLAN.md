# 결과물 정리 계획 (2026-11-05, fork 세션 — 읽기만 함, 수정·커밋 없음)

새 저장소: **name-perception-evaluator** — https://github.com/goodand/name-perception-evaluator.git (2026-11-05 확정)

기준: `git status`(2026-11-05 15시경), master, 미커밋 4 수정 + 35 신규(폴더 포함). 테스트 `.venv/Scripts/python.exe -m pytest tests -q` → **191 passed (3.66s)**.

## 1. 분류

A = 이름 하네스 → 새 저장소(`name-perception-evaluator`)로. B = ldx_workbench에 남김. C = 임시·버림. "미확인"은 추측하지 않은 것.

### 수정된 추적 파일 (M)

| 파일 | 분류 | 근거 |
|---|---|---|
| `scripts/check_terms.py` | **A+B 둘 다** | 추적본은 ldx 용어 판정(`docs/glossary/terms.yaml`, names_rounds)에도 쓰임. 하네스 전용 함수(overlap·choose·split_scores·lint_*·wilson)가 +237줄 추가됨. 새 저장소로 복사하고, ldx에는 수정분도 함께 커밋(ldx의 `test_check_terms.py` 회귀 테스트가 이 파일을 봄) |
| `scripts/collect_samples.py` | **A+B** | 같은 이유. 이번 세션 수정(RUNNER 상대경로, 평문 INSTR, plain_runner 분기)은 모두 하네스 작업. git log 3건(f60ed11, dba99c0, 9e8f79b) 모두 이 세션 계열 |
| `scripts/ask_local_llm.py` | **A+B** | 수정 1곳(JSON 입력)만. 기본 입력이 `docs/glossary/final_terms.json`(ldx 용어)이라 ldx 쪽 도구이기도 함. 이번 세션 수정 |
| `docs/harness/name_harness_v2.md` | **A** | v2.2 절 +41줄 추가(이 세션). 하네스 설계 기록 |

### 신규 파일 (??)

| 파일 | 분류 | 근거 |
|---|---|---|
| `scripts/namecheck.py` | A | CLI 진입점 |
| `scripts/run_naming.py` | A | 한 번에 돌리기 |
| `scripts/name_keywords.py` | A | 생성·키워드 통계 |
| `scripts/collect_variants.py` | A | 답변자 재실험 |
| `scripts/check_availability.py` | A | 충돌 조회 |
| `scripts/compare_judges.py` | A | 판정기 비교 |
| `scripts/plain_runner.py` | A | 평문 입출력(이 세션) |
| `scripts/prompt_check.py` | A | 개발 용어 경고(이 세션) |
| `scripts/review_explanations.py` | A | 격리 평가자(이 세션) |
| `scripts/vendor/workflow_runner/{adapters,claude_adapter}.py, PROVENANCE.json` | A | 동봉 실행기(원본 무수정) |
| `skills/modification-protocol/{SKILL.md,PROVENANCE.json}` | A | 수정 프로토콜 원문 |
| `setup.sh` | A | 설치 스크립트 |
| `docs/harness/NAMING_GUIDE.md`, `REPO_DEFINITION.md`, `DECISION_LOG.md` | A | 안내·정의·결정 기록 |
| `docs/harness/naming_profile.json`, `briefs/name-harness.json`, `dev_words.json`, `risky_tokens.json`, `naming_failures.json` | A | 프로필·브리프·사전·실패 사례 |
| `formal/name-harness/lean/` (NameHarness: System·Properties·Explore, lakefile, lean-toolchain v4.33.0) | A | 테스트 명세 동시 충족 증명(8절). `.lake/`는 자체 .gitignore |
| `tests/test_{ask_local_llm,check_availability,check_terms_context,check_terms_gate,compare_judges,name_keywords,namecheck_cli,naming_failures,overlap,portable,prompt_check,reexperiment,review_explanations,run_naming}.py` (14개) | A | 하네스 명세 |
| `docs/glossary/naming_repo_names.json`, `naming_repo_names_v2.json` | **A(기록, 보존)** | 이 하네스 저장소 이름 1·2차 후보 규칙. 선택이 끝나면 `naming_failures.json`에 요지만 남기고 버려도 됨 |
| `docs/glossary/gui_kind_names_semh1.json`, `repo_names_v11.json`, `slot_names_v1.json` | **B** | 표 대조 GUI 세션(`local_45a210d3`) 작업. 커밋 dc667a6·5a8ce2f 계열이 같은 폴더에 v2~v8을 넣음. 이 세션은 만들지 않음 → 그 세션이 커밋할 것. 단 `slot_names_v1.json`은 지금 `git status`에 없음(이미 dc667a6으로 커밋된 듯) — 미확인 |

### A에 들어가지만 추적 중인 파일(복사 대상, 상태 변화 없음)

`tests/test_check_terms.py`, `tests/test_collect_samples.py`, `tests/baseline_names_rounds.json`, `docs/glossary/names.yaml`, `names_r2.yaml`, `docs/glossary/names_rounds/*`(회귀 테스트 입력 5개). 새 저장소에서 회귀 테스트를 유지하려면 함께 복사해야 한다. 안 가져가면 `test_regression_names_rounds`를 빼야 함.

### C. 임시·버릴 것 (저장소 밖, 정리 불필요)

`<home>\AppData\Local\Temp\claude\…\<세션 id>\scratchpad\` 아래 `repo_v1~v4`, `repo_plain1`, `gen`, `gen2`, `smoke_*`, `e2e`, `reexp`, `s12~s14` 등 검증 결과물·답변·art_*. 저장소 안에는 임시 파일 없음(`git status`에 없음).

## 2. 새 저장소 구조 제안 (`name-perception-evaluator`)

```
name-perception-evaluator/
├── README.md
├── setup.sh
├── requirements.txt
├── .gitignore
├── scripts/
│   ├── namecheck.py          # CLI 진입점
│   ├── run_naming.py
│   ├── check_terms.py
│   ├── collect_samples.py
│   ├── collect_variants.py
│   ├── name_keywords.py
│   ├── check_availability.py
│   ├── compare_judges.py
│   ├── plain_runner.py
│   ├── prompt_check.py
│   ├── review_explanations.py
│   ├── ask_local_llm.py
│   └── vendor/workflow_runner/{adapters.py, claude_adapter.py, PROVENANCE.json}
├── skills/modification-protocol/{SKILL.md, PROVENANCE.json}
├── docs/
│   ├── NAMING_GUIDE.md
│   ├── REPO_DEFINITION.md
│   ├── DECISION_LOG.md
│   ├── name_harness_v2.md
│   ├── naming_profile.json
│   ├── dev_words.json
│   ├── risky_tokens.json
│   ├── naming_failures.json
│   └── briefs/name-harness.json
├── tests/ (16개 + baseline_names_rounds.json)
└── fixtures/names_rounds/ + names.yaml, names_r2.yaml   # 회귀 테스트 입력(선택)
```

경로를 `docs/harness/` → `docs/`로 올리면 코드의 경로 상수를 바꿔야 한다: `run_naming.PROFILE_DEFAULT`, `name_keywords.GEN_PROMPT`의 브리프·프로필 경로, `prompt_check.WORDS`, `check_terms.RISKY_DEFAULT`, `namecheck.PROFILE`·기본 brief, `tests/*`의 `ROOT / "docs/harness/..."`. 바꾸지 않으려면 `docs/harness/` 구조를 그대로 가져간다(권장: 그대로. 수정량 0).

### README.md 초안

```markdown
# name-perception-evaluator

새로 지은 이름(저장소·화면 유형·템플릿 칸 이름 등)이 **처음 보는 사람에게 의도한 뜻으로 읽히는지** 미리 확인하는 하네스.
후보를 맥락 없는 별도 모델에게 이름만 보여 주고, 받아들여진 뜻을 규칙으로 판정해 고른다.

## 설치
    bash setup.sh
가상환경·의존성·`claude` CLI 확인·오프라인 시험(pytest)·답변자 백엔드 점검(`namecheck doctor`)까지 한 번에 한다.
필수: Python 3.12+, `claude` CLI 로그인. 선택: gpt(OMP 실행기), LM Studio.

## 사용
    python scripts/namecheck.py brief-check docs/harness/briefs/<주제>.json
    python scripts/namecheck.py generate haiku,haiku,sonnet <out>/gen --brief <brief>
    python scripts/namecheck.py run <brief> <후보,…> <out> [--human] [--review claude:sonnet] [--no-local]
    python scripts/namecheck.py overlap --rules <rules.json> --samples <out>/*/*.jsonl
결과는 `<out>/report.md`. 자세한 명령은 docs/harness/NAMING_GUIDE.md.

## 문서
- 안내: docs/harness/NAMING_GUIDE.md (네 주체, 스크립트/스킬 구분, 명령표)
- 정의: docs/harness/REPO_DEFINITION.md (어떤 조건의 용어를 고르는가, 필수·선택 조건, 달성 전략)
- 결정·질문 기록: docs/harness/DECISION_LOG.md
- 설계: docs/harness/name_harness_v2.md

## 원칙(요약)
- 답변자에게는 이름만, 생성자에게는 하는 일·사람 행동만. 지시문에 개발·SW 단어를 넣지 않는다(`prompt_check.py`가 경고).
- 판정은 규칙. LLM 평가자(`--review`)는 경고만 낸다.
- 이름 충돌은 참고 정보. 사용자 후보를 먼저 돌린다.
```

### .gitignore

```
.venv/
__pycache__/
*.pyc
# 검증 결과물·답변·실행기 산출물
out/
runs/
art_*/
*.jsonl
!tests/**/*.jsonl
review.json
report.md
# 문서·자료 파일은 올리지 않는다(사용자 지시 2026-11-05)
*.pdf
*.csv
*.xlsx
*.xls
*.hwp
*.hwpx
# Lean 빌드 산출물
formal/**/.lake/
```
(`report.md`·`*.jsonl`은 `<out>` 안에만 생기므로 `out/`만 막아도 됨. 결과 폴더 이름을 `out/`으로 통일하는 규칙을 안내서에 적는 것을 권장.)

### requirements.txt

```
pytest==8.4.2
pyyaml==6.0.3
```
근거: `scripts/*.py` import는 표준 라이브러리 + `yaml`(`check_terms.load_rules`의 .yaml 규칙, `ask_local_llm`, `check_availability`)만. ldx `pyproject.toml`의 bm25s·duckdb 등은 하네스와 무관. 설치본 `.venv`에 `pip freeze` 결과가 비어 보이는데(uv 관리) 이는 미확인.

## 3. 재사용성 점검 (고칠 곳 — 제안만, 수정 안 함)

| 위치 | 문제 | 제안 |
|---|---|---|
| `scripts/vendor/workflow_runner/adapters.py:22-24` | `_OMP_ROOT = D:\web_chat_gpt\harness-evaluation-20261019\omp`, `_OMP_EXE`, `_CONTROLLED_CONFIG` PC 고정. 다른 PC에서 gpt 답변자는 "failed"로 끝남(PROVENANCE note에 명시됨) | 동봉본은 고치지 않는 원칙이므로 **감싸는 쪽에서** 환경 변수로 대체: `collect_samples.make_backend`·`name_keywords.generate`에서 `os.environ.get("NAME_HARNESS_OMP_ROOT")`가 있으면 `adapters._OMP_ROOT/_OMP_EXE/_CONTROLLED_CONFIG`를 import 뒤 덮어쓴다. `namecheck doctor`가 그 변수 유무를 표시. setup.sh 안내 문구에 추가 |
| `adapters.py:168` | `state_dir = _OMP_ROOT / "state"` OAuth 상태 재사용 | 위 환경 변수로 함께 해결 |
| `adapters.py:28-31` | 시스템 프롬프트 "isolated workflow worker…" — 개발 신호. gpt 경로에만 남음 | 평문 gpt 실행 경로(`plain_runner.gpt_text`)를 OMP RPC 없이 만들 수 없으면 현 상태 유지. 안내서에 "gpt 답변은 형식 요구·worker 프롬프트가 붙음(지시문 검사 경고)" 명시됨 |
| `scripts/namecheck.py:207` | `~/.lmstudio/bin/lms.exe` — Windows 전용 경로. Linux/macOS는 `~/.lmstudio/bin/lms` | `shutil.which("lms") or 후보 두 개(.exe 유무)` 순회 |
| `scripts/namecheck.py:188`, `plain_runner.py:17`, `ask_local_llm.py:32` | LM Studio 주소 `127.0.0.1:1234` 세 곳에 중복 | 한 곳(`plain_runner.LMS_BASE`)으로 모으고 환경 변수 `LMSTUDIO_URL`로 덮어쓰기 |
| `scripts/vendor/workflow_runner/PROVENANCE.json` | `source_repo` D:/ 경로는 출처 기록이므로 그대로 둠. sha256은 `tests/test_portable.py`가 검증(191 통과) | 변경 불필요 |
| `skills/modification-protocol/PROVENANCE.json` | 같음 | 변경 불필요 |
| `setup.sh` | clone 직후 흐름 읽기 점검: `.venv` 없음 → `uv sync`(uv.lock 없으면 pip로 pyyaml·pytest) → pytest → doctor. **문제 1**: `uv sync`는 `pyproject.toml`을 요구하는데 새 저장소에는 없음 → uv가 있으면 실패. **문제 2**: 끝의 안내가 `name_keywords.py generate`·`run_naming.py`를 직접 부르는데 안내서는 `namecheck`를 쓰라 함 | `uv`가 있어도 `pyproject.toml`이 없으면 `python -m venv` 경로로 가게 조건 추가, 또는 새 저장소에 최소 `pyproject.toml` 포함. 안내 문구를 `namecheck generate / run`으로 통일 |
| `scripts/check_terms.py:349` | 기본 규칙 경로 `docs/glossary/terms.yaml`(ldx 전용) | 새 저장소에는 없는 파일. 인자 없이 부를 때만 쓰이므로 안내만 하거나 `docs/harness/briefs`로 바꿈 |
| `scripts/ask_local_llm.py:43` | 기본 입력 `docs/glossary/final_terms.json`(ldx 전용) | 같음. 새 저장소로 가면 기본값을 없애거나 인자 필수로 |
| `tests/test_check_terms.py:134-141` | `docs/glossary/names*.yaml`·`names_rounds/*` 회귀 입력 의존 | `fixtures/`로 함께 복사하거나 이 테스트를 ldx에만 둠 |
| `tests/test_run_naming.py`, `test_review_explanations.py`, `test_prompt_check.py` | `from test_run_naming import …` 등 테스트 간 import — `tests/`에 `__init__.py` 없이 rootdir import에 의존 | pytest rootdir이 저장소 루트면 동작(지금 191 통과). 새 저장소에서도 루트에서 돌리면 됨. `conftest.py`로 `tests/`를 path에 넣으면 더 안전 |
| 결과 폴더 | `run <out>`을 사용자가 매번 지정, scratchpad에 흩어짐 | 기본 `out/<brief>_<날짜>/`를 제안하고 `.gitignore`에 `out/` |
| 인코딩 | `collect_samples.py`·`ask_local_llm.py` LF/CRLF 경고 | `.gitattributes`에 `*.py text eol=lf` |

## 4. push 전 점검 (사용자 지시 2026-11-05 — 순서대로. 실행은 사용자가 "커밋해"라고 한 뒤)

1. `.gitignore`를 **먼저** 만든다(2절 내용).
2. 개인 이름·계정·경로가 없는지 — 둘 다 0건이어야 한다:
   ```bash
   git grep -nIE "$PRIVATE_PATTERN|Users[\\/]" -- . ':!*.lock'
   ```
   ```bash
   grep -rnIE "$PRIVATE_PATTERN|Users[\\/]" docs scripts skills tests formal setup.sh README.md
   ```
   있으면 지우거나 `<home>`으로 바꾼다. 2026-11-05 점검: 하네스 파일(docs/harness, scripts, skills, tests, setup.sh, formal)에서 이 문서 1건만 있었고 `<home>`으로 바꿨다. PROVENANCE의 `D:/web_chat_gpt/...`는 드라이브 경로이고 개인 이름이 아니므로 출처 기록으로 둔다.
3. 자료 파일 확장자가 없는지 — 0건이어야 한다:
   ```bash
   git ls-files | grep -iE '\.(pdf|csv|xlsx?|hwpx?)$'
   ```
   ```bash
   find . -path ./.git -prune -o -type f -print | grep -iE '\.(pdf|csv|xlsx?|hwpx?)$'
   ```
   2026-11-05 점검: 복사 대상 폴더에 해당 확장자 없음. 회귀 입력 `docs/glossary/names_rounds/*.json`은 json.
4. 커밋 메시지·주석에 이메일이 없는지(`Co-Authored-By`의 noreply 주소만 예외).

## 5. 커밋 명령 초안 (실행하지 않음)

두 저장소로 나눠 간다는 전제. 이름(`name-perception-evaluator`) 결정 뒤 실행.

**(1) ldx_workbench — 하네스를 다른 세션이 계속 쓰므로 현 위치에도 커밋해 두는 안**

```bash
# 하네스 코드·문서·테스트 (A 전부; glossary의 다른 세션 파일은 제외)
git add scripts/check_terms.py scripts/collect_samples.py scripts/ask_local_llm.py \
  scripts/namecheck.py scripts/run_naming.py scripts/name_keywords.py scripts/collect_variants.py \
  scripts/check_availability.py scripts/compare_judges.py scripts/plain_runner.py scripts/prompt_check.py \
  scripts/review_explanations.py scripts/vendor/ skills/ setup.sh \
  docs/harness/ tests/
git commit -m "이름 검증 하네스 v2.3: namecheck CLI, 격리 평가자(--review), 개발 용어 경고(prompt_check), 평문 입출력(plain_runner), 묶음 겹침(overlap), 저장소 정의·결정 기록

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
주의: `docs/glossary/gui_kind_names_semh1.json`, `repo_names_v11.json`은 넣지 않는다(표 대조 GUI 세션 것). `naming_repo_names*.json`은 사용자가 기록으로 남길지 정한 뒤.

**(2) 새 저장소 `name-perception-evaluator` — 복사 뒤 첫 커밋**

```bash
mkdir name-perception-evaluator && cd name-perception-evaluator && git init
# ldx_workbench에서 복사: scripts/(위 12개 + vendor), skills/, setup.sh, docs/harness/ → docs/harness/ 그대로,
#   tests/(16개 + baseline_names_rounds.json), 선택: docs/glossary/names*.yaml + names_rounds/ (회귀 입력)
# 새로 쓰기(순서): .gitignore 먼저 → README.md, requirements.txt, .gitattributes
# 복사 뒤 4절 점검 2·3을 돌려 0건 확인
bash setup.sh      # 191 passed 확인
git add -A
git commit -m "이름 검증 하네스 첫 커밋: ldx_workbench에서 분리(원본 커밋 <sha>)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

## 6. 원래 세션에 넘길 고칠 것 (이 세션은 고치지 않음)

1. `setup.sh`: `uv sync`가 `pyproject.toml` 없으면 실패 → 조건 추가. 끝 안내를 `namecheck` 명령으로.
2. gpt OMP 경로를 환경 변수(`NAME_HARNESS_OMP_ROOT`)로 덮어쓰는 감싸기 + `doctor` 표시.
3. `namecheck.py:207` lms 경로 비Windows 대응. LM Studio 주소 3곳 통일.
4. `check_terms.py:349`, `ask_local_llm.py:43` ldx 전용 기본 경로.
5. `.gitattributes` `*.py text eol=lf`.
6. 결과 폴더 기본값 `out/` + `.gitignore`.

## 미확인
- `.venv`가 uv 관리인지(`pip freeze` 출력 없음) — 새 PC에서 `python -m venv` 경로로 가면 상관없음.
- `docs/glossary/slot_names_v1.json`이 이미 커밋됐는지(status에 없음 → 커밋된 것으로 보이나 확인 안 함).
- ~~`naming_repo_names*.json`을 기록으로 남길지~~ → 보존(사용자 2026-11-05). 새 저장소 `docs/history/`에 옛 후보 규칙·결과 보고서를 함께 둔다.

## 7. 누락된 테스트 (2026-11-05 점검, 함수 이름이 tests/ 어디에도 안 나오는 것 기준)

| 모듈 | 테스트 없음 | 위험 | 제안 |
|---|---|---|---|
| `plain_runner.py` | **모듈 전체** (`_clean`, `claude_text`, `qwen_text`, `ask_name`, `make_backend`) | 높음. 이 세션에서 새로 만든 평문 경로인데 가짜 실행기로도 안 돈다. `claude_text`의 `is_error` 처리, `_clean`의 `<think>`·"뜻:" 제거, `make_backend`가 이름 2개 이상이면 거부하는 것 모두 미검증 | `subprocess.run`·`urllib.request.urlopen`을 monkeypatch한 단위 테스트. `ask_name`이 "이름: x" 형식만 내고 다른 단어가 없는지(prompt_check 통과) |
| `collect_samples.make_backend` | gpt 분기가 `INSTR_NOW() + GPT_TAIL`을 붙이는지, claude·qwen이 plain_runner로 가는지 | 중간. 지시문 교체(collect_variants)가 부를 때 반영되는지는 `INSTR_NOW` 간접 검증만 | 가짜 `plain_runner.TEXT`·`adapters.run_agent`로 세 분기 각각 |
| `review_explanations` | `parse`(평문 "1. 다른 뜻 — …" 해석), `prompt_for`(규칙 신호어·다른 후보가 안 들어가는지는 run 경유로만), `report_lines`, `intent_of`(human_actions dict/list 두 형식) | 중간. `parse`는 번호 빠짐·"다른뜻" 띄어쓰기 변형·`-` 구분자 변형이 미검증 | `parse` 단위 테스트 5~6건, `intent_of` 두 형식 |
| `name_keywords` | `parse_plain` 직접(test_prompt_check에서 `parse_candidates` 경유 1건만), `load_batches`, `generate`의 평문 분기(claude는 `plain_runner.claude_text`, gpt는 `gpt_tail` 추가) | 중간. 생성기 평문 전환이 실제 호출 경로로 검증되지 않음 | `generate`를 가짜 `claude_text`로 1건, gpt 분기 1건 |
| `namecheck.py` | `cmd_run`은 CLI로 `--review`·`--answerers`·`--sep _` 조합 미검증(`--no-local` 1건만). `cmd_judge`·`cmd_compare`·`cmd_stats`·`cmd_risk`·`cmd_availability`·`cmd_generate`는 `--help` 목록 확인만 | 중간 | `main([...])`으로 각 명령 최소 1건(가짜 입력) |
| `run_naming._report` | 격리 평가자 표·경고 줄이 보고서에 들어가는 것은 run 경유 1건 | 낮음 | 생략 가능 |
| `check_terms` | `misread_hits`·`norm`·`_read`는 score 경유로 충분. `_runner_choose`는 원문 복사라 workflow-runner 테스트에 의존 | 낮음 | 생략 가능 |
| `check_availability._safe`, `compare_judges._lines`, `namecheck._emit/_load/_names` | 내부 보조 | 낮음 | 생략 가능 |

없는 테스트 종류(함수 단위가 아닌 것):
- **종단 평문 경로**: `run --review` 전 과정이 가짜 백엔드로는 돌지만(test_review_explanations), 가짜가 평문을 돌려주는 경로(`plain_runner.make_backend` → `collect`)는 없음. `validate`가 평문 결과 `{"items":[…]}`를 받는 것만 간접 확인.
- **지시문 검사 회귀**: `test_harness_prompts_are_clean`이 있으나 `dev_words.json`에 단어를 더하면 바로 깨지는 구조. 의도된 것(경고를 보고 고친다)이므로 유지.
- **`DECISION_LOG.md`·`REPO_DEFINITION.md`·`CLEANUP_PLAN.md`** 문서 링크 유효성(안내서가 가리키는 파일 존재) 검사 없음 → `tests/test_docs_links.py` 1건 제안.
- **`setup.sh`**: 실행 테스트 없음(쉘). 새 저장소에서 CI로 `bash setup.sh` 1회.

우선순위: plain_runner 단위 테스트 → review_explanations.parse → name_keywords.generate 평문 분기 → namecheck 각 명령 1건 → 문서 링크.

## 8. 테스트 명세 동시 충족 가능성 — Lean 4 증명 (2026-11-05)

위치: `formal/name-harness/lean/` (새 폴더, lake 프로젝트 `NameHarness`). 기존 `scripts/`·`tests/`는 손대지 않음.

- **모델** `NameHarness/System.lean`: `check_terms.py`의 `judge`·`misread_hits`·`score`·`_runner_choose`·`choose`·`overlap`, `prompt_check.py`의 `check`를 Lean 함수로 옮김. 설명문은 "들어 있는 신호어 집합"으로 추상화. 비율 비교는 분모를 곱한 자연수 비교(파이썬 실수 비교와 같은 순서).
- **정리** `NameHarness/Properties.lean`: 정리 33개.
  - pytest 단언 25개를 **같은 이름의 정리**로 옮겨 `decide`로 증명: `test_judge_*` 4, `test_score_*`·게이트 9, `test_choose_*` 8(예비 선택·baseline 동점·id 순·비율 vs 횟수 포함), `test_overlap_*` 2, `test_check_finds_words_from_both_dicts` 1, `runner_ties_keep_baseline` 1.
  - 일반 성질(모든 입력): `judge_false_of_misread`(오독이면 judge 실패), `excluded_iff_misreadN_pos`(제외 ⇔ 오독 표본>0), `pass_le_n`(통과≤표본), `not_fallback_of_eligible`(게이트 통과자가 있으면 예비 선택 아님), `choose_selected_mem`(선택된 이름은 표본 있는 입력 후보), `pyMax_mem`·`foldl_best_mem`.
- **결론**: 이 파일이 sorry 0으로 컴파일되므로, 위 테스트 단언들은 **한 구현(모델)으로 동시에 만족된다 = 서로 모순이 없다.** 일반 성질은 테스트가 요구하는 규칙(게이트·통과율·예비 선택·baseline)이 임의 입력에서도 충돌하지 않음을 보인다.
- **빌드·감사**: `lean 4.33.0`(로컬 Docker 이미지 `lean4:4.33.0-20261103-v1`; 네트워크가 githubusercontent를 막아 elan 설치 불가 → `lean-toolchain`을 v4.33.0으로 맞춤). `lake build` 성공. `#print axioms`: `propext`, `Quot.sound`, `Classical.choice`만(표준 공리). `sorry`·`native_decide` 0. 비공허성 예시(예비 선택이 실제로 일어나는 입력, 겹침이 1 이상 나오는 입력) `decide`로 확인.
- **한계(정직하게)**: 모델은 `norm`·부분 문자열 포함을 "집합 소속"으로 추상화했다. `rule_hash`·CLI 출력 문자열·stale/legacy 판정의 해시 계산·`wilson_upper`·`lint_names`는 모델에 없다(그 테스트들은 이 증명 범위 밖). 모델과 파이썬이 같은지는 테스트 25개가 양쪽에서 같은 답을 내는 것으로만 확인했다(차분 테스트 미실시).
- 실행:
  ```bash
  cd formal/name-harness/lean && MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/w" -w /w lean4:4.33.0-20261103-v1 lake build
  ```
