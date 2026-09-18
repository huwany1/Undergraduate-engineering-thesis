# -*- coding: utf-8 -*-
"""
P1 姿态视频链路处理包
"""

from .contracts import (
    RunStatus,
    ProcessingStatus,
    PoseStatus,
    OverlayStatus,
    Side,
    TimeBasis,
    ReasonCode,
    LandmarkPoint,
    PoseFrameResult,
    FrameEnvelope,
    FrameQuality,
    RunContext,
    InputManifest,
    ValidationReport,
)
from .input_probe import InputProbe, InputProbeError
from .decode_adapter import DecodeAdapter, DecodeAdapterError
from .quality_gate import QualityGate
from .overlay_renderer import OverlayRenderer
from .ordered_writer import OrderedWriter, OrderedWriterError
from .evidence_writer import EvidenceWriter
from .publisher import AtomicPublisher, PublishError
from .runner import PipelineRunner
from .engine.base import PoseEngine
from .engine.tasks_adapter import MediaPipeTasksPoseEngine, PoseEngineError
from .engine.mock_adapter import DeterministicMockPoseEngine

__all__ = [
    "RunStatus",
    "ProcessingStatus",
    "PoseStatus",
    "OverlayStatus",
    "Side",
    "TimeBasis",
    "ReasonCode",
    "LandmarkPoint",
    "PoseFrameResult",
    "FrameEnvelope",
    "FrameQuality",
    "RunContext",
    "InputManifest",
    "ValidationReport",
    "InputProbe",
    "InputProbeError",
    "DecodeAdapter",
    "DecodeAdapterError",
    "QualityGate",
    "OverlayRenderer",
    "OrderedWriter",
    "OrderedWriterError",
    "EvidenceWriter",
    "AtomicPublisher",
    "PublishError",
    "PipelineRunner",
    "PoseEngine",
    "MediaPipeTasksPoseEngine",
    "DeterministicMockPoseEngine",
    "PoseEngineError",
]
