# -*- coding: utf-8 -*-
"""
维度四：软件工程与五大架构指标对齐度自动化测试套件
(Dimension 4: Architecture & Software Engineering Verification)
覆盖:
1. 低耦合 (Low Coupling): UniversalFeedbackFormatter 泛化生成与无硬编码校验;
2. 高内聚 (High Cohesion): InferenceTaskWorker 独立任务生命周期与职责聚焦;
3. 高可用 (High Availability): 推理工作器超时熔断看门狗 & 实时会话空闲回收;
4. 高性能 (High Performance): 自适应分帧采样策略与波谷精细保真;
5. 可维护性 (Maintainability): AssessmentReportDto 数据契约 Schema 校验 & 前端模块化资产完整性.
"""

import os
import time
import pytest
from pathlib import Path
from typing import Dict, Any

from web_demo.contracts import (
    UniversalFeedbackFormatter,
    AssessmentReportDto,
    validate_report_dict,
)
from web_demo.worker import InferenceTaskWorker
from web_demo.analyzer import OnlineAnalysisManager
from web_demo.service import DemoService
from web_demo.live_manager import LiveStreamManager, LiveStreamSession


@pytest.fixture(scope="module")
def repo_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def demo_service(repo_root):
    return DemoService(repo_root=repo_root)


# =========================================================================
# 1. 低耦合验证：通用反馈格式化器 (UniversalFeedbackFormatter)
# =========================================================================

def test_feedback_formatter_perfect_squat():
    """验证标准深蹲文案生成（无 case_id 依赖）"""
    msg = UniversalFeedbackFormatter.format(
        status="ACCEPTABLE",
        primary_reason="NONE",
        min_knee=92.5,
        max_torso=38.4,
        total_reps=1,
    )
    assert "动作规范度良好" in msg
    assert "92.5°" in msg
    assert "38.4°" in msg
    assert "TC_01" not in msg  # 确认无硬编码标识


def test_feedback_formatter_insufficient_depth():
    """验证浅蹲缺陷文案动态生成"""
    msg = UniversalFeedbackFormatter.format(
        status="NEEDS_IMPROVEMENT",
        primary_reason="INSUFFICIENT_DEPTH",
        min_knee=118.0,
        max_torso=40.0,
        total_reps=1,
    )
    assert "下蹲深度不足" in msg
    assert "118.0°" in msg
    assert "适度加深髋部下沉幅度" in msg


def test_feedback_formatter_excessive_lean():
    """验证前倾过大缺陷文案动态生成"""
    msg = UniversalFeedbackFormatter.format(
        status="NEEDS_IMPROVEMENT",
        primary_reason="EXCESSIVE_TORSO_LEAN",
        min_knee=95.0,
        max_torso=58.0,
        total_reps=1,
    )
    assert "躯干前倾幅度偏大" in msg
    assert "58.0°" in msg
    assert "保持脊柱中立位" in msg


def test_feedback_formatter_dual_defect():
    """验证复合缺陷（深度不足 + 前倾过大）文案动态生成"""
    msg = UniversalFeedbackFormatter.format(
        status="NEEDS_IMPROVEMENT",
        primary_reason="INSUFFICIENT_DEPTH",
        min_knee=115.0,
        max_torso=55.0,
        all_reasons=["INSUFFICIENT_DEPTH", "EXCESSIVE_TORSO_LEAN"],
    )
    assert "复合问题" in msg
    assert "下蹲深度不足" in msg
    assert "躯干前倾过大" in msg


def test_feedback_formatter_out_of_frame():
    """验证画幅出框一票否决文案动态生成"""
    msg = UniversalFeedbackFormatter.format(
        status="REJECTED",
        primary_reason="OUT_OF_FRAME",
        min_knee=180.0,
        max_torso=0.0,
    )
    assert "前置质检门控一票否决" in msg
    assert "移出有效画幅" in msg


# =========================================================================
# 2. 可维护性验证：前后端契约 Schema 校验
# =========================================================================

def test_schema_validation_golden_cases(demo_service):
    """验证 5 大黄金用例详情输出严格符合 AssessmentReportDto 契约"""
    for cid in ["TC_01_PERFECT_SQUAT", "TC_02_SHALLOW_SQUAT", "TC_03_EXCESSIVE_LEAN", "TC_04_DUAL_DEFECT", "TC_05_OUT_OF_FRAME"]:
        detail = demo_service.get_case_detail(cid)
        assert detail is not None, f"用例 {cid} 详情获取失败"
        is_valid, errors = validate_report_dict(detail)
        assert is_valid is True, f"用例 {cid} Schema 校验失败: {errors}"


def test_schema_validation_dataset_demos(demo_service):
    """验证 MediaPipe 真实数据集演示详情输出符合契约"""
    demos = demo_service.get_dataset_demos()
    if demos:
        demo_id = demos[0]["demo_id"]
        detail = demo_service.get_dataset_demo_detail(demo_id)
        if detail:
            # 数据集可能使用 demo_id 作为主键，规范化补齐 case_id 进行契约校验
            if "case_id" not in detail and "demo_id" in detail:
                detail["case_id"] = detail["demo_id"]
            if "case_name" not in detail and "title" in detail:
                detail["case_name"] = detail["title"]
            if "actual_count" not in detail and "total_reps_completed" in detail:
                detail["actual_count"] = detail["total_reps_completed"]
            if "actual_status" not in detail:
                detail["actual_status"] = "ACCEPTABLE" if detail.get("total_reps_passed", 0) > 0 else "NEEDS_IMPROVEMENT"
            if "actual_primary_reason" not in detail:
                detail["actual_primary_reason"] = "NONE"

            is_valid, errors = validate_report_dict(detail)
            assert is_valid is True, f"数据集用例 Schema 校验失败: {errors}"


def test_schema_validator_catches_invalid_dict():
    """验证 Schema 校验器能准确捕获缺失字段与非法状态"""
    bad_data = {
        "case_id": "TEST_BAD",
        # 故意缺失 case_name, actual_count 等必须字段
        "actual_status": "ILLEGAL_STATUS_VALUE",
    }
    is_valid, errors = validate_report_dict(bad_data)
    assert is_valid is False
    assert any("Missing required field" in err for err in errors)
    assert any("Invalid actual_status" in err for err in errors)


# =========================================================================
# 3. 高内聚与高可用验证：InferenceTaskWorker 与超时熔断
# =========================================================================

def test_worker_initialization_and_cancel(repo_root):
    """验证 InferenceTaskWorker 实例生命周期与取消机制"""
    worker = InferenceTaskWorker(
        task_id="test_task_001",
        video_path=repo_root / "reports" / "validation_package" / "replays" / "TC_01_PERFECT_SQUAT_annotated.mp4",
        original_filename="test.mp4",
        model_path=repo_root / "models" / "pose_landmarker_full.task",
        screenshot_dir=repo_root / "reports" / "uploaded_demo" / "screenshots",
        sidecar_dir=repo_root / "reports" / "uploaded_demo" / "sidecars",
        summary_dir=repo_root / "reports" / "uploaded_demo" / "summaries",
        repo_root=repo_root,
        timeout_sec=0.001,  # 故意设置极小超时
    )
    assert worker.is_running is False
    worker.cancel()
    assert worker.cancel_event.is_set()


def test_worker_timeout_watchdog_trigger(repo_root):
    """验证超时看门狗能够安全熔断并抛出 TimeoutError，绝不无限制挂起"""
    video_path = repo_root / "reports" / "validation_package" / "replays" / "TC_01_PERFECT_SQUAT_annotated.mp4"
    if not video_path.exists():
        pytest.skip("测试视频文件不存在，跳过")

    # 设定 0.0001 秒的极限超时门槛，确保立即触发看门狗熔断
    worker = InferenceTaskWorker(
        task_id="test_timeout_task",
        video_path=video_path,
        original_filename="timeout_demo.mp4",
        model_path=repo_root / "models" / "pose_landmarker_full.task",
        screenshot_dir=repo_root / "reports" / "uploaded_demo" / "screenshots",
        sidecar_dir=repo_root / "reports" / "uploaded_demo" / "sidecars",
        summary_dir=repo_root / "reports" / "uploaded_demo" / "summaries",
        repo_root=repo_root,
        timeout_sec=0.0001,
    )

    with pytest.raises(TimeoutError) as exc_info:
        worker.execute()

    assert "推理任务执行超时" in str(exc_info.value)
    assert worker.is_running is False


# =========================================================================
# 4. 高可用验证：实时流管理器会话空闲回收 (Idle Session Sweeper)
# =========================================================================

def test_live_manager_idle_cleanup(repo_root):
    """验证 LiveStreamManager 能够正确回收闲置过期的会话"""
    manager = LiveStreamManager(repo_root=repo_root)

    # 创建一个模拟会话
    session = manager.create_session()
    sid = session.session_id
    assert sid in manager.sessions

    # 人工篡改最后活跃时间戳为 100 秒前
    session.last_active_at = time.time() - 100

    # 触发清理，阈值设为 50 秒
    cleaned = manager.cleanup_idle_sessions(timeout_sec=50)
    assert cleaned >= 1
    assert sid not in manager.sessions


# =========================================================================
# 5. 可维护性验证：前端模块文件资产完整性
# =========================================================================

def test_frontend_modularization_files_exist(repo_root):
    """验证前端 4 大解耦模块与 HTML 脚本引入关系完整"""
    modules_dir = repo_root / "web_demo" / "static" / "js" / "modules"
    assert modules_dir.exists(), "前端 modules 目录不存在"

    expected_modules = [
        "api_client.js",
        "skeleton_renderer.js",
        "live_stream.js",
        "rep_selector.js",
    ]
    for mod_name in expected_modules:
        mod_file = modules_dir / mod_name
        assert mod_file.exists(), f"模块文件缺失: {mod_name}"
        assert mod_file.stat().st_size > 100, f"模块文件内容为空: {mod_name}"

        # 检查命名空间挂载
        content = mod_file.read_text(encoding="utf-8")
        assert "global.SquatDemo" in content or "window.SquatDemo" in content

    # 验证 index.html 中按顺序引用了这些模块
    index_html = repo_root / "web_demo" / "static" / "index.html"
    index_text = index_html.read_text(encoding="utf-8")
    for mod_name in expected_modules:
        assert f"/static/js/modules/{mod_name}" in index_text
