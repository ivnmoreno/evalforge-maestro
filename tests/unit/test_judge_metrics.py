"""Unit tests for all five built-in judge metrics, decoupling, and thresholds."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from evalforge_maestro.exceptions import ConfigurationError, MetricError
from evalforge_maestro.judges.metrics import (
    AnswerCorrectnessMetric,
    AnswerRelevanceMetric,
    ContextRelevanceMetric,
    CustomRubricJudgeMetric,
    GroundednessMetric,
    answer_correctness,
    answer_relevance,
    context_relevance,
    custom_rubric_judge,
    groundedness,
)
from evalforge_maestro.types import (
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
    Metric,
    MetricStatus,
    RetrievedChunk,
)


def test_judge_metrics_conform_to_metric_protocol_and_formal_metadata() -> None:
    cfg = JudgeConfig(model="fake/judge", mock_mode=True)
    instances = [
        groundedness(config=cfg),
        answer_relevance(config=cfg),
        context_relevance(config=cfg),
        answer_correctness(config=cfg),
        custom_rubric_judge("Grade clarity and conciseness.", config=cfg),
    ]
    ids = [m.metadata.metric_id for m in instances]
    assert ids == [
        "groundedness",
        "answer_relevance",
        "context_relevance",
        "answer_correctness",
        "custom_rubric",
    ]
    for m in instances:
        assert isinstance(m, Metric)
        assert m.metadata.metric_version
        assert m.metadata.what_it_measures
        assert m.metadata.calculation_method
        assert m.metadata.known_limitations

    for bad_kw in (
        {"rubric": "   "},
        {"rubric": "valid", "metric_id": "  "},
        {"rubric": "valid", "metric_version": ""},
    ):
        with pytest.raises(MetricError):
            CustomRubricJudgeMetric(**bad_kw)  # type: ignore[arg-type]


def test_rag_evidence_decoupling_accurate_answer_irrelevant_context() -> None:
    async def mock_llm(**kwargs: Any) -> str:
        user_msg = kwargs["messages"][1]["content"]
        if "Criterion: Groundedness" in user_msg:
            return json.dumps(
                {
                    "score": 0.1,
                    "rationale": "Retrieved context discusses bananas; answer discusses Paris.",
                    "supported_claims": [],
                    "unsupported_claims": ["The capital of France is Paris."],
                }
            )
        if "Criterion: Context Relevance" in user_msg:
            return json.dumps(
                {
                    "score": 0.05,
                    "rationale": "Chunks are off-topic relative to query.",
                }
            )
        return json.dumps({"score": 0.98, "rationale": "Answer is factually correct and relevant."})

    cfg = JudgeConfig(model="fake/model", pass_threshold=0.5, retry_backoff_seconds=0.0)
    g = GroundednessMetric(config=cfg, completion_fn=mock_llm)
    c = ContextRelevanceMetric(config=cfg, completion_fn=mock_llm)
    ac = AnswerCorrectnessMetric(config=cfg, completion_fn=mock_llm)
    ar = AnswerRelevanceMetric(config=cfg, completion_fn=mock_llm)

    case = EvaluationCase(
        id="dec-1",
        input="What is the capital of France?",
        reference="Paris",
    )
    exec_res = ExecutionResult(
        case_id="dec-1",
        input=case.input,
        output="The capital of France is Paris.",
        retrieved_chunks=[RetrievedChunk(id="ch1", text="Bananas are rich in potassium.")],
        elapsed_seconds=0.02,
    )

    g_res = g.evaluate(case, exec_res)
    c_res = c.evaluate(case, exec_res)
    ac_res = ac.evaluate(case, exec_res)
    ar_res = ar.evaluate(case, exec_res)

    assert ac_res.status == MetricStatus.PASS and ac_res.score == 0.98
    assert ar_res.status == MetricStatus.PASS and ar_res.score == 0.98
    assert g_res.status == MetricStatus.FAIL and g_res.score == 0.1
    assert c_res.status == MetricStatus.FAIL and c_res.score == 0.05
    assert any("UNSUPPORTED:" in e for e in g_res.evidence)


def test_missing_inputs_return_not_applicable_and_upstream_errors_return_inconclusive() -> None:
    calls = 0

    async def should_not_be_called(**kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        return json.dumps({"score": 0.9, "rationale": "ok"})

    cfg = JudgeConfig(model="fake/model", retry_backoff_seconds=0.0)
    g = GroundednessMetric(config=cfg, completion_fn=should_not_be_called)
    cr = ContextRelevanceMetric(config=cfg, completion_fn=should_not_be_called)
    ac = AnswerCorrectnessMetric(config=cfg, completion_fn=should_not_be_called)
    ar = AnswerRelevanceMetric(config=cfg, completion_fn=should_not_be_called)

    # No retrieved chunks -> groundedness & context_relevance NOT_APPLICABLE
    # No reference -> answer_correctness NOT_APPLICABLE
    case_no_ref = EvaluationCase(id="na-1", input="Hello?")
    exec_no_ctx = ExecutionResult(
        case_id="na-1",
        input="Hello?",
        output="Hi there!",
        retrieved_chunks=[],
        elapsed_seconds=0.01,
    )
    assert g.evaluate(case_no_ref, exec_no_ctx).status == MetricStatus.NOT_APPLICABLE
    assert cr.evaluate(case_no_ref, exec_no_ctx).status == MetricStatus.NOT_APPLICABLE
    assert ac.evaluate(case_no_ref, exec_no_ctx).status == MetricStatus.NOT_APPLICABLE
    assert calls == 0

    # answer_relevance needs only input & output -> invokes completion_fn
    ar_res = ar.evaluate(case_no_ref, exec_no_ctx)
    assert ar_res.status == MetricStatus.PASS
    assert calls == 1

    # Upstream execution errors short-circuit cleanly to INCONCLUSIVE without calling judge
    exec_err = ExecutionResult(
        case_id="na-1",
        input="Hello?",
        output=None,
        errors=["Adapter timeout after 5s"],
        elapsed_seconds=5.0,
    )
    err_res = ar.evaluate(case_no_ref, exec_err)
    assert err_res.status == MetricStatus.INCONCLUSIVE
    assert err_res.score is None
    assert "Adapter timeout after 5s" in err_res.evidence
    assert calls == 1


def test_case_criteria_threshold_overrides_and_unsupported_anomaly_flag() -> None:
    async def mock_llm(**kwargs: Any) -> str:
        return json.dumps(
            {
                "score": 0.72,
                "rationale": "Mostly supported, one minor unsupported aside.",
                "supported_claims": ["Main fact is cited."],
                "unsupported_claims": ["Minor extra claim."],
            }
        )

    cfg = JudgeConfig(model="fake/model", pass_threshold=0.5)
    g = GroundednessMetric(config=cfg, completion_fn=mock_llm)
    case_default = EvaluationCase(id="t1", input="Q")
    case_strict = EvaluationCase(
        id="t2",
        input="Q",
        criteria=CaseCriteria(metric_thresholds={"groundedness": 0.8}),
    )
    execution = ExecutionResult(
        case_id="t1",
        input="Q",
        output="Claim.",
        retrieved_chunks=[RetrievedChunk(id="c1", text="Main fact.")],
        elapsed_seconds=0.01,
    )
    res_pass = g.evaluate(case_default, execution)
    assert res_pass.status == MetricStatus.PASS
    assert "unsupported_claims_present" in res_pass.anomaly_flags

    res_fail = g.evaluate(case_strict, execution)
    assert res_fail.status == MetricStatus.FAIL
    assert res_fail.config_snapshot["threshold"] == 0.8
    assert "api_key" not in res_fail.config_snapshot


@pytest.mark.gate_determinism
def test_mock_mode_is_deterministic_offline_evidence_aware_and_nonce_invariant() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, local_only=True, pass_threshold=0.5)
    g = GroundednessMetric(config=cfg)
    c = ContextRelevanceMetric(config=cfg)
    ac = AnswerCorrectnessMetric(config=cfg)
    ar = AnswerRelevanceMetric(config=cfg)
    cr = CustomRubricJudgeMetric(
        "Verify SLA percentages and monthly uptime guarantees are explicitly stated.",
        config=cfg,
    )

    case = EvaluationCase(
        id="rag-decouple",
        input="What is the SLA monthly uptime guarantee?",
        reference="99.9% monthly uptime guarantee",
    )
    bad_ctx_exec = ExecutionResult(
        case_id="rag-decouple",
        input=case.input,
        output="Our enterprise SLA provides a 99.9% monthly uptime guarantee.",
        retrieved_chunks=[
            RetrievedChunk(id="offtopic", text="Bananas and citrus fruits need warm weather.")
        ],
        elapsed_seconds=0.01,
    )

    run1 = [m.evaluate(case, bad_ctx_exec) for m in (g, c, ac, ar, cr)]
    run2 = [m.evaluate(case, bad_ctx_exec) for m in (g, c, ac, ar, cr)]
    assert [r.model_dump() for r in run1] == [r.model_dump() for r in run2]

    g_res, c_res, ac_res, ar_res, cr_res = run1
    # Accurate answer + off-topic context: correctness/relevance PASS while grounding/context FAIL
    assert ac_res.status == MetricStatus.PASS
    assert ar_res.status == MetricStatus.PASS
    assert g_res.status == MetricStatus.FAIL
    assert c_res.status == MetricStatus.FAIL
    assert cr_res.status == MetricStatus.PASS

    # Relevant context with faithful output passes groundedness and context_relevance
    good_ctx_exec = ExecutionResult(
        case_id="rag-decouple",
        input=case.input,
        output="Our enterprise SLA provides a 99.9% monthly uptime guarantee.",
        retrieved_chunks=[
            RetrievedChunk(
                id="sla-doc",
                text="Enterprise SLA policy specifies a 99.9% monthly uptime guarantee.",
            )
        ],
        elapsed_seconds=0.01,
    )
    assert g.evaluate(case, good_ctx_exec).status == MetricStatus.PASS
    assert c.evaluate(case, good_ctx_exec).status == MetricStatus.PASS


def test_mock_mode_scripted_responses_route_through_strict_validator() -> None:
    cfg = JudgeConfig(
        model="mock-judge",
        mock_mode=True,
        max_retries=2,
        retry_backoff_seconds=5.0,
    )
    metric = GroundednessMetric(
        config=cfg,
        mock_responses={
            "single-ok": json.dumps({"score": 0.95, "rationale": "Scripted pass."}),
            "single-bad": "not-valid-json",
            "retry-ok": [
                "{corrupt",
                json.dumps({"score": 0.82, "rationale": "Recovered on retry 2."}),
            ],
        },
    )
    chunk = [RetrievedChunk(id="c1", text="Context.")]

    def _run_case(cid: str) -> Any:
        return metric.evaluate(
            EvaluationCase(id=cid, input="q"),
            ExecutionResult(
                case_id=cid,
                input="q",
                output="a",
                retrieved_chunks=chunk,
                elapsed_seconds=0.0,
            ),
        )

    r_ok = _run_case("single-ok")
    assert r_ok.status == MetricStatus.PASS and r_ok.score == 0.95

    r_bad = _run_case("single-bad")
    assert r_bad.status == MetricStatus.INCONCLUSIVE and r_bad.score is None

    r_retry = _run_case("retry-ok")
    assert r_retry.status == MetricStatus.PASS and r_retry.score == 0.82


def test_aevaluate_batch_groups_by_context_bounds_concurrency_and_isolates_faults() -> None:
    dispatch_order: list[str] = []
    active = 0
    peak_active = 0

    async def tracked_completion(**kwargs: Any) -> str:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        user_msg = kwargs["messages"][1]["content"]
        try:
            await asyncio.sleep(0.01)
            # Extract case id via chunk text markers or user input token
            for marker in ("c0", "c1", "c2", "c3"):
                if f"Q-{marker}" in user_msg:
                    dispatch_order.append(marker)
                    if marker == "c1":
                        raise RuntimeError("Simulated single-case timeout/failure")
                    return json.dumps(
                        {
                            "score": 0.9 if marker != "c2" else 0.4,
                            "rationale": f"Evaluated {marker}.",
                        }
                    )
            raise ValueError("Missing case marker")
        finally:
            active -= 1

    ctx_a = [RetrievedChunk(id="doc-a", text="Shared context A.")]
    ctx_b = [RetrievedChunk(id="doc-b", text="Shared context B.")]

    def _pair(
        cid: str, chunks: list[RetrievedChunk], idx: int
    ) -> tuple[EvaluationCase, ExecutionResult]:
        q = f"Q-{cid}"
        return (
            EvaluationCase(id=cid, input=q),
            ExecutionResult(
                case_id=cid,
                input=q,
                output=f"out-{idx}",
                retrieved_chunks=chunks,
                elapsed_seconds=0.0,
            ),
        )

    items = [
        _pair("c0", ctx_a, 0),
        _pair("c1", ctx_b, 1),
        _pair("c2", ctx_a, 2),
        _pair("c3", ctx_b, 3),
    ]

    cfg = JudgeConfig(model="fake/batch", max_retries=0, retry_backoff_seconds=0.0)
    metric = GroundednessMetric(config=cfg, completion_fn=tracked_completion)
    results = asyncio.run(metric.aevaluate_batch(items, max_concurrency=2))

    assert peak_active <= 2
    # Both ctx_a cases (c0, c2) are scheduled contiguously before ctx_b cases (c1, c3)
    assert dispatch_order[:2] == ["c0", "c2"]
    assert set(dispatch_order[2:]) == {"c1", "c3"}
    # Output order strictly preserves original item ordering c0, c1, c2, c3
    assert results[0].score == 0.9 and results[0].status == MetricStatus.PASS
    assert results[1].score is None and results[1].status == MetricStatus.INCONCLUSIVE
    assert results[2].score == 0.4 and results[2].status == MetricStatus.FAIL
    assert results[3].score == 0.9 and results[3].status == MetricStatus.PASS


def test_mock_edge_cases_empty_outputs_offtopic_custom_rubric_and_batch_empty() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    g = GroundednessMetric(config=cfg)
    c = ContextRelevanceMetric(config=cfg)
    ac = AnswerCorrectnessMetric(config=cfg)
    ar = AnswerRelevanceMetric(config=cfg)
    cr_req = CustomRubricJudgeMetric(
        "Check security compliance terms.",
        require_reference=True,
        require_context=True,
        config=cfg,
    )

    assert asyncio.run(g.aevaluate_batch([], max_concurrency=2)) == []
    with pytest.raises(ConfigurationError):
        asyncio.run(g.aevaluate_batch([], max_concurrency=0))

    empty_exec = ExecutionResult(
        case_id="emp",
        input="What is the SLA?",
        output="   ",
        retrieved_chunks=[RetrievedChunk(id="c1", text="SLA doc")],
        elapsed_seconds=0.0,
    )
    case = EvaluationCase(id="emp", input="What is the SLA?", reference="99.9%")
    assert g.evaluate(case, empty_exec).score == 0.0
    assert ac.evaluate(case, empty_exec).score == 0.0
    assert ar.evaluate(case, empty_exec).score == 0.0
    assert cr_req.evaluate(case, empty_exec).score == 0.0
    # Empty reference / empty chunks with require_reference & require_context -> NOT_APPLICABLE
    assert (
        cr_req.evaluate(EvaluationCase(id="na", input="Q"), empty_exec).status
        == MetricStatus.NOT_APPLICABLE
    )

    verbose_offtopic = ExecutionResult(
        case_id="off",
        input="What is the SLA?",
        output="Pineapples grow very rapidly inside humid tropical plantations.",
        retrieved_chunks=[RetrievedChunk(id="c1", text="Enterprise SLA is 99.9%.")],
        elapsed_seconds=0.0,
    )
    assert ar.evaluate(case, verbose_offtopic).score == 0.2
    assert cr_req.evaluate(case, verbose_offtopic).score == 0.15
    assert c.evaluate(EvaluationCase(id="eq", input="What is?"), verbose_offtopic).score == 0.0

    # evaluate() inside active event loop delegates safely without RuntimeError
    async def _sync_in_loop() -> MetricStatus:
        return ar.evaluate(case, verbose_offtopic).status

    assert asyncio.run(_sync_in_loop()) == MetricStatus.FAIL

    # Empty scripted mock response sequence safely degrades to INCONCLUSIVE
    g_empty_seq = GroundednessMetric(config=cfg, mock_responses={"emp": []})
    res_empty_seq = g_empty_seq.evaluate(case, empty_exec)
    assert res_empty_seq.status == MetricStatus.INCONCLUSIVE
    assert res_empty_seq.score is None


def test_mock_groundedness_preserves_decimals_and_dotted_identifiers() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    metric = GroundednessMetric(config=cfg)

    grounded_case = EvaluationCase(id="dec-ok", input="What is the SLA and config version?")
    grounded_exec = ExecutionResult(
        case_id="dec-ok",
        input=grounded_case.input,
        output="99.9% monthly uptime SLA for v0.1.0 in evalforge.toml.",
        retrieved_chunks=[
            RetrievedChunk(
                id="doc-sla",
                text=(
                    "EvalForge Pro guarantees 99.9% monthly uptime SLA "
                    "using v0.1.0 and evalforge.toml."
                ),
            )
        ],
        elapsed_seconds=0.01,
    )
    ok_res = metric.evaluate(grounded_case, grounded_exec)
    assert ok_res.status == MetricStatus.PASS
    assert ok_res.score == 1.0
    assert ok_res.label == "pass"
    assert ok_res.anomaly_flags == []
    assert not any(ev.startswith("UNSUPPORTED:") for ev in ok_res.evidence)

    mixed_case = EvaluationCase(id="dec-mixed", input="What is the SLA?")
    mixed_exec = ExecutionResult(
        case_id="dec-mixed",
        input=mixed_case.input,
        output="99.9% monthly uptime SLA. Includes unlimited teleportation.",
        retrieved_chunks=[
            RetrievedChunk(
                id="doc-sla",
                text="EvalForge Pro provides a 99.9% monthly uptime SLA.",
            )
        ],
        elapsed_seconds=0.01,
    )
    mixed_res = metric.evaluate(mixed_case, mixed_exec)
    assert mixed_res.label == "fail"
    assert "unsupported_claims_present" in mixed_res.anomaly_flags
    assert any("teleportation" in ev for ev in mixed_res.evidence)
    assert not any(ev == "UNSUPPORTED: 99" for ev in mixed_res.evidence)
