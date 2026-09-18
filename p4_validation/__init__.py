# -*- coding: utf-8 -*-
"""
P4 验证包核心模块 (Validation Package Suite)
"""

from .contracts import (
    TestCaseId,
    VerificationStatus,
    KeyframeEventType,
    ToleranceBand,
    GoldenSampleSpec,
    ScreenshotArtifact,
    CaseVerificationResult,
    ValidationPackageSummary,
)
from .golden_assets import (
    SyntheticStreamGenerator,
    GoldenAssetRegistry,
)
from .replayer import (
    DeterministicReplayer,
    ReplayTrace,
    KeyframeEventSnapshot,
)
from .matrix_verifier import (
    TestMatrixVerifier,
)
from .overlay_renderer import (
    P4OverlayRenderer,
)
from .packager import (
    EvidencePackager,
)

__all__ = [
    "TestCaseId",
    "VerificationStatus",
    "KeyframeEventType",
    "ToleranceBand",
    "GoldenSampleSpec",
    "ScreenshotArtifact",
    "CaseVerificationResult",
    "ValidationPackageSummary",
    "SyntheticStreamGenerator",
    "GoldenAssetRegistry",
    "DeterministicReplayer",
    "ReplayTrace",
    "KeyframeEventSnapshot",
    "TestMatrixVerifier",
    "P4OverlayRenderer",
    "EvidencePackager",
]
