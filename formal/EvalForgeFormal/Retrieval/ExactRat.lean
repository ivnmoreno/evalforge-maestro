namespace EvalForgeFormal.Retrieval

/--
Self-contained non-negative exact rational number (`num / den` with `0 < den`).
Pure Lean 4 core (`Init`), avoiding IEEE-754 floating-point drift and external packages.
-/
structure NNRat where
  num : Nat
  den : Nat
  denPos : 0 < den
  deriving DecidableEq, Repr

namespace NNRat

/-- Construct a non-negative rational from numerator and strictly positive denominator. -/
def mkNat (num den : Nat) (h : 0 < den) : NNRat := ⟨num, den, h⟩

/-- Exact rational zero (`0 / 1`). -/
def zero : NNRat := ⟨0, 1, Nat.zero_lt_one⟩

/-- Exact rational one (`1 / 1`). -/
def one : NNRat := ⟨1, 1, Nat.zero_lt_one⟩

/-- Embed a natural number `n` as `n / 1`. -/
def ofNat (n : Nat) : NNRat := ⟨n, 1, Nat.zero_lt_one⟩

/-- Exact rational equivalence via cross-multiplication. -/
def equiv (a b : NNRat) : Prop := a.num * b.den = b.num * a.den

infix:50 " ≈ " => NNRat.equiv

/-- Non-strict rational order via cross-multiplication. -/
def le (a b : NNRat) : Prop := a.num * b.den ≤ b.num * a.den

/-- Strict rational order via cross-multiplication. -/
def lt (a b : NNRat) : Prop := a.num * b.den < b.num * a.den

instance : LE NNRat := ⟨NNRat.le⟩
instance : LT NNRat := ⟨NNRat.lt⟩

instance (a b : NNRat) : Decidable (a ≤ b) :=
  inferInstanceAs (Decidable (a.num * b.den ≤ b.num * a.den))

instance (a b : NNRat) : Decidable (a < b) :=
  inferInstanceAs (Decidable (a.num * b.den < b.num * a.den))

instance (a b : NNRat) : Decidable (a ≈ b) :=
  inferInstanceAs (Decidable (a.num * b.den = b.num * a.den))

/-- Executable boolean decision procedure for `a ≤ b`. -/
def leBool (a b : NNRat) : Bool := decide (a.num * b.den ≤ b.num * a.den)

theorem leBool_true_iff (a b : NNRat) : leBool a b = true ↔ a ≤ b :=
  decide_eq_true_iff

theorem leBool_false_iff (a b : NNRat) : leBool a b = false ↔ b < a := by
  show decide (a.num * b.den ≤ b.num * a.den) = false ↔ b.num * a.den < a.num * b.den
  rw [decide_eq_false_iff_not]
  omega

/-- Exact rational addition. -/
def add (a b : NNRat) : NNRat :=
  ⟨a.num * b.den + b.num * a.den, a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩

/-- Exact rational multiplication. -/
def mul (a b : NNRat) : NNRat :=
  ⟨a.num * b.num, a.den * b.den, Nat.mul_pos a.denPos b.denPos⟩

/-- Exact rational scaling by a natural number. -/
def scaleNat (n : Nat) (a : NNRat) : NNRat :=
  ⟨n * a.num, a.den, a.denPos⟩

/-- Exact rational division requiring strict positivity of divisor numerator. -/
def div (a b : NNRat) (hb : 0 < b.num) : NNRat :=
  ⟨a.num * b.den, a.den * b.num, Nat.mul_pos a.denPos hb⟩

/-- Canonical reduced form via `Nat.gcd` (`0 / d` reduces to `0 / 1`) for JSON serialization. -/
def normalize (r : NNRat) : NNRat :=
  if r.num = 0 then
    zero
  else
    let g := Nat.gcd r.num r.den
    have hgPos : 0 < g := Nat.gcd_pos_of_pos_right r.num r.denPos
    have hdvd : g ∣ r.den := Nat.gcd_dvd_right r.num r.den
    have hdenDivPos : 0 < r.den / g := by
      cases hq : r.den / g with
      | zero =>
        have hmul : g * (r.den / g) = r.den := Nat.mul_div_cancel' hdvd
        rw [hq, Nat.mul_zero] at hmul
        have := r.denPos
        omega
      | succ k => exact Nat.succ_pos k
    ⟨r.num / g, r.den / g, hdenDivPos⟩

theorem normalize_equiv (r : NNRat) : normalize r ≈ r := by
  unfold normalize equiv
  by_cases h0 : r.num = 0
  · simp [h0, zero]
  · simp only [h0, ↓reduceIte]
    let g := Nat.gcd r.num r.den
    have hgPos : 0 < g := Nat.gcd_pos_of_pos_right r.num r.denPos
    have hnum : g * (r.num / g) = r.num := Nat.mul_div_cancel' (Nat.gcd_dvd_left r.num r.den)
    have hden : g * (r.den / g) = r.den := Nat.mul_div_cancel' (Nat.gcd_dvd_right r.num r.den)
    have hmul : g * ((r.num / g) * r.den) = g * (r.num * (r.den / g)) := by
      calc
        g * ((r.num / g) * r.den) = (g * (r.num / g)) * r.den := (Nat.mul_assoc _ _ _).symm
        _ = r.num * r.den := by rw [hnum]
        _ = r.num * (g * (r.den / g)) := by rw [hden]
        _ = (r.num * g) * (r.den / g) := (Nat.mul_assoc _ _ _).symm
        _ = (g * r.num) * (r.den / g) := by rw [Nat.mul_comm r.num g]
        _ = g * (r.num * (r.den / g)) := Nat.mul_assoc _ _ _
    exact Nat.eq_of_mul_eq_mul_left hgPos hmul

theorem equiv_refl (a : NNRat) : a ≈ a := rfl

theorem equiv_symm {a b : NNRat} (h : a ≈ b) : b ≈ a := h.symm

theorem equiv_trans {a b c : NNRat} (hab : a ≈ b) (hbc : b ≈ c) : a ≈ c := by
  unfold equiv at *
  have h : b.den * (a.num * c.den) = b.den * (c.num * a.den) := by
    calc
      b.den * (a.num * c.den) = (a.num * b.den) * c.den := by
        rw [Nat.mul_left_comm, ← Nat.mul_assoc]
      _ = (b.num * a.den) * c.den := by rw [hab]
      _ = (b.num * c.den) * a.den := Nat.mul_right_comm _ _ _
      _ = (c.num * b.den) * a.den := by rw [hbc]
      _ = b.den * (c.num * a.den) := by rw [Nat.mul_comm c.num b.den, Nat.mul_assoc]
  exact Nat.eq_of_mul_eq_mul_left b.denPos h

theorem le_refl (a : NNRat) : a ≤ a := Nat.le_refl _

theorem le_of_equiv {a b : NNRat} (h : a ≈ b) : a ≤ b := Nat.le_of_eq h

theorem equiv_of_le_antisymm {a b : NNRat} (h1 : a ≤ b) (h2 : b ≤ a) : a ≈ b :=
  Nat.le_antisymm h1 h2

theorem le_trans {a b c : NNRat} (hab : a ≤ b) (hbc : b ≤ c) : a ≤ c := by
  show a.num * c.den ≤ c.num * a.den
  have h1 : (a.num * b.den) * c.den ≤ (b.num * a.den) * c.den := Nat.mul_le_mul_right c.den hab
  have h2 : (b.num * c.den) * a.den ≤ (c.num * b.den) * a.den := Nat.mul_le_mul_right a.den hbc
  have hmid : (b.num * a.den) * c.den = (b.num * c.den) * a.den := Nat.mul_right_comm _ _ _
  have hcomb : (a.num * b.den) * c.den ≤ (c.num * b.den) * a.den :=
    Nat.le_trans h1 (hmid ▸ h2)
  have hl : (a.num * b.den) * c.den = b.den * (a.num * c.den) := by
    rw [Nat.mul_assoc, Nat.mul_left_comm]
  have hr : (c.num * b.den) * a.den = b.den * (c.num * a.den) := by
    rw [Nat.mul_assoc, Nat.mul_left_comm]
  rw [hl, hr] at hcomb
  exact Nat.le_of_mul_le_mul_left hcomb b.denPos

theorem le_total (a b : NNRat) : a ≤ b ∨ b ≤ a := Nat.le_total _ _

theorem le_of_lt {a b : NNRat} (h : a < b) : a ≤ b := Nat.le_of_lt h

theorem lt_iff_not_le (a b : NNRat) : a < b ↔ ¬ (b ≤ a) := by
  show a.num * b.den < b.num * a.den ↔ ¬ (b.num * a.den ≤ a.num * b.den)
  omega

theorem zero_le (a : NNRat) : zero ≤ a := by
  show 0 * a.den ≤ a.num * 1
  simp

theorem le_one_iff (a : NNRat) : a ≤ one ↔ a.num ≤ a.den := by
  show a.num * 1 ≤ 1 * a.den ↔ a.num ≤ a.den
  simp

theorem zero_lt_iff (a : NNRat) : zero < a ↔ 0 < a.num := by
  show 0 * a.den < a.num * 1 ↔ 0 < a.num
  simp

theorem equiv_zero_iff (a : NNRat) : a ≈ zero ↔ a.num = 0 := by
  show a.num * 1 = 0 * a.den ↔ a.num = 0
  simp

theorem equiv_one_iff (a : NNRat) : a ≈ one ↔ a.num = a.den := by
  show a.num * 1 = 1 * a.den ↔ a.num = a.den
  simp

theorem le_add_right (a b : NNRat) : a ≤ a.add b := by
  show a.num * (a.den * b.den) ≤ (a.num * b.den + b.num * a.den) * a.den
  have h : a.num * (a.den * b.den) = (a.num * b.den) * a.den := by
    rw [Nat.mul_comm a.den b.den, Nat.mul_assoc]
  rw [h, Nat.add_mul]
  exact Nat.le_add_right _ _

theorem le_add_left (a b : NNRat) : b ≤ a.add b := by
  show b.num * (a.den * b.den) ≤ (a.num * b.den + b.num * a.den) * b.den
  have h : b.num * (a.den * b.den) = (b.num * a.den) * b.den := by
    rw [Nat.mul_assoc]
  rw [h, Nat.add_mul]
  exact Nat.le_add_left _ _

theorem add_le_add {a b c d : NNRat} (hab : a ≤ b) (hcd : c ≤ d) : a.add c ≤ b.add d := by
  show (a.num * c.den + c.num * a.den) * (b.den * d.den) ≤
    (b.num * d.den + d.num * b.den) * (a.den * c.den)
  have h1 : (a.num * c.den) * (b.den * d.den) ≤ (b.num * d.den) * (a.den * c.den) := by
    have hl : (a.num * c.den) * (b.den * d.den) = (a.num * b.den) * (c.den * d.den) := by
      calc
        (a.num * c.den) * (b.den * d.den) = a.num * (c.den * (b.den * d.den)) := Nat.mul_assoc _ _ _
        _ = a.num * (b.den * (c.den * d.den)) := by rw [Nat.mul_left_comm c.den b.den d.den]
        _ = (a.num * b.den) * (c.den * d.den) := (Nat.mul_assoc _ _ _).symm
    have hr : (b.num * d.den) * (a.den * c.den) = (b.num * a.den) * (c.den * d.den) := by
      calc
        (b.num * d.den) * (a.den * c.den) = b.num * (d.den * (a.den * c.den)) := Nat.mul_assoc _ _ _
        _ = b.num * (a.den * (d.den * c.den)) := by rw [Nat.mul_left_comm d.den a.den c.den]
        _ = b.num * (a.den * (c.den * d.den)) := by rw [Nat.mul_comm d.den c.den]
        _ = (b.num * a.den) * (c.den * d.den) := (Nat.mul_assoc _ _ _).symm
    rw [hl, hr]
    exact Nat.mul_le_mul_right (c.den * d.den) hab
  have h2 : (c.num * a.den) * (b.den * d.den) ≤ (d.num * b.den) * (a.den * c.den) := by
    have hl : (c.num * a.den) * (b.den * d.den) = (c.num * d.den) * (a.den * b.den) := by
      calc
        (c.num * a.den) * (b.den * d.den) = c.num * (a.den * (b.den * d.den)) := Nat.mul_assoc _ _ _
        _ = c.num * (a.den * (d.den * b.den)) := by rw [Nat.mul_comm b.den d.den]
        _ = c.num * (d.den * (a.den * b.den)) := by rw [Nat.mul_left_comm a.den d.den b.den]
        _ = (c.num * d.den) * (a.den * b.den) := (Nat.mul_assoc _ _ _).symm
    have hr : (d.num * b.den) * (a.den * c.den) = (d.num * c.den) * (a.den * b.den) := by
      calc
        (d.num * b.den) * (a.den * c.den) = d.num * (b.den * (a.den * c.den)) := Nat.mul_assoc _ _ _
        _ = d.num * (b.den * (c.den * a.den)) := by rw [Nat.mul_comm a.den c.den]
        _ = d.num * (c.den * (b.den * a.den)) := by rw [Nat.mul_left_comm b.den c.den a.den]
        _ = d.num * (c.den * (a.den * b.den)) := by rw [Nat.mul_comm b.den a.den]
        _ = (d.num * c.den) * (a.den * b.den) := (Nat.mul_assoc _ _ _).symm
    rw [hl, hr]
    exact Nat.mul_le_mul_right (a.den * b.den) hcd
  rw [Nat.add_mul, Nat.add_mul]
  exact Nat.add_le_add h1 h2

theorem add_assoc_equiv (a b c : NNRat) : (a.add b).add c ≈ a.add (b.add c) := by
  show ((a.num * b.den + b.num * a.den) * c.den + c.num * (a.den * b.den)) * (a.den * (b.den * c.den)) =
       (a.num * (b.den * c.den) + (b.num * c.den + c.num * b.den) * a.den) * ((a.den * b.den) * c.den)
  have hden : a.den * (b.den * c.den) = (a.den * b.den) * c.den := (Nat.mul_assoc _ _ _).symm
  rw [hden]
  apply congrArg (· * ((a.den * b.den) * c.den))
  have t1 : (a.num * b.den) * c.den = a.num * (b.den * c.den) := Nat.mul_assoc _ _ _
  have t2 : (b.num * a.den) * c.den = (b.num * c.den) * a.den := Nat.mul_right_comm _ _ _
  have t3 : c.num * (a.den * b.den) = (c.num * b.den) * a.den := by
    rw [Nat.mul_comm a.den b.den, Nat.mul_assoc]
  rw [Nat.add_mul, Nat.add_mul, t1, t2, t3, Nat.add_assoc]

theorem add_zero_right_equiv (a : NNRat) : a.add zero ≈ a := by
  show (a.num * 1 + 0 * a.den) * a.den = a.num * (a.den * 1)
  simp

theorem add_zero_left_equiv (a : NNRat) : zero.add a ≈ a := by
  show (0 * a.den + a.num * 1) * a.den = a.num * (1 * a.den)
  simp

theorem add_pos_of_pos_left {a b : NNRat} (ha : zero < a) : zero < a.add b := by
  rw [zero_lt_iff] at ha ⊢
  show 0 < a.num * b.den + b.num * a.den
  have h1 : 0 < a.num * b.den := Nat.mul_pos ha b.denPos
  omega

theorem scaleNat_le_scaleNat {m n : Nat} {a b : NNRat} (hmn : m ≤ n) (hab : a ≤ b) :
    scaleNat m a ≤ scaleNat n b := by
  show (m * a.num) * b.den ≤ (n * b.num) * a.den
  rw [Nat.mul_assoc, Nat.mul_assoc]
  exact Nat.mul_le_mul hmn hab

theorem scaleNat_zero_equiv (a : NNRat) : scaleNat 0 a ≈ zero := by
  show (0 * a.num) * 1 = 0 * a.den
  simp

theorem scaleNat_pos {n : Nat} {a : NNRat} (hn : 0 < n) (ha : zero < a) :
    zero < scaleNat n a := by
  rw [zero_lt_iff] at ha ⊢
  exact Nat.mul_pos hn ha

theorem div_le_one_of_le {a b : NNRat} (hab : a ≤ b) (hb : 0 < b.num) :
    div a b hb ≤ one := by
  rw [le_one_iff]
  show a.num * b.den ≤ a.den * b.num
  rw [Nat.mul_comm a.den b.num]
  exact hab

theorem div_self_equiv_one (a : NNRat) (ha : 0 < a.num) : div a a ha ≈ one := by
  rw [equiv_one_iff]
  exact Nat.mul_comm a.num a.den

theorem div_zero_equiv_zero (b : NNRat) (hb : 0 < b.num) : div zero b hb ≈ zero := by
  rw [equiv_zero_iff]
  simp [div, zero]

theorem div_equiv_zero_of_equiv_zero {a b : NNRat} (ha : a ≈ zero) (hb : 0 < b.num) :
    div a b hb ≈ zero := by
  rw [equiv_zero_iff] at ha ⊢
  simp [div, ha]

theorem div_equiv_one_of_equiv {a b : NNRat} (hab : a ≈ b) (hb : 0 < b.num) :
    div a b hb ≈ one := by
  rw [equiv_one_iff]
  exact hab.trans (Nat.mul_comm b.num a.den)

/--
Elementary rearrangement swap inequality: assigning the larger weight `w₁ ≥ w₂` to the larger
non-negative gain `b ≥ a` never decreases the weighted sum.
-/
theorem swap_le_of_le (a b : Nat) (w₁ w₂ : NNRat) (hab : a ≤ b) (hw : w₂ ≤ w₁) :
    (scaleNat a w₁).add (scaleNat b w₂) ≤ (scaleNat b w₁).add (scaleNat a w₂) := by
  show ((a * w₁.num) * w₂.den + (b * w₂.num) * w₁.den) * (w₁.den * w₂.den) ≤
       ((b * w₁.num) * w₂.den + (a * w₂.num) * w₁.den) * (w₁.den * w₂.den)
  apply Nat.mul_le_mul_right (w₁.den * w₂.den)
  have h1 : (a * w₁.num) * w₂.den = a * (w₁.num * w₂.den) := Nat.mul_assoc _ _ _
  have h2 : (b * w₂.num) * w₁.den = b * (w₂.num * w₁.den) := Nat.mul_assoc _ _ _
  have h3 : (b * w₁.num) * w₂.den = b * (w₁.num * w₂.den) := Nat.mul_assoc _ _ _
  have h4 : (a * w₂.num) * w₁.den = a * (w₂.num * w₁.den) := Nat.mul_assoc _ _ _
  rw [h1, h2, h3, h4]
  have hyx : w₂.num * w₁.den ≤ w₁.num * w₂.den := hw
  obtain ⟨d, hd⟩ := Nat.exists_eq_add_of_le hab
  obtain ⟨e, he⟩ := Nat.exists_eq_add_of_le hyx
  rw [hd, he, Nat.mul_add, Nat.add_mul, Nat.add_mul, Nat.mul_add, Nat.mul_add]
  omega

end NNRat

end EvalForgeFormal.Retrieval
