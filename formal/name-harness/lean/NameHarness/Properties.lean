import NameHarness.System
/-!
# 테스트 명세의 동시 충족 가능성

`tests/test_check_terms_gate.py`, `tests/test_overlap.py`, `tests/test_prompt_check.py`의 단언을
하나의 모델(`System.lean`)에 대한 정리로 옮겼다. 이 파일이 컴파일되면(sorry 0) 그 단언들은
**한 구현으로 동시에 만족된다** — 즉 서로 모순이 없다. 각 정리의 이름은 원본 테스트 함수 이름이다.
증명은 `decide`(유한 계산)이고, 일반 성질(모든 입력)은 마지막 절에 있다.
-/
namespace NameHarness

-- 공통 픽스처 (test_check_terms_gate.py BASE·MIS)
def BASE : Rule := { id := "R01", term := "merge-desk", must := [["표", "excel"], ["결정", "판단"]],
                     mustNot := ["자동병합"], misreadAs := [] }
def MIS : Rule := { BASE with misreadAs := [("SQL", ["on절", "join"]), ("git", ["브랜치"])] }

def smp (r : Rule) (t : Text) (contrast := false) (stale := false) : Sample :=
  { ruleId := r.id, term := r.term, text := t, contrast, stale }

/-! ## judge (test_judge_*) -/

theorem test_judge_unchanged_without_misread :
    judge ["표", "자동병합", "결정"] BASE = false ∧ judge ["표", "결정"] BASE = true := by decide

theorem test_judge_misread_reason :
    judge ["표", "join", "결정"] MIS = false ∧ misreadHits ["표", "join", "결정"] MIS = ["SQL"] := by decide

theorem test_misread_one_reason_per_field :
    misreadHits ["표", "join", "on절", "결정"] MIS = ["SQL"] := by decide

theorem test_misread_reason_exact_and_per_field :
    misreadHits ["표", "join", "브랜치", "결정"] MIS = ["SQL", "git"] := by decide

/-! ## score: 오독 게이트 (test_score_*, test_*_excluded) -/

def good : Sample := smp MIS ["표", "결정"]

theorem test_score_counts_misread_and_excludes :
    let s := score MIS (List.replicate 5 good ++ [smp MIS ["표", "브랜치", "결정"]])
    (s.pass, s.n, s.misreadN, s.excluded) = (5, 6, 1, true) := by decide

theorem test_not_excluded_without_misread :
    (score MIS (List.replicate 6 good)).excluded = false := by decide

theorem test_must_not_alone_does_not_exclude :
    let s := score MIS (smp MIS ["표", "자동병합", "결정"] :: List.replicate 5 good)
    (s.pass, s.excluded) = (5, false) := by decide

theorem test_contrast_misread_not_counted :
    let s := score MIS [smp MIS ["git", "브랜치", "자동병합"] (contrast := true)]
    (s.misreadN, s.excluded, s.n) = (0, false, 0) := by decide

theorem test_misread_n_counts_samples_not_fields :
    (score MIS (smp MIS ["표", "join", "브랜치", "결정"] :: List.replicate 5 good)).misreadN = 1 := by decide

theorem test_one_in_thirty_still_excluded :
    (score MIS (List.replicate 29 good ++ [smp MIS ["표", "join", "결정"]])).excluded = true := by decide

theorem test_stale_misread_not_counted :
    let st := smp MIS ["표", "join", "결정"] (stale := true)
    (score MIS [st]).excluded = false ∧ (score MIS [st] (allowStale := true)).excluded = true := by decide

theorem test_score_carries_baseline :
    let r : Rule := { MIS with baseline := true }
    let s := score r [smp r ["표", "결정"]]
    s.baseline = true ∧ choose [s] = (some "merge-desk", false) := by decide

/-! ## choose: 게이트 → 통과율 → baseline → id 순, 예비 선택 (test_choose_*) -/

/-- `_res(a=(pass, n, excluded, baseline, misread_n))` -/
def st (term : String) (pass n : Nat) (excluded : Bool) (baseline := false) (misreadN : Option Nat := none) : Stat :=
  { term, pass, n, excluded, baseline, misreadN := misreadN.getD (if excluded then 1 else 0) }

theorem test_choose_skips_excluded :
    (choose [st "a" 6 6 true, st "b" 5 6 false]).1 = some "b" := by decide

theorem test_choose_ties_keep_baseline :
    (choose [st "a" 6 6 false, st "b" 6 6 false true]).1 = some "b" ∧
    (choose [st "a" 6 6 false true, st "b" 6 6 false]).1 = some "a" := by decide

theorem test_choose_fallback_lowest_misread_rate_when_all_excluded :
    choose [st "a" 6 6 true false (some 3), st "b" 4 6 true false (some 1), st "c" 6 6 true false (some 2)]
      = (some "b", true) := by decide

theorem test_choose_fallback_then_pass_rate_then_baseline :
    (choose [st "a" 3 6 true false (some 1), st "b" 5 6 true false (some 1), st "c" 6 6 true false (some 2)]).1
      = some "b" ∧
    (choose [st "a" 5 6 true false (some 1), st "b" 5 6 true true (some 1)]).1 = some "b" := by decide

theorem test_choose_fallback_uses_rate_not_count :
    (choose [st "a" 6 6 true false (some 1), st "b" 20 30 true false (some 1)]).1 = some "b" := by decide

theorem test_choose_normal_is_not_fallback :
    choose [st "a" 6 6 true false (some 1), st "b" 3 6 false] = (some "b", false) := by decide

theorem test_choose_ignores_unsampled :
    (choose [st "a" 0 0 false, st "b" 3 6 false]).1 = some "b" := by decide

theorem test_choose_tie_without_baseline_is_first_id :
    (choose [st "a" 6 6 false, st "b" 6 6 false]).1 = some "a" := by decide

/-- 수정 프로토콜 원문 시험(workflow-runner tests_runner.test_comparison_ties_keep_baseline)과 같은 모양. -/
theorem runner_ties_keep_baseline :
    runnerChoose (fun _ => true) [st "new" 6 6 false, st "old" 6 6 false true] = some "old" := by decide

/-! ## overlap (test_overlap.py) -/

def TARGET : Rule := { id := "S01", term := "target", must := [["대상"]], mustNot := [], misreadAs := [] }
def WANTS  : Rule := { id := "S02", term := "wants",  must := [["원하는", "목표"]], mustNot := [], misreadAs := [] }
def ROLE   : Rule := { id := "S03", term := "role",   must := [["역할"]], mustNot := [], misreadAs := [] }
def SLOTS : List Rule := [TARGET, WANTS, ROLE]
def slotSamples : List Sample :=
  [smp TARGET ["목표", "대상"], smp TARGET ["다루는", "대상"], smp WANTS ["원하는", "상태"], smp ROLE ["맡은", "역할"]]

theorem test_overlap_counts_other_names_must :
    overlapWith SLOTS TARGET slotSamples = [("S02", 1), ("S03", 0)] ∧
    overlapWith SLOTS WANTS slotSamples = [("S01", 0), ("S03", 0)] ∧
    overlapWith SLOTS ROLE slotSamples = [("S01", 0), ("S02", 0)] := by decide

theorem test_overlap_skips_stale_and_rules_without_must :
    overlapWith SLOTS TARGET [smp TARGET ["목표", "대상"] (stale := true)] = [("S02", 0), ("S03", 0)] ∧
    (let x : Rule := { id := "S04", term := "x", must := [], mustNot := [], misreadAs := [] }
     overlapWith (SLOTS ++ [x]) TARGET [smp TARGET ["아무"]] = [("S02", 0), ("S03", 0)]) := by decide

/-! ## prompt_check (test_prompt_check.py) -/

def DICTS : List (String × List Sig) :=
  [("general", ["software", "code", "코드"]), ("leaky", ["json", "tool"])]

theorem test_check_finds_words_from_both_dicts :
    promptCheck DICTS ["return", "json", "for", "this", "software", "tool", "코드", "이름"]
      = [("json", "leaky"), ("software", "general"), ("tool", "leaky"), ("코드", "general")] ∧  -- 지시문 등장 순
    promptCheck DICTS ["이름", "하나가", "주어집니다"] = [] := by decide

/-! ## lint_names (test_lint_names*) — 조각 나누기·소문자화는 모델 밖이라 조각 목록을 직접 준다 -/

def RISKY : List (String × String) := [("engine", "실행·판정 엔진"), ("decision", "의사결정 테이블")]

theorem test_lint_names :
    let w := lintNames [("R01", ["decision", "tabular", "engine"]), ("R02", ["name", "semantic", "harness"])] RISKY
    w.length = 2 ∧ w.all (·.1 == "R01") = true := by decide

theorem test_lint_names_length :
    (lintNames [("A", ["name", "misread", "check", "harness"]), ("B", ["name", "semantic", "harness"]),
                ("C", ["tabular", "compare", "engine"]), ("D", ["table", "join", "condition", "x"])] []).map (·.1)
      = ["A", "D"] := by decide

/-- `test_lint_names_case_insensitive`는 소문자화(모델 밖)에 대한 것: 소문자 조각이면 걸린다는 부분만. -/
theorem test_lint_names_case_insensitive_core :
    (lintNames [("R01", ["decision", "engine"])] [("engine", "x")]).isEmpty = false := by decide

theorem test_wilson_upper_empty : wilsonUpperIsOne 0 = true := by decide

/-- 위험 단어 경고에는 길이 경고가 섞이지 않는다. -/
theorem riskyWarns_no_length (id : String) (toks : List String) (risky : List (String × String)) :
    (riskyWarns id toks risky).any isLengthWarn = false := by
  rw [List.any_eq_false]
  intro w hw
  obtain ⟨t, _, ht⟩ := List.mem_filterMap.mp hw
  cases hx : risky.lookup t <;> simp [hx] at ht
  subst ht; simp [isLengthWarn]

/-- 길이 경고는 조각이 MAX_KEYWORDS개를 넘을 때만 나온다(모든 입력). -/
theorem length_warn_iff (id : String) (toks : List String) (risky : List (String × String)) :
    (lintNames [(id, toks)] risky).any isLengthWarn = decide (toks.length > MAX_KEYWORDS) := by
  simp only [lintNames, List.flatMap_cons, List.flatMap_nil, List.append_nil, List.any_append,
    riskyWarns_no_length, Bool.false_or, lengthWarns]
  split <;> simp_all [isLengthWarn]

/-! ## 일반 성질(모든 입력): 테스트들이 요구하는 규칙이 서로 충돌하지 않음을 보이는 불변식 -/

/-- 오독 신호가 하나라도 있으면 judge는 실패한다(게이트와 통과율이 어긋나지 않음). -/
theorem judge_false_of_misread (t : Text) (r : Rule) (h : (misreadHits t r).isEmpty = false) :
    judge t r = false := by
  simp [judge, h]

/-- 제외(excluded)는 오독 표본 수가 0보다 큰 것과 같다 — "1회라도 오독이면 제외"가 집계와 일치. -/
theorem excluded_iff_misreadN_pos (r : Rule) (xs : List Sample) (a b : Bool) :
    (score r xs a b).excluded = true ↔ (score r xs a b).misreadN > 0 := by
  simp [score]

/-- 통과 수는 표본 수를 넘지 않는다(runner의 `0 ≤ passed ≤ total` 입력 조건을 항상 만족). -/
theorem pass_le_n (r : Rule) (xs : List Sample) (a b : Bool) :
    (score r xs a b).pass ≤ (score r xs a b).n := by
  simp only [score]
  exact List.length_filter_le _ _

/-- 게이트 통과자가 있으면 `chooseSampled`는 예비 선택이 아니다. -/
theorem chooseSampled_not_fallback (sampled : List Stat) (s : Stat)
    (hs : s ∈ sampled) (he : s.excluded = false) : (chooseSampled sampled).2 = false := by
  have hel : s ∈ sampled.filter (fun s => !s.excluded) := List.mem_filter.mpr ⟨hs, by simp [he]⟩
  have : runnerChoose (fun s => !s.excluded) sampled ≠ none := by
    unfold runnerChoose
    cases hf : sampled.filter (fun s => !s.excluded) with
    | nil => simp [hf] at hel
    | cons y ys => simp [pyMax]
  unfold chooseSampled
  split
  · rfl
  · exact absurd (by assumption) this

/-- 게이트를 통과한(제외 안 된) 표본 있는 후보가 하나라도 있으면 예비 선택이 아니다. -/
theorem not_fallback_of_eligible (xs : List Stat) (s : Stat)
    (hs : s ∈ xs) (hn : s.n > 0) (he : s.excluded = false) : (choose xs).2 = false := by
  have hmem : s ∈ xs.filter (·.n > 0) := List.mem_filter.mpr ⟨hs, by simpa using hn⟩
  unfold choose
  split
  · rename_i hnil; simp [hnil] at hmem
  · exact chooseSampled_not_fallback _ s hmem he

/-- foldl로 고른 "최선"은 시작값이나 목록 원소 중 하나다. -/
theorem foldl_best_mem (f : Stat → Stat → Bool) (acc : Stat) (ys : List Stat) :
    ys.foldl (fun best y => if f y best then y else best) acc = acc ∨
    ys.foldl (fun best y => if f y best then y else best) acc ∈ ys := by
  induction ys generalizing acc with
  | nil => simp
  | cons y ys ih =>
    simp only [List.foldl]
    rcases ih (if f y acc then y else acc) with h | h
    · rw [h]; split
      · right; simp
      · left; rfl
    · right; simp [h]

/-- 선택된 이름은 입력에 있던 이름이다(없는 후보를 만들어 내지 않음). -/
theorem pyMax_mem (xs : List Stat) (s : Stat) (h : pyMax xs = some s) : s ∈ xs := by
  cases xs with
  | nil => simp [pyMax] at h
  | cons x rest =>
    simp only [pyMax, Option.some.injEq] at h
    subst h
    rcases foldl_best_mem keyGT x rest with h | h
    · rw [h]; simp
    · simp [h]

/-- `chooseSampled`가 고른 이름은 입력 목록의 이름이다. -/
theorem chooseSampled_mem (sampled : List Stat) (t : String) (h : (chooseSampled sampled).1 = some t) :
    ∃ s ∈ sampled, s.term = t := by
  unfold chooseSampled at h
  split at h
  · rename_i t' hr
    simp only [Option.some.injEq] at h; subst h
    unfold runnerChoose at hr
    obtain ⟨s, hps, hst⟩ := Option.map_eq_some_iff.mp hr
    exact ⟨s, (List.mem_filter.mp (pyMax_mem _ _ hps)).1, hst⟩
  · simp only at h
    unfold runnerChoose at h
    obtain ⟨s, hps, hst⟩ := Option.map_eq_some_iff.mp h
    have h1 := (List.mem_filter.mp (pyMax_mem _ _ hps)).1
    exact ⟨s, (List.mem_filter.mp h1).1, hst⟩

/-- `choose`가 고른 이름은 표본이 있는 입력 후보의 이름이다(없는 후보를 만들어 내지 않음). -/
theorem choose_selected_mem (xs : List Stat) (t : String) (h : (choose xs).1 = some t) :
    ∃ s ∈ xs, s.term = t ∧ s.n > 0 := by
  unfold choose at h
  split at h
  · simp at h
  · obtain ⟨s, hm, hst⟩ := chooseSampled_mem _ t h
    have := List.mem_filter.mp hm
    exact ⟨s, this.1, hst, by simpa using this.2⟩

end NameHarness
