import NameHarness.Review
import NameHarness.Slots
import NameHarness.Combine
/-!
# 수정 프로토콜 코드의 성질 (2026-11-06 요청)

1. `search_words.review` — 단조성·낯선 낱말 거부·종료·ok ⇔ 전부 받아들임·keep/dropped 분할·뺀 이유 모양
2. `prompt_slots.gate` — 걸리지 않은 빈칸 불변·걸린 값 재제출 거부·종료·결정성
3. `name_keywords.combine` — 키워드 중복 없음·키워드 수·기존 이름 제외

`decide`로 끝나는 정리는 tests/ 의 같은 이름 테스트를 모델 위에서 되풀이한 것(파이썬은 keep·fix_only를 정렬하므로 순서만 다를 수 있다).
-/
namespace NameHarness

/-! ## 1. search_words.review -/
namespace Review

theorem lookup_append_left {acc ok : AccMap} {w : String} {a : Acc} (h : lookup acc w = some a) :
    lookup (acc ++ ok) w = some a := by
  unfold lookup at *
  rw [List.find?_append]
  cases hf : acc.find? (·.1 == w) <;> simp [hf] at h ⊢
  exact h

theorem lookup_append_cases {acc ok : AccMap} {w : String} {a : Acc} (h : lookup (acc ++ ok) w = some a) :
    lookup acc w = some a ∨ (w, a) ∈ ok := by
  unfold lookup at *
  rw [List.find?_append] at h
  cases hf : acc.find? (·.1 == w) with
  | some p => left; rw [hf] at h; simpa using h
  | none =>
    right
    rw [hf] at h
    simp only [Option.none_or, Option.map_eq_some_iff] at h
    obtain ⟨⟨pw, pa⟩, hp, ha⟩ := h
    have hq := List.find?_some hp
    simp at hq ha
    subst hq; subst ha
    exact List.mem_of_find?_eq_some hp

/-- 결과 상태의 accepted = 이전 accepted ++ 이번에 새로 받아들인 것(어느 갈래든). -/
theorem review_acc (s : State) (ds : List Dec) :
    (review s ds).1.acc = s.acc ++ (pass s.names s.acc ds []).ok := by
  simp only [review]
  split
  · rfl
  · split <;> rfl

/-- **단조성**: 받아들인 항목은 한 번 들어가면 값이 바뀌지 않는다. -/
theorem accepted_monotone (s : State) (ds : List Dec) {w : String} {a : Acc} (h : lookup s.acc w = some a) :
    lookup (review s ds).1.acc w = some a := by
  rw [review_acc]; exact lookup_append_left h

theorem decError_none_mem {names : List String} {acc : AccMap} {seen : List String} {d : Dec}
    (h : decError names acc seen d = none) : d.word ∈ names := by
  by_cases hc : d.word ∈ names
  · exact hc
  · unfold decError at h; simp [hc] at h

theorem pass_ok_mem_names (names : List String) (acc : AccMap) :
    ∀ (ds : List Dec) (seen : List String) (w : String) (a : Acc), (w, a) ∈ (pass names acc ds seen).ok → w ∈ names := by
  intro ds
  induction ds with
  | nil => intro seen w a h; simp [pass] at h
  | cons d ds ih =>
    intro seen w a h
    simp only [pass] at h
    split at h
    · exact ih _ w a h
    · rename_i he
      split at h
      · simp at h
        rcases h with ⟨rfl, -⟩ | h
        · exact decError_none_mem he
        · exact ih _ w a h
      · exact ih _ w a h

/-- **낯선 낱말 거부**: 결과 accepted에 있는 낱말은 전에 있던 것이거나 검색자가 낸 낱말이다. -/
theorem accepted_from_names (s : State) (ds : List Dec) {w : String} {a : Acc}
    (h : lookup (review s ds).1.acc w = some a) : lookup s.acc w = some a ∨ w ∈ s.names := by
  rw [review_acc] at h
  rcases lookup_append_cases h with h | h
  · exact Or.inl h
  · exact Or.inr (pass_ok_mem_names _ _ _ _ _ _ h)

/-- 처음 accepted가 비어 있었다면(검색 직후) accepted의 모든 낱말은 검색자가 낸 것이다. -/
theorem accepted_subset_names (s : State) (ds : List Dec) (h0 : s.acc = []) {w : String} {a : Acc}
    (h : lookup (review s ds).1.acc w = some a) : w ∈ s.names := by
  rcases accepted_from_names s ds h with h | h
  · simp [lookup, h0] at h
  · exact h

theorem decError_none_wf {names : List String} {acc : AccMap} {seen : List String} {d : Dec} {k : Bool}
    (h : decError names acc seen d = none) (hk : d.keep = some k) : (toAcc k d).wf := by
  cases k with
  | true => intro hc; simp [toAcc] at hc
  | false =>
    intro _
    unfold decError at h
    rw [hk] at h
    simp only [Bool.not_false, Bool.true_and] at h
    split at h
    · simp at h
    split at h
    · simp at h
    split at h
    · simp at h
    rename_i hr
    split at h
    · simp at h
    rename_i hn
    refine ⟨?_, ?_⟩
    · cases hr' : d.reason with
      | none => simp [hr'] at hr
      | some r =>
        refine ⟨r, by simp [toAcc, hr'], ?_⟩
        simp [hr'] at hr
        exact hr
    · intro hg
      simp [toAcc] at hg ⊢
      simp [hg] at hn
      exact hn

theorem pass_ok_wf (names : List String) (acc : AccMap) :
    ∀ (ds : List Dec) (seen : List String) (w : String) (a : Acc), (w, a) ∈ (pass names acc ds seen).ok → a.wf := by
  intro ds
  induction ds with
  | nil => intro seen w a h; simp [pass] at h
  | cons d ds ih =>
    intro seen w a h
    simp only [pass] at h
    split at h
    · exact ih _ w a h
    · rename_i he
      split at h
      · rename_i hl hk
        simp at h
        rcases h with ⟨-, rfl⟩ | h
        · exact decError_none_wf he hk
        · exact ih _ w a h
      · exact ih _ w a h

/-- accepted의 모양 조건은 보존된다. -/
theorem review_acc_wf (s : State) (ds : List Dec) (hs : s.acc.wf) : (review s ds).1.acc.wf := by
  rw [review_acc]
  intro w a h
  rcases lookup_append_cases h with h | h
  · exact hs w a h
  · exact pass_ok_wf _ _ _ _ w a h

/-- **ok ⇔ 전부 받아들임**: 오류가 없고, 모든 낱말이 (갱신된) accepted에 있다. -/
theorem ok_iff (s : State) (ds : List Dec) :
    (review s ds).2.isOk = true ↔
      (pass s.names s.acc ds []).errors = [] ∧ ∀ w ∈ s.names, lookup (review s ds).1.acc w ≠ none := by
  rw [review_acc]
  simp only [review]
  split
  · rename_i hc
    simp only [Result.isOk, true_iff]
    simp only [Bool.and_eq_true, List.isEmpty_iff, List.filter_eq_nil_iff] at hc
    obtain ⟨he, hm⟩ := hc
    refine ⟨he, fun w hw => ?_⟩
    have := hm w hw
    simp [he] at this
    exact this
  · rename_i hc
    have : ¬ ((pass s.names s.acc ds []).errors = [] ∧ ∀ w ∈ s.names, lookup (s.acc ++ (pass s.names s.acc ds []).ok) w ≠ none) := by
      intro ⟨he, hall⟩
      apply hc
      simp only [Bool.and_eq_true, List.isEmpty_iff, List.filter_eq_nil_iff]
      refine ⟨he, fun w hw => ?_⟩
      simp [he]
      exact hall w hw
    split <;> simp [Result.isOk, this]

/-- **keep·dropped 분할**: 합치면 전체 낱말(순열), 서로소. -/
theorem ok_partition (s : State) (ds : List Dec) (keep dropped : List String)
    (h : (review s ds).2 = .ok keep dropped) :
    (keep ++ dropped).Perm s.names ∧ ∀ w, w ∈ keep → w ∉ dropped := by
  simp only [review] at h
  split at h
  · simp only [Result.ok.injEq] at h
    obtain ⟨rfl, rfl⟩ := h
    refine ⟨List.filter_append_perm _ _, ?_⟩
    intro w hk hd
    simp only [List.mem_filter] at hk hd
    simp [hk.2] at hd
  · split at h <;> simp at h

/-- **뺀 항목의 이유**: ok일 때 dropped의 낱말은 accepted에 keep=false로 있고, 이유는 REASONS 안, 기타면 note가 있다. -/
theorem dropped_reason (s : State) (ds : List Dec) (keep dropped : List String) (hs : s.acc.wf)
    (h : (review s ds).2 = .ok keep dropped) :
    ∀ w ∈ dropped, ∃ a, lookup (review s ds).1.acc w = some a ∧ a.keep = false ∧
      (∃ r, a.reason = some r ∧ r ∈ REASONS) ∧ (a.reason = some "기타" → a.noteOk = true) := by
  intro w hw
  have hok : (review s ds).2.isOk = true := by rw [h]; rfl
  obtain ⟨-, hall⟩ := (ok_iff s ds).1 hok
  have hwf := review_acc_wf s ds hs
  have hwn : w ∈ s.names ∧ ¬ ((lookup (review s ds).1.acc w).map (·.keep) == some true) = true := by
    rw [review_acc]
    simp only [review] at h
    split at h
    · simp only [Result.ok.injEq] at h
      obtain ⟨-, rfl⟩ := h
      simpa [List.mem_filter] using hw
    · split at h <;> simp at h
  obtain ⟨hwn, hnk⟩ := hwn
  cases ha : lookup (review s ds).1.acc w with
  | none => exact absurd ha (hall w hwn)
  | some a =>
    rw [ha] at hnk
    have hkeep : a.keep = false := by
      cases hk : a.keep
      · rfl
      · simp [hk] at hnk
    obtain ⟨hr, hn⟩ := hwf w a ha hkeep
    exact ⟨a, rfl, hkeep, hr, hn⟩

/-- 회차: ok가 아니면 1 늘고, ok면 그대로. -/
theorem round_after (s : State) (ds : List Dec) :
    (review s ds).1.round = if (review s ds).2.isOk then s.round else s.round + 1 := by
  simp only [review]
  split
  · simp [Result.isOk]
  · split <;> simp [Result.isOk]

/-- **종료**: stopped ⇔ ok가 아니고 이번 거부로 회차가 max_rounds를 넘었다. 제출 내용과 무관. -/
theorem stopped_iff (s : State) (ds : List Dec) :
    (∃ e m, (review s ds).2 = .stopped e m) ↔ (review s ds).2.isOk = false ∧ s.maxRounds < s.round + 1 := by
  simp only [review]
  split
  · simp [Result.isOk]
  · split <;> simp [Result.isOk] <;> omega

/-- 거부가 이어지면 회차는 거부 수만큼 쌓인다: 거부 k번 뒤 round = round₀ + k. -/
theorem round_after_rejections (s : State) (dss : List (List Dec))
    (hrej : ∀ s' ds, ds ∈ dss → (review s' ds).2.isOk = false) :
    (dss.foldl (fun st ds => (review st ds).1) s).round = s.round + dss.length := by
  induction dss generalizing s with
  | nil => simp
  | cons ds dss ih =>
    simp only [List.foldl_cons, List.length_cons]
    rw [ih _ (fun s' ds' h => hrej s' ds' (List.mem_cons_of_mem _ h))]
    rw [round_after, hrej s ds (List.mem_cons_self ..)]
    simp; omega

/-! ### tests/test_search_words.py 의 review 테스트를 모델에서 -/

def S0 : State := { names := ["sense", "meaning", "tool"], acc := [], round := 0, maxRounds := 3 }
def dec (w : String) (k : Bool) (r : Option String := none) (n : Bool := false) : Dec := ⟨w, some k, r, n⟩

theorem test_review_ok_lists_dropped :
    (review S0 [dec "sense" true, dec "meaning" true, dec "tool" false (some "개발 용어 경고")]).2
      = .ok ["sense", "meaning"] ["tool"] := by decide

theorem test_review_rejects_new_word_and_bad_reason_then_fix_only :
    let r1 := review S0 [dec "sense" true, dec "checker" true, dec "tool" false (some "그냥")]
    r1.2 = .rejected 1 [("checker", "검색자가 내지 않은 낱말"), ("tool", "뺄 때 이유는 … 중 하나")] ["meaning"]
             ["checker", "tool", "meaning"] ∧
    (review r1.1 [dec "meaning" true, dec "tool" false (some "너무 넓음")]).2 = .ok ["sense", "meaning"] ["tool"] := by
  decide

theorem test_review_locks_accepted :
    let r1 := review S0 [dec "sense" true]
    (review r1.1 [dec "sense" false (some "너무 넓음")]).2
      = .rejected 2 [("sense", "이미 받아들인 항목은 바꿀 수 없음")] ["meaning", "tool"] ["sense", "meaning", "tool"] := by
  decide

theorem test_review_other_needs_note :
    (review S0 [dec "tool" false (some "기타")]).2
      = .rejected 1 [("tool", "기타는 note 필수")] ["sense", "meaning"] ["tool", "sense", "meaning"] := by decide

theorem test_review_stops_after_max_rounds :
    let r1 := review S0 []
    let r2 := review r1.1 []
    let r3 := review r2.1 []
    let r4 := review r3.1 []
    (∃ r e m f, r1.2 = .rejected r e m f) ∧ (∃ r e m f, r2.2 = .rejected r e m f) ∧
    (∃ r e m f, r3.2 = .rejected r e m f) ∧ (∃ e m, r4.2 = .stopped e m) := by
  refine ⟨⟨1, _, _, _, rfl⟩, ⟨2, _, _, _, rfl⟩, ⟨3, _, _, _, rfl⟩, ⟨_, _, rfl⟩⟩

/-- **관찰(반례)**: stopped 뒤에도 상태는 살아 있어, 다음 제출이 완전하면 ok를 돌려준다.
"넘으면 멈춘다"는 호출하는 쪽(namecheck)이 지켜야 하는 약속이다. -/
theorem ok_after_stopped :
    let r4 := (List.replicate 4 ([] : List Dec)).foldl (fun st ds => (review st ds).1) S0
    (∃ e m, (review r4 []).2 = .stopped e m) ∧
    (review r4 [dec "sense" true, dec "meaning" true, dec "tool" true]).2.isOk = true := by
  refine ⟨⟨_, _, rfl⟩, rfl⟩

end Review

/-! ## 2. prompt_slots.gate -/
namespace Slots

theorem get_update (s new : Slots) (k : String) : get (update s new) k = (get new k).or (get s k) := by
  unfold get update
  rw [List.find?_append]
  cases hn : new.find? (·.1 == k) with
  | some p => simp
  | none =>
    simp only [Option.none_or]
    congr 1
    induction s with
    | nil => rfl
    | cons kv s ih =>
      by_cases hk : kv.1 = k
      · have hq : (new.find? (·.1 == kv.1)).isNone = true := by rw [hk, hn]; rfl
        rw [List.filter_cons, if_pos hq]
        simp [List.find?_cons, hk]
      · have hp : (kv.1 == k) = false := by simpa using hk
        rw [List.filter_cons]
        split
        · simp only [List.find?_cons, hp]; exact ih
        · simp only [List.find?_cons, hp]; exact ih

theorem get_new_none_of_keys {new : Slots} {k : String} (h : ∀ kv ∈ new, kv.1 ≠ k) : get new k = none := by
  unfold get
  rw [List.find?_eq_none.2]
  · rfl
  · intro kv hkv; simpa using h kv hkv

/-- 바뀌지 않은 키의 값은 그대로. -/
theorem get_update_of_not_key {s new : Slots} {k : String} (h : ∀ kv ∈ new, kv.1 ≠ k) :
    get (update s new) k = get s k := by
  rw [get_update, get_new_none_of_keys h]; rfl

/-- 값이 바뀌었다면 new가 그 키에 그 값을 냈다. -/
theorem changed_from_new {s new : Slots} {k v : String} (h1 : get (update s new) k = some v) (h2 : get s k ≠ some v) :
    (k, v) ∈ new := by
  rw [get_update] at h1
  cases hn : get new k with
  | none => rw [hn] at h1; simp at h1; exact absurd h1 h2
  | some v' =>
    rw [hn] at h1
    simp at h1
    subst h1
    unfold get at hn
    simp only [Option.map_eq_some_iff] at hn
    obtain ⟨p, hp, rfl⟩ := hn
    have hm := List.mem_of_find?_eq_some hp
    have hq := List.find?_some hp
    obtain ⟨pk, pv⟩ := p
    simp at hq
    subst hq
    exact hm

def Unhit (p : Round) (k : String) : Prop := ∀ h ∈ p.hits, h.slot ≠ k

/-- 뒤집힌 기록(최신이 앞)에서, 앞 회차에서 걸리지 않은 빈칸은 다음 회차에서 값이 같다. -/
def KeepsUnhit : List Round → Prop
  | r₂ :: r₁ :: rs => (∀ k, Unhit r₁ k → get r₂.slots k = get r₁.slots k) ∧ KeepsUnhit (r₁ :: rs)
  | _ => True

theorem go_keepsUnhit (c : Cfg) (maxR : Nat) :
    ∀ (fuel rnd : Nat) (s : Slots) (seen : List Hit) (log : List Round),
      KeepsUnhit log → (∀ p, log.head? = some p → ∀ k, Unhit p k → get s k = get p.slots k) →
      KeepsUnhit (go c maxR fuel rnd s seen log).logRev := by
  intro fuel
  induction fuel with
  | zero => intro rnd s seen log h1 _; simpa [go, Result.logRev] using h1
  | succ fuel ih =>
    intro rnd s seen log h1 h2
    have hcons : KeepsUnhit (⟨s, hitsOf c s⟩ :: log) := by
      cases log with
      | nil => trivial
      | cons p rs => exact ⟨h2 p rfl, h1⟩
    simp only [go]
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    rename_i hnew _
    apply ih _ _ _ _ hcons
    intro p hp k hk
    simp only [List.head?_cons, Option.some.injEq] at hp
    subst hp
    apply get_update_of_not_key
    intro kv hkv hkk
    simp only [List.any_eq_true, Bool.not_eq_true', not_exists, not_and, Bool.not_eq_false] at hnew
    have := hnew kv hkv
    simp only [List.any_eq_true, beq_iff_eq] at this
    obtain ⟨h, hh, hhs⟩ := this
    exact hk h hh (hhs.trans hkk)

/-- **걸리지 않은 빈칸은 회차 사이에 값이 바뀌지 않는다** (기록 전체에서, 결과가 ok든 거부든). -/
theorem gate_keepsUnhit (c : Cfg) (maxR : Nat) (s : Slots) : KeepsUnhit (gate c maxR s).logRev :=
  go_keepsUnhit c maxR _ 0 s [] [] trivial (fun _ h => by simp at h)

def HitPair (log : List Round) (k v : String) : Prop := ∃ e ∈ log, ∃ h ∈ e.hits, h.slot = k ∧ h.value = v

/-- 뒤집힌 기록에서, 값이 바뀐 빈칸의 새 값은 그 전 어느 회차에서도 그 빈칸에 걸린 값이 아니다. -/
def NoRepeat : List Round → Prop
  | r₂ :: r₁ :: rs => (∀ k v, get r₂.slots k = some v → get r₁.slots k ≠ some v → ¬ HitPair (r₁ :: rs) k v) ∧ NoRepeat (r₁ :: rs)
  | _ => True

theorem go_noRepeat (c : Cfg) (maxR : Nat) :
    ∀ (fuel rnd : Nat) (s : Slots) (seen : List Hit) (log : List Round),
      NoRepeat log → (∀ h, h ∈ seen ↔ ∃ e ∈ log, h ∈ e.hits) →
      (∀ p, log.head? = some p → ∀ k v, get s k = some v → get p.slots k ≠ some v → ¬ HitPair log k v) →
      NoRepeat (go c maxR fuel rnd s seen log).logRev := by
  intro fuel
  induction fuel with
  | zero => intro rnd s seen log h1 _ _; simpa [go, Result.logRev] using h1
  | succ fuel ih =>
    intro rnd s seen log h1 hseen h2
    have hcons : NoRepeat (⟨s, hitsOf c s⟩ :: log) := by
      cases log with
      | nil => trivial
      | cons p rs => exact ⟨h2 p rfl, h1⟩
    simp only [go]
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    split
    · simpa [Result.logRev] using hcons
    rename_i hagain
    apply ih _ _ _ _ hcons
    · intro h
      simp only [List.mem_append, hseen, List.mem_cons, exists_eq_or_imp]
      exact Or.comm
    · intro p hp k v hv hne
      simp only [List.head?_cons, Option.some.injEq] at hp
      subst hp
      have hmem := changed_from_new hv hne
      intro ⟨e, he, h, hh, hk, hv'⟩
      simp only [List.any_eq_true, Bool.and_eq_true, beq_iff_eq, not_exists, not_and] at hagain
      apply hagain (k, v) hmem h
      · have : h ∈ seen ++ hitsOf c s := by
          simp only [List.mem_append, hseen]
          simp only [List.mem_cons] at he
          rcases he with rfl | he
          · exact Or.inr hh
          · exact Or.inl ⟨e, he, hh⟩
        exact this
      · exact hk
      · exact hv'

/-- **이전에 걸린 값은 다시 받아들여지지 않는다**: 어느 회차에서든 값이 바뀐 빈칸의 새 값은 그 빈칸에 전에 걸린 값이 아니다.
(채우는 쪽이 걸린 빈칸을 비워 두면 값은 *그대로* 남아 다음 회차에 다시 걸린다 — 그건 "다시 낸" 것이 아니다.) -/
theorem gate_noRepeat (c : Cfg) (maxR : Nat) (s : Slots) : NoRepeat (gate c maxR s).logRev :=
  go_noRepeat c maxR _ 0 s [] [] trivial (by simp) (fun _ h => by simp at h)

theorem go_reason_ne_fuel (c : Cfg) (maxR : Nat) :
    ∀ (fuel rnd : Nat) (s : Slots) (seen : List Hit) (log : List Round),
      rnd + fuel = maxR + 1 → 1 ≤ fuel → (go c maxR fuel rnd s seen log).reason ≠ some "fuel" := by
  intro fuel
  induction fuel with
  | zero => intros; omega
  | succ fuel ih =>
    intro rnd s seen log h1 _
    simp only [go]
    split
    · simp [Result.reason]
    split
    · simp [Result.reason]
    rename_i hne
    simp only [beq_iff_eq] at hne
    split
    · simp [Result.reason]
    split
    · simp [Result.reason]
    apply ih <;> omega

/-- **종료**: `range(max_rounds+1)`는 바닥나지 않는다 — 끝은 늘 ok 또는 세 가지 SlotRejected 중 하나. -/
theorem gate_reason_ne_fuel (c : Cfg) (maxR : Nat) (s : Slots) : (gate c maxR s).reason ≠ some "fuel" :=
  go_reason_ne_fuel c maxR _ 0 s [] [] (by omega) (by omega)

theorem gate_outcomes (c : Cfg) (maxR : Nat) (s : Slots) :
    (∃ t l, gate c maxR s = .ok t l) ∨
    ∃ l, gate c maxR s = .rejected "고쳐도 걸림" l ∨ gate c maxR s = .rejected "걸리지 않은 빈칸을 바꾸려 함" l ∨
         gate c maxR s = .rejected "이전에 걸린 값을 다시 냄" l := by
  have hf := gate_reason_ne_fuel c maxR s
  suffices ∀ fuel rnd s seen log, (go c maxR fuel rnd s seen log).reason ≠ some "fuel" →
      (∃ t l, go c maxR fuel rnd s seen log = .ok t l) ∨
      ∃ l, go c maxR fuel rnd s seen log = .rejected "고쳐도 걸림" l ∨
           go c maxR fuel rnd s seen log = .rejected "걸리지 않은 빈칸을 바꾸려 함" l ∨
           go c maxR fuel rnd s seen log = .rejected "이전에 걸린 값을 다시 냄" l from this _ _ _ _ _ hf
  intro fuel
  induction fuel with
  | zero => intro rnd s seen log h; simp [go, Result.reason] at h
  | succ fuel ih =>
    intro rnd s seen log h
    simp only [go]
    split
    · exact Or.inl ⟨_, _, rfl⟩
    split
    · exact Or.inr ⟨_, Or.inl rfl⟩
    split
    · exact Or.inr ⟨_, Or.inr (Or.inl rfl)⟩
    split
    · exact Or.inr ⟨_, Or.inr (Or.inr rfl)⟩
    rename_i h1 h2 h3 h4
    apply ih
    intro hh
    apply h
    simp only [go, h1, h2, h3, h4, ↓reduceIte]
    exact hh

theorem go_log_le (c : Cfg) (maxR : Nat) :
    ∀ (fuel rnd : Nat) (s : Slots) (seen : List Hit) (log : List Round),
      (go c maxR fuel rnd s seen log).logRev.length ≤ log.length + fuel := by
  intro fuel
  induction fuel with
  | zero => intros; simp [go, Result.logRev]
  | succ fuel ih =>
    intro rnd s seen log
    simp only [go]
    split
    · simp [Result.logRev] <;> omega
    split
    · simp [Result.logRev] <;> omega
    split
    · simp [Result.logRev] <;> omega
    split
    · simp [Result.logRev] <;> omega
    have := ih (rnd + 1) (update s (c.filler (rnd + 1) (hitsOf c s))) (seen ++ hitsOf c s) (⟨s, hitsOf c s⟩ :: log)
    simp only [List.length_cons] at this
    omega

/-- 기록은 최대 max_rounds + 1 회차(채우기 요청은 최대 max_rounds번). -/
theorem gate_log_le (c : Cfg) (maxR : Nat) (s : Slots) : (gate c maxR s).log.length ≤ maxR + 1 := by
  simpa [Result.log, gate] using go_log_le c maxR (maxR + 1) 0 s [] []

/-- **결정성**: 같은 (설정, 틀 빈칸, 처음 값)이면 같은 결과. 모델은 순수 함수라 자명하다 —
파이썬에서는 filler와 Kiwi가 결정적일 때만 성립한다(gate 자체는 난수·시간·전역 상태를 쓰지 않는다). -/
theorem gate_deterministic (c : Cfg) (maxR : Nat) (s₁ s₂ : Slots) (h : s₁ = s₂) : gate c maxR s₁ = gate c maxR s₂ := by
  subst h; rfl

/-! ### tests/test_prompt_slots.py 의 gate 테스트를 모델에서 (W = {user, tool}; 영어 값은 조사 불가) -/

/-- 사전에 걸리는 값: user·tool이 든 테스트 값들. -/
def badW (v : String) : Bool :=
  v ∈ ["end user", "user", "tool 사람", "user 팀원", "tool 독자", "user 손님"]
def noJosaW (v : String) : Bool := v ∈ ["end user", "user", "reader", "tool 사람", "user 팀원", "tool 독자", "user 손님"]

def cfg (f : Nat → List Hit → Slots) (josa : List String := ["독자", "길이"]) : Cfg :=
  { bad := badW, noJosa := noJosaW, josaHole := (· ∈ josa), filler := f }

theorem test_gate_refills_only_hit_slot :
    gate (cfg fun _ _ => [("독자", "처음 보는 사람")]) 3 [("독자", "end user"), ("길이", "한 줄")]
      = .ok [("독자", "처음 보는 사람"), ("길이", "한 줄")]
            [⟨[("독자", "처음 보는 사람"), ("길이", "한 줄")], []⟩, ⟨[("독자", "end user"), ("길이", "한 줄")], [⟨"독자", "end user"⟩]⟩] := by
  decide

theorem test_gate_rejects_touching_other_slot :
    (gate (cfg (fun _ _ => [("독자", "사람"), ("길이", "두 줄")]) ["독자"]) 3 [("독자", "user"), ("길이", "한 줄")]).reason
      = some "걸리지 않은 빈칸을 바꾸려 함" := by decide

theorem test_gate_rejects_repeat_value :
    (gate (cfg fun _ _ => [("독자", "user")]) 3 [("독자", "user")]).reason = some "이전에 걸린 값을 다시 냄" := by decide

theorem test_gate_stops_after_max_rounds :
    let r := gate (cfg fun rnd _ => [("독자", if rnd = 1 then "tool 사람" else if rnd = 2 then "user 팀원" else "tool 독자")]) 3
               [("독자", "user")]
    r.reason = some "고쳐도 걸림" ∧ r.log.length = 4 := by decide

theorem test_gate_english_in_josa_slot_is_refilled :
    (gate (cfg fun _ _ => [("독자", "독자")]) 3 [("독자", "reader")]) = .ok [("독자", "독자")]
      [⟨[("독자", "독자")], []⟩, ⟨[("독자", "reader")], [⟨"독자", "reader"⟩]⟩] := by decide

end Slots

/-! ## 3. name_keywords.combine -/
namespace Combine

/-- **결과 이름의 모양**: 키워드 중복 없음, 키워드 수 2 또는 3(3은 max_keywords ≥ 3일 때만), 기존 이름이 아님. -/
theorem mem_combine {heads tails mids seen : List String} {maxK : Nat} {ks : List String}
    (h : ks ∈ combine heads tails mids seen maxK) :
    ks.Nodup ∧ 2 ≤ ks.length ∧ ks.length ≤ 3 ∧ (ks.length = 3 → 3 ≤ maxK) ∧ name ks ∉ seen := by
  simp only [combine, List.mem_flatMap] at h
  obtain ⟨hd, -, t, -, hmem⟩ := h
  split at hmem
  · simp at hmem
  · simp only [List.mem_filter, Bool.and_eq_true, decide_eq_true_eq] at hmem
    obtain ⟨hc, hns, hnd⟩ := hmem
    refine ⟨hnd, ?_, ?_, ?_, hns⟩ <;>
    · simp only [List.cons_append, List.nil_append, List.mem_cons, List.mem_ite_nil_right, List.mem_map] at hc
      rcases hc with rfl | ⟨h3, m, -, rfl⟩ <;> simp <;> omega

/-- max_keywords ≥ 2 이면 키워드 수 ≤ max_keywords. -/
theorem length_le_maxK {heads tails mids seen : List String} {maxK : Nat} {ks : List String}
    (hk : 2 ≤ maxK) (h : ks ∈ combine heads tails mids seen maxK) : ks.length ≤ maxK := by
  obtain ⟨-, -, h3, h33, -⟩ := mem_combine h
  by_cases hl : ks.length = 3
  · exact hl ▸ h33 hl
  · omega

/-- **관찰(반례)**: max_keywords = 1 이어도 두 키워드 이름을 낸다 — 문서의 "2~max_keywords"가 성립하지 않는 입력. -/
theorem maxK_one_still_pairs : combine ["a"] ["b"] [] [] 1 = [["a", "b"]] := by decide

/-- tests/test_search_words.py::test_combine_uses_extra_words — extra "sense"가 앞·뒤 모두에 들어간다. -/
theorem test_combine_uses_extra_words :
    let seen := ["name-check", "word-guard", "name-guard", "word-check"]
    let out := combine ["name", "word", "sense"] ["check", "guard", "sense"] [] seen 3
    ["name", "sense"] ∈ out ∧ ["sense", "check"] ∈ out ∧
    ["name", "sense"] ∉ combine ["name", "word"] ["check", "guard"] [] seen 3 := by decide

end Combine

end NameHarness
