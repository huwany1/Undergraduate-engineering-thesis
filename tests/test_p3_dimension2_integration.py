# -*- coding: utf-8 -*-
"""
维度二核心规则端到端集成测试
依据: AGENTS.md 规范与维度二实施方案
测试内容:
1. 完美深蹲在六大规则下评级为 ACCEPTABLE
2. 单独触发膝内扣 (KNEE_VALGUS)
3. 单独触发脚跟离地 (HEEL_LIFT)
4. 单独触发骨盆翻转 (PELVIC_TILT)
5. 单独触发动作不对称 (BILATERAL_ASYMMETRY)
6. 复合质量瑕疵全序仲裁排序与综合非医疗指导文案
"""

import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.contracts import (
    RuleCardConfig,
    AssessmentStatus,
    AssessmentReasonCode,
)
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.feedback.sanitizer import SanitizerGate


def make_full_rep(
    min_knee=90.0,
    max_torso=30.0,
    valgus_ratio=None,
    heel_lift_deg=0.0,
    pelvic_tilt_deg=0.0,
    bilateral_diff=None,
):
    return RepetitionRecord(
        rep_id=1,
        is_valid=True,
        status="COMPLETED",
        start_frame=10,
        bottom_frame=50,
        end_frame=90,
        start_timeline_us=333333,
        bottom_timeline_us=1666666,
        end_timeline_us=3000000,
        duration_ms=2666.7,
        descending_duration_ms=1333.3,
        ascending_duration_ms=1333.4,
        min_knee_angle=min_knee,
        max_torso_lean_angle=max_torso,
        extended_metrics={
            "min_valgus_ratio": valgus_ratio,
            "max_heel_lift_deg": heel_lift_deg,
            "max_pelvic_tilt_deg": pelvic_tilt_deg,
            "max_bilateral_diff_deg": bilateral_diff,
        },
    )


def test_dimension2_perfect_squat_all_pass():
    engine = SquatAssessmentEngine()
    rep = make_full_rep(
        min_knee=85.0,
        max_torso=28.0,
        valgus_ratio=0.98,
        heel_lift_deg=2.0,
        pelvic_tilt_deg=3.0,
        bilateral_diff=4.0,
    )
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.ACCEPTABLE
    assert assessment.primary_reason_code == AssessmentReasonCode.ACCEPTABLE.value
    assert len(assessment.violations) == 0
    assert "动作规范" in assessment.summary_feedback
    SanitizerGate().validate(assessment.summary_feedback)


def test_dimension2_valgus_triggered():
    engine = SquatAssessmentEngine()
    rep = make_full_rep(valgus_ratio=0.70)
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert assessment.primary_reason_code == AssessmentReasonCode.KNEE_VALGUS.value
    assert any(v.reason_code == AssessmentReasonCode.KNEE_VALGUS.value for v in assessment.violations)
    assert "膝关节内扣" in assessment.summary_feedback
    SanitizerGate().validate(assessment.summary_feedback)


def test_dimension2_heel_lift_triggered():
    engine = SquatAssessmentEngine()
    rep = make_full_rep(heel_lift_deg=18.0)
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert assessment.primary_reason_code == AssessmentReasonCode.HEEL_LIFT.value
    assert any(v.reason_code == AssessmentReasonCode.HEEL_LIFT.value for v in assessment.violations)
    assert "脚后跟离地" in assessment.summary_feedback
    SanitizerGate().validate(assessment.summary_feedback)


def test_dimension2_pelvic_tilt_triggered():
    engine = SquatAssessmentEngine()
    rep = make_full_rep(pelvic_tilt_deg=16.0)
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert assessment.primary_reason_code == AssessmentReasonCode.PELVIC_TILT.value
    assert any(v.reason_code == AssessmentReasonCode.PELVIC_TILT.value for v in assessment.violations)
    assert "骨盆后倾翻转" in assessment.summary_feedback
    SanitizerGate().validate(assessment.summary_feedback)


def test_dimension2_bilateral_asymmetry_triggered():
    engine = SquatAssessmentEngine()
    rep = make_full_rep(bilateral_diff=22.0)
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert assessment.primary_reason_code == AssessmentReasonCode.BILATERAL_ASYMMETRY.value
    assert any(v.reason_code == AssessmentReasonCode.BILATERAL_ASYMMETRY.value for v in assessment.violations)
    assert "双侧不对称" in assessment.summary_feedback
    SanitizerGate().validate(assessment.summary_feedback)


def test_dimension2_multi_defect_arbitration_and_feedback():
    engine = SquatAssessmentEngine()
    # 模拟同时存在：下蹲不足 (115° > 100°)、膝内扣 (0.68 < 0.82)、脚跟离地 (16° > 12°)
    rep = make_full_rep(
        min_knee=115.0,
        valgus_ratio=0.68,
        heel_lift_deg=16.0,
    )
    assessment = engine.evaluate_repetition(rep)
    assert assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert len(assessment.violations) == 3
    # 验证全部通过严格敏感词门禁
    SanitizerGate().validate(assessment.summary_feedback)
    assert "下蹲深度显著不足" in assessment.summary_feedback
    assert "膝关节内扣" in assessment.summary_feedback
    assert "脚后跟离地" in assessment.summary_feedback
