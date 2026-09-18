# -*- coding: utf-8 -*-
"""
P4 自动化验证包一键生成与核验脚本
用法:
    uv run python scripts/run_p4_validation.py
"""

import sys
from pathlib import Path

# 将项目根目录加入模块搜索路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from p4_validation import (
    GoldenAssetRegistry,
    SyntheticStreamGenerator,
    DeterministicReplayer,
    TestMatrixVerifier,
    EvidencePackager,
    VerificationStatus,
)


def main():
    print("=" * 72)
    print("  P4 动作评估验证包流水线启动 (Validation Package Runner)")
    print("=" * 72)

    registry = GoldenAssetRegistry()
    replayer = DeterministicReplayer()
    packager = EvidencePackager()

    specs = registry.list_all()
    traces = []
    results = []

    print(f"\n[1/3] 执行 5 大黄金场景确定性时序回放与断言核验 (共 {len(specs)} 项)...")
    for spec in specs:
        print(f"  -> 驱动用例: [{spec.case_id.value}] {spec.case_name}")
        stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
        trace = replayer.replay_stream(spec.case_id, stream)
        traces.append(trace)

        res = TestMatrixVerifier.verify_case(spec, trace)
        results.append(res)

        badge = "[PASS]" if res.status == VerificationStatus.PASS else "[FAIL]"
        print(f"     核验结论: {badge} | 计数: {res.actual_count} | 状态: {res.actual_status} | 耗时: {res.execution_time_ms:.1f}ms")
        if res.diff_reasons:
            for diff in res.diff_reasons:
                print(f"     ! 差异: {diff}")

    # 导出全套自包含报告与资产
    output_dir = project_root / "reports" / "validation_package"
    print(f"\n[2/3] 正在生成自包含验证包交付物至: {output_dir} ...")
    summary = packager.package_suite(
        specs=specs,
        traces=traces,
        results=results,
        output_dir=output_dir,
        generate_video=True,
    )

    print("\n[3/3] 交付资产打包完成清单:")
    for rel_path, sha in summary.artifacts_manifest.items():
        print(f"  * {rel_path:<45} (SHA: {sha[:12]}...)")

    print("\n" + "=" * 72)
    print("  P4 动作评估验证包执行总览 (Summary)")
    print("=" * 72)
    print(f"  基线编号:       {summary.baseline_id}")
    print(f"  Git Commit:     {summary.git_commit}")
    print(f"  总用例数:       {summary.total_cases}")
    print(f"  通过用例数:     {summary.passed_cases}")
    print(f"  失败用例数:     {summary.failed_cases}")
    print(f"  吻合率:         {summary.concordance_rate * 100:.1f}%")
    print(f"  动作计数 MAE:   {summary.mae_count:.2f}")
    print(f"  异常阻断率:     {summary.rejection_rate * 100:.1f}%")
    print("=" * 72)

    if summary.failed_cases > 0:
        print("\n[ERROR] 存在核验失败用例，阻断交付！")
        sys.exit(1)
    else:
        print("\n[SUCCESS] 5 大黄金用例全量 100% 通过，自包含答辩验证包构建完毕！")
        sys.exit(0)


if __name__ == "__main__":
    main()
