# -*- coding: utf-8 -*-
"""
P4 自动化测试套件：证据抽帧与自包含资产包打包归档测试
"""

import json
from pathlib import Path
import pytest
import cv2

from p4_validation.contracts import TestCaseId
from p4_validation.golden_assets import GoldenAssetRegistry, SyntheticStreamGenerator
from p4_validation.replayer import DeterministicReplayer
from p4_validation.matrix_verifier import TestMatrixVerifier
from p4_validation.packager import EvidencePackager


def test_evidence_packaging_and_manifest_hashes(tmp_path: Path):
    registry = GoldenAssetRegistry()
    replayer = DeterministicReplayer()
    packager = EvidencePackager()

    specs = registry.list_all()
    traces = []
    results = []

    for spec in specs:
        stream = SyntheticStreamGenerator.generate_case_stream(spec.case_id)
        trace = replayer.replay_stream(spec.case_id, stream)
        traces.append(trace)

        res = TestMatrixVerifier.verify_case(spec, trace)
        results.append(res)

    output_dir = tmp_path / "val_pkg"
    # generate_video=False 保证测试秒级运行
    summary = packager.package_suite(
        specs=specs,
        traces=traces,
        results=results,
        output_dir=output_dir,
        generate_video=False,
    )

    # 1. 验证关键文件生成
    manifest_file = output_dir / "validation_manifest.json"
    report_file = output_dir / "summary_report.md"
    csv_file = output_dir / "metrics_summary.csv"
    screenshots_dir = output_dir / "screenshots"

    assert manifest_file.exists()
    assert report_file.exists()
    assert csv_file.exists()
    assert screenshots_dir.exists()

    # 2. 验证截图尺寸与数量
    png_files = list(screenshots_dir.glob("*.png"))
    assert len(png_files) >= 5
    first_img = cv2.imread(str(png_files[0]))
    assert first_img is not None
    assert first_img.shape == (720, 1280, 3)

    # 3. 验证 manifest 哈希一致性
    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_cases"] == 5
    assert data["passed_cases"] == 5
    assert data["failed_cases"] == 0
    assert "artifacts_manifest" in data

    for rel_path_str, recorded_hash in data["artifacts_manifest"].items():
        actual_file = output_dir / rel_path_str
        assert actual_file.exists(), f"清单中声明的文件不存在: {rel_path_str}"
        computed_hash = EvidencePackager._compute_sha256(actual_file)
        assert recorded_hash == computed_hash, f"文件哈希被篡改或不匹配: {rel_path_str}"
