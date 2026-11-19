"""Deterministic evidence-aware offline mock judge scorer and scripted dispatcher."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from evalforge_maestro._canonical import canonical_json_str, round_score
from evalforge_maestro.judges.prompts import JudgePromptSpec
from evalforge_maestro.types import EvaluationCase, ExecutionResult

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "your",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.%-][a-z0-9]+)*")
# Split sentence/clause boundaries without breaking decimals or dotted
# identifiers (e.g. 99.9%, v0.1.0, evalforge.toml).
_CLAUSE_SPLIT_RE = re.compile(r"(?:[!?;\n]|(?<![A-Za-z0-9])\.|\.(?![A-Za-z0-9]))+")


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return canonical_json_str(value)


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("es") and not token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokenize(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    raw = [_normalize_token(tok) for tok in _TOKEN_RE.findall(normalized)]
    filtered = {tok for tok in raw if tok not in _STOPWORDS}
    return filtered if filtered else set(raw)


def _score_groundedness_mock(execution: ExecutionResult) -> dict[str, Any]:
    out_text = _to_text(execution.output).strip()
    if not out_text:
        return {
            "score": 0.0,
            "rationale": "Mock groundedness: target output is empty.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": ["Empty target output."],
        }

    chunk_text = " ".join(chunk.text for chunk in execution.retrieved_chunks)
    chunk_tokens = _tokenize(chunk_text)
    out_tokens = _tokenize(out_text)
    if not out_tokens or not chunk_tokens:
        return {
            "score": 0.0,
            "rationale": "Mock groundedness: no overlapping evidence tokens in retrieved chunks.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [out_text],
        }

    supported_claims: list[str] = []
    unsupported_claims: list[str] = []
    for raw_clause in _CLAUSE_SPLIT_RE.split(out_text):
        clause = raw_clause.strip()
        if not clause:
            continue
        clause_tokens = _tokenize(clause)
        if not clause_tokens:
            continue
        overlap_ratio = len(clause_tokens & chunk_tokens) / len(clause_tokens)
        if overlap_ratio >= 0.5:
            supported_claims.append(clause)
        else:
            unsupported_claims.append(clause)

    score = round_score(len(out_tokens & chunk_tokens) / len(out_tokens))
    return {
        "score": score,
        "rationale": (
            f"Mock groundedness: {len(out_tokens & chunk_tokens)}/{len(out_tokens)} "
            "output evidence tokens grounded in retrieved chunks."
        ),
        "verdict": "pass" if not unsupported_claims and score >= 0.5 else "fail",
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
    }


def _score_context_relevance_mock(
    case: EvaluationCase,
    execution: ExecutionResult,
) -> dict[str, Any]:
    q_tokens = _tokenize(_to_text(case.input))
    chunk_tokens = _tokenize(" ".join(chunk.text for chunk in execution.retrieved_chunks))
    if not q_tokens or not chunk_tokens:
        return {
            "score": 0.0,
            "rationale": "Mock context_relevance: query or retrieved chunks contain no tokens.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    overlap = len(q_tokens & chunk_tokens)
    score = round_score(overlap / len(q_tokens))
    return {
        "score": score,
        "rationale": (
            f"Mock context_relevance: retrieved chunks cover {overlap}/{len(q_tokens)} "
            "query concept tokens."
        ),
        "verdict": "pass" if score >= 0.5 else "fail",
        "supported_claims": [],
        "unsupported_claims": [],
    }


def _score_answer_correctness_mock(
    case: EvaluationCase,
    execution: ExecutionResult,
) -> dict[str, Any]:
    ref_raw = _to_text(case.reference).strip()
    out_raw = _to_text(execution.output).strip()
    if not out_raw:
        return {
            "score": 0.0,
            "rationale": "Mock answer_correctness: target output is empty.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    norm_out = unicodedata.normalize("NFC", out_raw).casefold()
    norm_ref = unicodedata.normalize("NFC", ref_raw).casefold()
    if norm_out == norm_ref:
        return {
            "score": 1.0,
            "rationale": "Mock answer_correctness: exact normalized match with reference.",
            "verdict": "pass",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    o_tokens = _tokenize(out_raw)
    r_tokens = _tokenize(ref_raw)
    if not o_tokens or not r_tokens:
        return {
            "score": 0.0,
            "rationale": "Mock answer_correctness: insufficient comparable tokens.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    common = len(o_tokens & r_tokens)
    recall = common / len(r_tokens)
    precision = common / len(o_tokens)
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0.0 else 0.0
    score = round_score(0.75 * recall + 0.25 * f1)
    return {
        "score": score,
        "rationale": (
            f"Mock answer_correctness: reference recall={recall:.2f}, f1={f1:.2f} "
            "between output and reference."
        ),
        "verdict": "pass" if score >= 0.5 else "fail",
        "supported_claims": [],
        "unsupported_claims": [],
    }


def _score_answer_relevance_mock(
    case: EvaluationCase,
    execution: ExecutionResult,
) -> dict[str, Any]:
    out_raw = _to_text(execution.output).strip()
    if not out_raw:
        return {
            "score": 0.0,
            "rationale": "Mock answer_relevance: target output is empty.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    q_tokens = _tokenize(_to_text(case.input))
    o_tokens = _tokenize(out_raw)
    if not o_tokens:
        return {
            "score": 0.0,
            "rationale": "Mock answer_relevance: target output contains no substantive tokens.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    if not q_tokens:
        return {
            "score": 0.75,
            "rationale": "Mock answer_relevance: substantive non-empty output evaluated.",
            "verdict": "pass",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    overlap = len(o_tokens & q_tokens)
    if overlap > 0:
        score = round_score(0.6 + 0.4 * (overlap / len(q_tokens)))
        rationale = (
            f"Mock answer_relevance: output addresses {overlap}/{len(q_tokens)} query concepts."
        )
    elif len(o_tokens) <= 4:
        score = 0.75
        rationale = "Mock answer_relevance: concise direct response to user input."
    else:
        score = 0.2
        rationale = "Mock answer_relevance: verbose output shares zero concepts with query."
    return {
        "score": score,
        "rationale": rationale,
        "verdict": "pass" if score >= 0.5 else "fail",
        "supported_claims": [],
        "unsupported_claims": [],
    }


def _score_custom_rubric_mock(
    spec: JudgePromptSpec,
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    rubric_override: str | None = None,
) -> dict[str, Any]:
    out_raw = _to_text(execution.output).strip()
    if not out_raw:
        return {
            "score": 0.0,
            "rationale": f"Mock {spec.metric_id}: target output is empty.",
            "verdict": "fail",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    rubric_text = rubric_override if rubric_override is not None else spec.rubric_instructions
    o_tokens = _tokenize(out_raw)
    rubric_tokens = _tokenize(rubric_text)
    q_tokens = _tokenize(_to_text(case.input))
    anchor_tokens = rubric_tokens | q_tokens
    if not anchor_tokens or not o_tokens:
        return {
            "score": 0.75,
            "rationale": f"Mock {spec.metric_id}: non-empty response evaluated cleanly.",
            "verdict": "pass",
            "supported_claims": [],
            "unsupported_claims": [],
        }
    rubric_overlap = len(o_tokens & rubric_tokens)
    query_overlap = len(o_tokens & q_tokens)
    if rubric_overlap == 0 and query_overlap == 0:
        score = 0.15
    else:
        denom = max(1, min(len(rubric_tokens), 4))
        rubric_ratio = min(1.0, rubric_overlap / denom)
        query_ratio = min(1.0, query_overlap / max(1, len(q_tokens))) if q_tokens else 0.0
        signal = max(rubric_ratio, 0.5 * query_ratio)
        score = round_score(0.35 + 0.65 * signal)
    return {
        "score": score,
        "rationale": (
            f"Mock {spec.metric_id}: matched {rubric_overlap} rubric and "
            f"{query_overlap} query concepts."
        ),
        "verdict": "pass" if score >= 0.5 else "fail",
        "supported_claims": [],
        "unsupported_claims": [],
    }


def generate_mock_judge_json(
    spec: JudgePromptSpec,
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    rubric_override: str | None = None,
) -> str:
    """Return deterministic, evidence-sensitive JSON matching JudgeResponse contract."""
    if spec.metric_id == "groundedness":
        payload = _score_groundedness_mock(execution)
    elif spec.metric_id == "context_relevance":
        payload = _score_context_relevance_mock(case, execution)
    elif spec.metric_id == "answer_correctness":
        payload = _score_answer_correctness_mock(case, execution)
    elif spec.metric_id == "answer_relevance":
        payload = _score_answer_relevance_mock(case, execution)
    else:
        payload = _score_custom_rubric_mock(spec, case, execution, rubric_override=rubric_override)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)
