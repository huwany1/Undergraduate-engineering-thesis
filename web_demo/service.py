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
from p2_temporal.contracts import RepetitionRecord
from p2_temporal.analytics import MultiRepAnalyticsEngine
from .contracts import UniversalFeedbackFormatter, AssessmentReportDto, validate_report_dict
from .analyzer import OnlineAnalysisManager, AnalysisTaskStatus
from .live_manager import LiveStreamManager
from .llm_coach import DeepSeekCoachService


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
        self.analysis_manager = OnlineAnalysisManager(repo_root=self.repo_root)
        self.live_manager = LiveStreamManager(repo_root=self.repo_root)
        self.llm_coach = DeepSeekCoachService(repo_root=str(self.repo_root))

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
        # 支持用户上传或实时摄像头分析结果
        if case_id.startswith("UPLOAD_") or case_id.startswith("up_") or case_id.startswith("live_"):
            return self.get_uploaded_case_detail(case_id)

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

        all_reasons = ver_res.get("actual_reason_codes", [reason])

        # 证据化文案生成 (通用解耦)
        summary_feedback = self._build_feedback_summary(
            cid, status, reason, min_knee, max_torso, all_reasons=all_reasons
        )

        # 构造维度三 Multi-Reps 宏观统计与单次切片
        reps = []
        if ver_res.get("actual_count", spec.expected_count) > 0 and telemetry:
            valid_pts = [p for p in telemetry if p.get("is_valid", True)]
            start_pt = telemetry[0] if telemetry else {}
            end_pt = telemetry[-1] if telemetry else {}
            min_pt = min(valid_pts, key=lambda p: p.get("knee_angle", 180.0), default=start_pt)
            t_start_us = int(start_pt.get("time_s", 0) * 1e6)
            t_bottom_us = int(min_pt.get("time_s", 0) * 1e6)
            t_end_us = int(end_pt.get("time_s", 0) * 1e6)
            dur_ms = ver_res.get("execution_time_ms", (t_end_us - t_start_us) / 1000.0)
            desc_ms = max(0.0, (t_bottom_us - t_start_us) / 1000.0)
            asc_ms = max(0.0, (t_end_us - t_bottom_us) / 1000.0)
            reps.append(
                RepetitionRecord(
                    rep_id=1,
                    is_valid=True,
                    status="COMPLETED",
                    start_frame=start_pt.get("frame_index", 0),
                    bottom_frame=min_pt.get("frame_index", 0),
                    end_frame=end_pt.get("frame_index", 0),
                    start_timeline_us=t_start_us,
                    bottom_timeline_us=t_bottom_us,
                    end_timeline_us=t_end_us,
                    duration_ms=dur_ms,
                    descending_duration_ms=desc_ms,
                    ascending_duration_ms=asc_ms,
                    min_knee_angle=min_knee,
                    max_torso_lean_angle=max_torso,
                    reason_codes=ver_res.get("actual_reason_codes", [reason]),
                )
            )

        multi_rep_summary = MultiRepAnalyticsEngine.analyze(reps).to_dict()

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
            "repetitions": [r.to_dict() for r in reps],
            "multi_rep_summary": multi_rep_summary,
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
                        "landmarks": record.get("landmarks", []),
                    })
                except Exception:
                    continue
        return points

    def _build_feedback_summary(
        self,
        case_id: str,
        status: str,
        primary_reason: str,
        min_knee: float,
        max_torso: float,
        all_reasons: Optional[List[str]] = None,
    ) -> str:
        """
        根据要点规则生成合规、非医疗化、证据确凿的动作辅助训练提示
        通过 UniversalFeedbackFormatter 动态渲染，彻底消除硬编码 case_id 耦合
        """
        return UniversalFeedbackFormatter.format(
            status=status,
            primary_reason=primary_reason,
            min_knee=min_knee,
            max_torso=max_torso,
            all_reasons=all_reasons,
        )

    def get_dataset_demos(self) -> List[Dict[str, Any]]:
        """获取真实数据集演示用例列表"""
        demo_manifest_path = self.repo_root / "reports" / "dataset_demo" / "dataset_demo_manifest.json"
        if not demo_manifest_path.exists():
            return []
        try:
            with open(demo_manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("items", [])
        except Exception:
            return []

    def get_dataset_demo_detail(self, demo_id: str) -> Optional[Dict[str, Any]]:
        """获取单个真实数据集用例的详细时序、评估反馈与关键帧截图"""
        summary_file = self.repo_root / "reports" / "dataset_demo" / f"summary_{demo_id}.json"
        if not summary_file.exists():
            return None
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 读取逐帧时序 Sidecar
            sidecar_file = self.repo_root / "reports" / "dataset_demo" / "sidecars" / f"{demo_id}_frames.jsonl"
            telemetry = []
            if sidecar_file.exists():
                with open(sidecar_file, "r", encoding="utf-8") as sf:
                    for line in sf:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        kine = rec.get("kinematics", {})
                        telemetry.append({
                            "frame_index": rec.get("frame_index", 0),
                            "time_s": round(rec.get("timeline_us", 0) / 1e6, 3),
                            "knee_angle": round(kine.get("filtered_knee_angle", 0.0), 1),
                            "raw_knee_angle": round(kine.get("raw_knee_angle", 0.0), 1),
                            "torso_angle": round(kine.get("filtered_torso_angle", 0.0), 1),
                            "raw_torso_angle": round(kine.get("raw_torso_angle", 0.0), 1),
                            "fsm_state": rec.get("fsm_state", "UNKNOWN"),
                            "event": rec.get("event", "NONE"),
                            "is_valid": kine.get("is_valid", True),
                            "count": rec.get("cumulative_rep_count", 0),
                            "landmarks": rec.get("landmarks", []),
                        })

            data["telemetry"] = telemetry

            # 规范化关键帧 image_url
            for kf in data.get("keyframes", []):
                raw_path = kf.get("file_path", "")
                fname = Path(raw_path).name if raw_path else ""
                kf["image_url"] = f"/api/media/dataset_demo/screenshots/{fname}" if fname else None

            # 规范化对齐 AssessmentReportDto 标准字段 (实现多源用例同构与低耦合)
            if "case_id" not in data and "demo_id" in data:
                data["case_id"] = data["demo_id"]
            if "case_name" not in data and "title" in data:
                data["case_name"] = data["title"]
            if "actual_count" not in data and "total_reps_completed" in data:
                data["actual_count"] = data["total_reps_completed"]
            if "actual_status" not in data:
                data["actual_status"] = "ACCEPTABLE" if data.get("total_reps_passed", 0) > 0 else "NEEDS_IMPROVEMENT"
            if "actual_primary_reason" not in data:
                data["actual_primary_reason"] = "NONE"
            if "actual_reason_codes" not in data:
                data["actual_reason_codes"] = [data["actual_primary_reason"]]
            if "measured_min_knee_angle" not in data:
                data["measured_min_knee_angle"] = data.get("min_knee_angle", 0.0)
            if "measured_max_torso_angle" not in data:
                data["measured_max_torso_angle"] = data.get("max_torso_angle", 0.0)
            if "has_video" not in data:
                data["has_video"] = bool(data.get("video_url"))

            # 构造综合提示文案
            if not data.get("summary_feedback"):
                if data.get("assessments"):
                    ass_texts = [
                        f"Rep #{idx}: {a.get('summary_feedback', '')}"
                        for idx, a in enumerate(data["assessments"], 1)
                    ]
                    data["summary_feedback"] = " | ".join(ass_texts)
                else:
                    data["summary_feedback"] = f"动作评估就绪，共识别完成深蹲 {data.get('total_reps_completed', 0)} 次。"

            # 确保包含 Multi-Reps 宏观统计与单次切片
            if "multi_rep_summary" not in data or not data.get("multi_rep_summary"):
                reps_list = [
                    RepetitionRecord(
                        rep_id=r.get("rep_id", 1),
                        is_valid=r.get("is_valid", True),
                        status=r.get("status", "COMPLETED"),
                        start_frame=r.get("start_frame", 0),
                        bottom_frame=r.get("bottom_frame", 0),
                        end_frame=r.get("end_frame", 0),
                        start_timeline_us=r.get("start_timeline_us", 0),
                        bottom_timeline_us=r.get("bottom_timeline_us", 0),
                        end_timeline_us=r.get("end_timeline_us", 0),
                        duration_ms=r.get("duration_ms", 0.0),
                        descending_duration_ms=r.get("descending_duration_ms", 0.0),
                        ascending_duration_ms=r.get("ascending_duration_ms", 0.0),
                        min_knee_angle=r.get("min_knee_angle", 180.0),
                        max_torso_lean_angle=r.get("max_torso_lean_angle", 0.0),
                        reason_codes=r.get("reason_codes", []),
                    )
                    for r in data.get("repetitions", [])
                ]
                data["multi_rep_summary"] = MultiRepAnalyticsEngine.analyze(
                    reps_list, data.get("assessments", [])
                ).to_dict()

            return data
        except Exception:
            return None

    def submit_video_analysis(self, file_bytes: bytes, filename: str) -> str:
        """提交视频进行异步在线分析"""
        return self.analysis_manager.submit_video(file_bytes, filename)

    def get_analysis_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取在线分析任务当前进度与状态"""
        task = self.analysis_manager.get_task(task_id)
        if not task:
            # 兼容从持久化磁盘载入历史记录
            clean_tid = task_id.replace("UPLOAD_", "").replace("up_", "")
            candidate_file = self.analysis_manager.summary_dir / f"up_{clean_tid}_summary.json"
            if candidate_file.exists():
                try:
                    with open(candidate_file, "r", encoding="utf-8") as f:
                        res = json.load(f)
                    return {
                        "task_id": f"up_{clean_tid}",
                        "status": "COMPLETED",
                        "progress": 100,
                        "stage_name": "已加载历史分析结果",
                        "result": res,
                    }
                except Exception:
                    pass
            return None

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "stage_name": task.stage_name,
            "error": task.error,
            "result": task.result,
        }

    def list_uploaded_cases(self) -> List[Dict[str, Any]]:
        """列出全部已完成的自定义分析用例"""
        return self.analysis_manager.list_completed_sessions()

    def get_uploaded_case_detail(self, case_id: str) -> Optional[Dict[str, Any]]:
        """获取单个自定义分析的详细结果"""
        task_id = case_id
        if task_id.startswith("UPLOAD_"):
            task_id = task_id[len("UPLOAD_"):]

        res = None
        task = self.analysis_manager.get_task(task_id)
        if task and task.result:
            res = task.result
        else:
            # 回退检查持久化摘要 JSON
            summary_file = self.analysis_manager.summary_dir / f"{task_id}_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        res = json.load(f)
                except Exception:
                    pass

        if res and ("multi_rep_summary" not in res or not res.get("multi_rep_summary")):
            reps_list = [
                RepetitionRecord(
                    rep_id=r.get("rep_id", 1),
                    is_valid=r.get("is_valid", True),
                    status=r.get("status", "COMPLETED"),
                    start_frame=r.get("start_frame", 0),
                    bottom_frame=r.get("bottom_frame", 0),
                    end_frame=r.get("end_frame", 0),
                    start_timeline_us=r.get("start_timeline_us", 0),
                    bottom_timeline_us=r.get("bottom_timeline_us", 0),
                    end_timeline_us=r.get("end_timeline_us", 0),
                    duration_ms=r.get("duration_ms", 0.0),
                    descending_duration_ms=r.get("descending_duration_ms", 0.0),
                    ascending_duration_ms=r.get("ascending_duration_ms", 0.0),
                    min_knee_angle=r.get("min_knee_angle", 180.0),
                    max_torso_lean_angle=r.get("max_torso_lean_angle", 0.0),
                    reason_codes=r.get("reason_codes", []),
                )
                for r in res.get("repetitions", [])
            ]
            res["multi_rep_summary"] = MultiRepAnalyticsEngine.analyze(
                reps_list, res.get("assessments", [])
            ).to_dict()

        return res

    # ---------------- 实时摄像头服务接口 (Live Webcam Stream) ----------------

    def start_live_session(self) -> Dict[str, Any]:
        """开启并初始化一个全新的摄像头实时流会话"""
        session = self.live_manager.create_session()
        return {
            "session_id": session.session_id,
            "status": "RUNNING",
            "message": "实时摄像头推理引擎已就绪",
        }

    def process_live_frame(
        self,
        session_id: str,
        image_bytes: bytes,
        client_timestamp_ms: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """向指定会话推送单帧图像并获取实时骨骼与运动学评估结果"""
        session = self.live_manager.get_session(session_id)
        if not session:
            return None
        return session.process_frame(image_bytes, client_timestamp_ms)

    def stop_live_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """结束摄像头实时会话并获取动作质量汇总"""
        return self.live_manager.close_session(session_id)

    def get_live_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """查询指定实时会话状态"""
        session = self.live_manager.get_session(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "is_active": session.is_active,
            "frame_index": session.frame_index,
            "total_reps": len(session.completed_reps_assessment),
        }

    def cleanup_idle_live_sessions(self, timeout_sec: Optional[float] = None) -> int:
        """显式清理闲置超时的实时会话 (高可用运维)"""
        return self.live_manager.cleanup_idle_sessions(timeout_sec=timeout_sec)

    # ---------------------------------------------------------------------
    # 大模型 (LLM) 智能教练与连通性接口 (维度五)
    # ---------------------------------------------------------------------

    def get_llm_config(self) -> Dict[str, Any]:
        """获取当前大模型配置摘要（脱敏显示）"""
        return self.llm_coach.get_config_summary()

    def update_llm_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新大模型 API 密钥与端点设置"""
        return self.llm_coach.update_config(api_key=api_key, base_url=base_url, model=model)

    def test_llm_connection(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """测试 DeepSeek API 连通性与实测 RTT 往返延迟"""
        return self.llm_coach.test_connection(api_key=api_key, base_url=base_url, model=model)

    def generate_llm_feedback(
        self,
        case_id: Optional[str] = None,
        report_data: Optional[Dict[str, Any]] = None,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """为指定用例或报告数据生成 AI 教练深度点评"""
        target_report = report_data
        if not target_report and case_id:
            target_report = self.get_case_detail(case_id)

        if not target_report:
            target_report = {
                "case_name": case_id or "未指定用例",
                "actual_count": 0,
                "actual_status": "ACCEPTABLE",
                "actual_primary_reason": "R-PASS",
            }

        return self.llm_coach.generate_coach_advice(target_report, prompt_override=prompt_override)

    def chat_with_llm(
        self,
        messages: List[Dict[str, str]],
        case_id: Optional[str] = None,
        report_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """与 AI 健身教练围绕当前动作数据进行多轮互动答疑"""
        target_report = report_data
        if not target_report and case_id:
            target_report = self.get_case_detail(case_id)

        return self.llm_coach.chat_with_coach(messages, report_data=target_report)



