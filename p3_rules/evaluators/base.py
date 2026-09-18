# -*- coding: utf-8 -*-
"""
P3 规则评估器基础接口与抽象类
"""

from abc import ABC, abstractmethod
from typing import Optional
from p2_temporal.contracts import RepetitionRecord
from ..contracts import RuleViolation


class BaseRuleEvaluator(ABC):
    """单条规则评估器抽象基类"""

    @abstractmethod
    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        """
        对动作切片进行规则谓词匹配。
        若命中违规，返回 RuleViolation 实体；
        若未命中（完全合规），返回 None。
        """
        pass
