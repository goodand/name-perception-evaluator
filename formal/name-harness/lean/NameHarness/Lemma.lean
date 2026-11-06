/-!
# 두 단계 금지어 검사 모델 — `scripts/prompt_check.py` `check(text, words, level="all")` (2026-11-06 판)

- 글은 이미 `tokens`(소문자 [a-z]+ 낱말 목록)로 쪼갠 것을 받는다. 토큰화는 `../lemma_diff.py`가 파이썬으로 대조한다.
- 표제어 `lemma : String → String`은 임의의 함수(매개변수). simplemma 2.0.0은 사전 표+규칙이라 결정적이다.
- 사전 항목은 (사전 이름, 낱말 w, w의 토큰). 한국어 항목은 원문 부분 일치라 `ko`로 구분한다.
- 결과 정렬(`sorted(key=low.find(...))`)은 순열일 뿐이라 아래 성질(소속·중복 없음)에 영향이 없어 뺐다.
-/
namespace NameHarness.Lemma

inductive Level where
  | block
  | warn
  deriving Repr, DecidableEq

structure Entry where
  dict : String
  w    : String          -- w.lower().strip()
  toks : List String     -- tokens(w)
  ko   : Bool := false   -- 한글이 든 낱말(부분 일치)
  deriving Repr, DecidableEq

/-- `a`가 `b` 안에 들어 있다(파이썬 `a in b`). -/
def inStr (a b : List Char) : Bool :=
  (List.range (b.length + 1)).any fun i => a.isPrefixOf (b.drop i)

/-- `any(lem[i:i+len(wl)] == wl for i in range(len(lem)-len(wl)+1))` -/
def contig (lem wl : List String) : Bool :=
  (List.range (lem.length + 1 - wl.length)).any fun i => (lem.drop i).take wl.length == wl

/-- 항목 하나의 판정. `raw`는 소문자 원문(한국어 부분 일치용). src: check 54-71. -/
def classify (lemma : String → String) (raw : List Char) (toks : List String) (e : Entry) : Option Level :=
  if e.w.isEmpty then none
  else if e.ko then (if inStr e.w.toList raw then some .block else none)
  else
    let wl := e.toks.map lemma
    if wl.isEmpty then none
    else if contig (toks.map lemma) wl then some .block
    else if wl.length == 1 && decide (e.w.length ≥ 3) && toks.any (fun t => inStr e.w.toList t.toList) then some .warn
    else none

/-- 사전 순서대로 보며 처음 걸린 것만 남긴다(`seen`). src: check 51-71, level="all". -/
def go (lemma : String → String) (raw : List Char) (toks : List String) : List String → List Entry → List (String × Level)
  | _, [] => []
  | seen, e :: es =>
    if e.w ∈ seen then go lemma raw toks seen es
    else match classify lemma raw toks e with
      | some l => (e.w, l) :: go lemma raw toks (e.w :: seen) es
      | none => go lemma raw toks seen es

def check (lemma : String → String) (raw : List Char) (toks : List String) (es : List Entry) : List (String × Level) :=
  go lemma raw toks [] es

end NameHarness.Lemma
