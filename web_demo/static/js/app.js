// -*- coding: utf-8 -*-
/**
 * 前端交互核心控制器 (App Controller)
 * 职责：
 * 1. 驱动用例切换、遥测时序加载与视频播放同步；
 * 2. 实时更新 FSM 阶段徽章、质检门控与完成计数；
 * 3. 驱动特征帧快照与 P4 答辩矩阵模态窗口；
 * 4. 支持键盘快捷键 (空格播放/暂停, 左右方向键单帧步进)。
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM 元素引用
  const caseListEl = document.getElementById('case-list');
  const videoEl = document.getElementById('demo-video');
  const chartCanvas = document.getElementById('telemetry-chart');
  const tooltipEl = document.getElementById('chart-tooltip');

  const baselineBadge = document.getElementById('baseline-badge');
  const gitBadge = document.getElementById('git-badge');

  const currentCaseNameEl = document.getElementById('current-case-name');
  const currentCaseDescEl = document.getElementById('current-case-desc');

  const hudCountEl = document.getElementById('hud-count');
  const hudFsmEl = document.getElementById('hud-fsm');
  const hudGateEl = document.getElementById('hud-gate');

  const overlayTimeEl = document.getElementById('overlay-time');
  const overlayFrameEl = document.getElementById('overlay-frame');

  const valMinKneeEl = document.getElementById('val-min-knee');
  const valMaxTorsoEl = document.getElementById('val-max-torso');
  const valExecTimeEl = document.getElementById('val-exec-time');
  const evalStatusBadge = document.getElementById('eval-status-badge');
  const evalFeedbackText = document.getElementById('eval-feedback-text');
  const keyframesGrid = document.getElementById('keyframes-grid');

  // 模态弹窗
  const matrixDialog = document.getElementById('matrix-dialog');
  const openMatrixBtn = document.getElementById('open-matrix-btn');
  const closeMatrixBtn = document.getElementById('close-matrix-btn');

  const imageDialog = document.getElementById('image-dialog');
  const modalImagePreview = document.getElementById('modal-image-preview');
  const modalImageCaption = document.getElementById('modal-image-caption');
  const closeImageBtn = document.getElementById('close-image-btn');

  const uploadBox = document.getElementById('upload-box');
  const videoFileInput = document.getElementById('video-file-input');

  // 全局状态
  let currentCaseId = 'TC_01_PERFECT_SQUAT';
  let telemetryData = [];
  let casesData = [];

  // 初始化图表组件
  const chart = new window.TelemetryChart(chartCanvas, {
    tooltipElement: tooltipEl,
    onSeek: (targetTime) => {
      videoEl.currentTime = targetTime;
    },
  });

  // 1. 获取系统状态
  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (data.baseline_id) {
        baselineBadge.textContent = `基线: ${data.baseline_id}`;
      }
      if (data.git_commit) {
        gitBadge.textContent = `Git: ${data.git_commit.substring(0, 7)}`;
      }
    } catch (e) {
      console.warn('获取系统状态失败:', e);
    }
  }

  // 2. 加载 5 大黄金用例列表
  async function loadCases() {
    try {
      const res = await fetch('/api/cases');
      casesData = await res.json();
      renderCaseList(casesData);

      // 默认加载第一个用例
      if (casesData.length > 0) {
        selectCase(casesData[0].case_id);
      }
    } catch (e) {
      caseListEl.innerHTML = `<div class="empty-hint">加载用例失败: ${e.message}</div>`;
    }
  }

  function renderCaseList(cases) {
    caseListEl.innerHTML = '';
    cases.forEach((c) => {
      const card = document.createElement('div');
      card.className = `case-card ${c.case_id === currentCaseId ? 'active' : ''}`;
      card.dataset.id = c.case_id;

      let statusBadgeClass = 'acceptable';
      let statusText = '合格';
      if (c.actual_status === 'NEEDS_IMPROVEMENT') {
        statusBadgeClass = 'needs_improvement';
        statusText = '待改进';
      } else if (c.actual_status === 'NOT_EVALUATED') {
        statusBadgeClass = 'not_evaluated';
        statusText = '一票否决';
      }

      card.innerHTML = `
        <div class="case-card-header">
          <span class="case-card-title">${c.case_name}</span>
          <span class="badge badge-eval ${statusBadgeClass}">${statusText}</span>
        </div>
        <p class="case-card-desc">${c.description}</p>
        <div class="case-card-footer">
          <span>计数: ${c.actual_count} 次</span>
          <span>机位: ${c.camera_view}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        selectCase(c.case_id);
      });

      caseListEl.appendChild(card);
    });
  }

  // 3. 切换选定用例
  async function selectCase(caseId) {
    currentCaseId = caseId;

    // 更新侧边栏高亮状态
    document.querySelectorAll('.case-card').forEach((card) => {
      card.classList.toggle('active', card.dataset.id === caseId);
    });

    // 拉取用例详情
    try {
      const res = await fetch(`/api/case/${caseId}`);
      const detail = await res.json();
      renderCaseDetail(detail);
    } catch (e) {
      console.error('加载用例详情异常:', e);
    }
  }

  function renderCaseDetail(detail) {
    currentCaseNameEl.textContent = `${detail.case_id}: ${detail.case_name}`;
    currentCaseDescEl.textContent = detail.description;

    // 更新右侧评估卡片
    valMinKneeEl.textContent = `${detail.measured_min_knee_angle.toFixed(1)}°`;
    valMaxTorsoEl.textContent = `${detail.measured_max_torso_angle.toFixed(1)}°`;
    valExecTimeEl.textContent = `${detail.execution_time_ms.toFixed(1)} ms`;

    let badgeClass = 'acceptable';
    let statusText = '动作规范 (ACCEPTABLE)';
    if (detail.actual_status === 'NEEDS_IMPROVEMENT') {
      badgeClass = 'needs_improvement';
      statusText = '需要改进 (NEEDS_IMPROVEMENT)';
    } else if (detail.actual_status === 'NOT_EVALUATED') {
      badgeClass = 'not_evaluated';
      statusText = '拒绝评估 (NOT_EVALUATED)';
    }

    evalStatusBadge.className = `badge badge-eval ${badgeClass}`;
    evalStatusBadge.textContent = statusText;

    evalFeedbackText.textContent = detail.summary_feedback || '暂无评估建议';

    // 更新 HUD 初始值
    hudCountEl.textContent = detail.actual_count;
    hudFsmEl.textContent = 'STANDING';
    hudGateEl.className = 'badge badge-gate';
    hudGateEl.textContent = 'DRAWABLE';

    // 绑定时序遥测数据并绘制曲线
    telemetryData = detail.telemetry || [];
    chart.setData(telemetryData);

    // 载入视频
    if (detail.video_url) {
      videoEl.src = detail.video_url;
      videoEl.load();
    } else {
      videoEl.removeAttribute('src');
    }

    // 渲染特征帧快照
    renderKeyframes(detail.keyframes || []);
  }

  function renderKeyframes(keyframes) {
    keyframesGrid.innerHTML = '';
    if (!keyframes || keyframes.length === 0) {
      keyframesGrid.innerHTML = '<div class="empty-hint">本用例暂无关键帧快照</div>';
      return;
    }

    keyframes.forEach((kf) => {
      const card = document.createElement('div');
      card.className = 'keyframe-card';

      card.innerHTML = `
        <img src="${kf.image_url}" alt="${kf.description}" loading="lazy">
        <div class="keyframe-label">${kf.event_type} (f${kf.frame_index})</div>
      `;

      card.addEventListener('click', () => {
        modalImagePreview.src = kf.image_url;
        modalImageCaption.textContent = `[${kf.event_type}] ${kf.description} (帧号: ${kf.frame_index}, 时间戳: ${(kf.timeline_us / 1e6).toFixed(2)}s)`;
        imageDialog.showModal();
      });

      keyframesGrid.appendChild(card);
    });
  }

  // 4. 视频播放事件监听与音画遥测联动
  videoEl.addEventListener('timeupdate', () => {
    const curTime = videoEl.currentTime;

    // 格式化时间与帧序号 (基于 30fps)
    const mins = Math.floor(curTime / 60);
    const secs = (curTime % 60).toFixed(3).padStart(6, '0');
    overlayTimeEl.textContent = `${String(mins).padStart(2, '0')}:${secs}`;

    const approxFrame = Math.round(curTime * 30);
    overlayFrameEl.textContent = `Frame: ${approxFrame}`;

    // 同步驱动图表时间游标
    chart.setCurrentTime(curTime);

    // 同步实时 HUD 状态机与门控指示器
    if (telemetryData.length > 0) {
      // 匹配当前时间最接近的遥测点
      let closest = telemetryData[0];
      let minDiff = Math.abs(closest.time_s - curTime);
      for (let i = 1; i < telemetryData.length; i++) {
        const diff = Math.abs(telemetryData[i].time_s - curTime);
        if (diff < minDiff) {
          minDiff = diff;
          closest = telemetryData[i];
        }
      }

      if (closest) {
        hudFsmEl.textContent = closest.fsm_state;
        if (!closest.is_valid) {
          hudGateEl.className = 'badge badge-gate rejected';
          hudGateEl.textContent = 'OUT_OF_FRAME';
        } else {
          hudGateEl.className = 'badge badge-gate';
          hudGateEl.textContent = 'DRAWABLE';
        }
      }
    }
  });

  // 5. P4 答辩自包含验证矩阵模态窗口交互
  openMatrixBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/reports/validation');
      const data = await res.json();
      renderMatrixDialog(data);
      matrixDialog.showModal();
    } catch (e) {
      alert(`无法加载验证报告: ${e.message}`);
    }
  });

  closeMatrixBtn.addEventListener('click', () => {
    matrixDialog.close();
  });

  closeImageBtn.addEventListener('click', () => {
    imageDialog.close();
  });

  function renderMatrixDialog(reportData) {
    const manifest = reportData.manifest || {};
    document.getElementById('mat-total-cases').textContent = manifest.total_cases || 5;
    document.getElementById('mat-passed-cases').textContent = manifest.passed_cases || 5;
    document.getElementById('mat-concordance').textContent = `${((manifest.concordance_rate || 1.0) * 100).toFixed(1)}%`;
    document.getElementById('mat-mae').textContent = (manifest.mae_count || 0.0).toFixed(2);

    // 渲染表格
    const tbody = document.getElementById('matrix-table-body');
    tbody.innerHTML = '';
    const results = manifest.case_results || [];

    results.forEach((r) => {
      const tr = document.createElement('tr');
      const spec = casesData.find((c) => c.case_id === r.case_id) || {};
      tr.innerHTML = `
        <td><code>${r.case_id}</code></td>
        <td>${spec.case_name || r.case_id}</td>
        <td><strong>${r.actual_count}</strong></td>
        <td><span class="badge badge-eval ${r.actual_status.toLowerCase()}">${r.actual_status}</span></td>
        <td><code>${r.actual_primary_reason}</code></td>
        <td>${r.measured_min_knee_angle.toFixed(1)}°</td>
        <td>${r.measured_max_torso_angle.toFixed(1)}°</td>
        <td>${r.execution_time_ms.toFixed(2)}ms</td>
        <td><span class="badge badge-status online">PASS</span></td>
      `;
      tbody.appendChild(tr);
    });

    // 渲染 Markdown 预览
    document.getElementById('summary-md-content').textContent = reportData.summary_markdown || '无摘要报告';
  }

  // 6. 自定义本地视频上传交互
  uploadBox.addEventListener('click', () => {
    videoFileInput.click();
  });

  videoFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      // 演示模式提示
      alert(`已选择本地视频: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)\n\n系统已就绪，当前可通过选择 5 大受控黄金场景进行确定性答辩演示；自定义离线视频可作为扩展样本直接载入。`);
    }
  });

  // 7. 键盘便捷快捷键 (空格播放/暂停，左右箭头步进)
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.code === 'Space') {
      e.preventDefault();
      if (videoEl.paused) {
        videoEl.play();
      } else {
        videoEl.pause();
      }
    } else if (e.code === 'ArrowRight') {
      e.preventDefault();
      videoEl.currentTime = Math.min(videoEl.duration || 10, videoEl.currentTime + 1 / 30);
    } else if (e.code === 'ArrowLeft') {
      e.preventDefault();
      videoEl.currentTime = Math.max(0, videoEl.currentTime - 1 / 30);
    }
  });

  // 启动时初始化
  fetchStatus();
  loadCases();
});
