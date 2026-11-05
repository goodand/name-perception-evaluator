import NameHarness.System
/-!
차분 테스트용 실행 파일. 고정 시드 LCG로 입력을 만들어 모델 결과를 한 줄씩 찍는다.
같은 LCG를 `../diff_test.py`가 파이썬으로 재현해 `check_terms.py`·`prompt_check.py` 결과와 비교한다.
신호어는 소문자 한 글자(a~j): 파이썬 `norm(w) in text`(부분 문자열)와 집합 소속이 일치한다.
-/
open NameHarness

structure Rng where s : Nat

def Rng.next (r : Rng) : Nat × Rng :=
  let s := (r.s * 1103515245 + 12345) % 2147483648
  (s / 65536, ⟨s⟩)

def Rng.below (r : Rng) (n : Nat) : Nat × Rng :=
  let (x, r) := r.next
  (x % n, r)

def letters : List String := ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

/-- 길이 k, 중복 없는 글자 집합(정렬). -/
def pickSet (r : Rng) (k : Nat) : List String × Rng :=
  let rec go (r : Rng) (k : Nat) (acc : List String) : List String × Rng :=
    match k with
    | 0 => (acc, r)
    | k + 1 =>
      let (i, r) := r.below 10
      let w := letters[i]!
      go r k (if w ∈ acc then acc else acc ++ [w])
  let (xs, r) := go r k []
  (letters.filter (· ∈ xs), r)

def mkRule (r : Rng) (id term : String) : Rule × Rng :=
  let (nm, r) := r.below 3                      -- must 묶음 0~2개
  let rec musts (r : Rng) (n : Nat) (acc : List (List String)) : List (List String) × Rng :=
    match n with
    | 0 => (acc, r)
    | n + 1 => let (k, r) := r.below 3; let (ws, r) := pickSet r (k + 1); musts r n (acc ++ [ws])
  let (must, r) := musts r nm []
  let (kn, r) := r.below 2
  let (mustNot, r) := pickSet r kn
  let (nf, r) := r.below 3                      -- 분야 0~2개(이름순 F0 < F1)
  let rec fields (r : Rng) (n : Nat) (acc : List (String × List String)) : List (String × List String) × Rng :=
    match n with
    | 0 => (acc, r)
    | n + 1 => let (k, r) := r.below 2; let (ws, r) := pickSet r (k + 1); fields r n (acc ++ [(s!"F{acc.length}", ws)])
  let (mis, r) := fields r nf []
  let (b, r) := r.below 4
  ({ id, term, must, mustNot, misreadAs := mis, baseline := b == 0 }, r)

def showText (t : List String) : String := String.intercalate "" t

def caseScore (r : Rng) (i : Nat) : String × Rng :=
  let (rule, r) := mkRule r "R" "t"
  let (n, r) := r.below 6
  let rec samples (r : Rng) (n : Nat) (acc : List Sample) : List Sample × Rng :=
    match n with
    | 0 => (acc, r)
    | n + 1 =>
      let (k, r) := r.below 5; let (t, r) := pickSet r k
      let (flags, r) := r.below 8
      samples r n (acc ++ [{ ruleId := "R", term := "t", text := t, contrast := flags == 1,
                             stale := flags == 2, legacy := flags == 3 }])
  let (xs, r) := samples r n []
  let s := score rule xs
  let o := overlapWith [rule, { rule with id := "Q", term := "q" }] rule xs
  let line := s!"score {i} must={repr rule.must} mustNot={repr rule.mustNot} mis={repr rule.misreadAs} base={rule.baseline} " ++
    s!"xs={repr (xs.map fun x => (showText x.text, x.contrast, x.stale, x.legacy))} " ++
    s!"=> pass={s.pass} n={s.n} misN={s.misreadN} exc={s.excluded} ov={repr o}"
  (line, r)

def caseChoose (r : Rng) (i : Nat) : String × Rng :=
  let (n, r) := r.below 4
  let rec stats (r : Rng) (n : Nat) (acc : List Stat) : List Stat × Rng :=
    match n with
    | 0 => (acc, r)
    | n + 1 =>
      let (tot, r) := r.below 7; let (p, r) := r.below (tot + 1); let (m, r) := r.below (tot + 1)
      let (e, r) := r.below 3; let (b, r) := r.below 3
      let exc := if m > 0 then true else e == 0        -- 파이썬 score와 같이 misN>0 → 제외; 가끔 misN=0인데 제외도 섞음
      stats r n (acc ++ [{ term := s!"c{acc.length}", pass := p, n := tot, misreadN := m, excluded := exc, baseline := b == 0 }])
  let (xs, r) := stats r (n + 1) []
  let (sel, fb) := choose xs
  (s!"choose {i} xs={repr (xs.map fun s => (s.pass, s.n, s.misreadN, s.excluded, s.baseline))} => sel={repr sel} fb={fb}", r)

def casePrompt (r : Rng) (i : Nat) : String × Rng :=
  let (k1, r) := r.below 4; let (d1, r) := pickSet r k1
  let (k2, r) := r.below 4; let (d2, r) := pickSet r k2
  let (k3, r) := r.below 8; let (t, r) := pickSet r k3
  let hits := promptCheck [("general", d1), ("leaky", d2)] t
  (s!"prompt {i} general={repr d1} leaky={repr d2} text={repr t} => {repr hits}", r)

def main : IO Unit := do
  let mut r : Rng := ⟨20261105⟩
  for i in [0:200] do
    let (l, r') := caseScore r i; IO.println l; r := r'
  for i in [0:200] do
    let (l, r') := caseChoose r i; IO.println l; r := r'
  for i in [0:100] do
    let (l, r') := casePrompt r i; IO.println l; r := r'
