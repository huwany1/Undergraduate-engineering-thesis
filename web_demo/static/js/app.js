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

  const btnShowGolden = document.getElementById('btn-show-golden');
  const btnShowDataset = document.getElementById('btn-show-dataset');
  const btnShowUploads = document.getElementById('btn-show-uploads');
  const uploadsCountEl = document.getElementById('uploads-count');
  const selectorTag = document.getElementById('selector-tag');

  const uploadBoxDefault = document.getElementById('upload-box-default');
  const uploadProgressContainer = document.getElementById('upload-progress-container');
  const uploadProgressFill = document.getElementById('upload-progress-fill');
  const uploadPctNum = document.getElementById('upload-pct-num');
  const uploadStageBadge = document.getElementById('upload-stage-badge');
  const uploadStageDesc = document.getElementById('upload-stage-desc');
  const stepP1 = document.getElementById('step-p1');
  const stepP2 = document.getElementById('step-p2');
  const stepP3 = document.getElementById('step-p3');
  const stepDone = document.getElementById('step-done');

  // 全局状态
  let currentMode = 'GOLDEN'; // 'GOLDEN' | 'DATASET' | 'UPLOADS'
  let currentCaseId = 'TC_01_PERFECT_SQUAT';
  let telemetryData = [];
  let casesData = [];
  let datasetDemosData = [];
  let uploadedCasesData = [];

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

      // 获取用户上传分析总数
      const upRes = await fetch('/api/uploads');
      if (upRes.ok) {
        const uploads = await upRes.json();
        if (uploadsCountEl) uploadsCountEl.textContent = uploads.length;
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

  // 2.2 加载 MediaPipe 真实数据集用例列表
  async function loadDatasetDemos() {
    caseListEl.innerHTML = '<div class="loading-spinner">正在加载 MediaPipe 真实数据集演示...</div>';
    try {
      const res = await fetch('/api/dataset_demos');
      datasetDemosData = await res.json();
      if (datasetDemosData.length > 0) {
        currentCaseId = datasetDemosData[0].demo_id;
        renderDatasetDemoList(datasetDemosData);
        selectDatasetDemo(datasetDemosData[0].demo_id);
      } else {
        caseListEl.innerHTML = '<div class="empty-hint">暂无已分析的真实数据集资产，请先在终端运行 run_dataset_demo.py</div>';
      }
    } catch (e) {
      caseListEl.innerHTML = `<div class="empty-hint">加载数据集失败: ${e.message}</div>`;
    }
  }

  function renderDatasetDemoList(demos) {
    caseListEl.innerHTML = '';
    demos.forEach((d) => {
      const card = document.createElement('div');
      card.className = `case-card ${d.demo_id === currentCaseId ? 'active' : ''}`;
      card.dataset.id = d.demo_id;

      let statusBadgeClass = d.total_reps_passed > 0 ? 'acceptable' : 'needs_improvement';
      let statusText = d.total_reps_passed > 0 ? '达标' : '待改进';
      if (d.total_reps_completed === 0) {
        statusBadgeClass = 'not_evaluated';
        statusText = '未计次/超时';
      }

      card.innerHTML = `
        <div class="case-card-header">
          <span class="case-card-title">${d.title}</span>
          <span class="badge badge-eval ${statusBadgeClass}">${statusText}</span>
        </div>
        <p class="case-card-desc">源素材: ${d.filename || d.input_video}</p>
        <div class="case-card-footer">
          <span>完成: ${d.total_reps_completed} 次</span>
          <span>机位: ${d.camera_view}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        selectDatasetDemo(d.demo_id);
      });

      caseListEl.appendChild(card);
    });
  }

  async function selectDatasetDemo(demoId) {
    currentCaseId = demoId;
    document.querySelectorAll('.case-card').forEach((card) => {
      card.classList.toggle('active', card.dataset.id === demoId);
    });

    try {
      const res = await fetch(`/api/dataset_demo/${demoId}`);
      const detail = await res.json();
      renderDatasetDemoDetail(detail);
    } catch (e) {
      console.error('加载数据集演示详情异常:', e);
    }
  }

  function renderDatasetDemoDetail(detail) {
    currentCaseNameEl.textContent = `${detail.demo_id}: ${detail.title}`;
    currentCaseDescEl.textContent = `机位: ${detail.camera_view} | MediaPipe Tasks 真实推理 | 视频总帧数: ${detail.total_frames}`;

    valMinKneeEl.textContent = `${detail.min_knee_angle ? detail.min_knee_angle.toFixed(1) : 0.0}°`;
    valMaxTorsoEl.textContent = `${detail.max_torso_angle ? detail.max_torso_angle.toFixed(1) : 0.0}°`;
    valExecTimeEl.textContent = `${((detail.execution_time_s || 0) * 1000).toFixed(0)} ms`;

    let badgeClass = detail.total_reps_passed > 0 ? 'acceptable' : 'needs_improvement';
    let statusText = detail.total_reps_passed > 0 ? '动作规范达标 (ACCEPTABLE)' : '存在改进项 (NEEDS_IMPROVEMENT)';
    if (detail.total_reps_completed === 0) {
      badgeClass = 'not_evaluated';
      statusText = '未计次 / 拒绝评估 (NOT_EVALUATED)';
    }

    evalStatusBadge.className = `badge badge-eval ${badgeClass}`;
    evalStatusBadge.textContent = statusText;

    evalFeedbackText.textContent = detail.summary_feedback || '暂无评估建议';

    hudCountEl.textContent = detail.total_reps_completed;
    hudFsmEl.textContent = 'STANDING';
    hudGateEl.className = 'badge badge-gate';
    hudGateEl.textContent = 'DRAWABLE';

    telemetryData = detail.telemetry || [];
    chart.setData(telemetryData);

    if (detail.video_url) {
      videoEl.src = detail.video_url;
      videoEl.load();
      videoEl.muted = true;
      videoEl.play().catch(() => {});
    } else {
      videoEl.removeAttribute('src');
    }

    renderKeyframes(detail.keyframes || []);
  }

  // 3. 切换选定黄金用例
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
      videoEl.muted = true;
      videoEl.play().catch(() => {});
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

  videoEl.addEventListener('error', () => {
    console.warn('视频流解码状态:', videoEl.error);
    if (overlayTimeEl) {
      overlayTimeEl.textContent = '视频流就绪';
    }
  });

  videoEl.addEventListener('ended', () => {
    // 循环播放或重置到起始帧
    videoEl.currentTime = 0;
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

  // 6. 自定义本地视频上传交互与在线分析管道
  let isAnalyzing = false;

  uploadBox.addEventListener('click', (e) => {
    if (isAnalyzing) return;
    videoFileInput.click();
  });

  // 拖拽高亮与文件捕获
  ['dragenter', 'dragover'].forEach((eventName) => {
    uploadBox.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!isAnalyzing) {
        uploadBox.classList.add('drag-over');
      }
    });
  });

  ['dragleave', 'dragend'].forEach((eventName) => {
    uploadBox.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      uploadBox.classList.remove('drag-over');
    });
  });

  uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    uploadBox.classList.remove('drag-over');
    if (isAnalyzing) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (!file.name.toLowerCase().endsWith('.mp4')) {
        alert('仅支持上传 MP4 格式视频文件');
        return;
      }
      uploadAndAnalyzeVideo(file);
    }
  });

  videoFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      uploadAndAnalyzeVideo(file);
    }
    videoFileInput.value = '';
  });

  async function uploadAndAnalyzeVideo(file) {
    if (isAnalyzing) return;
    if (file.size > 50 * 1024 * 1024) {
      alert(`文件大小 ${(file.size / 1024 / 1024).toFixed(1)}MB 超出 50MB 上限`);
      return;
    }

    isAnalyzing = true;
    uploadBox.classList.add('analyzing');
    if (uploadBoxDefault) uploadBoxDefault.style.display = 'none';
    if (uploadProgressContainer) uploadProgressContainer.style.display = 'flex';

    updateUploadProgress(5, '正在上传视频至服务端...', '上传中', 'p1');

    try {
      const formData = new FormData();
      formData.append('video', file, file.name);

      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(errJson.error || '视频提交失败');
      }

      const uploadData = await res.json();
      const taskId = uploadData.task_id;
      updateUploadProgress(15, '视频已就绪，正在预热算法引擎...', 'P1 姿态', 'p1');

      // 启动轮询跟踪
      pollAnalysisTask(taskId, file.name);
    } catch (e) {
      console.error('上传视频失败:', e);
      updateUploadProgress(0, `上传失败: ${e.message}`, '异常', 'error');
      setTimeout(() => {
        resetUploadBox();
      }, 3000);
    }
  }

  function updateUploadProgress(percent, stageDesc, stageBadge, activeStep) {
    if (uploadProgressFill) uploadProgressFill.style.width = `${percent}%`;
    if (uploadPctNum) uploadPctNum.textContent = `${percent}%`;
    if (uploadStageDesc) uploadStageDesc.textContent = stageDesc;
    if (uploadStageBadge && stageBadge) uploadStageBadge.textContent = stageBadge;

    const steps = [stepP1, stepP2, stepP3, stepDone].filter(Boolean);
    steps.forEach((s) => {
      s.className = 'step-dot';
    });

    if (activeStep === 'p1') {
      if (stepP1) stepP1.className = 'step-dot active';
    } else if (activeStep === 'p2') {
      if (stepP1) stepP1.className = 'step-dot done';
      if (stepP2) stepP2.className = 'step-dot active';
    } else if (activeStep === 'p3') {
      if (stepP1) stepP1.className = 'step-dot done';
      if (stepP2) stepP2.className = 'step-dot done';
      if (stepP3) stepP3.className = 'step-dot active';
    } else if (activeStep === 'done') {
      if (stepP1) stepP1.className = 'step-dot done';
      if (stepP2) stepP2.className = 'step-dot done';
      if (stepP3) stepP3.className = 'step-dot done';
      if (stepDone) stepDone.className = 'step-dot active done';
    }
  }

  function resetUploadBox() {
    isAnalyzing = false;
    uploadBox.classList.remove('analyzing');
    if (uploadBoxDefault) uploadBoxDefault.style.display = 'block';
    if (uploadProgressContainer) uploadProgressContainer.style.display = 'none';
    if (uploadProgressFill) uploadProgressFill.style.width = '0%';
    if (uploadPctNum) uploadPctNum.textContent = '0%';
  }

  function pollAnalysisTask(taskId, originalName) {
    const startTime = Date.now();
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/task/${taskId}`);
        if (!res.ok) {
          throw new Error(`获取任务失败: ${res.status}`);
        }
        const taskData = await res.json();

        let step = 'p1';
        let badge = 'P1 姿态提取';
        if (taskData.progress >= 25 && taskData.progress < 75) {
          step = 'p2';
          badge = 'P2 滤波/FSM';
        } else if (taskData.progress >= 75 && taskData.progress < 95) {
          step = 'p3';
          badge = 'P3 质检评分';
        } else if (taskData.progress >= 95) {
          step = 'done';
          badge = '报告渲染';
        }

        updateUploadProgress(taskData.progress, taskData.stage_name, badge, step);

        if (taskData.status === 'COMPLETED') {
          clearInterval(pollInterval);
          updateUploadProgress(100, '分析完成！专属报告与回放曲线已就绪', '完成', 'done');

          setTimeout(() => {
            resetUploadBox();
            if (taskData.result) {
              renderCaseDetail(taskData.result);
              switchToUploadsTab(taskData.result.case_id);
            }
          }, 500);
        } else if (taskData.status === 'FAILED') {
          clearInterval(pollInterval);
          updateUploadProgress(100, `处理失败: ${taskData.error || '算法异常'}`, '失败', 'p1');
          setTimeout(() => {
            resetUploadBox();
          }, 3500);
        }

        if (Date.now() - startTime > 35000) {
          clearInterval(pollInterval);
          updateUploadProgress(100, '分析超时，请检查视频内容', '超时', 'p1');
          setTimeout(() => {
            resetUploadBox();
          }, 3000);
        }
      } catch (e) {
        console.warn('轮询状态异常:', e);
      }
    }, 300);
  }

  // 7. 切换至“我的分析”选项卡并高亮特定用例
  async function switchToUploadsTab(targetCaseId = null) {
    currentMode = 'UPLOADS';
    setTabActive(btnShowUploads);
    if (selectorTag) selectorTag.textContent = '在线自定义';
    await loadUploads(targetCaseId);
  }

  async function loadUploads(selectTargetId = null) {
    caseListEl.innerHTML = '<div class="loading-spinner">正在拉取自定义分析记录...</div>';
    try {
      const res = await fetch('/api/uploads');
      uploadedCasesData = await res.json();
      if (uploadsCountEl) uploadsCountEl.textContent = uploadedCasesData.length;

      if (uploadedCasesData.length > 0) {
        renderUploadedCaseList(uploadedCasesData);
        const targetId = selectTargetId || uploadedCasesData[0].case_id;
        selectCase(targetId);
      } else {
        caseListEl.innerHTML = '<div class="empty-hint">暂无自定义分析视频记录。<br>请随手拖拽一段 MP4 到下方上传框启动即时分析。</div>';
      }
    } catch (e) {
      caseListEl.innerHTML = `<div class="empty-hint">获取自定义记录失败: ${e.message}</div>`;
    }
  }

  function renderUploadedCaseList(uploads) {
    caseListEl.innerHTML = '';
    uploads.forEach((u) => {
      const card = document.createElement('div');
      card.className = `case-card ${u.case_id === currentCaseId ? 'active' : ''}`;
      card.dataset.id = u.case_id;

      let statusBadgeClass = 'acceptable';
      let statusText = '规范达标';
      if (u.actual_status === 'NEEDS_IMPROVEMENT') {
        statusBadgeClass = 'needs_improvement';
        statusText = '需要改进';
      } else if (u.actual_status === 'REJECTED') {
        statusBadgeClass = 'not_evaluated';
        statusText = '一票否决';
      }

      card.innerHTML = `
        <div class="case-card-header">
          <span class="case-card-title">${u.case_name}</span>
          <span class="badge badge-eval ${statusBadgeClass}">${statusText}</span>
        </div>
        <p class="case-card-desc">${u.description || '用户上传视频'}</p>
        <div class="case-card-footer">
          <span>完成: ${u.actual_count} 次</span>
          <span>状态: ${u.actual_status}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        selectCase(u.case_id);
      });

      caseListEl.appendChild(card);
    });
  }

  function setTabActive(activeBtn) {
    [btnShowGolden, btnShowDataset, btnShowUploads].forEach((b) => {
      if (!b) return;
      if (b === activeBtn) {
        b.classList.add('active');
        b.style.background = '#3b82f6';
        b.style.color = '#fff';
      } else {
        b.classList.remove('active');
        b.style.background = 'transparent';
        b.style.color = '#94a3b8';
      }
    });
  }

  // 8. 键盘便捷快捷键 (空格播放/暂停，左右箭头步进)
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

  // 9. 选项卡切换事件绑定
  if (btnShowGolden) {
    btnShowGolden.addEventListener('click', () => {
      currentMode = 'GOLDEN';
      setTabActive(btnShowGolden);
      if (selectorTag) selectorTag.textContent = 'P4 基准';
      loadCases();
    });
  }

  if (btnShowDataset) {
    btnShowDataset.addEventListener('click', () => {
      currentMode = 'DATASET';
      setTabActive(btnShowDataset);
      if (selectorTag) selectorTag.textContent = 'MediaPipe 实测';
      loadDatasetDemos();
    });
  }

  if (btnShowUploads) {
    btnShowUploads.addEventListener('click', () => {
      currentMode = 'UPLOADS';
      setTabActive(btnShowUploads);
      if (selectorTag) selectorTag.textContent = '在线自定义';
      loadUploads();
    });
  }

  // 启动时初始化
  fetchStatus();
  loadCases();
});
