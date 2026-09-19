// -*- coding: utf-8 -*-
/**
 * 连续动作切片下钻与多维宏观看板交互组件 (Rep Selector Module)
 * 职责：
 * 1. 渲染 Rep #1 ~ Rep #N 切片横向轮播卡片 (包含达标/待改进徽章、波谷角度、缺陷标签);
 * 2. 驱动单次动作下钻交互 (0.5x 慢放、区间自动循环、图表波谷聚焦遮罩);
 * 3. 渲染整组动作一致性得分 (Consistency Score)、疲劳衰减迷你柱状图与肌肉收缩节奏比例条;
 * 4. 监听视频播放时钟，实施切片区间循环约束.
 */

(function (global) {
  'use strict';

  class RepSelector {
    constructor(elements, chart, videoEl) {
      this.elements = elements || {};
      this.chart = chart;
      this.videoEl = videoEl;

      this.activeRepSlice = null;
      this.isSlowMoEnabled = true;
      this.isSliceLoopEnabled = true;
      this.currentDetail = null;

      this._initControlEvents();
    }

    _initControlEvents() {
      const { btnMacroOverview, btnSlowMoToggle, btnLoopToggle, btnExitDrilldown } = this.elements;

      if (btnMacroOverview) {
        btnMacroOverview.addEventListener('click', () => this.exitDrillDown());
      }
      if (btnExitDrilldown) {
        btnExitDrilldown.addEventListener('click', () => this.exitDrillDown());
      }
      if (btnSlowMoToggle) {
        btnSlowMoToggle.addEventListener('click', () => {
          this.isSlowMoEnabled = !this.isSlowMoEnabled;
          btnSlowMoToggle.classList.toggle('active', this.isSlowMoEnabled);
          if (this.activeRepSlice && this.videoEl) {
            this.videoEl.playbackRate = this.isSlowMoEnabled ? 0.5 : 1.0;
          }
        });
      }
      if (btnLoopToggle) {
        btnLoopToggle.addEventListener('click', () => {
          this.isSliceLoopEnabled = !this.isSliceLoopEnabled;
          btnLoopToggle.classList.toggle('active', this.isSliceLoopEnabled);
        });
      }
    }

    renderMultiRepSection(detail) {
      this.currentDetail = detail;
      this.exitDrillDown();

      const reps = detail.repetitions || [];
      const summary = detail.multi_rep_summary || null;
      const { repsCarouselEl } = this.elements;

      // 1. 渲染切片横向轮播卡片
      if (repsCarouselEl) {
        repsCarouselEl.innerHTML = '';
        if (!reps || reps.length === 0) {
          repsCarouselEl.innerHTML = '<div class="empty-hint">当前用例未检测到完整的连续动作切片</div>';
        } else {
          reps.forEach((rep) => {
            const card = document.createElement('div');
            card.className = `rep-slice-card ${rep.is_acceptable ? 'pass' : 'warn'}`;
            card.dataset.repIndex = rep.rep_index;

            const isPass = rep.is_acceptable;
            const statusBadge = isPass
              ? '<span class="badge badge-eval acceptable">合格</span>'
              : '<span class="badge badge-eval needs_improvement">待改进</span>';

            let issueHtml = '<div class="rep-tempo-tag">✓ 达标</div>';
            if (rep.issues && rep.issues.length > 0) {
              const firstIssue = rep.issues[0];
              const issueLabel = firstIssue === 'KNEE_ANGLE_TOO_LARGE' ? '下蹲过浅'
                : firstIssue === 'TORSO_LEAN_EXCESSIVE' ? '前倾过度'
                : firstIssue === 'ASYMMETRY_DETECTED' ? '左右不对称'
                : firstIssue === 'BOTTOM_PAUSE_TOO_SHORT' ? '停顿不足'
                : firstIssue === 'ECCENTRIC_TOO_FAST' ? '下蹲过急'
                : firstIssue;
              issueHtml = `<div class="rep-defect-pill" title="${rep.issues.join(', ')}">⚠️ ${issueLabel}</div>`;
            }

            card.innerHTML = `
              <div class="rep-card-header-row">
                <span class="rep-card-num">#${rep.rep_index} 深蹲</span>
                ${statusBadge}
              </div>
              <div class="rep-card-angles">
                <div class="rep-angle-item">
                  <span>膝角波谷</span>
                  <b class="knee">${rep.min_knee_angle.toFixed(1)}°</b>
                </div>
                <div class="rep-angle-item">
                  <span>躯干前倾</span>
                  <b class="torso">${rep.max_torso_angle.toFixed(1)}°</b>
                </div>
              </div>
              <div class="rep-card-footer-row">
                <span class="rep-tempo-tag">${rep.duration_s.toFixed(2)}s</span>
                ${issueHtml}
              </div>
            `;

            card.addEventListener('click', () => {
              this.enterDrillDown(rep);
            });

            repsCarouselEl.appendChild(card);
          });
        }
      }

      // 2. 渲染整组宏观统计看板
      if (summary) {
        this._renderMacroDashboard(summary, reps);
      }
    }

    _renderMacroDashboard(summary, reps) {
      const {
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
      } = this.elements;

      if (macroPassRateBadge) {
        const pct = Math.round((summary.pass_rate || 0) * 100);
        macroPassRateBadge.textContent = `合格率: ${pct}% (${summary.acceptable_reps}/${summary.total_reps})`;
        macroPassRateBadge.className = `badge badge-eval ${pct >= 80 ? 'acceptable' : pct >= 50 ? 'needs_improvement' : 'not_evaluated'}`;
      }

      // 卡片 1: 动作一致性得分
      const c = summary.consistency;
      if (c && consistencyScoreNum) {
        consistencyScoreNum.textContent = c.consistency_score.toFixed(0);
        if (consistencyGradeBadge) {
          consistencyGradeBadge.textContent = c.grade;
          consistencyGradeBadge.className = `badge badge-eval ${c.consistency_score >= 85 ? 'acceptable' : c.consistency_score >= 70 ? 'needs_improvement' : 'not_evaluated'}`;
        }
        if (consistencyKneeStd) consistencyKneeStd.textContent = `${c.knee_angle_std.toFixed(1)}°`;
        if (consistencyTorsoStd) consistencyTorsoStd.textContent = `${c.torso_angle_std.toFixed(1)}°`;
        if (consistencyDurCv) consistencyDurCv.textContent = `${(c.duration_cv * 100).toFixed(1)}%`;
        if (consistencyDesc) consistencyDesc.textContent = c.description;
      }

      // 卡片 2: 下蹲深度衰减趋势 (疲劳分析)
      const d = summary.depth_decay;
      if (d && fatigueStatusBadge) {
        let stLabel = '稳健良好 (STABLE)';
        let stClass = 'acceptable';
        if (d.status === 'FATIGUE_DETECTED') {
          stLabel = '⚠️ 疲劳衰减 (FATIGUE)';
          stClass = 'needs_improvement';
        } else if (d.status === 'IMPROVING') {
          stLabel = '渐入佳境 (IMPROVING)';
          stClass = 'acceptable';
        } else if (d.status === 'SINGLE_REP') {
          stLabel = '单次基准 (SINGLE_REP)';
          stClass = 'acceptable';
        }

        fatigueStatusBadge.textContent = stLabel;
        fatigueStatusBadge.className = `badge badge-eval ${stClass}`;

        if (fatigueSlopeVal) {
          fatigueSlopeVal.textContent = `${d.slope >= 0 ? '+' : ''}${d.slope.toFixed(2)}°/次`;
          fatigueSlopeVal.style.color = d.status === 'FATIGUE_DETECTED' ? '#ef4444' : '#10b981';
        }
        if (fatigueDeltaVal) {
          fatigueDeltaVal.textContent = `${d.total_delta_deg >= 0 ? '+' : ''}${d.total_delta_deg.toFixed(1)}°`;
          fatigueDeltaVal.style.color = d.status === 'FATIGUE_DETECTED' ? '#ef4444' : '#10b981';
        }
        if (fatigueDesc) fatigueDesc.textContent = d.description;

        // 渲染疲劳迷你柱状图 Sparklines
        if (fatigueSparklineBox) {
          fatigueSparklineBox.innerHTML = '';
          if (reps.length > 0) {
            const angles = reps.map((r) => r.min_knee_angle);
            const minA = Math.min(...angles);
            const maxA = Math.max(...angles);
            const span = Math.max(10, maxA - minA);

            reps.forEach((r) => {
              const col = document.createElement('div');
              col.className = 'fatigue-bar-col';
              col.title = `第 ${r.rep_index} 次: 膝角 ${r.min_knee_angle.toFixed(1)}° (${r.is_acceptable ? '合格' : '待改进'})`;

              const ratio = 1 - (r.min_knee_angle - minA) / (span || 1);
              const heightPct = Math.max(25, Math.round(35 + ratio * 60));
              const barColor = r.is_acceptable ? '#10b981' : '#f43f5e';

              col.innerHTML = `
                <div class="fatigue-bar-fill" style="height: ${heightPct}%; background: ${barColor};"></div>
                <span class="fatigue-bar-num">#${r.rep_index}</span>
              `;
              col.style.cursor = 'pointer';
              col.addEventListener('click', () => this.enterDrillDown(r));
              fatigueSparklineBox.appendChild(col);
            });
          }
        }
      }

      // 卡片 3: 动作节奏剖析
      const t = summary.tempo;
      if (t) {
        if (tempoRatioBadge) tempoRatioBadge.textContent = t.tempo_ratio || '2-1-1';
        const ecc = t.mean_eccentric_s || 1.5;
        const iso = t.mean_isometric_s || 0.5;
        const con = t.mean_concentric_s || 1.5;
        const total = Math.max(0.1, ecc + iso + con);

        const eccPct = Math.max(15, (ecc / total) * 100);
        const isoPct = Math.max(10, (iso / total) * 100);
        const conPct = Math.max(15, 100 - eccPct - isoPct);

        if (tempoEccentricBar) {
          tempoEccentricBar.style.width = `${eccPct.toFixed(1)}%`;
          tempoEccentricBar.textContent = `离心 ${ecc.toFixed(1)}s`;
        }
        if (tempoIsometricBar) {
          tempoIsometricBar.style.width = `${isoPct.toFixed(1)}%`;
          tempoIsometricBar.textContent = `停顿 ${iso.toFixed(1)}s`;
        }
        if (tempoConcentricBar) {
          tempoConcentricBar.style.width = `${conPct.toFixed(1)}%`;
          tempoConcentricBar.textContent = `向心 ${con.toFixed(1)}s`;
        }

        if (tempoEccText) tempoEccText.textContent = `${ecc.toFixed(1)}s`;
        if (tempoIsoText) tempoIsoText.textContent = `${iso.toFixed(1)}s`;
        if (tempoConText) tempoConText.textContent = `${con.toFixed(1)}s`;
        if (tempoDesc) tempoDesc.textContent = t.description;
      }
    }

    enterDrillDown(rep) {
      this.activeRepSlice = rep;
      const {
        drilldownModeHint,
        macroScopeTag,
        btnMacroOverview,
        btnExitDrilldown,
        repsCarouselEl,
        valMinKneeEl,
        valMaxTorsoEl,
        valExecTimeEl,
        evalStatusBadge,
        evalFeedbackText,
      } = this.elements;

      if (drilldownModeHint) {
        drilldownModeHint.innerHTML = `🔍 正在下钻聚焦: <b style="color: #38bdf8;">第 #${rep.rep_index} 次动作</b> (0.5x 慢放与循环)`;
      }
      if (macroScopeTag) {
        macroScopeTag.textContent = `Rep #${rep.rep_index} 局部切片`;
      }
      if (btnMacroOverview) btnMacroOverview.classList.remove('active');
      if (btnExitDrilldown) btnExitDrilldown.style.display = 'inline-flex';

      if (repsCarouselEl) {
        repsCarouselEl.querySelectorAll('.rep-slice-card').forEach((card) => {
          card.classList.toggle('active', parseInt(card.dataset.repIndex, 10) === rep.rep_index);
        });
      }

      if (valMinKneeEl) valMinKneeEl.textContent = `${rep.min_knee_angle.toFixed(1)}°`;
      if (valMaxTorsoEl) valMaxTorsoEl.textContent = `${rep.max_torso_angle.toFixed(1)}°`;
      if (valExecTimeEl) valExecTimeEl.textContent = `${(rep.duration_s * 1000).toFixed(0)} ms`;

      let badgeClass = rep.is_acceptable ? 'acceptable' : 'needs_improvement';
      let statusText = rep.is_acceptable ? `Rep #${rep.rep_index} 及格达标 (ACCEPTABLE)` : `Rep #${rep.rep_index} 待改进 (NEEDS_IMPROVEMENT)`;
      if (evalStatusBadge) {
        evalStatusBadge.className = `badge badge-eval ${badgeClass}`;
        evalStatusBadge.textContent = statusText;
      }

      if (evalFeedbackText) {
        let hint = rep.is_acceptable
          ? `第 #${rep.rep_index} 次深蹲动作规范！波谷膝角 ${rep.min_knee_angle.toFixed(1)}° <= 105.0°，躯干保持稳定，节奏适中。`
          : `第 #${rep.rep_index} 次动作提示：实测波谷膝角 ${rep.min_knee_angle.toFixed(1)}°，前倾角 ${rep.max_torso_angle.toFixed(1)}°。`;
        if (rep.issues && rep.issues.length > 0) {
          hint += ` 检测到主要缺陷: ${rep.issues.join('、')}。`;
        }
        evalFeedbackText.textContent = hint;
      }

      if (this.chart) {
        this.chart.highlightRepSlice(rep.start_time_s, rep.end_time_s, rep.bottom_time_s);
      }

      if (this.videoEl) {
        this.videoEl.currentTime = rep.start_time_s;
        this.videoEl.playbackRate = this.isSlowMoEnabled ? 0.5 : 1.0;
        this.videoEl.play().catch(() => {});
      }
    }

    exitDrillDown() {
      this.activeRepSlice = null;
      const {
        drilldownModeHint,
        macroScopeTag,
        btnMacroOverview,
        btnExitDrilldown,
        repsCarouselEl,
        valMinKneeEl,
        valMaxTorsoEl,
        valExecTimeEl,
        evalStatusBadge,
        evalFeedbackText,
      } = this.elements;

      if (drilldownModeHint) drilldownModeHint.textContent = '点击卡片进入单次慢放与波谷聚焦';
      if (macroScopeTag) macroScopeTag.textContent = '全量宏观透视';
      if (btnMacroOverview) btnMacroOverview.classList.add('active');
      if (btnExitDrilldown) btnExitDrilldown.style.display = 'none';

      if (repsCarouselEl) {
        repsCarouselEl.querySelectorAll('.rep-slice-card').forEach((card) => {
          card.classList.remove('active');
        });
      }

      if (this.chart) this.chart.clearRepHighlight();
      if (this.videoEl) this.videoEl.playbackRate = 1.0;

      if (this.currentDetail) {
        const isDataset = Boolean(this.currentDetail.demo_id);
        if (isDataset) {
          if (valMinKneeEl) valMinKneeEl.textContent = `${this.currentDetail.min_knee_angle ? this.currentDetail.min_knee_angle.toFixed(1) : 0.0}°`;
          if (valMaxTorsoEl) valMaxTorsoEl.textContent = `${this.currentDetail.max_torso_angle ? this.currentDetail.max_torso_angle.toFixed(1) : 0.0}°`;
          if (valExecTimeEl) valExecTimeEl.textContent = `${((this.currentDetail.execution_time_s || 0) * 1000).toFixed(0)} ms`;

          let badgeClass = this.currentDetail.total_reps_passed > 0 ? 'acceptable' : 'needs_improvement';
          let statusText = this.currentDetail.total_reps_passed > 0 ? '动作规范达标 (ACCEPTABLE)' : '存在改进项 (NEEDS_IMPROVEMENT)';
          if (this.currentDetail.total_reps_completed === 0) {
            badgeClass = 'not_evaluated';
            statusText = '未计次 / 拒绝评估 (NOT_EVALUATED)';
          }
          if (evalStatusBadge) {
            evalStatusBadge.className = `badge badge-eval ${badgeClass}`;
            evalStatusBadge.textContent = statusText;
          }
          if (evalFeedbackText) evalFeedbackText.textContent = this.currentDetail.summary_feedback || '暂无评估建议';
        } else {
          if (valMinKneeEl) valMinKneeEl.textContent = `${(this.currentDetail.measured_min_knee_angle || 0).toFixed(1)}°`;
          if (valMaxTorsoEl) valMaxTorsoEl.textContent = `${(this.currentDetail.measured_max_torso_angle || 0).toFixed(1)}°`;
          if (valExecTimeEl) valExecTimeEl.textContent = `${(this.currentDetail.execution_time_ms || 0).toFixed(1)} ms`;

          let badgeClass = 'acceptable';
          let statusText = '动作规范 (ACCEPTABLE)';
          if (this.currentDetail.actual_status === 'NEEDS_IMPROVEMENT') {
            badgeClass = 'needs_improvement';
            statusText = '需要改进 (NEEDS_IMPROVEMENT)';
          } else if (this.currentDetail.actual_status === 'NOT_EVALUATED' || this.currentDetail.actual_status === 'REJECTED') {
            badgeClass = 'not_evaluated';
            statusText = '拒绝评估 (NOT_EVALUATED)';
          }
          if (evalStatusBadge) {
            evalStatusBadge.className = `badge badge-eval ${badgeClass}`;
            evalStatusBadge.textContent = statusText;
          }
          if (evalFeedbackText) evalFeedbackText.textContent = this.currentDetail.summary_feedback || '暂无评估建议';
        }
      }
    }

    checkPlaybackBound(currentTime) {
      if (this.activeRepSlice && this.isSliceLoopEnabled && this.videoEl) {
        if (currentTime >= this.activeRepSlice.end_time_s) {
          this.videoEl.currentTime = this.activeRepSlice.start_time_s;
        }
      }
    }
  }

  // 挂载到统一命名空间与全局
  global.SquatDemo = global.SquatDemo || {};
  global.SquatDemo.RepSelector = RepSelector;
  global.RepSelector = RepSelector;
})(typeof window !== 'undefined' ? window : this);
