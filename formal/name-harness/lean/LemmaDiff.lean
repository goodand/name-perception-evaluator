import NameHarness.Lemma
/-! 두 단계 검사 차분 테스트 입력·출력을 찍는다(`../lemma_diff.py`). 표제어는 작은 표(`LEM`)로 고정한다. -/
open NameHarness.Lemma

structure Rng where s : Nat
def Rng.below (r : Rng) (n : Nat) : Nat × Rng :=
  let s := (r.s * 1103515245 + 12345) % 2147483648
  ((s / 65536) % n, ⟨s⟩)

def VOCAB : List String := ["ab", "abs", "abc", "b", "bab", "cab", "cabs", "test", "tests", "pytest", "contest", "tested"]
def lem (w : String) : String :=
  if w == "abs" then "ab" else if w == "cabs" then "cab" else if w == "tests" || w == "tested" then "test" else w

def pick (r : Rng) (n : Nat) : List String × Rng :=
  match n with
  | 0 => ([], r)
  | n + 1 => let (i, r) := r.below VOCAB.length; let (xs, r) := pick r n; (VOCAB[i]! :: xs, r)

def showL (xs : List (String × Level)) : String :=
  reprStr (xs.map fun (w, l) => (w, match l with | .block => "block" | .warn => "warn"))

def main : IO Unit := do
  let mut r : Rng := ⟨20261106⟩
  for i in [0:400] do
    let (nt, r1) := r.below 6; let (toks, r2) := pick r1 nt
    let (ne, r3) := r2.below 4
    let mut es : List Entry := []
    let mut rr := r3
    for _ in [0:ne + 1] do
      let (k, ra) := rr.below 2; let (ws, rb) := pick ra (k + 1)
      es := es ++ [{ dict := "d", w := String.intercalate " " ws, toks := ws }]
      rr := rb
    r := rr
    IO.println s!"lem {i} toks={repr toks} words={repr (es.map (·.w))} => {showL (check lem [] toks es)}"
