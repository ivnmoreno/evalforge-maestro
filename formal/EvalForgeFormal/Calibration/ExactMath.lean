import EvalForgeFormal.Retrieval.ExactRat

namespace EvalForgeFormal.Calibration

open EvalForgeFormal.Retrieval

/-- Absolute difference between two natural numbers. -/
def natAbsDiff (a b : Nat) : Nat :=
  if a ≤ b then b - a else a - b

theorem natAbsDiff_symm (a b : Nat) : natAbsDiff a b = natAbsDiff b a := by
  unfold natAbsDiff
  split <;> split <;> omega

theorem natAbsDiff_self (a : Nat) : natAbsDiff a a = 0 := by
  unfold natAbsDiff
  simp

private theorem nat_mul4_ac_bd (a b c d : Nat) : (a * b) * (c * d) = (a * c) * (b * d) := by
  calc
    (a * b) * (c * d) = a * (b * (c * d)) := Nat.mul_assoc _ _ _
    _ = a * (c * (b * d)) := by rw [Nat.mul_left_comm b c d]
    _ = (a * c) * (b * d) := (Nat.mul_assoc _ _ _).symm

private theorem nat_mul4_ad_bc (a b c d : Nat) : (a * b) * (c * d) = (a * d) * (b * c) := by
  rw [Nat.mul_comm c d]
  exact nat_mul4_ac_bd a b d c

/-- Exact rational absolute difference `|a - b|` in `NNRat`. -/
def nnAbsDiff (a b : NNRat) : NNRat :=
  if a.num * b.den ≤ b.num * a.den then
    ⟨b.num * a.den - a.num * b.den, a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩
  else
    ⟨a.num * b.den - b.num * a.den, a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩

/-- Exact rational midpoint `(a + b) / 2` in `NNRat`. -/
def nnMidpoint (a b : NNRat) : NNRat :=
  ⟨a.num * b.den + b.num * a.den, 2 * (a.den * b.den),
    Nat.mul_pos (by omega) (Nat.mul_pos a.denPos b.denPos)⟩

/-- Exact rational sum of a list of non-negative rationals. -/
def nnSumList : List NNRat → NNRat
  | [] => NNRat.zero
  | x :: xs => x.add (nnSumList xs)

/-- Exact rational arithmetic mean of a non-empty list of non-negative rationals. -/
def nnMeanList (xs : List NNRat) (h : 0 < xs.length) : NNRat :=
  NNRat.div (nnSumList xs) (NNRat.ofNat xs.length) h

theorem nnrat_add_comm_equiv (a b : NNRat) : a.add b ≈ b.add a := by
  show (a.num * b.den + b.num * a.den) * (b.den * a.den) =
       (b.num * a.den + a.num * b.den) * (a.den * b.den)
  rw [Nat.add_comm (a.num * b.den) (b.num * a.den), Nat.mul_comm b.den a.den]

theorem nnrat_add_equiv_congr {a₁ a₂ b₁ b₂ : NNRat} (ha : a₁ ≈ a₂) (hb : b₁ ≈ b₂) :
    a₁.add b₁ ≈ a₂.add b₂ := by
  apply NNRat.equiv_of_le_antisymm
  · exact NNRat.add_le_add (NNRat.le_of_equiv ha) (NNRat.le_of_equiv hb)
  · exact NNRat.add_le_add (NNRat.le_of_equiv ha.symm) (NNRat.le_of_equiv hb.symm)

theorem nnrat_le_of_equiv_left {a₁ a₂ b : NNRat} (ha : a₁ ≈ a₂) (h : a₁ ≤ b) : a₂ ≤ b :=
  NNRat.le_trans (NNRat.le_of_equiv ha.symm) h

theorem nnrat_le_of_equiv_right {a b₁ b₂ : NNRat} (hb : b₁ ≈ b₂) (h : a ≤ b₁) : a ≤ b₂ :=
  NNRat.le_trans h (NNRat.le_of_equiv hb)

theorem nnrat_lt_of_equiv_left {a₁ a₂ b : NNRat} (ha : a₁ ≈ a₂) (h : a₁ < b) : a₂ < b := by
  rw [NNRat.lt_iff_not_le] at h ⊢
  intro hle
  exact h (NNRat.le_trans hle (NNRat.le_of_equiv ha.symm))

theorem nnrat_lt_of_equiv_right {a b₁ b₂ : NNRat} (hb : b₁ ≈ b₂) (h : a < b₁) : a < b₂ := by
  rw [NNRat.lt_iff_not_le] at h ⊢
  intro hle
  exact h (NNRat.le_trans (NNRat.le_of_equiv hb) hle)

theorem nnrat_normalize_eq_of_equiv {a b : NNRat} (h : a ≈ b) :
    NNRat.normalize a = NNRat.normalize b := by
  have heq : NNRat.normalize a ≈ NNRat.normalize b :=
    NNRat.equiv_trans (NNRat.normalize_equiv a) (NNRat.equiv_trans h (NNRat.normalize_equiv b).symm)
  by_cases ha0 : a.num = 0
  · have hb0 : b.num = 0 := by
      have hmul : 0 = b.num * a.den := by simpa [NNRat.equiv, ha0] using h
      cases Nat.mul_eq_zero.mp hmul.symm with
      | inl hbn => exact hbn
      | inr had => have := a.denPos; omega
    simp [NNRat.normalize, ha0, hb0]
  · have hb0 : b.num ≠ 0 := by
      intro hbn
      have hmul : a.num * b.den = 0 := by simpa [NNRat.equiv, hbn] using h
      cases Nat.mul_eq_zero.mp hmul with
      | inl han => exact ha0 han
      | inr hbd => have := b.denPos; omega
    let ga := Nat.gcd a.num a.den
    let gb := Nat.gcd b.num b.den
    have hgaPos : 0 < ga := Nat.gcd_pos_of_pos_right a.num a.denPos
    have hgbPos : 0 < gb := Nat.gcd_pos_of_pos_right b.num b.denPos
    have hca : Nat.Coprime (a.num / ga) (a.den / ga) := Nat.coprime_div_gcd_div_gcd hgaPos
    have hcb : Nat.Coprime (b.num / gb) (b.den / gb) := Nat.coprime_div_gcd_div_gcd hgbPos
    have hna : (NNRat.normalize a).num = a.num / ga := by simp [NNRat.normalize, ha0, ga]
    have hda : (NNRat.normalize a).den = a.den / ga := by simp [NNRat.normalize, ha0, ga]
    have hnb : (NNRat.normalize b).num = b.num / gb := by simp [NNRat.normalize, hb0, gb]
    have hdb : (NNRat.normalize b).den = b.den / gb := by simp [NNRat.normalize, hb0, gb]
    have hcross : (a.num / ga) * (b.den / gb) = (b.num / gb) * (a.den / ga) := by
      simpa [NNRat.equiv, hna, hda, hnb, hdb] using heq
    have hdvd1 : (a.num / ga) ∣ (b.num / gb) := by
      have hd : (a.num / ga) ∣ (b.num / gb) * (a.den / ga) := ⟨b.den / gb, hcross.symm⟩
      exact hca.dvd_of_dvd_mul_right hd
    have hdvd2 : (b.num / gb) ∣ (a.num / ga) := by
      have hd : (b.num / gb) ∣ (a.num / ga) * (b.den / gb) := ⟨a.den / ga, hcross⟩
      exact hcb.dvd_of_dvd_mul_right hd
    have hnumEq : a.num / ga = b.num / gb := Nat.dvd_antisymm hdvd1 hdvd2
    have hanPos : 0 < a.num / ga := by
      have hmul : ga * (a.num / ga) = a.num := Nat.mul_div_cancel' (Nat.gcd_dvd_left a.num a.den)
      cases hq : a.num / ga with
      | zero =>
        rw [hq, Nat.mul_zero] at hmul
        exact absurd hmul.symm ha0
      | succ k => exact Nat.succ_pos k
    have hdenEq : a.den / ga = b.den / gb := by
      rw [hnumEq] at hcross
      have hbnPos : 0 < b.num / gb := hnumEq ▸ hanPos
      exact (Nat.eq_of_mul_eq_mul_left hbnPos hcross).symm
    cases hA : NNRat.normalize a with
    | mk an ad had =>
      cases hB : NNRat.normalize b with
      | mk bn bd hbd =>
        have h1 : an = bn := by
          have : an = a.num / ga := by simpa [hA] using hna
          have : bn = b.num / gb := by simpa [hB] using hnb
          omega
        have h2 : ad = bd := by
          have : ad = a.den / ga := by simpa [hA] using hda
          have : bd = b.den / gb := by simpa [hB] using hdb
          omega
        subst h1
        subst h2
        rfl

theorem nnrat_normalize_idempotent (a : NNRat) :
    NNRat.normalize (NNRat.normalize a) = NNRat.normalize a :=
  nnrat_normalize_eq_of_equiv (NNRat.normalize_equiv a)

theorem nnAbsDiff_symm (a b : NNRat) : nnAbsDiff a b ≈ nnAbsDiff b a := by
  unfold nnAbsDiff NNRat.equiv
  by_cases h1 : a.num * b.den ≤ b.num * a.den
  · by_cases h2 : b.num * a.den ≤ a.num * b.den
    · have heq : a.num * b.den = b.num * a.den := Nat.le_antisymm h1 h2
      simp [heq]
    · simp only [h1, h2, ↓reduceIte]
      rw [Nat.mul_comm b.den a.den]
  · have h2 : b.num * a.den ≤ a.num * b.den := by omega
    simp only [h1, h2, ↓reduceIte]
    rw [Nat.mul_comm b.den a.den]

theorem nnAbsDiff_self_equiv_zero (a : NNRat) : nnAbsDiff a a ≈ NNRat.zero := by
  unfold nnAbsDiff
  rw [NNRat.equiv_zero_iff]
  simp

theorem nnAbsDiff_equiv_zero_iff (a b : NNRat) : nnAbsDiff a b ≈ NNRat.zero ↔ a ≈ b := by
  unfold nnAbsDiff
  rw [NNRat.equiv_zero_iff]
  by_cases h : a.num * b.den ≤ b.num * a.den
  · simp only [h, ↓reduceIte, NNRat.equiv]
    omega
  · simp only [h, ↓reduceIte, NNRat.equiv]
    omega

theorem nnAbsDiff_le_one_of_unit {a b : NNRat} (ha : a ≤ NNRat.one) (hb : b ≤ NNRat.one) :
    nnAbsDiff a b ≤ NNRat.one := by
  rw [NNRat.le_one_iff] at ha hb ⊢
  unfold nnAbsDiff
  have h1 : a.num * b.den ≤ a.den * b.den := Nat.mul_le_mul_right b.den ha
  have h2 : b.num * a.den ≤ a.den * b.den := by
    rw [Nat.mul_comm a.den b.den]
    exact Nat.mul_le_mul_right a.den hb
  by_cases h : a.num * b.den ≤ b.num * a.den
  · simp only [h, ↓reduceIte]
    omega
  · simp only [h, ↓reduceIte]
    omega

private theorem cross_a_eq {a₁ a₂ b₁ b₂ : NNRat} (ha : a₁ ≈ a₂) :
    (a₁.num * b₁.den) * (a₂.den * b₂.den) = (a₂.num * b₂.den) * (a₁.den * b₁.den) := by
  have ha' : a₁.num * a₂.den = a₂.num * a₁.den := ha
  calc
    (a₁.num * b₁.den) * (a₂.den * b₂.den)
        = (a₁.num * a₂.den) * (b₁.den * b₂.den) := nat_mul4_ac_bd _ _ _ _
    _ = (a₂.num * a₁.den) * (b₁.den * b₂.den) := by rw [ha']
    _ = (a₂.num * b₂.den) * (a₁.den * b₁.den) := by
          rw [nat_mul4_ad_bc, Nat.mul_comm a₁.den b₁.den]

private theorem cross_b_eq {a₁ a₂ b₁ b₂ : NNRat} (hb : b₁ ≈ b₂) :
    (b₁.num * a₁.den) * (a₂.den * b₂.den) = (b₂.num * a₂.den) * (a₁.den * b₁.den) := by
  have hb' : b₁.num * b₂.den = b₂.num * b₁.den := hb
  calc
    (b₁.num * a₁.den) * (a₂.den * b₂.den)
        = (b₁.num * b₂.den) * (a₁.den * a₂.den) := nat_mul4_ad_bc _ _ _ _
    _ = (b₂.num * b₁.den) * (a₁.den * a₂.den) := by rw [hb']
    _ = (b₂.num * a₂.den) * (a₁.den * b₁.den) := by
          rw [nat_mul4_ad_bc, Nat.mul_comm b₁.den a₁.den]

theorem nnAbsDiff_equiv_congr {a₁ a₂ b₁ b₂ : NNRat} (ha : a₁ ≈ a₂) (hb : b₁ ≈ b₂) :
    nnAbsDiff a₁ b₁ ≈ nnAbsDiff a₂ b₂ := by
  have hiff : a₁ ≤ b₁ ↔ a₂ ≤ b₂ := by
    constructor
    · intro h; exact nnrat_le_of_equiv_right hb (nnrat_le_of_equiv_left ha h)
    · intro h; exact nnrat_le_of_equiv_right hb.symm (nnrat_le_of_equiv_left ha.symm h)
  have hmul_sub : ∀ (x y z w m n : Nat), x * n = z * m → y * n = w * m →
      (x - y) * n = (z - w) * m := by
    intro x y z w m n hxz hyw
    rw [Nat.sub_mul, Nat.sub_mul, hxz, hyw]
  unfold nnAbsDiff NNRat.equiv
  by_cases h1 : a₁.num * b₁.den ≤ b₁.num * a₁.den
  · have h2 : a₂.num * b₂.den ≤ b₂.num * a₂.den := hiff.mp h1
    simp only [h1, h2, ↓reduceIte]
    exact hmul_sub _ _ _ _ _ _ (cross_b_eq hb) (cross_a_eq ha)
  · have h2 : ¬ (a₂.num * b₂.den ≤ b₂.num * a₂.den) := fun hc => h1 (hiff.mpr hc)
    simp only [h1, h2, ↓reduceIte]
    exact hmul_sub _ _ _ _ _ _ (cross_a_eq ha) (cross_b_eq hb)

theorem nnMidpoint_unit {a b : NNRat} (ha : a ≤ NNRat.one) (hb : b ≤ NNRat.one) :
    nnMidpoint a b ≤ NNRat.one := by
  rw [NNRat.le_one_iff] at ha hb ⊢
  show a.num * b.den + b.num * a.den ≤ 2 * (a.den * b.den)
  have h1 : a.num * b.den ≤ a.den * b.den := Nat.mul_le_mul_right b.den ha
  have h2 : b.num * a.den ≤ a.den * b.den := by
    rw [Nat.mul_comm a.den b.den]
    exact Nat.mul_le_mul_right a.den hb
  omega

theorem nnMidpoint_equiv_of_equidistant {a b t : NNRat}
    (hab : a < b) (hdist : nnAbsDiff a t ≈ nnAbsDiff b t) :
    nnMidpoint a b ≈ t := by
  have hlt : a.num * b.den < b.num * a.den := hab
  by_cases hat : a.num * t.den ≤ t.num * a.den
  · by_cases hbt : b.num * t.den ≤ t.num * b.den
    · have hEq : (t.num * a.den - a.num * t.den) * (b.den * t.den) =
                 (t.num * b.den - b.num * t.den) * (a.den * t.den) := by
        simpa [nnAbsDiff, NNRat.equiv, hat, hbt] using hdist
      have h1 : (t.num * a.den - a.num * t.den) * b.den =
                (t.num * b.den - b.num * t.den) * a.den := by
        have hL : (t.num * a.den - a.num * t.den) * (b.den * t.den) =
                  t.den * ((t.num * a.den - a.num * t.den) * b.den) := by
          rw [Nat.mul_comm b.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        have hR : (t.num * b.den - b.num * t.den) * (a.den * t.den) =
                  t.den * ((t.num * b.den - b.num * t.den) * a.den) := by
          rw [Nat.mul_comm a.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        rw [hL, hR] at hEq
        exact Nat.eq_of_mul_eq_mul_left t.denPos hEq
      rw [Nat.sub_mul, Nat.sub_mul] at h1
      have hT : (t.num * a.den) * b.den = (t.num * b.den) * a.den := by
        rw [Nat.mul_assoc, Nat.mul_comm a.den b.den, ← Nat.mul_assoc]
      have hA : (a.num * t.den) * b.den = t.den * (a.num * b.den) := by
        rw [Nat.mul_comm a.num t.den, Nat.mul_assoc]
      have hB : (b.num * t.den) * a.den = t.den * (b.num * a.den) := by
        rw [Nat.mul_comm b.num t.den, Nat.mul_assoc]
      have hleA : (a.num * t.den) * b.den ≤ (t.num * a.den) * b.den :=
        Nat.mul_le_mul_right b.den hat
      have hleB : (b.num * t.den) * a.den ≤ (t.num * b.den) * a.den :=
        Nat.mul_le_mul_right a.den hbt
      rw [hT] at h1 hleA
      have hEqAB : (a.num * t.den) * b.den = (b.num * t.den) * a.den := by omega
      rw [hA, hB] at hEqAB
      have hFinal := Nat.eq_of_mul_eq_mul_left t.denPos hEqAB
      omega
    · have htb : t.num * b.den ≤ b.num * t.den := by omega
      have hEq : (t.num * a.den - a.num * t.den) * (b.den * t.den) =
                 (b.num * t.den - t.num * b.den) * (a.den * t.den) := by
        simpa [nnAbsDiff, NNRat.equiv, hat, hbt] using hdist
      have h1 : (t.num * a.den - a.num * t.den) * b.den =
                (b.num * t.den - t.num * b.den) * a.den := by
        have hL : (t.num * a.den - a.num * t.den) * (b.den * t.den) =
                  t.den * ((t.num * a.den - a.num * t.den) * b.den) := by
          rw [Nat.mul_comm b.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        have hR : (b.num * t.den - t.num * b.den) * (a.den * t.den) =
                  t.den * ((b.num * t.den - t.num * b.den) * a.den) := by
          rw [Nat.mul_comm a.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        rw [hL, hR] at hEq
        exact Nat.eq_of_mul_eq_mul_left t.denPos hEq
      rw [Nat.sub_mul, Nat.sub_mul] at h1
      have hleA : (a.num * t.den) * b.den ≤ (t.num * a.den) * b.den :=
        Nat.mul_le_mul_right b.den hat
      have hleB : (t.num * b.den) * a.den ≤ (b.num * t.den) * a.den :=
        Nat.mul_le_mul_right a.den htb
      have hT1 : (t.num * a.den) * b.den = t.num * (a.den * b.den) := Nat.mul_assoc _ _ _
      have hT2 : (t.num * b.den) * a.den = t.num * (a.den * b.den) := by
        rw [Nat.mul_assoc, Nat.mul_comm b.den a.den]
      have hA : (a.num * t.den) * b.den = (a.num * b.den) * t.den := Nat.mul_right_comm _ _ _
      have hB : (b.num * t.den) * a.den = (b.num * a.den) * t.den := Nat.mul_right_comm _ _ _
      rw [hT1, hA] at hleA
      rw [hT2, hB] at hleB
      rw [hT1, hT2, hA, hB] at h1
      show (a.num * b.den + b.num * a.den) * t.den = t.num * (2 * (a.den * b.den))
      rw [Nat.add_mul, Nat.mul_left_comm t.num 2 (a.den * b.den)]
      omega
  · by_cases hbt : b.num * t.den ≤ t.num * b.den
    · have hta : t < a := (NNRat.lt_iff_not_le t a).mpr hat
      have hba : b < a := by
        have hle : b ≤ t := hbt
        rw [NNRat.lt_iff_not_le] at hta ⊢
        intro hab'
        exact hta (NNRat.le_trans hab' hle)
      have := (NNRat.lt_iff_not_le b a).mp hba
      exact absurd (NNRat.le_of_lt hab) this
    · have hEq : (a.num * t.den - t.num * a.den) * (b.den * t.den) =
                 (b.num * t.den - t.num * b.den) * (a.den * t.den) := by
        simpa [nnAbsDiff, NNRat.equiv, hat, hbt] using hdist
      have h1 : (a.num * t.den - t.num * a.den) * b.den =
                (b.num * t.den - t.num * b.den) * a.den := by
        have hL : (a.num * t.den - t.num * a.den) * (b.den * t.den) =
                  t.den * ((a.num * t.den - t.num * a.den) * b.den) := by
          rw [Nat.mul_comm b.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        have hR : (b.num * t.den - t.num * b.den) * (a.den * t.den) =
                  t.den * ((b.num * t.den - t.num * b.den) * a.den) := by
          rw [Nat.mul_comm a.den t.den, ← Nat.mul_assoc, Nat.mul_comm _ t.den, Nat.mul_assoc]
        rw [hL, hR] at hEq
        exact Nat.eq_of_mul_eq_mul_left t.denPos hEq
      rw [Nat.sub_mul, Nat.sub_mul] at h1
      have hta' : t.num * a.den ≤ a.num * t.den := by omega
      have htb' : t.num * b.den ≤ b.num * t.den := by omega
      have hleA : (t.num * a.den) * b.den ≤ (a.num * t.den) * b.den :=
        Nat.mul_le_mul_right b.den hta'
      have hleB : (t.num * b.den) * a.den ≤ (b.num * t.den) * a.den :=
        Nat.mul_le_mul_right a.den htb'
      have hT : (t.num * a.den) * b.den = (t.num * b.den) * a.den := by
        rw [Nat.mul_assoc, Nat.mul_comm a.den b.den, ← Nat.mul_assoc]
      have hA : (a.num * t.den) * b.den = t.den * (a.num * b.den) := by
        rw [Nat.mul_comm a.num t.den, Nat.mul_assoc]
      have hB : (b.num * t.den) * a.den = t.den * (b.num * a.den) := by
        rw [Nat.mul_comm b.num t.den, Nat.mul_assoc]
      rw [hT] at h1 hleA
      have hEqAB : (a.num * t.den) * b.den = (b.num * t.den) * a.den := by omega
      rw [hA, hB] at hEqAB
      have hFinal := Nat.eq_of_mul_eq_mul_left t.denPos hEqAB
      omega

theorem nnSumList_perm {xs ys : List NNRat} (h : List.Perm xs ys) :
    nnSumList xs ≈ nnSumList ys := by
  induction h with
  | nil => exact NNRat.equiv_refl _
  | cons x _ ih => exact nnrat_add_equiv_congr (NNRat.equiv_refl x) ih
  | swap x y l =>
    let s := nnSumList l
    have h1 : y.add (x.add s) ≈ (y.add x).add s := (NNRat.add_assoc_equiv y x s).symm
    have h2 : (y.add x).add s ≈ (x.add y).add s :=
      nnrat_add_equiv_congr (nnrat_add_comm_equiv y x) (NNRat.equiv_refl s)
    have h3 : (x.add y).add s ≈ x.add (y.add s) := NNRat.add_assoc_equiv x y s
    exact NNRat.equiv_trans h1 (NNRat.equiv_trans h2 h3)
  | trans _ _ ih1 ih2 => exact NNRat.equiv_trans ih1 ih2

theorem nnSumList_le_ofNat_length (xs : List NNRat) (hunit : ∀ x ∈ xs, x ≤ NNRat.one) :
    nnSumList xs ≤ NNRat.ofNat xs.length := by
  induction xs with
  | nil => exact NNRat.le_refl _
  | cons x xs ih =>
    have hx : x ≤ NNRat.one := hunit x (by simp)
    have hxs : nnSumList xs ≤ NNRat.ofNat xs.length :=
      ih (fun y hy => hunit y (by simp [hy]))
    have hadd : x.add (nnSumList xs) ≤ NNRat.one.add (NNRat.ofNat xs.length) :=
      NNRat.add_le_add hx hxs
    have hEq : NNRat.one.add (NNRat.ofNat xs.length) ≈ NNRat.ofNat (xs.length + 1) := by
      show (1 * 1 + xs.length * 1) * 1 = (xs.length + 1) * (1 * 1)
      omega
    exact nnrat_le_of_equiv_right hEq hadd

theorem nnMeanList_le_one (xs : List NNRat) (hpos : 0 < xs.length)
    (hunit : ∀ x ∈ xs, x ≤ NNRat.one) :
    nnMeanList xs hpos ≤ NNRat.one :=
  NNRat.div_le_one_of_le (nnSumList_le_ofNat_length xs hunit) hpos

theorem nnMeanList_perm {xs ys : List NNRat} (hp : List.Perm xs ys)
    (hx : 0 < xs.length) (hy : 0 < ys.length) :
    nnMeanList xs hx ≈ nnMeanList ys hy := by
  have hsum : nnSumList xs ≈ nnSumList ys := nnSumList_perm hp
  have hlen : xs.length = ys.length := hp.length_eq
  show ((nnSumList xs).num * 1) * ((nnSumList ys).den * ys.length) =
       ((nnSumList ys).num * 1) * ((nnSumList xs).den * xs.length)
  rw [hlen, Nat.mul_one, Nat.mul_one]
  calc
    (nnSumList xs).num * ((nnSumList ys).den * ys.length)
        = ((nnSumList xs).num * (nnSumList ys).den) * ys.length := (Nat.mul_assoc _ _ _).symm
    _ = ((nnSumList ys).num * (nnSumList xs).den) * ys.length := by rw [hsum]
    _ = (nnSumList ys).num * ((nnSumList xs).den * ys.length) := Nat.mul_assoc _ _ _

/--
Exact signed rational (`num / den` with `num : Int` and `0 < den`) for `score_delta` and
`mean_score_delta ∈ [-1, 1]`. Pure Lean 4 core (`Init`), zero external packages.
-/
structure SignedRat where
  num : Int
  den : Nat
  denPos : 0 < den
  deriving DecidableEq, Repr

namespace SignedRat

/-- Exact signed rational zero (`0 / 1`). -/
def zero : SignedRat := ⟨0, 1, Nat.zero_lt_one⟩

/-- Exact signed rational equivalence via integer cross-multiplication. -/
def equiv (a b : SignedRat) : Prop :=
  a.num * (b.den : Int) = b.num * (a.den : Int)

infix:50 " ≈ₛ " => SignedRat.equiv

/-- Predicate asserting a signed rational lies within `[-1, 1]`. -/
def inUnitInterval (s : SignedRat) : Prop :=
  -((s.den : Int)) ≤ s.num ∧ s.num ≤ (s.den : Int)

/-- Exact signed difference `a - b` of two non-negative rationals. -/
def subNNRat (a b : NNRat) : SignedRat :=
  ⟨((a.num * b.den : Nat) : Int) - ((b.num * a.den : Nat) : Int),
   a.den * b.den,
   Nat.mul_pos a.denPos b.denPos⟩

/-- Canonical reduced form via `Nat.gcd` (`0 / d` reduces to `0 / 1`) for JSON serialization. -/
def normalize (s : SignedRat) : SignedRat :=
  if s.num = 0 then
    zero
  else
    let g := Nat.gcd s.num.natAbs s.den
    have hdvd : g ∣ s.den := Nat.gcd_dvd_right s.num.natAbs s.den
    have hdenDivPos : 0 < s.den / g := by
      cases hq : s.den / g with
      | zero =>
        have hmul : g * (s.den / g) = s.den := Nat.mul_div_cancel' hdvd
        rw [hq, Nat.mul_zero] at hmul
        have := s.denPos
        omega
      | succ k => exact Nat.succ_pos k
    let qNat := s.num.natAbs / g
    let qInt : Int := if 0 ≤ s.num then (qNat : Int) else -((qNat : Int))
    ⟨qInt, s.den / g, hdenDivPos⟩

theorem equiv_refl (a : SignedRat) : a ≈ₛ a := rfl

theorem equiv_symm {a b : SignedRat} (h : a ≈ₛ b) : b ≈ₛ a := h.symm

theorem equiv_trans {a b c : SignedRat} (hab : a ≈ₛ b) (hbc : b ≈ₛ c) : a ≈ₛ c := by
  unfold equiv at *
  have hdenNe : (b.den : Int) ≠ 0 := by
    have := b.denPos
    omega
  have h : (b.den : Int) * (a.num * (c.den : Int)) =
           (b.den : Int) * (c.num * (a.den : Int)) := by
    calc
      (b.den : Int) * (a.num * (c.den : Int))
          = (a.num * (b.den : Int)) * (c.den : Int) := by
            rw [Int.mul_left_comm, ← Int.mul_assoc]
      _ = (b.num * (a.den : Int)) * (c.den : Int) := by rw [hab]
      _ = (b.num * (c.den : Int)) * (a.den : Int) := by
            rw [Int.mul_assoc, Int.mul_comm (a.den : Int) (c.den : Int), ← Int.mul_assoc]
      _ = (c.num * (b.den : Int)) * (a.den : Int) := by rw [hbc]
      _ = (b.den : Int) * (c.num * (a.den : Int)) := by
            rw [Int.mul_comm c.num (b.den : Int), Int.mul_assoc]
  exact Int.eq_of_mul_eq_mul_left hdenNe h

theorem normalize_equiv (s : SignedRat) : normalize s ≈ₛ s := by
  unfold normalize equiv
  by_cases h0 : s.num = 0
  · simp [h0, zero]
  · simp only [h0, ↓reduceIte]
    let g := Nat.gcd s.num.natAbs s.den
    have hgPos : 0 < g := Nat.gcd_pos_of_pos_right s.num.natAbs s.denPos
    have hnumNat : g * (s.num.natAbs / g) = s.num.natAbs :=
      Nat.mul_div_cancel' (Nat.gcd_dvd_left s.num.natAbs s.den)
    have hdenNat : g * (s.den / g) = s.den :=
      Nat.mul_div_cancel' (Nat.gcd_dvd_right s.num.natAbs s.den)
    have hdenInt : (g : Int) * ((s.den / g : Nat) : Int) = (s.den : Int) := by
      rw [← Int.natCast_mul, hdenNat]
    have hgNe : (g : Int) ≠ 0 := by omega
    by_cases hpos : 0 ≤ s.num
    · simp only [hpos, ↓reduceIte]
      have hs : (s.num.natAbs : Int) = s.num := by omega
      have hnumInt : (g : Int) * ((s.num.natAbs / g : Nat) : Int) = s.num := by
        rw [← Int.natCast_mul, hnumNat, hs]
      have hmul : (g : Int) * (((s.num.natAbs / g : Nat) : Int) * (s.den : Int)) =
                  (g : Int) * (s.num * ((s.den / g : Nat) : Int)) := by
        calc
          (g : Int) * (((s.num.natAbs / g : Nat) : Int) * (s.den : Int))
              = ((g : Int) * ((s.num.natAbs / g : Nat) : Int)) * (s.den : Int) := (Int.mul_assoc _ _ _).symm
          _ = s.num * (s.den : Int) := by rw [hnumInt]
          _ = s.num * ((g : Int) * ((s.den / g : Nat) : Int)) := by rw [hdenInt]
          _ = (g : Int) * (s.num * ((s.den / g : Nat) : Int)) := by
                rw [← Int.mul_assoc, Int.mul_comm s.num (g : Int), Int.mul_assoc]
      exact Int.eq_of_mul_eq_mul_left hgNe hmul
    · simp only [hpos, ↓reduceIte]
      have hs : -((s.num.natAbs : Int)) = s.num := by omega
      have hnumInt : (g : Int) * -(((s.num.natAbs / g : Nat) : Int)) = s.num := by
        rw [Int.mul_neg, ← Int.natCast_mul, hnumNat, hs]
      have hmul : (g : Int) * (-(((s.num.natAbs / g : Nat) : Int)) * (s.den : Int)) =
                  (g : Int) * (s.num * ((s.den / g : Nat) : Int)) := by
        calc
          (g : Int) * (-(((s.num.natAbs / g : Nat) : Int)) * (s.den : Int))
              = ((g : Int) * -(((s.num.natAbs / g : Nat) : Int))) * (s.den : Int) := (Int.mul_assoc _ _ _).symm
          _ = s.num * (s.den : Int) := by rw [hnumInt]
          _ = s.num * ((g : Int) * ((s.den / g : Nat) : Int)) := by rw [hdenInt]
          _ = (g : Int) * (s.num * ((s.den / g : Nat) : Int)) := by
                rw [← Int.mul_assoc, Int.mul_comm s.num (g : Int), Int.mul_assoc]
      exact Int.eq_of_mul_eq_mul_left hgNe hmul

theorem inUnitInterval_of_equiv {a b : SignedRat} (hab : a ≈ₛ b) (ha : a.inUnitInterval) :
    b.inUnitInterval := by
  rcases ha with ⟨hlo, hhi⟩
  have hadPos : (0 : Int) < (a.den : Int) := by have := a.denPos; omega
  have hbdPos : (0 : Int) < (b.den : Int) := by have := b.denPos; omega
  have hlo' : -((a.den : Int)) * (b.den : Int) ≤ a.num * (b.den : Int) :=
    Int.mul_le_mul_of_nonneg_right hlo (Int.le_of_lt hbdPos)
  have hhi' : a.num * (b.den : Int) ≤ (a.den : Int) * (b.den : Int) :=
    Int.mul_le_mul_of_nonneg_right hhi (Int.le_of_lt hbdPos)
  rw [hab] at hlo' hhi'
  have hlo'' : -((b.den : Int)) * (a.den : Int) ≤ b.num * (a.den : Int) := by
    have : -((a.den : Int)) * (b.den : Int) = -((b.den : Int)) * (a.den : Int) := by
      rw [Int.neg_mul, Int.neg_mul, Int.mul_comm (a.den : Int) (b.den : Int)]
    exact this ▸ hlo'
  have hhi'' : b.num * (a.den : Int) ≤ (b.den : Int) * (a.den : Int) := by
    rw [Int.mul_comm (a.den : Int) (b.den : Int)] at hhi'
    exact hhi'
  exact ⟨Int.le_of_mul_le_mul_right hlo'' hadPos, Int.le_of_mul_le_mul_right hhi'' hadPos⟩

theorem subNNRat_inUnitInterval {a b : NNRat} (ha : a ≤ NNRat.one) (hb : b ≤ NNRat.one) :
    (subNNRat a b).inUnitInterval := by
  rw [NNRat.le_one_iff] at ha hb
  have h1 : a.num * b.den ≤ a.den * b.den := Nat.mul_le_mul_right b.den ha
  have h2 : b.num * a.den ≤ a.den * b.den := by
    rw [Nat.mul_comm a.den b.den]
    exact Nat.mul_le_mul_right a.den hb
  unfold subNNRat inUnitInterval
  dsimp only
  constructor <;> omega

theorem subNNRat_equiv_congr {a₁ a₂ b₁ b₂ : NNRat} (ha : a₁ ≈ a₂) (hb : b₁ ≈ b₂) :
    subNNRat a₁ b₁ ≈ₛ subNNRat a₂ b₂ := by
  unfold subNNRat equiv
  dsimp only
  have h1 : (a₁.num * b₁.den) * (a₂.den * b₂.den) = (a₂.num * b₂.den) * (a₁.den * b₁.den) :=
    cross_a_eq ha
  have h2 : (b₁.num * a₁.den) * (a₂.den * b₂.den) = (b₂.num * a₂.den) * (a₁.den * b₁.den) :=
    cross_b_eq hb
  rw [Int.sub_mul, Int.sub_mul, ← Int.natCast_mul, ← Int.natCast_mul,
      ← Int.natCast_mul, ← Int.natCast_mul, h1, h2]

end SignedRat

end EvalForgeFormal.Calibration
