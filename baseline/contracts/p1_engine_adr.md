# ADR-P1-001: 姿态估计引擎选型与资产管理决策记录

- **状态**：已批准 (APPROVED)
- **方案编号**：`ADR-P1-ENGINE-v1.0`
- **对应门禁**：`G1-P1`
- **责任人**：技术负责人

---

## 1. 上下文与需求

P1 姿态视频链路负责将 P0 准入的受控单人侧视深蹲视频逐帧转换为标准的 33 个姿态关键点、可见度与存在性元数据。
根据 `P1_姿态视频链路_P0级详细实施方案.md`，离线视频逐帧处理必须具备以下特性：
1. 逐帧严格保序，不丢帧、不抽帧；
2. 引擎原生支持按调用方提供的严格递增时间戳 (`timeline_us` / `timestamp_ms`) 进行时序处理；
3. 输出中立 DTO，阻断第三方 SDK 内部对象外溢；
4. 模型资产受控、来源合法，在无网络 CI 环境下提供确定性测试备选。

## 2. 候选对比与评估

| 候选方案 | 版本 / 接口模式 | 优势 | 劣势 / 约束 | 结论 |
|---|---|---|---|---|
| **MediaPipe Tasks PoseLandmarker** | `mediapipe 0.10.21` / `RunningMode.VIDEO` | 原生支持逐帧传入自定义时间戳；Google 官方推荐最新架构；输出包含 33 点、visibility 与 presence | 需要独立的 `.task` 模型资产文件（如 `pose_landmarker_full.task`） | **正式生产候选 (Primary Candidate)** |
| **MediaPipe Legacy Pose** | `mp.solutions.pose` | 内置模型无需外置文件 | 缺乏显式视频时间戳输入接口；不符合 P1 调用方时间契约约束；仅作对比研究 | **非正式生产实现 (Exploratory Only)** |
| **Deterministic Mock Pose Engine** | 内部实现合成引擎 | 100% 确定性、无网络/GPU/模型依赖，可注入任意异常场景（无姿态、遮挡、越界、乱序） | 不具备真实图像识别能力 | **CI 与门禁回归专用引擎 (Test/CI Engine)** |

## 3. 决策结果

1. **确定 MediaPipe Tasks `PoseLandmarker` (`RunningMode.VIDEO`) 为 P1 正式实现引擎**。
2. 建立端口-适配器架构 (`PoseEngine` 抽象端口)，以适配器模式将 MediaPipe Tasks 输出封装为中立数据类 `PoseFrameResult`。
3. 建立受控模型资产管理规范：
   - 官方模型：`pose_landmarker_full.task`
   - 官方来源：`https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task`
   - 许可证：Apache License 2.0
   - 受控存放路径：`models/pose_landmarker_full.task`（由 `.gitignore` 排除，禁止提交至公开仓库）
   - SHA-256 校验：加载前必须比对预设 SHA-256 哈希，若缺失或损坏抛出 `MODEL_ASSET_MISSING` 或 `MODEL_HASH_MISMATCH`。
4. 提供 `DeterministicMockPoseEngine` 用于离线单元测试与门禁验证，保障自动化测试高确定性与秒级通过。
