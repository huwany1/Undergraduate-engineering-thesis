# -*- coding: utf-8 -*-
"""
P3 非医疗化敏感词熔断过滤器 (Sanitizer Gate)
依据: P3_规则与反馈_详细实施方案.md (Section 9.3)
"""

from typing import List

# 严厉禁止的医疗与病理词汇黑名单
DISALLOWED_MEDICAL_TERMS: List[str] = [
    "损伤", "伤害", "疼痛", "疾病", "病理", "治疗", "康复", "矫正",
    "骨折", "半月板", "韧带撕裂", "关节炎", "腰肌劳损", "骨盆畸形", "医疗"
]


class MedicalTerminologyViolationError(ValueError):
    """检测到医疗化词汇时触发的防御性异常"""
    pass


class SanitizerGate:
    """文案合规门禁扫描器"""

    def __init__(self, disallowed_terms: List[str] = None):
        self.disallowed_terms = disallowed_terms or DISALLOWED_MEDICAL_TERMS

    def validate(self, text: str) -> None:
        """
        扫描文本，若命中任何医疗/病理黑名单词汇，立即抛出异常熔断。
        """
        if not text:
            return

        for term in self.disallowed_terms:
            if term in text:
                raise MedicalTerminologyViolationError(
                    f"安全门禁拦截：反馈文本检测到禁止使用的医疗化/病理化词汇 '{term}'。"
                    "依据 P0/P3 规范，系统仅输出客观运动学要点提示，严禁做出医疗断言。"
                )

    def is_safe(self, text: str) -> bool:
        """非抛错版本的安全性检测"""
        try:
            self.validate(text)
            return True
        except MedicalTerminologyViolationError:
            return False
