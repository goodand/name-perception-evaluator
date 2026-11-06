/-!
# 빈칸 수정 프로토콜 모델 — `scripts/prompt_slots.py` `gate()`

빈칸 값 검사(`check_slots`)와 조사 검사(`_josa` → NoJosa)는 값만 보는 술어로 추상화한다:
`bad v`(사전에 걸림), `noJosa v`(조사 자리에 둘 수 없음). 채우는 쪽(filler)은 회차와 걸린 빈칸 목록을 받아 새 값을 돌려주는 함수.
`for rnd in range(max_rounds + 1)` 은 연료 `maxR + 1` 의 구조 재귀. 기록(log)은 최신 회차가 앞에 오게 쌓고(`logRev`), `log`는 뒤집은 것.
-/
namespace NameHarness.Slots

abbrev Slots := List (String × String)

def get (s : Slots) (k : String) : Option String := (s.find? (·.1 == k)).map (·.2)

/-- `slots.update(new)`: new에 있는 키는 바꾸고 나머지는 그대로. -/
def update (s : Slots) (new : Slots) : Slots :=
  new ++ s.filter fun kv => (new.find? (·.1 == kv.1)).isNone

structure Hit where
  slot  : String
  value : String
  deriving Repr, DecidableEq

structure Round where
  slots : Slots
  hits  : List Hit
  deriving Repr, DecidableEq

inductive Result where
  | ok (slots : Slots) (logRev : List Round)
  | rejected (reason : String) (logRev : List Round)
  deriving Repr, DecidableEq

structure Cfg where
  bad      : String → Bool            -- check_slots: 값이 사전에 걸림
  noJosa   : String → Bool            -- _josa가 NoJosa를 냄
  josaHole : String → Bool            -- 틀에서 조사가 붙는 빈칸
  filler   : Nat → List Hit → Slots   -- (round, hits) → 새 값

/-- src: gate 102-107. 사전에 걸린 빈칸 + (걸리지 않은 조사 빈칸 중) 조사를 못 붙이는 값. -/
def hitsOf (c : Cfg) (s : Slots) : List Hit :=
  let h1 := (s.filter fun kv => c.bad kv.2).map fun kv => ⟨kv.1, kv.2⟩
  let h2 := (s.filter fun kv => c.josaHole kv.1 && !(h1.any (·.slot == kv.1)) && c.noJosa kv.2).map fun kv => ⟨kv.1, kv.2⟩
  h1 ++ h2

/-- src: gate 101-124. `seen`: 지금까지 걸린 (빈칸, 값). 연료 0은 도달하지 않는다(`gate_reason_ne_fuel`). -/
def go (c : Cfg) (maxR : Nat) : Nat → Nat → Slots → List Hit → List Round → Result
  | 0, _, _, _, log => .rejected "fuel" log
  | fuel + 1, rnd, s, seen, log =>
    let hits := hitsOf c s
    let log := ⟨s, hits⟩ :: log
    if hits.isEmpty then .ok s log
    else
      let seen := seen ++ hits
      if rnd == maxR then .rejected "고쳐도 걸림" log
      else
        let new := c.filler (rnd + 1) hits
        if new.any (fun kv => !(hits.any (·.slot == kv.1))) then .rejected "걸리지 않은 빈칸을 바꾸려 함" log
        else if new.any (fun kv => seen.any fun h => h.slot == kv.1 && h.value == kv.2) then .rejected "이전에 걸린 값을 다시 냄" log
        else go c maxR fuel (rnd + 1) (update s new) seen log

def gate (c : Cfg) (maxR : Nat) (s : Slots) : Result := go c maxR (maxR + 1) 0 s [] []

def Result.logRev : Result → List Round
  | .ok _ l => l
  | .rejected _ l => l

def Result.log (r : Result) : List Round := r.logRev.reverse

def Result.reason : Result → Option String
  | .ok _ _ => none
  | .rejected r _ => some r

end NameHarness.Slots
