/-!
# 낱말 점검 상태 기계 모델 — `scripts/search_words.py` `review()`

상태: 검색자가 낸 낱말 `names`, 받아들인 항목 `acc`(낱말 → 결정), 회차 `round`, 한도 `maxRounds`.
제출(decisions)을 한 건씩 검사해 오류·새로 받아들인 항목을 모으고, 상태를 갱신한다.

추상화: 파이썬의 `keep`이 bool이 아닌 경우는 `keep = none`, `str(note).strip()`이 비었는지는 `noteOk : Bool`.
낱말은 소문자화된 뒤의 값으로 본다(`str(d.get("word","")).lower()`).
-/
namespace NameHarness.Review

def REASONS : List String := ["뜻이 다름", "너무 넓음", "개발 용어 경고", "기타"]

/-- 받아들인 결정. 파이썬은 keep=True면 reason/note를 저장하지 않는다 → `reason = none`. -/
structure Acc where
  keep   : Bool
  reason : Option String
  noteOk : Bool
  deriving Repr, DecidableEq

/-- 외부 에이전트의 결정 한 건. -/
structure Dec where
  word   : String
  keep   : Option Bool
  reason : Option String
  noteOk : Bool
  deriving Repr, DecidableEq

abbrev AccMap := List (String × Acc)

def lookup (acc : AccMap) (w : String) : Option Acc := (acc.find? (·.1 == w)).map (·.2)

/-- 결정 한 건의 오류(없으면 none). src: search_words.py review 78-89. -/
def decError (names : List String) (acc : AccMap) (seen : List String) (d : Dec) : Option String :=
  if d.word ∉ names then some "검색자가 내지 않은 낱말"
  else if d.word ∈ seen then some "같은 낱말을 두 번 냄"
  else match d.keep with
    | none => some "keep은 true 또는 false"
    | some keep =>
      if !keep && d.reason.all (· ∉ REASONS) then some "뺄 때 이유는 … 중 하나"
      else if !keep && d.reason == some "기타" && !d.noteOk then some "기타는 note 필수"
      else match lookup acc d.word with
        | some a => if (a.keep, a.reason) != (keep, d.reason) then some "이미 받아들인 항목은 바꿀 수 없음" else none
        | none => none

/-- 받아들일 모양으로 바꾼다(keep=True면 reason·note 없음). src: review 94. -/
def toAcc (keep : Bool) (d : Dec) : Acc :=
  if keep then ⟨true, none, false⟩ else ⟨false, d.reason, d.noteOk⟩

structure Pass where
  errors : List (String × String)   -- (word, error)
  ok     : AccMap                   -- 이번에 새로 받아들인 항목
  deriving Repr

/-- 제출 전체를 한 건씩 검사. src: review 75-94. -/
def pass (names : List String) (acc : AccMap) : List Dec → List String → Pass
  | [], _ => ⟨[], []⟩
  | d :: ds, seen =>
    let rest := pass names acc ds (d.word :: seen)
    match decError names acc seen d with
    | some e => ⟨(d.word, e) :: rest.errors, rest.ok⟩
    | none =>
      match lookup acc d.word, d.keep with
      | none, some k => ⟨rest.errors, (d.word, toAcc k d) :: rest.ok⟩
      | _, _ => rest

structure State where
  names     : List String
  acc       : AccMap
  round     : Nat
  maxRounds : Nat
  deriving Repr

inductive Result where
  | ok (keep dropped : List String)
  | rejected (round : Nat) (errors : List (String × String)) (missing fixOnly : List String)
  | stopped (errors : List (String × String)) (missing : List String)
  deriving Repr, DecidableEq

def Result.isOk : Result → Bool
  | .ok _ _ => true
  | _ => false

/-- src: review 95-106. 돌려주는 값은 (새 상태, 결과). `acc.update(ok)`는 `acc ++ ok`(ok의 낱말은 acc에 없다: `pass_ok_fresh`). -/
def review (s : State) (ds : List Dec) : State × Result :=
  let p := pass s.names s.acc ds []
  let acc' := s.acc ++ p.ok
  let errWords := p.errors.map (·.1)
  let missing := s.names.filter fun w => (lookup acc' w).isNone && w ∉ errWords
  if p.errors.isEmpty && missing.isEmpty then
    let keep := s.names.filter fun w => (lookup acc' w).map (·.keep) == some true
    let dropped := s.names.filter fun w => !((lookup acc' w).map (·.keep) == some true)
    ({ s with acc := acc' }, .ok keep dropped)
  else
    let r := s.round + 1
    let s' := { s with acc := acc', round := r }
    if r > s.maxRounds then (s', .stopped p.errors missing)
    else (s', .rejected r p.errors missing (errWords ++ missing))

/-- 받아들인 항목의 모양 조건: 뺀 항목은 REASONS 안의 이유, 기타면 note 있음. -/
def Acc.wf (a : Acc) : Prop :=
  a.keep = false → (∃ r, a.reason = some r ∧ r ∈ REASONS) ∧ (a.reason = some "기타" → a.noteOk = true)

def AccMap.wf (acc : AccMap) : Prop := ∀ w a, lookup acc w = some a → a.wf

end NameHarness.Review
