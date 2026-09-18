# -*- coding: utf-8 -*-
"""
P4 自动化测试套件：黄金资产清单契约与 Schema 校验测试
"""

import json
from pathlib import Path
import pytest

from p4_validation.contracts import TestCaseId, GoldenSampleSpec
from p4_validation.golden_assets import GoldenAssetRegistry


def test_golden_asset_registry_full_coverage():
    registry = GoldenAssetRegistry()
    specs = registry.list_all()

    assert len(specs) == 5
    case_ids = {s.case_id for s in specs}
    assert case_ids == {
        TestCaseId.TC_01_PERFECT_SQUAT,
        TestCaseId.TC_02_SHALLOW_SQUAT,
        TestCaseId.TC_03_EXCESSIVE_LEAN,
        TestCaseId.TC_04_DUAL_DEFECT,
        TestCaseId.TC_05_OUT_OF_FRAME,
    }


def test_golden_asset_spec_integrity():
    registry = GoldenAssetRegistry()
    for spec in registry.list_all():
        assert spec.expected_count in (0, 1)
        assert spec.expected_status in ("ACCEPTABLE", "NEEDS_IMPROVEMENT", "NOT_EVALUATED")
        assert len(spec.expected_primary_reason) > 0
        assert isinstance(spec.expected_reason_codes, list)
        assert len(spec.expected_reason_codes) >= 1

        # 容差带合法性
        band = spec.tolerance_band
        assert band.knee_min_deg[0] <= band.knee_min_deg[1]
        assert band.torso_max_deg[0] <= band.torso_max_deg[1]
        assert band.angle_margin_deg > 0.0


def test_manifest_export_and_json_serialization(tmp_path: Path):
    registry = GoldenAssetRegistry()
    export_file = tmp_path / "golden_manifest.json"
    exported_path = registry.export_manifest(export_file)

    assert exported_path.exists()
    with open(exported_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["manifest_version"] == "1.0.0"
    assert data["baseline_id"] == "P0-SQUAT-SIDE-OFFLINE-v1.0"
    assert len(data["samples"]) == 5
    assert data["samples"][0]["case_id"] == TestCaseId.TC_01_PERFECT_SQUAT.value
