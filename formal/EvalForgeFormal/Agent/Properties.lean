import EvalForgeFormal.Agent.Metrics

namespace EvalForgeFormal.Agent

open EvalForgeFormal.Retrieval (NNRat enumFrom dedupPreserveFirst)

/-! ## Elementary Pure-Core Rational & List Helpers -/

private theorem nnratMin_le_left (a b : NNRat) : nnratMin a b ≤ a := by
  unfold nnratMin
  cases h : NNRat.leBool a b
  · exact NNRat.le_of_lt ((NNRat.leBool_false_iff a b).mp h)
  · exact NNRat.le_refl a

private theorem nnratMin_le_right (a b : NNRat) : nnratMin a b ≤ b := by
  unfold nnratMin
  cases h : NNRat.leBool a b
  · exact NNRat.le_refl b
  · exact (NNRat.leBool_true_iff a b).mp h

private theorem le_nnratMin {a b c : NNRat} (ha : c ≤ a) (hb : c ≤ b) : c ≤ nnratMin a b := by
  unfold nnratMin
  cases NNRat.leBool a b
  · exact hb
  · exact ha

private theorem nnratMin_mono {a₁ a₂ b₁ b₂ : NNRat} (ha : a₁ ≤ a₂) (hb : b₁ ≤ b₂) :
    nnratMin a₁ b₁ ≤ nnratMin a₂ b₂ :=
  le_nnratMin (NNRat.le_trans (nnratMin_le_left a₁ b₁) ha)
    (NNRat.le_trans (nnratMin_le_right a₁ b₁) hb)

private theorem left_le_nnratMax (a b : NNRat) : a ≤ nnratMax a b := by
  unfold nnratMax
  cases h : NNRat.leBool a b
  · exact NNRat.le_refl a
  · exact (NNRat.leBool_true_iff a b).mp h

private theorem right_le_nnratMax (a b : NNRat) : b ≤ nnratMax a b := by
  unfold nnratMax
  cases h : NNRat.leBool a b
  · exact NNRat.le_of_lt ((NNRat.leBool_false_iff a b).mp h)
  · exact NNRat.le_refl b

private theorem nodup_length_le_of_subset {α : Type} {a b : List α}
    (hnd : a.Nodup) (hsub : ∀ x ∈ a, x ∈ b) : a.length ≤ b.length := by
  induction a generalizing b with
  | nil => exact Nat.zero_le _
  | cons x xs ih =>
    rw [List.nodup_cons] at hnd
    have hxMem : x ∈ b := hsub x (List.mem_cons_self ..)
    obtain ⟨b₁, b₂, rfl⟩ := List.mem_iff_append.mp hxMem
    have hsub' : ∀ y ∈ xs, y ∈ b₁ ++ b₂ := by
      intro y hy
      have hyB : y ∈ b₁ ++ x :: b₂ := hsub y (List.mem_cons_of_mem x hy)
      rw [List.mem_append, List.mem_cons] at hyB
      rw [List.mem_append]
      rcases hyB with h1 | rfl | h2
      · exact Or.inl h1
      · exact False.elim (hnd.1 hy)
      · exact Or.inr h2
    have hle := ih hnd.2 hsub'
    simp only [List.length_cons, List.length_append] at hle ⊢
    omega

private theorem nodup_length_eq_of_mem_iff {α : Type} {a b : List α}
    (ha : a.Nodup) (hb : b.Nodup) (hmem : ∀ x, x ∈ a ↔ x ∈ b) : a.length = b.length :=
  Nat.le_antisymm
    (nodup_length_le_of_subset ha (fun x hx => (hmem x).mp hx))
    (nodup_length_le_of_subset hb (fun x hx => (hmem x).mpr hx))

private theorem filter_length_add_not {α : Type} (p : α → Bool) (xs : List α) :
    (xs.filter p).length + (xs.filter (fun x => !p x)).length = xs.length := by
  induction xs with
  | nil => rfl
  | cons x xs ih =>
    cases hp : p x <;> simp [hp] <;> omega

private theorem dedupPreserveFirstAux_not_mem_seen (seen xs : List String) :
    ∀ y ∈ EvalForgeFormal.Retrieval.dedupPreserveFirstAux seen xs, y ∉ seen := by
  induction xs generalizing seen with
  | nil => intro _ h; cases h
  | cons x xs ih =>
    intro y hy
    unfold EvalForgeFormal.Retrieval.dedupPreserveFirstAux at hy
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte] at hy
      exact ih seen y hy
    · simp only [hseen, ↓reduceIte, List.mem_cons] at hy
      rcases hy with rfl | htail
      · exact hseen
      · intro hySeen
        exact ih (x :: seen) y htail (List.mem_cons_of_mem x hySeen)

private theorem dedupPreserveFirstAux_nodup (seen xs : List String) :
    (EvalForgeFormal.Retrieval.dedupPreserveFirstAux seen xs).Nodup := by
  induction xs generalizing seen with
  | nil => exact List.nodup_nil
  | cons x xs ih =>
    unfold EvalForgeFormal.Retrieval.dedupPreserveFirstAux
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte]
      exact ih seen
    · simp only [hseen, ↓reduceIte, List.nodup_cons]
      refine ⟨?_, ih (x :: seen)⟩
      intro hxTail
      exact dedupPreserveFirstAux_not_mem_seen (x :: seen) xs x hxTail (List.mem_cons_self ..)

private theorem dedupPreserveFirstAux_mem_iff (seen xs : List String) (y : String) :
    y ∈ EvalForgeFormal.Retrieval.dedupPreserveFirstAux seen xs ↔ y ∈ xs ∧ y ∉ seen := by
  induction xs generalizing seen with
  | nil => simp [EvalForgeFormal.Retrieval.dedupPreserveFirstAux]
  | cons x xs ih =>
    unfold EvalForgeFormal.Retrieval.dedupPreserveFirstAux
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte, ih, List.mem_cons]
      constructor
      · rintro ⟨hyXs, hyNotSeen⟩
        exact ⟨Or.inr hyXs, hyNotSeen⟩
      · rintro ⟨rfl | hyXs, hyNotSeen⟩
        · exact False.elim (hyNotSeen hseen)
        · exact ⟨hyXs, hyNotSeen⟩
    · simp only [hseen, ↓reduceIte, List.mem_cons, ih]
      constructor
      · rintro (rfl | ⟨hyXs, hyNotSeen'⟩)
        · exact ⟨Or.inl rfl, hseen⟩
        · exact ⟨Or.inr hyXs, fun h => hyNotSeen' (Or.inr h)⟩
      · rintro ⟨rfl | hyXs, hyNotSeen⟩
        · exact Or.inl rfl
        · by_cases hyx : y = x
          · exact Or.inl hyx
          · exact Or.inr ⟨hyXs, by rintro (rfl | h); exact hyx rfl; exact hyNotSeen h⟩

private theorem dedupPreserveFirst_nodup' (xs : List String) :
    (dedupPreserveFirst xs).Nodup :=
  dedupPreserveFirstAux_nodup [] xs

private theorem dedupPreserveFirst_mem_iff' (xs : List String) (y : String) :
    y ∈ dedupPreserveFirst xs ↔ y ∈ xs := by
  simpa [dedupPreserveFirst] using dedupPreserveFirstAux_mem_iff [] xs y

private theorem enumFrom_length {α : Type} (k : Nat) (xs : List α) :
    (enumFrom k xs).length = xs.length := by
  induction xs generalizing k with
  | nil => rfl
  | cons _ _ ih => simp [enumFrom, ih]

private theorem enumFrom_map_snd {α : Type} (k : Nat) (xs : List α) :
    (enumFrom k xs).map Prod.snd = xs := by
  induction xs generalizing k with
  | nil => rfl
  | cons _ _ ih => simp [enumFrom, ih]

private theorem mem_enumFrom_lt {α : Type} (k : Nat) (xs : List α) {i : Nat} {x : α}
    (h : (i, x) ∈ enumFrom k xs) : k ≤ i ∧ i < k + xs.length := by
  induction xs generalizing k with
  | nil => cases h
  | cons y ys ih =>
    simp only [enumFrom, List.mem_cons, Prod.mk.injEq] at h
    rcases h with ⟨rfl, _⟩ | htl
    · simp only [List.length_cons]; omega
    · have hrec := ih (k + 1) htl
      simp only [List.length_cons]
      omega

private theorem enumFrom_pairwise_lt {α : Type} (k : Nat) (xs : List α) :
    List.Pairwise (fun a b => a.1 < b.1) (enumFrom k xs) := by
  induction xs generalizing k with
  | nil => exact List.Pairwise.nil
  | cons y ys ih =>
    simp only [enumFrom, List.pairwise_cons]
    refine ⟨?_, ih (k + 1)⟩
    intro p hp
    have hlt := mem_enumFrom_lt (k + 1) ys hp
    omega

/-! ## Group 1 — Guard Precedence & Threshold Finalization (`5` Theorems) -/

/-- Theorem 1: Per-metric threshold override in `criteria.metricThresholds` takes top precedence. -/
theorem resolveThreshold_metric_override
    (criteria : AgentCriteria) (metricId : String) (defaultThreshold t : NNRat)
    (h : lookupMetricThreshold criteria.metricThresholds metricId = some t) :
    resolveThreshold criteria metricId defaultThreshold = t := by
  unfold resolveThreshold
  rw [h]

/-- Theorem 2: Case-level `passThreshold` takes precedence over metric default when no per-metric override exists. -/
theorem resolveThreshold_pass_fallback
    (criteria : AgentCriteria) (metricId : String) (defaultThreshold p : NNRat)
    (hNone : lookupMetricThreshold criteria.metricThresholds metricId = none)
    (hPass : criteria.passThreshold = some p) :
    resolveThreshold criteria metricId defaultThreshold = p := by
  unfold resolveThreshold
  rw [hNone, hPass]

/-- Theorem 3: Metric default threshold is used when neither `metricThresholds` nor `passThreshold` applies. -/
theorem resolveThreshold_default_fallback
    (criteria : AgentCriteria) (metricId : String) (defaultThreshold : NNRat)
    (hNone : lookupMetricThreshold criteria.metricThresholds metricId = none)
    (hPassNone : criteria.passThreshold = none) :
    resolveThreshold criteria metricId defaultThreshold = defaultThreshold := by
  unfold resolveThreshold
  rw [hNone, hPassNone]

/--
Theorem 4: Non-empty `execution.errors` unconditionally forces `INCONCLUSIVE` (`score = none`)
across all six deterministic agent metrics, superseding `NOT_APPLICABLE` and numeric scoring.
-/
theorem evaluate_errors_inconclusive_all_six
    (errors : List String) (hErr : errors ≠ [])
    (expected : List ExpectedTool) (topCalls : List ToolCall) (trace : List TraceStep)
    (criteria : AgentCriteria) (defaultThreshold loopPenalty : NNRat)
    (selMode : ToolSelectionMode) (strictMode : Bool) (schemaOracle : SchemaOracle)
    (seqMode : SequenceMode) (defMaxSteps defMaxCalls : Option Nat) (defAllowRepeats : Nat)
    (metricForbTools metricForbPatterns : List String) :
    let o1 := evaluateToolSelection selMode errors expected topCalls trace criteria defaultThreshold
    let o2 := evaluateArgumentCorrectness strictMode errors expected topCalls trace schemaOracle criteria defaultThreshold
    let o3 := evaluateExecutionSequence seqMode errors expected topCalls trace criteria defaultThreshold
    let o4 := evaluateToolEfficiency defMaxSteps defMaxCalls defAllowRepeats loopPenalty errors topCalls trace criteria defaultThreshold
    let o5 := evaluatePolicyCompliance metricForbTools metricForbPatterns errors topCalls trace criteria defaultThreshold
    let o6 := evaluateFailureRecovery errors topCalls trace criteria defaultThreshold
    (o1.status = .inconclusive ∧ o1.score = none) ∧
    (o2.status = .inconclusive ∧ o2.score = none) ∧
    (o3.status = .inconclusive ∧ o3.score = none) ∧
    (o4.status = .inconclusive ∧ o4.score = none) ∧
    (o5.status = .inconclusive ∧ o5.score = none) ∧
    (o6.status = .inconclusive ∧ o6.score = none) := by
  cases errors with
  | nil => exact False.elim (hErr rfl)
  | cons _ _ =>
    simp [evaluateToolSelection, evaluateArgumentCorrectness, evaluateExecutionSequence,
      evaluateToolEfficiency, evaluatePolicyCompliance, evaluateFailureRecovery]

/-- Theorem 5: `finalizeAgentMetric` emits `PASS` iff `threshold ≤ score`, `FAIL` iff `score < threshold`, and preserves `some score`. -/
theorem finalizeAgentMetric_pass_fail_sound (score threshold : NNRat) :
    let out := finalizeAgentMetric score threshold
    out.score = some score ∧
    out.threshold = threshold ∧
    (out.status = .pass ↔ threshold ≤ score) ∧
    (out.status = .fail ↔ score < threshold) := by
  dsimp only
  unfold finalizeAgentMetric
  cases h : NNRat.leBool threshold score
  · have hlt : score < threshold := (NNRat.leBool_false_iff threshold score).mp h
    have hnle : ¬ (threshold ≤ score) := (NNRat.lt_iff_not_le score threshold).mp hlt
    simp [hlt, hnle]
  · have hle : threshold ≤ score := (NNRat.leBool_true_iff threshold score).mp h
    have hnlt : ¬ (score < threshold) := fun hc => ((NNRat.lt_iff_not_le score threshold).mp hc) hle
    simp [hle, hnlt]

/-! ## Group 2 — Preparation, Deduplication & Ordering (`4` Theorems) -/

private def callDedupInv (calls : List ToolCall) (seen : List String) : Prop :=
  (calls.filterMap ToolCall.id).Nodup ∧
  ∀ cid, cid ∈ calls.filterMap ToolCall.id → cid ∈ seen

private theorem appendUniqueCall_preserves_inv (calls : List ToolCall) (seen : List String)
    (c : ToolCall) (hInv : callDedupInv calls seen) :
    let st := appendUniqueCall calls seen c
    callDedupInv st.1 st.2 := by
  obtain ⟨hNd, hSub⟩ := hInv
  unfold appendUniqueCall
  cases hid : c.id with
  | none =>
    refine ⟨?_, ?_⟩
    · simp only [List.filterMap_append, List.filterMap_cons, hid, List.filterMap_nil, List.append_nil]
      exact hNd
    · intro cid hcid
      simp only [List.filterMap_append, List.filterMap_cons, hid, List.filterMap_nil, List.append_nil] at hcid
      exact hSub cid hcid
  | some newId =>
    by_cases hIn : newId ∈ seen
    · simp only [hIn, ↓reduceIte]
      exact ⟨hNd, hSub⟩
    · simp only [hIn, ↓reduceIte]
      refine ⟨?_, ?_⟩
      · simp only [List.filterMap_append, List.filterMap_cons, hid, List.filterMap_nil]
        rw [List.nodup_append]
        refine ⟨hNd, List.nodup_cons.mpr ⟨by simp, List.nodup_nil⟩, ?_⟩
        intro a ha b hb hEq
        simp only [List.mem_singleton] at hb
        subst hb
        subst hEq
        exact hIn (hSub a ha)
      · intro cid hcid
        simp only [List.filterMap_append, List.filterMap_cons, hid, List.filterMap_nil,
          List.mem_append, List.mem_singleton] at hcid
        rcases hcid with hOld | rfl
        · exact List.mem_cons_of_mem newId (hSub cid hOld)
        · exact List.mem_cons_self ..

private theorem foldl_appendUniqueCall_preserves_inv
    (nested : List ToolCall) (st : List ToolCall × List String)
    (hInv : callDedupInv st.1 st.2) :
    let st' := nested.foldl (fun s c => appendUniqueCall s.1 s.2 c) st
    callDedupInv st'.1 st'.2 := by
  induction nested generalizing st with
  | nil => exact hInv
  | cons c cs ih =>
    simp only [List.foldl_cons]
    exact ih (appendUniqueCall st.1 st.2 c) (appendUniqueCall_preserves_inv st.1 st.2 c hInv)

private theorem mergeTraceStep_preserves_inv (st : List ToolCall × List String) (step : TraceStep)
    (hInv : callDedupInv st.1 st.2) :
    let st' := mergeTraceStep st step
    callDedupInv st'.1 st'.2 := by
  unfold mergeTraceStep
  by_cases hEmpty : step.toolCalls.isEmpty
  · simp only [hEmpty, Bool.not_true, Bool.false_eq_true, ↓reduceIte]
    cases step.kind <;> cases step.name <;> try exact hInv
    exact appendUniqueCall_preserves_inv st.1 st.2 _ hInv
  · simp only [hEmpty, Bool.not_false, ↓reduceIte]
    exact foldl_appendUniqueCall_preserves_inv step.toolCalls st hInv

private theorem foldl_mergeTraceStep_preserves_inv
    (trace : List TraceStep) (st : List ToolCall × List String)
    (hInv : callDedupInv st.1 st.2) :
    let st' := trace.foldl mergeTraceStep st
    callDedupInv st'.1 st'.2 := by
  induction trace generalizing st with
  | nil => exact hInv
  | cons s ss ih =>
    simp only [List.foldl_cons]
    exact ih (mergeTraceStep st s) (mergeTraceStep_preserves_inv st s hInv)

private theorem enrichToolCall_preserves_id (results : List (String × TraceStep)) (call : ToolCall) :
    (enrichToolCall results call).id = call.id := by
  unfold enrichToolCall
  cases h : call.id with
  | none => simp [h]
  | some cid =>
    cases hLook : lookupToolResult results cid <;> simp [h, hLook]

private theorem enrichToolCall_preserves_name (results : List (String × TraceStep)) (call : ToolCall) :
    (enrichToolCall results call).name = call.name := by
  unfold enrichToolCall
  cases h : call.id with
  | none => simp
  | some cid =>
    cases hLook : lookupToolResult results cid <;> simp [hLook]

/--
Theorem 6: Given duplicate-free top-level non-`none` call IDs, `prepareAgentInputs` produces a
merged and enriched call list whose non-`none` IDs are strictly duplicate-free (`Nodup`).
-/
theorem prepareAgentInputs_id_dedup_unique
    (topCalls : List ToolCall) (trace : List TraceStep)
    (hTopNodup : (topCalls.filterMap ToolCall.id).Nodup) :
    ((prepareAgentInputs topCalls trace).filterMap ToolCall.id).Nodup := by
  unfold prepareAgentInputs collectRawCalls
  have hInv : callDedupInv topCalls (topCalls.filterMap ToolCall.id) :=
    ⟨hTopNodup, fun _ h => h⟩
  have hMerged := foldl_mergeTraceStep_preserves_inv trace (topCalls, topCalls.filterMap ToolCall.id) hInv
  have hMapEq :
      (((trace.foldl mergeTraceStep (topCalls, topCalls.filterMap ToolCall.id)).1.map
        (enrichToolCall (collectToolResults trace))).filterMap ToolCall.id) =
      ((trace.foldl mergeTraceStep (topCalls, topCalls.filterMap ToolCall.id)).1.filterMap ToolCall.id) := by
    rw [List.filterMap_map]
    have hComp : (ToolCall.id ∘ enrichToolCall (collectToolResults trace)) = ToolCall.id := by
      funext c
      exact enrichToolCall_preserves_id (collectToolResults trace) c
    rw [hComp]
  rw [hMapEq]
  exact hMerged.1

/--
Theorem 7: `TOOL_RESULT` enrichment preserves call count, call IDs, and call names verbatim.
-/
theorem prepareAgentInputs_enrichment_preserves_length
    (topCalls : List ToolCall) (trace : List TraceStep) :
    (prepareAgentInputs topCalls trace).length = (collectRawCalls topCalls trace).length ∧
    (prepareAgentInputs topCalls trace).map ToolCall.id = (collectRawCalls topCalls trace).map ToolCall.id ∧
    (prepareAgentInputs topCalls trace).map ToolCall.name = (collectRawCalls topCalls trace).map ToolCall.name := by
  unfold prepareAgentInputs
  refine ⟨List.length_map .., ?_, ?_⟩
  · rw [List.map_map]
    have hComp : (ToolCall.id ∘ enrichToolCall (collectToolResults trace)) = ToolCall.id := by
      funext c
      exact enrichToolCall_preserves_id (collectToolResults trace) c
    rw [hComp]
  · rw [List.map_map]
    have hComp : (ToolCall.name ∘ enrichToolCall (collectToolResults trace)) = ToolCall.name := by
      funext c
      exact enrichToolCall_preserves_name (collectToolResults trace) c
    rw [hComp]

private theorem expectedSortKeyLe_trans (n : Nat) (a b c : Nat × ExpectedTool)
    (hab : expectedSortKeyLe n a b = true) (hbc : expectedSortKeyLe n b c = true) :
    expectedSortKeyLe n a c = true := by
  unfold expectedSortKeyLe at *
  simp only [decide_eq_true_eq] at hab hbc ⊢
  omega

private theorem expectedSortKeyLe_total (n : Nat) (a b : Nat × ExpectedTool) :
    (expectedSortKeyLe n a b || expectedSortKeyLe n b a) = true := by
  unfold expectedSortKeyLe
  simp only [Bool.or_eq_true, decide_eq_true_eq]
  omega

/--
Theorem 8: `_ordered_expected_tools` preserves the exact expectation multiset (`List.Perm`) and length.
-/
theorem orderedExpectedTools_perm_and_length (expected : List ExpectedTool) :
    (orderedExpectedTools expected).Perm expected ∧
    (orderedExpectedTools expected).length = expected.length := by
  have hPerm : (orderedExpectedTools expected).Perm expected := by
    unfold orderedExpectedTools orderedExpectedToolsIndexed
    split
    · have hp := (List.mergeSort_perm (enumFrom 0 expected) (expectedSortKeyLe expected.length)).map Prod.snd
      simpa [enumFrom_map_snd] using hp
    · rw [enumFrom_map_snd]
  exact ⟨hPerm, hPerm.length_eq⟩

/--
Theorem 9: `orderedExpectedToolsIndexed` always outputs a sequence pairwise sorted by `(order ?? len, idx)`.
-/
theorem orderedExpectedTools_pairwise_sorted (expected : List ExpectedTool) :
    List.Pairwise (fun a b => expectedSortKeyLe expected.length a b = true)
      (orderedExpectedToolsIndexed expected) := by
  unfold orderedExpectedToolsIndexed
  by_cases hAny : expected.any (fun item => item.order.isSome) = true
  · simp only [hAny, ↓reduceIte]
    exact List.pairwise_mergeSort (expectedSortKeyLe_trans expected.length)
      (expectedSortKeyLe_total expected.length) _
  · simp only [hAny]
    have hAllNone : ∀ item ∈ expected, item.order = none := by
      intro item hMem
      cases hOrd : item.order with
      | none => rfl
      | some o =>
        have hTrue : expected.any (fun x => x.order.isSome) = true := by
          rw [List.any_eq_true]
          exact ⟨item, hMem, by simp [hOrd]⟩
        exact False.elim (hAny hTrue)
    have hIdxLt := enumFrom_pairwise_lt 0 expected
    have hMemSub : ∀ p ∈ enumFrom 0 expected, p.2 ∈ expected := by
      intro p hp
      have : p.2 ∈ (enumFrom 0 expected).map Prod.snd := List.mem_map.mpr ⟨p, hp, rfl⟩
      rwa [enumFrom_map_snd] at this
    have hImp : ∀ {l : List (Nat × ExpectedTool)},
        (∀ p ∈ l, p.2 ∈ expected) →
        List.Pairwise (fun a b => a.1 < b.1) l →
        List.Pairwise (fun a b => expectedSortKeyLe expected.length a b = true) l := by
      intro l hSub hPw
      induction hPw with
      | nil => exact List.Pairwise.nil
      | @cons a as ha _ ih =>
        refine List.Pairwise.cons ?_ (ih (fun p hp => hSub p (List.mem_cons_of_mem a hp)))
        intro b hb
        have haNone := hAllNone a.2 (hSub a (List.mem_cons_self ..))
        have hbNone := hAllNone b.2 (hSub b (List.mem_cons_of_mem a hb))
        have hlt := ha b hb
        unfold expectedSortKeyLe expectedSortKey
        simp only [haNone, hbNone, Option.getD_none, decide_eq_true_eq, true_and]
        exact Or.inr (Nat.le_of_lt hlt)
    exact hImp hMemSub hIdxLt

/-! ## Group 3 — `tool_selection` (`6` Theorems) -/

private theorem toolSelectionTp_eq_req_filter (req called : List String)
    (hReq : req.Nodup) (hCalled : called.Nodup) :
    toolSelectionTp req called = (req.filter (fun n => decide (n ∈ called))).length := by
  unfold toolSelectionTp
  apply nodup_length_eq_of_mem_iff
  · exact hCalled.filter _
  · exact hReq.filter _
  · intro x
    simp only [List.mem_filter, decide_eq_true_eq]
    exact ⟨fun ⟨h1, h2⟩ => ⟨h2, h1⟩, fun ⟨h1, h2⟩ => ⟨h2, h1⟩⟩

private theorem toolSelectionTp_add_missing (expected : List ExpectedTool) (calls : List ToolCall) :
    toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
    toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) =
    (requiredToolNames expected).length := by
  have hReqNd : (requiredToolNames expected).Nodup := dedupPreserveFirst_nodup' _
  have hCalledNd : (calledToolNames calls).Nodup := dedupPreserveFirst_nodup' _
  rw [toolSelectionTp_eq_req_filter _ _ hReqNd hCalledNd]
  unfold toolSelectionMissingCount
  exact filter_length_add_not (fun n => decide (n ∈ calledToolNames calls)) (requiredToolNames expected)

private theorem toolSelectionTp_le_reqLen (expected : List ExpectedTool) (calls : List ToolCall) :
    toolSelectionTp (requiredToolNames expected) (calledToolNames calls) ≤
    (requiredToolNames expected).length := by
  have h := toolSelectionTp_add_missing expected calls
  omega

/-- Theorem 10: `tool_selection` always produces a score in `[0, 1]` across all three modes. -/
theorem toolSelection_bounds (mode : ToolSelectionMode) (expected : List ExpectedTool)
    (calls : List ToolCall) (hNe : expected ≠ []) :
    let s := toolSelectionScore mode expected calls hNe
    NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  dsimp only
  refine ⟨NNRat.zero_le _, ?_⟩
  cases mode
  · dsimp only [toolSelectionScore]
    unfold toolSelectionF1
    dsimp only
    split
    · exact NNRat.zero_le NNRat.one
    · rw [NNRat.le_one_iff]
      dsimp only
      have hLe := toolSelectionTp_le_reqLen expected calls
      omega
  · dsimp only [toolSelectionScore]
    unfold toolSelectionRecall
    rw [NNRat.le_one_iff]
    exact toolSelectionTp_le_reqLen expected calls
  · dsimp only [toolSelectionScore]
    unfold toolSelectionExactSet
    dsimp only
    split
    · exact NNRat.le_refl NNRat.one
    · exact NNRat.zero_le NNRat.one

/--
Theorem 11: Whenever `tp > 0`, `toolSelectionF1` is exact-rationally equivalent (`≈`) to the
harmonic mean `2 * precision * recall / (precision + recall)` computed in Python `agent.py#L179-L182`.
-/
theorem toolSelection_f1_eq_harmonic_mean (expected : List ExpectedTool) (calls : List ToolCall)
    (hNe : expected ≠ [])
    (hTpPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) :
    let prec := toolSelectionPrecision expected calls
    let recScore := toolSelectionRecall expected calls hNe
    let sumPR := NNRat.add prec recScore
    have hSumPos : 0 < sumPR.num := by
      have hRecPos : NNRat.zero < recScore := by
        rw [NNRat.zero_lt_iff]
        exact hTpPos
      have hSumLt : NNRat.zero < sumPR := by
        have h1 : recScore ≤ sumPR := NNRat.le_add_left prec recScore
        show 0 * sumPR.den < sumPR.num * 1
        have hRecNum : 0 < recScore.num := (NNRat.zero_lt_iff recScore).mp hRecPos
        have hCross : recScore.num * sumPR.den ≤ sumPR.num * recScore.den := h1
        have hPosLeft : 0 < recScore.num * sumPR.den := Nat.mul_pos hRecNum sumPR.denPos
        have hPosRight : 0 < sumPR.num * recScore.den := Nat.lt_of_lt_of_le hPosLeft hCross
        have hSumNumPos : 0 < sumPR.num := Nat.pos_of_mul_pos_right hPosRight
        omega
      exact (NNRat.zero_lt_iff sumPR).mp hSumLt
    NNRat.equiv (toolSelectionF1 expected calls hNe)
      (NNRat.div (NNRat.scaleNat 2 (NNRat.mul prec recScore)) sumPR hSumPos) := by
  intro prec recScore sumPR hSumPos
  have hTpNe : toolSelectionTp (requiredToolNames expected) (calledToolNames calls) ≠ 0 := by omega
  have hDenPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by omega
  have hPrecDef : prec = ⟨toolSelectionTp (requiredToolNames expected) (calledToolNames calls),
      toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
        toolSelectionFp (allowedToolNames expected) (calledToolNames calls), hDenPos⟩ := by
    show toolSelectionPrecision expected calls = _
    unfold toolSelectionPrecision
    simp only [hDenPos, ↓reduceDIte]
  have hF1Def : toolSelectionF1 expected calls hNe =
      ⟨2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls),
        (requiredToolNames expected).length +
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
          toolSelectionFp (allowedToolNames expected) (calledToolNames calls),
        by have hr := requiredToolNames_pos_of_ne_nil hNe; omega⟩ := by
    unfold toolSelectionF1
    simp only [hTpNe, ↓reduceIte]
  rw [hF1Def]
  show (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
      ((prec.den * recScore.den) * (prec.num * recScore.den + recScore.num * prec.den)) =
    (2 * (prec.num * recScore.num) * (prec.den * recScore.den)) *
      ((requiredToolNames expected).length +
        toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
        toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
  rw [hPrecDef]
  dsimp only [recScore, toolSelectionRecall]
  generalize toolSelectionTp (requiredToolNames expected) (calledToolNames calls) = tp
  generalize toolSelectionFp (allowedToolNames expected) (calledToolNames calls) = fp
  generalize (requiredToolNames expected).length = rLen
  have hSum : tp * rLen + tp * (tp + fp) = tp * (rLen + tp + fp) := by
    rw [← Nat.mul_add, Nat.add_assoc]
  rw [hSum]
  have hL : 2 * tp * ((tp + fp) * rLen * (tp * (rLen + tp + fp))) =
      2 * (tp * tp) * ((tp + fp) * rLen) * (rLen + tp + fp) := by
    calc
      2 * tp * ((tp + fp) * rLen * (tp * (rLen + tp + fp)))
          = (2 * tp) * (tp * (((tp + fp) * rLen) * (rLen + tp + fp))) := by
            rw [Nat.mul_left_comm ((tp + fp) * rLen) tp (rLen + tp + fp), Nat.mul_assoc]
      _ = ((2 * tp) * tp) * (((tp + fp) * rLen) * (rLen + tp + fp)) := (Nat.mul_assoc _ _ _).symm
      _ = (2 * (tp * tp)) * (((tp + fp) * rLen) * (rLen + tp + fp)) := by rw [Nat.mul_assoc 2 tp tp]
      _ = 2 * (tp * tp) * ((tp + fp) * rLen) * (rLen + tp + fp) := (Nat.mul_assoc _ _ _).symm
  exact hL

/--
Theorem 12: Exact `tool_selection` mode hierarchy: `exact_set` lower-bounds `precision`, `recall`,
and `f1`, and `f1` is always sandwiched between `min(precision, recall)` and `max(precision, recall)`.
-/
theorem toolSelection_mode_hierarchy (expected : List ExpectedTool) (calls : List ToolCall)
    (hNe : expected ≠ []) :
    let ex := toolSelectionExactSet expected calls
    let prec := toolSelectionPrecision expected calls
    let recScore := toolSelectionRecall expected calls hNe
    let f1 := toolSelectionF1 expected calls hNe
    ex ≤ prec ∧ ex ≤ recScore ∧ ex ≤ f1 ∧ nnratMin prec recScore ≤ f1 ∧ f1 ≤ nnratMax prec recScore := by
  dsimp only
  have hAdd := toolSelectionTp_add_missing expected calls
  have hReqPos := requiredToolNames_pos_of_ne_nil hNe
  have hExBound :
      toolSelectionExactSet expected calls ≤ toolSelectionPrecision expected calls ∧
      toolSelectionExactSet expected calls ≤ toolSelectionRecall expected calls hNe ∧
      toolSelectionExactSet expected calls ≤ toolSelectionF1 expected calls hNe := by
    unfold toolSelectionExactSet
    by_cases hCond :
        (toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) == 0 &&
          toolSelectionFp (allowedToolNames expected) (calledToolNames calls) == 0) = true
    · simp only [hCond, ↓reduceIte]
      simp only [Bool.and_eq_true, beq_iff_eq] at hCond
      obtain ⟨hMiss, hFp⟩ := hCond
      have hTpEq : toolSelectionTp (requiredToolNames expected) (calledToolNames calls) =
          (requiredToolNames expected).length := by omega
      have hTpPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls) := by omega
      have hTpNe : toolSelectionTp (requiredToolNames expected) (calledToolNames calls) ≠ 0 := by omega
      refine ⟨?_, ?_, ?_⟩
      · unfold toolSelectionPrecision
        have hDenPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by omega
        simp only [hDenPos, ↓reduceDIte]
        show 1 * (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) * 1
        omega
      · unfold toolSelectionRecall
        show 1 * (requiredToolNames expected).length ≤
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) * 1
        omega
      · unfold toolSelectionF1
        simp only [hTpNe, ↓reduceIte]
        show 1 * ((requiredToolNames expected).length +
            toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) * 1
        omega
    · simp only [hCond]
      exact ⟨NNRat.zero_le _, NNRat.zero_le _, NNRat.zero_le _⟩
  refine ⟨hExBound.1, hExBound.2.1, hExBound.2.2, ?_⟩
  by_cases hTp0 : toolSelectionTp (requiredToolNames expected) (calledToolNames calls) = 0
  · have hPrec0 : toolSelectionPrecision expected calls ≤ NNRat.zero := by
      unfold toolSelectionPrecision
      dsimp only
      split
      · show toolSelectionTp (requiredToolNames expected) (calledToolNames calls) * 1 ≤ 0 * _
        omega
      · exact NNRat.le_refl NNRat.zero
    have hRec0 : toolSelectionRecall expected calls hNe ≤ NNRat.zero := by
      unfold toolSelectionRecall
      show toolSelectionTp (requiredToolNames expected) (calledToolNames calls) * 1 ≤ 0 * _
      omega
    have hF10 : toolSelectionF1 expected calls hNe = NNRat.zero := by
      unfold toolSelectionF1
      simp [hTp0]
    rw [hF10]
    exact ⟨NNRat.le_trans (nnratMin_le_left _ _) hPrec0, NNRat.zero_le _⟩
  · have hTpPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls) := by omega
    have hDenPos : 0 < toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
        toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by omega
    have hPrecDef : toolSelectionPrecision expected calls =
        ⟨toolSelectionTp (requiredToolNames expected) (calledToolNames calls),
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls), hDenPos⟩ := by
      unfold toolSelectionPrecision
      simp only [hDenPos, ↓reduceDIte]
    have hF1Def : toolSelectionF1 expected calls hNe =
        ⟨2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls),
          (requiredToolNames expected).length +
            toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls),
          by omega⟩ := by
      unfold toolSelectionF1
      simp only [hTp0, ↓reduceIte]
    rcases Nat.le_total (requiredToolNames expected).length
        (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
          toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) with hRle | hFle
    · -- R ≤ tp + fp, so prec ≤ f1 ≤ rec
      have hPrecLeF1 : toolSelectionPrecision expected calls ≤ toolSelectionF1 expected calls hNe := by
        rw [hPrecDef, hF1Def]
        show toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
            ((requiredToolNames expected).length +
              toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
            (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
        have h1 : (requiredToolNames expected).length +
            toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls) ≤
          2 * (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) := by omega
        calc
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
              ((requiredToolNames expected).length +
                toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
              ≤ toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
                (2 * (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                  toolSelectionFp (allowedToolNames expected) (calledToolNames calls))) :=
            Nat.mul_le_mul_left _ h1
          _ = (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
              (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) := by
            rw [Nat.mul_left_comm, Nat.mul_assoc]
      have hF1LeRec : toolSelectionF1 expected calls hNe ≤ toolSelectionRecall expected calls hNe := by
        rw [hF1Def]
        unfold toolSelectionRecall
        show (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
            (requiredToolNames expected).length ≤
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
            ((requiredToolNames expected).length +
              toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
        have h1 : 2 * (requiredToolNames expected).length ≤
            (requiredToolNames expected).length +
              toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by omega
        calc
          (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
              (requiredToolNames expected).length
              = toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
                (2 * (requiredToolNames expected).length) := by
            rw [Nat.mul_comm 2, Nat.mul_assoc]
          _ ≤ toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
              ((requiredToolNames expected).length +
                toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) :=
            Nat.mul_le_mul_left _ h1
      exact ⟨NNRat.le_trans (nnratMin_le_left _ _) hPrecLeF1,
        NNRat.le_trans hF1LeRec (right_le_nnratMax _ _)⟩
    · -- tp + fp ≤ R, so rec ≤ f1 ≤ prec
      have hRecLeF1 : toolSelectionRecall expected calls hNe ≤ toolSelectionF1 expected calls hNe := by
        rw [hF1Def]
        unfold toolSelectionRecall
        show toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
            ((requiredToolNames expected).length +
              toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
            (requiredToolNames expected).length
        have h1 : (requiredToolNames expected).length +
            toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls) ≤
          2 * (requiredToolNames expected).length := by omega
        calc
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
              ((requiredToolNames expected).length +
                toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
              ≤ toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
                (2 * (requiredToolNames expected).length) :=
            Nat.mul_le_mul_left _ h1
          _ = (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
              (requiredToolNames expected).length := by
            rw [Nat.mul_left_comm, Nat.mul_assoc]
      have hF1LePrec : toolSelectionF1 expected calls hNe ≤ toolSelectionPrecision expected calls := by
        rw [hPrecDef, hF1Def]
        show (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
            (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
            ((requiredToolNames expected).length +
              toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
              toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
        have h1 : 2 * (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) ≤
          (requiredToolNames expected).length +
            toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by omega
        calc
          (2 * toolSelectionTp (requiredToolNames expected) (calledToolNames calls)) *
              (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls))
              = toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
                (2 * (toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                  toolSelectionFp (allowedToolNames expected) (calledToolNames calls))) := by
            rw [Nat.mul_comm 2, Nat.mul_assoc]
          _ ≤ toolSelectionTp (requiredToolNames expected) (calledToolNames calls) *
              ((requiredToolNames expected).length +
                toolSelectionTp (requiredToolNames expected) (calledToolNames calls) +
                toolSelectionFp (allowedToolNames expected) (calledToolNames calls)) :=
            Nat.mul_le_mul_left _ h1
      exact ⟨NNRat.le_trans (nnratMin_le_right _ _) hRecLeF1,
        NNRat.le_trans hF1LePrec (left_le_nnratMax _ _)⟩

/--
Theorem 13: Exact perfection biconditional for `tool_selection`: `exactSet ≈ 1` iff `f1 ≈ 1` iff
zero missing required tools and zero unexpected tools.
-/
theorem toolSelection_exactSet_eq_one_iff (expected : List ExpectedTool) (calls : List ToolCall)
    (hNe : expected ≠ []) :
    (NNRat.equiv (toolSelectionExactSet expected calls) NNRat.one ↔
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) = 0 ∧
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls) = 0) ∧
    (NNRat.equiv (toolSelectionF1 expected calls hNe) NNRat.one ↔
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) = 0 ∧
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls) = 0) := by
  have hAdd := toolSelectionTp_add_missing expected calls
  have hReqPos := requiredToolNames_pos_of_ne_nil hNe
  constructor
  · unfold toolSelectionExactSet
    by_cases hCond :
        (toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) == 0 &&
          toolSelectionFp (allowedToolNames expected) (calledToolNames calls) == 0) = true
    · simp only [hCond, ↓reduceIte]
      simp only [Bool.and_eq_true, beq_iff_eq] at hCond
      exact ⟨fun _ => hCond, fun _ => NNRat.equiv_refl NNRat.one⟩
    · simp only [hCond]
      constructor
      · intro h01
        rw [NNRat.equiv_one_iff] at h01
        simp [NNRat.zero] at h01
      · rintro ⟨hM, hF⟩
        have hTrue : (toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) == 0 &&
            toolSelectionFp (allowedToolNames expected) (calledToolNames calls) == 0) = true := by
          simp [hM, hF]
        exact False.elim (hCond hTrue)
  · unfold toolSelectionF1
    by_cases hTp0 : toolSelectionTp (requiredToolNames expected) (calledToolNames calls) = 0
    · simp only [hTp0, ↓reduceIte]
      constructor
      · intro h01
        rw [NNRat.equiv_one_iff] at h01
        simp [NNRat.zero] at h01
      · rintro ⟨hM, _⟩
        omega
    · simp only [hTp0, ↓reduceIte, NNRat.equiv_one_iff]
      omega

/--
Theorem 14: Invoking an optional expected tool (`optCall.name ∈ allowed` and `optCall.name ∉ req`)
never penalizes or alters `tool_selection` scores under any mode.
-/
theorem toolSelection_optional_non_penalizing (mode : ToolSelectionMode)
    (expected : List ExpectedTool) (calls : List ToolCall) (optCall : ToolCall)
    (hNe : expected ≠ [])
    (hAllowed : optCall.name ∈ allowedToolNames expected)
    (hNotReq : optCall.name ∉ requiredToolNames expected) :
    toolSelectionScore mode expected (optCall :: calls) hNe =
    toolSelectionScore mode expected calls hNe := by
  have hCalledMem : ∀ x, x ∈ calledToolNames (optCall :: calls) ↔
      x = optCall.name ∨ x ∈ calledToolNames calls := by
    intro x
    unfold calledToolNames
    simp only [dedupPreserveFirst_mem_iff', List.map_cons, List.mem_cons]
  have hTpEq :
      toolSelectionTp (requiredToolNames expected) (calledToolNames (optCall :: calls)) =
      toolSelectionTp (requiredToolNames expected) (calledToolNames calls) := by
    unfold toolSelectionTp
    apply nodup_length_eq_of_mem_iff
    · exact (dedupPreserveFirst_nodup' _).filter _
    · exact (dedupPreserveFirst_nodup' _).filter _
    · intro x
      simp only [List.mem_filter, decide_eq_true_eq, hCalledMem]
      constructor
      · rintro ⟨rfl | hIn, hReq⟩
        · exact False.elim (hNotReq hReq)
        · exact ⟨hIn, hReq⟩
      · rintro ⟨hIn, hReq⟩
        exact ⟨Or.inr hIn, hReq⟩
  have hFpEq :
      toolSelectionFp (allowedToolNames expected) (calledToolNames (optCall :: calls)) =
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls) := by
    unfold toolSelectionFp
    apply nodup_length_eq_of_mem_iff
    · exact (dedupPreserveFirst_nodup' _).filter _
    · exact (dedupPreserveFirst_nodup' _).filter _
    · intro x
      simp only [List.mem_filter, Bool.not_eq_true', decide_eq_false_iff_not, hCalledMem]
      constructor
      · rintro ⟨rfl | hIn, hNotAl⟩
        · exact False.elim (hNotAl hAllowed)
        · exact ⟨hIn, hNotAl⟩
      · rintro ⟨hIn, hNotAl⟩
        exact ⟨Or.inr hIn, hNotAl⟩
  have hMissEq :
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames (optCall :: calls)) =
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls) := by
    have h1 := toolSelectionTp_add_missing expected (optCall :: calls)
    have h2 := toolSelectionTp_add_missing expected calls
    omega
  cases mode <;> simp [toolSelectionScore, toolSelectionRecall, toolSelectionExactSet,
    toolSelectionF1, hTpEq, hFpEq, hMissEq]

/--
Theorem 15: `tool_selection` depends solely on the set of called tool names—invariant to call
reordering and duplicate invocations.
-/
theorem toolSelection_order_and_dup_invariant (mode : ToolSelectionMode)
    (expected : List ExpectedTool) (calls₁ calls₂ : List ToolCall) (hNe : expected ≠ [])
    (hSet : ∀ n, n ∈ calls₁.map ToolCall.name ↔ n ∈ calls₂.map ToolCall.name) :
    toolSelectionScore mode expected calls₁ hNe = toolSelectionScore mode expected calls₂ hNe := by
  have hCalledMem : ∀ x, x ∈ calledToolNames calls₁ ↔ x ∈ calledToolNames calls₂ := by
    intro x
    unfold calledToolNames
    rw [dedupPreserveFirst_mem_iff', dedupPreserveFirst_mem_iff']
    exact hSet x
  have hTpEq :
      toolSelectionTp (requiredToolNames expected) (calledToolNames calls₁) =
      toolSelectionTp (requiredToolNames expected) (calledToolNames calls₂) := by
    unfold toolSelectionTp
    apply nodup_length_eq_of_mem_iff
    · exact (dedupPreserveFirst_nodup' _).filter _
    · exact (dedupPreserveFirst_nodup' _).filter _
    · intro x
      simp only [List.mem_filter, decide_eq_true_eq, hCalledMem]
  have hFpEq :
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls₁) =
      toolSelectionFp (allowedToolNames expected) (calledToolNames calls₂) := by
    unfold toolSelectionFp
    apply nodup_length_eq_of_mem_iff
    · exact (dedupPreserveFirst_nodup' _).filter _
    · exact (dedupPreserveFirst_nodup' _).filter _
    · intro x
      simp only [List.mem_filter, Bool.not_eq_true', decide_eq_false_iff_not, hCalledMem]
  have hMissEq :
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls₁) =
      toolSelectionMissingCount (requiredToolNames expected) (calledToolNames calls₂) := by
    have h1 := toolSelectionTp_add_missing expected calls₁
    have h2 := toolSelectionTp_add_missing expected calls₂
    omega
  cases mode <;> simp [toolSelectionScore, toolSelectionRecall, toolSelectionExactSet,
    toolSelectionF1, hTpEq, hFpEq, hMissEq]

/-! ## Group 4 — `argument_correctness` (`4` Theorems) -/

private theorem countMatchedKeys_le_length (expArgs callArgs : List (String × String)) :
    countMatchedKeys expArgs callArgs ≤ expArgs.length :=
  List.length_filter_le _ _

private theorem countMatchedKeys_eq_length_of_subset (expArgs callArgs : List (String × String))
    (hSub : argMapSubset expArgs callArgs = true) :
    countMatchedKeys expArgs callArgs = expArgs.length := by
  unfold argMapSubset at hSub
  unfold countMatchedKeys
  induction expArgs with
  | nil => rfl
  | cons p ps ih =>
    simp only [List.all_cons, Bool.and_eq_true] at hSub
    simp only [List.filter_cons, hSub.1, ↓reduceIte, List.length_cons]
    exact congrArg (· + 1) (ih hSub.2)

private theorem scoreDictArgs_le_one (expArgs callArgs : List (String × String)) (useExact : Bool) :
    scoreDictArgs expArgs callArgs useExact ≤ NNRat.one := by
  unfold scoreDictArgs
  cases useExact
  · simp only [Bool.false_eq_true, ↓reduceIte]
    split
    · exact NNRat.le_refl NNRat.one
    · rename_i n hLen
      rw [NNRat.le_one_iff]
      dsimp only
      have hLe := countMatchedKeys_le_length expArgs callArgs
      omega
  · simp only [↓reduceIte]
    split
    · exact NNRat.le_refl NNRat.one
    · exact NNRat.zero_le NNRat.one

private theorem scoreDictArgs_exact_le_subset (expArgs callArgs : List (String × String)) :
    scoreDictArgs expArgs callArgs true ≤ scoreDictArgs expArgs callArgs false := by
  unfold scoreDictArgs
  simp only [↓reduceIte, Bool.false_eq_true]
  by_cases hEq : argMapsEqual callArgs expArgs = true
  · simp only [hEq, ↓reduceIte]
    unfold argMapsEqual at hEq
    simp only [Bool.and_eq_true] at hEq
    have hCount := countMatchedKeys_eq_length_of_subset expArgs callArgs hEq.1
    split
    · exact NNRat.le_refl NNRat.one
    · rename_i n hLen
      show 1 * (n + 1) ≤ countMatchedKeys expArgs callArgs * 1
      omega
  · simp only [hEq]
    exact NNRat.zero_le _

private theorem div_ofNat2_le_one {a b : NNRat} (ha : a ≤ NNRat.one) (hb : b ≤ NNRat.one) :
    NNRat.div (NNRat.add a b) (NNRat.ofNat 2) (by decide) ≤ NNRat.one := by
  apply NNRat.div_le_one_of_le
  have hAdd := NNRat.add_le_add ha hb
  have hTwo : NNRat.add NNRat.one NNRat.one ≤ NNRat.ofNat 2 := by
    show (1 * 1 + 1 * 1) * 1 ≤ 2 * (1 * 1)
    omega
  exact NNRat.le_trans hAdd hTwo

private theorem div_ofNat2_mono {a b c d : NNRat} (hac : a ≤ c) (hbd : b ≤ d) :
    NNRat.div (NNRat.add a b) (NNRat.ofNat 2) (by decide) ≤
    NNRat.div (NNRat.add c d) (NNRat.ofNat 2) (by decide) := by
  have hAdd : NNRat.add a b ≤ NNRat.add c d := NNRat.add_le_add hac hbd
  show ((NNRat.add a b).num * 1) * ((NNRat.add c d).den * 2) ≤
    ((NNRat.add c d).num * 1) * ((NNRat.add a b).den * 2)
  have h1 : (NNRat.add a b).num * (NNRat.add c d).den ≤
      (NNRat.add c d).num * (NNRat.add a b).den := hAdd
  have h2 := Nat.mul_le_mul_right 2 h1
  simpa [Nat.mul_assoc] using h2

/-- Theorem 16: `_score_single_call_args` always produces a value in `[0, 1]`. -/
theorem scoreSingleCallArgs_bounds (exp : ExpectedTool) (call : ToolCall)
    (strictMode schemaValid : Bool) :
    let s := scoreSingleCallArgs exp call strictMode schemaValid
    NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  dsimp only
  refine ⟨NNRat.zero_le _, ?_⟩
  unfold scoreSingleCallArgs
  by_cases hErr : call.argumentParseError.isSome = true
  · simp only [hErr, ↓reduceIte]
    exact NNRat.zero_le NNRat.one
  · simp only [hErr]
    cases exp.hasSchema with
    | false =>
      cases exp.arguments with
      | none => exact NNRat.zero_le NNRat.one
      | some expArgs => exact scoreDictArgs_le_one expArgs call.arguments _
    | true =>
      cases exp.arguments with
      | none =>
        cases schemaValid
        · exact NNRat.zero_le NNRat.one
        · exact NNRat.le_refl NNRat.one
      | some expArgs =>
        apply div_ofNat2_le_one
        · cases schemaValid
          · exact NNRat.zero_le NNRat.one
          · exact NNRat.le_refl NNRat.one
        · exact scoreDictArgs_le_one expArgs call.arguments _

/-- Theorem 17: Any `argument_parse_error` immediately forces `_score_single_call_args = 0`. -/
theorem scoreSingleCallArgs_parse_error_zero (exp : ExpectedTool) (call : ToolCall)
    (strictMode schemaValid : Bool) (err : String)
    (hErr : call.argumentParseError = some err) :
    scoreSingleCallArgs exp call strictMode schemaValid = NNRat.zero := by
  unfold scoreSingleCallArgs
  simp [hErr]

/-- Theorem 18: Enabling `strict_mode = true` never exceeds `strict_mode = false` on any call. -/
theorem scoreSingleCallArgs_strict_le_subset (exp : ExpectedTool) (call : ToolCall)
    (schemaValid : Bool) :
    scoreSingleCallArgs exp call true schemaValid ≤
    scoreSingleCallArgs exp call false schemaValid := by
  unfold scoreSingleCallArgs
  by_cases hErr : call.argumentParseError.isSome = true
  · simp only [hErr, ↓reduceIte]
    exact NNRat.le_refl NNRat.zero
  · simp only [hErr, Bool.true_or, Bool.false_or]
    cases hMode : exp.argumentMatchMode with
    | exact =>
      simp only [beq_self_eq_true]
      exact NNRat.le_refl _
    | subset =>
      simp only [reduceCtorEq]
      cases exp.hasSchema with
      | false =>
        cases exp.arguments with
        | none => exact NNRat.le_refl _
        | some expArgs => exact scoreDictArgs_exact_le_subset expArgs call.arguments
      | true =>
        cases exp.arguments with
        | none => exact NNRat.le_refl _
        | some expArgs =>
          exact div_ofNat2_mono (NNRat.le_refl _) (scoreDictArgs_exact_le_subset expArgs call.arguments)

private theorem findBestCallAux_inv
    (exp : ExpectedTool) (expIdx : Nat) (strictMode : Bool)
    (schemaOracle : SchemaOracle) (used : List Nat) (nCalls : Nat)
    (work : List (Nat × ToolCall)) (best : Option (Nat × NNRat))
    (hWork : ∀ p ∈ work, p.1 < nCalls)
    (hBest : ∀ idx s, best = some (idx, s) → idx ∉ used ∧ idx < nCalls ∧ s ≤ NNRat.one) :
    ∀ idx s, findBestCallAux exp expIdx strictMode schemaOracle used work best = some (idx, s) →
      idx ∉ used ∧ idx < nCalls ∧ s ≤ NNRat.one := by
  induction work generalizing best with
  | nil => exact hBest
  | cons p ps ih =>
    cases p with
    | mk callIdx call =>
      unfold findBestCallAux
      have hCallLt : callIdx < nCalls := hWork (callIdx, call) (List.mem_cons_self ..)
      have hPsWork : ∀ q ∈ ps, q.1 < nCalls := fun q hq => hWork q (List.mem_cons_of_mem _ hq)
      by_cases hSkip : (decide (callIdx ∈ used) || (call.name != exp.name)) = true
      · simp only [hSkip, ↓reduceIte]
        exact ih best hPsWork hBest
      · simp only [hSkip]
        have hNotUsed : callIdx ∉ used := by
          intro hMem
          have hTrue : (decide (callIdx ∈ used) || (call.name != exp.name)) = true := by
            simp [hMem]
          exact hSkip hTrue
        have hCandLe : scoreSingleCallArgs exp call strictMode (schemaOracle expIdx callIdx) ≤ NNRat.one :=
          (scoreSingleCallArgs_bounds exp call strictMode (schemaOracle expIdx callIdx)).2
        apply ih _ hPsWork
        intro idx s hEq
        cases best with
        | none =>
          simp only [Option.some.injEq, Prod.mk.injEq] at hEq
          obtain ⟨rfl, rfl⟩ := hEq
          exact ⟨hNotUsed, hCallLt, hCandLe⟩
        | some bp =>
          cases bp with
          | mk bIdx bScore =>
            dsimp only at hEq
            split at hEq
            · exact hBest idx s hEq
            · simp only [Option.some.injEq, Prod.mk.injEq] at hEq
              obtain ⟨rfl, rfl⟩ := hEq
              exact ⟨hNotUsed, hCallLt, hCandLe⟩

private theorem greedyMatchLoop_inv
    (calls : List ToolCall) (strictMode : Bool) (schemaOracle : SchemaOracle)
    (work : List (Nat × ExpectedTool)) (used : List Nat) (accScores : List NNRat)
    (hNd : used.Nodup) (hLt : ∀ i ∈ used, i < calls.length)
    (hAccLe : ∀ s ∈ accScores, s ≤ NNRat.one) :
    let res := greedyMatchLoop calls strictMode schemaOracle used accScores work
    res.1.Nodup ∧
    (∀ i ∈ res.1, i < calls.length) ∧
    res.1.length ≤ used.length + work.length ∧
    res.2.length = accScores.length + work.length ∧
    (∀ s ∈ res.2, s ≤ NNRat.one) := by
  induction work generalizing used accScores with
  | nil =>
    simp only [greedyMatchLoop, List.length_nil, Nat.add_zero]
    exact ⟨hNd, hLt, Nat.le_refl _, trivial, hAccLe⟩
  | cons p ps ih =>
    cases p with
    | mk expIdx exp =>
      unfold greedyMatchLoop
      have hEnumWork : ∀ q ∈ enumFrom 0 calls, q.1 < calls.length := by
        intro q hq
        have h := mem_enumFrom_lt 0 calls hq
        omega
      cases hFind : findBestCallAux exp expIdx strictMode schemaOracle used (enumFrom 0 calls) none with
      | none =>
        have hAcc' : ∀ s ∈ accScores ++ [NNRat.zero], s ≤ NNRat.one := by
          intro s hs
          simp only [List.mem_append, List.mem_singleton] at hs
          rcases hs with hOld | rfl
          · exact hAccLe s hOld
          · exact NNRat.zero_le NNRat.one
        have hRec := ih used (accScores ++ [NNRat.zero]) hNd hLt hAcc'
        refine ⟨hRec.1, hRec.2.1, ?_, ?_, hRec.2.2.2.2⟩
        · simp only [List.length_cons]; omega
        · have hLen := hRec.2.2.2.1
          simp only [List.length_append, List.length_cons, List.length_nil] at hLen ⊢
          omega
      | some bp =>
        cases bp with
        | mk bestIdx bestScore =>
          have hFound := findBestCallAux_inv exp expIdx strictMode schemaOracle used calls.length
            (enumFrom 0 calls) none hEnumWork (fun _ _ h => nomatch h) bestIdx bestScore hFind
          have hNd' : (bestIdx :: used).Nodup := List.nodup_cons.mpr ⟨hFound.1, hNd⟩
          have hLt' : ∀ i ∈ bestIdx :: used, i < calls.length := by
            intro i hi
            simp only [List.mem_cons] at hi
            rcases hi with rfl | hOld
            · exact hFound.2.1
            · exact hLt i hOld
          have hAcc' : ∀ s ∈ accScores ++ [bestScore], s ≤ NNRat.one := by
            intro s hs
            simp only [List.mem_append, List.mem_singleton] at hs
            rcases hs with hOld | rfl
            · exact hAccLe s hOld
            · exact hFound.2.2
          have hRec := ih (bestIdx :: used) (accScores ++ [bestScore]) hNd' hLt' hAcc'
          refine ⟨hRec.1, hRec.2.1, ?_, ?_, hRec.2.2.2.2⟩
          · have hLen := hRec.2.2.1
            simp only [List.length_cons] at hLen ⊢
            omega
          · have hLen := hRec.2.2.2.1
            simp only [List.length_append, List.length_cons, List.length_nil] at hLen ⊢
            omega

private theorem sumNNRat_le_ofNat_length (scores : List NNRat)
    (hLe : ∀ s ∈ scores, s ≤ NNRat.one) :
    sumNNRat scores ≤ NNRat.ofNat scores.length := by
  induction scores with
  | nil => exact NNRat.le_refl NNRat.zero
  | cons s ss ih =>
    simp only [sumNNRat, List.length_cons]
    have hs : s ≤ NNRat.one := hLe s (List.mem_cons_self ..)
    have hss := ih (fun x hx => hLe x (List.mem_cons_of_mem s hx))
    have hAdd := NNRat.add_le_add hs hss
    have hEq : NNRat.add NNRat.one (NNRat.ofNat ss.length) ≤ NNRat.ofNat (ss.length + 1) := by
      show (1 * 1 + ss.length * 1) * 1 ≤ (ss.length + 1) * (1 * 1)
      omega
    exact NNRat.le_trans hAdd hEq

/--
Theorem 19: `argument_correctness` always scores within `[0, 1]`, consumes each call index at most
once (`used.Nodup`), and consumes at most `min constrained.length calls.length` calls.
-/
theorem argumentCorrectness_bounds_and_usage_cap
    (constrained : List ExpectedTool) (calls : List ToolCall)
    (strictMode : Bool) (schemaOracle : SchemaOracle) (hNe : constrained ≠ []) :
    let res := greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)
    let score := argumentCorrectnessScore constrained calls strictMode schemaOracle hNe
    res.1.Nodup ∧
    res.1.length ≤ constrained.length ∧
    res.1.length ≤ calls.length ∧
    NNRat.zero ≤ score ∧
    score ≤ NNRat.one := by
  dsimp only
  have hInv := greedyMatchLoop_inv calls strictMode schemaOracle (enumFrom 0 constrained) [] []
    List.nodup_nil (fun _ h => nomatch h) (fun _ h => nomatch h)
  have hEnumLen : (enumFrom 0 constrained).length = constrained.length := enumFrom_length 0 constrained
  have hUsedLeConstrained : (greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)).1.length ≤ constrained.length := by
    have h := hInv.2.2.1
    simp only [List.length_nil, Nat.zero_add, hEnumLen] at h
    exact h
  have hUsedLeCalls : (greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)).1.length ≤ calls.length := by
    have hSub : ∀ i ∈ (greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)).1,
        i ∈ List.range calls.length := by
      intro i hi
      exact List.mem_range.mpr (hInv.2.1 i hi)
    have hLe := nodup_length_le_of_subset hInv.1 hSub
    simpa [List.length_range] using hLe
  have hScoreLeOne : argumentCorrectnessScore constrained calls strictMode schemaOracle hNe ≤ NNRat.one := by
    unfold argumentCorrectnessScore
    dsimp only
    apply NNRat.div_le_one_of_le
    have hSum := sumNNRat_le_ofNat_length
      (greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)).2
      hInv.2.2.2.2
    have hLenEq : (greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)).2.length =
        constrained.length := by
      have h := hInv.2.2.2.1
      simp only [List.length_nil, Nat.zero_add, hEnumLen] at h
      exact h
    rwa [hLenEq] at hSum
  exact ⟨hInv.1, hUsedLeConstrained, hUsedLeCalls, NNRat.zero_le _, hScoreLeOne⟩

/-! ## Group 5 — `execution_sequence` (`4` Theorems) -/

private theorem prefixMatchCount_le_left : ∀ (exp act : List String),
    prefixMatchCount exp act ≤ exp.length
  | [], _ => Nat.zero_le _
  | _ :: _, [] => Nat.zero_le _
  | e :: es, a :: as => by
    unfold prefixMatchCount
    split
    · have ih := prefixMatchCount_le_left es as
      simp only [List.length_cons]
      omega
    · exact Nat.zero_le _

private theorem subseqMatchCount_le_left : ∀ (exp act : List String),
    subseqMatchCount exp act ≤ exp.length
  | [], _ => by simp [subseqMatchCount]
  | _ :: _, [] => by simp [subseqMatchCount]
  | e :: es, a :: as => by
    unfold subseqMatchCount
    split
    · have ih := subseqMatchCount_le_left es as
      simp only [List.length_cons]
      omega
    · exact subseqMatchCount_le_left (e :: es) as

private theorem prefixMatchCount_self : ∀ (xs : List String),
    prefixMatchCount xs xs = xs.length
  | [] => rfl
  | x :: xs => by
    simp [prefixMatchCount, prefixMatchCount_self xs]
    omega

private theorem prefixMatchCount_le_subseqMatchCount : ∀ (exp act : List String),
    prefixMatchCount exp act ≤ subseqMatchCount exp act
  | [], _ => by simp [prefixMatchCount, subseqMatchCount]
  | _ :: _, [] => by simp [prefixMatchCount, subseqMatchCount]
  | e :: es, a :: as => by
    unfold prefixMatchCount subseqMatchCount
    split
    · exact Nat.add_le_add_left (prefixMatchCount_le_subseqMatchCount es as) 1
    · exact Nat.zero_le _

private theorem prefixMatchCount_append_mono : ∀ (exp act extra : List String),
    prefixMatchCount exp act ≤ prefixMatchCount exp (act ++ extra)
  | [], _, _ => by simp [prefixMatchCount]
  | _ :: _, [], _ => by simp [prefixMatchCount]
  | e :: es, a :: as, extra => by
    simp only [List.cons_append, prefixMatchCount]
    split
    · exact Nat.add_le_add_left (prefixMatchCount_append_mono es as extra) 1
    · exact Nat.le_refl 0

private theorem subseqMatchCount_append_mono (extra : List String) :
    ∀ (act exp : List String),
      subseqMatchCount exp act ≤ subseqMatchCount exp (act ++ extra)
  | [], exp => by
    cases exp <;> simp [subseqMatchCount]
  | a :: as, [] => by simp [subseqMatchCount]
  | a :: as, e :: es => by
    simp only [List.cons_append, subseqMatchCount]
    split
    · exact Nat.add_le_add_left (subseqMatchCount_append_mono extra as es) 1
    · exact subseqMatchCount_append_mono extra as (e :: es)

/-- Theorem 20: `execution_sequence` always produces a score in `[0, 1]` across all three modes. -/
theorem executionSequence_bounds (mode : SequenceMode) (expSeq actSeq : List String)
    (hPos : 0 < expSeq.length) :
    let s := executionSequenceRawScore mode expSeq actSeq hPos
    NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  dsimp only
  refine ⟨NNRat.zero_le _, ?_⟩
  cases mode
  · dsimp only [executionSequenceRawScore]
    rw [NNRat.le_one_iff]
    exact subseqMatchCount_le_left expSeq actSeq
  · dsimp only [executionSequenceRawScore]
    rw [NNRat.le_one_iff]
    exact prefixMatchCount_le_left expSeq actSeq
  · dsimp only [executionSequenceRawScore]
    split
    · exact NNRat.le_refl NNRat.one
    · exact NNRat.zero_le NNRat.one

/-- Theorem 21: Strict mode hierarchy `exact ≤ prefix ≤ subsequence` for `execution_sequence`. -/
theorem executionSequence_mode_hierarchy (expSeq actSeq : List String)
    (hPos : 0 < expSeq.length) :
    executionSequenceRawScore .exact expSeq actSeq hPos ≤
      executionSequenceRawScore .prefix expSeq actSeq hPos ∧
    executionSequenceRawScore .prefix expSeq actSeq hPos ≤
      executionSequenceRawScore .subsequence expSeq actSeq hPos := by
  constructor
  · unfold executionSequenceRawScore
    by_cases hEq : actSeq = expSeq
    · subst hEq
      simp only [beq_self_eq_true, ↓reduceIte]
      show 1 * actSeq.length ≤ prefixMatchCount actSeq actSeq * 1
      rw [prefixMatchCount_self]
      omega
    · have hBeq : (actSeq == expSeq) = false := beq_false_of_ne hEq
      simp only [hBeq, Bool.false_eq_true, ↓reduceIte]
      exact NNRat.zero_le _
  · unfold executionSequenceRawScore
    show prefixMatchCount expSeq actSeq * expSeq.length ≤
      subseqMatchCount expSeq actSeq * expSeq.length
    exact Nat.mul_le_mul_right expSeq.length (prefixMatchCount_le_subseqMatchCount expSeq actSeq)

/-- Theorem 22: Exact sequence equality achieves score `1` across all three modes (`exact`, `prefix`, `subsequence`). -/
theorem executionSequence_exact_match_one (expSeq : List String) (hPos : 0 < expSeq.length) :
    NNRat.equiv (executionSequenceRawScore .exact expSeq expSeq hPos) NNRat.one ∧
    NNRat.equiv (executionSequenceRawScore .prefix expSeq expSeq hPos) NNRat.one ∧
    NNRat.equiv (executionSequenceRawScore .subsequence expSeq expSeq hPos) NNRat.one := by
  have hPre : prefixMatchCount expSeq expSeq = expSeq.length := prefixMatchCount_self expSeq
  have hSubLe : subseqMatchCount expSeq expSeq ≤ expSeq.length := subseqMatchCount_le_left expSeq expSeq
  have hPreLeSub : prefixMatchCount expSeq expSeq ≤ subseqMatchCount expSeq expSeq :=
    prefixMatchCount_le_subseqMatchCount expSeq expSeq
  have hSubEq : subseqMatchCount expSeq expSeq = expSeq.length := by omega
  refine ⟨?_, ?_, ?_⟩
  · simp [executionSequenceRawScore, NNRat.equiv_refl]
  · unfold executionSequenceRawScore
    rw [NNRat.equiv_one_iff]
    exact hPre
  · unfold executionSequenceRawScore
    rw [NNRat.equiv_one_iff]
    exact hSubEq

/-- Theorem 23: Appending suffix tool calls never decreases `prefix` or `subsequence` scores. -/
theorem executionSequence_suffix_mono (expSeq actSeq extra : List String)
    (hPos : 0 < expSeq.length) :
    executionSequenceRawScore .prefix expSeq actSeq hPos ≤
      executionSequenceRawScore .prefix expSeq (actSeq ++ extra) hPos ∧
    executionSequenceRawScore .subsequence expSeq actSeq hPos ≤
      executionSequenceRawScore .subsequence expSeq (actSeq ++ extra) hPos := by
  constructor
  · unfold executionSequenceRawScore
    show prefixMatchCount expSeq actSeq * expSeq.length ≤
      prefixMatchCount expSeq (actSeq ++ extra) * expSeq.length
    exact Nat.mul_le_mul_right expSeq.length (prefixMatchCount_append_mono expSeq actSeq extra)
  · unfold executionSequenceRawScore
    show subseqMatchCount expSeq actSeq * expSeq.length ≤
      subseqMatchCount expSeq (actSeq ++ extra) * expSeq.length
    exact Nat.mul_le_mul_right expSeq.length (subseqMatchCount_append_mono extra actSeq expSeq)

/-! ## Group 6 — `tool_efficiency` (`5` Theorems) -/

private theorem budgetFactor_le_one (limit : Option Nat) (actual : Nat) :
    budgetFactor limit actual ≤ NNRat.one := by
  unfold budgetFactor
  cases limit with
  | none => exact NNRat.le_refl NNRat.one
  | some m =>
    dsimp only
    split
    · rw [NNRat.le_one_iff]; dsimp only; omega
    · exact NNRat.le_refl NNRat.one

private theorem loopPenaltyFactor_le_one (loops maxRepeats : Nat) (loopPenalty : NNRat) :
    loopPenaltyFactor loops maxRepeats loopPenalty ≤ NNRat.one := by
  unfold loopPenaltyFactor
  dsimp only
  split
  · exact NNRat.le_refl NNRat.one
  · split
    · exact NNRat.zero_le NNRat.one
    · rw [NNRat.le_one_iff]; dsimp only; omega

private theorem budgetFactor_anti_mono_actual (limit : Option Nat) {a₁ a₂ : Nat} (ha : a₁ ≤ a₂) :
    budgetFactor limit a₂ ≤ budgetFactor limit a₁ := by
  unfold budgetFactor
  cases limit with
  | none => exact NNRat.le_refl NNRat.one
  | some m =>
    dsimp only
    by_cases h1 : m < a₁
    · have h2 : m < a₂ := by omega
      simp only [h1, h2, ↓reduceDIte]
      show m * a₁ ≤ m * a₂
      exact Nat.mul_le_mul_left m ha
    · simp only [h1, ↓reduceDIte]
      split
      · rw [NNRat.le_one_iff]; dsimp only; omega
      · exact NNRat.le_refl NNRat.one

private theorem budgetFactor_mono_limit {l₁ l₂ : Option Nat} (actual : Nat)
    (hRelax : match l₁, l₂ with
      | some m₁, some m₂ => m₁ ≤ m₂
      | _, none => True
      | none, some _ => False) :
    budgetFactor l₁ actual ≤ budgetFactor l₂ actual := by
  cases l₁ with
  | none =>
    cases l₂ with
    | none => exact NNRat.le_refl NNRat.one
    | some _ => exact False.elim hRelax
  | some m₁ =>
    cases l₂ with
    | none => exact budgetFactor_le_one (some m₁) actual
    | some m₂ =>
      dsimp only at hRelax
      unfold budgetFactor
      by_cases h2 : m₂ < actual
      · have h1 : m₁ < actual := by omega
        simp only [h1, h2, ↓reduceDIte]
        show m₁ * actual ≤ m₂ * actual
        exact Nat.mul_le_mul_right actual hRelax
      · simp only [h2, ↓reduceDIte]
        split
        · rw [NNRat.le_one_iff]; dsimp only; omega
        · exact NNRat.le_refl NNRat.one

private theorem loopPenaltyFactor_anti_mono {e₁ e₂ : Nat} {p₁ p₂ : NNRat}
    (he : e₁ ≤ e₂) (hp : p₁ ≤ p₂) :
    let f := fun (ex : Nat) (p : NNRat) =>
      if ex = 0 then NNRat.one
      else
        let totalPen := NNRat.scaleNat ex p
        if NNRat.leBool NNRat.one totalPen then NNRat.zero
        else ⟨totalPen.den - totalPen.num, totalPen.den, totalPen.denPos⟩
    f e₂ p₂ ≤ f e₁ p₁ := by
  dsimp only
  by_cases h1 : e₁ = 0
  · simp only [h1, ↓reduceIte]
    split
    · exact NNRat.le_refl NNRat.one
    · split
      · exact NNRat.zero_le NNRat.one
      · rw [NNRat.le_one_iff]; dsimp only; omega
  · have h2 : e₂ ≠ 0 := by omega
    simp only [h1, h2, ↓reduceIte]
    have hScale : NNRat.scaleNat e₁ p₁ ≤ NNRat.scaleNat e₂ p₂ := NNRat.scaleNat_le_scaleNat he hp
    cases hCap2 : NNRat.leBool NNRat.one (NNRat.scaleNat e₂ p₂)
    · have hLt2 : NNRat.scaleNat e₂ p₂ < NNRat.one := (NNRat.leBool_false_iff _ _).mp hCap2
      have hLt1 : NNRat.scaleNat e₁ p₁ < NNRat.one := by
        rw [NNRat.lt_iff_not_le] at hLt2 ⊢
        intro hGe
        exact hLt2 (NNRat.le_trans hGe hScale)
      have hCap1 : NNRat.leBool NNRat.one (NNRat.scaleNat e₁ p₁) = false :=
        (NNRat.leBool_false_iff _ _).mpr hLt1
      simp only [hCap1, Bool.false_eq_true, ↓reduceIte]
      show (p₂.den - e₂ * p₂.num) * p₁.den ≤ (p₁.den - e₁ * p₁.num) * p₂.den
      have hNumLe2 : e₂ * p₂.num < p₂.den := by
        have h : (e₂ * p₂.num) * 1 < 1 * p₂.den := hLt2
        omega
      have hNumLe1 : e₁ * p₁.num < p₁.den := by
        have h : (e₁ * p₁.num) * 1 < 1 * p₁.den := hLt1
        omega
      have hCross : (e₁ * p₁.num) * p₂.den ≤ (e₂ * p₂.num) * p₁.den := hScale
      rw [Nat.sub_mul, Nat.sub_mul]
      have hComm : p₂.den * p₁.den = p₁.den * p₂.den := Nat.mul_comm _ _
      rw [hComm]
      exact Nat.sub_le_sub_left hCross (p₁.den * p₂.den)
    · exact NNRat.zero_le _

/-- Theorem 24: `tool_efficiency` always produces a score in `[0, 1]`. -/
theorem toolEfficiency_bounds (maxSteps maxCalls : Option Nat)
    (actualSteps actualCalls loops maxRepeats : Nat) (loopPenalty : NNRat) :
    let s := toolEfficiencyRawScore maxSteps maxCalls actualSteps actualCalls loops maxRepeats loopPenalty
    NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  dsimp only
  refine ⟨NNRat.zero_le _, ?_⟩
  unfold toolEfficiencyRawScore
  exact NNRat.le_trans (nnratMin_le_left _ _) (nnratMin_le_left _ _)

/-- Theorem 25: Compliant traces within step/call budgets and loop allowance achieve exact score `1`. -/
theorem toolEfficiency_budget_compliant_one (maxSteps maxCalls : Option Nat)
    (actualSteps actualCalls loops maxRepeats : Nat) (loopPenalty : NNRat)
    (hSteps : ∀ m, maxSteps = some m → actualSteps ≤ m)
    (hCalls : ∀ m, maxCalls = some m → actualCalls ≤ m)
    (hLoops : loops ≤ maxRepeats) :
    toolEfficiencyRawScore maxSteps maxCalls actualSteps actualCalls loops maxRepeats loopPenalty =
    NNRat.one := by
  have hStepOne : budgetFactor maxSteps actualSteps = NNRat.one := by
    unfold budgetFactor
    cases maxSteps with
    | none => rfl
    | some m =>
      have hLe := hSteps m rfl
      have hNotLt : ¬ (m < actualSteps) := by omega
      simp [hNotLt]
  have hCallOne : budgetFactor maxCalls actualCalls = NNRat.one := by
    unfold budgetFactor
    cases maxCalls with
    | none => rfl
    | some m =>
      have hLe := hCalls m rfl
      have hNotLt : ¬ (m < actualCalls) := by omega
      simp [hNotLt]
  have hLoopOne : loopPenaltyFactor loops maxRepeats loopPenalty = NNRat.one := by
    unfold loopPenaltyFactor
    have hSub0 : loops - maxRepeats = 0 := by omega
    simp [hSub0]
  unfold toolEfficiencyRawScore
  rw [hStepOne, hCallOne, hLoopOne]
  simp [nnratMin, NNRat.leBool, NNRat.one]

/-- Theorem 26: Higher step/call counts, redundant loops, or stricter loop penalty never increase `tool_efficiency`. -/
theorem toolEfficiency_anti_mono_usage (maxSteps maxCalls : Option Nat)
    (actualSteps₁ actualSteps₂ actualCalls₁ actualCalls₂ loops₁ loops₂ maxRepeats : Nat)
    (loopPenalty₁ loopPenalty₂ : NNRat)
    (hSteps : actualSteps₁ ≤ actualSteps₂)
    (hCalls : actualCalls₁ ≤ actualCalls₂)
    (hLoops : loops₁ ≤ loops₂)
    (hPen : loopPenalty₁ ≤ loopPenalty₂) :
    toolEfficiencyRawScore maxSteps maxCalls actualSteps₂ actualCalls₂ loops₂ maxRepeats loopPenalty₂ ≤
    toolEfficiencyRawScore maxSteps maxCalls actualSteps₁ actualCalls₁ loops₁ maxRepeats loopPenalty₁ := by
  unfold toolEfficiencyRawScore
  apply nnratMin_mono
  · exact nnratMin_mono (NNRat.le_refl NNRat.one) (budgetFactor_anti_mono_actual maxSteps hSteps)
  · apply nnratMin_mono (budgetFactor_anti_mono_actual maxCalls hCalls)
    exact loopPenaltyFactor_anti_mono (by omega : loops₁ - maxRepeats ≤ loops₂ - maxRepeats) hPen

/-- Theorem 27: Relaxing step/call budgets or increasing `allow_redundant_failures` never decreases `tool_efficiency`. -/
theorem toolEfficiency_mono_budgets
    (maxSteps₁ maxSteps₂ maxCalls₁ maxCalls₂ : Option Nat)
    (actualSteps actualCalls loops maxRepeats₁ maxRepeats₂ : Nat)
    (loopPenalty : NNRat)
    (hStepsRelax : match maxSteps₁, maxSteps₂ with
      | some m₁, some m₂ => m₁ ≤ m₂
      | _, none => True
      | none, some _ => False)
    (hCallsRelax : match maxCalls₁, maxCalls₂ with
      | some m₁, some m₂ => m₁ ≤ m₂
      | _, none => True
      | none, some _ => False)
    (hRepeats : maxRepeats₁ ≤ maxRepeats₂) :
    toolEfficiencyRawScore maxSteps₁ maxCalls₁ actualSteps actualCalls loops maxRepeats₁ loopPenalty ≤
    toolEfficiencyRawScore maxSteps₂ maxCalls₂ actualSteps actualCalls loops maxRepeats₂ loopPenalty := by
  unfold toolEfficiencyRawScore
  apply nnratMin_mono
  · exact nnratMin_mono (NNRat.le_refl NNRat.one) (budgetFactor_mono_limit actualSteps hStepsRelax)
  · apply nnratMin_mono (budgetFactor_mono_limit actualCalls hCallsRelax)
    exact loopPenaltyFactor_anti_mono (by omega : loops - maxRepeats₂ ≤ loops - maxRepeats₁)
      (NNRat.le_refl loopPenalty)

private theorem countRedundantLoopsAux_zero_of_nodup (seen : List String) (calls : List ToolCall)
    (hNd : ((calls.filter (fun c => c.status != .success)).map ToolCall.canonicalSig).Nodup)
    (hDisj : ∀ c ∈ calls, (c.status != .success) = true → c.canonicalSig ∉ seen) :
    countRedundantLoopsAux seen calls = 0 := by
  induction calls generalizing seen with
  | nil => rfl
  | cons c cs ih =>
    unfold countRedundantLoopsAux
    cases hSt : (c.status != .success) with
    | false =>
      simp only [Bool.false_eq_true, ↓reduceIte]
      simp only [List.filter_cons, hSt, Bool.false_eq_true, ↓reduceIte] at hNd
      exact ih seen hNd (fun x hx => hDisj x (List.mem_cons_of_mem c hx))
    | true =>
      simp only [↓reduceIte]
      have hNotSeen : c.canonicalSig ∉ seen := hDisj c (List.mem_cons_self ..) hSt
      simp only [hNotSeen, ↓reduceIte]
      simp only [List.filter_cons, hSt, ↓reduceIte, List.map_cons, List.nodup_cons] at hNd
      apply ih (c.canonicalSig :: seen) hNd.2
      intro x hx hxFail hxMem
      simp only [List.mem_cons] at hxMem
      rcases hxMem with hEq | hOld
      · have hInMap : c.canonicalSig ∈ (cs.filter (fun y => y.status != .success)).map ToolCall.canonicalSig :=
          List.mem_map.mpr ⟨x, List.mem_filter.mpr ⟨hx, hxFail⟩, hEq⟩
        exact hNd.1 hInMap
      · exact hDisj x (List.mem_cons_of_mem c hx) hxFail hOld

/--
Theorem 28: Single-retry immunity — distinct failing signatures produce zero redundant loops, and
specifically a single failing call followed by a clean `SUCCESS` retry incurs `0` redundant loops.
-/
theorem countRedundantLoops_single_retry_immunity :
    (∀ calls : List ToolCall,
      ((calls.filter (fun c => c.status != .success)).map ToolCall.canonicalSig).Nodup →
      countRedundantLoops calls = 0) ∧
    (∀ c₁ c₂ : ToolCall, c₂.status = .success → countRedundantLoops [c₁, c₂] = 0) := by
  constructor
  · intro calls hNd
    exact countRedundantLoopsAux_zero_of_nodup [] calls hNd (fun _ _ _ h => nomatch h)
  · intro c₁ c₂ hOk
    unfold countRedundantLoops
    simp only [countRedundantLoopsAux]
    cases (c₁.status != .success) <;> simp [hOk]

/-! ## Group 7 — `policy_compliance` (`4` Theorems) -/

/-- Theorem 29: `policy_compliance` has strict binary codomain `{0, 1}` (hence bounded in `[0, 1]`). -/
theorem policyCompliance_binary (forbiddenTools forbiddenPatterns : List String)
    (calls : List ToolCall) (trace : List TraceStep) :
    let s := policyComplianceRawScore forbiddenTools forbiddenPatterns calls trace
    (s = NNRat.zero ∨ s = NNRat.one) ∧ NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  dsimp only
  unfold policyComplianceRawScore
  cases hasAnyPolicyViolation forbiddenTools forbiddenPatterns calls trace
  · exact ⟨Or.inr rfl, NNRat.zero_le NNRat.one, NNRat.le_refl NNRat.one⟩
  · exact ⟨Or.inl rfl, NNRat.le_refl NNRat.zero, NNRat.zero_le NNRat.one⟩

/-- Theorem 30: Zero-tolerance biconditional — `score = 1` iff zero policy violations across calls and trace. -/
theorem policyCompliance_zero_tolerance_iff (forbiddenTools forbiddenPatterns : List String)
    (calls : List ToolCall) (trace : List TraceStep) :
    (policyComplianceRawScore forbiddenTools forbiddenPatterns calls trace = NNRat.one ↔
      hasAnyPolicyViolation forbiddenTools forbiddenPatterns calls trace = false) ∧
    (policyComplianceRawScore forbiddenTools forbiddenPatterns calls trace = NNRat.zero ↔
      hasAnyPolicyViolation forbiddenTools forbiddenPatterns calls trace = true) := by
  unfold policyComplianceRawScore
  cases hasAnyPolicyViolation forbiddenTools forbiddenPatterns calls trace <;>
    simp [NNRat.one, NNRat.zero]

/-- Theorem 31: Tightening forbidden tool or argument pattern lists never increases `policy_compliance`. -/
theorem policyCompliance_constraint_anti_mono
    (ft₁ ft₂ fp₁ fp₂ : List String) (calls : List ToolCall) (trace : List TraceStep)
    (hFt : ∀ t ∈ ft₁, t ∈ ft₂) (hFp : ∀ p ∈ fp₁, p ∈ fp₂) :
    policyComplianceRawScore ft₂ fp₂ calls trace ≤
    policyComplianceRawScore ft₁ fp₁ calls trace := by
  have hImp : hasAnyPolicyViolation ft₁ fp₁ calls trace = true →
      hasAnyPolicyViolation ft₂ fp₂ calls trace = true := by
    unfold hasAnyPolicyViolation
    simp only [Bool.or_eq_true, List.any_eq_true]
    rintro (⟨c, hc, hViol⟩ | hTr)
    · left
      refine ⟨c, hc, ?_⟩
      unfold callHasPolicyViolation at hViol ⊢
      simp only [Bool.or_eq_true, decide_eq_true_eq, List.any_eq_true] at hViol ⊢
      rcases hViol with (hBlk | hName) | ⟨pat, hPat, hSub⟩
      · exact Or.inl (Or.inl hBlk)
      · exact Or.inl (Or.inr (hFt _ hName))
      · exact Or.inr ⟨pat, hFp _ hPat, hSub⟩
    · exact Or.inr hTr
  unfold policyComplianceRawScore
  cases h1 : hasAnyPolicyViolation ft₁ fp₁ calls trace
  · simp only [Bool.false_eq_true, ↓reduceIte]
    cases hasAnyPolicyViolation ft₂ fp₂ calls trace
    · exact NNRat.le_refl NNRat.one
    · exact NNRat.zero_le NNRat.one
  · rw [hImp h1]
    exact NNRat.le_refl NNRat.zero

/-- Theorem 32: Append irreversibility — once a policy violation occurs, appending calls or trace steps cannot restore compliance. -/
theorem policyCompliance_violation_irreversible
    (ft fp : List String) (calls extraCalls : List ToolCall) (trace extraTrace : List TraceStep)
    (hViol : hasAnyPolicyViolation ft fp calls trace = true) :
    policyComplianceRawScore ft fp (calls ++ extraCalls) (trace ++ extraTrace) = NNRat.zero := by
  have hStill : hasAnyPolicyViolation ft fp (calls ++ extraCalls) (trace ++ extraTrace) = true := by
    unfold hasAnyPolicyViolation at hViol ⊢
    simp only [Bool.or_eq_true, List.any_append] at hViol ⊢
    rcases hViol with hC | hT
    · exact Or.inl (Or.inl hC)
    · exact Or.inr (Or.inl hT)
  unfold policyComplianceRawScore
  simp [hStill]

/-! ## Group 8 — `failure_recovery` (`6` Theorems) -/

private theorem countFailures_cons (p : Bool × Bool) (rest : List (Bool × Bool)) :
    countFailures (p :: rest) = (if p.1 then 1 else 0) + countFailures rest := by
  unfold countFailures
  cases h : p.1 <;> simp [h, Nat.add_comm]

private theorem countRecovered_le_countFailures : ∀ (t : List (Bool × Bool)),
    countRecovered t ≤ countFailures t
  | [] => Nat.le_refl 0
  | (isFail, isOk) :: rest => by
    rw [countFailures_cons]
    unfold countRecovered
    have ih := countRecovered_le_countFailures rest
    cases isFail
    · simp only [Bool.false_and, Bool.false_eq_true, ↓reduceIte, Nat.zero_add]
      exact ih
    · simp only [Bool.true_and, ↓reduceIte]
      cases rest.any Prod.snd <;> simp <;> omega

private theorem countFailures_append (a b : List (Bool × Bool)) :
    countFailures (a ++ b) = countFailures a + countFailures b := by
  unfold countFailures
  rw [List.filter_append, List.length_append]

private theorem countRecovered_eq_zero_of_countFailures_zero {t : List (Bool × Bool)}
    (h : countFailures t = 0) : countRecovered t = 0 := by
  have hLe := countRecovered_le_countFailures t
  omega

private theorem countRecovered_cons (isFail isOk : Bool) (rest : List (Bool × Bool)) :
    countRecovered ((isFail, isOk) :: rest) =
      (if isFail && rest.any Prod.snd then 1 else 0) + countRecovered rest := rfl

private theorem countRecovered_append_le (a b : List (Bool × Bool)) :
    countRecovered (a ++ b) ≤ countFailures a + countRecovered b := by
  induction a with
  | nil => simp [countFailures]
  | cons p ps ih =>
    cases p with
    | mk isFail isOk =>
      rw [List.cons_append, countFailures_cons, countRecovered_cons]
      cases isFail
      · simp only [Bool.false_and, Bool.false_eq_true, ↓reduceIte, Nat.zero_add]
        exact ih
      · simp only [Bool.true_and, ↓reduceIte]
        cases (ps ++ b).any Prod.snd <;> simp <;> omega

private theorem countRecovered_append_ge_right (a b : List (Bool × Bool)) :
    countRecovered b ≤ countRecovered (a ++ b) := by
  induction a with
  | nil => exact Nat.le_refl _
  | cons p ps ih =>
    cases p with
    | mk isFail isOk =>
      rw [List.cons_append, countRecovered_cons]
      omega

private theorem countRecovered_append_of_any_snd (a b : List (Bool × Bool))
    (hb : b.any Prod.snd = true) :
    countRecovered (a ++ b) = countFailures a + countRecovered b := by
  induction a with
  | nil => simp [countFailures]
  | cons p ps ih =>
    cases p with
    | mk isFail isOk =>
      have hAny : (ps ++ b).any Prod.snd = true := by
        simp [List.any_append, hb]
      rw [List.cons_append, countFailures_cons, countRecovered_cons]
      cases isFail <;> simp [hAny, ih] <;> omega

private theorem countRecovered_eq_zero_of_no_snd : ∀ (t : List (Bool × Bool)),
    t.any Prod.snd = false → countRecovered t = 0
  | [], _ => rfl
  | (isFail, isOk) :: rest, hNo => by
    simp only [List.any_cons, Bool.or_eq_false_iff] at hNo
    simp only [countRecovered, hNo.2, Bool.and_false, Bool.false_eq_true, ↓reduceIte, Nat.zero_add]
    exact countRecovered_eq_zero_of_no_snd rest hNo.2

private theorem exists_last_failure : ∀ (t : List (Bool × Bool)),
    0 < countFailures t →
    ∃ pre f post, t = pre ++ (true, f) :: post ∧ countFailures post = 0
  | [], h => by simp [countFailures] at h
  | (isFail, isOk) :: rest, h => by
    by_cases hRest : 0 < countFailures rest
    · obtain ⟨pre, f, post, hEq, hPost0⟩ := exists_last_failure rest hRest
      exact ⟨(isFail, isOk) :: pre, f, post, by simp [hEq], hPost0⟩
    · have hRest0 : countFailures rest = 0 := by omega
      cases isFail with
      | false =>
        rw [countFailures_cons] at h
        simp only [Bool.false_eq_true, ↓reduceIte, Nat.zero_add] at h
        exact False.elim (hRest h)
      | true =>
        exact ⟨[], isOk, rest, rfl, hRest0⟩

private theorem exists_first_failure : ∀ (t : List (Bool × Bool)),
    0 < countFailures t →
    ∃ pre f post, t = pre ++ (true, f) :: post ∧ countFailures pre = 0
  | [], h => by simp [countFailures] at h
  | (isFail, isOk) :: rest, h => by
    cases isFail with
    | true =>
      exact ⟨[], isOk, rest, rfl, rfl⟩
    | false =>
      rw [countFailures_cons] at h
      simp only [Bool.false_eq_true, ↓reduceIte, Nat.zero_add] at h
      obtain ⟨pre, f, post, hEq, hPre0⟩ := exists_first_failure rest h
      refine ⟨(false, isOk) :: pre, f, post, by simp [hEq], ?_⟩
      rw [countFailures_cons]
      simpa using hPre0

/--
Theorem 33: When `errors = []`, `failure_recovery` returns `NOT_APPLICABLE` (`score = none`)
iff the prepared recovery timeline contains zero failure events.
-/
theorem failureRecovery_notApplicable_iff
    (topCalls : List ToolCall) (trace : List TraceStep)
    (criteria : AgentCriteria) (defaultThreshold : NNRat) :
    let out := evaluateFailureRecovery [] topCalls trace criteria defaultThreshold
    let tl := buildRecoveryTimeline (prepareAgentInputs topCalls trace) trace
    (out.status = .notApplicable ↔ countFailures tl = 0) ∧
    (out.status = .notApplicable → out.score = none) := by
  dsimp only
  unfold evaluateFailureRecovery failureRecoveryRawScore
  simp only [List.isEmpty_nil, Bool.not_true, Bool.false_eq_true, ↓reduceIte]
  cases h : countFailures (buildRecoveryTimeline (prepareAgentInputs topCalls trace) trace) with
  | zero =>
    simp
  | succ n =>
    dsimp only
    unfold finalizeAgentMetric
    cases NNRat.leBool (resolveThreshold criteria "failure_recovery" defaultThreshold)
      ⟨countRecovered (buildRecoveryTimeline (prepareAgentInputs topCalls trace) trace), n + 1, Nat.succ_pos n⟩ <;>
      simp

/-- Theorem 34: Whenever `failure_recovery` yields `some score`, `score ∈ [0, 1]`. -/
theorem failureRecovery_bounds (timeline : List (Bool × Bool)) (s : NNRat)
    (h : failureRecoveryRawScore timeline = some s) :
    NNRat.zero ≤ s ∧ s ≤ NNRat.one := by
  unfold failureRecoveryRawScore at h
  cases hCf : countFailures timeline with
  | zero => simp [hCf] at h
  | succ n =>
    simp only [hCf, Option.some.injEq] at h
    subst h
    refine ⟨NNRat.zero_le _, ?_⟩
    rw [NNRat.le_one_iff]
    dsimp only
    have hLe := countRecovered_le_countFailures timeline
    omega

/--
Theorem 35: `failure_recovery` achieves score `1` iff a `SUCCESS` event occurs strictly after
the last failure event in the timeline.
-/
theorem failureRecovery_eq_one_iff_success_after_last_failure (timeline : List (Bool × Bool))
    (s : NNRat) (hScore : failureRecoveryRawScore timeline = some s) :
    NNRat.equiv s NNRat.one ↔
      ∃ pre f post, timeline = pre ++ (true, f) :: post ∧
        countFailures post = 0 ∧ post.any Prod.snd = true := by
  unfold failureRecoveryRawScore at hScore
  cases hCf : countFailures timeline with
  | zero => simp [hCf] at hScore
  | succ n =>
    simp only [hCf, Option.some.injEq] at hScore
    subst hScore
    rw [NNRat.equiv_one_iff]
    dsimp only
    constructor
    · intro hRecEq
      have hPos : 0 < countFailures timeline := by omega
      obtain ⟨pre, f, post, hEq, hPost0⟩ := exists_last_failure timeline hPos
      refine ⟨pre, f, post, hEq, hPost0, ?_⟩
      have hRecLe := countRecovered_append_le pre ((true, f) :: post)
      have hCfSplit : countFailures timeline = countFailures pre + 1 := by
        rw [hEq, countFailures_append, countFailures_cons]
        simp only [↓reduceIte]
        omega
      have hPostRec0 : countRecovered post = 0 := countRecovered_eq_zero_of_countFailures_zero hPost0
      rw [hEq] at hRecEq
      simp only [countRecovered, Bool.true_and, hPostRec0, Nat.add_zero] at hRecLe
      cases hAny : post.any Prod.snd with
      | true => rfl
      | false =>
        simp only [hAny, Bool.false_eq_true, ↓reduceIte, Nat.add_zero] at hRecLe
        omega
    · rintro ⟨pre, f, post, hEq, hPost0, hAny⟩
      have hPostRec0 : countRecovered post = 0 := countRecovered_eq_zero_of_countFailures_zero hPost0
      have hRec : countRecovered timeline = countFailures pre + 1 := by
        rw [hEq, countRecovered_append_of_any_snd pre ((true, f) :: post) (by simp [List.any_cons, hAny])]
        simp [countRecovered, hAny, hPostRec0]
      have hTot : countFailures timeline = countFailures pre + 1 := by
        rw [hEq, countFailures_append, countFailures_cons]
        simp only [↓reduceIte]
        omega
      omega

/--
Theorem 36: `failure_recovery` yields score `0` iff no `SUCCESS` event occurs strictly after
the first failure event in the timeline.
-/
theorem failureRecovery_eq_zero_iff_no_success_after_first_failure (timeline : List (Bool × Bool))
    (s : NNRat) (hScore : failureRecoveryRawScore timeline = some s) :
    NNRat.equiv s NNRat.zero ↔
      ∃ pre f post, timeline = pre ++ (true, f) :: post ∧
        countFailures pre = 0 ∧ post.any Prod.snd = false := by
  unfold failureRecoveryRawScore at hScore
  cases hCf : countFailures timeline with
  | zero => simp [hCf] at hScore
  | succ n =>
    simp only [hCf, Option.some.injEq] at hScore
    subst hScore
    rw [NNRat.equiv_zero_iff]
    dsimp only
    constructor
    · intro hRec0
      have hPos : 0 < countFailures timeline := by omega
      obtain ⟨pre, f, post, hEq, hPre0⟩ := exists_first_failure timeline hPos
      refine ⟨pre, f, post, hEq, hPre0, ?_⟩
      have hGe := countRecovered_append_ge_right pre ((true, f) :: post)
      rw [← hEq, hRec0] at hGe
      simp only [countRecovered, Bool.true_and] at hGe
      cases hAny : post.any Prod.snd with
      | false => rfl
      | true =>
        simp only [hAny, ↓reduceIte] at hGe
        omega
    · rintro ⟨pre, f, post, hEq, hPre0, hNo⟩
      have hPostRec0 : countRecovered post = 0 := countRecovered_eq_zero_of_no_snd post hNo
      have hTailRec0 : countRecovered ((true, f) :: post) = 0 := by
        simp [countRecovered, hNo, hPostRec0]
      have hLe := countRecovered_append_le pre ((true, f) :: post)
      rw [← hEq, hPre0, hTailRec0] at hLe
      omega

/--
Theorem 37: Any timeline ending in a failure event (`(true, f)`) always yields `some s` with
strict inequality `s < 1`.
-/
theorem failureRecovery_trailing_failure_lt_one (timeline : List (Bool × Bool)) (f : Bool) :
    ∃ s : NNRat, failureRecoveryRawScore (timeline ++ [(true, f)]) = some s ∧ s < NNRat.one := by
  have hCf : countFailures (timeline ++ [(true, f)]) = countFailures timeline + 1 := by
    rw [countFailures_append]
    simp [countFailures]
  unfold failureRecoveryRawScore
  rw [hCf]
  refine ⟨⟨countRecovered (timeline ++ [(true, f)]), countFailures timeline + 1,
    Nat.succ_pos _⟩, rfl, ?_⟩
  show countRecovered (timeline ++ [(true, f)]) * 1 < 1 * (countFailures timeline + 1)
  have hLe := countRecovered_append_le timeline [(true, f)]
  have hLast : countRecovered [(true, f)] = 0 := by simp [countRecovered]
  omega

/--
Theorem 38: Appending a terminal `SUCCESS` event (`(false, true)`) to any timeline containing
at least one failure always achieves exact score `1`.
-/
theorem failureRecovery_append_success_achieves_one (timeline : List (Bool × Bool))
    (hFail : 0 < countFailures timeline) :
    ∃ s : NNRat, failureRecoveryRawScore (timeline ++ [(false, true)]) = some s ∧
      NNRat.equiv s NNRat.one := by
  have hCf : countFailures (timeline ++ [(false, true)]) = countFailures timeline := by
    rw [countFailures_append]
    simp [countFailures]
  cases hN : countFailures timeline with
  | zero => omega
  | succ n =>
    unfold failureRecoveryRawScore
    rw [hCf, hN]
    refine ⟨⟨countRecovered (timeline ++ [(false, true)]), n + 1, Nat.succ_pos n⟩, rfl, ?_⟩
    rw [NNRat.equiv_one_iff]
    dsimp only
    have hRec := countRecovered_append_of_any_snd timeline [(false, true)] (by simp)
    have hLast : countRecovered [(false, true)] = 0 := by simp [countRecovered]
    omega

end EvalForgeFormal.Agent
