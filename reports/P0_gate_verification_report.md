# P0 准入门禁自动化审查与演练报告

- **基线编号**：`P0-SQUAT-SIDE-OFFLINE-v1.0`
- **生成时间**：`2026-09-18T21:55:00+08:00`
- **总体判定**：**ALL PASS（全量通过，放行后续P1）**

---

## 1. 门禁（G0–G6）核验结果表

| 门禁代码 | 门禁名称 | 状态 | 审查结论与证据 |
|---|---|---|---|
| `G0_SCOPE_CONSISTENCY` | G0 范围一致性 | **PASS** | 范围卡声明清晰，0处违规承诺，禁止项已全部固化 |
| `G1_CAMERA_EXECUTABLE` | G1 机位可执行 | **PASS** | 机位几何标定完整，双样张制度与现场记录表头核验无误 |
| `G2_RULE_DETERMINISTIC` | G2 规则可判定 | **PASS** | 三条规则形式化定义清晰，聚合策略与前置门控覆盖规则确定 |
| `G3_CONSENT_TRACEABLE` | G3 授权可追溯 | **PASS** | 数据分级存储、知情同意要件、凭证解耦及S1/S2防泄漏规则完备 |
| `G4_DATASET_ISOLATED` | G4 标注可验证 | **PASS** | 校准集与验证集受试者隔离规则明确，双人双盲分歧台账就绪，零伪真值红线锁定 |
| `G5_VERSION_AUDITABLE` | G5 版本可审计 | **PASS** | 全量卡片 SHA-256 哈希重算一致，基线指纹防篡改绑定成功 |
| `G6_REFUSAL_CONTRACT_SIMULATION` | G6-P0 拒绝演练 | **PASS** | 8/8 组无效状态演练全量通过：阻断率 100%，次数虚增 0 次，质量反馈屏蔽率 100% |

---

## 2. G6-P0 无效状态矩阵桌面演练（Dry-Run）明细

系统对《详细实施方案》第 5.2 节定义的全部 8 种无效状态进行了模拟测试，验证准入层是否做到“不计数、不评价、精准输出原因码”：

| 场景编号 | 场景描述 | 期望拒绝码 | 实际响应码 | 动作计数 | 评价抑制 | 演练结果 |
|---|---|---|---|---|---|---|
| `SIM_01_NO_PERSON` | 帧中无人入镜 | `NO_PERSON` | `NO_PERSON` | `0` | 100%抑制 | **PASS** |
| `SIM_02_MULTI_PERSON` | 画面出现多人走动 | `MULTI_PERSON` | `MULTI_PERSON` | `0` | 100%抑制 | **PASS** |
| `SIM_03_OUT_OF_FRAME` | 脚踝或足底移出画幅下边缘 | `OUT_OF_FRAME` | `OUT_OF_FRAME` | `0` | 100%抑制 | **PASS** |
| `SIM_04_LOW_VISIBILITY` | 强背光导致关键点置信度不足 | `LOW_VISIBILITY` | `LOW_VISIBILITY` | `0` | 100%抑制 | **PASS** |
| `SIM_05_WRONG_VIEW` | 斜向 45 度视角录制（非主侧视） | `WRONG_VIEW` | `WRONG_VIEW` | `0` | 100%抑制 | **PASS** |
| `SIM_06_INCOMPLETE_REP` | 深蹲下潜一半未达最低点直接站起 | `INCOMPLETE_REP` | `INCOMPLETE_REP` | `0` | 100%抑制 | **PASS** |
| `SIM_07_CONSENT_BLOCKED` | 受试者撤回同意或许可凭据过期 | `CONSENT_BLOCKED` | `CONSENT_BLOCKED` | `0` | 100%抑制 | **PASS** |
| `SIM_08_BASELINE_MISMATCH` | 视频处理请求使用旧版已作废基线配置 | `BASELINE_MISMATCH` | `BASELINE_MISMATCH` | `0` | 100%抑制 | **PASS** |

---

## 3. SHA-256 契约防篡改指纹清单

```yaml
scope_contract.yaml: "3edbfba340b0094ba4b13c83e5b91af145e1d95f981e25c3a4598864b8f893d4"
camera_profile.yaml: "89ba49e7bbb75d804e7e688c598dffc8e2fd20f397a623cbba3cf25f20d3f3b9"
rule_set.yaml: "9c58783d5cf834b0a33358066e279a0fb290f8e6fe70888c818ed6fa597d40b2"
consent_governance.yaml: "6468fb7e8c38e2a9fe3f77f6f169ae261f08cd2e9c03cd3df6b4b5dd5ea30937"
dataset_manifest.yaml: "4574be744fe6d247f0cab4fa0ef3d277466699fc00f473ac9db8c90f0e513d1c"
```

## 4. 结论

依据 [P0_口径冻结_详细实施方案.md](file:///c:/Users/huwany/Desktop/Undergraduate-engineering-thesis/P0_口径冻结_详细实施方案.md) 的退出条件：G0–G6 全部通过，四卡与基线清单齐备，无效状态拒绝机制已在准入层面闭环验证完毕。准予进入 P1 阶段。