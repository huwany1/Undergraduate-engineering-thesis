// -*- coding: utf-8 -*-
/**
 * 纯原生 Canvas 双通道时序运动学遥测图表 (Vanilla Telemetry Chart)
 * 功能：
 * 1. 绘制膝关节角与躯干前倾角时序曲线；
 * 2. 绘制 105° 深度合格门限与 45° 前倾预警门限；
 * 3. 动态绘制与视频播放同步的垂直游标；
 * 4. 支持鼠标点击/拖拽快速定位 (Seek) 到指定时间。
 */

class TelemetryChart {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d');
    this.data = []; // [{ time_s, knee_angle, torso_angle, fsm_state, is_valid }]
    this.currentTime = 0;
    this.duration = 1;
    this.onSeekCallback = options.onSeek || null;
    this.tooltipEl = options.tooltipElement || null;

    this.padding = { top: 20, right: 30, bottom: 25, left: 40 };
    this.repHighlight = null; // { startSec, endSec, bottomSec, repLabel }

    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.resetTransform();
    this.ctx.scale(dpr, dpr);
    this.cssWidth = rect.width;
    this.cssHeight = rect.height;
    this.render();
  }

  setData(telemetryPoints) {
    this.data = telemetryPoints || [];
    if (this.data.length > 0) {
      this.duration = Math.max(...this.data.map(p => p.time_s), 0.1);
    } else {
      this.duration = 1;
    }
    this.render();
  }

  setCurrentTime(timeSec) {
    this.currentTime = timeSec;
    this.render();
  }

  setRepHighlight(startSec, endSec, bottomSec = null, repLabel = '') {
    this.repHighlight = { startSec, endSec, bottomSec, repLabel };
    this.render();
  }

  clearRepHighlight() {
    this.repHighlight = null;
    this.render();
  }

  appendPoint(point) {
    if (!point) return;
    this.data.push(point);
    this.duration = Math.max(this.duration, (point.time_s || 0) + 0.1);
    this.currentTime = point.time_s || 0;
    this.render();
  }

  clear() {
    this.data = [];
    this.duration = 1;
    this.currentTime = 0;
    this.render();
  }

  initEvents() {
    let isDragging = false;

    const handleSeek = (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const chartWidth = this.cssWidth - this.padding.left - this.padding.right;
      if (chartWidth <= 0) return;

      const ratio = Math.max(0, Math.min(1, (x - this.padding.left) / chartWidth));
      const targetTime = ratio * this.duration;

      if (this.onSeekCallback) {
        this.onSeekCallback(targetTime);
      }
    };

    this.canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      handleSeek(e);
    });

    window.addEventListener('mousemove', (e) => {
      if (isDragging) {
        handleSeek(e);
      }
    });

    window.addEventListener('mouseup', () => {
      isDragging = false;
    });

    // 鼠标悬停显示 tooltip
    this.canvas.addEventListener('mousemove', (e) => {
      if (!this.data || this.data.length === 0 || !this.tooltipEl) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const chartWidth = this.cssWidth - this.padding.left - this.padding.right;

      if (x < this.padding.left || x > this.cssWidth - this.padding.right) {
        this.tooltipEl.style.display = 'none';
        return;
      }

      const ratio = (x - this.padding.left) / chartWidth;
      const hoverTime = ratio * this.duration;

      // 寻找最近的数据点
      let closest = this.data[0];
      let minDiff = Math.abs(closest.time_s - hoverTime);
      for (let i = 1; i < this.data.length; i++) {
        const diff = Math.abs(this.data[i].time_s - hoverTime);
        if (diff < minDiff) {
          minDiff = diff;
          closest = this.data[i];
        }
      }

      if (closest) {
        this.tooltipEl.style.display = 'block';
        this.tooltipEl.innerHTML = `
          <div>时间: ${closest.time_s.toFixed(2)}s | 帧: ${closest.frame_index}</div>
          <div style="color: #06b6d4;">膝关节角: ${closest.knee_angle.toFixed(1)}°</div>
          <div style="color: #f59e0b;">躯干前倾: ${closest.torso_angle.toFixed(1)}°</div>
          <div style="color: #94a3b8; font-size: 0.7rem;">阶段: ${closest.fsm_state}</div>
        `;
      }
    });

    this.canvas.addEventListener('mouseleave', () => {
      if (this.tooltipEl) {
        this.tooltipEl.style.display = 'none';
      }
    });
  }

  render() {
    const ctx = this.ctx;
    const w = this.cssWidth;
    const h = this.cssHeight;
    const p = this.padding;

    ctx.clearRect(0, 0, w, h);

    const chartW = w - p.left - p.right;
    const chartH = h - p.top - p.bottom;

    if (chartW <= 0 || chartH <= 0) return;

    // 坐标系映射：角度范围 0° ~ 180°
    const minAngle = 0;
    const maxAngle = 180;

    const getX = (t) => p.left + (t / this.duration) * chartW;
    const getY = (deg) => p.top + chartH - ((deg - minAngle) / (maxAngle - minAngle)) * chartH;

    // 1. 绘制网格与刻度
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';

    const yTicks = [0, 45, 90, 105, 135, 180];
    for (const tick of yTicks) {
      const y = getY(tick);
      ctx.beginPath();
      ctx.moveTo(p.left, y);
      ctx.lineTo(w - p.right, y);
      ctx.stroke();

      ctx.fillText(`${tick}°`, p.left - 6, y + 3);
    }

    // X 轴时间标签
    ctx.textAlign = 'center';
    const xStep = Math.max(0.5, Math.round(this.duration / 5 * 2) / 2);
    for (let t = 0; t <= this.duration; t += xStep) {
      const x = getX(t);
      ctx.fillText(`${t.toFixed(1)}s`, x, h - 8);
    }

    // 2. 绘制参考辅助基准线
    // 105° 深度合格基准线 (深蹲及格)
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = 'rgba(6, 182, 212, 0.45)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(p.left, getY(105));
    ctx.lineTo(w - p.right, getY(105));
    ctx.stroke();

    // 45° 躯干前倾基准线 (过度前倾预警)
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.45)';
    ctx.beginPath();
    ctx.moveTo(p.left, getY(45));
    ctx.lineTo(w - p.right, getY(45));
    ctx.stroke();
    ctx.restore();

    if (!this.data || this.data.length === 0) {
      ctx.fillStyle = '#64748b';
      ctx.textAlign = 'center';
      ctx.fillText('暂无遥测曲线数据', w / 2, h / 2);
      return;
    }

    // 2.5 绘制单次切片聚焦高亮背景带 (Drill-Down Focus Band)
    if (this.repHighlight) {
      const hStart = Math.max(0, this.repHighlight.startSec);
      const hEnd = Math.min(this.duration, this.repHighlight.endSec);
      const xStart = getX(hStart);
      const xEnd = getX(hEnd);
      const bandWidth = Math.max(4, xEnd - xStart);

      ctx.save();
      // 高亮背景光带
      ctx.fillStyle = 'rgba(59, 130, 246, 0.18)';
      ctx.fillRect(xStart, p.top, bandWidth, chartH);

      // 边框虚线
      ctx.strokeStyle = 'rgba(59, 130, 246, 0.8)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(xStart, p.top, bandWidth, chartH);

      // 顶部切片标签提示
      ctx.fillStyle = '#60a5fa';
      ctx.font = 'bold 10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(this.repHighlight.repLabel || '切片聚焦', xStart + 4, p.top + 12);

      // 波谷最低点标记线
      if (this.repHighlight.bottomSec !== null && this.repHighlight.bottomSec !== undefined) {
        const xBottom = getX(this.repHighlight.bottomSec);
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.85)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(xBottom, p.top);
        ctx.lineTo(xBottom, p.top + chartH);
        ctx.stroke();

        ctx.fillStyle = '#f87171';
        ctx.textAlign = 'center';
        ctx.font = 'bold 9px sans-serif';
        ctx.fillText('▼波谷', xBottom, p.top - 4);
      }
      ctx.restore();
    }

    // 3. 绘制膝关节角度曲线 (Knee Angle - Cyan)
    ctx.save();
    ctx.shadowColor = 'rgba(6, 182, 212, 0.45)';
    ctx.shadowBlur = 4;
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#06b6d4';
    ctx.beginPath();
    let started = false;
    for (const pt of this.data) {
      const x = getX(pt.time_s);
      const y = getY(pt.knee_angle);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    ctx.restore();

    // 4. 绘制躯干前倾角曲线 (Torso Angle - Amber)
    ctx.save();
    ctx.shadowColor = 'rgba(245, 158, 11, 0.45)';
    ctx.shadowBlur = 4;
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#f59e0b';
    ctx.beginPath();
    started = false;
    for (const pt of this.data) {
      const x = getX(pt.time_s);
      const y = getY(pt.torso_angle);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    ctx.restore();

    // 5. 绘制当前播放位置的垂直时间游标 (Red/White Playhead)
    const playheadX = getX(Math.min(this.currentTime, this.duration));
    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#f43f5e';
    ctx.shadowColor = 'rgba(244, 63, 94, 0.8)';
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.moveTo(playheadX, p.top);
    ctx.lineTo(playheadX, h - p.bottom);
    ctx.stroke();

    // 游标顶部小三角形指示
    ctx.fillStyle = '#f43f5e';
    ctx.beginPath();
    ctx.moveTo(playheadX - 4, p.top - 4);
    ctx.lineTo(playheadX + 4, p.top - 4);
    ctx.lineTo(playheadX, p.top + 2);
    ctx.fill();
    ctx.restore();
  }
}

window.TelemetryChart = TelemetryChart;
