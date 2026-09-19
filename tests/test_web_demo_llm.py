# -*- coding: utf-8 -*-
"""
大模型 (LLM) 智能教练与 DeepSeek API 交互测试套件
覆盖:
1. LLMConfig 凭证脱敏与端点构建;
2. GroundedPromptBuilder 运动学事实注入与非医疗化约束;
3. DeepSeekClient 在正常响应、401 鉴权失败、超时断网下的容错与 RTT 统计;
4. 优雅离线降级 (Graceful Fallback) 逻辑;
5. REST API (/api/llm/*) 端到端调用契约.
"""

import io
import json
import threading
import urllib.request
import urllib.error
from typing import Dict, Any
import pytest

from web_demo.llm_coach import (
    LLMConfig,
    GroundedPromptBuilder,
    DeepSeekClient,
    DeepSeekCoachService,
)
from web_demo.service import DemoService
from web_demo.server import run_server


@pytest.fixture(scope="module")
def web_server():
    """启动测试专用多线程 HTTP 服务"""
    server = run_server(port=0, host="127.0.0.1")
    actual_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{actual_port}"
    yield base_url

    server.shutdown()
    server.server_close()


class MockHTTPResponse:
    """模拟 urllib.request.urlopen 响应对象"""

    def __init__(self, data: Dict[str, Any], status: int = 200):
        self.data_bytes = json.dumps(data).encode("utf-8")
        self.status = status

    def read(self):
        return self.data_bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# =========================================================================
# 1. 单元测试: 配置、提示词与客户端
# =========================================================================

def test_llm_config_masking_and_endpoints():
    """测试 API Key 脱敏与接口路由规范化"""
    cfg_empty = LLMConfig(api_key="")
    assert cfg_empty.get_masked_key() == ""

    cfg_short = LLMConfig(api_key="12345")
    assert cfg_short.get_masked_key() == "sk-****"

    cfg_normal = LLMConfig(api_key="sk-abcdef1234567890")
    assert cfg_normal.get_masked_key() == "sk-****7890"

    # 端点格式规范化
    cfg1 = LLMConfig(base_url="https://api.deepseek.com")
    assert cfg1.get_completions_endpoint() == "https://api.deepseek.com/v1/chat/completions"

    cfg2 = LLMConfig(base_url="https://api.deepseek.com/v1")
    assert cfg2.get_completions_endpoint() == "https://api.deepseek.com/v1/chat/completions"


def test_grounded_prompt_builder_contains_facts():
    """测试生物力学事实能否被准确组装入 Context"""
    report_data = {
        "case_name": "测试用例_躯干过度前倾",
        "actual_count": 3,
        "actual_status": "NEEDS_IMPROVEMENT",
        "min_knee_angle": 88.5,
        "max_torso_lean": 56.2,
        "duration_ms": 2400,
        "actual_primary_reason": "R-LEAN-001",
        "group_analytics": {
            "consistency_score": 85,
            "fatigue_status": "STABLE",
            "cadence_tempo_code": "2-1-1",
        }
    }

    context = GroundedPromptBuilder.build_report_context(report_data)
    assert "88.5°" in context
    assert "56.2°" in context
    assert "R-LEAN-001" in context
    assert "3 次" in context
    assert "85 分" in context
    assert "2-1-1" in context


def test_deepseek_client_mock_success(monkeypatch):
    """模拟 DeepSeek API 正常返回 HTTP 200"""
    mock_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "本次深蹲深度良好，但前倾角达到了 56.2°。建议收紧核心腹压，视线平视斜前方。",
                }
            }
        ]
    }

    def mock_urlopen(req, timeout=10.0):
        return MockHTTPResponse(mock_payload, status=200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    config = LLMConfig(api_key="sk-test-key-12345")
    success, content, latency_ms, status_code = DeepSeekClient.call_api(
        config, [{"role": "user", "content": "ping"}]
    )

    assert success is True
    assert "本次深蹲深度良好" in content
    assert status_code == 200
    assert latency_ms >= 0


def test_deepseek_client_mock_auth_error(monkeypatch):
    """模拟 DeepSeek API 鉴权失败 HTTP 401"""
    def mock_urlopen_raise(req, timeout=10.0):
        fp = io.BytesIO(b'{"error":{"message":"Authentication failed: Invalid API key"}}')
        raise urllib.error.HTTPError(
            url="https://api.deepseek.com/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=fp,
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_raise)

    config = LLMConfig(api_key="sk-invalid-key")
    success, content, latency_ms, status_code = DeepSeekClient.call_api(
        config, [{"role": "user", "content": "ping"}]
    )

    assert success is False
    assert status_code == 401
    assert "Authentication failed" in content


def test_deepseek_client_mock_network_timeout(monkeypatch):
    """模拟网络超时或连接失败"""
    def mock_urlopen_timeout(req, timeout=10.0):
        raise urllib.error.URLError("Connection timed out")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_timeout)

    config = LLMConfig(api_key="sk-test-key")
    success, content, latency_ms, status_code = DeepSeekClient.call_api(
        config, [{"role": "user", "content": "ping"}]
    )

    assert success is False
    assert status_code == 0
    assert "网络连接不可达" in content


# =========================================================================
# 2. 业务层测试: 连通性测试与离线优雅兜底
# =========================================================================

def test_coach_service_test_connection(monkeypatch):
    """测试服务层的连通性探测"""
    def mock_urlopen(req, timeout=8.0):
        return MockHTTPResponse({"choices": [{"message": {"content": "PONG"}}]}, status=200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    service = DeepSeekCoachService()
    res = service.test_connection(api_key="sk-valid-key")
    assert res["success"] is True
    assert "连通性测试成功" in res["message"]


def test_coach_service_fallback_without_key():
    """未配置 Key 时应无缝回退至本地规则模板，不报错"""
    service = DeepSeekCoachService()
    service.config.api_key = ""

    report_data = {
        "actual_status": "NEEDS_IMPROVEMENT",
        "actual_primary_reason": "R-DEPTH-001",
        "min_knee_angle": 115.0,
        "max_torso_lean": 32.0,
    }

    feedback = service.generate_coach_advice(report_data)
    assert feedback["is_fallback"] is True
    assert "下蹲深度偏浅" in feedback["advice"]
    assert feedback["model"] == "local-biomechanical-expert"

    # 对话未配置 Key 提示
    chat_res = service.chat_with_coach([{"role": "user", "content": "我该怎么做？"}])
    assert chat_res["is_fallback"] is True
    assert "未配置 DeepSeek API Key" in chat_res["reply"]


def test_coach_service_fallback_on_network_failure(monkeypatch):
    """网络故障时应平滑回退至本地规则，绝不抛出未捕获异常"""
    def mock_fail(req, timeout=10.0):
        raise urllib.error.URLError("DNS resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", mock_fail)

    service = DeepSeekCoachService()
    service.config.api_key = "sk-some-key"

    report_data = {
        "actual_status": "ACCEPTABLE",
        "actual_primary_reason": "R-PASS",
        "min_knee_angle": 92.0,
        "max_torso_lean": 28.0,
    }

    feedback = service.generate_coach_advice(report_data)
    assert feedback["is_fallback"] is True
    assert "动作标杆" in feedback["advice"]
    assert "自动切换至本地专家规则模板" in feedback["fallback_reason"]


# =========================================================================
# 3. 集成测试: REST API 端点验证
# =========================================================================

def test_rest_api_llm_config_get_and_post(web_server):
    """验证 GET /api/llm/config 与 POST /api/llm/config"""
    # 1. GET
    req = urllib.request.Request(f"{web_server}/api/llm/config")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "has_key" in data
        assert "base_url" in data
        assert "model" in data

    # 2. POST 更新配置
    update_payload = {
        "api_key": "sk-test-saved-key-8888",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    }
    post_data = json.dumps(update_payload).encode("utf-8")
    req_post = urllib.request.Request(
        f"{web_server}/api/llm/config",
        data=post_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_post) as resp:
        assert resp.status == 200
        res_json = json.loads(resp.read().decode("utf-8"))
        assert res_json["has_key"] is True
        assert res_json["masked_key"] == "sk-****8888"


def test_rest_api_llm_test_connection(web_server, monkeypatch):
    """验证 POST /api/llm/test 接口"""
    monkeypatch.setattr(
        DeepSeekClient,
        "call_api",
        classmethod(lambda cls, *args, **kwargs: (True, "PONG", 15.2, 200)),
    )

    test_payload = {"api_key": "sk-mock-key"}
    req = urllib.request.Request(
        f"{web_server}/api/llm/test",
        data=json.dumps(test_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res_json = json.loads(resp.read().decode("utf-8"))
        assert res_json["success"] is True
        assert res_json["model"] == "deepseek-chat"


def test_rest_api_llm_feedback_and_chat(web_server):
    """验证 POST /api/llm/feedback 与 POST /api/llm/chat (离线降级兜底)"""
    # 1. 反馈生成 (对既有用例 TC_01_PERFECT_SQUAT)
    fb_payload = {"case_id": "TC_01_PERFECT_SQUAT"}
    req = urllib.request.Request(
        f"{web_server}/api/llm/feedback",
        data=json.dumps(fb_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res_json = json.loads(resp.read().decode("utf-8"))
        assert "advice" in res_json
        assert len(res_json["advice"]) > 0

    # 2. 对话交互
    chat_payload = {
        "messages": [{"role": "user", "content": "怎么才能蹲得更稳？"}],
        "case_id": "TC_01_PERFECT_SQUAT",
    }
    req_chat = urllib.request.Request(
        f"{web_server}/api/llm/chat",
        data=json.dumps(chat_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_chat) as resp:
        assert resp.status == 200
        res_json = json.loads(resp.read().decode("utf-8"))
        assert "reply" in res_json
        assert len(res_json["reply"]) > 0


def test_load_dotenv_fallback_and_auto_env_injection(tmp_path, monkeypatch):
    """验证 .env 文件安全解析与无感自动载入机制"""
    from web_demo.llm_coach import load_dotenv_fallback

    # 1. 隔离当前环境变量
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # 2. 创建临时 .env 文件
    env_file = tmp_path / ".env"
    env_file.write_text("# 配置文件注释\nDEEPSEEK_API_KEY=sk-test-auto-key-123456\nOTHER_VAR=test\n", encoding="utf-8")

    # 3. 触发解析
    loaded_key = load_dotenv_fallback(repo_root=str(tmp_path))
    assert loaded_key == "sk-test-auto-key-123456"

    # 4. 验证 DeepSeekCoachService 在没有全局变量时自动读取
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    service = DeepSeekCoachService(repo_root=str(tmp_path))
    summary = service.get_config_summary()
    assert summary["has_key"] is True
    assert summary["masked_key"] == "sk-****3456"
