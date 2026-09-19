// -*- coding: utf-8 -*-
/**
 * 实时硬件摄像头与虚拟推流控制器组件 (Live Stream Controller Module)
 * 职责：
 * 1. 原生 Web Audio API 动作反馈音效合成器 (AudioManager);
 * 2. 驱动 getUserMedia 摄像头流获取与设备选择;
 * 3. 基于 In-Flight 令牌锁实行单窗口背压流控，丢帧不积压，25~30 FPS 低延迟;
 * 4. 驱动骨骼绘制、动态双角悬浮气泡、HUD 计数与时序曲线;
 * 5. 动作完成时触发 Web Audio 提示音与庆祝横幅;
 * 6. 支持无物理摄像头时的虚拟演示流无缝兜底.
 */

(function (global) {
  'use strict';

  class AudioManager {
    constructor() {
      this.audioCtx = null;
      this.isEnabled = true;
    }

    ensureContext() {
      if (!this.audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
          this.audioCtx = new AudioContext();
        }
      }
      if (this.audioCtx && this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
    }

    playRepChime(success = true) {
      if (!this.isEnabled) return;
      try {
        this.ensureContext();
        if (!this.audioCtx) return;
        const now = this.audioCtx.currentTime;
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);

        if (success) {
          // D5 (587.33Hz) -> A5 (880.00Hz) 两个音符悦耳上扬
          osc.type = 'sine';
          osc.frequency.setValueAtTime(587.33, now);
          osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.12);
          gain.gain.setValueAtTime(0.28, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.38);
          osc.start(now);
          osc.stop(now + 0.4);
        } else {
          // 较低沉的轻微提示音
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(329.63, now);
          osc.frequency.exponentialRampToValueAtTime(220.00, now + 0.15);
          gain.gain.setValueAtTime(0.25, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
          osc.start(now);
          osc.stop(now + 0.32);
        }
      } catch (e) {
        console.warn('播放音效失败:', e);
      }
    }
  }

  class LiveCameraController {
    constructor({
      videoEl,
      canvasEl,
      overlayEl,
      metricsEl,
      celebrationEl,
      celebrationTextEl,
      skeletonRenderer,
      chart,
      audioManager,
      onSessionFinished,
      updateHud,
    }) {
      this.videoEl = videoEl;
      this.canvasEl = canvasEl;
      this.overlayEl = overlayEl;
      this.metricsEl = metricsEl;
      this.celebrationEl = celebrationEl;
      this.celebrationTextEl = celebrationTextEl;
      this.skeletonRenderer = skeletonRenderer;
      this.chart = chart;
      this.audioManager = audioManager;
      this.onSessionFinished = onSessionFinished;
      this.updateHud = updateHud;

      this.mediaStream = null;
      this.sessionId = null;
      this.isRunning = false;
      this.isVirtual = false;
      this.inFlight = false;
      this.rafId = null;

      // 离屏捕获 Canvas (固定 640x480 分辨率，平衡精度与极速低延迟)
      this.captureCanvas = document.createElement('canvas');
      this.captureCanvas.width = 640;
      this.captureCanvas.height = 480;
      this.captureCtx = this.captureCanvas.getContext('2d', { willReadFrequently: true });

      // 帧率与延迟统计
      this.frameCount = 0;
      this.lastFpsCalcTime = performance.now();
      this.currentFps = 0;
      this.currentRtt = 0;

      // 动作完成横幅定时器
      this.celebrationTimer = null;
    }

    async startCamera(deviceId = null) {
      this.isVirtual = false;
      this.audioManager.ensureContext();

      const constraints = {
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      };
      if (deviceId) {
        constraints.video.deviceId = { exact: deviceId };
      }

      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('当前浏览器环境不支持 getUserMedia 摄像头接口 (可能需要 HTTPS 或 localhost 访问)');
        }
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        this.mediaStream = stream;
        this.videoEl.srcObject = stream;
        this.videoEl.controls = false;
        await this.videoEl.play();

        await this._initBackendSession();
        this._startCaptureLoop();
        this._showOverlay(true, 'LIVE 硬件摄像头实时推理');
        return { success: true };
      } catch (err) {
        console.warn('获取物理摄像头失败:', err);
        return {
          success: false,
          error: err.name || 'CameraError',
          message: err.message || '无法访问物理摄像头',
        };
      }
    }

    async startVirtualCamera(videoUrl = '/api/media/replays/TC_01_PERFECT_SQUAT_annotated.mp4') {
      this.isVirtual = true;
      this.audioManager.ensureContext();

      try {
        if (this.mediaStream) {
          this.mediaStream.getTracks().forEach(t => t.stop());
          this.mediaStream = null;
        }
        this.videoEl.srcObject = null;
        this.videoEl.src = videoUrl;
        this.videoEl.loop = true;
        this.videoEl.muted = true;
        this.videoEl.controls = false;
        await this.videoEl.play();

        await this._initBackendSession();
        this._startCaptureLoop();
        this._showOverlay(true, 'LIVE 虚拟演示流实时推理');
        return { success: true };
      } catch (err) {
        console.warn('启动虚拟演示流失败:', err);
        return {
          success: false,
          error: 'VirtualCameraError',
          message: err.message || '启动虚拟演示流失败',
        };
      }
    }

    async _initBackendSession() {
      const res = await fetch('/api/live/session/start', { method: 'POST' });
      if (!res.ok) {
        throw new Error(`后端实时会话初始化失败 (HTTP ${res.status})`);
      }
      const data = await res.json();
      this.sessionId = data.session_id;
      this.isRunning = true;
      this.inFlight = false;
      this.frameCount = 0;
      this.lastFpsCalcTime = performance.now();
      this.chart.clear();
      this.skeletonRenderer.resize();
    }

    _startCaptureLoop() {
      const loop = async () => {
        if (!this.isRunning) return;

        const now = performance.now();
        this.frameCount++;
        if (now - this.lastFpsCalcTime >= 1000) {
          this.currentFps = Math.round((this.frameCount * 1000) / (now - this.lastFpsCalcTime));
          this.frameCount = 0;
          this.lastFpsCalcTime = now;
          this._updateMetricsDisplay();
        }

        // 核心背压流控机制 (In-Flight Guard / Sliding Window = 1)
        if (!this.inFlight && this.videoEl.readyState >= 2 && this.videoEl.videoWidth > 0) {
          this.inFlight = true;
          const sendStart = performance.now();

          try {
            this.captureCtx.drawImage(this.videoEl, 0, 0, 640, 480);
            this.captureCanvas.toBlob(async (blob) => {
              if (!blob || !this.isRunning) {
                this.inFlight = false;
                return;
              }

              try {
                const res = await fetch(`/api/live/session/${this.sessionId}/frame`, {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'image/jpeg',
                    'X-Client-Timestamp': String(Date.now()),
                  },
                  body: blob,
                });

                if (res.ok) {
                  const point = await res.json();
                  this.currentRtt = Math.round(performance.now() - sendStart);
                  this._updateMetricsDisplay();

                  if (this.updateHud) this.updateHud(point);
                  this.skeletonRenderer.render(point);
                  this.chart.appendPoint(point);

                  if (point.rep_event) {
                    this._handleRepCompleted(point.rep_event);
                  }
                }
              } catch (postErr) {
                console.warn('单帧推流回包异常 (网络跳帧):', postErr);
              } finally {
                this.inFlight = false;
              }
            }, 'image/jpeg', 0.65);
          } catch (captureErr) {
            console.warn('Canvas 捕获异常:', captureErr);
            this.inFlight = false;
          }
        }

        this.rafId = requestAnimationFrame(loop);
      };

      this.rafId = requestAnimationFrame(loop);
    }

    _handleRepCompleted(event) {
      const isPass = event.status === 'ACCEPTABLE';
      this.audioManager.playRepChime(isPass);

      if (this.celebrationEl && this.celebrationTextEl) {
        if (this.celebrationTimer) clearTimeout(this.celebrationTimer);
        const statusText = isPass ? '深度及格达标' : '动作待改进';
        this.celebrationTextEl.textContent = `第 ${event.rep_id} 次完成！${statusText} (膝角: ${event.min_knee_angle}°, 耗时: ${event.duration_s}s)`;
        this.celebrationEl.style.display = 'flex';
        this.celebrationEl.style.background = isPass
          ? 'linear-gradient(135deg, rgba(6, 78, 59, 0.95), rgba(4, 120, 87, 0.95))'
          : 'linear-gradient(135deg, rgba(120, 53, 15, 0.95), rgba(180, 83, 9, 0.95))';
        this.celebrationEl.style.borderColor = isPass ? '#10b981' : '#f59e0b';

        this.celebrationTimer = setTimeout(() => {
          this.celebrationEl.style.display = 'none';
        }, 3500);
      }
    }

    _updateMetricsDisplay() {
      if (this.metricsEl) {
        this.metricsEl.textContent = `FPS: ${this.currentFps} | RTT: ${this.currentRtt}ms`;
      }
    }

    _showOverlay(show, text = null) {
      if (this.overlayEl) {
        this.overlayEl.style.display = show ? 'flex' : 'none';
        if (text) {
          const textEl = this.overlayEl.querySelector('.live-pill-text');
          if (textEl) textEl.textContent = text;
        }
      }
    }

    async stop() {
      if (!this.isRunning) return null;
      this.isRunning = false;
      if (this.rafId) {
        cancelAnimationFrame(this.rafId);
        this.rafId = null;
      }

      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach(t => t.stop());
        this.mediaStream = null;
      }
      this.videoEl.pause();
      this.videoEl.srcObject = null;
      this.videoEl.controls = true;
      this._showOverlay(false);
      this.skeletonRenderer.clear();

      if (this.celebrationEl) this.celebrationEl.style.display = 'none';

      let summary = null;
      if (this.sessionId) {
        try {
          const res = await fetch(`/api/live/session/${this.sessionId}/stop`, { method: 'POST' });
          if (res.ok) {
            summary = await res.json();
            if (this.onSessionFinished) {
              this.onSessionFinished(summary);
            }
          }
        } catch (err) {
          console.warn('结束实时会话失败:', err);
        }
        this.sessionId = null;
      }

      return summary;
    }
  }

  // 挂载到统一命名空间与全局
  global.SquatDemo = global.SquatDemo || {};
  global.SquatDemo.AudioManager = AudioManager;
  global.SquatDemo.LiveCameraController = LiveCameraController;
  global.AudioManager = AudioManager;
  global.LiveCameraController = LiveCameraController;
})(typeof window !== 'undefined' ? window : this);
