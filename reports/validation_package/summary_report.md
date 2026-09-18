# P4 动作评估验证包总结报告 (Validation Package Summary)

- **基线编号**：`P0-SQUAT-SIDE-OFFLINE-v1.0`
- **Git 提交**：`74a1ae3`
- **生成时间**：`2026-09-19T00:18:45.897159`
- **总体核验结论**：**🟢 ALL PASS**

> [!NOTE]
> 本报告由 P4 自动化验证流水线自包含生成。所有测试用例均基于冻结的固定基线与确定性时间戳回放，
> 结果具备 100% 跨平台与跨次回放一致性，所有导出的视频、截图与日志已全量绑定 SHA-256 签名。

## 1. 核心量化指标看板

| 指标项目 | 测量数值 | 达标基准 | 判定 |
|---|:---:|:---:|:---:|
| **测试用例总通过率** | `5/5` (100.0%) | 100% | **PASS** |
| **动作计数绝对误差 (MAE)** | `0.00` | $\le 0.0$ | **PASS** |
| **异常状态阻断率 (Rejection)** | `100.0%` | 100% | **PASS** |

## 2. 黄金测试用例矩阵核验明细

| 用例编号 | 场景描述 | 预期计数/实际 | 预期评级/实际 | 预期主原因码/实际 | 测量极值 (膝角/倾角) | 状态 |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `TC_01_PERFECT_SQUAT` | 标准规范深蹲 (标杆组) | 1 / 1 | `ACCEPTABLE` / `ACCEPTABLE` | `ACCEPTABLE` / `ACCEPTABLE` | 92.4° / 21.4° | **PASS** |
| `TC_02_SHALLOW_SQUAT` | 下蹲深度不足 (浅蹲) | 1 / 1 | `NEEDS_IMPROVEMENT` / `NEEDS_IMPROVEMENT` | `INSUFFICIENT_DEPTH` / `INSUFFICIENT_DEPTH` | 108.9° / 21.4° | **PASS** |
| `TC_03_EXCESSIVE_LEAN` | 躯干过度前倾 | 1 / 1 | `NEEDS_IMPROVEMENT` / `NEEDS_IMPROVEMENT` | `EXCESSIVE_TORSO_LEAN` / `EXCESSIVE_TORSO_LEAN` | 92.4° / 51.1° | **PASS** |
| `TC_04_DUAL_DEFECT` | 复合缺陷深蹲 | 1 / 1 | `NEEDS_IMPROVEMENT` / `NEEDS_IMPROVEMENT` | `INSUFFICIENT_DEPTH` / `INSUFFICIENT_DEPTH` | 109.4° / 50.1° | **PASS** |
| `TC_05_OUT_OF_FRAME` | 身体出框异常拒绝 | 0 / 0 | `NOT_EVALUATED` / `NOT_EVALUATED` | `OUT_OF_FRAME` / `OUT_OF_FRAME` | 127.0° / 16.4° | **PASS** |

## 3. 免责声明与学术边界

> [!IMPORTANT]
> 1. **非医疗诊断声明**：本系统所有测量值与原因码仅基于 2D 屏幕空间几何特征，作为体育健身动作训练辅助参考，不构成医疗康复或损伤诊断依据；
> 2. **自包含离线演示**：为应对答辩现场网络或环境硬件波动，验证包已提供预渲染的标注 MP4 视频与关键帧截图库，作为最高可靠性的答辩灾备支撑。
