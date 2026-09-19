// -*- coding: utf-8 -*-
/**
 * 实时姿态骨骼与生物力学角度渲染器组件 (Skeleton & Biomechanics Overlay Renderer Module)
 * 职责：
 * 1. 监听视频画幅与信箱黑边 (Letterbox/Pillarbox)，建立归一化坐标精准映射；
 * 2. 绘制 MediaPipe Pose 33 关键点骨骼拓扑连线与多色关节点高亮；
 * 3. 动态计算优势侧膝关节与躯干位置，原位渲染实测屈曲角/前倾角悬浮胶囊；
 * 4. 适配 HiDPI 屏幕 Retina 缩放，保障 60 FPS 极速矢量渲染。
 */

(function (global) {
  'use strict';

  class SkeletonRenderer {
    constructor(canvas, video, container) {
      this.canvas = canvas;
      this.ctx = canvas ? canvas.getContext('2d') : null;
      this.video = video;
      this.container = container;
      this.isEnabled = true;
      this.displayWidth = 0;
      this.displayHeight = 0;

      this.resize();
      window.addEventListener('resize', () => this.resize());

      // MediaPipe Pose 33 关键点拓扑连接定义
      this.connections = [
        // 头部五官
        [0, 1], [1, 2], [2, 3], [3, 7],
        [0, 4], [4, 5], [5, 6], [6, 8],
        [9, 10],
        // 躯干与肩髋
        [11, 12], [11, 23], [12, 24], [23, 24],
        // 左上肢
        [11, 13], [13, 15], [15, 17], [15, 19], [15, 21], [17, 19],
        // 右上肢
        [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
        // 左下肢
        [23, 25], [25, 27], [27, 29], [29, 31], [27, 31],
        // 右下肢
        [24, 26], [26, 28], [28, 30], [30, 32], [28, 32],
      ];
    }

    resize() {
      if (!this.container || !this.canvas || !this.ctx) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = this.container.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      this.displayWidth = rect.width;
      this.displayHeight = rect.height;
      this.canvas.width = Math.round(rect.width * dpr);
      this.canvas.height = Math.round(rect.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    clear() {
      if (!this.ctx) return;
      this.ctx.clearRect(0, 0, this.displayWidth, this.displayHeight);
    }

    getVideoContentRect() {
      const vWidth = (this.video && this.video.videoWidth) ? this.video.videoWidth : 1920;
      const vHeight = (this.video && this.video.videoHeight) ? this.video.videoHeight : 1080;
      const cWidth = this.displayWidth;
      const cHeight = this.displayHeight;
      if (!cWidth || !cHeight) return { x: 0, y: 0, width: 0, height: 0 };

      const vAspect = vWidth / vHeight;
      const cAspect = cWidth / cHeight;
      let renderWidth, renderHeight, offsetX, offsetY;

      if (vAspect > cAspect) {
        renderWidth = cWidth;
        renderHeight = cWidth / vAspect;
        offsetX = 0;
        offsetY = (cHeight - renderHeight) / 2;
      } else {
        renderHeight = cHeight;
        renderWidth = cHeight * vAspect;
        offsetX = (cWidth - renderWidth) / 2;
        offsetY = 0;
      }
      return { x: offsetX, y: offsetY, width: renderWidth, height: renderHeight };
    }

    render(telemetryPoint) {
      this.clear();
      if (!this.isEnabled || !telemetryPoint || !this.ctx) return;

      const landmarks = telemetryPoint.landmarks;
      const hasLandmarks = Array.isArray(landmarks) && landmarks.length >= 33;
      const rect = this.getVideoContentRect();

      if (hasLandmarks && telemetryPoint.is_valid) {
        this.drawSkeleton(landmarks, rect, telemetryPoint);
      }

      this.drawAngleBadges(landmarks, rect, telemetryPoint, hasLandmarks);
    }

    drawSkeleton(landmarks, rect, telemetryPoint) {
      const ctx = this.ctx;
      const pts = landmarks.map((p) => ({
        x: rect.x + p[0] * rect.width,
        y: rect.y + p[1] * rect.height,
        vis: p[2] !== undefined ? p[2] : 1.0,
      }));

      ctx.lineWidth = 3.5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      this.connections.forEach(([i, j]) => {
        const p1 = pts[i];
        const p2 = pts[j];
        if (!p1 || !p2 || p1.vis < 0.25 || p2.vis < 0.25) return;

        let strokeColor = 'rgba(59, 130, 246, 0.9)';
        if ((i >= 23 && i <= 32) || (j >= 23 && j <= 32)) {
          strokeColor = 'rgba(16, 185, 129, 0.95)';
        } else if ((i >= 11 && i <= 16) || (j >= 11 && j <= 16)) {
          strokeColor = 'rgba(56, 189, 248, 0.9)';
        }

        ctx.strokeStyle = strokeColor;
        ctx.shadowColor = strokeColor;
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      });

      ctx.shadowBlur = 0;

      pts.forEach((pt, idx) => {
        if (pt.vis < 0.25) return;
        const isHead = idx < 11;
        const radius = isHead ? 2.5 : 4.5;

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
        ctx.strokeStyle = (idx === 25 || idx === 26) ? '#38bdf8' : '#0284c7';
        ctx.lineWidth = 2;
        ctx.stroke();
      });

      const leftKnee = pts[25];
      const rightKnee = pts[26];
      const targetKnee = (rightKnee && rightKnee.vis > (leftKnee ? leftKnee.vis : 0)) ? rightKnee : leftKnee;

      if (targetKnee && targetKnee.vis >= 0.25) {
        ctx.beginPath();
        ctx.arc(targetKnee.x, targetKnee.y, 11, 0, Math.PI * 2);
        const isPass = telemetryPoint.knee_angle <= 105.0;
        ctx.fillStyle = isPass ? 'rgba(16, 185, 129, 0.35)' : 'rgba(56, 189, 248, 0.35)';
        ctx.fill();
        ctx.strokeStyle = isPass ? '#10b981' : '#38bdf8';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }

    drawAngleBadges(landmarks, rect, telemetryPoint, hasLandmarks) {
      const ctx = this.ctx;
      const kneeAngle = telemetryPoint.knee_angle || 0;
      const torsoAngle = telemetryPoint.torso_angle || 0;

      let kneeX, kneeY, torsoX, torsoY;

      if (hasLandmarks && telemetryPoint.is_valid) {
        const leftKnee = landmarks[25];
        const rightKnee = landmarks[26];
        const k = (rightKnee && rightKnee[2] > (leftKnee ? leftKnee[2] : 0)) ? rightKnee : leftKnee;
        if (k && k[2] > 0.2) {
          kneeX = rect.x + k[0] * rect.width + 14;
          kneeY = rect.y + k[1] * rect.height - 10;
        }

        const leftHip = landmarks[23];
        const rightHip = landmarks[24];
        const h = (rightHip && rightHip[2] > (leftHip ? leftHip[2] : 0)) ? rightHip : leftHip;
        if (h && h[2] > 0.2) {
          torsoX = rect.x + h[0] * rect.width + 14;
          torsoY = rect.y + h[1] * rect.height - 24;
        }
      } else {
        kneeX = this.displayWidth - 130;
        kneeY = 48;
        torsoX = this.displayWidth - 130;
        torsoY = 78;
      }

      const drawPill = (text, x, y, bg, border, textColor) => {
        ctx.save();
        ctx.font = 'bold 12px monospace';
        const paddingH = 8;
        const pillH = 22;
        const textMetrics = ctx.measureText(text);
        const pillW = textMetrics.width + paddingH * 2;

        const clampedX = Math.max(10, Math.min(this.displayWidth - pillW - 12, x));
        const clampedY = Math.max(10, Math.min(this.displayHeight - pillH - 12, y));

        ctx.fillStyle = bg;
        ctx.strokeStyle = border;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(clampedX, clampedY, pillW, pillH, 4);
        } else {
          ctx.rect(clampedX, clampedY, pillW, pillH);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = textColor;
        ctx.textBaseline = 'middle';
        ctx.fillText(text, clampedX + paddingH, clampedY + pillH / 2);
        ctx.restore();
      };

      if (kneeX !== undefined && kneeY !== undefined) {
        const isDepthPass = kneeAngle <= 105.0;
        const kneeBg = isDepthPass ? 'rgba(6, 78, 59, 0.9)' : 'rgba(15, 23, 42, 0.85)';
        const kneeBorder = isDepthPass ? '#10b981' : 'rgba(56, 189, 248, 0.5)';
        const kneeTextColor = isDepthPass ? '#6ee7b7' : '#38bdf8';
        drawPill(`膝角: ${kneeAngle.toFixed(1)}°`, kneeX, kneeY, kneeBg, kneeBorder, kneeTextColor);
      }

      if (torsoX !== undefined && torsoY !== undefined) {
        const isLeanWarn = torsoAngle > 45.0;
        const torsoBg = isLeanWarn ? 'rgba(127, 29, 29, 0.9)' : 'rgba(15, 23, 42, 0.85)';
        const torsoBorder = isLeanWarn ? '#ef4444' : 'rgba(251, 146, 60, 0.5)';
        const torsoTextColor = isLeanWarn ? '#fca5a5' : '#fb923c';
        drawPill(`前倾: ${torsoAngle.toFixed(1)}°`, torsoX, torsoY, torsoBg, torsoBorder, torsoTextColor);
      }
    }
  }

  // 挂载到统一命名空间与全局
  global.SquatDemo = global.SquatDemo || {};
  global.SquatDemo.SkeletonRenderer = SkeletonRenderer;
  global.SkeletonRenderer = SkeletonRenderer;
})(typeof window !== 'undefined' ? window : this);
