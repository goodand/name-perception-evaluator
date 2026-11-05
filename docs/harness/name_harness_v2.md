# 이름·용어 검증 하네스 v2 설계 (2026-11-04)

대상: `scripts/check_terms.py`(판정), `scripts/ask_local_llm.py`(Qwen 표본), 이름 세션의 임시 실행기(`%TEMP%\nmp\cl_run.py`·`gpt_run.py`·`jd2.py`).
입력: 이름 세션이 보고한 문제 7개(2026-11-04). 원칙: 기존 코드 재사용·최소 패치, LLM judge 없음(규칙 판정 + 사람/메인 교차 확인), 규칙 수정 후 새 표본으로만 재판정.

## 문제 → 결정

| # | 문제 | 결정 | 구현 위치 |
|---|---|---|---|
| P1 | 판정이 느슨해 대부분 통과, 변별 안 됨. 의도가 '실행 주체'·'범위' 같은 축에서 갈림 | 규칙에 선택 필드 `axes`를 추가. 축마다 `require`(하나 이상 나와야 함)와 `forbid`(하나도 나오면 안 됨). 축 결과를 `axis:<이름>` 사유로 따로 출력. 판정 결과에 **변별 경고**: 같은 규칙 묶음에서 이름의 80% 이상이 만점이면 "변별 없음" 출력 | `check_terms.py` `judge()` 확장, `report()` |
| P1' | 격리 심판 모델 2단계 | **구현하지 않음(확장 지점만)**. LLM judge 금지 원칙과 충돌. 필요해지면 "사람이 읽을 순서를 정하는 보조"로만, 판정 점수에는 넣지 않는다 | 설계 기록만 |
| P2 | 대소문자·한영 표기로 정상 설명 탈락 | 판정 전 정규화: NFKC → 소문자 → 공백·하이픈·밑줄 하나로. 규칙 단어도 같은 정규화. **한영 별칭 표**(엑셀↔excel, 표↔table…)는 넣지 않고 대신 **규칙 점검(lint)**: must 그룹·axes require에 한글만 있거나 영문만 있으면 경고 → 규칙 작성자가 보완. 별칭 표는 숨은 규칙이 되어 재현성이 떨어지므로 | `normalize()`, `lint_rules()` |
| P3 | 이름 여러 개를 한 목록에 주면 서로 힌트 | 표본 수집에 `--solo`: 이름 하나당 호출 한 번. 기본값은 기존 목록 방식(이전 회차와 비교 가능하게), 이름 검증 기본 권장은 solo | `collect_samples.py` |
| P4 | Qwen 타임아웃·건너뛰기 없음, yaml 미설치·깨짐 | 호출마다 `--timeout`(기본 300초). 실패·시간초과는 **빈 성공이 아니라** 상태 `failed`/`timed_out` 표본으로 기록하고 판정에서 제외·개수 표시. `import yaml`은 규칙 파일 읽을 때만(지연 import), judge만 쓰면 yaml 불필요. ldx `.venv`에 pyyaml을 dev 의존성으로 고정 | `ask_local_llm.ask(timeout=)`, `check_terms.load_rules()` |
| P5 | Claude 실행기 줄바꿈 인자 → 첫 줄만, 빈 배열이 에러 없이 저장 | Claude는 기존 격리 어댑터 `workflow-runner/claude_adapter.run_agent`(이미 stdin 전달)를 재사용, workflow-runner는 수정하지 않음. 수집기 공통 검사: **응답 항목 수가 요청 수와 다르거나, 요청한 id가 빠지거나, 설명이 빈 문자열이면 그 표본은 `failed`**. 저장 전 검사 | `collect_samples.py` `validate()` |
| P6 | 표본 형식이 모델마다 다름 | `to_items(obj)` 하나로 통일: 배열 / `{"items":[…]}` / run_agent 결과 `{"output":{"items":[…]}}` / 그 밖은 `ValueError`. 기존 표본 파일(gpt·cl·qwen)도 그대로 읽음 | `check_terms.to_items()` |
| P7 | 규칙 수정 기록 없음, 새 표본 원칙을 지킬 장치 없음 | 규칙마다 **규칙 해시**(`must`·`must_not`·`axes`를 정렬 JSON으로 sha256 앞 12자; `intended`·`candidates`·주석은 제외). 새 표본 파일은 봉투 `{"format":"samples/v2","rules_file","rule_hashes":{id:hash},"model","mode","prompt_sha","created","samples":[…]}`. 판정은 표본의 해시와 현재 해시가 다르면 그 id를 **stale로 제외**하고 표시(`--allow-stale`로만 포함). 봉투 없는 옛 표본은 `legacy`로 표시하고 **기본 제외**, `--allow-legacy`로만 포함(이전 회차 재현용). ← W3 실측: 포함하면 NoStaleCounted 위반(`tla/legacy_on.cfg`). 수정 사유는 규칙 파일 머리 주석에 쓰는 기존 관례 유지 | `rule_hash()`, 판정 |

## 바뀌지 않는 것
- 판정 기본식: must 모든 그룹 충족 + must_not 없음 (+ 새 axes 모두 충족). axes 없는 기존 규칙(terms.yaml, names.yaml)은 **결과가 이전과 같아야 함**(회귀 테스트).
- 사용법 `python scripts/check_terms.py <round.json> [rules]` 유지. 새로 `--samples`(여러 표본 파일 집계) 추가.
- 다른 세션 파일(`docs/glossary/repo_names*`)은 읽기만.

## 모듈 경계 (응집·결합)
- `check_terms.py`: 순수 함수(normalize·judge·rule_hash·to_items·lint_rules·aggregate) + CLI. 네트워크·프로세스 없음.
- `collect_samples.py`(신규, 유일한 새 파일): 모델 백엔드 3개(qwen=ask_local_llm.ask, gpt=adapters.run_agent, claude=claude_adapter.run_agent)를 같은 인터페이스 `call(items, timeout)->obj`로 감싸고, solo/list 모드·순서 뒤집기·validate·봉투 저장. 판정은 하지 않음(수집과 판정 분리).
- `ask_local_llm.py`: `ask()`에 timeout 인자 추가만. 기존 CLI 유지.

## 테스트(명세) — `tests/test_check_terms.py`, `tests/test_collect_samples.py`
1. 회귀: 기존 규칙·기존 표본(names_rounds/*.json)에서 통과 수가 패치 전과 같다(패치 전 값을 먼저 고정).
2. 정규화: "Excel"·"ＥＸＣＥＬ"·"excel" 같은 판정, "merge-decision"과 "merge decision" 같은 판정.
3. axes: require 없음→실패 사유 `axis:executor`, forbid 있음→실패, axes 없으면 영향 없음.
4. lint: 한글만 있는 그룹 경고, 한영 섞이면 경고 없음.
5. to_items: 네 형식 + 이상 형식 ValueError.
6. rule_hash: intended·candidates 바꿔도 같음, must 순서는 그대로 의미 있게(그룹 내부 순서 무시, 정렬), must_not 바꾸면 다름.
7. stale: 해시 다른 id는 제외·표시, `--allow-stale`이면 포함, 봉투 없는 표본은 legacy 포함.
8. validate: 빈 배열·id 누락·빈 설명·항목 수 불일치 → failed. 정상 → ok.
9. solo: 이름 3개 → 호출 3번, 각 호출 입력에 이름 1개만(가짜 백엔드로 확인).
10. timeout: 가짜 백엔드가 TimeoutError → 표본 상태 timed_out, 다른 표본은 계속.
11. 변별 경고: 이름 10개 중 9개 만점 → 경고, 5개 → 경고 없음.
12. 지연 import: `sys.modules['yaml']=None` 상태에서 `judge`·`to_items` import·호출 가능.

## 위험한 관심사 1개 — 형식 검증(W3) 대상
"규칙이 바뀐 뒤 옛 규칙으로 받은 표본이 현재 판정 합계에 섞이지 않는다"(P7). 상태: 규칙 버전, 표본(수집 시 버전), 판정. 속성 NoStaleCounted. 모델 `tla/StaleSamples.tla`, 경계 MaxV=2·MaxS=4(규칙 3판·표본 4개).

| 설정 | 기대 | 결과 |
|---|---|---|
| fix_on (해시 비교, legacy 제외) | 통과 | 통과, 155 상태 |
| fix_off (해시 비교 없음) | 위반 | 위반 |
| legacy_on (legacy 포함, 처음 설계) | — | **위반 → 설계 수정** |
| reach (새 표본이 셈에 드는 상태 존재) | 위반(=도달 가능) | 위반 |

## 확장 지점(구현 안 함)
격리 심판 모델(P1'), 한영 별칭 표, 규칙 변경 로그 파일 자동화, 표본 캐시 재사용.

## v2.1 — 적대 검증 반영 (2026-11-04, opus 검토자: 반박 7·부분 5·유지 1, 측정 대상 repo_names_samples 594개 설명)
위 표보다 이 절이 우선한다.

| 검토 지적 | 반영 |
|---|---|
| **id 재사용**: 같은 R01이 회차마다 다른 이름(`ldx`→`excel-csv-sqlite-explorer`→`tabular-merge-assistant`), 현재 규칙과 표본 이름 겹침 0개. 해시에 term이 없어 stale을 못 잡음 → W3 속성이 실제로는 성립 안 함 | 규칙 해시 = sha256(정렬 JSON{term, must, must_not} + `JUDGE_VERSION`) 앞 12자. 판정은 (id, term) 쌍으로 짝짓고, 표본 term ≠ 규칙 term이면 그 항목은 `term_mismatch`로 제외·표시. 판정식(normalize·judge)을 바꾸면 `JUDGE_VERSION`을 올린다 |
| legacy 포함은 원칙과 충돌 | 기본 제외, `--allow-legacy`로만 (W3 legacy_on 반례와 일치) |
| P1 axes: "자동" 0/594, "사람·사용자가·직접" 5/594 → require로 두면 전부 탈락. require=must, forbid=must_not 중복 | **axes 스키마 폐기.** must 그룹에 선택 이름표만: 그룹을 `{label: executor, any: [...]}`로도 쓸 수 있고 실패 사유가 `누락[executor]`로 나온다. 축을 판정에 넣기 전에 새 solo 표본으로 축 단어 출현율부터 잰다 |
| 80% 만점 경고는 표본 6개로 우연에 흔들림(0.8^6≈26%) | 경고 폐기. **대조 이름(contrast)** 으로 변별을 잰다: 규칙에 선택 필드 `contrasts: [이름…]`(의도와 다르게 읽혀야 할 이름, 예 `auto-merge-tool`). 수집기가 같은 지시문으로 대조 이름 표본도 받고, 보고에 "대조 통과율"을 낸다. 대조가 통과하면 규칙이 느슨한 것 |
| P2: 소문자는 이미 있음, NFKC 효과 0/594. 남은 원인은 띄어쓰기("자동병합" vs "자동 병합")·한영 어휘 | 정규화 = 소문자 + **공백 제거 비교**(규칙 단어·설명 모두 공백 제거 후 부분 문자열). 하이픈·밑줄은 건드리지 않음(회귀 위험). NFKC는 넣지 않음. 한영 누락은 lint 경고 유지. 정규화 전후 결과가 달라지는 행을 회귀 테스트에서 목록으로 출력 |
| P3: solo에서 순서 뒤집기 무의미, 오염된 방식이 기본값 | **solo 기본**, `--list`는 재현용. 순서 뒤집기는 list에서만 |
| P4: timeout(900)은 이미 있음. 진짜 문제는 예외 미처리로 전체 중단 + 끝에 한 번만 저장 | 표본마다 즉시 이어 쓰기(jsonl), 같은 (모델, 이름, 회차)가 있으면 건너뛰고 재개. 모든 예외(타임아웃·JSON 파싱·`[` 없음)를 `failed`/`timed_out` 표본으로 기록하고 계속 |
| P5: cl_run은 이미 stdin. claude_adapter는 출력이 dict가 아니면 output=None인데 succeeded | validate: status≠succeeded 또는 output None 또는 items 누락·빈 설명·id/term 불일치 → failed. 세 백엔드 공통 지시문 원문 하나(`{"items":[…]}` 강제), 모델 id 명시 저장. claude.cmd 실호출 확인됨(sonnet, `auto-merge-tool` 1개, 중괄호 인자 정상) |
| P6: 실패 표본 output=None 처리 미정 | `to_items`는 형식 변환만, 실패 표본은 `[]`가 아니라 None을 돌려 판정에서 "실패 n개"로 셈. 형식 검사는 수집 단계 한 곳 |
| P7-c prompt_sha가 표본마다 다름 | 지시문 원문 해시(`instr_sha`) + mode를 따로 기록 |
| 테스트 6 모순 | 그룹 순서·그룹 안 순서 모두 정렬해서 해시 |
| 누락: 같은 파일 안 id 중복 | 표본 하나 안에 같은 (id, term)이 둘 이상이면 그 표본 항목 `duplicate`로 제외 |

W3 재실행: 해시에 term 포함 = 이름이 바뀌면 버전이 바뀌는 것과 같으므로 `StaleSamples.tla`의 rv 증가가 이름 교체도 표현한다(모델 변경 없음).

## v2.2 — 오독 게이트·부트스트랩·충돌 조회 (2026-11-04, 명명 전담 세션; 수정 프로토콜 절차로 작업)
위 v2.1보다 이 절이 우선한다. 기존 27개 테스트 통과 유지, `JUDGE_VERSION` "2" 유지(아래 근거).

| 사용자 요구(원문 요지) | 반영 |
|---|---|
| "6회 중 1개라도 오독이 있으면 제외하는 것. 다른 이름이 더 적절하다는 것" | 규칙 선택 필드 `misread_as: {분야: [신호어]}`. 설명에 신호가 나오면 실패 사유 `misread:<분야>: <단어>`(분야당 하나). **표본 하나라도 오독이면 `excluded`** — 순위 가중이 아니라 게이트. must_not만으로는 제외하지 않음(분야가 없는 신호). 대조(contrast) 표본은 세지 않음 |
| 수정 프로토콜 "기존안과 후보를 하네스로 비교, 동점은 기존 유지" | `choose()` = `workflow-runner/runner.py choose()` **원문 복사**(sha256 a1156710…0ae4, diff 무차이). 게이트(오독 없음) → 통과율 → 동점은 `baseline: true` 유지 → 둘 다 없으면 id 순 첫째. 표본 0개 이름은 뺌 |
| "boot strap처럼 독립 실험을 반복해서 검증" | 재표본 부트스트랩을 한때 넣었다가 **뺐다**(사용자: "전수 조사해야 하는데 6번을 하나씩 뽑는 것 의미가 없잖아"). 표본은 전수 집계한다. 독립 반복은 **답변자 재실험**(지시문·시드를 바꿔 재수집, `instr_sha`별 집계)과 **평가자 재실험**(같은 답변에 규칙 변형 적용)으로 나눠 확장 지점에 둔다 |
| "너무 많이 소거해서 이름 후보 생성에 한계가 생기면 오독률이 낮은 것들 중에서 골라야지" | `misread_n`(오독이 난 **표본** 수, 분야 수 아님). 제외된 이름에도 `오독률 k/n` 표시. `choose()`: 게이트 통과 후보가 없으면 **예비 선택** — 오독률 최저(비율, 횟수 아님) 이름만 남겨 같은 `_runner_choose`로 통과율 → 기존안 유지. 출력에 `예비 선택:`으로 구분 |
| 오독 0회의 남은 위험 | Wilson 95% 상한을 함께 표시(0/6 → 39%, 0/30 → 11%). 게이트에는 쓰지 않음. 회차를 늘릴지 판단하는 근거 |
| 위험 단어 사전 | `docs/harness/risky_tokens.json`(축적 오독 사례 + s12~s14 실측). `--lint`에서 이름 조각(-·_ 기준, 소문자)이 사전에 있으면 `lint-name:` **경고만**(차단 아님). `engine`·`prep`·`dataset`·`builder`는 사용자가 허용(2026-11-04)했으므로 문구에 명시 |
| 충돌 조회 | `scripts/check_availability.py`: PyPI(PEP 503 정규화)·npm·GitHub(정확 일치, 대소문자 무시). 200→taken, 404→free, 그 외·예외·결과 잘림→**unverified(free로 치지 않음)**. 네트워크는 주입 가능한 fetch로만(테스트는 오프라인). 이 PC는 Bash 네트워크가 막혀 PowerShell에서 실행 |

### JUDGE_VERSION을 올리지 않은 근거
`judge()` 본문은 바뀌었지만 `misread_as`가 없는 규칙에서는 반환값이 바이트 단위로 같다(`tests/test_check_terms_gate.py::test_judge_unchanged_without_misread`, `test_hash_unchanged_without_misread`). 올리면 이미 받은 v2 표본이 전부 stale로 떨어져 하네스 소유 세션의 제약 2와 충돌한다. 반대 논거(판정식이 바뀌면 올리는 것이 원칙)도 타당하므로, `misread_as`가 있는 규칙은 해시에 그 값이 들어가 자연히 새 표본만 쓰인다.

### 알려진 한계
- 오독 판정은 공백 제거 부분 문자열이라 **부정문("SQL JOIN과는 다르다")과 단어 경계("ON 절차"→"on절")도 걸린다.** 의도된 보수적 동작(LLM 판정 금지). 제외된 이름은 `근거:`로 걸린 설명 원문을 보여 사람이 오탐을 확인한다. 신호어는 짧은 흔한 말보다 분야를 특정하는 말(예: "SQL의 MERGE 문", "ON 조건절")로 쓴다.
- 실측: `repo_names_v11`(12개)에 misread_as(SQL·git·빌더 패턴·실행 엔진)를 붙이자 11개 제외, 남은 1개도 통과 1/6 → 이 후보 집합은 폐기.
- 사용자가 말한 명명 절차(목적·조건 정의 → 사람 행동의 명사-술어 쌍 1~3개 → 이름; 웹 검색·적대 검증·맥락 관리)는 **이 하네스 범위 밖**이다. 하네스는 후보가 나온 뒤의 채점·게이트·선택만 맡는다. 절차는 스킬로 따로 만든다(미작성).
- 기준선 대비 실측: 8개 규칙 파일(이름 15·12·6·15·12·10·16·12 = 98개) × 기존 판정기(f60ed11) vs 새 판정기 → 파일마다 판정 줄 수 같고 다른 줄 0, 새 쪽에 `선택:` 줄만 추가(`scratchpad/reg`).

### 평가자 맥락 (사용자: "평가자는 목적, 차별점, 역할 등 답변자보다 유리한 context를 갖고 있어야")
답변자는 이름만 받는다(`collect_samples.py`는 `id`·`term`만 보냄). 평가자(규칙과 그 작성자)는 전부 안다. 이 비대칭이 검증의 전제다.
구현(v2.2) 규칙 선택 필드 — 판정·해시에 쓰지 않고 판정 단어의 근거로만 남긴다(이미 받은 표본 보호):
`purpose`(달성할 목적·조건), `human_actions`(사람 행동 [명사, 술어] 1~3쌍), `distinct_from`({혼동 금지 이웃 개념: 그것을 잡는 `misread_as` 분야 또는 `contrasts` 이름}), `role`(시스템 안 역할).
`--lint`의 `lint-context:` 경고: purpose 비었음 / human_actions 형식 / distinct_from이 가리키는 분야·대조 이름이 없음(**근거 없음**) / misread_as 분야가 distinct_from에 없음(**출처 없음**). 맥락 필드를 하나도 안 쓴 옛 규칙은 건너뛴다(기존 12개 파일 경고 0).
누출 방지: `tests/test_check_terms_context.py::test_context_never_sent_to_answerer`가 실제 `collect()`로 답변자 입력이 `id`·`term`뿐임을 고정한다.

예(이 하네스 저장소 이름, 임시 `name-semantic-harness`):
```json
{"id": "H01", "term": "name-semantic-harness",
 "purpose": "이름 후보가 처음 보는 사람에게 목적·역할·차별점대로 읽히는지 확인해, 오독이 있는 후보를 걸러 낸다",
 "human_actions": [["후보", "고른다"], ["오독", "확인한다"], ["이름", "확정한다"]],
 "distinct_from": {"네이밍 컨벤션 린터": "naming-convention-linter", "무작위 이름 생성기": "random-name-generator", "DNS 이름 조회": "DNS"},
 "role": "명명 절차의 검증 단계(후보 생성·웹 검색은 범위 밖)",
 "must": [{"label": "이름", "any": ["이름", "명칭", "식별자", "name"]}, {"label": "의미", "any": ["의미", "뜻", "해석", "의도", "semantic"]}, {"label": "평가", "any": ["평가", "검증", "확인", "테스트"]}],
 "misread_as": {"DNS": ["dns", "도메인 이름", "네임서버"]},
 "contrasts": ["naming-convention-linter", "random-name-generator"]}
```
