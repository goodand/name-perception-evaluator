/-!
# 이름 검증 하네스의 판정·선택 모델

원본: `scripts/check_terms.py` — `judge`, `misread_hits`, `score`, `_runner_choose`, `choose`, `overlap`;
`scripts/prompt_check.py` — `check`.

추상화: 설명문(텍스트)을 "그 안에 들어 있는 신호어 집합"으로 본다(`norm`한 부분 문자열 포함 = 집합 소속).
비율 비교는 분모를 곱해 자연수로 한다(파이썬의 `passed/total` 실수 비교와 같은 순서, 0 나누기 없음).
-/
namespace NameHarness

abbrev Sig := String   -- 정규화된 신호어

/-- 설명문: 들어 있는 신호어 목록. -/
abbrev Text := List Sig

/-- 규칙(브리프에서 만든 한 이름의 조건). `must`는 묶음(any) 목록, `misread_as`는 (분야, 신호어들). -/
structure Rule where
  id        : String
  term      : String
  must      : List (List Sig)
  mustNot   : List Sig
  misreadAs : List (String × List Sig)   -- 분야 이름순으로 정렬돼 있다고 본다
  baseline  : Bool := false
  deriving Repr, DecidableEq

def hasAny (t : Text) (ws : List Sig) : Bool := ws.any (· ∈ t)

/-- src: check_terms.py `misread_hits` — 분야당 최대 1개, 분야 이름순. -/
def misreadHits (t : Text) (r : Rule) : List String :=
  (r.misreadAs.filter fun (_, ws) => hasAny t ws).map (·.1)

/-- src: check_terms.py `judge` — 모든 must 묶음 충족 ∧ must_not 없음 ∧ 오독 신호 없음. -/
def judge (t : Text) (r : Rule) : Bool :=
  r.must.all (hasAny t) && !(hasAny t r.mustNot) && (misreadHits t r).isEmpty

/-- 표본 하나(봉투 + 항목 하나). `stale`: rule_hash 불일치, `legacy`: 옛 형식, `contrast`: 대조 이름. -/
structure Sample where
  ruleId   : String
  term     : String
  text     : Text
  contrast : Bool := false
  stale    : Bool := false
  legacy   : Bool := false
  deriving Repr, DecidableEq

/-- src: check_terms.py `score` 의 한 규칙 집계. -/
structure Stat where
  term      : String
  pass      : Nat
  n         : Nat
  misreadN  : Nat
  excluded  : Bool
  baseline  : Bool
  deriving Repr, DecidableEq

/-- 집계에 들어가는 표본: 같은 규칙·같은 이름(대조 아님)·stale/legacy 아님(옵션 없을 때). -/
def counted (r : Rule) (allowStale allowLegacy : Bool) (s : Sample) : Bool :=
  s.ruleId == r.id && !s.contrast && s.term == r.term
    && (allowStale || !s.stale) && (allowLegacy || !s.legacy)

def score (r : Rule) (xs : List Sample) (allowStale := false) (allowLegacy := false) : Stat :=
  let ss := xs.filter (counted r allowStale allowLegacy)
  let mis := ss.filter fun s => !(misreadHits s.text r).isEmpty
  { term := r.term, pass := (ss.filter fun s => judge s.text r).length, n := ss.length,
    misreadN := mis.length, excluded := !mis.isEmpty, baseline := r.baseline }

/-- `passed/total` 비교: a ≥ b ⇔ a.pass*b.n ≥ b.pass*a.n (n>0에서 실수 비교와 같다). -/
def rateGE (a b : Stat) : Bool := a.pass * b.n ≥ b.pass * a.n
def rateEQ (a b : Stat) : Bool := a.pass * b.n == b.pass * a.n

/-- 키 (passed/total, baseline) 로 `a`가 `b`보다 엄격히 큰가(파이썬 max의 튜플 비교). -/
def keyGT (a b : Stat) : Bool :=
  (rateGE a b && !rateEQ a b) || (rateEQ a b && a.baseline && !b.baseline)

/-- 파이썬 `max(iterable, key)`: 키가 최대인 **첫** 원소. -/
def pyMax : List Stat → Option Stat
  | [] => none
  | x :: xs => some (xs.foldl (fun best y => if keyGT y best then y else best) x)

/-- src: `_runner_choose` — 게이트 통과자 중 (통과율, baseline) 최대, 동점은 먼저 온 것(id 순). -/
def runnerChoose (gate : Stat → Bool) (xs : List Stat) : Option String :=
  (pyMax (xs.filter gate)).map (·.term)

/-- 오독률 비교 a ≤ b ⇔ a.misreadN*b.n ≤ b.misreadN*a.n. -/
def misLE (a b : Stat) : Bool := a.misreadN * b.n ≤ b.misreadN * a.n

/-- 오독률 최저인 것들(비율 기준). -/
def lowestMisread (xs : List Stat) : List Stat :=
  xs.filter fun a => xs.all (misLE a)

/-- src: check_terms.py `choose`. 입력은 id 순 정렬된 집계. 결과: (선택, 예비 선택 여부). -/
def chooseSampled (sampled : List Stat) : Option String × Bool :=
  match runnerChoose (fun s => !s.excluded) sampled with
  | some t => (some t, false)
  | none => (runnerChoose (fun _ => true) (lowestMisread sampled), true)

def choose (xs : List Stat) : Option String × Bool :=
  match xs.filter (·.n > 0) with
  | [] => (none, false)
  | sampled => chooseSampled sampled

/-- src: check_terms.py `overlap` — 이름 A의 설명이 B(≠A, must 있음)의 must를 모두 채운 횟수. -/
def overlapWith (rules : List Rule) (a : Rule) (xs : List Sample) : List (String × Nat) :=
  let ss := xs.filter (counted a false false)
  (rules.filter fun b => b.id != a.id && !b.must.isEmpty).map fun b =>
    (b.id, (ss.filter fun s => b.must.all (hasAny s.text)).length)

/-- 안정 삽입 정렬(구조 재귀라 `decide`가 계산할 수 있다). `le a b`가 참이면 a가 앞. -/
def insertBy {α} (le : α → α → Bool) (x : α) : List α → List α
  | [] => [x]
  | y :: ys => if le y x then y :: insertBy le x ys else x :: y :: ys

def insertionSort {α} (le : α → α → Bool) : List α → List α
  | [] => []
  | x :: xs => insertBy le x (insertionSort le xs)

/-- src: prompt_check.py `check` — 사전에 있는 단어가 지시문에 있으면 (단어, 사전) 한 번씩,
지시문에서 처음 나온 자리 순(`sorted(key=text.find)`; 안정 정렬이라 같은 자리는 사전 순서 유지). -/
def promptCheck (dicts : List (String × List Sig)) (prompt : Text) : List (Sig × String) :=
  let hits := (dicts.flatMap fun (d, ws) => ws.map (·, d)).filter (fun (w, _) => w ∈ prompt)
    |>.foldl (fun acc (w, d) => if acc.any (·.1 == w) then acc else acc ++ [(w, d)]) []
  insertionSort (fun a b => prompt.idxOf a.1 ≤ prompt.idxOf b.1) hits

/-- src: check_terms.py `MAX_KEYWORDS` -/
def MAX_KEYWORDS : Nat := 3

/-- src: check_terms.py `lint_names` — 경고를 (규칙 id, 종류) 로 센다.
이름을 `-`·`_`로 나눠 소문자로 만드는 일(`re.split`·`lower`)은 `norm`처럼 모델 밖: 입력은 (id, 조각 목록). -/
inductive Warn | risky (tok field : String) | length (k : Nat)
  deriving Repr, DecidableEq

def isLengthWarn : String × Warn → Bool
  | (_, Warn.length _) => true
  | _ => false

def riskyWarns (id : String) (toks : List String) (risky : List (String × String)) : List (String × Warn) :=
  toks.filterMap fun t => (risky.lookup t).map fun f => (id, Warn.risky t f)

def lengthWarns (id : String) (toks : List String) : List (String × Warn) :=
  if toks.length > MAX_KEYWORDS then [(id, Warn.length toks.length)] else []

def lintNames (rules : List (String × List String)) (risky : List (String × String)) : List (String × Warn) :=
  rules.flatMap fun (id, toks) => riskyWarns id toks risky ++ lengthWarns id toks

/-- src: check_terms.py `wilson_upper` — 실수 제곱근은 모델 밖. 정확히 말할 수 있는 성질만:
n = 0 이면 1, 그 외는 비율 k/n보다 크거나 같고 1 이하. (여기서는 n=0 분기만 모델.) -/
def wilsonUpperIsOne (n : Nat) : Bool := n == 0

end NameHarness
