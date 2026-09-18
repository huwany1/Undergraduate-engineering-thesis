# -*- coding: utf-8 -*-
"""
P4 自动化测试套件：5 大黄金场景矩阵核验硬断言测试
"""

import pytest
from p4_validation.contracts import TestCaseId, VerificationStatus
from p4_validation.golden_assets import GoldenAssetRegistry, SyntheticStreamGenerator
from p4_validation.replayer import DeterministicReplayer
from p4_validation.matrix_verifier import TestMatrixVerifier


@pytest.fixture
def replayer():
    return DeterministicReplayer()


@pytest.fixture
def registry():
    return GoldenAssetRegistry()


def test_matrix_tc01_perfect_squat(replayer, registry):
    spec = registry.get_spec(TestCaseId.TC_01_PERFECT_SQUAT)
    stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
    trace = replayer.replay_stream(spec.case_id, stream)
    res = TestMatrixVerifier.verify_case(spec, trace)

    assert res.status == VerificationStatus.PASS
    assert res.actual_count == 1
    assert res.actual_status == "ACCEPTABLE"
    assert res.actual_primary_reason == "ACCEPTABLE"
    assert len(res.diff_reasons) == 0


def test_matrix_tc02_shallow_squat(replayer, registry):
    spec = registry.get_spec(TestCaseId.TC_02_SHALLOW_SQUAT)
    stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
    trace = replayer.replay_stream(spec.case_id, stream)
    res = TestMatrixVerifier.verify_case(spec, trace)

    assert res.status == VerificationStatus.PASS
    assert res.actual_count == 1
    assert res.actual_status == "NEEDS_IMPROVEMENT"
    assert res.actual_primary_reason == "INSUFFICIENT_DEPTH"
    assert "INSUFFICIENT_DEPTH" in res.actual_reason_codes
    assert len(res.diff_reasons) == 0


def test_matrix_tc03_excessive_lean(replayer, registry):
    spec = registry.get_spec(TestCaseId.TC_03_EXCESSIVE_LEAN)
    stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
    trace = replayer.replay_stream(spec.case_id, stream)
    res = TestMatrixVerifier.verify_case(spec, trace)

    assert res.status == VerificationStatus.PASS
    assert res.actual_count == 1
    assert res.actual_status == "NEEDS_IMPROVEMENT"
    assert res.actual_primary_reason == "EXCESSIVE_TORSO_LEAN"
    assert "EXCESSIVE_TORSO_LEAN" in res.actual_reason_codes
    assert len(res.diff_reasons) == 0


def test_matrix_tc04_dual_defect(replayer, registry):
    spec = registry.get_spec(TestCaseId.TC_04_DUAL_DEFECT)
    stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
    trace = replayer.replay_stream(spec.case_id, stream)
    res = TestMatrixVerifier.verify_case(spec, trace)

    assert res.status == VerificationStatus.PASS
    assert res.actual_count == 1
    assert res.actual_status == "NEEDS_IMPROVEMENT"
    # 根据严重度仲裁，深度缺陷和前倾缺陷均被捕获
    assert "INSUFFICIENT_DEPTH" in res.actual_reason_codes
    assert "EXCESSIVE_TORSO_LEAN" in res.actual_reason_codes
    assert len(res.diff_reasons) == 0


def test_matrix_tc05_out_of_frame_refusal(replayer, registry):
    spec = registry.get_spec(TestCaseId.TC_05_OUT_OF_FRAME)
    stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
    trace = replayer.replay_stream(spec.case_id, stream)
    res = TestMatrixVerifier.verify_case(spec, trace)

    assert res.status == VerificationStatus.PASS
    assert res.actual_count == 0
    assert res.actual_status == "NOT_EVALUATED"
    assert res.actual_primary_reason in ("OUT_OF_FRAME", "INCOMPLETE_REP")
    assert len(res.diff_reasons) == 0


def test_matrix_full_suite_summary(replayer, registry):
    specs = registry.list_all()
    results = []
    for spec in specs:
        stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
        trace = replayer.replay_stream(spec.case_id, stream)
        res = TestMatrixVerifier.verify_case(spec, trace)
        results.append(res)

    summary = TestMatrixVerifier.summarize_suite(results)

    assert summary.total_cases == 5
    assert summary.passed_cases == 5
    assert summary.failed_cases == 0
    assert summary.concordance_rate == 1.0
    assert summary.rejection_rate == 1.0
    assert summary.mae_count == 0.0
