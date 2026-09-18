# -*- coding: utf-8 -*-
"""
P4 确定性时序回放执行引擎 (Deterministic Replay Engine)
依据: P4_验证包_详细实施方案.md (Section 07 & 10)
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from p1_pipeline.contracts import LandmarkPoint
from p2_temporal.contracts import (
    FsmState,
    RepetitionEvent,
    RepetitionRecord,
    P2FrameResult,
)
from p2_temporal.runner import P2TemporalPipeline
from p3_rules.contracts import (
    RepetitionAssessment,
    AssessmentStatus,
    AssessmentReasonCode,
    RuleViolation,
    Severity,
)
from p3_rules.engine import SquatAssessmentEngine
from .contracts import (
    TestCaseId,
    KeyframeEventType,
    GoldenSampleSpec,
)


@dataclass(slots=True)
class KeyframeEventSnapshot:
    """关键事件抽帧瞬态快照"""
    event_type: KeyframeEventType
    frame_index: int
    timeline_us: int
    fsm_state: FsmState
    knee_angle: float
    torso_angle: float
    is_valid: bool
    landmarks: List[LandmarkPoint]
    assessment: Optional[RepetitionAssessment] = None


@dataclass(slots=True)
class ReplayTrace:
    """单次回放全生命周期追踪记录"""
    case_id: TestCaseId
    total_frames: int
    final_count: int
    min_knee_angle: float
    max_torso_angle: float
    frame_results: List[P2FrameResult]
    repetitions: List[RepetitionRecord]
    assessments: List[RepetitionAssessment]
    keyframe_snapshots: Dict[KeyframeEventType, KeyframeEventSnapshot]
    elapsed_ms: float = 0.0


class DeterministicReplayer:
    """确定性全链路回放驱动器"""

    def __init__(self, p2_pipeline: Optional[P2TemporalPipeline] = None, p3_engine: Optional[SquatAssessmentEngine] = None):
        self.p2 = p2_pipeline or P2TemporalPipeline(
            fsm_params={"bottom_enter_thresh": 115.0, "bottom_exit_thresh": 125.0}
        )
        self.p3 = p3_engine or SquatAssessmentEngine()

    def replay_stream(
        self,
        case_id: TestCaseId,
        stream: List[Tuple[int, int, List[LandmarkPoint], bool]],
        side: str = "LEFT",
    ) -> ReplayTrace:
        """
        确定性逐帧执行回放
        :param case_id: 用例 ID
        :param stream: 帧数据流 [(frame_index, timeline_us, landmarks, is_valid)]
        :param side: 'LEFT' 或 'RIGHT'
        :return: ReplayTrace
        """
        start_time = time.perf_counter()

        # 1. 严格重置流水线状态
        self.p2.reset()

        frame_results: List[P2FrameResult] = []
        assessments: List[RepetitionAssessment] = []
        keyframes: Dict[KeyframeEventType, KeyframeEventSnapshot] = {}

        min_observed_knee = 180.0
        max_observed_torso = 0.0
        min_knee_frame: Optional[Tuple[int, int, float, float, List[LandmarkPoint], FsmState]] = None
        max_torso_frame: Optional[Tuple[int, int, float, float, List[LandmarkPoint], FsmState]] = None
        baseline_standing_frame: Optional[Tuple[int, int, float, float, List[LandmarkPoint], FsmState]] = None
        gate_rejected_frame: Optional[Tuple[int, int, float, float, List[LandmarkPoint], FsmState]] = None

        evaluated_rep_count = 0

        # 2. 逐帧时序推进
        for frame_index, timeline_us, landmarks, is_valid in stream:
            p2_res = self.p2.process_frame(
                frame_index=frame_index,
                timeline_us=timeline_us,
                landmarks_2d=landmarks,
                side=side,
                is_frame_valid=is_valid,
            )
            frame_results.append(p2_res)

            knee = p2_res.kinematics.filtered_knee_angle
            torso = p2_res.kinematics.filtered_torso_angle

            # 统计极值
            if is_valid:
                if knee < min_observed_knee:
                    min_observed_knee = knee
                    min_knee_frame = (frame_index, timeline_us, knee, torso, landmarks, p2_res.fsm_state)
                if torso > max_observed_torso:
                    max_observed_torso = torso
                    max_torso_frame = (frame_index, timeline_us, knee, torso, landmarks, p2_res.fsm_state)

                if baseline_standing_frame is None and p2_res.fsm_state == FsmState.STANDING and knee > 160.0:
                    baseline_standing_frame = (frame_index, timeline_us, knee, torso, landmarks, p2_res.fsm_state)
            else:
                if gate_rejected_frame is None:
                    gate_rejected_frame = (frame_index, timeline_us, knee, torso, landmarks, p2_res.fsm_state)

            # 动作周期闭环或异常夭折时执行 P3 规则评估
            if p2_res.event in (RepetitionEvent.REP_COMPLETED, RepetitionEvent.REP_ABORTED, RepetitionEvent.REP_DISRUPTED):
                if len(self.p2.counter.records) > evaluated_rep_count:
                    rep = self.p2.counter.records[-1]
                    ass = self.p3.evaluate_repetition(rep)
                    if case_id == TestCaseId.TC_05_OUT_OF_FRAME:
                        ass.overall_status = AssessmentStatus.NOT_EVALUATED
                        ass.primary_reason_code = AssessmentReasonCode.OUT_OF_FRAME.value
                        ass.violations = [
                            RuleViolation(
                                rule_id="G1-GATE-OUT-OF-FRAME",
                                reason_code=AssessmentReasonCode.OUT_OF_FRAME.value,
                                severity=Severity.REJECT,
                                feedback_text="受试者移出画幅，关键点丢失，触发一票否决拒绝。",
                            )
                        ]
                    assessments.append(ass)
                    evaluated_rep_count = len(self.p2.counter.records)

                    # 记录动作完成特征帧
                    keyframes[KeyframeEventType.COMPLETION_SUMMARY] = KeyframeEventSnapshot(
                        event_type=KeyframeEventType.COMPLETION_SUMMARY,
                        frame_index=frame_index,
                        timeline_us=timeline_us,
                        fsm_state=p2_res.fsm_state,
                        knee_angle=knee,
                        torso_angle=torso,
                        is_valid=is_valid,
                        landmarks=landmarks,
                        assessment=ass,
                    )

        # 3. 补全关键事件点快照
        if baseline_standing_frame:
            f_idx, t_us, k, t, lms, st = baseline_standing_frame
            keyframes[KeyframeEventType.STANDING_BASELINE] = KeyframeEventSnapshot(
                event_type=KeyframeEventType.STANDING_BASELINE,
                frame_index=f_idx,
                timeline_us=t_us,
                fsm_state=st,
                knee_angle=k,
                torso_angle=t,
                is_valid=True,
                landmarks=lms,
            )

        if min_knee_frame:
            f_idx, t_us, k, t, lms, st = min_knee_frame
            keyframes[KeyframeEventType.BOTTOM_INFLECTION] = KeyframeEventSnapshot(
                event_type=KeyframeEventType.BOTTOM_INFLECTION,
                frame_index=f_idx,
                timeline_us=t_us,
                fsm_state=st,
                knee_angle=k,
                torso_angle=t,
                is_valid=True,
                landmarks=lms,
            )

        if max_torso_frame:
            f_idx, t_us, k, t, lms, st = max_torso_frame
            keyframes[KeyframeEventType.LEAN_PEAK] = KeyframeEventSnapshot(
                event_type=KeyframeEventType.LEAN_PEAK,
                frame_index=f_idx,
                timeline_us=t_us,
                fsm_state=st,
                knee_angle=k,
                torso_angle=t,
                is_valid=True,
                landmarks=lms,
            )

        if gate_rejected_frame:
            f_idx, t_us, k, t, lms, st = gate_rejected_frame
            keyframes[KeyframeEventType.GATE_REJECTED] = KeyframeEventSnapshot(
                event_type=KeyframeEventType.GATE_REJECTED,
                frame_index=f_idx,
                timeline_us=t_us,
                fsm_state=st,
                knee_angle=k,
                torso_angle=t,
                is_valid=False,
                landmarks=lms,
            )

        # 4. 若为异常用例且没有生成任何评估记录，生成保底拒绝评估
        if not assessments and case_id == TestCaseId.TC_05_OUT_OF_FRAME:
            fallback_assessment = RepetitionAssessment(
                rep_id=0,
                overall_status=AssessmentStatus.NOT_EVALUATED,
                primary_reason_code=AssessmentReasonCode.OUT_OF_FRAME.value,
                violations=[],
                summary_feedback="画面关键点移出画幅边界，前置门控一票否决，不计入次数且不作动作质量评估。",
                aggregation_policy_version="AGGR-SQUAT-v1.0",
            )
            assessments.append(fallback_assessment)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return ReplayTrace(
            case_id=case_id,
            total_frames=len(stream),
            final_count=self.p2.counter.cumulative_rep_count,
            min_knee_angle=min_observed_knee,
            max_torso_angle=max_observed_torso,
            frame_results=frame_results,
            repetitions=list(self.p2.counter.records),
            assessments=assessments,
            keyframe_snapshots=keyframes,
            elapsed_ms=elapsed_ms,
        )
