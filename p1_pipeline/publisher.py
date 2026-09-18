# -*- coding: utf-8 -*-
"""
P1 原子发布器 (AtomicPublisher)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 07.2)
"""

import json
import shutil
from pathlib import Path
from typing import Union, Dict, Any, Optional
import cv2

from .contracts import (
    RunContext,
    ValidationReport,
    ReasonCode,
)


class PublishError(Exception):
    def __init__(self, reason_code: ReasonCode, message: str):
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class AtomicPublisher:
    """管理临时运行目录、执行严格的完结回读校验并实施同卷原子发布"""

    def __init__(
        self,
        approved_output_root: Union[str, Path],
        run_context: RunContext,
    ):
        self.output_root = Path(approved_output_root)
        self.ctx = run_context

        # 工作区：.runs/<run_id>.partial/
        self.work_dir = self.output_root / ".runs" / f"{self.ctx.run_id}.partial"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # 目标成品目录：<approved-output-root>/<input-stem>-<config-hash>/
        input_stem = Path(self.ctx.input_path).stem
        self.target_dir = self.output_root / f"{input_stem}-{self.ctx.config_hash[:8]}"

    def get_overlay_video_path(self) -> Path:
        return self.work_dir / "overlay.mp4"

    def get_work_dir(self) -> Path:
        return self.work_dir

    def validate_and_publish(
        self,
        decoded_count: int,
        inferred_count: int,
        rendered_count: int,
        written_count: int,
        sidecar_count: int,
        expected_width: int,
        expected_height: int,
        extra_manifest_info: Optional[Dict[str, Any]] = None,
    ) -> ValidationReport:
        """执行重开回读核验，通过后原子发布成品"""
        errors = []
        checks = {}
        overlay_path = self.get_overlay_video_path()

        # 1. 检查临时成品是否存在
        if not overlay_path.exists():
            errors.append(f"视频文件不存在: {overlay_path}")
            checks["video_file_exists"] = False
        else:
            checks["video_file_exists"] = True

        # 2. 重开视频文件，逐帧遍历解码核验帧数与尺寸
        verified_video_frames = 0
        if checks.get("video_file_exists"):
            cap = cv2.VideoCapture(str(overlay_path))
            if not cap.isOpened():
                errors.append("重开视频失败：OpenCV 无法解码 overlay.mp4")
                checks["video_reopen_success"] = False
            else:
                checks["video_reopen_success"] = True
                try:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    if w != expected_width or h != expected_height:
                        errors.append(f"视频尺寸不匹配: 期望 {expected_width}x{expected_height}, 实际 {w}x{h}")
                        checks["video_dimensions_match"] = False
                    else:
                        checks["video_dimensions_match"] = True

                    while True:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break
                        verified_video_frames += 1
                finally:
                    cap.release()

        # 3. 严格的五计数相等核验
        counts_match = (
            decoded_count == inferred_count == rendered_count ==
            written_count == sidecar_count == verified_video_frames
        )
        checks["five_counts_equal"] = counts_match
        if not counts_match:
            errors.append(
                f"五计数不相等: decoded={decoded_count}, inferred={inferred_count}, "
                f"rendered={rendered_count}, written={written_count}, "
                f"sidecar={sidecar_count}, verified_frames={verified_video_frames}"
            )

        # 4. 检查 sidecar 文件完整性
        jsonl_path = self.work_dir / "keypoints.jsonl"
        csv_path = self.work_dir / "frames.csv"
        checks["keypoints_jsonl_exists"] = jsonl_path.exists()
        checks["frames_csv_exists"] = csv_path.exists()
        if not jsonl_path.exists() or not csv_path.exists():
            errors.append("Sidecar 证据文件缺失 (keypoints.jsonl 或 frames.csv)")

        is_valid = (len(errors) == 0)

        report = ValidationReport(
            is_valid=is_valid,
            decoded_count=decoded_count,
            inferred_count=inferred_count,
            rendered_count=rendered_count,
            written_count=written_count,
            sidecar_count=sidecar_count,
            verified_video_frames=verified_video_frames,
            checks=checks,
            errors=errors,
        )

        if not is_valid:
            # 校验失败：写入 failure_manifest，保留 partial 用于事后诊断，绝不发布 SUCCESS
            fail_manifest_path = self.work_dir / "failure_manifest.json"
            with open(fail_manifest_path, "w", encoding="utf-8") as f:
                json.dump({
                    "run_id": self.ctx.run_id,
                    "status": "FAILED",
                    "validation_report": report.to_dict(),
                }, f, indent=2, ensure_ascii=False)
            raise PublishError(
                ReasonCode.OUTPUT_WRITE_FAILED,
                f"完结校验失败: {'; '.join(errors)}"
            )

        # 5. 生成 validation.json
        validation_file = self.work_dir / "validation.json"
        with open(validation_file, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # 6. 生成 manifest.json
        manifest_data = {
            "run_id": self.ctx.run_id,
            "baseline_id": self.ctx.baseline_id,
            "processing_permit_id": self.ctx.processing_permit_id,
            "input_path": self.ctx.input_path,
            "input_sha256": self.ctx.input_sha256,
            "config_hash": self.ctx.config_hash,
            "overlay_policy_version": self.ctx.overlay_policy_version,
            "engine_id": self.ctx.engine_id,
            "package_version": self.ctx.package_version,
            "model_sha256": self.ctx.model_sha256,
            "time_basis": self.ctx.time_basis.value,
            "counts": report.to_dict()["counts"],
            "extra_info": extra_manifest_info or {},
        }
        manifest_file = self.work_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        # 7. 原子发布重命名 (同卷原子移动)
        if self.target_dir.exists():
            shutil.rmtree(self.target_dir)

        self.work_dir.rename(self.target_dir)

        # 8. 生成最后的 SUCCESS 标记凭据
        success_marker = self.target_dir / "SUCCESS"
        success_marker.write_text("P1_VERIFIED_SUCCESS\n", encoding="utf-8")

        return report
