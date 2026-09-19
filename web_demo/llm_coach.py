# -*- coding: utf-8 -*-
"""
DeepSeek 大模型（LLM）健身教练服务适配器 (DeepSeek Coach Module)
职责:
1. 支持配置 DeepSeek API Key、Base URL 与 Model，支持动态修改与连通性测试;
2. 生物力学事实锚定 (Grounded Prompt)：将底层视觉算法测得的角度、原因码与节奏精准注入提示词;
3. 严格遵循非医疗化与防幻觉约束，输出有温度、专业的运动指导语;
4. 具备优雅降级 (Graceful Fallback)：无 API Key、网络断开或超时熔断时，无缝切换至本地专家规则模板.
"""

import os
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple


def load_dotenv_fallback(repo_root: Optional[str] = None) -> Optional[str]:
    """从项目根目录 .env 文件安全解析 DEEPSEEK_API_KEY（标准库无第三方依赖）"""
    candidates = []
    if repo_root:
        candidates.append(Path(repo_root) / ".env")
    candidates.append(Path(__file__).resolve().parent.parent / ".env")
    candidates.append(Path.cwd() / ".env")

    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k == "DEEPSEEK_API_KEY" and v:
                            os.environ["DEEPSEEK_API_KEY"] = v
                            return v
            except Exception:
                pass
    return None


@dataclass
class LLMConfig:
    """大模型接口配置契约"""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout_seconds: float = 10.0

    def get_masked_key(self) -> str:
        """脱敏展示 API Key"""
        if not self.api_key:
            return ""
        key = self.api_key.strip()
        if len(key) <= 8:
            return "sk-****"
        return f"{key[:3]}****{key[-4:]}"

    def get_completions_endpoint(self) -> str:
        """格式化标准的 OpenAI 兼容 completions 接口 URL"""
        base = self.base_url.strip().rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"


class GroundedPromptBuilder:
    """生物力学事实提示词构建器 (Grounded Prompt Builder)"""

    SYSTEM_ROLE = (
        "你是一位拥有国家认证资质的高级运动体能与动作康复教练。你的任务是基于计算机视觉与生物力学系统提取的"
        "客观动作事实，为训练者提供专业、温和且具有指导性的反馈。\n"
        "【严格遵循以下原则】\n"
        "1. 事实锚定：必须且仅能基于下方提供的实测客观数据（深度膝角、躯干前倾、完成次数、节奏等）进行点评，绝不得凭空臆造或篡改数据；\n"
        "2. 非医疗化：严格禁止使用任何临床医疗、病理诊断词汇（如病变、治疗、半月板损伤、韧带撕裂、骨骼畸形等），仅做健身姿态指导；\n"
        "3. 鼓励为主：先肯定完成度与良好指标，再指出具体待提升点；\n"
        "4. 具体动作感知指导：提供 1~2 点简单、易执行的核心或站位建议（例如收紧核心腹压、视线平视斜前方、想象全脚掌抓地等）；\n"
        "5. 篇幅精炼：总字数控制在 100~160 字之间，分段清晰，适合快速阅读。"
    )

    @staticmethod
    def build_report_context(report_data: Dict[str, Any]) -> str:
        """将报告数据序列化为高保真事实文本"""
        case_name = report_data.get("case_name") or report_data.get("filename") or "深蹲动作训练"
        reps_count = report_data.get("actual_count", report_data.get("reps_count", 0))
        status = report_data.get("actual_status", report_data.get("eval_status", "ACCEPTABLE"))

        min_knee = report_data.get("min_knee_angle", report_data.get("knee_min_angle", None))
        max_torso = report_data.get("max_torso_lean", report_data.get("torso_max_angle", None))
        duration_ms = report_data.get("duration_ms", report_data.get("exec_time_ms", None))
        primary_reason = report_data.get("actual_primary_reason", report_data.get("primary_reason", "R-PASS"))

        # 连续动作宏观指标 (若存在)
        group_analytics = report_data.get("group_analytics", {})
        consistency_score = group_analytics.get("consistency_score")
        fatigue_status = group_analytics.get("fatigue_status")
        cadence_code = group_analytics.get("cadence_tempo_code")

        context_lines = [
            f"【动作事实 Context】",
            f"- 训练项目: 深蹲 (Squat) - {case_name}",
            f"- 完成总次数: {reps_count} 次",
            f"- 综合评估结论: {status}",
        ]

        if min_knee is not None:
            depth_eval = "达标 (≤105°)" if min_knee <= 105.0 else "深度不足 (>105°)"
            context_lines.append(f"- 膝关节极限屈曲角: {min_knee:.1f}° ({depth_eval})")

        if max_torso is not None:
            lean_eval = "正常稳定 (≤45°)" if max_torso <= 45.0 else "前倾过大 (>45°)"
            context_lines.append(f"- 躯干最大前倾角: {max_torso:.1f}° ({lean_eval})")

        if duration_ms is not None:
            context_lines.append(f"- 动作周期耗时: {duration_ms / 1000.0:.2f} 秒")

        context_lines.append(f"- 规则触发原因码: {primary_reason}")

        if consistency_score is not None:
            context_lines.append(f"- 整组动作一致性得分: {consistency_score} 分")
        if fatigue_status:
            context_lines.append(f"- 核心肌群疲劳识别: {fatigue_status}")
        if cadence_code:
            context_lines.append(f"- 离心/停顿/向心收缩节奏配比: {cadence_code}")

        return "\n".join(context_lines)


class DeepSeekClient:
    """DeepSeek API 传输客户端 (基于原生 urllib，零三方依赖)"""

    @classmethod
    def call_api(
        cls,
        config: LLMConfig,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> Tuple[bool, str, float, int]:
        """
        调用 DeepSeek Chat Completion API
        返回: (success: bool, content_or_error: str, latency_ms: float, status_code: int)
        """
        if not config.api_key:
            return False, "未配置 DeepSeek API Key，请在设置中填入有效的 API 密钥", 0.0, 400

        endpoint = config.get_completions_endpoint()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key.strip()}",
            "User-Agent": "SquatMotionAssessmentDemo/0.1.0",
        }

        payload = {
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
                latency_ms = (time.time() - start_time) * 1000.0
                status_code = response.status
                body = response.read().decode("utf-8")
                res_json = json.loads(body)

                choices = res_json.get("choices", [])
                if choices and "message" in choices[0]:
                    reply_text = choices[0]["message"].get("content", "").strip()
                    return True, reply_text, round(latency_ms, 1), status_code
                return False, "API 响应格式异常，未找到有效文本回复", round(latency_ms, 1), status_code

        except urllib.error.HTTPError as he:
            latency_ms = (time.time() - start_time) * 1000.0
            error_body = ""
            try:
                error_body = he.read().decode("utf-8")
                err_json = json.loads(error_body)
                msg = err_json.get("error", {}).get("message", error_body)
            except Exception:
                msg = error_body or str(he)
            return False, f"DeepSeek API 请求失败 (HTTP {he.code}): {msg}", round(latency_ms, 1), he.code

        except urllib.error.URLError as ue:
            latency_ms = (time.time() - start_time) * 1000.0
            return False, f"网络连接不可达或地址解析失败: {str(ue.reason)}", round(latency_ms, 1), 0

        except Exception as ex:
            latency_ms = (time.time() - start_time) * 1000.0
            return False, f"调用过程中发生未知错误: {str(ex)}", round(latency_ms, 1), 500


class DeepSeekCoachService:
    """
    AI 智能健身教练高层管理服务
    支持配置注入、连通性探测、深度点评生成、多轮对话与优雅离线兜底
    """

    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root
        # 默认优先从环境变量读取，若无则尝试从本地 .env 文件安全载入
        env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not env_key:
            env_key = load_dotenv_fallback(repo_root) or ""
        self.config = LLMConfig(api_key=env_key)

    def get_config_summary(self) -> Dict[str, Any]:
        """获取当前配置状态（脱敏）"""
        return {
            "has_key": bool(self.config.api_key),
            "masked_key": self.config.get_masked_key(),
            "base_url": self.config.base_url,
            "model": self.config.model,
            "timeout_seconds": self.config.timeout_seconds,
        }

    def update_config(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        """更新配置"""
        if api_key is not None:
            self.config.api_key = api_key.strip()
        if base_url is not None and base_url.strip():
            self.config.base_url = base_url.strip()
        if model is not None and model.strip():
            self.config.model = model.strip()
        return self.get_config_summary()

    def test_connection(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        连通性测试 (极速 Ping)
        支持传入临时凭据测试，测试通过不强制覆盖当前凭据，由用户决定保存
        """
        temp_config = LLMConfig(
            api_key=(api_key if api_key is not None else self.config.api_key).strip(),
            base_url=(base_url if base_url is not None else self.config.base_url).strip(),
            model=(model if model is not None else self.config.model).strip(),
            timeout_seconds=8.0,
        )

        test_messages = [
            {"role": "system", "content": "You are a health check agent. Respond with 'PONG' only."},
            {"role": "user", "content": "PING"},
        ]

        success, content, latency_ms, status_code = DeepSeekClient.call_api(
            temp_config, test_messages, max_tokens=10
        )

        if success:
            return {
                "success": True,
                "latency_ms": latency_ms,
                "model": temp_config.model,
                "message": f"DeepSeek API 连通性测试成功！响应往返延迟: {latency_ms:.1f}ms",
            }
        else:
            return {
                "success": False,
                "latency_ms": latency_ms,
                "status_code": status_code,
                "error": content,
                "message": f"连接失败: {content}",
            }

    def generate_coach_advice(self, report_data: Dict[str, Any], prompt_override: Optional[str] = None) -> Dict[str, Any]:
        """
        生成当前动作报告的深度教练评语
        具备自动优雅降级机制
        """
        fact_context = GroundedPromptBuilder.build_report_context(report_data)
        user_prompt = (
            f"请根据以下实测生物力学数据，为训练者生成一份温和、专业的动作质量指导评语：\n\n{fact_context}"
        )
        if prompt_override:
            user_prompt += f"\n\n训练者特别关注点：{prompt_override}"

        messages = [
            {"role": "system", "content": GroundedPromptBuilder.SYSTEM_ROLE},
            {"role": "user", "content": user_prompt},
        ]

        # 尝试调用 DeepSeek API
        if self.config.api_key:
            success, content, latency_ms, _ = DeepSeekClient.call_api(
                self.config, messages, temperature=0.6, max_tokens=300
            )
            if success:
                return {
                    "advice": content,
                    "is_fallback": False,
                    "model": self.config.model,
                    "latency_ms": latency_ms,
                    "generated_at": time.strftime("%H:%M:%S"),
                }
            # API 调用失败，记录原因并优雅回退
            fallback_reason = f"DeepSeek API 暂时不可用 ({content})，已自动切换至本地专家规则模板"
        else:
            fallback_reason = "未配置 DeepSeek API Key，已启用离线专家规则模板指导"

        # 离线优雅降级兜底生成
        fallback_text = self._build_offline_fallback(report_data)
        return {
            "advice": fallback_text,
            "is_fallback": True,
            "fallback_reason": fallback_reason,
            "model": "local-biomechanical-expert",
            "latency_ms": 0.0,
            "generated_at": time.strftime("%H:%M:%S"),
        }

    def chat_with_coach(
        self,
        history_messages: List[Dict[str, str]],
        report_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        围绕动作表现进行多轮自然语言问答交互
        """
        system_content = GroundedPromptBuilder.SYSTEM_ROLE
        if report_data:
            fact_context = GroundedPromptBuilder.build_report_context(report_data)
            system_content += f"\n\n【当前训练会话的生物力学背景数据】\n{fact_context}\n用户接下来的追问均围绕此数据展开。"

        full_messages = [{"role": "system", "content": system_content}]

        # 过滤并添加历史消息（最近 6 轮防超出上下文）
        recent_history = history_messages[-6:] if len(history_messages) > 6 else history_messages
        for m in recent_history:
            role = m.get("role", "user")
            content = m.get("content", "").strip()
            if role in ("user", "assistant") and content:
                full_messages.append({"role": role, "content": content})

        if not self.config.api_key:
            return {
                "reply": "【离线提示】当前未配置 DeepSeek API Key，无法进行自由问答交互。请在页面右上角点击「DeepSeek 设置」配置有效的 API Key 即可畅享完整智能对话！",
                "is_fallback": True,
                "latency_ms": 0.0,
            }

        success, content, latency_ms, _ = DeepSeekClient.call_api(
            self.config, full_messages, temperature=0.7, max_tokens=400
        )

        if success:
            return {
                "reply": content,
                "is_fallback": False,
                "model": self.config.model,
                "latency_ms": latency_ms,
            }
        else:
            return {
                "reply": f"抱歉，与 DeepSeek 服务通信受阻（{content}）。请检查网络或在右上角重新测试 API 连通性。",
                "is_fallback": True,
                "latency_ms": latency_ms,
            }

    def _build_offline_fallback(self, report_data: Dict[str, Any]) -> str:
        """基于确定性规则原因码构建高质量本地专家指导文案 (完全离线保证)"""
        status = report_data.get("actual_status", report_data.get("eval_status", "ACCEPTABLE"))
        primary_reason = report_data.get("actual_primary_reason", report_data.get("primary_reason", "R-PASS"))
        min_knee = report_data.get("min_knee_angle", report_data.get("knee_min_angle", 90.0))
        max_torso = report_data.get("max_torso_lean", report_data.get("torso_max_angle", 30.0))

        if status == "ACCEPTABLE" or primary_reason == "R-PASS":
            return (
                f"【动作标杆】恭喜！本次深蹲表现十分标准。下蹲极限膝角达到 {min_knee:.1f}°，"
                f"躯干前倾稳定控制在 {max_torso:.1f}° 范围之内，重心居中且下肢发力平衡。"
                f"建议在起身向心收缩时保持呼气，下一次尝试保持这个良好的收缩节奏！"
            )

        tips = []
        if "R-DEPTH" in primary_reason or min_knee > 105.0:
            tips.append(f"下蹲深度偏浅（实测极限膝角 {min_knee:.1f}°，及格线 ≤105.0°），未能有效激活臀大肌。建议站距微调至与肩同宽、脚尖微向外展 15~30°，并在下蹲时主动向外推膝以打开下蹲空间。")

        if "R-LEAN" in primary_reason or max_torso > 45.0:
            tips.append(f"躯干前倾幅度偏大（实测最大前倾 {max_torso:.1f}°，建议 ≤45.0°），这可能导致腰背剪切力增大。建议下蹲前深吸气憋紧核心增加腹压，下蹲全程视线平视斜前方，保持胸部挺起。")

        if "R-CYCLE" in primary_reason:
            tips.append("动作节奏过快或过慢。推荐标准节奏：2 秒离心平稳下蹲，波谷稍作停顿 1 秒，1 秒果断起身向心发力。")

        if not tips:
            tips.append("整体动作完成度较好，注意全程保持脊柱中立与全脚掌重心均衡。")

        return "【专家规则指导】\n" + "\n".join(tips)
