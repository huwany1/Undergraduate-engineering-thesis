# -*- coding: utf-8 -*-
"""
P1 姿态视频链路编排入口 (PipelineRunner)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 03 & 05)
"""

import uuid
import hashlib
from pathlib import Path
from typing import Union, Dict, Any, Optional

from .contracts import (
    RunContext,
    TimeBasis,
    ValidationReport,
)
from .input_probe import InputProbe
from .decode_adapter import DecodeAdapter
from .engine.base import PoseEngine
from .engine.tasks_adapter import MediaPipeTasksPoseEngine
from .quality_gate import QualityGate
from .overlay_renderer import OverlayRenderer
from .ordered_writer import OrderedWriter
from .evidence_writer import EvidenceWriter
from .publisher import AtomicPublisher


class PipelineRunner:
    """P1 单向流水线执行器"""

    def __init__(
        self,
        output_root: Union[str, Path] = "data/S2_derived_features",
        engine: Optional[PoseEngine] = None,
        time_basis: TimeBasis = TimeBasis.DERIVED_CFR_NONRELEASE,
        config_hash: Optional[str] = None,
    ):
        self.output_root = Path(output_root)
        self.engine = engine
        self.time_basis = time_basis
        self.config_hash = config_hash or "CFG-DEFAULT-v1.0"

    def run(
        self,
        video_path: Union[str, Path],
        permit_data: Union[str, Path, Dict[str, Any]],
        extra_manifest: Optional[Dict[str, Any]] = None,
    ) -> ValidationReport:
        # 1. 预检
        manifest = InputProbe.probe(
            video_path=video_path,
            permit_data=permit_data,
            time_basis=self.time_basis,
        )

        run_id = f"run-{uuid.uuid4().hex[:12]}"

        # 确定姿态引擎
        engine = self.engine
        if engine is None:
            engine = MediaPipeTasksPoseEngine()

        engine_id = getattr(engine, "engine_id", engine.__class__.__name__)

        # 构建 RunContext
        ctx = RunContext(
            run_id=run_id,
            input_path=str(Path(video_path).resolve()),
            input_sha256=manifest.video_sha256,
            baseline_id="P0-SQUAT-SIDE-OFFLINE-v1.0",
            processing_permit_id=manifest.permit_id,
            config_hash=hashlib.sha256(self.config_hash.encode("utf-8")).hexdigest()[:16],
            overlay_policy_version="OVERLAY-2D-v1.0",
            engine_id=engine_id,
            package_version="0.1.0",
            time_basis=self.time_basis,
        )

        # 2. 初始化发布器与流式证据写入器
        publisher = AtomicPublisher(self.output_root, ctx)
        work_dir = publisher.get_work_dir()

        evidence_writer = EvidenceWriter(work_dir)
        ordered_writer = OrderedWriter(
            output_video_path=publisher.get_overlay_video_path(),
            width=manifest.width,
            height=manifest.height,
            fps=manifest.fps,
        )

        decoder = DecodeAdapter(
            video_path=video_path,
            run_id=run_id,
            fps=manifest.fps,
            time_basis=self.time_basis,
        )

        quality_gate = QualityGate()
        renderer = OverlayRenderer()

        engine.initialize()

        decoded_count = 0
        inferred_count = 0
        rendered_count = 0

        try:
            for envelope in decoder.iterate_frames():
                decoded_count += 1

                # 推理
                pose_result = engine.infer_frame(envelope.decoded_rgb, envelope.timeline_us)
                inferred_count += 1

                # 门控
                quality = quality_gate.evaluate(pose_result)

                # 渲染
                rendered_bgr = renderer.render(envelope, pose_result, quality)
                rendered_count += 1

                # 严格保序写出
                ordered_writer.write_frame(envelope.frame_index, rendered_bgr)

                # 流式写出证据
                evidence_writer.write_record(envelope, pose_result, quality)

        finally:
            # 无论成功或异常，必须安全释放写出句柄
            ordered_writer.close()
            evidence_writer.close()
            engine.close()

        # 3. 完结校验与原子发布
        report = publisher.validate_and_publish(
            decoded_count=decoded_count,
            inferred_count=inferred_count,
            rendered_count=rendered_count,
            written_count=ordered_writer.written_count,
            sidecar_count=evidence_writer.sidecar_count,
            expected_width=manifest.width,
            expected_height=manifest.height,
            extra_manifest_info=extra_manifest,
        )

        return report
