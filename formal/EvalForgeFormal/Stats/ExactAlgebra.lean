import EvalForgeFormal.Retrieval.ExactRat
import EvalForgeFormal.Calibration.ExactMath

namespace EvalForgeFormal.Stats

open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration

/-!
# Exact-Rational Statistical Algebra (Pure Lean 4 `Init`)

Extends `NNRat` (`EvalForgeFormal.Retrieval`) and `SignedRat` (`EvalForgeFormal.Calibration`)
with exact signed order, arithmetic, `[-1, 1]` clamping, squared deviations (`sqNNRat`),
unbiased sample variance, and exact rational Welch–Satterthwaite degrees of freedom without
introducing Mathlib or irrational square roots.
-/

private theorem nat_two_mul_le_sq_add_sq_of_le {u v : Nat} (h : u ≤ v) :
    2 * u * v ≤ u * u + v * v := by
  obtain ⟨d, rfl⟩ := Nat.exists_eq_add_of_le h
  have hL : 2 * u * (u + d) = 2 * (u * u) + 2 * (u * d) := by
    rw [Nat.mul_add, Nat.mul_assoc, Nat.mul_assoc]
  have hR : u * u + (u + d) * (u + d) = 2 * (u * u) + 2 * (u * d) + d * d := by
    rw [Nat.add_mul, Nat.mul_add, Nat.mul_add, Nat.mul_comm d u]
    omega
  rw [hL, hR]
  exact Nat.le_add_right _ _

private theorem nat_two_mul_le_sq_add_sq (u v : Nat) : 2 * u * v ≤ u * u + v * v := by
  by_cases h : u ≤ v
  · exact nat_two_mul_le_sq_add_sq_of_le h
  · have hv : v ≤ u := by omega
    have h1 := nat_two_mul_le_sq_add_sq_of_le hv
    rw [Nat.mul_assoc, Nat.mul_comm v u, ← Nat.mul_assoc, Nat.add_comm (v * v) (u * u)] at h1
    exact h1

private theorem nat_mul4_ac_bd (a b c d : Nat) : (a * b) * (c * d) = (a * c) * (b * d) := by
  calc
    (a * b) * (c * d) = a * (b * (c * d)) := Nat.mul_assoc _ _ _
    _ = a * (c * (b * d)) := by rw [Nat.mul_left_comm b c d]
    _ = (a * c) * (b * d) := (Nat.mul_assoc _ _ _).symm

private theorem int_mul4_ac_bd (a b c d : Int) : (a * b) * (c * d) = (a * c) * (b * d) := by
  calc
    (a * b) * (c * d) = a * (b * (c * d)) := Int.mul_assoc _ _ _
    _ = a * (c * (b * d)) := by rw [Int.mul_left_comm b c d]
    _ = (a * c) * (b * d) := (Int.mul_assoc _ _ _).symm

private theorem int_mul4_ad_bc (a b c d : Int) : (a * b) * (c * d) = (a * d) * (b * c) := by
  rw [Int.mul_comm c d]
  exact int_mul4_ac_bd a b d c

/-- Exact signed rational `+1` (`1 / 1`). -/
def sOne : SignedRat := ⟨1, 1, Nat.zero_lt_one⟩

/-- Exact signed rational `-1` (`-1 / 1`). -/
def sNegOne : SignedRat := ⟨-1, 1, Nat.zero_lt_one⟩

/-- Embed a non-negative rational into `SignedRat`. -/
def ofNNRat (r : NNRat) : SignedRat := ⟨(r.num : Int), r.den, r.denPos⟩

/-- Exact negation of a signed rational. -/
def sNeg (s : SignedRat) : SignedRat := ⟨-s.num, s.den, s.denPos⟩

/-- Exact addition of signed rationals. -/
def sAdd (a b : SignedRat) : SignedRat :=
  ⟨a.num * (b.den : Int) + b.num * (a.den : Int), a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩

/-- Exact subtraction of signed rationals (`a - b`). -/
def sSub (a b : SignedRat) : SignedRat :=
  sAdd a (sNeg b)

/-- Exact multiplication of signed rationals. -/
def sMul (a b : SignedRat) : SignedRat :=
  ⟨a.num * b.num, a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩

/-- Exact division of a signed rational by a strictly positive natural number. -/
def sDivNat (a : SignedRat) (n : Nat) (hn : 0 < n) : SignedRat :=
  ⟨a.num, a.den * n, Nat.mul_pos a.denPos hn⟩

/-- Exact non-negative square `s²` in `NNRat`. -/
def sSqNNRat (s : SignedRat) : NNRat :=
  ⟨s.num.natAbs * s.num.natAbs, s.den * s.den, Nat.mul_pos s.denPos s.denPos⟩

/-- Non-strict order on `SignedRat` via cross-multiplication. -/
def sLe (a b : SignedRat) : Prop :=
  a.num * (b.den : Int) ≤ b.num * (a.den : Int)

/-- Strict order on `SignedRat` via cross-multiplication. -/
def sLt (a b : SignedRat) : Prop :=
  a.num * (b.den : Int) < b.num * (a.den : Int)

infix:50 " ≤ₛ " => sLe
infix:50 " <ₛ " => sLt

instance (a b : SignedRat) : Decidable (a ≤ₛ b) :=
  inferInstanceAs (Decidable (a.num * (b.den : Int) ≤ b.num * (a.den : Int)))

instance (a b : SignedRat) : Decidable (a <ₛ b) :=
  inferInstanceAs (Decidable (a.num * (b.den : Int) < b.num * (a.den : Int)))

/-- Clamp a signed rational to the closed unit delta interval `[-1, 1]`. -/
def sClampUnit (s : SignedRat) : SignedRat :=
  if s.num < -((s.den : Int)) then sNegOne
  else if (s.den : Int) < s.num then sOne
  else s

theorem sLe_refl (a : SignedRat) : a ≤ₛ a := Int.le_refl _

theorem sLe_of_equiv {a b : SignedRat} (h : a ≈ₛ b) : a ≤ₛ b := Int.le_of_eq h

theorem sEquiv_of_sLe_antisymm {a b : SignedRat} (h1 : a ≤ₛ b) (h2 : b ≤ₛ a) : a ≈ₛ b :=
  Int.le_antisymm h1 h2

theorem sLe_trans {a b c : SignedRat} (hab : a ≤ₛ b) (hbc : b ≤ₛ c) : a ≤ₛ c := by
  unfold sLe at *
  have hbPos : (0 : Int) < (b.den : Int) := by have := b.denPos; omega
  have haNonneg : (0 : Int) ≤ (a.den : Int) := by have := a.denPos; omega
  have hcNonneg : (0 : Int) ≤ (c.den : Int) := by have := c.denPos; omega
  have h1 : (a.num * (b.den : Int)) * (c.den : Int) ≤ (b.num * (a.den : Int)) * (c.den : Int) :=
    Int.mul_le_mul_of_nonneg_right hab hcNonneg
  have h2 : (b.num * (c.den : Int)) * (a.den : Int) ≤ (c.num * (b.den : Int)) * (a.den : Int) :=
    Int.mul_le_mul_of_nonneg_right hbc haNonneg
  have hmid : (b.num * (a.den : Int)) * (c.den : Int) = (b.num * (c.den : Int)) * (a.den : Int) := by
    rw [Int.mul_assoc, Int.mul_comm (a.den : Int) (c.den : Int), ← Int.mul_assoc]
  have hcomb : (a.num * (b.den : Int)) * (c.den : Int) ≤ (c.num * (b.den : Int)) * (a.den : Int) :=
    Int.le_trans h1 (hmid ▸ h2)
  have hl : (a.num * (b.den : Int)) * (c.den : Int) = (b.den : Int) * (a.num * (c.den : Int)) := by
    rw [Int.mul_assoc, Int.mul_left_comm]
  have hr : (c.num * (b.den : Int)) * (a.den : Int) = (b.den : Int) * (c.num * (a.den : Int)) := by
    rw [Int.mul_assoc, Int.mul_left_comm]
  rw [hl, hr] at hcomb
  exact Int.le_of_mul_le_mul_left hcomb hbPos

theorem sLe_of_equiv_left {a₁ a₂ b : SignedRat} (ha : a₁ ≈ₛ a₂) (h : a₁ ≤ₛ b) : a₂ ≤ₛ b :=
  sLe_trans (sLe_of_equiv ha.symm) h

theorem sLe_of_equiv_right {a b₁ b₂ : SignedRat} (hb : b₁ ≈ₛ b₂) (h : a ≤ₛ b₁) : a ≤ₛ b₂ :=
  sLe_trans h (sLe_of_equiv hb)

theorem sNeg_involutive (s : SignedRat) : sNeg (sNeg s) = s := by
  cases s with
  | mk num den denPos =>
    simp [sNeg]

theorem sNeg_equiv_congr {a b : SignedRat} (h : a ≈ₛ b) : sNeg a ≈ₛ sNeg b := by
  unfold sNeg SignedRat.equiv at *
  dsimp only
  rw [Int.neg_mul, Int.neg_mul, h]

theorem sNeg_le_sNeg_iff (a b : SignedRat) : sNeg b ≤ₛ sNeg a ↔ a ≤ₛ b := by
  unfold sNeg sLe
  dsimp only
  rw [Int.neg_mul, Int.neg_mul]
  omega

theorem sEquiv_zero_iff (s : SignedRat) : s ≈ₛ SignedRat.zero ↔ s.num = 0 := by
  unfold SignedRat.equiv SignedRat.zero
  simp

theorem sNeg_zero_equiv : sNeg SignedRat.zero ≈ₛ SignedRat.zero := by
  rw [sEquiv_zero_iff]
  rfl

theorem sNeg_subNNRat (a b : NNRat) : sNeg (SignedRat.subNNRat a b) ≈ₛ SignedRat.subNNRat b a := by
  unfold sNeg SignedRat.subNNRat SignedRat.equiv
  dsimp only
  rw [Nat.mul_comm b.den a.den]
  have h1 : -(((a.num * b.den : Nat) : Int) - ((b.num * a.den : Nat) : Int)) =
            ((b.num * a.den : Nat) : Int) - ((a.num * b.den : Nat) : Int) := by omega
  rw [h1]

theorem sAdd_comm_equiv (a b : SignedRat) : sAdd a b ≈ₛ sAdd b a := by
  unfold sAdd SignedRat.equiv
  dsimp only
  rw [Int.add_comm (a.num * (b.den : Int)) (b.num * (a.den : Int)), Nat.mul_comm b.den a.den]

theorem sAdd_assoc_equiv (a b c : SignedRat) : sAdd (sAdd a b) c ≈ₛ sAdd a (sAdd b c) := by
  unfold sAdd SignedRat.equiv
  dsimp only
  have hden : ((a.den * (b.den * c.den) : Nat) : Int) = (((a.den * b.den) * c.den : Nat) : Int) := by
    rw [Nat.mul_assoc]
  rw [hden]
  apply congrArg (· * (((a.den * b.den) * c.den : Nat) : Int))
  rw [Int.natCast_mul, Int.natCast_mul, Int.add_mul, Int.add_mul]
  have t1 : (a.num * (b.den : Int)) * (c.den : Int) = a.num * ((b.den : Int) * (c.den : Int)) :=
    Int.mul_assoc _ _ _
  have t2 : (b.num * (a.den : Int)) * (c.den : Int) = (b.num * (c.den : Int)) * (a.den : Int) := by
    rw [Int.mul_assoc, Int.mul_comm (a.den : Int) (c.den : Int), ← Int.mul_assoc]
  have t3 : c.num * ((a.den : Int) * (b.den : Int)) = (c.num * (b.den : Int)) * (a.den : Int) := by
    rw [Int.mul_comm (a.den : Int) (b.den : Int), Int.mul_assoc]
  rw [t1, t2, t3, Int.add_assoc]

theorem sAdd_equiv_congr {a₁ a₂ b₁ b₂ : SignedRat} (ha : a₁ ≈ₛ a₂) (hb : b₁ ≈ₛ b₂) :
    sAdd a₁ b₁ ≈ₛ sAdd a₂ b₂ := by
  unfold sAdd SignedRat.equiv at *
  dsimp only
  rw [Int.natCast_mul, Int.natCast_mul, Int.add_mul, Int.add_mul]
  have h1 : (a₁.num * (b₁.den : Int)) * ((a₂.den : Int) * (b₂.den : Int)) =
            (a₂.num * (b₂.den : Int)) * ((a₁.den : Int) * (b₁.den : Int)) := by
    calc
      (a₁.num * (b₁.den : Int)) * ((a₂.den : Int) * (b₂.den : Int))
          = (a₁.num * (a₂.den : Int)) * ((b₁.den : Int) * (b₂.den : Int)) := int_mul4_ac_bd _ _ _ _
      _ = (a₂.num * (a₁.den : Int)) * ((b₁.den : Int) * (b₂.den : Int)) := by rw [ha]
      _ = (a₂.num * (b₂.den : Int)) * ((a₁.den : Int) * (b₁.den : Int)) := by
            rw [int_mul4_ad_bc, Int.mul_comm (a₁.den : Int) (b₁.den : Int)]
  have h2 : (b₁.num * (a₁.den : Int)) * ((a₂.den : Int) * (b₂.den : Int)) =
            (b₂.num * (a₂.den : Int)) * ((a₁.den : Int) * (b₁.den : Int)) := by
    calc
      (b₁.num * (a₁.den : Int)) * ((a₂.den : Int) * (b₂.den : Int))
          = (b₁.num * (b₂.den : Int)) * ((a₁.den : Int) * (a₂.den : Int)) := int_mul4_ad_bc _ _ _ _
      _ = (b₂.num * (b₁.den : Int)) * ((a₁.den : Int) * (a₂.den : Int)) := by rw [hb]
      _ = (b₂.num * (a₂.den : Int)) * ((a₁.den : Int) * (b₁.den : Int)) := by
            rw [int_mul4_ad_bc, Int.mul_comm (b₁.den : Int) (a₁.den : Int)]
  rw [h1, h2]

theorem sSub_equiv_congr {a₁ a₂ b₁ b₂ : SignedRat} (ha : a₁ ≈ₛ a₂) (hb : b₁ ≈ₛ b₂) :
    sSub a₁ b₁ ≈ₛ sSub a₂ b₂ :=
  sAdd_equiv_congr ha (sNeg_equiv_congr hb)

theorem sNeg_sAdd_equiv (a b : SignedRat) : sNeg (sAdd a b) ≈ₛ sAdd (sNeg a) (sNeg b) := by
  unfold sNeg sAdd SignedRat.equiv
  dsimp only
  rw [Int.neg_add, Int.neg_mul, Int.neg_mul]

theorem sNeg_sSub_equiv (a b : SignedRat) : sNeg (sSub a b) ≈ₛ sSub (sNeg a) (sNeg b) := by
  unfold sSub
  exact sNeg_sAdd_equiv a (sNeg b)

theorem sSub_ofNNRat_le_self (d : SignedRat) (m : NNRat) : sSub d (ofNNRat m) ≤ₛ d := by
  unfold sSub sAdd sNeg ofNNRat sLe
  dsimp only
  rw [Int.natCast_mul, Int.add_mul, Int.neg_mul, Int.neg_mul]
  have h1 : (d.num * (m.den : Int)) * (d.den : Int) = d.num * ((d.den : Int) * (m.den : Int)) := by
    rw [Int.mul_assoc, Int.mul_comm (m.den : Int) (d.den : Int)]
  have h2 : (0 : Int) ≤ (((m.num : Int) * (d.den : Int)) * (d.den : Int)) := by
    have hm : (0 : Int) ≤ (m.num : Int) := Int.natCast_nonneg m.num
    have hd : (0 : Int) ≤ (d.den : Int) := Int.natCast_nonneg d.den
    exact Int.mul_nonneg (Int.mul_nonneg hm hd) hd
  rw [h1]
  omega

theorem self_le_sAdd_ofNNRat (d : SignedRat) (m : NNRat) : d ≤ₛ sAdd d (ofNNRat m) := by
  unfold sAdd ofNNRat sLe
  dsimp only
  rw [Int.natCast_mul, Int.add_mul]
  have h1 : d.num * ((d.den : Int) * (m.den : Int)) = (d.num * (m.den : Int)) * (d.den : Int) := by
    rw [Int.mul_comm (d.den : Int) (m.den : Int), ← Int.mul_assoc]
  have h2 : (0 : Int) ≤ (((m.num : Int) * (d.den : Int)) * (d.den : Int)) := by
    have hm : (0 : Int) ≤ (m.num : Int) := Int.natCast_nonneg m.num
    have hd : (0 : Int) ≤ (d.den : Int) := Int.natCast_nonneg d.den
    exact Int.mul_nonneg (Int.mul_nonneg hm hd) hd
  rw [h1]
  omega

theorem sNeg_sAdd_ofNNRat (d : SignedRat) (m : NNRat) :
    sNeg (sAdd d (ofNNRat m)) ≈ₛ sSub (sNeg d) (ofNNRat m) := by
  unfold sSub
  exact sNeg_sAdd_equiv d (ofNNRat m)

theorem sNeg_sSub_ofNNRat (d : SignedRat) (m : NNRat) :
    sNeg (sSub d (ofNNRat m)) ≈ₛ sAdd (sNeg d) (ofNNRat m) := by
  unfold sSub
  have h := sNeg_sAdd_equiv d (sNeg (ofNNRat m))
  rw [sNeg_involutive] at h
  exact h

theorem sClampUnit_inUnitInterval (s : SignedRat) : (sClampUnit s).inUnitInterval := by
  unfold sClampUnit SignedRat.inUnitInterval sNegOne sOne
  by_cases h1 : s.num < -((s.den : Int))
  · simp [h1]
  · by_cases h2 : (s.den : Int) < s.num
    · simp [h1, h2]
    · simp only [h1, h2, ↓reduceIte]
      omega

theorem sNegOne_le_of_inUnit {s : SignedRat} (h : s.inUnitInterval) : sNegOne ≤ₛ s := by
  rcases h with ⟨hlo, _⟩
  unfold sNegOne sLe
  dsimp only
  omega

theorem le_sOne_of_inUnit {s : SignedRat} (h : s.inUnitInterval) : s ≤ₛ sOne := by
  rcases h with ⟨_, hhi⟩
  unfold sOne sLe
  dsimp only
  omega

theorem sClampUnit_bounds (s : SignedRat) : sNegOne ≤ₛ sClampUnit s ∧ sClampUnit s ≤ₛ sOne :=
  ⟨sNegOne_le_of_inUnit (sClampUnit_inUnitInterval s),
   le_sOne_of_inUnit (sClampUnit_inUnitInterval s)⟩

theorem sClampUnit_of_inUnit {s : SignedRat} (h : s.inUnitInterval) : sClampUnit s = s := by
  rcases h with ⟨hlo, hhi⟩
  unfold sClampUnit
  have h1 : ¬ (s.num < -((s.den : Int))) := by omega
  have h2 : ¬ ((s.den : Int) < s.num) := by omega
  simp [h1, h2]

theorem sClampUnit_mono {a b : SignedRat} (hab : a ≤ₛ b) : sClampUnit a ≤ₛ sClampUnit b := by
  unfold sClampUnit
  by_cases ha1 : a.num < -((a.den : Int))
  · simp only [ha1, ↓reduceIte]
    exact sNegOne_le_of_inUnit (sClampUnit_inUnitInterval b)
  · by_cases ha2 : (a.den : Int) < a.num
    · simp only [ha1, ha2, ↓reduceIte]
      have hbPos : (0 : Int) < (b.den : Int) := by have := b.denPos; omega
      have haPos : (0 : Int) < (a.den : Int) := by have := a.denPos; omega
      have hmul : (a.den : Int) * (b.den : Int) < a.num * (b.den : Int) :=
        Int.mul_lt_mul_of_pos_right ha2 hbPos
      have hle : (a.den : Int) * (b.den : Int) < b.num * (a.den : Int) :=
        Int.lt_of_lt_of_le hmul hab
      have hcomm : (a.den : Int) * (b.den : Int) = (b.den : Int) * (a.den : Int) :=
        Int.mul_comm _ _
      rw [hcomm] at hle
      have hb2 : (b.den : Int) < b.num := Int.lt_of_mul_lt_mul_right hle (Int.le_of_lt haPos)
      have hb1 : ¬ (b.num < -((b.den : Int))) := by omega
      simp only [hb1, hb2, ↓reduceIte]
      exact sLe_refl sOne
    · simp only [ha1, ha2, ↓reduceIte]
      by_cases hb1 : b.num < -((b.den : Int))
      · have hbPos : (0 : Int) < (b.den : Int) := by have := b.denPos; omega
        have haPos : (0 : Int) < (a.den : Int) := by have := a.denPos; omega
        have hlo : -((a.den : Int)) ≤ a.num := by omega
        have h1 : -((a.den : Int)) * (b.den : Int) ≤ a.num * (b.den : Int) :=
          Int.mul_le_mul_of_nonneg_right hlo (Int.le_of_lt hbPos)
        have h2 : b.num * (a.den : Int) < -((b.den : Int)) * (a.den : Int) :=
          Int.mul_lt_mul_of_pos_right hb1 haPos
        have heq : -((a.den : Int)) * (b.den : Int) = -((b.den : Int)) * (a.den : Int) := by
          rw [Int.neg_mul, Int.neg_mul, Int.mul_comm (a.den : Int) (b.den : Int)]
        have hlt : b.num * (a.den : Int) < a.num * (b.den : Int) :=
          Int.lt_of_lt_of_le (heq ▸ h2) h1
        have hcontra : a.num * (b.den : Int) ≤ b.num * (a.den : Int) := hab
        omega
      · by_cases hb2 : (b.den : Int) < b.num
        · simp only [hb1, hb2, ↓reduceIte]
          have haUnit : a.inUnitInterval := by unfold SignedRat.inUnitInterval; omega
          exact le_sOne_of_inUnit haUnit
        · simp only [hb1, hb2, ↓reduceIte]
          exact hab

theorem sClampUnit_equiv_congr {a b : SignedRat} (hab : a ≈ₛ b) :
    sClampUnit a ≈ₛ sClampUnit b :=
  sEquiv_of_sLe_antisymm
    (sClampUnit_mono (sLe_of_equiv hab))
    (sClampUnit_mono (sLe_of_equiv hab.symm))

theorem sClampUnit_neg (s : SignedRat) : sClampUnit (sNeg s) ≈ₛ sNeg (sClampUnit s) := by
  unfold sClampUnit sNeg SignedRat.equiv sNegOne sOne
  by_cases h1 : s.num < -((s.den : Int))
  · have hn1 : ¬ (-s.num < -((s.den : Int))) := by omega
    have hn2 : (s.den : Int) < -s.num := by omega
    simp [h1, hn1, hn2]
  · by_cases h2 : (s.den : Int) < s.num
    · have hn1 : -s.num < -((s.den : Int)) := by omega
      simp [h1, h2, hn1]
    · have hn1 : ¬ (-s.num < -((s.den : Int))) := by omega
      have hn2 : ¬ ((s.den : Int) < -s.num) := by omega
      simp [h1, h2, hn1, hn2]

theorem sSqNNRat_neg (s : SignedRat) : sSqNNRat (sNeg s) = sSqNNRat s := by
  unfold sSqNNRat sNeg
  simp [Int.natAbs_neg]

theorem sSqNNRat_equiv_zero_iff (s : SignedRat) : sSqNNRat s ≈ NNRat.zero ↔ s.num = 0 := by
  unfold sSqNNRat
  rw [NNRat.equiv_zero_iff]
  dsimp only
  constructor
  · intro h
    cases Nat.mul_eq_zero.mp h with
    | inl h0 => exact Int.natAbs_eq_zero.mp h0
    | inr h0 => exact Int.natAbs_eq_zero.mp h0
  · intro h
    simp [h]

theorem sSqNNRat_equiv_congr {a b : SignedRat} (h : a ≈ₛ b) : sSqNNRat a ≈ sSqNNRat b := by
  unfold sSqNNRat NNRat.equiv
  dsimp only
  have habs : (a.num * (b.den : Int)).natAbs = (b.num * (a.den : Int)).natAbs := by
    rw [h]
  rw [Int.natAbs_mul, Int.natAbs_mul, Int.natAbs_natCast, Int.natAbs_natCast] at habs
  have hsq : (a.num.natAbs * b.den) * (a.num.natAbs * b.den) =
             (b.num.natAbs * a.den) * (b.num.natAbs * a.den) := by
    rw [habs]
  rw [nat_mul4_ac_bd a.num.natAbs b.den a.num.natAbs b.den,
      nat_mul4_ac_bd b.num.natAbs a.den b.num.natAbs a.den] at hsq
  exact hsq

/-- Exact sum of a list of signed rationals. -/
def sSumList : List SignedRat → SignedRat
  | [] => SignedRat.zero
  | x :: xs => sAdd x (sSumList xs)

/-- Exact arithmetic mean of a non-empty list of signed rationals. -/
def sMeanList (xs : List SignedRat) (h : 0 < xs.length) : SignedRat :=
  sDivNat (sSumList xs) xs.length h

theorem sSumList_perm {xs ys : List SignedRat} (hp : List.Perm xs ys) :
    sSumList xs ≈ₛ sSumList ys := by
  induction hp with
  | nil => exact SignedRat.equiv_refl _
  | cons x _ ih => exact sAdd_equiv_congr (SignedRat.equiv_refl x) ih
  | swap x y l =>
    let s := sSumList l
    have h1 : sAdd y (sAdd x s) ≈ₛ sAdd (sAdd y x) s := (sAdd_assoc_equiv y x s).symm
    have h2 : sAdd (sAdd y x) s ≈ₛ sAdd (sAdd x y) s :=
      sAdd_equiv_congr (sAdd_comm_equiv y x) (SignedRat.equiv_refl s)
    have h3 : sAdd (sAdd x y) s ≈ₛ sAdd x (sAdd y s) := sAdd_assoc_equiv x y s
    exact SignedRat.equiv_trans h1 (SignedRat.equiv_trans h2 h3)
  | trans _ _ ih1 ih2 => exact SignedRat.equiv_trans ih1 ih2

theorem sDivNat_equiv_congr {a b : SignedRat} {m n : Nat} (hab : a ≈ₛ b) (hmn : m = n)
    (hm : 0 < m) (hn : 0 < n) : sDivNat a m hm ≈ₛ sDivNat b n hn := by
  subst hmn
  unfold sDivNat SignedRat.equiv at *
  dsimp only
  rw [Int.natCast_mul, Int.natCast_mul, ← Int.mul_assoc, ← Int.mul_assoc, hab]

theorem sMeanList_perm {xs ys : List SignedRat} (hp : List.Perm xs ys)
    (hx : 0 < xs.length) (hy : 0 < ys.length) :
    sMeanList xs hx ≈ₛ sMeanList ys hy :=
  sDivNat_equiv_congr (sSumList_perm hp) hp.length_eq hx hy

theorem sSumList_neg (xs : List SignedRat) : sSumList (xs.map sNeg) ≈ₛ sNeg (sSumList xs) := by
  induction xs with
  | nil =>
    exact sNeg_zero_equiv.symm
  | cons x xs ih =>
    simp only [List.map_cons, sSumList]
    exact SignedRat.equiv_trans
      (sAdd_equiv_congr (SignedRat.equiv_refl (sNeg x)) ih)
      (sNeg_sAdd_equiv x (sSumList xs)).symm

theorem sMeanList_neg (xs : List SignedRat) (h : 0 < xs.length)
    (h' : 0 < (xs.map sNeg).length) :
    sMeanList (xs.map sNeg) h' ≈ₛ sNeg (sMeanList xs h) := by
  have hsum : sSumList (xs.map sNeg) ≈ₛ sNeg (sSumList xs) := sSumList_neg xs
  have hlen : (xs.map sNeg).length = xs.length := List.length_map _
  have hdiv : sDivNat (sSumList (xs.map sNeg)) (xs.map sNeg).length h' ≈ₛ
              sDivNat (sNeg (sSumList xs)) xs.length h :=
    sDivNat_equiv_congr hsum hlen h' h
  exact hdiv

/-- Exact paired per-case differences `cand_i - base_i`. -/
def pairedDiffs (base cand : List NNRat) : List SignedRat :=
  List.zipWith (fun b c => SignedRat.subNNRat c b) base cand

theorem pairedDiffs_length (base cand : List NNRat) (h : base.length = cand.length) :
    (pairedDiffs base cand).length = base.length := by
  unfold pairedDiffs
  rw [List.length_zipWith, h, Nat.min_self]

theorem pairedDiffs_swap (base cand : List NNRat) :
    (pairedDiffs cand base).length = (pairedDiffs base cand).length := by
  unfold pairedDiffs
  rw [List.length_zipWith, List.length_zipWith, Nat.min_comm]

theorem sAdd_subNNRat_equiv (a b c d : NNRat) :
    sAdd (SignedRat.subNNRat a b) (SignedRat.subNNRat c d) ≈ₛ
    SignedRat.subNNRat (a.add c) (b.add d) := by
  unfold sAdd SignedRat.subNNRat NNRat.add SignedRat.equiv
  dsimp only
  -- Express everything over Int and verify polynomial identity by distributivity
  have hL :
    ((((a.num * b.den : Nat) : Int) - ((b.num * a.den : Nat) : Int)) * ((c.den * d.den : Nat) : Int) +
     (((c.num * d.den : Nat) : Int) - ((d.num * c.den : Nat) : Int)) * ((a.den * b.den : Nat) : Int)) *
     (((a.den * c.den) * (b.den * d.den) : Nat) : Int) =
    ((((a.num * c.den + c.num * a.den) * (b.den * d.den) : Nat) : Int) -
     (((b.num * d.den + d.num * b.den) * (a.den * c.den) : Nat) : Int)) *
     (((a.den * b.den) * (c.den * d.den) : Nat) : Int) := by
    have hden : (((a.den * c.den) * (b.den * d.den) : Nat) : Int) =
                (((a.den * b.den) * (c.den * d.den) : Nat) : Int) := by
      rw [nat_mul4_ac_bd a.den c.den b.den d.den]
    rw [hden]
    apply congrArg (· * (((a.den * b.den) * (c.den * d.den) : Nat) : Int))
    push_cast
    rw [Int.sub_mul, Int.sub_mul, Int.add_mul, Int.add_mul]
    have t1 : ((a.num : Int) * (b.den : Int)) * ((c.den : Int) * (d.den : Int)) =
              ((a.num : Int) * (c.den : Int)) * ((b.den : Int) * (d.den : Int)) :=
      int_mul4_ac_bd _ _ _ _
    have t2 : ((b.num : Int) * (a.den : Int)) * ((c.den : Int) * (d.den : Int)) =
              ((b.num : Int) * (d.den : Int)) * ((a.den : Int) * (c.den : Int)) :=
      int_mul4_ad_bc _ _ _ _
    have t3 : ((c.num : Int) * (d.den : Int)) * ((a.den : Int) * (b.den : Int)) =
              ((c.num : Int) * (a.den : Int)) * ((b.den : Int) * (d.den : Int)) := by
      rw [int_mul4_ac_bd, Int.mul_comm (d.den : Int) (b.den : Int)]
    have t4 : ((d.num : Int) * (c.den : Int)) * ((a.den : Int) * (b.den : Int)) =
              ((d.num : Int) * (b.den : Int)) * ((a.den : Int) * (c.den : Int)) := by
      rw [int_mul4_ad_bc, Int.mul_comm (c.den : Int) (a.den : Int)]
    rw [t1, t2, t3, t4]
    omega
  exact hL

theorem sSumList_pairedDiffs (base cand : List NNRat) (hlen : base.length = cand.length) :
    sSumList (pairedDiffs base cand) ≈ₛ SignedRat.subNNRat (nnSumList cand) (nnSumList base) := by
  induction base generalizing cand with
  | nil =>
    cases cand with
    | nil =>
      unfold pairedDiffs sSumList nnSumList SignedRat.subNNRat SignedRat.zero SignedRat.equiv NNRat.zero
      simp
    | cons _ _ =>
      simp at hlen
  | cons b bs ih =>
    cases cand with
    | nil =>
      simp at hlen
    | cons c cs =>
      have hlen' : bs.length = cs.length := by simpa using hlen
      simp only [pairedDiffs, List.zipWith_cons_cons, sSumList, nnSumList]
      have hrec := ih cs hlen'
      have h1 : sAdd (SignedRat.subNNRat c b) (sSumList (pairedDiffs bs cs)) ≈ₛ
                sAdd (SignedRat.subNNRat c b) (SignedRat.subNNRat (nnSumList cs) (nnSumList bs)) :=
        sAdd_equiv_congr (SignedRat.equiv_refl _) hrec
      exact SignedRat.equiv_trans h1 (sAdd_subNNRat_equiv c b (nnSumList cs) (nnSumList bs))

theorem sMeanList_pairedDiffs_eq_sub_means (base cand : List NNRat)
    (hlen : base.length = cand.length)
    (hpos : 0 < base.length)
    (hdp : 0 < (pairedDiffs base cand).length)
    (hcp : 0 < cand.length) :
    sMeanList (pairedDiffs base cand) hdp ≈ₛ
    SignedRat.subNNRat (nnMeanList cand hcp) (nnMeanList base hpos) := by
  have hsum := sSumList_pairedDiffs base cand hlen
  have hdlen : (pairedDiffs base cand).length = base.length := pairedDiffs_length base cand hlen
  have h1 : sMeanList (pairedDiffs base cand) hdp ≈ₛ
            sDivNat (SignedRat.subNNRat (nnSumList cand) (nnSumList base)) base.length hpos :=
    sDivNat_equiv_congr hsum hdlen hdp hpos
  apply SignedRat.equiv_trans h1
  unfold sDivNat SignedRat.subNNRat nnMeanList NNRat.div NNRat.ofNat SignedRat.equiv
  dsimp only
  rw [← hlen]
  push_cast
  have hL :
    ((((nnSumList cand).num : Int) * ((nnSumList base).den : Int) -
      ((nnSumList base).num : Int) * ((nnSumList cand).den : Int)) *
      (((nnSumList cand).den : Int) * (base.length : Int) * (((nnSumList base).den : Int) * (base.length : Int)))) =
    ((((nnSumList cand).num : Int) * 1 * (((nnSumList base).den : Int) * (base.length : Int)) -
      ((nnSumList base).num : Int) * 1 * (((nnSumList cand).den : Int) * (base.length : Int))) *
      (((nnSumList cand).den : Int) * ((nnSumList base).den : Int) * (base.length : Int))) := by
    simp only [Int.mul_one]
    rw [Int.sub_mul, Int.sub_mul]
    have t1 :
      (((nnSumList cand).num : Int) * ((nnSumList base).den : Int)) *
        (((nnSumList cand).den : Int) * (base.length : Int) * (((nnSumList base).den : Int) * (base.length : Int))) =
      (((nnSumList cand).num : Int) * (((nnSumList base).den : Int) * (base.length : Int))) *
        (((nnSumList cand).den : Int) * ((nnSumList base).den : Int) * (base.length : Int)) := by
      have ha :
        (((nnSumList cand).num : Int) * ((nnSumList base).den : Int)) *
          ((((nnSumList cand).den : Int) * (base.length : Int)) * (((nnSumList base).den : Int) * (base.length : Int))) =
        (((nnSumList cand).num : Int) * (((nnSumList base).den : Int) * (base.length : Int))) *
          (((nnSumList base).den : Int) * (((nnSumList cand).den : Int) * (base.length : Int))) := by
        rw [int_mul4_ad_bc]
      rw [ha]
      apply congrArg ((((nnSumList cand).num : Int) * (((nnSumList base).den : Int) * (base.length : Int))) * ·)
      rw [← Int.mul_assoc, Int.mul_comm ((nnSumList base).den : Int) ((nnSumList cand).den : Int)]
    have t2 :
      (((nnSumList base).num : Int) * ((nnSumList cand).den : Int)) *
        (((nnSumList cand).den : Int) * (base.length : Int) * (((nnSumList base).den : Int) * (base.length : Int))) =
      (((nnSumList base).num : Int) * (((nnSumList cand).den : Int) * (base.length : Int))) *
        (((nnSumList cand).den : Int) * ((nnSumList base).den : Int) * (base.length : Int)) := by
      have hb :
        (((nnSumList base).num : Int) * ((nnSumList cand).den : Int)) *
          ((((nnSumList cand).den : Int) * (base.length : Int)) * (((nnSumList base).den : Int) * (base.length : Int))) =
        (((nnSumList base).num : Int) * (((nnSumList cand).den : Int) * (base.length : Int))) *
          (((nnSumList cand).den : Int) * (((nnSumList base).den : Int) * (base.length : Int))) := by
        rw [int_mul4_ac_bd]
      rw [hb]
      apply congrArg ((((nnSumList base).num : Int) * (((nnSumList cand).den : Int) * (base.length : Int))) * ·)
      rw [← Int.mul_assoc]
    rw [t1, t2]
  exact hL

/-- Exact sum of squared deviations `∑ (x_i - m)²` for `NNRat` samples. -/
def sumSqDevNNRat (xs : List NNRat) (m : NNRat) : NNRat :=
  nnSumList (xs.map fun x => sSqNNRat (SignedRat.subNNRat x m))

/-- Exact sum of squared deviations `∑ (x_i - m)²` for `SignedRat` samples. -/
def sumSqDevSigned (xs : List SignedRat) (m : SignedRat) : NNRat :=
  nnSumList (xs.map fun x => sSqNNRat (sSub x m))

/-- Exact unbiased sample variance `∑ (x_i - mean)² / (n - 1)` for `n ≥ 2` `NNRat` samples. -/
def sampleVarNNRat (xs : List NNRat) (h : 2 ≤ xs.length) : NNRat :=
  have hpos : 0 < xs.length := by omega
  have hnm1 : 0 < xs.length - 1 := by omega
  NNRat.div (sumSqDevNNRat xs (nnMeanList xs hpos)) (NNRat.ofNat (xs.length - 1)) hnm1

/-- Exact unbiased sample variance `∑ (x_i - mean)² / (n - 1)` for `n ≥ 2` `SignedRat` samples. -/
def sampleVarSigned (xs : List SignedRat) (h : 2 ≤ xs.length) : NNRat :=
  have hpos : 0 < xs.length := by omega
  have hnm1 : 0 < xs.length - 1 := by omega
  NNRat.div (sumSqDevSigned xs (sMeanList xs hpos)) (NNRat.ofNat (xs.length - 1)) hnm1

theorem nnSumList_equiv_zero_iff (xs : List NNRat) :
    nnSumList xs ≈ NNRat.zero ↔ ∀ x ∈ xs, x ≈ NNRat.zero := by
  induction xs with
  | nil =>
    simp [nnSumList, NNRat.equiv_refl]
  | cons x xs ih =>
    simp only [nnSumList, List.mem_cons, forall_eq_or_imp]
    rw [NNRat.equiv_zero_iff]
    constructor
    · intro h
      have hnum : x.num * (nnSumList xs).den + (nnSumList xs).num * x.den = 0 := h
      have hx0 : x.num = 0 := by
        have hd := (nnSumList xs).denPos
        have : x.num * (nnSumList xs).den = 0 := by omega
        cases Nat.mul_eq_zero.mp this with
        | inl h0 => exact h0
        | inr h0 => omega
      have hxs0 : (nnSumList xs).num = 0 := by
        have hd := x.denPos
        have : (nnSumList xs).num * x.den = 0 := by omega
        cases Nat.mul_eq_zero.mp this with
        | inl h0 => exact h0
        | inr h0 => omega
      exact ⟨(NNRat.equiv_zero_iff x).mpr hx0, ih.mp ((NNRat.equiv_zero_iff _).mpr hxs0)⟩
    · rintro ⟨hx, hxs⟩
      have hx0 : x.num = 0 := (NNRat.equiv_zero_iff x).mp hx
      have hxs0 : (nnSumList xs).num = 0 := (NNRat.equiv_zero_iff _).mp (ih.mpr hxs)
      show x.num * (nnSumList xs).den + (nnSumList xs).num * x.den = 0
      simp [hx0, hxs0]

theorem nnSumList_map_equiv_congr {α : Type} (xs : List α) (f g : α → NNRat)
    (h : ∀ x ∈ xs, f x ≈ g x) :
    nnSumList (xs.map f) ≈ nnSumList (xs.map g) := by
  induction xs with
  | nil => exact NNRat.equiv_refl _
  | cons x xs ih =>
    simp only [List.map_cons, nnSumList]
    exact nnrat_add_equiv_congr
      (h x (by simp))
      (ih (fun y hy => h y (by simp [hy])))

theorem sumSqDevNNRat_congr_mean (xs : List NNRat) {m₁ m₂ : NNRat} (hm : m₁ ≈ m₂) :
    sumSqDevNNRat xs m₁ ≈ sumSqDevNNRat xs m₂ :=
  nnSumList_map_equiv_congr xs _ _ (fun x _ =>
    sSqNNRat_equiv_congr (SignedRat.subNNRat_equiv_congr (NNRat.equiv_refl x) hm))

theorem sumSqDevSigned_congr_mean (xs : List SignedRat) {m₁ m₂ : SignedRat} (hm : m₁ ≈ₛ m₂) :
    sumSqDevSigned xs m₁ ≈ sumSqDevSigned xs m₂ :=
  nnSumList_map_equiv_congr xs _ _ (fun x _ =>
    sSqNNRat_equiv_congr (sSub_equiv_congr (SignedRat.equiv_refl x) hm))

theorem nnrat_div_equiv_congr {a₁ a₂ b₁ b₂ : NNRat}
    (ha : a₁ ≈ a₂) (hb : b₁ ≈ b₂) (hb₁ : 0 < b₁.num) (hb₂ : 0 < b₂.num) :
    NNRat.div a₁ b₁ hb₁ ≈ NNRat.div a₂ b₂ hb₂ := by
  unfold NNRat.div NNRat.equiv at *
  dsimp only
  calc
    (a₁.num * b₁.den) * (a₂.den * b₂.num)
        = (a₁.num * a₂.den) * (b₁.den * b₂.num) := nat_mul4_ac_bd _ _ _ _
    _ = (a₂.num * a₁.den) * (b₂.den * b₁.num) := by
          rw [ha, Nat.mul_comm b₁.den b₂.num, hb.symm, Nat.mul_comm b₁.num b₂.den]
    _ = (a₂.num * b₂.den) * (a₁.den * b₁.num) := nat_mul4_ac_bd _ _ _ _

theorem sampleVarNNRat_perm {xs ys : List NNRat} (hp : List.Perm xs ys)
    (hx : 2 ≤ xs.length) (hy : 2 ≤ ys.length) :
    sampleVarNNRat xs hx ≈ sampleVarNNRat ys hy := by
  unfold sampleVarNNRat
  have hmean : nnMeanList xs (by omega) ≈ nnMeanList ys (by omega) :=
    nnMeanList_perm hp (by omega) (by omega)
  have hsum1 : sumSqDevNNRat xs (nnMeanList xs (by omega)) ≈
               sumSqDevNNRat xs (nnMeanList ys (by omega)) :=
    sumSqDevNNRat_congr_mean xs hmean
  have hsum2 : sumSqDevNNRat xs (nnMeanList ys (by omega)) ≈
               sumSqDevNNRat ys (nnMeanList ys (by omega)) :=
    nnSumList_perm (hp.map _)
  have hsum : sumSqDevNNRat xs (nnMeanList xs (by omega)) ≈
              sumSqDevNNRat ys (nnMeanList ys (by omega)) :=
    NNRat.equiv_trans hsum1 hsum2
  have hlen : xs.length - 1 = ys.length - 1 := by rw [hp.length_eq]
  have hden : NNRat.ofNat (xs.length - 1) ≈ NNRat.ofNat (ys.length - 1) := by
    rw [hlen]; exact NNRat.equiv_refl _
  exact nnrat_div_equiv_congr hsum hden (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)

theorem sampleVarSigned_perm {xs ys : List SignedRat} (hp : List.Perm xs ys)
    (hx : 2 ≤ xs.length) (hy : 2 ≤ ys.length) :
    sampleVarSigned xs hx ≈ sampleVarSigned ys hy := by
  unfold sampleVarSigned
  have hmean : sMeanList xs (by omega) ≈ₛ sMeanList ys (by omega) :=
    sMeanList_perm hp (by omega) (by omega)
  have hsum1 : sumSqDevSigned xs (sMeanList xs (by omega)) ≈
               sumSqDevSigned xs (sMeanList ys (by omega)) :=
    sumSqDevSigned_congr_mean xs hmean
  have hsum2 : sumSqDevSigned xs (sMeanList ys (by omega)) ≈
               sumSqDevSigned ys (sMeanList ys (by omega)) :=
    nnSumList_perm (hp.map _)
  have hsum := NNRat.equiv_trans hsum1 hsum2
  have hlen : xs.length - 1 = ys.length - 1 := by rw [hp.length_eq]
  have hden : NNRat.ofNat (xs.length - 1) ≈ NNRat.ofNat (ys.length - 1) := by
    rw [hlen]; exact NNRat.equiv_refl _
  exact nnrat_div_equiv_congr hsum hden (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)

theorem sampleVarSigned_neg (xs : List SignedRat) (h : 2 ≤ xs.length)
    (h' : 2 ≤ (xs.map sNeg).length) :
    sampleVarSigned (xs.map sNeg) h' ≈ sampleVarSigned xs h := by
  unfold sampleVarSigned
  have hmean : sMeanList (xs.map sNeg) (by omega) ≈ₛ sNeg (sMeanList xs (by omega)) :=
    sMeanList_neg xs (by omega) (by omega)
  have hsum1 : sumSqDevSigned (xs.map sNeg) (sMeanList (xs.map sNeg) (by omega)) ≈
               sumSqDevSigned (xs.map sNeg) (sNeg (sMeanList xs (by omega))) :=
    sumSqDevSigned_congr_mean (xs.map sNeg) hmean
  have hsum2 : sumSqDevSigned (xs.map sNeg) (sNeg (sMeanList xs (by omega))) ≈
               sumSqDevSigned xs (sMeanList xs (by omega)) := by
    unfold sumSqDevSigned
    rw [List.map_map]
    apply nnSumList_map_equiv_congr xs
    intro x _
    simp only [Function.comp_apply]
    have h1 : sSub (sNeg x) (sNeg (sMeanList xs (by omega))) ≈ₛ
              sNeg (sSub x (sMeanList xs (by omega))) :=
      (sNeg_sSub_equiv x (sMeanList xs (by omega))).symm
    have h2 : sSqNNRat (sSub (sNeg x) (sNeg (sMeanList xs (by omega)))) ≈
              sSqNNRat (sNeg (sSub x (sMeanList xs (by omega)))) :=
      sSqNNRat_equiv_congr h1
    rw [sSqNNRat_neg] at h2
    exact h2
  have hsum := NNRat.equiv_trans hsum1 hsum2
  have hlen : (xs.map sNeg).length - 1 = xs.length - 1 := by simp
  have hden : NNRat.ofNat ((xs.map sNeg).length - 1) ≈ NNRat.ofNat (xs.length - 1) := by
    rw [hlen]; exact NNRat.equiv_refl _
  exact nnrat_div_equiv_congr hsum hden (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)

theorem sampleVarNNRat_eq_zero_iff (xs : List NNRat) (h : 2 ≤ xs.length) :
    sampleVarNNRat xs h ≈ NNRat.zero ↔ ∀ x ∈ xs, x ≈ nnMeanList xs (by omega) := by
  unfold sampleVarNNRat
  rw [NNRat.equiv_zero_iff]
  dsimp only [NNRat.div, NNRat.ofNat]
  rw [Nat.mul_one]
  have hsumZero : (sumSqDevNNRat xs (nnMeanList xs (by omega))).num = 0 ↔
                  sumSqDevNNRat xs (nnMeanList xs (by omega)) ≈ NNRat.zero :=
    (NNRat.equiv_zero_iff _).symm
  rw [hsumZero]
  unfold sumSqDevNNRat
  rw [nnSumList_equiv_zero_iff]
  constructor
  · intro hall x hx
    have hsq := hall (sSqNNRat (SignedRat.subNNRat x (nnMeanList xs (by omega))))
      (List.mem_map.mpr ⟨x, hx, rfl⟩)
    have hnum0 : (SignedRat.subNNRat x (nnMeanList xs (by omega))).num = 0 :=
      (sSqNNRat_equiv_zero_iff _).mp hsq
    unfold SignedRat.subNNRat at hnum0
    dsimp only at hnum0
    unfold NNRat.equiv
    omega
  · intro hall y hy
    rcases List.mem_map.mp hy with ⟨x, hx, rfl⟩
    rw [sSqNNRat_equiv_zero_iff]
    have hxeq := hall x hx
    unfold SignedRat.subNNRat
    dsimp only
    unfold NNRat.equiv at hxeq
    omega

/-- Exact rational pooled variance `((k - 1) * varB + (m - 1) * varC) / (k + m - 2)` for Welch `effect_size`. -/
def pooledVarNNRat (varB varC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) : NNRat :=
  have hdenPos : 0 < k + m - 2 := by omega
  let num := (NNRat.scaleNat (k - 1) varB).add (NNRat.scaleNat (m - 1) varC)
  NNRat.div num (NNRat.ofNat (k + m - 2)) hdenPos

theorem pooledVarNNRat_symm (varB varC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    pooledVarNNRat varB varC k m hk hm ≈ pooledVarNNRat varC varB m k hm hk := by
  unfold pooledVarNNRat
  have hnum := nnrat_add_comm_equiv (NNRat.scaleNat (k - 1) varB) (NNRat.scaleNat (m - 1) varC)
  have hden : NNRat.ofNat (k + m - 2) ≈ NNRat.ofNat (m + k - 2) := by
    have heq : k + m - 2 = m + k - 2 := by omega
    rw [heq]; exact NNRat.equiv_refl _
  exact nnrat_div_equiv_congr hnum hden (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)

theorem pooledVarNNRat_equiv_congr {varB₁ varB₂ varC₁ varC₂ : NNRat} {k m : Nat}
    (hb : varB₁ ≈ varB₂) (hc : varC₁ ≈ varC₂) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    pooledVarNNRat varB₁ varC₁ k m hk hm ≈ pooledVarNNRat varB₂ varC₂ k m hk hm := by
  unfold pooledVarNNRat
  have hs1 : NNRat.scaleNat (k - 1) varB₁ ≈ NNRat.scaleNat (k - 1) varB₂ := by
    apply NNRat.equiv_of_le_antisymm
    · exact NNRat.scaleNat_le_scaleNat (Nat.le_refl _) (NNRat.le_of_equiv hb)
    · exact NNRat.scaleNat_le_scaleNat (Nat.le_refl _) (NNRat.le_of_equiv hb.symm)
  have hs2 : NNRat.scaleNat (m - 1) varC₁ ≈ NNRat.scaleNat (m - 1) varC₂ := by
    apply NNRat.equiv_of_le_antisymm
    · exact NNRat.scaleNat_le_scaleNat (Nat.le_refl _) (NNRat.le_of_equiv hc)
    · exact NNRat.scaleNat_le_scaleNat (Nat.le_refl _) (NNRat.le_of_equiv hc.symm)
  exact nnrat_div_equiv_congr (nnrat_add_equiv_congr hs1 hs2) (NNRat.equiv_refl _)
    (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)

/--
Exact rational Welch–Satterthwaite degrees of freedom for `vB = varB / k`, `vC = varC / m`
with `k ≥ 2` and `m ≥ 2`. Uses exact common-denominator representation `A = vB.num * vC.den`,
`B = vC.num * vB.den` yielding `a * b * (A + B)² / (b * A² + a * B²)` when `A + B > 0`
(algebraically identical to `(vB + vC)² / (vB² / (k - 1) + vC² / (m - 1))`) and `k + m - 2`
when both `vB = 0` and `vC = 0` (mirroring `stats.py:333-339`).
-/
def welchSatterthwaiteDf (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) : NNRat :=
  let a := k - 1
  let b := m - 1
  let A := vB.num * vC.den
  let B := vC.num * vB.den
  if hzero : A + B = 0 then
    NNRat.ofNat (k + m - 2)
  else
    have haPos : 0 < a := by omega
    have hbPos : 0 < b := by omega
    have hdenPos : 0 < b * (A * A) + a * (B * B) := by
      by_cases hA : A = 0
      · have hBPos : 0 < B := by omega
        have hBB : 0 < B * B := Nat.mul_pos hBPos hBPos
        have := Nat.mul_pos haPos hBB
        omega
      · have hAPos : 0 < A := by omega
        have hAA : 0 < A * A := Nat.mul_pos hAPos hAPos
        have := Nat.mul_pos hbPos hAA
        omega
    ⟨a * b * ((A + B) * (A + B)), b * (A * A) + a * (B * B), hdenPos⟩

private theorem welch_cross_eq (a b A₁ B₁ A₂ B₂ D₁ D₂ : Nat)
    (hD1Pos : 0 < D₁) (hD2Pos : 0 < D₂)
    (hscaleA : A₁ * D₂ = A₂ * D₁) (hscaleB : B₁ * D₂ = B₂ * D₁) :
    (a * b * ((A₁ + B₁) * (A₁ + B₁))) * (b * (A₂ * A₂) + a * (B₂ * B₂)) =
    (a * b * ((A₂ + B₂) * (A₂ + B₂))) * (b * (A₁ * A₁) + a * (B₁ * B₁)) := by
  have hKPos : 0 < (D₁ * D₁) * (D₂ * D₂) :=
    Nat.mul_pos (Nat.mul_pos hD1Pos hD1Pos) (Nat.mul_pos hD2Pos hD2Pos)
  apply Nat.eq_of_mul_eq_mul_left hKPos
  have hS1 : (A₁ + B₁) * D₂ = (A₂ + B₂) * D₁ := by
    rw [Nat.add_mul, Nat.add_mul, hscaleA, hscaleB]
  have hSqSum : ((A₁ + B₁) * (A₁ + B₁)) * (D₂ * D₂) = ((A₂ + B₂) * (A₂ + B₂)) * (D₁ * D₁) := by
    rw [← nat_mul4_ac_bd (A₁ + B₁) D₂ (A₁ + B₁) D₂, hS1,
        nat_mul4_ac_bd (A₂ + B₂) D₁ (A₂ + B₂) D₁]
  have hSqA : (A₁ * A₁) * (D₂ * D₂) = (A₂ * A₂) * (D₁ * D₁) := by
    rw [← nat_mul4_ac_bd A₁ D₂ A₁ D₂, hscaleA, nat_mul4_ac_bd A₂ D₁ A₂ D₁]
  have hSqB : (B₁ * B₁) * (D₂ * D₂) = (B₂ * B₂) * (D₁ * D₁) := by
    rw [← nat_mul4_ac_bd B₁ D₂ B₁ D₂, hscaleB, nat_mul4_ac_bd B₂ D₁ B₂ D₁]
  have hDenEq : (b * (A₁ * A₁) + a * (B₁ * B₁)) * (D₂ * D₂) =
                (b * (A₂ * A₂) + a * (B₂ * B₂)) * (D₁ * D₁) := by
    rw [Nat.add_mul, Nat.add_mul,
        Nat.mul_assoc b (A₁ * A₁) (D₂ * D₂), Nat.mul_assoc a (B₁ * B₁) (D₂ * D₂),
        Nat.mul_assoc b (A₂ * A₂) (D₁ * D₁), Nat.mul_assoc a (B₂ * B₂) (D₁ * D₁),
        hSqA, hSqB]
  calc
    ((D₁ * D₁) * (D₂ * D₂)) * ((a * b * ((A₁ + B₁) * (A₁ + B₁))) * (b * (A₂ * A₂) + a * (B₂ * B₂)))
        = (a * b) * ((((A₁ + B₁) * (A₁ + B₁)) * (D₂ * D₂)) * ((b * (A₂ * A₂) + a * (B₂ * B₂)) * (D₁ * D₁))) := by
          have p1 :
            ((D₁ * D₁) * (D₂ * D₂)) * ((a * b * ((A₁ + B₁) * (A₁ + B₁))) * (b * (A₂ * A₂) + a * (B₂ * B₂))) =
            (a * b) * (((D₁ * D₁) * (D₂ * D₂)) * (((A₁ + B₁) * (A₁ + B₁)) * (b * (A₂ * A₂) + a * (B₂ * B₂)))) := by
            rw [Nat.mul_assoc (a * b), Nat.mul_left_comm]
          rw [p1]
          apply congrArg ((a * b) * ·)
          rw [Nat.mul_comm (D₁ * D₁) (D₂ * D₂), nat_mul4_ac_bd,
              Nat.mul_comm (D₂ * D₂), Nat.mul_comm (D₁ * D₁)]
    _ = (a * b) * ((((A₂ + B₂) * (A₂ + B₂)) * (D₁ * D₁)) * ((b * (A₁ * A₁) + a * (B₁ * B₁)) * (D₂ * D₂))) := by
          rw [hSqSum, ← hDenEq]
    _ = ((D₁ * D₁) * (D₂ * D₂)) * ((a * b * ((A₂ + B₂) * (A₂ + B₂))) * (b * (A₁ * A₁) + a * (B₁ * B₁))) := by
          have p2 :
            ((D₁ * D₁) * (D₂ * D₂)) * ((a * b * ((A₂ + B₂) * (A₂ + B₂))) * (b * (A₁ * A₁) + a * (B₁ * B₁))) =
            (a * b) * (((D₁ * D₁) * (D₂ * D₂)) * (((A₂ + B₂) * (A₂ + B₂)) * (b * (A₁ * A₁) + a * (B₁ * B₁)))) := by
            rw [Nat.mul_assoc (a * b), Nat.mul_left_comm]
          rw [p2]
          apply congrArg ((a * b) * ·)
          rw [nat_mul4_ac_bd, Nat.mul_comm (D₁ * D₁), Nat.mul_comm (D₂ * D₂), Nat.mul_comm]

private theorem welch_lower_nat (a b A B : Nat) :
    min a b * (b * (A * A) + a * (B * B)) ≤ a * b * ((A + B) * (A + B)) := by
  have hminA : min a b ≤ a := Nat.min_le_left a b
  have hminB : min a b ≤ b := Nat.min_le_right a b
  have h1 : min a b * (b * (A * A)) ≤ a * b * (A * A) := by
    rw [← Nat.mul_assoc]
    exact Nat.mul_le_mul_right (A * A) (Nat.mul_le_mul_right b hminA)
  have h2 : min a b * (a * (B * B)) ≤ a * b * (B * B) := by
    rw [← Nat.mul_assoc, Nat.mul_comm (min a b) a]
    exact Nat.mul_le_mul_right (B * B) (Nat.mul_le_mul_left a hminB)
  have h3 : min a b * (b * (A * A) + a * (B * B)) ≤ a * b * (A * A + B * B) := by
    rw [Nat.mul_add, Nat.mul_add]
    exact Nat.add_le_add h1 h2
  have h4 : A * A + B * B ≤ (A + B) * (A + B) := by
    rw [Nat.add_mul, Nat.mul_add, Nat.mul_add]
    omega
  exact Nat.le_trans h3 (Nat.mul_le_mul_left (a * b) h4)

private theorem welch_upper_nat (a b A B : Nat) :
    a * b * ((A + B) * (A + B)) ≤ (a + b) * (b * (A * A) + a * (B * B)) := by
  have hcs : 2 * (b * A) * (a * B) ≤ (b * A) * (b * A) + (a * B) * (a * B) :=
    nat_two_mul_le_sq_add_sq (b * A) (a * B)
  have hmid : a * b * (A * B + B * A) = 2 * (b * A) * (a * B) := by
    have hBA : B * A = A * B := Nat.mul_comm B A
    rw [hBA]
    have h2 : A * B + A * B = 2 * (A * B) := by omega
    rw [h2]
    calc
      a * b * (2 * (A * B)) = 2 * ((a * b) * (A * B)) := by rw [Nat.mul_left_comm]
      _ = 2 * ((b * a) * (A * B)) := by rw [Nat.mul_comm a b]
      _ = 2 * ((b * A) * (a * B)) := by rw [nat_mul4_ac_bd b a A B]
      _ = 2 * (b * A) * (a * B) := (Nat.mul_assoc _ _ _).symm
  have hsq1 : (b * A) * (b * A) = b * (b * (A * A)) := by
    rw [nat_mul4_ac_bd b A b A, Nat.mul_assoc]
  have hsq2 : (a * B) * (a * B) = a * (a * (B * B)) := by
    rw [nat_mul4_ac_bd a B a B, Nat.mul_assoc]
  have hL : a * b * ((A + B) * (A + B)) =
            a * (b * (A * A)) + a * b * (A * B + B * A) + b * (a * (B * B)) := by
    have hsq : (A + B) * (A + B) = A * A + (A * B + B * A) + B * B := by
      rw [Nat.add_mul, Nat.mul_add, Nat.mul_add]
      omega
    rw [hsq, Nat.mul_add, Nat.mul_add, Nat.mul_assoc a b (A * A),
        Nat.mul_assoc a b (B * B), Nat.mul_left_comm a b (B * B)]
  have hR : (a + b) * (b * (A * A) + a * (B * B)) =
            a * (b * (A * A)) + (a * (a * (B * B)) + b * (b * (A * A))) + b * (a * (B * B)) := by
    rw [Nat.add_mul, Nat.mul_add, Nat.mul_add]
    omega
  rw [hL, hR, hmid, ← hsq1, ← hsq2]
  omega

private theorem welch_scale_nat (a b A B F : Nat) :
    (a * b * ((F * (A + B)) * (F * (A + B)))) * (b * (A * A) + a * (B * B)) =
    (a * b * ((A + B) * (A + B))) * (b * ((F * A) * (F * A)) + a * ((F * B) * (F * B))) := by
  have h1 : (F * (A + B)) * (F * (A + B)) = (F * F) * ((A + B) * (A + B)) :=
    nat_mul4_ac_bd F (A + B) F (A + B)
  have h2 : (F * A) * (F * A) = (F * F) * (A * A) := nat_mul4_ac_bd F A F A
  have h3 : (F * B) * (F * B) = (F * F) * (B * B) := nat_mul4_ac_bd F B F B
  rw [h1, h2, h3]
  have hden : b * ((F * F) * (A * A)) + a * ((F * F) * (B * B)) =
              (F * F) * (b * (A * A) + a * (B * B)) := by
    rw [Nat.mul_left_comm b (F * F), Nat.mul_left_comm a (F * F), ← Nat.mul_add]
  rw [hden]
  calc
    (a * b * ((F * F) * ((A + B) * (A + B)))) * (b * (A * A) + a * (B * B))
        = (F * F) * ((a * b * ((A + B) * (A + B))) * (b * (A * A) + a * (B * B))) := by
          rw [Nat.mul_left_comm (a * b) (F * F), Nat.mul_assoc]
    _ = (a * b * ((A + B) * (A + B))) * ((F * F) * (b * (A * A) + a * (B * B))) := by
          rw [Nat.mul_left_comm]

theorem welchSatterthwaiteDf_equiv_congr {vB₁ vB₂ vC₁ vC₂ : NNRat} {k m : Nat}
    (hb : vB₁ ≈ vB₂) (hc : vC₁ ≈ vC₂) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf vB₁ vC₁ k m hk hm ≈ welchSatterthwaiteDf vB₂ vC₂ k m hk hm := by
  unfold welchSatterthwaiteDf
  dsimp only
  have hAb : vB₁.num * vB₂.den = vB₂.num * vB₁.den := hb
  have hAc : vC₁.num * vC₂.den = vC₂.num * vC₁.den := hc
  have hscaleA : (vB₁.num * vC₁.den) * (vB₂.den * vC₂.den) =
                 (vB₂.num * vC₂.den) * (vB₁.den * vC₁.den) := by
    calc
      (vB₁.num * vC₁.den) * (vB₂.den * vC₂.den)
          = (vB₁.num * vB₂.den) * (vC₁.den * vC₂.den) := nat_mul4_ac_bd _ _ _ _
      _ = (vB₂.num * vB₁.den) * (vC₁.den * vC₂.den) := by rw [hAb]
      _ = (vB₂.num * vC₂.den) * (vB₁.den * vC₁.den) := by
            rw [Nat.mul_comm vC₁.den vC₂.den, nat_mul4_ac_bd]
  have hscaleB : (vC₁.num * vB₁.den) * (vB₂.den * vC₂.den) =
                 (vC₂.num * vB₂.den) * (vB₁.den * vC₁.den) := by
    calc
      (vC₁.num * vB₁.den) * (vB₂.den * vC₂.den)
          = (vC₁.num * vC₂.den) * (vB₁.den * vB₂.den) := by
            rw [Nat.mul_comm vB₂.den vC₂.den, nat_mul4_ac_bd]
      _ = (vC₂.num * vC₁.den) * (vB₁.den * vB₂.den) := by rw [hAc]
      _ = (vC₂.num * vB₂.den) * (vB₁.den * vC₁.den) := by
            rw [Nat.mul_comm vB₁.den vB₂.den, nat_mul4_ac_bd, Nat.mul_comm vC₁.den vB₁.den]
  have hD1Pos : 0 < vB₁.den * vC₁.den := Nat.mul_pos vB₁.denPos vC₁.denPos
  have hD2Pos : 0 < vB₂.den * vC₂.den := Nat.mul_pos vB₂.denPos vC₂.denPos
  have hzeroIff : vB₁.num * vC₁.den + vC₁.num * vB₁.den = 0 ↔
                  vB₂.num * vC₂.den + vC₂.num * vB₂.den = 0 := by
    constructor
    · intro hz
      have hA1 : vB₁.num * vC₁.den = 0 := by omega
      have hB1 : vC₁.num * vB₁.den = 0 := by omega
      have hA2D : (vB₂.num * vC₂.den) * (vB₁.den * vC₁.den) = 0 := by
        rw [← hscaleA, hA1, Nat.zero_mul]
      have hB2D : (vC₂.num * vB₂.den) * (vB₁.den * vC₁.den) = 0 := by
        rw [← hscaleB, hB1, Nat.zero_mul]
      have hA2 : vB₂.num * vC₂.den = 0 := by
        cases Nat.mul_eq_zero.mp hA2D with | inl h => exact h | inr h => omega
      have hB2 : vC₂.num * vB₂.den = 0 := by
        cases Nat.mul_eq_zero.mp hB2D with | inl h => exact h | inr h => omega
      omega
    · intro hz
      have hA2 : vB₂.num * vC₂.den = 0 := by omega
      have hB2 : vC₂.num * vB₂.den = 0 := by omega
      have hA1D : (vB₁.num * vC₁.den) * (vB₂.den * vC₂.den) = 0 := by
        rw [hscaleA, hA2, Nat.zero_mul]
      have hB1D : (vC₁.num * vB₁.den) * (vB₂.den * vC₂.den) = 0 := by
        rw [hscaleB, hB2, Nat.zero_mul]
      have hA1 : vB₁.num * vC₁.den = 0 := by
        cases Nat.mul_eq_zero.mp hA1D with | inl h => exact h | inr h => omega
      have hB1 : vC₁.num * vB₁.den = 0 := by
        cases Nat.mul_eq_zero.mp hB1D with | inl h => exact h | inr h => omega
      omega
  by_cases hz1 : vB₁.num * vC₁.den + vC₁.num * vB₁.den = 0
  · have hz2 : vB₂.num * vC₂.den + vC₂.num * vB₂.den = 0 := hzeroIff.mp hz1
    simp only [hz1, hz2, ↓reduceDIte]
    exact NNRat.equiv_refl _
  · have hz2 : ¬ (vB₂.num * vC₂.den + vC₂.num * vB₂.den = 0) := fun hc' => hz1 (hzeroIff.mpr hc')
    simp only [hz1, hz2, ↓reduceDIte]
    exact welch_cross_eq (k - 1) (m - 1) _ _ _ _ _ _ hD1Pos hD2Pos hscaleA hscaleB

theorem welchSatterthwaiteDf_pos_core (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    NNRat.zero < welchSatterthwaiteDf vB vC k m hk hm := by
  unfold welchSatterthwaiteDf
  dsimp only
  split
  · rw [NNRat.zero_lt_iff]
    dsimp [NNRat.ofNat]
    omega
  · rename_i hne
    rw [NNRat.zero_lt_iff]
    dsimp only
    have ha : 0 < k - 1 := by omega
    have hb : 0 < m - 1 := by omega
    have hsum : 0 < vB.num * vC.den + vC.num * vB.den := by omega
    exact Nat.mul_pos (Nat.mul_pos ha hb) (Nat.mul_pos hsum hsum)

theorem welchSatterthwaiteDf_lower_bound_core (vB vC : NNRat) (k m : Nat)
    (hk : 2 ≤ k) (hm : 2 ≤ m) :
    NNRat.ofNat (min (k - 1) (m - 1)) ≤ welchSatterthwaiteDf vB vC k m hk hm := by
  unfold welchSatterthwaiteDf
  dsimp only
  split
  · show min (k - 1) (m - 1) * 1 ≤ (k + m - 2) * 1
    omega
  · show min (k - 1) (m - 1) * ((m - 1) * (vB.num * vC.den * (vB.num * vC.den)) +
      (k - 1) * (vC.num * vB.den * (vC.num * vB.den))) ≤
      (k - 1) * (m - 1) * ((vB.num * vC.den + vC.num * vB.den) * (vB.num * vC.den + vC.num * vB.den)) * 1
    rw [Nat.mul_one]
    exact welch_lower_nat (k - 1) (m - 1) (vB.num * vC.den) (vC.num * vB.den)

theorem welchSatterthwaiteDf_upper_bound_core (vB vC : NNRat) (k m : Nat)
    (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf vB vC k m hk hm ≤ NNRat.ofNat (k + m - 2) := by
  unfold welchSatterthwaiteDf
  dsimp only
  split
  · exact NNRat.le_refl _
  · show (k - 1) * (m - 1) * ((vB.num * vC.den + vC.num * vB.den) * (vB.num * vC.den + vC.num * vB.den)) * 1 ≤
         (k + m - 2) * ((m - 1) * (vB.num * vC.den * (vB.num * vC.den)) +
           (k - 1) * (vC.num * vB.den * (vC.num * vB.den)))
    rw [Nat.mul_one]
    have hsum_ab : k + m - 2 = (k - 1) + (m - 1) := by omega
    rw [hsum_ab]
    exact welch_upper_nat (k - 1) (m - 1) (vB.num * vC.den) (vC.num * vB.den)

theorem welchSatterthwaiteDf_scale_invariant_core (s vB vC : NNRat) (hs : 0 < s.num)
    (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf (s.mul vB) (s.mul vC) k m hk hm ≈
    welchSatterthwaiteDf vB vC k m hk hm := by
  unfold welchSatterthwaiteDf NNRat.mul
  dsimp only
  have hFPos : 0 < s.num * s.den := Nat.mul_pos hs s.denPos
  have hAs : (s.num * vB.num) * (s.den * vC.den) = (s.num * s.den) * (vB.num * vC.den) :=
    nat_mul4_ac_bd s.num vB.num s.den vC.den
  have hBs : (s.num * vC.num) * (s.den * vB.den) = (s.num * s.den) * (vC.num * vB.den) :=
    nat_mul4_ac_bd s.num vC.num s.den vB.den
  have hSumEq : (s.num * vB.num) * (s.den * vC.den) + (s.num * vC.num) * (s.den * vB.den) =
                (s.num * s.den) * (vB.num * vC.den + vC.num * vB.den) := by
    rw [hAs, hBs, ← Nat.mul_add]
  have hzeroIff : (s.num * vB.num) * (s.den * vC.den) + (s.num * vC.num) * (s.den * vB.den) = 0 ↔
                  vB.num * vC.den + vC.num * vB.den = 0 := by
    rw [hSumEq]
    constructor
    · intro h
      cases Nat.mul_eq_zero.mp h with | inl hF => omega | inr hAB => exact hAB
    · intro h; simp [h]
  by_cases hz : vB.num * vC.den + vC.num * vB.den = 0
  · have hzs : (s.num * vB.num) * (s.den * vC.den) + (s.num * vC.num) * (s.den * vB.den) = 0 :=
      hzeroIff.mpr hz
    simp only [hz, hzs, ↓reduceDIte]
    exact NNRat.equiv_refl _
  · have hzs : ¬ ((s.num * vB.num) * (s.den * vC.den) + (s.num * vC.num) * (s.den * vB.den) = 0) :=
      fun hc => hz (hzeroIff.mp hc)
    simp only [hz, hzs, ↓reduceDIte]
    unfold NNRat.equiv
    dsimp only
    rw [hAs, hBs, ← Nat.mul_add]
    exact welch_scale_nat (k - 1) (m - 1) (vB.num * vC.den) (vC.num * vB.den) (s.num * s.den)

theorem welchSatterthwaiteDf_symm_core (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf vB vC k m hk hm ≈ welchSatterthwaiteDf vC vB m k hm hk := by
  unfold welchSatterthwaiteDf
  dsimp only
  have hcomm : vB.num * vC.den + vC.num * vB.den = vC.num * vB.den + vB.num * vC.den :=
    Nat.add_comm _ _
  by_cases hz : vB.num * vC.den + vC.num * vB.den = 0
  · have hz' : vC.num * vB.den + vB.num * vC.den = 0 := by omega
    simp only [hz, hz', ↓reduceDIte]
    have hkm : k + m - 2 = m + k - 2 := by omega
    rw [hkm]
    exact NNRat.equiv_refl _
  · have hz' : ¬ (vC.num * vB.den + vB.num * vC.den = 0) := by omega
    simp only [hz, hz', ↓reduceDIte]
    unfold NNRat.equiv
    dsimp only
    rw [Nat.mul_comm (k - 1) (m - 1), hcomm,
        Nat.add_comm ((m - 1) * (vB.num * vC.den * (vB.num * vC.den)))
                     ((k - 1) * (vC.num * vB.den * (vC.num * vB.den)))]

end EvalForgeFormal.Stats
