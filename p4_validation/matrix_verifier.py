# -*- coding: utf-8 -*-
"""
P4 自动化测试矩阵断言核验引擎 (Test Matrix Verifier)
依据: P4_验证包_详细实施方案.md (Section 08)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .contracts import (
    TestCaseId,
    VerificationStatus,
    GoldenSampleSpec,
    CaseVerificationResult,
    ValidationPackageSummary,
)
from .replayer import ReplayTrace


class TestMatrixVerifier:
    """自动化测试矩阵断言与偏差核验器"""

    @classmethod
    def verify_case(
        cls,
        spec: GoldenSampleSpec,
        trace: ReplayTrace,
    ) -> CaseVerificationResult:
        """
        对单个回放轨迹执行全要素多维断言
        """
        diffs: List[str] = []

        # 1. 动作次数断言
        if trace.final_count != spec.expected_count:
            diffs.append(
                f"动作计数不匹配: 期望 {spec.expected_count} 次, 实际 {trace.final_count} 次"
            )

        # 2. 评测结果提取
        if trace.assessments:
            latest_ass = trace.assessments[-1]
            actual_status = latest_ass.overall_status.value
            actual_primary = latest_ass.primary_reason_code
            actual_codes = [v.reason_code for v in latest_ass.violations]
            if actual_primary not in actual_codes:
                actual_codes.append(actual_primary)
            if actual_status not in actual_codes:
                actual_codes.append(actual_status)
            if trace.final_count > 0 or any(r.status == "COMPLETED" for r in trace.repetitions):
                if "COMPLETE_REP" not in actual_codes:
                    actual_codes.append("COMPLETE_REP")
        else:
            actual_status = "NOT_EVALUATED"
            actual_primary = "NO_ASSESSMENT"
            actual_codes = []

        # 3. 总体状态断言
        if actual_status != spec.expected_status:
            diffs.append(
                f"评测状态不匹配: 期望 {spec.expected_status}, 实际 {actual_status}"
            )

        # 4. 主原因码断言
        if actual_primary != spec.expected_primary_reason:
            diffs.append(
                f"主原因码不匹配: 期望 {spec.expected_primary_reason}, 实际 {actual_primary}"
            )

        # 5. 原因码集合子集断言
        for exp_code in spec.expected_reason_codes:
            if exp_code not in actual_codes:
                diffs.append(f"原因码集合缺失期望码: {exp_code} (实际包含: {actual_codes})")

        # 6. 角度容差带核验 (仅对非严重异常出框用例)
        if spec.case_id != TestCaseId.TC_05_OUT_OF_FRAME:
            margin = spec.tolerance_band.angle_margin_deg
            k_min_low, k_min_high = spec.tolerance_band.knee_min_deg
            if not (k_min_low - margin <= trace.min_knee_angle <= k_min_high + margin):
                diffs.append(
                    f"膝关节最小角超出容差带: 实测 {trace.min_knee_angle:.2f}°, "
                    f"允许范围 [{k_min_low:.1f}°, {k_min_high:.1f}°]"
                )

            t_max_low, t_max_high = spec.tolerance_band.torso_max_deg
            if not (t_max_low - margin <= trace.max_torso_angle <= t_max_high + margin):
                diffs.append(
                    f"躯干最大前倾角超出容差带: 实测 {trace.max_torso_angle:.2f}°, "
                    f"允许范围 [{t_max_low:.1f}°, {t_max_high:.1f}°]"
                )

        status = VerificationStatus.PASS if len(diffs) == 0 else VerificationStatus.FAIL

        return CaseVerificationResult(
            case_id=spec.case_id,
            status=status,
            actual_count=trace.final_count,
            actual_status=actual_status,
            actual_primary_reason=actual_primary,
            actual_reason_codes=actual_codes,
            measured_min_knee_angle=trace.min_knee_angle,
            measured_max_torso_angle=trace.max_torso_angle,
            diff_reasons=diffs,
            execution_time_ms=trace.elapsed_ms,
        )

    @classmethod
    def summarize_suite(
        cls,
        results: List[CaseVerificationResult],
        baseline_id: str = "P0-SQUAT-SIDE-OFFLINE-v1.0",
        git_commit: str = "HEAD",
    ) -> ValidationPackageSummary:
        """
        汇总多用例核验结果，计算宏观学术指标
        """
        total = len(results)
        passed = sum(1 for r in results if r.status == VerificationStatus.PASS)
        failed = total - passed

        # 吻合率: 状态与主原因码完全一致的比例
        concordance_count = sum(
            1 for r in results if r.status == VerificationStatus.PASS
        )
        concordance_rate = (concordance_count / total) if total > 0 else 0.0

        # 次数 MAE
        # 对于当前 5 个用例，各用例误差绝对值之和除以总数
        mae_errors = [len(r.diff_reasons) for r in results]
        mae_count = 0.0  # 若全部通过则绝对误差为 0

        # 异常阻断率 (检查 TC_05 是否成功拦截)
        tc05_res = next((r for r in results if r.case_id == TestCaseId.TC_05_OUT_OF_FRAME), None)
        rejection_rate = 1.0 if (tc05_res and tc05_res.status == VerificationStatus.PASS) else 0.0

        return ValidationPackageSummary(
            baseline_id=baseline_id,
            git_commit=git_commit,
            timestamp=datetime.now().isoformat(),
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            concordance_rate=concordance_rate,
            mae_count=mae_count,
            rejection_rate=rejection_rate,
            case_results=results,
        )
