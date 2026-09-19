# -*- coding: utf-8 -*-
"""
P2 时序统计与多维动作分析引擎 (Multi-Repetition Analytics)
"""

from .group_analytics import (
    MultiRepAnalyticsEngine,
    ConsistencyScoreResult,
    DepthDecayResult,
    TempoAnalysisResult,
    SingleRepSlice,
    MultiRepSummary,
)

__all__ = [
    "MultiRepAnalyticsEngine",
    "ConsistencyScoreResult",
    "DepthDecayResult",
    "TempoAnalysisResult",
    "SingleRepSlice",
    "MultiRepSummary",
]
