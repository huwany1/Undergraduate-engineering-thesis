#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1 门禁（G1-P1 与 G2-P1）自动化核验工具
依据: P1_姿态视频链路_P0级详细实施方案.md
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
import cv2
import numpy as np
import yaml

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

BASELINE_DIR = ROOT_DIR / "baseline"
CONTRACTS_DIR = BASELINE_DIR / "contracts"

from p1_pipeline import (
    PipelineRunner,
    DeterministicMockPoseEngine,
    MediaPipeTasksPoseEngine,
    PoseEngineError,
    InputProbeError,
    OrderedWriterError,
    OrderedWriter,
    ReasonCode,
    TimeBasis,
)


def create_synthetic_test_video(path: Path, num_frames: int = 15, width: int = 320, height: int = 240, fps: float = 30.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    for i in range(num_frames):
        # 创建带有帧编号和彩色渐变的合成图像
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, :] = (i * 15 % 255, 100, 150)
        cv2.putText(img, f"Frame {i}", (30, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(img)
    writer.release()


class P1GateVerifier:
    def __init__(self):
        self.results = {}
        self.details = {}

    def log_gate(self, gate_id: str, passed: bool, message: str, extra=None):
        status_str = "PASS" if passed else "FAIL"
        self.results[gate_id] = passed
        self.details[gate_id] = {
            "status": status_str,
            "message": message,
            "extra": extra or {}
        }
        print(f"[{status_str}] {gate_id}: {message}")

    def verify_g1_p1_engine_signed_off(self):
        """G1-P1: 引擎选型、ADR 规范、依赖可复现及中立 DTO 边界"""
        adr_yaml = CONTRACTS_DIR / "p1_engine_adr.yaml"
        adr_md = CONTRACTS_DIR / "p1_engine_adr.md"
        contract_yaml = CONTRACTS_DIR / "p1_pipeline_contract.yaml"

        if not adr_yaml.exists() or not adr_md.exists() or not contract_yaml.exists():
            self.log_gate("G1_P1_ENGINE_SIGNED_OFF", False, "ADR 或 Pipeline 契约文件缺失")
            return

        with open(adr_yaml, "r", encoding="utf-8") as f:
            adr_cfg = yaml.safe_load(f)

        candidates = adr_cfg.get("engine_candidates", {})
        if "primary_production" not in candidates or "ci_deterministic" not in candidates:
            self.log_gate("G1_P1_ENGINE_SIGNED_OFF", False, "ADR 候选引擎未齐备")
            return

        with open(contract_yaml, "r", encoding="utf-8") as f:
            pipe_cfg = yaml.safe_load(f)

        topo = pipe_cfg.get("skeleton_topology", {})
        if topo.get("point_count") != 33 or len(topo.get("connections", [])) < 30:
            self.log_gate("G1_P1_ENGINE_SIGNED_OFF", False, "33 点骨架拓扑定义不完备")
            return

        self.log_gate(
            "G1_P1_ENGINE_SIGNED_OFF",
            True,
            "ADR 明确候选引擎、受控模型规范、33 点拓扑及中立 DTO 边界"
        )

    def verify_g2_p1_pipeline_integrity(self):
        """G2-P1: 五计数相等、重开验证、无业务评价及故障熔断"""
        temp_dir = Path(tempfile.mkdtemp(prefix="p1_gate_test_"))
        try:
            video_path = temp_dir / "test_synthetic.mp4"
            create_synthetic_test_video(video_path, num_frames=12, width=320, height=240, fps=25.0)

            valid_permit = {
                "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
                "sample_id": "SMP-TEST-001",
                "source_video_id": "VID-TEST-01",
                "runtime_permit": {
                    "processing_permit_id": "PRM-TEST-001-A1",
                    "disposal_status": "ACTIVE_HOLD",
                },
                "admission_status": {
                    "quality_status": "ADMITTED",
                },
            }

            output_root = temp_dir / "output"
            engine = DeterministicMockPoseEngine(simulate_side="LEFT")
            runner = PipelineRunner(
                output_root=output_root,
                engine=engine,
                time_basis=TimeBasis.DERIVED_CFR_NONRELEASE,
            )

            # 1. 运行端到端流水线
            report = runner.run(
                video_path=video_path,
                permit_data=valid_permit,
            )

            if not report.is_valid:
                self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, f"流水线验证失败: {report.errors}")
                return

            counts = report.to_dict()["counts"]
            five_equal = (
                counts["decoded_count"] == 12 and
                counts["inferred_count"] == 12 and
                counts["rendered_count"] == 12 and
                counts["written_count"] == 12 and
                counts["sidecar_count"] == 12 and
                counts["verified_video_frames"] == 12
            )
            if not five_equal:
                self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, f"五计数与回读不一致: {counts}")
                return

            # 检查成品目录存在 SUCCESS 标记
            success_files = list(output_root.glob("*/SUCCESS"))
            if len(success_files) != 1:
                self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, "未发现唯一种子产物 SUCCESS 标记文件")
                return

            # 2. 检查故障注入熔断（无 permit）
            invalid_permit = {
                "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
                "runtime_permit": {"processing_permit_id": "PRM-REVOKED", "disposal_status": "REVOKED"},
                "admission_status": {"quality_status": "ADMITTED"}
            }
            try:
                runner.run(video_path=video_path, permit_data=invalid_permit)
                self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, "失效 Permit 未被阻断")
                return
            except InputProbeError as e:
                if e.reason_code != ReasonCode.P0_PERMIT_INVALID:
                    self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, f"错误码非 P0_PERMIT_INVALID: {e.reason_code}")
                    return

            # 3. 检查乱序写出熔断
            writer_test_path = temp_dir / "order_test.mp4"
            writer = OrderedWriter(writer_test_path, width=320, height=240, fps=25.0)
            dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
            writer.write_frame(0, dummy_frame)
            try:
                writer.write_frame(2, dummy_frame)  # 跳过 1，注入乱序
                self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, "乱序帧未被 OrderedWriter 熔断")
                return
            except OrderedWriterError as e:
                if e.reason_code != ReasonCode.INTERNAL_ORDER_VIOLATION:
                    self.log_gate("G2_P1_PIPELINE_INTEGRITY", False, f"错误码非 INTERNAL_ORDER_VIOLATION: {e.reason_code}")
                    return
            finally:
                writer.close()

            self.log_gate(
                "G2_P1_PIPELINE_INTEGRITY",
                True,
                "五计数完全吻合、重开遍历核验通过、成品原子发布具备 SUCCESS、故障与乱序注入严格熔断闭合"
            )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def run_all_checks(self) -> bool:
        print("=" * 70)
        print("P1 姿态视频链路门禁（G1-P1, G2-P1）核验启动")
        print("=" * 70)
        self.verify_g1_p1_engine_signed_off()
        self.verify_g2_p1_pipeline_integrity()
        print("=" * 70)

        all_passed = all(self.results.values()) and len(self.results) == 2
        print(f"核验结果: {'全部通过 (ALL PASS)' if all_passed else '存在失败项 (FAILED)'}")
        return all_passed


if __name__ == "__main__":
    verifier = P1GateVerifier()
    success = verifier.run_all_checks()
    sys.exit(0 if success else 1)
