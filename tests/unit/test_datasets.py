"""Unit tests for DatasetEngine streaming validation and canonical fingerprinting."""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

import pytest

from evalforge_maestro.datasets import DatasetEngine, DatasetStreamResult
from evalforge_maestro.exceptions import (
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
)
from evalforge_maestro.types import EvaluationCase


def _write_jsonl(path: Path, rows: list[str]) -> Path:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_streaming_iteration_and_default_dataset_ids(tmp_path: Path) -> None:
    ds_file = _write_jsonl(
        tmp_path / "golden_set.jsonl",
        [
            '{"id": "c1", "input": "hello", "reference": "world"}',
            "",
            '{"id": "c2", "input": {"k": 1}, "criteria": {"mandatory": true}}',
            "   ",
        ],
    )
    engine = DatasetEngine(ds_file, dataset_version="2026.1")
    captured: list[DatasetStreamResult] = []
    cases = list(engine.iter_cases(on_complete=captured.append))

    assert [c.id for c in cases] == ["c1", "c2"]
    assert len(captured) == 1
    meta = captured[0]
    assert meta.dataset_id == "golden_set"
    assert meta.dataset_version == "2026.1"
    assert meta.evaluated_case_count == 2
    assert meta.dataset_capped is False
    assert meta.max_dataset_cases is None
    assert len(meta.dataset_fingerprint) == 64

    mem_engine = DatasetEngine([{"id": "m1", "input": "x"}])
    assert mem_engine.fingerprint().dataset_id == "in-memory"

    with pytest.raises(DatasetError):
        DatasetEngine(ds_file, dataset_id="   ")


def test_fingerprint_invariant_across_key_order_and_whitespace(tmp_path: Path) -> None:
    file_a = _write_jsonl(
        tmp_path / "a.jsonl",
        [
            '{"id": "1", "input": "q1", "reference": "a1", "metadata": {"tags": ["t"]}}',
            '{"id": "2", "input": "q2", "reference": "a2"}',
        ],
    )
    file_b = _write_jsonl(
        tmp_path / "b.jsonl",
        [
            '{"reference":"a1",  "metadata": {"tags": ["t"]}, "input":  "q1", "id": "1"}',
            "",
            '{"schema_version": "1.0", "reference": "a2", "id": "2", "input": "q2"}',
            "   ",
        ],
    )
    file_changed = _write_jsonl(
        tmp_path / "c.jsonl",
        [
            '{"id": "1", "input": "q1!", "reference": "a1", "metadata": {"tags": ["t"]}}',
            '{"id": "2", "input": "q2", "reference": "a2"}',
        ],
    )

    fp_a = DatasetEngine(file_a).fingerprint().dataset_fingerprint
    fp_b = DatasetEngine(file_b).fingerprint().dataset_fingerprint
    fp_c = DatasetEngine(file_changed).fingerprint().dataset_fingerprint
    assert fp_a == fp_b
    assert fp_a != fp_c


def test_validation_errors_duplicates_and_empty_datasets(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("\n   \n\n", encoding="utf-8")
    with pytest.raises(EmptyDatasetError):
        list(DatasetEngine(empty_file).iter_cases())

    with pytest.raises(EmptyDatasetError):
        DatasetEngine([]).fingerprint()

    with pytest.raises(DatasetError, match="not found"):
        list(DatasetEngine(tmp_path / "missing.jsonl").iter_cases())

    bad_json = _write_jsonl(tmp_path / "bad_json.jsonl", ['{"id": "1", "input": "ok"}', "{oops"])
    with pytest.raises(DatasetError) as exc_json:
        list(DatasetEngine(bad_json).iter_cases())
    assert exc_json.value.line_number == 2

    non_obj = _write_jsonl(tmp_path / "non_obj.jsonl", ['["not", "an", "object"]'])
    with pytest.raises(DatasetError) as exc_non_obj:
        list(DatasetEngine(non_obj).iter_cases())
    assert exc_non_obj.value.line_number == 1

    bad_schema = _write_jsonl(tmp_path / "bad_schema.jsonl", ['{"id": "c9"}'])
    with pytest.raises(DatasetError) as exc_schema:
        list(DatasetEngine(bad_schema).iter_cases())
    assert exc_schema.value.line_number == 1
    assert exc_schema.value.case_id == "c9"
    assert exc_schema.value.field == "input"

    dup_file = _write_jsonl(
        tmp_path / "dup.jsonl",
        ['{"id": "c1", "input": "a"}', '{"id": " c1 ", "input": "b"}'],
    )
    with pytest.raises(DuplicateCaseIdError) as exc_dup:
        list(DatasetEngine(dup_file).iter_cases())
    assert exc_dup.value.line_number == 2
    assert exc_dup.value.case_id == "c1"


def test_max_cases_partial_slice_and_one_line_lookahead(tmp_path: Path) -> None:
    five_cases = _write_jsonl(
        tmp_path / "five.jsonl",
        [f'{{"id": "c{i}", "input": "q{i}"}}' for i in range(5)] + ["", "  "],
    )
    exact_res = DatasetEngine(five_cases).fingerprint(max_cases=5)
    assert exact_res.evaluated_case_count == 5
    assert exact_res.dataset_capped is False
    assert exact_res.max_dataset_cases == 5

    six_with_bad_tail = _write_jsonl(
        tmp_path / "six.jsonl",
        [f'{{"id": "c{i}", "input": "q{i}"}}' for i in range(5)]
        + ["{CORRUPT_UNREAD_TAIL_RECORD_MUST_NOT_BE_PARSED}"],
    )
    capped_res = DatasetEngine(six_with_bad_tail).fingerprint(max_cases=5)
    assert capped_res.evaluated_case_count == 5
    assert capped_res.dataset_capped is True
    assert capped_res.dataset_fingerprint == exact_res.dataset_fingerprint

    with pytest.raises(DatasetError):
        list(DatasetEngine(five_cases).iter_cases(max_cases=0))


def test_large_10k_streaming_performance_and_bounded_memory(tmp_path: Path) -> None:
    large_file = tmp_path / "large_10k.jsonl"
    payload_pad = "x" * 2048
    with large_file.open("w", encoding="utf-8") as handle:
        for i in range(10_000):
            handle.write(
                json.dumps({"id": f"case-{i}", "input": f"q-{i}", "reference": payload_pad}) + "\n"
            )

    tracemalloc.start()
    start = time.perf_counter()
    stream_info: list[DatasetStreamResult] = []
    count = 0
    for case in DatasetEngine(large_file).iter_cases(on_complete=stream_info.append):
        assert isinstance(case, EvaluationCase)
        count += 1
    elapsed = time.perf_counter() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert count == 10_000
    assert stream_info[0].evaluated_case_count == 10_000
    assert elapsed < 5.0
    # 10k x 2KB payload = ~20MB raw; lazy streaming peak should stay well below full payload load
    assert peak < 15 * 1024 * 1024
