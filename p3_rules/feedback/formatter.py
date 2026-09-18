# -*- coding: utf-8 -*-
"""
P3 模板化证据提示格式化器 (Feedback Formatter)
依据: P3_规则与反馈_详细实施方案.md (Section 9.2)
"""

from typing import List, Optional
from ..contracts import (
    AssessmentStatus,
    RuleViolation,
    AssessmentReasonCode,
)
from .sanitizer import SanitizerGate


class FeedbackFormatter:
    """证据化非医疗动作反馈格式化引擎"""

    TPL_ACCEPTABLE = "动作规范，下蹲深度充分，躯干姿态稳定。"
    TPL_NOT_EVALUATED = "姿态置信度不足或画面不完整，本次不作质量评价。"

    def __init__(self, sanitizer: Optional[SanitizerGate] = None):
        self.sanitizer = sanitizer or SanitizerGate()

    def compose_summary(
        self,
        overall_status: AssessmentStatus,
        violations: List[RuleViolation]
    ) -> str:
        """
        根据总体状态与有序违规列表，生成综合动作反馈文本。
        """
        if overall_status == AssessmentStatus.ACCEPTABLE:
            summary = self.TPL_ACCEPTABLE
        elif overall_status == AssessmentStatus.NOT_EVALUATED:
            # 取第一条门控拒绝原因的文案，或兜底文案
            if violations and violations[0].feedback_text:
                summary = violations[0].feedback_text
            else:
                summary = self.TPL_NOT_EVALUATED
        else:
            # NEEDS_IMPROVEMENT: 汇总所有排序后的要点建议
            pieces = []
            for v in violations:
                if v.feedback_text:
                    pieces.append(v.feedback_text)
            if pieces:
                summary = " ".join(pieces)
            else:
                summary = "动作已完成，部分姿态指标有待提高。"

        # 强制通过敏感词合规安全门禁
        self.sanitizer.validate(summary)
        return summary
