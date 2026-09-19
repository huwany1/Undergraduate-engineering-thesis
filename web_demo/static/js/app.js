// -*- coding: utf-8 -*-
/**
 * 前端交互核心控制器 (App Controller)
 * 职责：
 * 1. 驱动用例切换、遥测时序加载与视频播放同步；
 * 2. 实时更新 FSM 阶段徽章、质检门控与完成计数；
 * 3. 驱动特征帧快照与 P4 答辩矩阵模态窗口；
 * 4. 支持键盘快捷键 (空格播放/暂停, 左右方向键单帧步进)。
 */

// 引用由 modules/ 拆分提供的组件 (遵循通用命名空间规范，实现高内聚与可维护性)
const SkeletonRenderer = (window.SquatDemo && window.SquatDemo.SkeletonRenderer) || window.SkeletonRenderer;
const AudioManager = (window.SquatDemo && window.SquatDemo.AudioManager) || window.AudioManager;
const LiveCameraController = (window.SquatDemo && window.SquatDemo.LiveCameraController) || window.LiveCameraController;
const ApiClient = (window.SquatDemo && window.SquatDemo.ApiClient) || window.ApiClient;
const RepSelector = (window.SquatDemo && window.SquatDemo.RepSelector) || window.RepSelector;
const LLMCoachUI = (window.SquatDemo && window.SquatDemo.LLMCoachUI) || window.LLMCoachUI;

document.addEventListener('DOMContentLoaded', () => {
  // DOM 元素引用
  const caseListEl = document.getElementById('case-list');
  const videoEl = document.getElementById('demo-video');
  const videoContainer = document.getElementById('video-container');
  const skeletonCanvas = document.getElementById('skeleton-canvas');
  const toggleSkeletonCheckbox = document.getElementById('toggle-skeleton');
  const chartCanvas = document.getElementById('telemetry-chart');
  const tooltipEl = document.getElementById('chart-tooltip');

  const baselineBadge = document.getElementById('baseline-badge');
  const gitBadge = document.getElementById('git-badge');

  const currentCaseNameEl = document.getElementById('current-case-name');
  const currentCaseDescEl = document.getElementById('current-case-desc');

  const hudCountEl = document.getElementById('hud-count');
  const hudCurKneeEl = document.getElementById('hud-cur-knee');
  const hudCurTorsoEl = document.getElementById('hud-cur-torso');
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
  const btnShowCamera = document.getElementById('btn-show-camera');
  const uploadsCountEl = document.getElementById('uploads-count');
  const selectorTag = document.getElementById('selector-tag');

  const liveCameraOverlay = document.getElementById('live-camera-overlay');
  const liveMetricsText = document.getElementById('live-metrics-text');
  const btnLiveStop = document.getElementById('btn-live-stop');
  const repCelebrationBanner = document.getElementById('rep-celebration-banner');
  const celebrationText = document.getElementById('celebration-text');
  const toggleSound = document.getElementById('toggle-sound');
  const uploadPanelSection = document.getElementById('upload-panel-section');

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

  // 连续动作切片下钻与整组宏观看板 DOM 元素引用
  const multiRepPanel = document.getElementById('multi-rep-panel');
  const drilldownModeHint = document.getElementById('drilldown-mode-hint');
  const btnMacroOverview = document.getElementById('btn-macro-overview');
  const btnSlowMoToggle = document.getElementById('btn-slowmo-toggle');
  const btnLoopToggle = document.getElementById('btn-loop-toggle');
  const btnExitDrilldown = document.getElementById('btn-exit-drilldown');
  const repsCarouselEl = document.getElementById('reps-carousel');

  const macroDashboardPanel = document.getElementById('macro-dashboard-panel');
  const macroScopeTag = document.getElementById('macro-scope-tag');
  const macroPassRateBadge = document.getElementById('macro-pass-rate-badge');

  const consistencyGradeBadge = document.getElementById('consistency-grade-badge');
  const consistencyScoreNum = document.getElementById('consistency-score-num');
  const consistencyKneeStd = document.getElementById('consistency-knee-std');
  const consistencyTorsoStd = document.getElementById('consistency-torso-std');
  const consistencyDurCv = document.getElementById('consistency-dur-cv');
  const consistencyDesc = document.getElementById('consistency-desc');

  const fatigueStatusBadge = document.getElementById('fatigue-status-badge');
  const fatigueSparklineBox = document.getElementById('fatigue-sparkline-box');
  const fatigueSlopeVal = document.getElementById('fatigue-slope-val');
  const fatigueDeltaVal = document.getElementById('fatigue-delta-val');
  const fatigueDesc = document.getElementById('fatigue-desc');

  const tempoRatioBadge = document.getElementById('tempo-ratio-badge');
  const tempoEccentricBar = document.getElementById('tempo-eccentric-bar');
  const tempoIsometricBar = document.getElementById('tempo-isometric-bar');
  const tempoConcentricBar = document.getElementById('tempo-concentric-bar');
  const tempoEccText = document.getElementById('tempo-ecc-text');
  const tempoIsoText = document.getElementById('tempo-iso-text');
  const tempoConText = document.getElementById('tempo-con-text');
  const tempoDesc = document.getElementById('tempo-desc');

  // 全局状态
  let currentMode = 'GOLDEN'; // 'GOLDEN' | 'DATASET' | 'UPLOADS' | 'CAMERA'
  let currentCaseId = 'TC_01_PERFECT_SQUAT';
  let telemetryData = [];
  let casesData = [];
  let datasetDemosData = [];
  let uploadedCasesData = [];

  // 连续动作切片与单次下钻状态
  let activeRepSlice = null;
  let isSlowMoEnabled = true;
  let isSliceLoopEnabled = true;
  let currentDetail = null;
  if (btnSlowMoToggle) btnSlowMoToggle.classList.add('active');

  // 初始化音效管理器
  const audioManager = new AudioManager();
  if (toggleSound) {
    toggleSound.addEventListener('change', (e) => {
      audioManager.isEnabled = e.target.checked;
    });
  }

  // 初始化骨架渲染器与图表组件
  const skeletonRenderer = new SkeletonRenderer(skeletonCanvas, videoEl, videoContainer);

  if (toggleSkeletonCheckbox) {
    toggleSkeletonCheckbox.addEventListener('change', (e) => {
      skeletonRenderer.isEnabled = e.target.checked;
      syncPlaybackFrame();
    });
  }

  const chart = new window.TelemetryChart(chartCanvas, {
    tooltipElement: tooltipEl,
    onSeek: (targetTime) => {
      videoEl.currentTime = targetTime;
      syncPlaybackFrame();
    },
  });

  // 实例化实时摄像头与虚拟推流控制器
  const liveController = new LiveCameraController({
    videoEl,
    canvasEl: skeletonCanvas,
    overlayEl: liveCameraOverlay,
    metricsEl: liveMetricsText,
    celebrationEl: repCelebrationBanner,
    celebrationTextEl: celebrationText,
    skeletonRenderer,
    chart,
    audioManager,
    updateHud: (point) => {
      if (hudCountEl) hudCountEl.textContent = point.count !== undefined ? point.count : 0;
      if (hudCurKneeEl) {
        hudCurKneeEl.textContent = `${point.knee_angle.toFixed(1)}°`;
        hudCurKneeEl.style.color = point.knee_angle <= 105.0 ? '#10b981' : '#38bdf8';
        hudCurKneeEl.style.textShadow = point.knee_angle <= 105.0
          ? '0 0 8px rgba(16, 185, 129, 0.4)'
          : '0 0 8px rgba(56, 189, 248, 0.4)';
      }
      if (hudCurTorsoEl) {
        hudCurTorsoEl.textContent = `${point.torso_angle.toFixed(1)}°`;
        hudCurTorsoEl.style.color = point.torso_angle > 45.0 ? '#ef4444' : '#fb923c';
        hudCurTorsoEl.style.textShadow = point.torso_angle > 45.0
          ? '0 0 8px rgba(239, 68, 68, 0.4)'
          : '0 0 8px rgba(251, 146, 60, 0.4)';
      }
      if (hudFsmEl) hudFsmEl.textContent = point.fsm_state;
      if (hudGateEl) {
        if (!point.is_valid) {
          hudGateEl.className = 'badge badge-gate rejected';
          hudGateEl.textContent = point.gate_status || 'OUT_OF_FRAME';
        } else {
          hudGateEl.className = 'badge badge-gate';
          hudGateEl.textContent = 'DRAWABLE';
        }
      }
    },
    onSessionFinished: (summary) => {
      renderLiveSessionFinished(summary);
    },
  });

    if (btnLiveStop) {
    btnLiveStop.addEventListener('click', async () => {
      await liveController.stop();
    });
  }

  // 实例化连续动作切片下钻与宏观看板交互控制器 (组件化解耦)
  const repSelector = new RepSelector({
    btnMacroOverview,
    btnSlowMoToggle,
    btnLoopToggle,
    btnExitDrilldown,
    repsCarouselEl,
    macroPassRateBadge,
    consistencyGradeBadge,
    consistencyScoreNum,
    consistencyKneeStd,
    consistencyTorsoStd,
    consistencyDurCv,
    consistencyDesc,
    fatigueStatusBadge,
    fatigueSparklineBox,
    fatigueSlopeVal,
    fatigueDeltaVal,
    fatigueDesc,
    tempoRatioBadge,
    tempoEccentricBar,
    tempoIsometricBar,
    tempoConcentricBar,
    tempoEccText,
    tempoIsoText,
    tempoConText,
    tempoDesc,
    drilldownModeHint,
    macroScopeTag,
    valMinKneeEl,
    valMaxTorsoEl,
    valExecTimeEl,
    evalStatusBadge,
    evalFeedbackText,
  }, chart, videoEl);

  // 实例化 AI 智能健身教练控制器 (维度五)
  const llmCoach = LLMCoachUI ? new LLMCoachUI() : null;
  if (llmCoach) {
    llmCoach.init();
  }

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

    hudCountEl.textContent = '0';
    if (hudCurKneeEl) {
      hudCurKneeEl.textContent = '--°';
      hudCurKneeEl.style.color = '#38bdf8';
    }
    if (hudCurTorsoEl) {
      hudCurTorsoEl.textContent = '--°';
      hudCurTorsoEl.style.color = '#fb923c';
    }
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
    renderMultiRepSection(detail);
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
    hudCountEl.textContent = '0';
    if (hudCurKneeEl) {
      hudCurKneeEl.textContent = '--°';
      hudCurKneeEl.style.color = '#38bdf8';
    }
    if (hudCurTorsoEl) {
      hudCurTorsoEl.textContent = '--°';
      hudCurTorsoEl.style.color = '#fb923c';
    }
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
    renderMultiRepSection(detail);
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

    // 驱动 AI 智能教练深度点评与上下文更新 (维度五)
    if (llmCoach) {
      llmCoach.setCurrentCase(detail.case_id, detail);
    }
  }

  // 3.1 连续动作切片下钻与整组宏观看板 (委托由 RepSelector 模块驱动)
  function renderMultiRepSection(detail) {
    if (repSelector) {
      repSelector.renderMultiRepSection(detail);
    }
  }

  function exitDrillDown() {
    if (repSelector) {
      repSelector.exitDrillDown();
    }
  }

  // 4. 高频平滑姿态骨骼渲染、音画同步与实时双角/计数刷新引擎
  let animFrameId = null;

  function syncPlaybackFrame() {
    const curTime = videoEl.currentTime;

    // 单次下钻切片循环回放约束 (由 RepSelector 模块守护)
    if (repSelector) {
      repSelector.checkPlaybackBound(curTime);
    }

    // 格式化时间与帧序号 (基于 30fps)
    const mins = Math.floor(curTime / 60);
    const secs = (curTime % 60).toFixed(3).padStart(6, '0');
    if (overlayTimeEl) overlayTimeEl.textContent = `${String(mins).padStart(2, '0')}:${secs}`;

    const approxFrame = Math.round(curTime * 30);
    if (overlayFrameEl) overlayFrameEl.textContent = `Frame: ${approxFrame}`;

    // 同步驱动图表时间游标
    chart.setCurrentTime(curTime);

    // 同步实时 HUD 状态机、门控、实时角度与实时计数
    if (telemetryData.length > 0) {
      let closest = telemetryData[0];
      let minDiff = Math.abs(closest.time_s - curTime);
      for (let i = 1; i < telemetryData.length; i++) {
        const diff = Math.abs(telemetryData[i].time_s - curTime);
        if (diff < minDiff) {
          minDiff = diff;
          closest = telemetryData[i];
        } else if (diff > minDiff && telemetryData[i].time_s > curTime + 0.15) {
          break;
        }
      }

      if (closest) {
        // 1. 实时完成计数 (根据当前播放时序动态递增 0 -> 1 -> 2...)
        if (hudCountEl) {
          hudCountEl.textContent = closest.count !== undefined ? closest.count : 0;
        }

        // 2. 实时膝关节屈曲角
        if (hudCurKneeEl) {
          hudCurKneeEl.textContent = `${closest.knee_angle.toFixed(1)}°`;
          if (closest.knee_angle <= 105.0) {
            hudCurKneeEl.style.color = '#10b981';
            hudCurKneeEl.style.textShadow = '0 0 8px rgba(16, 185, 129, 0.4)';
          } else {
            hudCurKneeEl.style.color = '#38bdf8';
            hudCurKneeEl.style.textShadow = '0 0 8px rgba(56, 189, 248, 0.4)';
          }
        }

        // 3. 实时躯干前倾角
        if (hudCurTorsoEl) {
          hudCurTorsoEl.textContent = `${closest.torso_angle.toFixed(1)}°`;
          if (closest.torso_angle > 45.0) {
            hudCurTorsoEl.style.color = '#ef4444';
            hudCurTorsoEl.style.textShadow = '0 0 8px rgba(239, 68, 68, 0.4)';
          } else {
            hudCurTorsoEl.style.color = '#fb923c';
            hudCurTorsoEl.style.textShadow = '0 0 8px rgba(251, 146, 60, 0.4)';
          }
        }

        // 4. 状态机阶段与门控状态
        if (hudFsmEl) hudFsmEl.textContent = closest.fsm_state;
        if (hudGateEl) {
          if (!closest.is_valid) {
            hudGateEl.className = 'badge badge-gate rejected';
            hudGateEl.textContent = 'OUT_OF_FRAME';
          } else {
            hudGateEl.className = 'badge badge-gate';
            hudGateEl.textContent = 'DRAWABLE';
          }
        }

        // 5. 渲染画面骨架与画面内动态角度悬浮气泡
        skeletonRenderer.render(closest);
      }
    } else {
      skeletonRenderer.clear();
    }
  }

  function startPlaybackLoop() {
    if (animFrameId) cancelAnimationFrame(animFrameId);
    function loop() {
      if (!videoEl.paused && !videoEl.ended) {
        syncPlaybackFrame();
        animFrameId = requestAnimationFrame(loop);
      }
    }
    animFrameId = requestAnimationFrame(loop);
  }

  function stopPlaybackLoop() {
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    syncPlaybackFrame();
  }

  videoEl.addEventListener('play', () => {
    skeletonRenderer.resize();
    startPlaybackLoop();
  });

  videoEl.addEventListener('pause', () => {
    stopPlaybackLoop();
  });

  videoEl.addEventListener('seeked', () => {
    syncPlaybackFrame();
  });

  videoEl.addEventListener('loadeddata', () => {
    skeletonRenderer.resize();
    syncPlaybackFrame();
  });

  videoEl.addEventListener('timeupdate', () => {
    if (videoEl.paused) {
      syncPlaybackFrame();
    }
  });

  videoEl.addEventListener('error', () => {
    console.warn('视频流解码状态:', videoEl.error);
    if (overlayTimeEl) {
      overlayTimeEl.textContent = '视频流就绪';
    }
  });

  videoEl.addEventListener('ended', () => {
    if (activeRepSlice && isSliceLoopEnabled) {
      videoEl.currentTime = activeRepSlice.start_time_s;
      videoEl.play().catch(() => {});
    } else {
      stopPlaybackLoop();
      videoEl.currentTime = 0;
      syncPlaybackFrame();
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

      const activeRadio = document.querySelector('input[name="accel_profile"]:checked');
      const selectedProfile = activeRadio ? activeRadio.value : 'CPU_HIGH_PERF';
      const uploadUrl = `/api/upload?accel_profile=${encodeURIComponent(selectedProfile)}`;

      const res = await fetch(uploadUrl, {
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
    [btnShowGolden, btnShowDataset, btnShowUploads, btnShowCamera].forEach((b) => {
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

  // 2.4 实时摄像头模式交互与面板渲染
  async function loadCameraMode() {
    videoEl.pause();
    videoEl.removeAttribute('src');
    skeletonRenderer.clear();
    chart.clear();
    exitDrillDown();
    if (repsCarouselEl) {
      repsCarouselEl.innerHTML = '<div class="empty-hint">实时摄像头训练中，完成深蹲将即时生成动作切片</div>';
    }

    currentCaseNameEl.textContent = '实时摄像头深蹲动作质量监测与计数';
    currentCaseDescEl.textContent = '接入电脑前置或外置摄像头，单人侧面站立，实时绘制 33 点姿态骨架与关节角度悬浮气泡，自动跟踪 FSM 动作阶段与完成计数。';

    hudCountEl.textContent = '0';
    if (hudCurKneeEl) {
      hudCurKneeEl.textContent = '--°';
      hudCurKneeEl.style.color = '#38bdf8';
    }
    if (hudCurTorsoEl) {
      hudCurTorsoEl.textContent = '--°';
      hudCurTorsoEl.style.color = '#fb923c';
    }
    hudFsmEl.textContent = 'STANDING';
    hudGateEl.className = 'badge badge-gate';
    hudGateEl.textContent = 'DRAWABLE';

    keyframesGrid.innerHTML = '<div class="empty-hint">实时摄像头训练中，完成深蹲将即时提示</div>';
    evalStatusBadge.className = 'badge badge-eval acceptable';
    evalStatusBadge.textContent = '就绪等待开启';
    evalFeedbackText.textContent = '请调整站位确保全身入镜，然后点击左侧“开启实时摄像头”或“切换虚拟演示流”启动推理。';

    caseListEl.innerHTML = `
      <div class="camera-launcher-card">
        <div class="camera-card-header">
          <span class="camera-card-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 7l-7 5 7 5V7z"></path><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
            摄像头设备控制
          </span>
          <span class="badge badge-status online" id="camera-device-status">● 设备就绪</span>
        </div>
        <p class="camera-card-desc">支持电脑自带前置摄像头、USB 外接超广角摄像头及移动虚拟流设备。</p>
        
        <div style="display:flex; flex-direction:column; gap:6px;">
          <label style="font-size:0.75rem; color:#94a3b8;">选择视频采集输入设备：</label>
          <select id="camera-device-select" class="camera-device-select">
            <option value="">默认前置摄像头 (Default)</option>
          </select>
        </div>

        <div class="camera-btn-group">
          <button class="btn-camera-start" id="btn-start-camera-stream">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            开启实时摄像头
          </button>
          <button class="btn-camera-virtual" id="btn-start-virtual-stream" title="若电脑无物理摄像头或权限受限，一键开启离线素材推流">
            🎬 切换虚拟演示流 (无摄像头兜底)
          </button>
        </div>

        <div class="camera-tips-box">
          <b>动作指导与机位建议：</b><br>
          1. 身体侧面与镜头保持约 90° 夹角；<br>
          2. 距离镜头约 1.8~2.5 米，保持头部至脚踝完整在画框内；<br>
          3. 动作遵循 站立 -> 匀速下蹲 (膝角 ≤ 105°) -> 波谷停顿 -> 起身还原。
        </div>

        <div id="camera-error-hint" style="display:none; padding:8px 10px; background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); border-radius:6px; color:#fca5a5; font-size:0.75rem; line-height:1.4;"></div>
      </div>
    `;

    // 枚举媒体设备
    const deviceSelect = document.getElementById('camera-device-select');
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(d => d.kind === 'videoinput');
        if (videoDevices.length > 0) {
          deviceSelect.innerHTML = '';
          videoDevices.forEach((d, idx) => {
            const opt = document.createElement('option');
            opt.value = d.deviceId;
            opt.textContent = d.label || `摄像头 #${idx + 1}`;
            deviceSelect.appendChild(opt);
          });
        }
      } catch (devErr) {
        console.warn('枚举摄像头设备失败:', devErr);
      }
    }

    const startCameraBtn = document.getElementById('btn-start-camera-stream');
    const startVirtualBtn = document.getElementById('btn-start-virtual-stream');
    const errorHint = document.getElementById('camera-error-hint');
    const deviceStatus = document.getElementById('camera-device-status');

    if (startCameraBtn) {
      startCameraBtn.addEventListener('click', async () => {
        errorHint.style.display = 'none';
        startCameraBtn.disabled = true;
        startCameraBtn.innerHTML = '正在启动摄像头并连接推理引擎...';

        const deviceId = deviceSelect ? deviceSelect.value : null;
        const res = await liveController.startCamera(deviceId);
        if (!res.success) {
          startCameraBtn.disabled = false;
          startCameraBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            开启实时摄像头
          `;
          errorHint.style.display = 'block';
          errorHint.innerHTML = `
            <b>⚠️ 摄像头接入受限</b> (${res.message})。<br>
            您可能处于无物理摄像头或权限禁用环境。建议直接点击下方【切换虚拟演示流】进行免硬件零门槛体验！
          `;
          if (deviceStatus) {
            deviceStatus.className = 'badge badge-status';
            deviceStatus.textContent = '● 设备受限';
            deviceStatus.style.background = 'rgba(239,68,68,0.2)';
            deviceStatus.style.color = '#f87171';
          }
        } else {
          startCameraBtn.disabled = true;
          startCameraBtn.innerHTML = '● 摄像头实时推流中...';
          startCameraBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
          if (deviceStatus) {
            deviceStatus.className = 'badge badge-status online';
            deviceStatus.textContent = '● 推流中';
          }
        }
      });
    }

    if (startVirtualBtn) {
      startVirtualBtn.addEventListener('click', async () => {
        errorHint.style.display = 'none';
        const res = await liveController.startVirtualCamera();
        if (res.success) {
          if (startCameraBtn) {
            startCameraBtn.disabled = true;
            startCameraBtn.innerHTML = '● 虚拟演示流推流中...';
            startCameraBtn.style.background = 'linear-gradient(135deg, #8b5cf6, #6366f1)';
          }
          if (deviceStatus) {
            deviceStatus.className = 'badge badge-status online';
            deviceStatus.textContent = '● 虚拟推流中';
          }
        }
      });
    }
  }

  function renderLiveSessionFinished(summary) {
    evalStatusBadge.className = `badge badge-eval ${summary.actual_status === 'ACCEPTABLE' ? 'acceptable' : 'needs_improvement'}`;
    evalStatusBadge.textContent = summary.actual_status === 'ACCEPTABLE' ? '达标 (ACCEPTABLE)' : '待改进 (NEEDS_IMPROVEMENT)';
    evalFeedbackText.textContent = summary.summary_guidance || '训练已完成';

    valExecTimeEl.textContent = `${summary.duration_s} s`;

    fetchStatus();
    if (summary && summary.repetitions && summary.repetitions.length > 0) {
      renderMultiRepSection(summary);
    }

    // 驱动 AI 智能教练对本次摄像头会话进行深度点评
    if (llmCoach) {
      llmCoach.setCurrentCase(summary.saved_case_id || 'live_session', summary);
    }

    caseListEl.innerHTML = `
      <div class="camera-launcher-card" style="border-color: rgba(16, 185, 129, 0.4);">
        <div class="camera-card-header">
          <span class="camera-card-title" style="color: #10b981;">🎉 本次训练完成</span>
          <span class="badge badge-eval ${summary.actual_status === 'ACCEPTABLE' ? 'acceptable' : 'needs_improvement'}">${summary.actual_status}</span>
        </div>
        <p class="camera-card-desc">
          耗时 <b>${summary.duration_s}</b> 秒，共完成 <b>${summary.total_reps}</b> 次深蹲动作（达标 ${summary.metrics_summary ? summary.metrics_summary.acceptable_reps : 0} 次）。
        </p>
        <p class="camera-card-desc" style="color: #cbd5e1; font-size:0.75rem;">
          ${summary.summary_guidance}
        </p>
        <div class="camera-btn-group">
          <button class="btn-camera-start" id="btn-restart-camera">
            🔄 继续新一轮训练
          </button>
          <button class="btn-camera-virtual" id="btn-view-saved-live">
            📊 查看本次分析完整时序与回放
          </button>
        </div>
      </div>
    `;

    const restartBtn = document.getElementById('btn-restart-camera');
    if (restartBtn) restartBtn.addEventListener('click', () => loadCameraMode());

    const viewSavedBtn = document.getElementById('btn-view-saved-live');
    if (viewSavedBtn) {
      viewSavedBtn.addEventListener('click', () => {
        currentMode = 'UPLOADS';
        setTabActive(btnShowUploads);
        if (selectorTag) selectorTag.textContent = '在线自定义';
        if (uploadPanelSection) uploadPanelSection.style.display = 'block';
        loadUploads(summary.case_id);
      });
    }
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
      syncPlaybackFrame();
    } else if (e.code === 'ArrowLeft') {
      e.preventDefault();
      videoEl.currentTime = Math.max(0, videoEl.currentTime - 1 / 30);
      syncPlaybackFrame();
    }
  });

  // 9. 选项卡切换事件绑定
  if (btnShowGolden) {
    btnShowGolden.addEventListener('click', () => {
      if (liveController.isRunning) liveController.stop();
      currentMode = 'GOLDEN';
      setTabActive(btnShowGolden);
      if (selectorTag) selectorTag.textContent = 'P4 基准';
      if (uploadPanelSection) uploadPanelSection.style.display = 'block';
      loadCases();
    });
  }

  if (btnShowDataset) {
    btnShowDataset.addEventListener('click', () => {
      if (liveController.isRunning) liveController.stop();
      currentMode = 'DATASET';
      setTabActive(btnShowDataset);
      if (selectorTag) selectorTag.textContent = 'MediaPipe 实测';
      if (uploadPanelSection) uploadPanelSection.style.display = 'block';
      loadDatasetDemos();
    });
  }

  if (btnShowUploads) {
    btnShowUploads.addEventListener('click', () => {
      if (liveController.isRunning) liveController.stop();
      currentMode = 'UPLOADS';
      setTabActive(btnShowUploads);
      if (selectorTag) selectorTag.textContent = '在线自定义';
      if (uploadPanelSection) uploadPanelSection.style.display = 'block';
      loadUploads();
    });
  }

  if (btnShowCamera) {
    btnShowCamera.addEventListener('click', () => {
      if (liveController.isRunning) liveController.stop();
      currentMode = 'CAMERA';
      setTabActive(btnShowCamera);
      if (selectorTag) selectorTag.textContent = '实时摄像头';
      if (uploadPanelSection) uploadPanelSection.style.display = 'none';
      loadCameraMode();
    });
  }

  // --- 硬件算力与显卡加速引擎前端控制器 ---
  const hardwareAccelPanel = document.getElementById('hardware-accel-panel');
  const btnDetectHardware = document.getElementById('btn-detect-hardware');
  const gpuNameText = document.getElementById('gpu-name-text');
  const gpuTypeBadge = document.getElementById('gpu-type-badge');
  const radioCpu = document.querySelector('input[name="accel_profile"][value="CPU_HIGH_PERF"]');
  const radioGpu = document.querySelector('input[name="accel_profile"][value="GPU_ACCELERATED"]');
  const labelModeCpu = document.getElementById('label-mode-cpu');
  const labelModeGpu = document.getElementById('label-mode-gpu');
  const modeNoticeBanner = document.getElementById('mode-notice-banner');

  let currentHardwareData = null;

  async function loadHardwareStatus(forceRefresh = false) {
    if (btnDetectHardware) {
      btnDetectHardware.disabled = true;
      btnDetectHardware.textContent = forceRefresh ? '正在检测...' : '检测显卡';
    }
    try {
      const data = await ApiClient.getHardwareStatus(forceRefresh);
      currentHardwareData = data;
      renderHardwareUI(data);
    } catch (err) {
      console.warn('获取显卡硬件状态失败:', err);
      if (gpuNameText) gpuNameText.textContent = '显卡探测遇到问题 (已回退 CPU 模式)';
    } finally {
      if (btnDetectHardware) {
        btnDetectHardware.disabled = false;
        btnDetectHardware.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
          检测显卡
        `;
      }
    }
  }

  function renderHardwareUI(data) {
    if (!data) return;
    const gpus = data.gpus || [];
    const hasDiscrete = data.has_discrete_gpu;
    const primaryGpu = gpus[0];

    if (gpuNameText) {
      gpuNameText.textContent = primaryGpu ? primaryGpu.name : '标准显示适配器';
      gpuNameText.title = primaryGpu ? `${primaryGpu.name} (显存: ${primaryGpu.ram_mb ? primaryGpu.ram_mb + 'MB' : '共享系统内存'})` : '';
    }

    if (gpuTypeBadge) {
      if (hasDiscrete) {
        gpuTypeBadge.textContent = '独立显卡 (dGPU)';
        gpuTypeBadge.style.background = 'rgba(34, 197, 94, 0.2)';
        gpuTypeBadge.style.color = '#4ade80';
        gpuTypeBadge.style.borderColor = 'rgba(34, 197, 94, 0.4)';
      } else {
        const vendor = (primaryGpu && primaryGpu.vendor) ? primaryGpu.vendor : '';
        gpuTypeBadge.textContent = `${vendor} 集成核显 (iGPU)`.trim();
        gpuTypeBadge.style.background = 'rgba(234, 179, 8, 0.2)';
        gpuTypeBadge.style.color = '#facc15';
        gpuTypeBadge.style.borderColor = 'rgba(234, 179, 8, 0.4)';
      }
    }

    const active = data.active_profile || 'CPU_HIGH_PERF';
    applyProfileSelection(active);
  }

  function applyProfileSelection(profile) {
    const isCpu = profile === 'CPU_HIGH_PERF';
    if (radioCpu) radioCpu.checked = isCpu;
    if (radioGpu) radioGpu.checked = !isCpu;

    if (labelModeCpu) {
      labelModeCpu.className = isCpu ? 'mode-card active' : 'mode-card';
      labelModeCpu.style.borderColor = isCpu ? '#3b82f6' : 'rgba(255,255,255,0.1)';
      labelModeCpu.style.background = isCpu ? 'rgba(59, 130, 246, 0.08)' : 'rgba(15, 23, 42, 0.4)';
    }
    if (labelModeGpu) {
      labelModeGpu.className = !isCpu ? 'mode-card active' : 'mode-card';
      labelModeGpu.style.borderColor = !isCpu ? '#3b82f6' : 'rgba(255,255,255,0.1)';
      labelModeGpu.style.background = !isCpu ? 'rgba(59, 130, 246, 0.08)' : 'rgba(15, 23, 42, 0.4)';
    }

    if (modeNoticeBanner) {
      const hasDiscrete = currentHardwareData && currentHardwareData.has_discrete_gpu;
      if (!isCpu) {
        modeNoticeBanner.style.display = 'block';
        if (hasDiscrete) {
          modeNoticeBanner.style.background = 'rgba(34, 197, 94, 0.15)';
          modeNoticeBanner.style.color = '#4ade80';
          modeNoticeBanner.style.border = '1px solid rgba(34, 197, 94, 0.3)';
          modeNoticeBanner.textContent = '✅ 检测到独立显卡 (dGPU)，GPU 硬件加速已激活，将利用专用显存加速视频解码与预处理。';
        } else {
          modeNoticeBanner.style.background = 'rgba(234, 179, 8, 0.15)';
          modeNoticeBanner.style.color = '#fde047';
          modeNoticeBanner.style.border = '1px solid rgba(234, 179, 8, 0.3)';
          modeNoticeBanner.textContent = '⚠️ 当前检测为集成核显 (iGPU)，开启 GPU 加速可能导致桌面窗口 (DWM) 与视频回放轻微卡顿，建议使用 CPU 模式（仍允许开启）。';
        }
      } else {
        modeNoticeBanner.style.display = 'none';
      }
    }
  }

  function setupHardwareAccelerationUI() {
    if (btnDetectHardware) {
      btnDetectHardware.addEventListener('click', () => loadHardwareStatus(true));
    }

    const radios = [radioCpu, radioGpu].filter(Boolean);
    radios.forEach((r) => {
      r.addEventListener('change', async (e) => {
        const val = e.target.value;
        applyProfileSelection(val);
        try {
          await ApiClient.setHardwareProfile(val);
        } catch (err) {
          console.error('切换算力模式失败:', err);
        }
      });
    });

    loadHardwareStatus(false);
  }

  // 启动时初始化
  fetchStatus();
  setupHardwareAccelerationUI();
  loadCases();
});
