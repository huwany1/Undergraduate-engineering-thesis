# MediaPipe 深蹲真实数据集端到端演示交付报告 (Dataset Demo Report)

本报告沉淀了精选自开源计算机视觉与姿态估计基准的深蹲真实视频，通过 **MediaPipe Tasks PoseLandmarker** 官方视频流模型、**1€ 自适应滤波**、**有限状态机 (FSM)** 以及 **规则评估引擎** 执行端到端推理与辅助评价的完整演示资产。

---

## 一、数据集选型与资产清单 (Dataset Overview)

| 素材编号 | 素材名称 | 来源基准 | 原始分辨率 | 帧率 (FPS) | 总帧数 | 时长 | 适用评估要点 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DEMO_01** | 标准侧身深蹲演示素材 | `rohanx01/Squat-Analysis-Model` | 608 × 1080 | 29.97 | 614 | 20.5s | 连续侧视标准深蹲、动作周期安全时长门禁检验 |
| **DEMO_02** | 深度屈曲深蹲演示素材 | `RishitToteja/Exercise-Detection-Mediapipe` | 720 × 912 | 25.00 | 859 | 34.4s | 连续多轮大屈曲深蹲、躯干前倾规则 (R-LEAN-001) 触发与辅助建议 |
| **DEMO_03** | 正面视角深蹲对比素材 | `RishitToteja/Exercise-Detection-Mediapipe` | 720 × 960 | 25.00 | 187 | 7.5s | 正面视角动作规范度、深度达标 (ACCEPTABLE) 综合通过 |

> [!NOTE]
> **数据分级隔离保护**：
> - 原始视频存放在 `data/S1_raw_sensitive/demo_squats/`，受 `.gitignore` 保护并绑定 `PERMIT-DEMO-DATASET-v1.0` 准入许可，防止向代码库泄漏原始未经授权的大体积二进制素材。
> - 标注叠加回放视频保存在 `reports/dataset_demo/replays/`，逐帧时序证据保存于 `reports/dataset_demo/sidecars/`。

---

## 二、端到端流水线评估结果汇总 (Evaluation Summary)

```mermaid
flowchart LR
    A["真实深蹲视频<br>(MP4)"] --> B["P1 姿态视频链路<br>(MediaPipe Tasks 33关键点)"]
    B --> C["P2 时序闭环<br>(1€滤波 + FSM状态机)"]
    C --> D["P3 规则评估<br>(深度/前倾/周期规则)"]
    D --> E["演示看板 & Web UI<br>(HTTP 206流式 + 图表联动)"]
```

| 素材编号 | 识别完成次数 | 动作合格次数 | 实测最小膝角 | 实测最大前倾角 | 核心评估结论与规则反馈 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **DEMO_01_STANDARD_SQUAT** | 1 | 0 | 165.2° | 22.8° | `NOT_EVALUATED` (DISCARDED_TIMEOUT): 动作下蹲长停顿（历时 10.9s），触发周期安全门禁 |
| **DEMO_02_DEEP_SQUAT** | 6 | 0 | 78.4° | 58.1° | `NEEDS_IMPROVEMENT` (EXCESSIVE_TORSO_LEAN): 6 次完整深蹲均达到深度标准，但前倾角均超标 (52.1°~58.1° > 45.0°) |
| **DEMO_03_FRONT_VIEW_COMPARISON** | 1 | 1 | 91.2° | 32.6° | `ACCEPTABLE` (ACCEPTABLE): 动作规范，下蹲深度充分，躯干姿态保持良好 |

---

## 三、一键运行与复现指令 (Reproduction Guide)

```bash
# 1. 下载真实深蹲演示数据集
uv run python scripts/download_squat_dataset.py

# 2. 运行 MediaPipe 端到端流水线演示套件
uv run python scripts/run_dataset_demo.py

# 3. 启动交互式 Web 演示系统并在浏览器中交互验证
uv run python scripts/run_web_demo.py --open
```

> [!TIP]
> 启动 Web 演示界面后，点击左侧栏顶部的 **「MediaPipe 真实数据」** 按钮，即可在 5 大黄金测试用例与真实视频数据集演示之间无缝切换。
