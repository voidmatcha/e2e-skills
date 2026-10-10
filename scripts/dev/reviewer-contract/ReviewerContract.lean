-- SPDX-License-Identifier: Apache-2.0
/-!
# e2e-reviewer severity contract

Core Lean 4, no Mathlib. The pattern list and catalog severities are generated from the skill by
`scripts/dev/reviewer-contract.py --write`; the instance rules and theorems are written by hand
from `skills/e2e-reviewer/references/pattern-reference.md` and `references/reporting.md`.

The fields of `Judgment` are what a reviewer settles by reading the code under review. Every `def`
fixes what follows from them. The theorems are checked facts about these definitions.
-/

namespace E2EReviewer

inductive Severity | P0 | P1 | P2
  deriving DecidableEq, Repr

/-- Rank for comparison: P0 is the most severe. -/
def Severity.rank : Severity → Nat
  | .P0 => 0 | .P1 => 1 | .P2 => 2

/-- The more severe of two severities. -/
def Severity.worst (a b : Severity) : Severity := if a.rank ≤ b.rank then a else b

def Severity.label : Severity → String
  | .P0 => "P0" | .P1 => "P1" | .P2 => "P2"

-- BEGIN GENERATED: scripts/dev/reviewer-contract.py --write
/-- Every reportable pattern ID, as finding headings and the holdout scorer use it. -/
inductive Pattern
  | p1
  | p2
  | p3
  | p3b
  | p4a
  | p4b
  | p4c_4e
  | p4f
  | p4g
  | p4h
  | p4i
  | p4j
  | p4k
  | p5a
  | p5b
  | p6
  | p7
  | p8
  | p8a
  | p8b
  | p8c
  | p9
  | p9b
  | p9c
  | p10
  | p10a
  | p10b
  | p10c
  | p10d
  | p10e
  | p10f
  | p11
  | p11c
  | p12
  | p13
  | p14
  | p15
  | p16
  | p17
  | p18
  | p19
  | p20
  | p21
  | p22
  | p23
  deriving DecidableEq, Repr

def Pattern.id : Pattern → String
  | .p1 => "1"
  | .p2 => "2"
  | .p3 => "3"
  | .p3b => "3b"
  | .p4a => "4a"
  | .p4b => "4b"
  | .p4c_4e => "4c-4e"
  | .p4f => "4f"
  | .p4g => "4g"
  | .p4h => "4h"
  | .p4i => "4i"
  | .p4j => "4j"
  | .p4k => "4k"
  | .p5a => "5a"
  | .p5b => "5b"
  | .p6 => "6"
  | .p7 => "7"
  | .p8 => "8"
  | .p8a => "8a"
  | .p8b => "8b"
  | .p8c => "8c"
  | .p9 => "9"
  | .p9b => "9b"
  | .p9c => "9c"
  | .p10 => "10"
  | .p10a => "10a"
  | .p10b => "10b"
  | .p10c => "10c"
  | .p10d => "10d"
  | .p10e => "10e"
  | .p10f => "10f"
  | .p11 => "11"
  | .p11c => "11c"
  | .p12 => "12"
  | .p13 => "13"
  | .p14 => "14"
  | .p15 => "15"
  | .p16 => "16"
  | .p17 => "17"
  | .p18 => "18"
  | .p19 => "19"
  | .p20 => "20"
  | .p21 => "21"
  | .p22 => "22"
  | .p23 => "23"

/-- The Quick Reference severity: each pattern's usual case, not a verdict. -/
def catalogSeverity : Pattern → Severity
  | .p1 => .P0
  | .p2 => .P0
  | .p3 => .P0
  | .p3b => .P0
  | .p4a => .P0
  | .p4b => .P1
  | .p4c_4e => .P1
  | .p4f => .P0
  | .p4g => .P1
  | .p4h => .P1
  | .p4i => .P1
  | .p4j => .P1
  | .p4k => .P1
  | .p5a => .P0
  | .p5b => .P1
  | .p6 => .P1
  | .p7 => .P0
  | .p8 => .P0
  | .p8a => .P0
  | .p8b => .P0
  | .p8c => .P0
  | .p9 => .P1
  | .p9b => .P1
  | .p9c => .P1
  | .p10 => .P1
  | .p10a => .P1
  | .p10b => .P1
  | .p10c => .P1
  | .p10d => .P1
  | .p10e => .P1
  | .p10f => .P1
  | .p11 => .P2
  | .p11c => .P2
  | .p12 => .P0
  | .p13 => .P1
  | .p14 => .P1
  | .p15 => .P1
  | .p16 => .P1
  | .p17 => .P1
  | .p18 => .P1
  | .p19 => .P1
  | .p20 => .P1
  | .p21 => .P2
  | .p22 => .P1
  | .p23 => .P2
-- END GENERATED

/-- What a reviewer judges about one instance. -/
structure Judgment where
  /-- How many outcomes the test promises (title, action, or acceptance contract) that it really
      verifies. -/
  verified : Nat
  /-- The test stays green when the feature is broken. -/
  passesWhenBroken : Bool
  /-- #23 only: a negative or empty-state assertion passes because a render guard hid the seeded
      items. -/
  guardHidesSeed : Bool

/-- The P0 definition in reporting.md: both halves are required. -/
def meetsP0Definition (j : Judgment) : Bool := j.passesWhenBroken && j.verified == 0

/-- The documented instance rules: `#1` is P0 when no promised outcome is verified and P1 when
    one is (pattern-reference.md #1 Severity); `#23` is P0 for the guard-hidden variant and P2
    otherwise (pattern-reference.md #23 Severity). -/
def instanceSeverity : Pattern → Judgment → Option Severity
  | .p1 => fun j => some (if j.verified = 0 then .P0 else .P1)
  | .p23 => fun j => some (if j.guardHidesSeed then .P0 else .P2)
  | _ => fun _ => none

/-- Severity of one instance: a documented instance rule, else P0 when the instance meets the P0
    definition outright (reporting.md), else the catalog severity. -/
def severity (p : Pattern) (j : Judgment) : Severity :=
  match instanceSeverity p j with
  | some s => s
  | none => if meetsP0Definition j then .P0 else catalogSeverity p

/-- A consolidated finding takes the most severe of its patterns. -/
def worstOf (ps : List (Pattern × Judgment)) : Severity :=
  ps.foldl (fun acc pj => acc.worst (severity pj.1 pj.2)) .P2

/-- `#1 #9`: every pattern ID of a consolidated block, each with its `#`. -/
def idList (ps : List (Pattern × Judgment)) : String :=
  " ".intercalate (ps.map (fun pj => "#" ++ pj.1.id))

/-- The finding heading from reporting.md: it always names the pattern IDs. -/
def heading (ps : List (Pattern × Judgment)) (file title : String) : String :=
  "## [" ++ (worstOf ps).label ++ "] " ++ file ++ " — " ++ idList ps ++ " " ++ title

/-! ## Checked facts -/

/-- Outside a documented instance rule, a severity never moves below its catalog severity: the
    only change is up to P0 when the P0 definition is met. -/
theorem no_undocumented_downgrade (p : Pattern) (j : Judgment) (h : instanceSeverity p j = none) :
    severity p j = catalogSeverity p ∨ severity p j = .P0 := by
  unfold severity; rw [h]; by_cases hp : meetsP0Definition j = true <;> simp [hp]

/-- `#1` with nothing verified is P0; with something verified it is P1, never P0. -/
theorem name_assertion (j : Judgment) :
    severity .p1 j = (if j.verified = 0 then .P0 else .P1) := by
  simp [severity, instanceSeverity]

/-- Only the guard variant moves `#23` off P2. -/
theorem fixture_guard (j : Judgment) :
    severity .p23 j = (if j.guardHidesSeed then .P0 else .P2) := by
  simp [severity, instanceSeverity]

/-- An instance that verifies something it promised never meets the P0 definition. -/
theorem partial_verification_not_p0_definition (j : Judgment) (h : j.verified ≠ 0) :
    meetsP0Definition j = false := by
  simp [meetsP0Definition, h]

/-- Consolidation never reports a block as less severe than either side. -/
theorem worst_le_left (a b : Severity) : (a.worst b).rank ≤ a.rank := by
  cases a <;> cases b <;> decide

theorem worst_le_right (a b : Severity) : (a.worst b).rank ≤ b.rank := by
  cases a <;> cases b <;> decide

/-- A single-pattern heading contains `#` followed by the pattern ID. -/
theorem heading_names_id (p : Pattern) (j : Judgment) (file title : String) :
    heading [(p, j)] file title =
      "## [" ++ (worstOf [(p, j)]).label ++ "] " ++ file ++ " — " ++ ("#" ++ p.id) ++ " " ++ title := by
  simp [heading, idList]

end E2EReviewer
