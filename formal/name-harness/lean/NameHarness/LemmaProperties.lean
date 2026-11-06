import NameHarness.Lemma
/-!
# 두 단계 금지어 검사의 성질 (2026-11-06 요청)
1. block이면 warn이 아니다  2. 놓침 없음  3. 토큰화 불변(영어 항목, 한국어는 반례)  4. 한 단어는 한 번만
-/
namespace NameHarness.Lemma

theorem go_not_seen (lemma : String → String) (raw : List Char) (toks : List String) :
    ∀ (es : List Entry) (seen : List String) (w : String) (l : Level), (w, l) ∈ go lemma raw toks seen es → w ∉ seen := by
  intro es
  induction es with
  | nil => intro seen w l h; simp [go] at h
  | cons e es ih =>
    intro seen w l h hs
    simp only [go] at h
    split at h
    · exact ih _ _ _ h hs
    · split at h
      · simp only [List.mem_cons, Prod.mk.injEq] at h
        rcases h with ⟨rfl, -⟩ | h
        · contradiction
        · exact ih _ _ _ h (List.mem_cons_of_mem _ hs)
      · exact ih _ _ _ h hs

theorem go_nodup (lemma : String → String) (raw : List Char) (toks : List String) :
    ∀ (es : List Entry) (seen : List String), ((go lemma raw toks seen es).map (·.1)).Nodup := by
  intro es
  induction es with
  | nil => intro seen; simp [go]
  | cons e es ih =>
    intro seen
    simp only [go]
    split
    · exact ih _
    · split
      · simp only [List.map_cons, List.nodup_cons]
        refine ⟨?_, ih _⟩
        intro hm
        simp only [List.mem_map] at hm
        obtain ⟨⟨w, l⟩, hw, hwe⟩ := hm
        simp at hwe
        subst hwe
        exact go_not_seen _ _ _ _ _ _ _ hw (List.mem_cons_self ..)
      · exact ih _

/-- **4. 한 단어는 결과에 한 번만 나온다.** -/
theorem check_nodup (lemma : String → String) (raw : List Char) (toks : List String) (es : List Entry) :
    ((check lemma raw toks es).map (·.1)).Nodup := go_nodup _ _ _ _ _

theorem nodup_fst_unique {w : String} : ∀ (xs : List (String × Level)) {l₁ l₂ : Level},
    (xs.map (·.1)).Nodup → (w, l₁) ∈ xs → (w, l₂) ∈ xs → l₁ = l₂ := by
  intro xs
  induction xs with
  | nil => intro _ _ _ h; simp at h
  | cons x xs ih =>
    intro l₁ l₂ hn h1 h2
    simp only [List.map_cons, List.nodup_cons, List.mem_map] at hn
    simp only [List.mem_cons] at h1 h2
    rcases h1 with h1 | h1 <;> rcases h2 with h2 | h2
    · rw [← h1] at h2; simp at h2; exact h2.symm
    · exact absurd ⟨_, h2, by rw [← h1]⟩ hn.1
    · exact absurd ⟨_, h1, by rw [← h2]⟩ hn.1
    · exact ih hn.2 h1 h2

/-- **1. block이면 warn이 아니다**(같은 낱말이 두 단계로 동시에 나오지 않는다). -/
theorem block_warn_exclusive (lemma : String → String) (raw : List Char) (toks : List String) (es : List Entry) (w : String) :
    ¬ ((w, Level.block) ∈ check lemma raw toks es ∧ (w, Level.warn) ∈ check lemma raw toks es) := by
  intro ⟨hb, hw⟩
  have := nodup_fst_unique _ (check_nodup lemma raw toks es) hb hw
  cases this

theorem contig_single {lem : List String} {x : String} (h : x ∈ lem) : contig lem [x] = true := by
  unfold contig
  simp only [List.any_eq_true, List.mem_range, List.length_singleton]
  obtain ⟨i, hi, hx⟩ := List.getElem_of_mem h
  refine ⟨i, by omega, ?_⟩
  rw [List.take_one, List.head?_drop, List.getElem?_eq_getElem hi, hx]
  simp

/-- 한 낱말 영어 항목이 글의 낱말로 들어 있으면 block으로 판정된다. -/
theorem classify_word (lemma : String → String) (raw : List Char) (toks : List String) (e : Entry)
    (hk : e.ko = false) (ht : e.toks = [e.w]) (hne : e.w.isEmpty = false) (hm : e.w ∈ toks) :
    classify lemma raw toks e = some .block := by
  have hc : contig (toks.map lemma) [lemma e.w] = true := contig_single (List.mem_map_of_mem hm)
  simp [classify, hk, ht, hne, hc]

theorem go_complete (lemma : String → String) (raw : List Char) (toks : List String) :
    ∀ (es : List Entry) (seen : List String) (e : Entry), e ∈ es → (classify lemma raw toks e).isSome →
      e.w ∈ seen ∨ ∃ l, (e.w, l) ∈ go lemma raw toks seen es := by
  intro es
  induction es with
  | nil => intro _ _ h; simp at h
  | cons x xs ih =>
    intro seen e he hs
    simp only [List.mem_cons] at he
    rcases he with rfl | he
    · simp only [go]
      split
      · exact Or.inl ‹_›
      · cases hc : classify lemma raw toks e with
        | none => simp [hc] at hs
        | some l => exact Or.inr ⟨l, by simp⟩
    · simp only [go]
      split
      · exact ih _ _ he hs
      · split
        · rcases ih (x.w :: seen) e he hs with h | h
          · simp only [List.mem_cons] at h
            rcases h with h | h
            · rename_i l _; right; exact ⟨l, by rw [h]; exact List.mem_cons_self ..⟩
            · exact Or.inl h
          · obtain ⟨l, hl⟩ := h; exact Or.inr ⟨l, List.mem_cons_of_mem _ hl⟩
        · exact ih _ _ he hs

/-- **2. 놓침 없음**: 사전의 한 낱말 영어 항목(토큰이 자기 자신)이 글에 낱말로 들어 있으면 그 낱말은 결과에 있다.
그때의 단계는 block이다 — 단, 같은 낱말이 앞 사전에서 이미 걸렸다면 그 항목의 단계. 3글자 조건 없이도 성립한다. -/
theorem no_miss (lemma : String → String) (raw : List Char) (toks : List String) (es : List Entry) (e : Entry)
    (he : e ∈ es) (hk : e.ko = false) (ht : e.toks = [e.w]) (hne : e.w.isEmpty = false) (hm : e.w ∈ toks) :
    ∃ l, (e.w, l) ∈ check lemma raw toks es := by
  rcases go_complete lemma raw toks es [] e he (by rw [classify_word _ _ _ _ hk ht hne hm]; rfl) with h | h
  · simp at h
  · exact h

/-- **3. 토큰화 불변(영어 항목)**: 한국어 항목이 없으면 결과는 원문이 아니라 낱말 목록에만 달려 있다. -/
theorem token_invariant (lemma : String → String) (raw₁ raw₂ : List Char) (toks : List String) :
    ∀ (es : List Entry) (seen : List String), (∀ e ∈ es, e.ko = false) →
      go lemma raw₁ toks seen es = go lemma raw₂ toks seen es := by
  intro es
  induction es with
  | nil => intros; rfl
  | cons e es ih =>
    intro seen hko
    have hk := hko e (List.mem_cons_self ..)
    have hc : classify lemma raw₁ toks e = classify lemma raw₂ toks e := by simp [classify, hk]
    have ih' := fun s => ih s (fun e' h => hko e' (List.mem_cons_of_mem _ h))
    simp only [go, hc, ih']

/-- **반례(3번, 한국어)**: 공백 하나만 다른 `개발`과 `개 발`은 영어 낱말 목록이 같지만(둘 다 빈 목록) 결과가 다르다. -/
theorem ko_not_token_invariant :
    check id "개발".toList [] [{ dict := "general", w := "개발", toks := [], ko := true }] = [("개발", .block)] ∧
    check id "개 발".toList [] [{ dict := "general", w := "개발", toks := [], ko := true }] = [] := by decide

/-- 길이 2 이하 한 낱말 항목은 warn이 없다(낱말로 있으면 block, 낱말 안에만 있으면 아무것도 아님). -/
theorem short_no_warn : check id [] ["xaby"] [{ dict := "d", w := "ab", toks := ["ab"] }] = [] := by decide
theorem warn_example : check id [] ["pytest"] [{ dict := "d", w := "test", toks := ["test"] }] = [("test", .warn)] := by
  decide

end NameHarness.Lemma
