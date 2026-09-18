# -*- coding: utf-8 -*-
"""
P1 流式结构化证据写入器 (EvidenceWriter)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 04.3, 04.4 & 07.1)
"""

import json
import csv
from pathlib import Path
from typing import Union, TextIO
from .contracts import (
    FrameEnvelope,
    PoseFrameResult,
    FrameQuality,
)


class EvidenceWriter:
    """流式写入 keypoints.jsonl 与 frames.csv，记录全量姿态与帧级审计证据"""

    def __init__(
        self,
        output_dir: Union[str, Path]
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.jsonl_path = self.output_dir / "keypoints.jsonl"
        self.csv_path = self.output_dir / "frames.csv"

        self.jsonl_file: TextIO = open(self.jsonl_path, "w", encoding="utf-8")
        self.csv_file: TextIO = open(self.csv_path, "w", newline="", encoding="utf-8")

        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "frame_index",
            "timeline_us",
            "pose_status",
            "overlay_status",
            "required_side",
            "reason_codes",
            "keypoints_count",
        ])

        self.sidecar_count = 0

    def write_record(
        self,
        envelope: FrameEnvelope,
        pose_result: PoseFrameResult,
        quality: FrameQuality
    ) -> None:
        # 1. 写入 keypoints.jsonl
        record = {
            "run_id": envelope.run_id,
            "frame_index": envelope.frame_index,
            "timeline_us": envelope.timeline_us,
            "source_pts": envelope.source_pts,
            "time_base": envelope.time_base,
            "pose": pose_result.to_dict(),
            "quality": quality.to_dict(),
        }
        self.jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")

        # 2. 写入 frames.csv 摘要
        reasons_str = ";".join([rc.value for rc in quality.reason_codes])
        self.csv_writer.writerow([
            envelope.frame_index,
            envelope.timeline_us,
            pose_result.pose_status.value,
            quality.overlay_status.value,
            quality.required_side.value if quality.required_side else "NONE",
            reasons_str,
            len(pose_result.landmarks_2d),
        ])

        self.sidecar_count += 1

    def flush(self) -> None:
        self.jsonl_file.flush()
        self.csv_file.flush()

    def close(self) -> None:
        self.flush()
        if not self.jsonl_file.closed:
            self.jsonl_file.close()
        if not self.csv_file.closed:
            self.csv_file.close()
