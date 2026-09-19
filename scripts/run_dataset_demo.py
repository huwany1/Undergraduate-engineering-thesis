# -*- coding: utf-8 -*-
"""
MediaPipe 深蹲数据集端到端流水线演示执行器 (Dataset Demo Runner)
依据: P0 口径、P1 姿态视频链路、P2 时序闭环、P3 规则评估与 Web 演示契约
功能:
1. 自动读取已下载的真实深蹲素材 (data/S1_raw_sensitive/demo_squats/);
2. 调度 MediaPipe Tasks PoseLandmarker 执行高保真逐帧姿态识别 (P1);
3. 调度运动学计算、1€ 自适应滤波、FSM 有限状态机与可靠计数器 (P2);
4. 调度动作深度与躯干前倾规则评估引擎，生成非医疗化解释性反馈 (P3);
5. 渲染具备高质感 HUD 状态看板的标注演示视频、关键帧快照与逐帧遥测数据;
6. 导出可直接供 Web 演示系统分发与答辩呈现的自包含报告与媒体资产。
"""

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import cv2
import numpy as np
import platform

# 控制台编码安全配置
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def safe_rel_path(path: Path) -> str:
    """安全转换为相对于项目根目录的路径，若不在根目录下则回退为绝对路径"""
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")

from p1_pipeline.runner import PipelineRunner
from p1_pipeline.engine.tasks_adapter import MediaPipeTasksPoseEngine
from p1_pipeline.contracts import TimeBasis
from p2_temporal.runner import P2TemporalPipeline
from p2_temporal.contracts import RepetitionRecord
from p2_temporal.analytics import MultiRepAnalyticsEngine
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.contracts import RuleCardConfig, AssessmentStatus

DATASET_DIR = REPO_ROOT / "data" / "S1_raw_sensitive" / "demo_squats"
DEFAULT_MANIFEST = DATASET_DIR / "dataset_manifest.json"
OUTPUT_DIR = REPO_ROOT / "reports" / "dataset_demo"
MODEL_PATH = REPO_ROOT / "models" / "pose_landmarker_full.task"


def create_compatible_video_writer(filepath: Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    """
    创建与现代浏览器 (Chrome/Edge/Safari/Firefox) 及多操作系统完全兼容的视频写入器。
    Windows 首选 Media Foundation H264，Linux/macOS 首选 FFMPEG avc1，降级回退支持 mp4v。
    """
    filepath_str = str(filepath)
    if platform.system() == "Windows":
        try:
            w = cv2.VideoWriter(filepath_str, cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*"H264"), fps, (width, height))
            if w.isOpened():
                return w
        except Exception:
            pass

    try:
        w = cv2.VideoWriter(filepath_str, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"avc1"), fps, (width, height))
        if w.isOpened():
            return w
    except Exception:
        pass

    return cv2.VideoWriter(filepath_str, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))


def render_enhanced_demo_video(
    input_video_path: Path,
    output_video_path: Path,
    p2_records: List[Dict[str, Any]],
    rep_assessments: List[Any],
    case_title: str,
) -> List[Dict[str, Any]]:
    """
    渲染带有专业视觉 HUD (Head-Up Display) 的最终动作回放视频与关键帧捕获
    返回捕获的关键帧列表
    """
    cap = cv2.VideoCapture(str(input_video_path))
    if not cap.isOpened():
        return []

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0 or np.isnan(fps):
        fps = 30.0

    output_video_path.parent.mkdir(parents=True, exist_ok=True)
    writer = create_compatible_video_writer(output_video_path, fps, width, height)

    record_map = {r["frame_index"]: r for r in p2_records}
    keyframes = []

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        rec = record_map.get(frame_idx, {})
        kinematics = rec.get("kinematics", {})
        knee_angle = kinematics.get("filtered_knee_angle", 0.0)
        torso_angle = kinematics.get("filtered_torso_angle", 0.0)
        fsm_state = rec.get("fsm_state", "STANDING")
        event = rec.get("event", "NONE")
        cum_count = rec.get("cumulative_rep_count", 0)

        # 1. 顶部半透明 HUD 背景条
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 85), (20, 20, 24), -1)
        # 底部状态栏背景
        cv2.rectangle(overlay, (0, height - 40), (width, height), (20, 20, 24), -1)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

        # 2. 绘制顶部 HUD 文本
        cv2.putText(
            frame,
            f"MediaPipe Pose Demo | {case_title}",
            (16, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 240, 255),
            2,
            cv2.LINE_AA,
        )

        # 动态指标栏
        knee_color = (0, 255, 120) if knee_angle <= 105.0 else (0, 200, 255)
        torso_color = (0, 255, 120) if torso_angle <= 45.0 else (50, 100, 255)

        hud_text_1 = f"Knee: {knee_angle:.1f}deg (Thresh <= 105)  |  Torso: {torso_angle:.1f}deg (Thresh <= 45)"
        cv2.putText(frame, hud_text_1, (16, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)

        # 状态机与计数徽章
        fsm_color = (0, 255, 200) if fsm_state == "INFLECTION" else (255, 215, 0)
        cv2.putText(
            frame,
            f"FSM State: [{fsm_state}]  |  Completed Reps: {cum_count}",
            (16, 76),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            fsm_color,
            2,
            cv2.LINE_AA,
        )

        # 底部时间轴与帧信息
        time_s = frame_idx / fps
        cv2.putText(
            frame,
            f"Time: {time_s:.2f}s | Frame #{frame_idx} | Pipeline: P1-MediaPipe -> P2-1Euro -> P3-RuleCard",
            (16, height - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (160, 160, 160),
            1,
            cv2.LINE_AA,
        )

        # 关键帧捕获逻辑 (到达谷底或完成动作)
        if event in ("INFLECTION_REACHED", "REP_COMPLETED"):
            screenshot_dir = output_video_path.parent.parent / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            kf_filename = f"{output_video_path.stem}_kf_{frame_idx}_{event}.png"
            kf_path = screenshot_dir / kf_filename
            cv2.imwrite(str(kf_path), frame)
            keyframes.append({
                "event_type": event,
                "frame_index": frame_idx,
                "timeline_us": int(time_s * 1e6),
                "description": f"动作关键事件帧: {event} (膝角: {knee_angle:.1f}°, 前倾: {torso_angle:.1f}°)",
                "file_path": safe_rel_path(kf_path),
            })

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    return keyframes


def run_single_dataset_demo(
    video_path: Path,
    demo_id: str,
    title: str,
    camera_view: str,
    permit_id: str = "PERMIT-DEMO-DATASET-v1.0",
    max_frames: Optional[int] = None,
) -> Dict[str, Any]:
    """对单个视频执行端到端 P1 -> P2 -> P3 流水线分析与资产归档"""
    print(f"\n{'='*72}")
    print(f"  [*] 启动端到端演示流水线: [{demo_id}] {title}")
    print(f"  视频源: {video_path}")
    print(f"  机位模式: {camera_view}")
    print(f"{'='*72}")

    start_time = time.perf_counter()

    # 1. 准备 P1 准入凭证与引擎
    permit_data = {
        "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
        "sample_id": f"SMP-{demo_id}",
        "source_video_id": video_path.name,
        "runtime_permit": {
            "processing_permit_id": permit_id,
            "disposal_status": "ACTIVE_HOLD",
        },
        "admission_status": {
            "quality_status": "ADMITTED",
        },
    }

    engine = MediaPipeTasksPoseEngine(
        model_path=str(MODEL_PATH),
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    s2_work_root = REPO_ROOT / "data" / "S2_derived_features" / "dataset_demo_runs"
    runner = PipelineRunner(output_root=s2_work_root, engine=engine)

    print("  [1/4] 执行 P1 视频解码与 MediaPipe Tasks 逐帧姿态识别...")
    p1_report = runner.run(
        video_path=video_path,
        permit_data=permit_data,
        extra_manifest={"demo_id": demo_id, "camera_view": camera_view},
    )
    print(f"        P1 完成: 成功处理并核验 {p1_report.decoded_count} 帧")

    # 2. 执行 P2 时序滤波与 FSM 状态机
    print("  [2/4] 执行 P2 1€ 自适应滤波、有限状态机与动作分割...")
    cfg_hash = hashlib.sha256(runner.config_hash.encode("utf-8")).hexdigest()[:8]
    published_dir = s2_work_root / f"{video_path.stem}-{cfg_hash}"
    p1_sidecar_path = published_dir / "keypoints.jsonl"
    p2_out_dir = published_dir / "p2_temporal"
    p2_pipeline = P2TemporalPipeline()

    p2_summary = p2_pipeline.run_from_p1_sidecar(
        p1_sidecar_path=str(p1_sidecar_path),
        output_dir=str(p2_out_dir),
        required_side="LEFT",
    )
    print(f"        P2 完成: 识别完成深蹲 {p2_summary['cumulative_reps']} 次 (尝试: {p2_summary['attempted_reps']} 次)")

    # 读取 P2 sidecar 逐帧数据与切片清单
    p2_sidecar_file = p2_out_dir / "p2_sidecar.jsonl"
    p2_records = []
    with open(p2_sidecar_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p2_records.append(json.loads(line.strip()))

    rep_manifest_file = p2_out_dir / "repetitions_manifest.json"
    rep_manifest = {}
    if rep_manifest_file.exists():
        with open(rep_manifest_file, "r", encoding="utf-8") as rf:
            rep_manifest = json.load(rf)

    reps_data = rep_manifest.get("repetitions", [])
    completed_reps = [
        RepetitionRecord(
            rep_id=int(r.get("rep_id", 0)),
            is_valid=bool(r.get("is_valid", True)),
            status=str(r.get("status", "COMPLETED")),
            start_frame=int(r.get("start_frame", 0)),
            bottom_frame=int(r.get("bottom_frame", 0)),
            end_frame=int(r.get("end_frame", 0)),
            start_timeline_us=int(r.get("start_timeline_us", 0)),
            bottom_timeline_us=int(r.get("bottom_timeline_us", 0)),
            end_timeline_us=int(r.get("end_timeline_us", 0)),
            duration_ms=float(r.get("duration_ms", 0.0)),
            descending_duration_ms=float(r.get("descending_duration_ms", 0.0)),
            ascending_duration_ms=float(r.get("ascending_duration_ms", 0.0)),
            min_knee_angle=float(r.get("min_knee_angle", 180.0)),
            max_torso_lean_angle=float(r.get("max_torso_lean_angle", 0.0)),
            reason_codes=r.get("reason_codes", []),
        )
        for r in reps_data
        if r.get("status") == "COMPLETED" or r.get("is_valid", False)
    ]

    # 3. 执行 P3 规则引擎与反馈生成
    print("  [3/4] 执行 P3 规则卡核验 (R-CYCLE-001, R-DEPTH-001, R-LEAN-001) 与非医疗反馈生成...")
    assessment_engine = SquatAssessmentEngine(config=RuleCardConfig())
    assessments = assessment_engine.evaluate_all(completed_reps)

    # 综合研判
    passed_reps = sum(1 for a in assessments if a.overall_status == AssessmentStatus.ACCEPTABLE)
    min_knee_across_reps = min([r.min_knee_angle for r in completed_reps], default=180.0)
    max_torso_across_reps = max([r.max_torso_lean_angle for r in completed_reps], default=0.0)

    print(f"        P3 完成: 评估 {len(assessments)} 次切片 (达标合格: {passed_reps} 次)")
    for idx, ass in enumerate(assessments, 1):
        status_val = ass.overall_status.value if hasattr(ass.overall_status, "value") else str(ass.overall_status)
        reason_val = ass.primary_reason_code.value if hasattr(ass.primary_reason_code, "value") else str(ass.primary_reason_code)
        print(f"        -> Rep #{idx}: 状态 [{status_val}] | 原因: {reason_val}")
        print(f"           建议: {ass.summary_feedback}")

    # 4. 生成带 HUD 的渲染视频回放与关键帧
    print("  [4/4] 导出演示回放视频与关键帧资产至 reports/dataset_demo/ ...")
    replays_dir = OUTPUT_DIR / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    out_video_path = replays_dir / f"{demo_id}_annotated.mp4"

    # 使用 P1 生成的骨骼叠加视频作为底板进行 HUD 增强渲染
    p1_overlay_video = published_dir / "overlay.mp4"
    base_video = p1_overlay_video if p1_overlay_video.exists() else video_path

    keyframes = render_enhanced_demo_video(
        input_video_path=base_video,
        output_video_path=out_video_path,
        p2_records=p2_records,
        rep_assessments=assessments,
        case_title=title,
    )

    # 导出时序 Sidecar 至 reports/dataset_demo/sidecars/
    sidecars_dir = OUTPUT_DIR / "sidecars"
    sidecars_dir.mkdir(parents=True, exist_ok=True)
    out_sidecar_path = sidecars_dir / f"{demo_id}_frames.jsonl"
    with open(out_sidecar_path, "w", encoding="utf-8") as sf:
        for r in p2_records:
            sf.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_time = time.perf_counter() - start_time

    # 计算维度三 Multi-Reps 宏观统计与单次切片
    multi_rep_summary = MultiRepAnalyticsEngine.analyze(completed_reps, assessments).to_dict()

    # 整理结果字典
    result = {
        "demo_id": demo_id,
        "title": title,
        "camera_view": camera_view,
        "input_video": safe_rel_path(video_path),
        "annotated_video": safe_rel_path(out_video_path),
        "has_video": out_video_path.exists(),
        "video_url": f"/api/media/dataset_demo/replays/{out_video_path.name}",
        "total_frames": len(p2_records),
        "total_reps_completed": p2_summary["cumulative_reps"],
        "total_reps_passed": passed_reps,
        "min_knee_angle": round(min_knee_across_reps, 1),
        "max_torso_angle": round(max_torso_across_reps, 1),
        "execution_time_s": round(total_time, 2),
        "assessments": [a.to_dict() for a in assessments],
        "repetitions": [r.to_dict() for r in completed_reps],
        "multi_rep_summary": multi_rep_summary,
        "keyframes": keyframes,
        "telemetry_sidecar": safe_rel_path(out_sidecar_path),
    }

    # 写出单例总结报告
    summary_path = OUTPUT_DIR / f"summary_{demo_id}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"  [SUCCESS] [{demo_id}] 演示流就绪 (总耗时: {total_time:.2f}s, 输出: {out_video_path.name})\n")
    return result


def run_dataset_demo_suite(
    manifest_path: Optional[Path] = None,
    specific_demo_id: Optional[str] = None,
) -> Dict[str, Any]:
    """批量执行演示数据集分析并生成全局清单"""
    m_path = manifest_path or DEFAULT_MANIFEST
    if not m_path.exists():
        print(f"[!] 数据集清单未找到: {m_path}，正在自动尝试下载...")
        from scripts.download_squat_dataset import download_dataset
        download_dataset()

    with open(m_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    items = manifest_data.get("items", [])
    if specific_demo_id:
        items = [it for it in items if it["demo_id"] == specific_demo_id]
        if not items:
            print(f"[ERROR] 未找到 demo_id 为 '{specific_demo_id}' 的素材！")
            sys.exit(1)

    print("=" * 72)
    print("  [*] MediaPipe 深蹲真实数据集端到端流水线演示套件启动")
    print("=" * 72)
    print(f"  素材条目: 共 {len(items)} 项")
    print(f"  交付目录: {OUTPUT_DIR}")
    print("=" * 72)

    demo_results = []
    for item in items:
        v_path = REPO_ROOT / item["relative_path"]
        res = run_single_dataset_demo(
            video_path=v_path,
            demo_id=item["demo_id"],
            title=item["title"],
            camera_view=item["camera_view"],
            permit_id=item.get("permit_id", "PERMIT-DEMO-DATASET-v1.0"),
        )
        demo_results.append(res)

    suite_manifest = {
        "suite_name": "MediaPipe Real Dataset Demonstration Suite",
        "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_demos": len(demo_results),
        "items": demo_results,
    }

    manifest_out = OUTPUT_DIR / "dataset_demo_manifest.json"
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump(suite_manifest, f, indent=2, ensure_ascii=False)

    print("=" * 72)
    print(f"  [SUCCESS] 演示套件全链路运行完成！全局清单已输出至:")
    print(f"  -> {manifest_out}")
    print("=" * 72)

    return suite_manifest


def main():
    parser = argparse.ArgumentParser(description="MediaPipe 深蹲真实数据集端到端演示执行器")
    parser.add_argument("--demo-id", help="仅执行指定的单个素材 (如 DEMO_01_STANDARD_SQUAT)")
    parser.add_argument("--manifest", help="指定外部 dataset_manifest.json 路径")
    args = parser.parse_args()

    m_path = Path(args.manifest) if args.manifest else None
    run_dataset_demo_suite(manifest_path=m_path, specific_demo_id=args.demo_id)


if __name__ == "__main__":
    main()
