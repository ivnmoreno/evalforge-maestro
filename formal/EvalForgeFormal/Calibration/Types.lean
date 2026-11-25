import EvalForgeFormal.Calibration.ExactMath

namespace EvalForgeFormal.Calibration

open EvalForgeFormal.Retrieval

/-- Canonical judge metric status matching `MetricStatus` in `src/evalforge_maestro/types.py`. -/
inductive JudgeStatus where
  | pass
  | fail
  | warning
  | inconclusive
  | notApplicable
  deriving DecidableEq, Repr

namespace JudgeStatus

/-- Returns `true` iff this judge status excludes a sample from valid calibration scoring. -/
def isExcluded : JudgeStatus → Bool
  | .inconclusive => true
  | .notApplicable => true
  | .pass => false
  | .fail => false
  | .warning => false

/-- Canonical serialized string matching `MetricStatus.value`. -/
def toCanonicalString : JudgeStatus → String
  | .pass => "PASS"
  | .fail => "FAIL"
  | .warning => "WARNING"
  | .inconclusive => "INCONCLUSIVE"
  | .notApplicable => "NOT_APPLICABLE"

end JudgeStatus

/-- Disagreement categories matching `CalibrationDisagreementType` in `types.py`. -/
inductive DisagreementType where
  | tooGenerous
  | tooHarsh
  | scoreDivergence
  | inconclusive
  deriving DecidableEq, Repr

namespace DisagreementType

/-- Canonical serialized string matching `CalibrationDisagreementType.value`. -/
def toCanonicalString : DisagreementType → String
  | .tooGenerous => "too_generous"
  | .tooHarsh => "too_harsh"
  | .scoreDivergence => "score_divergence"
  | .inconclusive => "inconclusive"

end DisagreementType

/-- Formal configuration thresholds for judge calibration (`data-model.md`). -/
structure CalibrationConfig where
  passThreshold : NNRat
  humanThreshold : NNRat
  scoreDivergenceThreshold : NNRat
  deriving DecidableEq, Repr

/-- Predicate stating a `CalibrationConfig` satisfies canonical unit/positive threshold bounds. -/
def CalibrationConfig.isValid (cfg : CalibrationConfig) : Prop :=
  cfg.passThreshold ≤ NNRat.one ∧
  cfg.humanThreshold ≤ NNRat.one ∧
  0 < cfg.scoreDivergenceThreshold.num ∧
  cfg.scoreDivergenceThreshold ≤ NNRat.one

/-- Pre-validated calibration sample pairing human labels with a judge evaluation outcome. -/
structure CalibrationSample where
  caseId : String
  humanScore : Option NNRat
  humanPassed : Option Bool
  judgeScore : Option NNRat
  judgeStatus : JudgeStatus
  deriving DecidableEq, Repr

/-- Predicate asserting optional scores on a sample lie in `[0, 1]`. -/
def CalibrationSample.scoresUnit (s : CalibrationSample) : Prop :=
  (∀ hs, s.humanScore = some hs → hs ≤ NNRat.one) ∧
  (∀ js, s.judgeScore = some js → js ≤ NNRat.one)

/-- Projected valid calibration row included in aggregate metrics and threshold optimization. -/
structure ValidRow where
  humanNumeric : NNRat
  judgeScore : NNRat
  humanPassed : Bool
  deriving DecidableEq, Repr

/-- Per-sample disagreement record matching `CalibrationDisagreement` in `types.py`. -/
structure DisagreementRecord where
  caseId : String
  disagreementType : DisagreementType
  humanPassed : Bool
  judgeStatus : JudgeStatus
  judgePassed : Option Bool
  scoreDelta : Option SignedRat
  deriving DecidableEq, Repr

/-- Candidate threshold evaluation record for `_optimize_pass_threshold`. -/
structure CandidateEval where
  threshold : NNRat
  agree : Nat
  generous : Nat
  harsh : Nat
  biasSkew : Nat
  dist : NNRat
  deriving DecidableEq, Repr

/-- Formal calibration summary matching `CalibrationReport` numeric & diagnostic fields. -/
structure CalibrationSummary where
  totalCases : Nat
  validCases : Nat
  inconclusiveCases : Nat
  agreedCount : Nat
  tooGenerousCount : Nat
  tooHarshCount : Nat
  exactAgreementRate : Option NNRat
  tooGenerousRate : Option NNRat
  tooHarshRate : Option NNRat
  meanHumanScore : Option NNRat
  meanJudgeScore : Option NNRat
  meanScoreDelta : Option SignedRat
  disagreements : List DisagreementRecord
  recommendedPassThreshold : NNRat
  deriving DecidableEq, Repr

end EvalForgeFormal.Calibration
