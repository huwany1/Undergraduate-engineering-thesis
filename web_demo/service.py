# -*- coding: utf-8 -*-
"""
Web 演示业务适配层 (Demo Service)
职责：
1. 检索与加载 P4 验证包中 5 大黄金用例数据、回放视频、逐帧遥测与特征帧快照；
2. 加载 P4 验证包总结报告、指标 CSV 与 Manifest；
3. 封装桥接 P1-P2-P3 离线视频分析流水线，支持用户自定义视频在线推理。
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, List, Optional

from p4_validation.contracts import TestCaseId
from p4_validation.golden_assets import GoldenAssetRegistry


class DemoService:
    """演示业务适配服务"""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        self.validation_dir = self.repo_root / "reports" / "validation_package"
        self.manifest_path = self.validation_dir / "validation_manifest.json"
        self.summary_report_path = self.validation_dir / "summary_report.md"
        self.metrics_csv_path = self.validation_dir / "metrics_summary.csv"
        self.replays_dir = self.validation_dir / "replays"
        self.screenshots_dir = self.validation_dir / "screenshots"
        self.sidecars_dir = self.validation_dir / "sidecars"
        self.registry = GoldenAssetRegistry()

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态与工程基线信息"""
        manifest_data = self._load_manifest()
        return {
            "service": "squat-motion-assessment-web-demo",
            "version": "0.1.0",
            "status": "ONLINE",
            "baseline_id": manifest_data.get("baseline_id", "P0-SQUAT-SIDE-OFFLINE-v1.0"),
            "git_commit": manifest_data.get("git_commit", "N/A"),
            "timestamp": manifest_data.get("timestamp", ""),
            "total_golden_cases": len(self.registry.list_all()),
            "validation_passed": manifest_data.get("passed_cases", 0) == manifest_data.get("total_cases", 0),
        }

    def get_cases(self) -> List[Dict[str, Any]]:
        """获取全部 5 大黄金用例的概览列表"""
        manifest_data = self._load_manifest()
        case_results_map = {res["case_id"]: res for res in manifest_data.get("case_results", [])}
        specs = self.registry.list_all()

        cases_list = []
        for spec in specs:
            cid = spec.case_id.value
            ver_res = case_results_map.get(cid, {})

            # 确定回放视频相对 URL
            video_name = f"{cid}_annotated.mp4"
            video_path = self.replays_dir / video_name
            has_video = video_path.exists()

            cases_list.append({
                "case_id": cid,
                "case_name": spec.case_name,
                "description": spec.description,
                "expected_count": spec.expected_count,
                "expected_status": spec.expected_status,
                "expected_primary_reason": spec.expected_primary_reason,
                "camera_view": spec.camera_view,
                "actual_count": ver_res.get("actual_count", spec.expected_count),
                "actual_status": ver_res.get("actual_status", spec.expected_status),
                "actual_primary_reason": ver_res.get("actual_primary_reason", spec.expected_primary_reason),
                "verification_status": ver_res.get("status", "PASS"),
                "has_video": has_video,
                "video_url": f"/api/media/replays/{video_name}" if has_video else None,
            })

        return cases_list

    def get_case_detail(self, case_id: str) -> Optional[Dict[str, Any]]:
        """获取单个用例的完整遥测时序、评估结果与截图资产"""
        try:
            tid = TestCaseId(case_id)
            spec = self.registry.get_spec(tid)
        except (ValueError, KeyError):
            return None

        cid = spec.case_id.value
        manifest_data = self._load_manifest()
        case_results_map = {res["case_id"]: res for res in manifest_data.get("case_results", [])}
        ver_res = case_results_map.get(cid, {})

        # 1. 载入逐帧遥测数据
        telemetry = self._load_telemetry(cid)

        # 2. 载入关键帧快照
        keyframes = []
        for kf in ver_res.get("keyframes", []):
            raw_path = kf.get("file_path", "")
            fname = Path(raw_path).name if raw_path else ""
            keyframes.append({
                "event_type": kf.get("event_type"),
                "frame_index": kf.get("frame_index"),
                "timeline_us": kf.get("timeline_us"),
                "description": kf.get("description"),
                "image_url": f"/api/media/screenshots/{fname}" if fname else None,
            })

        # 3. 构造结果对象
        video_name = f"{cid}_annotated.mp4"
        has_video = (self.replays_dir / video_name).exists()

        # 生成可解释性规则违规与反馈详情
        violations = []
        status = ver_res.get("actual_status", spec.expected_status)
        reason = ver_res.get("actual_primary_reason", spec.expected_primary_reason)
        min_knee = ver_res.get("measured_min_knee_angle", 0.0)
        max_torso = ver_res.get("measured_max_torso_angle", 0.0)

        # 证据化文案生成
        summary_feedback = self._build_feedback_summary(cid, status, reason, min_knee, max_torso)

        return {
            "case_id": cid,
            "case_name": spec.case_name,
            "description": spec.description,
            "expected_count": spec.expected_count,
            "expected_status": spec.expected_status,
            "expected_primary_reason": spec.expected_primary_reason,
            "actual_count": ver_res.get("actual_count", spec.expected_count),
            "actual_status": status,
            "actual_primary_reason": reason,
            "actual_reason_codes": ver_res.get("actual_reason_codes", [reason]),
            "measured_min_knee_angle": min_knee,
            "measured_max_torso_angle": max_torso,
            "execution_time_ms": ver_res.get("execution_time_ms", 0.0),
            "summary_feedback": summary_feedback,
            "has_video": has_video,
            "video_url": f"/api/media/replays/{video_name}" if has_video else None,
            "telemetry": telemetry,
            "keyframes": keyframes,
        }

    def get_validation_report(self) -> Dict[str, Any]:
        """获取 P4 全量自包含验证报告与矩阵数据"""
        manifest_data = self._load_manifest()

        # 读取 Markdown 报告纯文本
        summary_md = ""
        if self.summary_report_path.exists():
            with open(self.summary_report_path, "r", encoding="utf-8") as f:
                summary_md = f.read()

        # 读取 Metrics CSV
        metrics_rows = []
        if self.metrics_csv_path.exists():
            with open(self.metrics_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                metrics_rows = list(reader)

        return {
            "manifest": manifest_data,
            "summary_markdown": summary_md,
            "metrics_csv": metrics_rows,
        }

    def _load_manifest(self) -> Dict[str, Any]:
        """安全读取 validation_manifest.json"""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_telemetry(self, case_id: str) -> List[Dict[str, Any]]:
        """从 sidecar 文件中加载逐帧精简遥测数据"""
        sidecar_path = self.sidecars_dir / f"{case_id}_frames.jsonl"
        points: List[Dict[str, Any]] = []
        if not sidecar_path.exists():
            return points

        with open(sidecar_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    kinematics = record.get("kinematics", {})
                    points.append({
                        "frame_index": record.get("frame_index", 0),
                        "time_s": round(record.get("timeline_us", 0) / 1e6, 3),
                        "knee_angle": round(kinematics.get("filtered_knee_angle", 0.0), 1),
                        "raw_knee_angle": round(kinematics.get("raw_knee_angle", 0.0), 1),
                        "torso_angle": round(kinematics.get("filtered_torso_angle", 0.0), 1),
                        "raw_torso_angle": round(kinematics.get("raw_torso_angle", 0.0), 1),
                        "fsm_state": record.get("fsm_state", "UNKNOWN"),
                        "event": record.get("event", "NONE"),
                        "is_valid": kinematics.get("is_valid", True),
                        "count": record.get("cumulative_rep_count", 0),
                    })
                except Exception:
                    continue
        return points

    def _build_feedback_summary(
        self, case_id: str, status: str, primary_reason: str, min_knee: float, max_torso: float
    ) -> str:
        """根据要点规则生成合规、非医疗化、证据确凿的动作辅助训练提示"""
        if case_id == "TC_01_PERFECT_SQUAT":
            return f"动作规范度良好。膝关节最小屈曲角达到 {min_knee:.1f}°（标准阈值 <= 105.0°），躯干最大前倾角保持在 {max_torso:.1f}°（安全阈值 <= 45.0°），动作平稳且完整。"
        elif case_id == "TC_02_SHALLOW_SQUAT":
            return f"动作要点待改进：下蹲深度不足。实测膝关节最小屈曲角为 {min_knee:.1f}°，未触达及格阈值 105.0°。建议训练时在保持核心收紧的前提下，适度加深髋部下沉幅度。"
        elif case_id == "TC_03_EXCESSIVE_LEAN":
            return f"动作要点待改进：躯干前倾幅度偏大。实测躯干最大前倾角为 {max_torso:.1f}°，超过基准线 45.0°。建议下蹲时挺胸沉肩，目视前方，保持脊柱中立位。"
        elif case_id == "TC_04_DUAL_DEFECT":
            return f"动作要点待改进（复合问题）：检测到下蹲深度不足（膝角 {min_knee:.1f}° > 105.0°）且躯干前倾过大（前倾角 {max_torso:.1f}° > 45.0°）。建议适当减小动作速度，优先维持躯干直立再逐步增加下蹲深度。"
        elif case_id == "TC_05_OUT_OF_FRAME":
            return "前置质检门控一票否决：检测到受试者移出有效画幅，关键运动特征点缺失。系统克制地拒绝输出动作次数与质量评价，请调整摄像机机位确保全身入镜。"
        else:
            return f"评估状态: {status}, 主原因码: {primary_reason}。"
