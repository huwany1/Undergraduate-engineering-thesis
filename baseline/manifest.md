# P0 基线清单（Baseline Manifest）

> **基线编号**：`P0-SQUAT-SIDE-OFFLINE-v1.0`  
> **生效日期**：2026-09-18  
> **状态**：门禁全量自动化核验通过，待各方最终签核（放行 P1 前置条件）

---

## 1. 基线组件版本固化

本基线包将四卡一规范绑定为唯一防篡改版本集合：

| 构件名称 | 契约标识 / 版本 | 责任人 | SHA-256 完整性校验和 |
|---|---|---|---|
| **卡 A：范围与边界卡** | `SQUAT-SIDE-SINGLE-OFFLINE-v1.0` | 技术负责人 | `3edbfba340b0094ba4b13c83e5b91af145e1d95f981e25c3a4598864b8f893d4` |
| **卡 B：机位规范卡** | `CAM-SIDE-FIXED-v1.0` | 采集负责人 | `89ba49e7bbb75d804e7e688c598dffc8e2fd20f397a623cbba3cf25f20d3f3b9` |
| **卡 C：规则卡集** | `RULE-SQUAT-v1.0` / `AGG-STRICT-GATED-v1.0` | 规则负责人 | `9c58783d5cf834b0a33358066e279a0fb290f8e6fe70888c818ed6fa597d40b2` |
| **卡 D：数据授权与治理卡** | `CONSENT-GOV-v1.0` / `FORM-SQUAT-2026-v1` | 数据负责人 | `6468fb7e8c38e2a9fe3f77f6f169ae261f08cd2e9c03cd3df6b4b5dd5ea30937` |
| **卡 E：数据集规范手册** | `DS-MANIFEST-v1.0` / `LABEL-GUIDE-v1.0` | 配置管理员 | `4574be744fe6d247f0cab4fa0ef3d277466699fc00f473ac9db8c90f0e513d1c` |

---

## 2. 基线指纹生成格式

每一份进入系统的视频、中间关键点特征、阶段转换事件与最终可视化结果，必须携带统一的**基线指纹（Baseline Fingerprint）**：

$$\text{Fingerprint} = \text{baseline\_id} \cdot \text{scope\_version} \cdot \text{camera\_profile\_id} \cdot \text{rule\_set\_version} \cdot \text{consent\_status} \cdot \text{source\_video\_id} \cdot \text{operator} \cdot \text{recorded\_at}$$

**标准指纹示例**：  
`P0-SQUAT-SIDE-OFFLINE-v1.0.SQUAT-SIDE-SINGLE-OFFLINE-v1.0.CAM-SIDE-FIXED-v1.0.RULE-SQUAT-v1.0.ACTIVE.VID-REC-20260918-01.Op_Zhang.20260918T1430`

---

## 3. P0 准入门禁（G0–G6）审核结论

| 门禁代码 | 门禁名称 | 审查标准 | 核验状态 |
|---|---|---|---|
| **G0** | 范围一致性 | 契约与报告中禁止承诺词出现次数为 0 | **PASS** |
| **G1** | 机位可执行 | 几何距离/高度标定完整，双样张复核机制建立 | **PASS** |
| **G2** | 规则可判定 | 3 条规则谓词形式化定义，聚合策略优先级无歧义 | **PASS** |
| **G3** | 授权可追溯 | 知情同意要件齐备，凭证解耦，到期 2026-12-31 处置闭环 | **PASS** |
| **G4** | 标注可验证 | 校准集与验证集按受试者物理隔离，双人双盲分歧台账建立 | **PASS** |
| **G5** | 版本可审计 | 五大契约 SHA-256 实时重算校验完全一致 | **PASS** |
| **G6-P0** | 拒绝合同演练 | 8 组无效输入模拟 100% 阻断，不计数、不评价、留原因码 | **PASS** |

---

## 4. 签核表（Signoff Sheet）

| 角色 | 姓名 | 签核意见 | 签核日期 |
|---|---|---|---|
| **技术负责人** | [待签核] | 范围明确、机位可复现、规则形式化确定、G6 桌面演练通过 | 2026-09-18 |
| **数据负责人** | [待签核] | 授权要件完备、S1-S4 隔离有效、到期处置机制完备 | 2026-09-18 |
| **指导教师** | [待签核] | 符合本科毕业设计教学科研范围与伦理要求，同意放行后续 P1 | 2026-09-18 |
