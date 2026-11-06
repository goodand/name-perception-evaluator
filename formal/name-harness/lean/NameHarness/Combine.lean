/-!
# 키워드 조합 모델 — `scripts/name_keywords.py` `combine()`

앞자리 `heads`, 뒷자리 `tails`, 가운데 `mids`(extra는 이미 heads·tails 끝에 붙은 것으로 본다), 기존 이름 `seen`.
점수·정렬·`top` 자르기는 결과의 부분집합만 고르므로 아래 성질(모든 결과 원소에 대한 것)에 영향이 없어 뺐다.
`len(set(ks)) == len(ks)` 는 `ks.Nodup`(결정 가능)으로 적는다.
-/
namespace NameHarness.Combine

def name (ks : List String) : String := String.intercalate "-" ks

/-- src: combine 153-162. -/
def combine (heads tails mids seen : List String) (maxK : Nat) : List (List String) :=
  heads.flatMap fun h => tails.flatMap fun t =>
    if h == t then [] else
      let cands := [[h, t]] ++ (if maxK ≥ 3 then ((heads ++ mids).filter fun m => m != h && m != t).map fun m => [h, m, t] else [])
      cands.filter fun ks => decide (name ks ∉ seen) && decide ks.Nodup

end NameHarness.Combine
