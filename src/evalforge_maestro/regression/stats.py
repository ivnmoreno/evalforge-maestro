"""Pure-stdlib Student's t, Welch's t, and paired statistical distribution helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta, round_score
from evalforge_maestro.types import SignificanceStatus, StatisticalMethod, StatisticalSummary

_CF_MAX_ITER = 200
_CF_EPS = 3e-14
_FPMIN = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Evaluate continued fraction for regularized incomplete beta I_x(a, b)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d

    for m in range(1, _CF_MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _CF_EPS:
            break

    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Compute regularized incomplete beta function I_x(a, b) via math.lgamma."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_bt = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return max(0.0, min(1.0, bt * _betacf(a, b, x) / a))
    return max(0.0, min(1.0, 1.0 - bt * _betacf(b, a, 1.0 - x) / b))


def student_t_two_tailed_p(t_stat: float, df: float) -> float:
    """Compute exact two-tailed Student's t p-value for statistic t_stat and df > 0."""
    if df <= 0.0:
        raise ValueError(f"Degrees of freedom must be positive, got {df!r}")
    t_abs = abs(t_stat)
    if t_abs == 0.0:
        return 1.0
    x = df / (df + t_abs * t_abs)
    return max(0.0, min(1.0, regularized_incomplete_beta(0.5 * df, 0.5, x)))


def student_t_critical(df: float, confidence_level: float = 0.95) -> float:
    """Invert regularized incomplete beta to compute two-tailed critical value t*."""
    if df <= 0.0:
        raise ValueError(f"Degrees of freedom must be positive, got {df!r}")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError(f"confidence_level must lie in (0, 1), got {confidence_level!r}")

    alpha = 1.0 - confidence_level
    lo = 0.0
    hi = 1.0
    for _ in range(72):
        mid = 0.5 * (lo + hi)
        if regularized_incomplete_beta(0.5 * df, 0.5, mid) < alpha:
            lo = mid
        else:
            hi = mid
    x = 0.5 * (lo + hi)
    return math.sqrt(df * (1.0 - x) / max(x, _FPMIN))


def _mean_and_sample_std(values: Sequence[float]) -> tuple[float | None, float | None]:
    n = len(values)
    if n == 0:
        return None, None
    mean_v = sum(values) / n
    if n < 2:
        return mean_v, None
    var = sum((v - mean_v) ** 2 for v in values) / (n - 1)
    return mean_v, math.sqrt(max(0.0, var))


def _clamp_delta(value: float) -> float:
    return round_delta(max(-1.0, min(1.0, value)))


def _finalize_inference(
    *,
    method: StatisticalMethod,
    confidence_level: float,
    sample_size: int,
    baseline_sample_size: int,
    candidate_sample_size: int,
    excluded_pair_count: int,
    mean_delta: float | None,
    delta_std: float | None,
    standard_error: float | None,
    baseline_std: float | None,
    candidate_std: float | None,
    effect_size: float | None,
    df: float | None,
    has_enough_samples: bool,
) -> StatisticalSummary:
    rounded_base_sd = round_delta(baseline_std) if baseline_std is not None else None
    rounded_cand_sd = round_delta(candidate_std) if candidate_std is not None else None
    rounded_delta_sd = round_delta(delta_std) if delta_std is not None else None
    rounded_mean = _clamp_delta(mean_delta) if mean_delta is not None else None

    if not has_enough_samples or mean_delta is None or standard_error is None or df is None:
        return StatisticalSummary(
            method=method,
            confidence_level=confidence_level,
            sample_size=sample_size,
            baseline_sample_size=baseline_sample_size,
            candidate_sample_size=candidate_sample_size,
            excluded_pair_count=excluded_pair_count,
            mean_delta=rounded_mean,
            delta_std=rounded_delta_sd,
            standard_error=None,
            baseline_std=rounded_base_sd,
            candidate_std=rounded_cand_sd,
            significance=SignificanceStatus.INSUFFICIENT_DATA,
            statistically_significant=False,
            explanation=(
                f"{method.value}: insufficient sample count ({sample_size}) "
                "for confidence interval estimation."
            ),
        )

    alpha = 1.0 - confidence_level
    rounded_se = round_delta(max(0.0, standard_error))
    rounded_df = round_delta(df)
    rounded_eff = round_delta(effect_size) if effect_size is not None else None

    if standard_error <= FLOAT_EPSILON:
        ci_low = rounded_mean
        ci_high = rounded_mean
        if abs(mean_delta) <= FLOAT_EPSILON:
            p_val = 1.0
            sig = SignificanceStatus.NOT_SIGNIFICANT
            is_sig = False
            msg = f"{method.value}: zero variance and zero mean delta (not significant)."
        elif mean_delta > 0.0:
            p_val = 0.0
            sig = SignificanceStatus.SIGNIFICANT_IMPROVEMENT
            is_sig = True
            msg = (
                f"{method.value}: constant positive shift {rounded_mean:+.6g} "
                f"across {sample_size} sample(s) (zero variance, significant improvement)."
            )
        else:
            p_val = 0.0
            sig = SignificanceStatus.SIGNIFICANT_REGRESSION
            is_sig = True
            msg = (
                f"{method.value}: constant negative shift {rounded_mean:+.6g} "
                f"across {sample_size} sample(s) (zero variance, significant regression)."
            )
        return StatisticalSummary(
            method=method,
            confidence_level=confidence_level,
            sample_size=sample_size,
            baseline_sample_size=baseline_sample_size,
            candidate_sample_size=candidate_sample_size,
            excluded_pair_count=excluded_pair_count,
            mean_delta=rounded_mean,
            delta_std=rounded_delta_sd,
            standard_error=0.0,
            baseline_std=rounded_base_sd,
            candidate_std=rounded_cand_sd,
            ci_low=ci_low,
            ci_high=ci_high,
            p_value=p_val,
            effect_size=rounded_eff,
            degrees_of_freedom=rounded_df,
            significance=sig,
            statistically_significant=is_sig,
            explanation=msg,
        )

    t_crit = student_t_critical(df, confidence_level)
    margin = t_crit * standard_error
    ci_low = _clamp_delta(mean_delta - margin)
    ci_high = _clamp_delta(mean_delta + margin)
    t_stat = mean_delta / standard_error
    p_val = round_score(student_t_two_tailed_p(t_stat, df))

    if p_val < alpha - FLOAT_EPSILON:
        sig = (
            SignificanceStatus.SIGNIFICANT_IMPROVEMENT
            if mean_delta > 0.0
            else SignificanceStatus.SIGNIFICANT_REGRESSION
        )
        is_sig = True
    else:
        sig = SignificanceStatus.NOT_SIGNIFICANT
        is_sig = False

    return StatisticalSummary(
        method=method,
        confidence_level=confidence_level,
        sample_size=sample_size,
        baseline_sample_size=baseline_sample_size,
        candidate_sample_size=candidate_sample_size,
        excluded_pair_count=excluded_pair_count,
        mean_delta=rounded_mean,
        delta_std=rounded_delta_sd,
        standard_error=rounded_se,
        baseline_std=rounded_base_sd,
        candidate_std=rounded_cand_sd,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_val,
        effect_size=rounded_eff,
        degrees_of_freedom=rounded_df,
        significance=sig,
        statistically_significant=is_sig,
        explanation=(
            f"{method.value}: delta={rounded_mean:+.6g}, "
            f"{round(confidence_level * 100)}% CI=[{ci_low:+.6g}, {ci_high:+.6g}], "
            f"p={p_val:.6g}, n={sample_size} ({sig.value})."
        ),
    )


def compute_paired_case_statistics(
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    confidence_level: float = 0.95,
    min_samples: int = 2,
    excluded_pair_count: int = 0,
) -> StatisticalSummary:
    """Compute paired Student's t interval and p-value over aligned case scores."""
    if len(baseline_scores) != len(candidate_scores):
        raise ValueError("Paired baseline and candidate score sequences must have equal length")
    n = len(baseline_scores)
    diffs = [cand - base for base, cand in zip(baseline_scores, candidate_scores, strict=True)]
    mean_d, sd_d = _mean_and_sample_std(diffs)
    _, base_sd = _mean_and_sample_std(baseline_scores)
    _, cand_sd = _mean_and_sample_std(candidate_scores)

    has_enough = n >= max(2, min_samples)
    se = (sd_d / math.sqrt(n)) if (sd_d is not None and n >= 2) else None
    eff = (
        (mean_d / sd_d)
        if (mean_d is not None and sd_d is not None and sd_d > FLOAT_EPSILON)
        else None
    )
    df = float(n - 1) if n >= 2 else None

    return _finalize_inference(
        method=StatisticalMethod.PAIRED_T_CASE,
        confidence_level=confidence_level,
        sample_size=n,
        baseline_sample_size=n,
        candidate_sample_size=n,
        excluded_pair_count=excluded_pair_count,
        mean_delta=mean_d,
        delta_std=sd_d,
        standard_error=se,
        baseline_std=base_sd,
        candidate_std=cand_sd,
        effect_size=eff,
        df=df,
        has_enough_samples=has_enough,
    )


def compute_welch_run_statistics(
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    confidence_level: float = 0.95,
    min_samples: int = 2,
) -> StatisticalSummary:
    """Compute Welch's unequal-variance t-interval across baseline and candidate run means."""
    k = len(baseline_scores)
    m = len(candidate_scores)
    sample_size = min(k, m)
    mean_b, sd_b = _mean_and_sample_std(baseline_scores)
    mean_c, sd_c = _mean_and_sample_std(candidate_scores)
    mean_d = (mean_c - mean_b) if (mean_b is not None and mean_c is not None) else None

    has_enough = k >= max(2, min_samples) and m >= max(2, min_samples)
    se: float | None = None
    df: float | None = None
    eff: float | None = None

    if sd_b is not None and sd_c is not None:
        v_b = (sd_b * sd_b) / k if sd_b > FLOAT_EPSILON else 0.0
        v_c = (sd_c * sd_c) / m if sd_c > FLOAT_EPSILON else 0.0
        v_sum = v_b + v_c
        se = math.sqrt(v_sum)
        pooled_sd = math.sqrt(((k - 1) * sd_b * sd_b + (m - 1) * sd_c * sd_c) / (k + m - 2))
        if mean_d is not None and pooled_sd > FLOAT_EPSILON:
            eff = mean_d / pooled_sd
        if se > FLOAT_EPSILON:
            scale = max(v_b, v_c)
            rb = v_b / scale
            rc = v_c / scale
            df = ((rb + rc) ** 2) / ((rb * rb) / (k - 1) + (rc * rc) / (m - 1))
        else:
            df = float(k + m - 2)

    return _finalize_inference(
        method=StatisticalMethod.WELCH_T_RUN,
        confidence_level=confidence_level,
        sample_size=sample_size,
        baseline_sample_size=k,
        candidate_sample_size=m,
        excluded_pair_count=0,
        mean_delta=mean_d,
        delta_std=None,
        standard_error=se,
        baseline_std=sd_b,
        candidate_std=sd_c,
        effect_size=eff,
        df=df,
        has_enough_samples=has_enough,
    )


def compute_one_sample_run_statistics(
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    confidence_level: float = 0.95,
    min_samples: int = 2,
) -> StatisticalSummary:
    """Compute one-sample t-interval when comparing one scalar reference run vs N >= 2 trials."""
    k = len(baseline_scores)
    m = len(candidate_scores)
    if (k < 2 and m < 2) or (k >= 2 and m >= 2) or k == 0 or m == 0:
        raise ValueError(
            "compute_one_sample_run_statistics expects one single-run side and one >=2-run side"
        )

    mean_b, sd_b = _mean_and_sample_std(baseline_scores)
    mean_c, sd_c = _mean_and_sample_std(candidate_scores)
    mean_d = (mean_c or 0.0) - (mean_b or 0.0)

    if m >= 2:
        repeated_n = m
        repeated_sd = sd_c if sd_c is not None else 0.0
    else:
        repeated_n = k
        repeated_sd = sd_b if sd_b is not None else 0.0

    se = repeated_sd / math.sqrt(repeated_n)
    eff = (mean_d / repeated_sd) if repeated_sd > FLOAT_EPSILON else None
    df = float(repeated_n - 1)
    has_enough = repeated_n >= max(2, min_samples)

    return _finalize_inference(
        method=StatisticalMethod.ONE_SAMPLE_T_RUN,
        confidence_level=confidence_level,
        sample_size=repeated_n,
        baseline_sample_size=k,
        candidate_sample_size=m,
        excluded_pair_count=0,
        mean_delta=mean_d,
        delta_std=None,
        standard_error=se,
        baseline_std=sd_b,
        candidate_std=sd_c,
        effect_size=eff,
        df=df,
        has_enough_samples=has_enough,
    )
