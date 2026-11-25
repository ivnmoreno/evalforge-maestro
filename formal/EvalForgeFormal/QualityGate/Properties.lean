import EvalForgeFormal.QualityGate.Aggregation

namespace EvalForgeFormal.QualityGate

/-! ## Precedence Order Properties (`FR-002`) -/

/-- Strict precedence chain: `pass < warning < inconclusive < fail`. -/
theorem precedence_strict_chain :
    GateDecision.pass < GateDecision.warning ∧
    GateDecision.warning < GateDecision.inconclusive ∧
    GateDecision.inconclusive < GateDecision.fail := by
  refine ⟨?_, ?_, ?_⟩ <;> decide

/-- Precedence order `≤` on `GateDecision` is total and antisymmetric. -/
theorem precedence_total (a b : GateDecision) :
    (a ≤ b ∨ b ≤ a) ∧ (a ≤ b → b ≤ a → a = b) := by
  cases a <;> cases b <;> decide

/-! ## Dominance Properties (`FR-004` #1–#3) -/

/-- Failure dominance: any non-empty `failureReasons` selects `.fail`. -/
theorem fail_dominates (s : ReasonState) (hf : s.failureReasons ≠ []) :
    selectDecision s = .fail := by
  cases s with
  | mk f i w =>
    cases f with
    | nil => exact False.elim (hf rfl)
    | cons _ _ => rfl

/-- Inconclusive dominance over warnings and passes when `failureReasons` is empty. -/
theorem inconclusive_dominates_warning_and_pass
    (s : ReasonState) (hf : s.failureReasons = []) (hi : s.inconclusiveReasons ≠ []) :
    selectDecision s = .inconclusive := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => cases hf
    | nil =>
      cases i with
      | nil => exact False.elim (hi rfl)
      | cons _ _ => rfl

/-- Warning dominance over passes when `failureReasons` and `inconclusiveReasons` are empty. -/
theorem warning_dominates_pass
    (s : ReasonState)
    (hf : s.failureReasons = [])
    (hi : s.inconclusiveReasons = [])
    (hw : s.warningReasons ≠ []) :
    selectDecision s = .warning := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => cases hf
    | nil =>
      cases i with
      | cons _ _ => cases hi
      | nil =>
        cases w with
        | nil => exact False.elim (hw rfl)
        | cons _ _ => rfl

/-! ## Complete Reason-to-Decision Biconditionals (`FR-004` #4–#5) -/

/-- Exact characterization of `FAIL`. -/
theorem selectDecision_eq_fail_iff (s : ReasonState) :
    selectDecision s = .fail ↔ s.failureReasons ≠ [] := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => simp [selectDecision]
    | nil =>
      cases i with
      | cons _ _ => simp [selectDecision]
      | nil =>
        cases w <;> simp [selectDecision]

/-- Exact characterization of `INCONCLUSIVE`. -/
theorem selectDecision_eq_inconclusive_iff (s : ReasonState) :
    selectDecision s = .inconclusive ↔ s.failureReasons = [] ∧ s.inconclusiveReasons ≠ [] := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => simp [selectDecision]
    | nil =>
      cases i with
      | cons _ _ => simp [selectDecision]
      | nil =>
        cases w <;> simp [selectDecision]

/-- Exact characterization of `WARNING`. -/
theorem selectDecision_eq_warning_iff (s : ReasonState) :
    selectDecision s = .warning ↔
      s.failureReasons = [] ∧ s.inconclusiveReasons = [] ∧ s.warningReasons ≠ [] := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => simp [selectDecision]
    | nil =>
      cases i with
      | cons _ _ => simp [selectDecision]
      | nil =>
        cases w <;> simp [selectDecision]

/-- Empty-reason pass equivalence: `PASS` iff all three reason lists are empty. -/
theorem selectDecision_eq_pass_iff (s : ReasonState) :
    selectDecision s = .pass ↔
      s.failureReasons = [] ∧ s.inconclusiveReasons = [] ∧ s.warningReasons = [] := by
  cases s with
  | mk f i w =>
    cases f with
    | cons _ _ => simp [selectDecision]
    | nil =>
      cases i with
      | cons _ _ => simp [selectDecision]
      | nil =>
        cases w <;> simp [selectDecision]

/-! ## Determinism & Non-Emptiness Invariance (`FR-004` #6) -/

/-- Deterministic decision selection: identical inputs always produce identical decisions. -/
theorem selectDecision_deterministic (s₁ s₂ : ReasonState) (h : s₁ = s₂) :
    selectDecision s₁ = selectDecision s₂ :=
  congrArg selectDecision h

/--
Decision selection depends strictly on reason-list emptiness flags (invariant to list
reordering, duplicates, and message text content).
-/
theorem selectDecision_depends_only_on_nonempty
    (s₁ s₂ : ReasonState)
    (hf : s₁.failureReasons.isEmpty = s₂.failureReasons.isEmpty)
    (hi : s₁.inconclusiveReasons.isEmpty = s₂.inconclusiveReasons.isEmpty)
    (hw : s₁.warningReasons.isEmpty = s₂.warningReasons.isEmpty) :
    selectDecision s₁ = selectDecision s₂ := by
  unfold selectDecision
  rw [hf, hi, hw]

/-! ## Exhaustive 8-State Classification (`FR-004` #7) -/

/-- Truth-table decision specification over the 8 boolean presence combinations. -/
def expectedDecisionForPresence (hasFail hasInconclusive hasWarning : Bool) : GateDecision :=
  match hasFail, hasInconclusive, hasWarning with
  | true, _, _ => .fail
  | false, true, _ => .inconclusive
  | false, false, true => .warning
  | false, false, false => .pass

/--
Exhaustive decision classification across all `2^3 = 8` boolean reason-presence states,
proving exact agreement and uniqueness for every combination.
-/
theorem selectDecision_exhaustive_eight_states (s : ReasonState) :
    let hasFail := !s.failureReasons.isEmpty
    let hasInc := !s.inconclusiveReasons.isEmpty
    let hasWarn := !s.warningReasons.isEmpty
    selectDecision s = expectedDecisionForPresence hasFail hasInc hasWarn ∧
    (∀ d : GateDecision,
      selectDecision s = d → d = expectedDecisionForPresence hasFail hasInc hasWarn) ∧
    ((hasFail = true ∧ hasInc = true ∧ hasWarn = true → selectDecision s = .fail) ∧
     (hasFail = true ∧ hasInc = true ∧ hasWarn = false → selectDecision s = .fail) ∧
     (hasFail = true ∧ hasInc = false ∧ hasWarn = true → selectDecision s = .fail) ∧
     (hasFail = true ∧ hasInc = false ∧ hasWarn = false → selectDecision s = .fail) ∧
     (hasFail = false ∧ hasInc = true ∧ hasWarn = true → selectDecision s = .inconclusive) ∧
     (hasFail = false ∧ hasInc = true ∧ hasWarn = false → selectDecision s = .inconclusive) ∧
     (hasFail = false ∧ hasInc = false ∧ hasWarn = true → selectDecision s = .warning) ∧
     (hasFail = false ∧ hasInc = false ∧ hasWarn = false → selectDecision s = .pass)) := by
  cases s with
  | mk f i w =>
    cases f <;> cases i <;> cases w <;>
      simp [selectDecision, expectedDecisionForPresence]

/-! ## Derived Acceptance/Blocking Flag Soundness (`FR-004` #8) -/

/-- `passed = true` iff `decision = .pass`. -/
theorem evaluateReasonState_passed_iff (s : ReasonState) :
    (evaluateReasonState s).passed = true ↔ (evaluateReasonState s).decision = .pass := by
  unfold evaluateReasonState
  cases selectDecision s <;> decide

/-- `blocking = true` iff `decision = .fail`. -/
theorem evaluateReasonState_blocking_iff (s : ReasonState) :
    (evaluateReasonState s).blocking = true ↔ (evaluateReasonState s).decision = .fail := by
  unfold evaluateReasonState
  cases selectDecision s <;> decide

/-- `passed` and `blocking` are mutually exclusive for every `ReasonState`. -/
theorem evaluateReasonState_passed_blocking_mutex (s : ReasonState) :
    ¬ ((evaluateReasonState s).passed = true ∧ (evaluateReasonState s).blocking = true) := by
  unfold evaluateReasonState
  cases selectDecision s <;> decide

/-- Both `WARNING` and `INCONCLUSIVE` yield `passed = false` and `blocking = false`. -/
theorem evaluateReasonState_warning_and_inconclusive_neither
    (s : ReasonState)
    (h : (evaluateReasonState s).decision = .warning ∨
         (evaluateReasonState s).decision = .inconclusive) :
    (evaluateReasonState s).passed = false ∧ (evaluateReasonState s).blocking = false := by
  unfold evaluateReasonState at h ⊢
  cases hd : selectDecision s <;> simp_all <;> decide

/-! ## `_RuleRecorder` Partitioning & Check-to-Decision Correspondence (`FR-004` #9) -/

private theorem foldl_recordCheck_failure_nonempty_iff
    (s : ReasonState) (checks : List RuleCheck) :
    (checks.foldl recordCheck s).failureReasons ≠ [] ↔
      s.failureReasons ≠ [] ∨ ∃ c ∈ checks, c.status = .fail := by
  induction checks generalizing s with
  | nil => simp
  | cons c cs ih =>
    simp only [List.foldl_cons, List.mem_cons]
    rw [ih]
    cases hst : c.status with
    | fail =>
      simp [recordCheck, hst]
    | inconclusive =>
      simp [recordCheck, hst]
    | warning =>
      simp [recordCheck, hst]
    | pass =>
      simp [recordCheck, hst]

private theorem foldl_recordCheck_inconclusive_nonempty_iff
    (s : ReasonState) (checks : List RuleCheck) :
    (checks.foldl recordCheck s).inconclusiveReasons ≠ [] ↔
      s.inconclusiveReasons ≠ [] ∨ ∃ c ∈ checks, c.status = .inconclusive := by
  induction checks generalizing s with
  | nil => simp
  | cons c cs ih =>
    simp only [List.foldl_cons, List.mem_cons]
    rw [ih]
    cases hst : c.status with
    | fail =>
      simp [recordCheck, hst]
    | inconclusive =>
      simp [recordCheck, hst]
    | warning =>
      simp [recordCheck, hst]
    | pass =>
      simp [recordCheck, hst]

private theorem foldl_recordCheck_warning_nonempty_iff
    (s : ReasonState) (checks : List RuleCheck) :
    (checks.foldl recordCheck s).warningReasons ≠ [] ↔
      s.warningReasons ≠ [] ∨ ∃ c ∈ checks, c.status = .warning := by
  induction checks generalizing s with
  | nil => simp
  | cons c cs ih =>
    simp only [List.foldl_cons, List.mem_cons]
    rw [ih]
    cases hst : c.status with
    | fail =>
      simp [recordCheck, hst]
    | inconclusive =>
      simp [recordCheck, hst]
    | warning =>
      simp [recordCheck, hst]
    | pass =>
      simp [recordCheck, hst]

/-- `failureReasons` is non-empty iff at least one recorded check has status `.fail`. -/
theorem recordChecks_failure_nonempty_iff (checks : List RuleCheck) :
    (recordChecks checks).failureReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .fail := by
  simpa [recordChecks, ReasonState.empty] using
    foldl_recordCheck_failure_nonempty_iff ReasonState.empty checks

/-- `inconclusiveReasons` is non-empty iff at least one recorded check has status `.inconclusive`. -/
theorem recordChecks_inconclusive_nonempty_iff (checks : List RuleCheck) :
    (recordChecks checks).inconclusiveReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .inconclusive := by
  simpa [recordChecks, ReasonState.empty] using
    foldl_recordCheck_inconclusive_nonempty_iff ReasonState.empty checks

/-- `warningReasons` is non-empty iff at least one recorded check has status `.warning`. -/
theorem recordChecks_warning_nonempty_iff (checks : List RuleCheck) :
    (recordChecks checks).warningReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .warning := by
  simpa [recordChecks, ReasonState.empty] using
    foldl_recordCheck_warning_nonempty_iff ReasonState.empty checks

/-- Aggregated decision is `FAIL` iff at least one check has status `.fail`. -/
theorem evaluateChecks_eq_fail_iff (checks : List RuleCheck) :
    (evaluateChecks checks).decision = .fail ↔ ∃ c ∈ checks, c.status = .fail := by
  unfold evaluateChecks evaluateReasonState
  dsimp only
  rw [selectDecision_eq_fail_iff, recordChecks_failure_nonempty_iff]

/-- Aggregated decision is `PASS` iff every recorded check has status `.pass`. -/
theorem evaluateChecks_eq_pass_iff (checks : List RuleCheck) :
    (evaluateChecks checks).decision = .pass ↔ ∀ c ∈ checks, c.status = .pass := by
  unfold evaluateChecks evaluateReasonState
  dsimp only
  rw [selectDecision_eq_pass_iff]
  constructor
  · intro ⟨hf, hi, hw⟩ c hc
    cases hst : c.status with
    | pass => rfl
    | fail =>
      have hne : (recordChecks checks).failureReasons ≠ [] :=
        (recordChecks_failure_nonempty_iff checks).2 ⟨c, hc, hst⟩
      exact False.elim (hne hf)
    | inconclusive =>
      have hne : (recordChecks checks).inconclusiveReasons ≠ [] :=
        (recordChecks_inconclusive_nonempty_iff checks).2 ⟨c, hc, hst⟩
      exact False.elim (hne hi)
    | warning =>
      have hne : (recordChecks checks).warningReasons ≠ [] :=
        (recordChecks_warning_nonempty_iff checks).2 ⟨c, hc, hst⟩
      exact False.elim (hne hw)
  · intro hall
    refine ⟨?_, ?_, ?_⟩
    · cases hf : (recordChecks checks).failureReasons with
      | nil => rfl
      | cons x xs =>
        have hne : (recordChecks checks).failureReasons ≠ [] := by simp [hf]
        obtain ⟨c, hc, hst⟩ := (recordChecks_failure_nonempty_iff checks).1 hne
        have hp := hall c hc
        rw [hp] at hst
        exact False.elim (GateDecision.noConfusion hst)
    · cases hi : (recordChecks checks).inconclusiveReasons with
      | nil => rfl
      | cons x xs =>
        have hne : (recordChecks checks).inconclusiveReasons ≠ [] := by simp [hi]
        obtain ⟨c, hc, hst⟩ := (recordChecks_inconclusive_nonempty_iff checks).1 hne
        have hp := hall c hc
        rw [hp] at hst
        exact False.elim (GateDecision.noConfusion hst)
    · cases hw : (recordChecks checks).warningReasons with
      | nil => rfl
      | cons x xs =>
        have hne : (recordChecks checks).warningReasons ≠ [] := by simp [hw]
        obtain ⟨c, hc, hst⟩ := (recordChecks_warning_nonempty_iff checks).1 hne
        have hp := hall c hc
        rw [hp] at hst
        exact False.elim (GateDecision.noConfusion hst)

private theorem isEmpty_eq_of_ne_nil_iff {α : Type} {l₁ l₂ : List α}
    (h : l₁ ≠ [] ↔ l₂ ≠ []) :
    l₁.isEmpty = l₂.isEmpty := by
  cases l₁ with
  | nil =>
    cases l₂ with
    | nil => rfl
    | cons _ _ =>
      have : ([] : List α) ≠ [] := h.2 (by simp)
      exact False.elim (this rfl)
  | cons _ _ =>
    cases l₂ with
    | nil =>
      have : ([] : List α) ≠ [] := h.1 (by simp)
      exact False.elim (this rfl)
    | cons _ _ => rfl

/--
Final `GateOutcome` is invariant under any permutation, duplication, or rewriting of
`RuleCheck` lists that preserves the set of present rule statuses.
-/
theorem evaluateChecks_status_set_invariance
    (checks₁ checks₂ : List RuleCheck)
    (h : ∀ st : GateDecision,
      (∃ c ∈ checks₁, c.status = st) ↔ (∃ c ∈ checks₂, c.status = st)) :
    evaluateChecks checks₁ = evaluateChecks checks₂ := by
  have hf : (recordChecks checks₁).failureReasons.isEmpty =
      (recordChecks checks₂).failureReasons.isEmpty :=
    isEmpty_eq_of_ne_nil_iff
      ((recordChecks_failure_nonempty_iff checks₁).trans
        ((h .fail).trans (recordChecks_failure_nonempty_iff checks₂).symm))
  have hi : (recordChecks checks₁).inconclusiveReasons.isEmpty =
      (recordChecks checks₂).inconclusiveReasons.isEmpty :=
    isEmpty_eq_of_ne_nil_iff
      ((recordChecks_inconclusive_nonempty_iff checks₁).trans
        ((h .inconclusive).trans (recordChecks_inconclusive_nonempty_iff checks₂).symm))
  have hw : (recordChecks checks₁).warningReasons.isEmpty =
      (recordChecks checks₂).warningReasons.isEmpty :=
    isEmpty_eq_of_ne_nil_iff
      ((recordChecks_warning_nonempty_iff checks₁).trans
        ((h .warning).trans (recordChecks_warning_nonempty_iff checks₂).symm))
  have hd : selectDecision (recordChecks checks₁) = selectDecision (recordChecks checks₂) :=
    selectDecision_depends_only_on_nonempty (recordChecks checks₁) (recordChecks checks₂) hf hi hw
  unfold evaluateChecks evaluateReasonState
  rw [hd]

end EvalForgeFormal.QualityGate
