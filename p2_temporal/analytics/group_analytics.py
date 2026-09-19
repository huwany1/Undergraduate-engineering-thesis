# -*- coding: utf-8 -*-
"""
深蹲动作整组多维生物力学分析引擎 (Multi-Repetition Analytics Engine)
依据: 维度三连续动作切片与多维统计规范
职责:
1. 整组动作一致性得分 (Consistency Score) 计算与波动方差量化;
2. 下蹲深度衰减趋势 (Squat Depth Decay) 一阶线性拟合与核心肌群疲劳探测;
3. 动作节奏剖析 (Tempo Analysis)，精准切分离心 (Eccentric)、等长驻留 (Isometric) 与向心 (Concentric) 三大时序阶段;
4. 聚合生成单次切片视图实体 (Single Rep Slices)，支撑前端下钻与局部慢动作回放。
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from ..contracts import RepetitionRecord


@dataclass
class ConsistencyScoreResult:
    """整组动作一致性得分模型"""
    score: float                         # 0.0 ~ 100.0
    grade: str                           # EXCELLENT | GOOD | MODERATE | ERRATIC | SINGLE_REP
    knee_std: float                      # 深度标准差 (deg)
    torso_std: float                     # 前倾标准差 (deg)
    duration_cv: float                   # 持续时长变异系数 (std / mean)
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "grade": self.grade,
            "knee_std": round(self.knee_std, 2),
            "torso_std": round(self.torso_std, 2),
            "duration_cv": round(self.duration_cv, 3),
            "description": self.description,
        }


@dataclass
class DepthDecayResult:
    """下蹲深度衰减趋势与肌群疲劳分析模型"""
    status: str                          # STABLE | FATIGUE_DETECTED | WARM_UP_IMPROVED | SINGLE_REP | NO_DATA
    slope_deg_per_rep: float             # 线性拟合斜率 (度/次，正数表示变浅，负数表示变深)
    total_delta_deg: float               # 终末次膝角 - 首次膝角 (正数表示衰减)
    progression: List[float]             # 历次最小屈曲膝角序列 [k1, k2, ..., kn]
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "slope_deg_per_rep": round(self.slope_deg_per_rep, 2),
            "total_delta_deg": round(self.total_delta_deg, 2),
            "progression": [round(p, 1) for p in self.progression],
            "description": self.description,
        }


@dataclass
class TempoAnalysisResult:
    """动作节奏与肌纤维收缩时序模型"""
    avg_descending_s: float              # 平均离心下蹲时长 (s)
    avg_pause_s: float                   # 平均底部等长驻留时长 (s)
    avg_ascending_s: float               # 平均向心站起时长 (s)
    avg_duration_s: float                # 平均单次完整动作耗时 (s)
    tempo_ratio_str: str                 # 标准代号 (如 "1.4s - 0.2s - 1.3s")
    eccentric_concentric_ratio: float    # 离心/向心时长比
    pacing_feedback: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_descending_s": round(self.avg_descending_s, 2),
            "avg_pause_s": round(self.avg_pause_s, 2),
            "avg_ascending_s": round(self.avg_ascending_s, 2),
            "avg_duration_s": round(self.avg_duration_s, 2),
            "tempo_ratio_str": self.tempo_ratio_str,
            "eccentric_concentric_ratio": round(self.eccentric_concentric_ratio, 2),
            "pacing_feedback": self.pacing_feedback,
        }


@dataclass
class SingleRepSlice:
    """单次深蹲结构化切片与要点质检综合实体"""
    rep_id: int
    is_valid: bool
    status: str                          # COMPLETED | ABORTED | DISRUPTED
    start_frame: int
    bottom_frame: int
    end_frame: int
    start_time_s: float
    bottom_time_s: float
    end_time_s: float
    duration_s: float
    descending_s: float
    pause_s: float
    ascending_s: float
    tempo_str: str
    min_knee_angle: float
    max_torso_lean_angle: float
    overall_status: str                  # ACCEPTABLE | NEEDS_IMPROVEMENT | NOT_EVALUATED
    primary_reason_code: str
    violations: List[Dict[str, Any]] = field(default_factory=list)
    feedback_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rep_id": self.rep_id,
            "is_valid": self.is_valid,
            "status": self.status,
            "start_frame": self.start_frame,
            "bottom_frame": self.bottom_frame,
            "end_frame": self.end_frame,
            "start_time_s": round(self.start_time_s, 3),
            "bottom_time_s": round(self.bottom_time_s, 3),
            "end_time_s": round(self.end_time_s, 3),
            "duration_s": round(self.duration_s, 2),
            "descending_s": round(self.descending_s, 2),
            "pause_s": round(self.pause_s, 2),
            "ascending_s": round(self.ascending_s, 2),
            "tempo_str": self.tempo_str,
            "min_knee_angle": round(self.min_knee_angle, 1),
            "max_torso_lean_angle": round(self.max_torso_lean_angle, 1),
            "overall_status": self.overall_status,
            "primary_reason_code": self.primary_reason_code,
            "violations": self.violations,
            "feedback_text": self.feedback_text,
        }


@dataclass
class MultiRepSummary:
    """整组动作多维宏观统计看板聚合根"""
    total_completed_reps: int
    passed_reps: int
    pass_rate_pct: float
    consistency: ConsistencyScoreResult
    depth_decay: DepthDecayResult
    tempo: TempoAnalysisResult
    slices: List[SingleRepSlice]
    macro_feedback: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_completed_reps": self.total_completed_reps,
            "passed_reps": self.passed_reps,
            "pass_rate_pct": round(self.pass_rate_pct, 1),
            "consistency": self.consistency.to_dict(),
            "depth_decay": self.depth_decay.to_dict(),
            "tempo": self.tempo.to_dict(),
            "slices": [s.to_dict() for s in self.slices],
            "macro_feedback": self.macro_feedback,
        }


class MultiRepAnalyticsEngine:
    """连续动作多维宏观统计与单次切片分析引擎 (纯函数式、低耦合、高内聚)"""

    @classmethod
    def analyze(
        cls,
        records: List[RepetitionRecord],
        assessments: Optional[List[Any]] = None,
    ) -> MultiRepSummary:
        """
        输入 P2 RepetitionRecords 与可选的 P3 RepetitionAssessments，
        执行全套统计数学建模，输出完备的宏观指标与切片实体。
        """
        # 1. 过滤已完成/有效的动作记录
        completed_reps = [r for r in records if r.status == "COMPLETED" or r.is_valid]
        n_reps = len(completed_reps)

        # 映射 assessments (按 rep_id 或顺序对齐)
        ass_map: Dict[int, Any] = {}
        if assessments:
            for idx, a in enumerate(assessments, 1):
                r_id = getattr(a, "rep_id", None)
                if r_id is None and isinstance(a, dict):
                    r_id = a.get("rep_id")
                target_id = r_id if r_id is not None else idx
                ass_map[target_id] = a

        # 2. 构建单次切片实体列表 (SingleRepSlice)
        slices: List[SingleRepSlice] = []
        passed_count = 0

        for r in completed_reps:
            ass = ass_map.get(r.rep_id)
            overall_status = "NEEDS_IMPROVEMENT"
            primary_reason = "NORMAL"
            feedback_text = ""
            violations_data: List[Dict[str, Any]] = []

            if ass:
                if hasattr(ass, "overall_status"):
                    overall_status = ass.overall_status.value if hasattr(ass.overall_status, "value") else str(ass.overall_status)
                elif isinstance(ass, dict):
                    overall_status = str(ass.get("overall_status", "NEEDS_IMPROVEMENT"))

                if hasattr(ass, "primary_reason_code"):
                    primary_reason = ass.primary_reason_code.value if hasattr(ass.primary_reason_code, "value") else str(ass.primary_reason_code)
                elif isinstance(ass, dict):
                    primary_reason = str(ass.get("primary_reason_code", "NORMAL"))

                if hasattr(ass, "summary_feedback"):
                    feedback_text = ass.summary_feedback
                elif isinstance(ass, dict):
                    feedback_text = ass.get("summary_feedback", "")

                raw_viols = getattr(ass, "violations", []) if not isinstance(ass, dict) else ass.get("violations", [])
                for v in raw_viols:
                    if hasattr(v, "to_dict"):
                        violations_data.append(v.to_dict())
                    elif isinstance(v, dict):
                        violations_data.append(v)
            else:
                # 依据膝角/前倾缺省判定
                is_pass = (r.min_knee_angle <= 105.0) and (r.max_torso_lean_angle <= 45.0)
                overall_status = "ACCEPTABLE" if is_pass else "NEEDS_IMPROVEMENT"
                primary_reason = "ACCEPTABLE" if is_pass else ("INSUFFICIENT_DEPTH" if r.min_knee_angle > 105.0 else "EXCESSIVE_TORSO_LEAN")
                feedback_text = "动作及格达标" if is_pass else f"膝角 {r.min_knee_angle:.1f}°，前倾 {r.max_torso_lean_angle:.1f}°"

            if overall_status == "ACCEPTABLE":
                passed_count += 1

            t_start = r.start_timeline_us / 1e6
            t_bottom = r.bottom_timeline_us / 1e6
            t_end = r.end_timeline_us / 1e6
            t_total = max(0.1, r.duration_ms / 1000.0)
            t_desc = max(0.0, r.descending_duration_ms / 1000.0)
            t_asc = max(0.0, r.ascending_duration_ms / 1000.0)
            t_pause = max(0.0, t_total - t_desc - t_asc)

            tempo_str = f"{t_desc:.1f}s - {t_pause:.1f}s - {t_asc:.1f}s"

            slices.append(
                SingleRepSlice(
                    rep_id=r.rep_id,
                    is_valid=r.is_valid,
                    status=r.status,
                    start_frame=r.start_frame,
                    bottom_frame=r.bottom_frame,
                    end_frame=r.end_frame,
                    start_time_s=t_start,
                    bottom_time_s=t_bottom,
                    end_time_s=t_end,
                    duration_s=t_total,
                    descending_s=t_desc,
                    pause_s=t_pause,
                    ascending_s=t_asc,
                    tempo_str=tempo_str,
                    min_knee_angle=r.min_knee_angle,
                    max_torso_lean_angle=r.max_torso_lean_angle,
                    overall_status=overall_status,
                    primary_reason_code=primary_reason,
                    violations=violations_data,
                    feedback_text=feedback_text,
                )
            )

        pass_rate = (passed_count / n_reps * 100.0) if n_reps > 0 else 0.0

        # 3. 计算一致性得分 (Consistency Score)
        consistency_res = cls._calculate_consistency(completed_reps)

        # 4. 计算下蹲深度衰减趋势 (Depth Decay & Fatigue)
        decay_res = cls._calculate_depth_decay(completed_reps)

        # 5. 计算动作节奏分析 (Tempo Analysis)
        tempo_res = cls._calculate_tempo(completed_reps)

        # 6. 生成综合宏观指导文案
        macro_feedback = cls._compose_macro_feedback(n_reps, passed_count, consistency_res, decay_res, tempo_res)

        return MultiRepSummary(
            total_completed_reps=n_reps,
            passed_reps=passed_count,
            pass_rate_pct=pass_rate,
            consistency=consistency_res,
            depth_decay=decay_res,
            tempo=tempo_res,
            slices=slices,
            macro_feedback=macro_feedback,
        )

    @classmethod
    def _calculate_consistency(cls, reps: List[RepetitionRecord]) -> ConsistencyScoreResult:
        """
        计算整组动作一致性得分 (Consistency Score)
        规约:
        - N=0: 返回 0 分，无数据
        - N=1: 单次基准，100.0 分
        - N>=2: 综合膝角标准差 (weight 2.5)、躯干前倾标准差 (weight 1.5) 与时长变异系数 (weight 20.0)
        """
        n = len(reps)
        if n == 0:
            return ConsistencyScoreResult(
                score=0.0,
                grade="NO_DATA",
                knee_std=0.0,
                torso_std=0.0,
                duration_cv=0.0,
                description="未检测到已完成的深蹲动作，暂无一致性评分。",
            )
        if n == 1:
            return ConsistencyScoreResult(
                score=100.0,
                grade="SINGLE_REP",
                knee_std=0.0,
                torso_std=0.0,
                duration_cv=0.0,
                description="单次基准动作，无法计算多轮方差，基准一致性评定为 100 分。",
            )

        knee_angles = [r.min_knee_angle for r in reps]
        torso_angles = [r.max_torso_lean_angle for r in reps]
        durations = [r.duration_ms for r in reps]

        knee_std = cls._std(knee_angles)
        torso_std = cls._std(torso_angles)
        dur_mean = sum(durations) / n
        dur_std = cls._std(durations)
        dur_cv = (dur_std / dur_mean) if dur_mean > 0 else 0.0

        penalty = 2.5 * knee_std + 1.5 * torso_std + 20.0 * dur_cv
        raw_score = 100.0 - penalty
        score = max(0.0, min(100.0, raw_score))

        if score >= 90.0:
            grade = "EXCELLENT"
            desc = f"整组动作一致性极高 (得分 {score:.1f})，下蹲深度离散度仅 ±{knee_std:.1f}°，节奏稳定。"
        elif score >= 80.0:
            grade = "GOOD"
            desc = f"整组动作一致性良好 (得分 {score:.1f})，体态与时长控制平稳 (深度离散度 ±{knee_std:.1f}°)。"
        elif score >= 65.0:
            grade = "MODERATE"
            desc = f"整组动作一致性中等 (得分 {score:.1f})，历次下蹲深度与前倾存在一定波动 (深度标准差 {knee_std:.1f}°)。"
        else:
            grade = "ERRATIC"
            desc = f"整组动作波动较大 (得分 {score:.1f})，历次动作形态差异显著，建议放慢速度强化核心肌肉记忆。"

        return ConsistencyScoreResult(
            score=score,
            grade=grade,
            knee_std=knee_std,
            torso_std=torso_std,
            duration_cv=dur_cv,
            description=desc,
        )

    @classmethod
    def _calculate_depth_decay(cls, reps: List[RepetitionRecord]) -> DepthDecayResult:
        """
        下蹲深度衰减趋势与肌群疲劳分析 (一阶普通最小二乘法 OLS 线性拟合)
        注意：深蹲中波谷膝角数值越小代表下蹲越深；数值变大代表深度衰减/变浅。
        """
        n = len(reps)
        if n == 0:
            return DepthDecayResult(
                status="NO_DATA",
                slope_deg_per_rep=0.0,
                total_delta_deg=0.0,
                progression=[],
                description="无动作数据。",
            )

        progression = [r.min_knee_angle for r in reps]
        if n == 1:
            return DepthDecayResult(
                status="SINGLE_REP",
                slope_deg_per_rep=0.0,
                total_delta_deg=0.0,
                progression=progression,
                description=f"单次深蹲波谷膝角 {progression[0]:.1f}°，宏观衰减趋势需连续完成 ≥2 次深蹲生成。",
            )

        # 线性回归拟合 y = slope * x + intercept, x in [1, 2, ..., n]
        x = list(range(1, n + 1))
        x_mean = sum(x) / n
        y_mean = sum(progression) / n

        numerator = sum((x[i] - x_mean) * (progression[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = (numerator / denominator) if denominator > 0 else 0.0
        total_delta = progression[-1] - progression[0]

        # 判定疲劳状态
        # 膝角增大代表变浅 (slope > 0.6 或 delta >= 3.5)
        if slope > 0.6 or total_delta >= 3.5:
            status = "FATIGUE_DETECTED"
            desc = (
                f"⚠️ 检测到下蹲深度衰减趋势：波谷膝角逐次变浅 (斜率 +{slope:.2f}°/次，总衰减 +{total_delta:.1f}°，"
                f"从 #{1} 次 {progression[0]:.1f}° 变浅至 #{n} 次 {progression[-1]:.1f}°)。"
                "提示大腿股四头肌与臀大肌出现疲劳代偿，建议适度休整或调整组间负荷。"
            )
        elif slope < -0.6 or total_delta <= -3.5:
            status = "WARM_UP_IMPROVED"
            desc = (
                f"下蹲深度逐渐加深 (斜率 {slope:.2f}°/次，深入 {abs(total_delta):.1f}°)，"
                "显示肌肉热身充分、髋膝关节活动度良好。"
            )
        else:
            status = "STABLE"
            desc = f"整组下蹲深度保持极佳稳定 (斜率 {slope:.2f}°/次，波动在安全范围 ±3.0° 内)，核心肌群耐力充沛。"

        return DepthDecayResult(
            status=status,
            slope_deg_per_rep=slope,
            total_delta_deg=total_delta,
            progression=progression,
            description=desc,
        )

    @classmethod
    def _calculate_tempo(cls, reps: List[RepetitionRecord]) -> TempoAnalysisResult:
        """
        动作节奏与肌肉离心/向心收缩配比分析
        标准健美/力量节奏: Eccentric (下蹲离心) -> Pause (波谷等长) -> Concentric (起身向心)
        """
        n = len(reps)
        if n == 0:
            return TempoAnalysisResult(
                avg_descending_s=0.0,
                avg_pause_s=0.0,
                avg_ascending_s=0.0,
                avg_duration_s=0.0,
                tempo_ratio_str="-- - -- - --",
                eccentric_concentric_ratio=1.0,
                pacing_feedback="暂无节奏分析数据。",
            )

        desc_list = [r.descending_duration_ms / 1000.0 for r in reps]
        asc_list = [r.ascending_duration_ms / 1000.0 for r in reps]
        dur_list = [r.duration_ms / 1000.0 for r in reps]
        pause_list = [max(0.0, dur_list[i] - desc_list[i] - asc_list[i]) for i in range(n)]

        avg_desc = sum(desc_list) / n
        avg_asc = sum(asc_list) / n
        avg_pause = sum(pause_list) / n
        avg_dur = sum(dur_list) / n

        ratio_ea = avg_desc / max(0.1, avg_asc)
        tempo_str = f"{avg_desc:.1f}s - {avg_pause:.1f}s - {avg_asc:.1f}s"

        feedback_parts = []
        if avg_desc < 0.8:
            feedback_parts.append("下蹲离心速度偏快 (<0.8s)，缺少离心控制，易产生膝盖冲击借力")
        elif avg_desc >= 1.5:
            feedback_parts.append("离心下蹲充分受控 (≥1.5s)，肌群张力刺激极佳")
        else:
            feedback_parts.append(f"下蹲耗时正常 ({avg_desc:.1f}s)")

        if avg_asc > 2.5:
            feedback_parts.append("起身向心过程阻滞偏慢 (>2.5s)，提示向心爆发力储备不足")

        if ratio_ea >= 1.0:
            feedback_parts.append("离心/向心比例平衡 (离心耗时 ≥ 向心)")
        else:
            feedback_parts.append("离心快于向心，建议有意识地放慢下沉速度 (如下蹲 2 秒、起身 1 秒)")

        pacing_feedback = "；".join(feedback_parts) + f"。整组平均单次耗时 {avg_dur:.2f} 秒。"

        return TempoAnalysisResult(
            avg_descending_s=avg_desc,
            avg_pause_s=avg_pause,
            avg_ascending_s=avg_asc,
            avg_duration_s=avg_dur,
            tempo_ratio_str=tempo_str,
            eccentric_concentric_ratio=ratio_ea,
            pacing_feedback=pacing_feedback,
        )

    @classmethod
    def _compose_macro_feedback(
        cls,
        total_reps: int,
        passed_reps: int,
        consistency: ConsistencyScoreResult,
        decay: DepthDecayResult,
        tempo: TempoAnalysisResult,
    ) -> str:
        """组装整组训练宏观综合训练建议文案"""
        if total_reps == 0:
            return "本次训练未检测到完整深蹲动作闭环。"

        lines = [
            f"整组完成深蹲 {total_reps} 次（达标合格 {passed_reps} 次，达标率 {passed_reps / total_reps * 100.0:.1f}%）。",
            f"一致性评定：{consistency.description}",
            f"耐力与疲劳：{decay.description}",
            f"节奏配比（离心-等长-向心）：{tempo.tempo_ratio_str}。{tempo.pacing_feedback}",
        ]
        return " ".join(lines)

    @staticmethod
    def _std(values: List[float]) -> float:
        """样本标准差 (带零方差与单样本安全保护)"""
        if len(values) <= 1:
            return 0.0
        mean_val = sum(values) / len(values)
        variance = sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(max(0.0, variance))
