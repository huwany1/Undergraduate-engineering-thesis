// -*- coding: utf-8 -*-
/**
 * AI 智能健身教练交互控制组件 (LLM Coach UI Module)
 * 职责：
 * 1. 负责 DeepSeek API 凭证与端点设置弹窗交互、连通性探测 (Ping 测速);
 * 2. 负责将实测动作数据驱动大模型生成拟人化个性评语 (带打字机特效);
 * 3. 负责 AI 健身教练多轮追问对话交互与快捷提问气泡 (Quick Prompts);
 * 4. 离线优雅降级状态感知与友好提示.
 */

(function (global) {
  'use strict';

  class LLMCoachUI {
    constructor() {
      this.apiClient = global.SquatDemo ? global.SquatDemo.ApiClient : global.ApiClient;
      this.currentCaseId = null;
      this.currentReportData = null;
      this.chatHistory = [];
      this.isGeneratingAdvice = false;
      this.isChatting = false;

      // DOM 元素缓存
      this.dom = {
        configDialog: document.getElementById('llm-config-dialog'),
        btnOpenConfig: document.getElementById('btn-open-llm-config'),
        btnCloseConfig: document.getElementById('btn-close-llm-config'),
        btnSaveConfig: document.getElementById('btn-save-llm-config'),
        btnTestConnection: document.getElementById('btn-test-llm-connection'),
        apiKeyInput: document.getElementById('llm-api-key-input'),
        baseUrlInput: document.getElementById('llm-base-url-input'),
        modelSelect: document.getElementById('llm-model-select'),
        testResultBox: document.getElementById('llm-test-result'),
        toggleKeyVisibility: document.getElementById('btn-toggle-key-visibility'),

        headerLlmBadge: document.getElementById('header-llm-badge'),
        headerLlmStatusText: document.getElementById('header-llm-status-text'),

        btnGenerateAdvice: document.getElementById('btn-generate-ai-advice'),
        adviceContainer: document.getElementById('ai-coach-advice-text'),
        adviceBadge: document.getElementById('ai-coach-model-badge'),
        adviceMeta: document.getElementById('ai-coach-advice-meta'),

        chatHistoryBox: document.getElementById('ai-coach-chat-messages'),
        chatInput: document.getElementById('ai-coach-chat-input'),
        btnSendChat: document.getElementById('btn-send-llm-chat'),
        quickPromptsBox: document.getElementById('ai-coach-quick-prompts'),
      };
    }

    init() {
      if (!this.dom.configDialog) {
        console.warn('[LLMCoachUI] 未找到大模型弹窗相关 DOM，跳过初始化');
        return;
      }

      this._bindEvents();
      this._loadInitialConfig();
    }

    _bindEvents() {
      // 1. 设置弹窗控制
      if (this.dom.btnOpenConfig) {
        this.dom.btnOpenConfig.addEventListener('click', () => this.openConfigDialog());
      }
      if (this.dom.btnCloseConfig) {
        this.dom.btnCloseConfig.addEventListener('click', () => this.closeConfigDialog());
      }
      if (this.dom.btnTestConnection) {
        this.dom.btnTestConnection.addEventListener('click', () => this.testConnection());
      }
      if (this.dom.btnSaveConfig) {
        this.dom.btnSaveConfig.addEventListener('click', () => this.saveConfig());
      }
      if (this.dom.toggleKeyVisibility) {
        this.dom.toggleKeyVisibility.addEventListener('click', () => {
          const isPwd = this.dom.apiKeyInput.type === 'password';
          this.dom.apiKeyInput.type = isPwd ? 'text' : 'password';
          this.dom.toggleKeyVisibility.textContent = isPwd ? '🙈' : '👁️';
        });
      }

      // 2. 生成 AI 教练深度点评
      if (this.dom.btnGenerateAdvice) {
        this.dom.btnGenerateAdvice.addEventListener('click', () => this.generateAdvice());
      }

      // 3. 对话发送与回车响应
      if (this.dom.btnSendChat) {
        this.dom.btnSendChat.addEventListener('click', () => this.sendChatMessage());
      }
      if (this.dom.chatInput) {
        this.dom.chatInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendChatMessage();
          }
        });
      }

      // 4. 快捷提问气泡点击
      if (this.dom.quickPromptsBox) {
        this.dom.quickPromptsBox.addEventListener('click', (e) => {
          const chip = e.target.closest('.prompt-chip');
          if (chip && chip.dataset.prompt) {
            if (this.dom.chatInput) {
              this.dom.chatInput.value = chip.dataset.prompt;
              this.sendChatMessage();
            }
          }
        });
      }
    }

    async _loadInitialConfig() {
      try {
        const config = await this.apiClient.getLLMConfig();
        if (config) {
          if (this.dom.baseUrlInput) this.dom.baseUrlInput.value = config.base_url || 'https://api.deepseek.com';
          if (this.dom.modelSelect) this.dom.modelSelect.value = config.model || 'deepseek-chat';
          if (config.has_key && this.dom.apiKeyInput) {
            this.dom.apiKeyInput.placeholder = `已配置: ${config.masked_key} (如需更改直接输入新 Key)`;
          }
          this._updateHeaderStatusBadge(config.has_key, config.model);
        }
      } catch (err) {
        console.warn('[LLMCoachUI] 获取配置失败:', err);
      }
    }

    _updateHeaderStatusBadge(hasKey, model = 'deepseek-chat') {
      if (!this.dom.headerLlmBadge) return;
      if (hasKey) {
        this.dom.headerLlmBadge.className = 'badge badge-llm-online';
        if (this.dom.headerLlmStatusText) {
          this.dom.headerLlmStatusText.textContent = `DeepSeek 已就绪 (${model})`;
        }
      } else {
        this.dom.headerLlmBadge.className = 'badge badge-llm-offline';
        if (this.dom.headerLlmStatusText) {
          this.dom.headerLlmStatusText.textContent = '未配置 Key (离线模板兜底)';
        }
      }
    }

    openConfigDialog() {
      if (!this.dom.configDialog) return;
      if (this.dom.testResultBox) {
        this.dom.testResultBox.style.display = 'none';
        this.dom.testResultBox.className = 'test-result-box';
      }
      this.dom.configDialog.showModal();
    }

    closeConfigDialog() {
      if (!this.dom.configDialog) return;
      this.dom.configDialog.close();
    }

    async testConnection() {
      const apiKey = (this.dom.apiKeyInput ? this.dom.apiKeyInput.value : '').trim();
      const baseUrl = (this.dom.baseUrlInput ? this.dom.baseUrlInput.value : '').trim();
      const model = (this.dom.modelSelect ? this.dom.modelSelect.value : '').trim();

      if (!this.dom.testResultBox) return;
      this.dom.testResultBox.style.display = 'block';
      this.dom.testResultBox.className = 'test-result-box testing';
      this.dom.testResultBox.innerHTML = `
        <span class="spinner-inline"></span> 正在向 DeepSeek API 发起连通性探测 (Ping)...
      `;

      if (this.dom.btnTestConnection) this.dom.btnTestConnection.disabled = true;

      try {
        const payload = {};
        if (apiKey) payload.api_key = apiKey;
        if (baseUrl) payload.base_url = baseUrl;
        if (model) payload.model = model;

        const res = await this.apiClient.testLLMConnection(payload);
        if (res.success) {
          this.dom.testResultBox.className = 'test-result-box success';
          this.dom.testResultBox.innerHTML = `
            <strong>🟢 连通性测试通过！</strong><br>
            模型: <code>${res.model || model}</code><br>
            实测往返延迟 (RTT): <strong>${res.latency_ms} ms</strong><br>
            <span style="font-size: 11px; opacity: 0.85;">${res.message || '服务响应健康'}</span>
          `;
        } else {
          this.dom.testResultBox.className = 'test-result-box error';
          this.dom.testResultBox.innerHTML = `
            <strong>🔴 连通性测试失败！</strong><br>
            ${res.message || res.error || '无法连接到 API 服务'}<br>
            <span style="font-size: 11px; opacity: 0.85;">建议检查网络代理、Base URL 或 API Key 是否有效。</span>
          `;
        }
      } catch (err) {
        this.dom.testResultBox.className = 'test-result-box error';
        this.dom.testResultBox.innerHTML = `
          <strong>🔴 连接测试异常</strong><br>
          ${err.message || '未知通信错误'}
        `;
      } finally {
        if (this.dom.btnTestConnection) this.dom.btnTestConnection.disabled = false;
      }
    }

    async saveConfig() {
      const apiKey = (this.dom.apiKeyInput ? this.dom.apiKeyInput.value : '').trim();
      const baseUrl = (this.dom.baseUrlInput ? this.dom.baseUrlInput.value : '').trim();
      const model = (this.dom.modelSelect ? this.dom.modelSelect.value : '').trim();

      try {
        const payload = {};
        if (apiKey) payload.api_key = apiKey;
        if (baseUrl) payload.base_url = baseUrl;
        if (model) payload.model = model;

        const res = await this.apiClient.updateLLMConfig(payload);
        this._updateHeaderStatusBadge(res.has_key, res.model);
        this.closeConfigDialog();

        // 重新生成点评 (若已有当前用例)
        if (this.currentCaseId || this.currentReportData) {
          this.generateAdvice();
        }
      } catch (err) {
        alert(`保存配置失败: ${err.message}`);
      }
    }

    setCurrentCase(caseId, reportData = null) {
      this.currentCaseId = caseId;
      this.currentReportData = reportData;
      // 清空对话历史并重置为当前用例专属问答
      this.chatHistory = [];
      if (this.dom.chatHistoryBox) {
        this.dom.chatHistoryBox.innerHTML = `
          <div class="chat-bubble ai">
            <span class="chat-avatar">🤖</span>
            <div class="chat-text">
              你好！我是你的 AI 智能健身教练。我已经加载了本轮深蹲的实测数据，随时可以就下蹲深度、前倾角调整或收缩节奏向我提问！
            </div>
          </div>
        `;
      }

      // 自动触发一次深度点评生成
      this.generateAdvice();
    }

    async generateAdvice() {
      if (this.isGeneratingAdvice) return;
      this.isGeneratingAdvice = true;

      if (this.dom.btnGenerateAdvice) {
        this.dom.btnGenerateAdvice.disabled = true;
        this.dom.btnGenerateAdvice.innerHTML = '<span class="spinner-inline"></span> AI 思考中...';
      }

      if (this.dom.adviceContainer) {
        this.dom.adviceContainer.innerHTML = '<span class="loading-typing">AI 健身教练正在结合生物力学事实深度推导建议...</span>';
      }

      try {
        const payload = {
          case_id: this.currentCaseId,
          report_data: this.currentReportData,
        };

        const res = await this.apiClient.getLLMFeedback(payload);

        // 渲染徽标
        if (this.dom.adviceBadge) {
          if (res.is_fallback) {
            this.dom.adviceBadge.className = 'badge badge-eval not-eval';
            this.dom.adviceBadge.textContent = '专家离线规则兜底';
            this.dom.adviceBadge.title = res.fallback_reason || '';
          } else {
            this.dom.adviceBadge.className = 'badge badge-eval acceptable';
            this.dom.adviceBadge.textContent = `DeepSeek (${res.model}) · ${res.latency_ms}ms`;
          }
        }

        // 打字机呈现
        this._typewriterEffect(this.dom.adviceContainer, res.advice || '暂无建议输出');

      } catch (err) {
        if (this.dom.adviceContainer) {
          this.dom.adviceContainer.textContent = `生成点评时发生错误: ${err.message}`;
        }
      } finally {
        this.isGeneratingAdvice = false;
        if (this.dom.btnGenerateAdvice) {
          this.dom.btnGenerateAdvice.disabled = false;
          this.dom.btnGenerateAdvice.innerHTML = '🔄 重新生成 AI 点评';
        }
      }
    }

    async sendChatMessage() {
      if (this.isChatting) return;
      const text = (this.dom.chatInput ? this.dom.chatInput.value : '').trim();
      if (!text) return;

      this.isChatting = true;
      if (this.dom.chatInput) this.dom.chatInput.value = '';

      // 1. 追加用户气泡
      this._appendChatBubble('user', text);
      this.chatHistory.push({ role: 'user', content: text });

      // 2. 渲染正在输入指示器
      const loadingId = this._appendChatBubble('ai', '<span class="typing-dots"><span>.</span><span>.</span><span>.</span></span> AI 教练正在组织语言...');

      try {
        const payload = {
          messages: this.chatHistory,
          case_id: this.currentCaseId,
          report_data: this.currentReportData,
        };

        const res = await this.apiClient.chatWithLLM(payload);
        const reply = res.reply || '抱歉，未能获取到有效答复。';
        this.chatHistory.push({ role: 'assistant', content: reply });

        // 更新气泡内容
        const bubbleElem = document.getElementById(loadingId);
        if (bubbleElem) {
          const textContainer = bubbleElem.querySelector('.chat-text');
          if (textContainer) {
            this._typewriterEffect(textContainer, reply);
          }
        }
      } catch (err) {
        const bubbleElem = document.getElementById(loadingId);
        if (bubbleElem) {
          const textContainer = bubbleElem.querySelector('.chat-text');
          if (textContainer) {
            textContainer.textContent = `通信异常: ${err.message}`;
          }
        }
      } finally {
        this.isChatting = false;
      }
    }

    _appendChatBubble(role, contentHtml) {
      if (!this.dom.chatHistoryBox) return null;
      const bubbleId = 'bubble-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
      const isUser = role === 'user';

      const bubbleDiv = document.createElement('div');
      bubbleDiv.id = bubbleId;
      bubbleDiv.className = `chat-bubble ${isUser ? 'user' : 'ai'}`;
      bubbleDiv.innerHTML = `
        <span class="chat-avatar">${isUser ? '👤' : '🤖'}</span>
        <div class="chat-text">${contentHtml}</div>
      `;

      this.dom.chatHistoryBox.appendChild(bubbleDiv);
      this.dom.chatHistoryBox.scrollTop = this.dom.chatHistoryBox.scrollHeight;
      return bubbleId;
    }

    _typewriterEffect(container, text, speed = 12) {
      if (!container) return;
      container.textContent = '';
      let index = 0;
      const timer = setInterval(() => {
        if (index < text.length) {
          container.textContent += text.charAt(index);
          index++;
          if (this.dom.chatHistoryBox) {
            this.dom.chatHistoryBox.scrollTop = this.dom.chatHistoryBox.scrollHeight;
          }
        } else {
          clearInterval(timer);
        }
      }, speed);
    }
  }

  // 挂载到命名空间与全局
  global.SquatDemo = global.SquatDemo || {};
  global.SquatDemo.LLMCoachUI = LLMCoachUI;
  global.LLMCoachUI = LLMCoachUI;
})(typeof window !== 'undefined' ? window : this);
