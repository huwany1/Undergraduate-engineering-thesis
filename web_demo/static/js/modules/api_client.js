// -*- coding: utf-8 -*-
/**
 * RESTful API 统一交互客户端组件 (API Client Module)
 * 职责：
 * 1. 统一管理与后端 Python 原生 HTTP 服务的网络通信 (GET / POST);
 * 2. 封装错误处理、超时熔断提示与 JSON 数据解析;
 * 3. 支持用例列表、详情、上传任务轮询与实时摄像头帧交互.
 */

(function (global) {
  'use strict';

  class ApiClient {
    static async get(url) {
      const resp = await fetch(url, {
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) {
        let errDetail = `HTTP ${resp.status}`;
        try {
          const errJson = await resp.json();
          if (errJson && errJson.error) errDetail = errJson.error;
        } catch (_) {}
        throw new Error(errDetail);
      }
      return await resp.json();
    }

    static async post(url, body, headers = {}) {
      const resp = await fetch(url, {
        method: 'POST',
        headers: headers,
        body: body,
      });
      if (!resp.ok) {
        let errDetail = `HTTP ${resp.status}`;
        try {
          const errJson = await resp.json();
          if (errJson && errJson.error) errDetail = errJson.error;
        } catch (_) {}
        throw new Error(errDetail);
      }
      return await resp.json();
    }

    // --- 业务接口方法 ---

    static async getStatus() {
      return this.get('/api/status');
    }

    static async getCases() {
      return this.get('/api/cases');
    }

    static async getCaseDetail(caseId) {
      return this.get(`/api/case/${encodeURIComponent(caseId)}`);
    }

    static async getValidationReport() {
      return this.get('/api/reports/validation');
    }

    static async getDatasetDemos() {
      return this.get('/api/dataset_demos');
    }

    static async getDatasetDemoDetail(demoId) {
      return this.get(`/api/dataset_demo/${encodeURIComponent(demoId)}`);
    }

    static async listUploads() {
      return this.get('/api/uploads');
    }

    static async getTaskStatus(taskId) {
      return this.get(`/api/task/${encodeURIComponent(taskId)}`);
    }

    static async getHardwareStatus(forceRefresh = false) {
      return this.get(`/api/system/hardware${forceRefresh ? '?refresh=1' : ''}`);
    }

    static async setHardwareProfile(profile) {
      return this.post('/api/system/hardware/profile', JSON.stringify({ profile }), {
        'Content-Type': 'application/json',
      });
    }

    static async uploadVideo(formData, accelProfile = null) {
      const url = accelProfile ? `/api/upload?accel_profile=${encodeURIComponent(accelProfile)}` : '/api/upload';
      const resp = await fetch(url, {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.error || `上传失败 (HTTP ${resp.status})`);
      }
      return await resp.json();
    }

    static async startLiveSession() {
      return this.post('/api/live/session/start', null);
    }

    static async sendLiveFrame(sessionId, blob, clientTimestampMs) {
      const url = `/api/live/session/${encodeURIComponent(sessionId)}/frame`;
      const headers = {
        'Content-Type': 'application/octet-stream',
        'X-Client-Timestamp': String(clientTimestampMs || Date.now()),
      };
      return this.post(url, blob, headers);
    }

    static async stopLiveSession(sessionId) {
      const url = `/api/live/session/${encodeURIComponent(sessionId)}/stop`;
      return this.post(url, null);
    }

    // --- 大模型 (LLM) 智能教练接口 ---

    static async getLLMConfig() {
      return this.get('/api/llm/config');
    }

    static async updateLLMConfig(payload) {
      return this.post('/api/llm/config', JSON.stringify(payload), {
        'Content-Type': 'application/json',
      });
    }

    static async testLLMConnection(payload) {
      return this.post('/api/llm/test', JSON.stringify(payload), {
        'Content-Type': 'application/json',
      });
    }

    static async getLLMFeedback(payload) {
      return this.post('/api/llm/feedback', JSON.stringify(payload), {
        'Content-Type': 'application/json',
      });
    }

    static async chatWithLLM(payload) {
      return this.post('/api/llm/chat', JSON.stringify(payload), {
        'Content-Type': 'application/json',
      });
    }
  }

  // 挂载到统一命名空间与全局
  global.SquatDemo = global.SquatDemo || {};
  global.SquatDemo.ApiClient = ApiClient;
  global.ApiClient = ApiClient;
})(typeof window !== 'undefined' ? window : this);
