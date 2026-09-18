# -*- coding: utf-8 -*-
"""
CI 测试套件：P0 口径冻结与准入门禁自动化测试
Baseline ID: P0-SQUAT-SIDE-OFFLINE-v1.0
"""

import sys
import hashlib
import json
import csv
from pathlib import Path
import pytest
import yaml

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.verify_p0_gates import P0GateVerifier, BASELINE_DIR, CONTRACTS_DIR, TEMPLATES_DIR


@pytest.fixture
def verifier():
    return P0GateVerifier()


class TestP0BaselineGates:
    """自动化测试 G0-G6 各门禁的合规性与确定性"""

    def test_g0_scope_consistency(self, verifier):
        """测试 G0 范围一致性：禁止承诺项齐备，0 处违规表述"""
        scope_yaml_path = CONTRACTS_DIR / "scope_contract.yaml"
        assert scope_yaml_path.exists(), "scope_contract.yaml 必须存在"

        with open(scope_yaml_path, "r", encoding="utf-8") as f:
            scope_cfg = yaml.safe_load(f)

        prohibited = scope_cfg.get("prohibited_claims", [])
        assert len(prohibited) >= 5, "禁止承诺清单必须包含医疗诊断、自动矫正等核心禁止项"
        assert "医疗诊断" in prohibited
        assert "自动矫正成功" in prohibited
        assert "全链路已集成" in prohibited

        verifier.verify_g0_scope_consistency()
        assert verifier.results.get("G0_SCOPE_CONSISTENCY") is True

    def test_g1_camera_executable(self, verifier):
        """测试 G1 机位规范：几何高度与距离标定齐备，双样张制度与现场表头有效"""
        cam_yaml_path = CONTRACTS_DIR / "camera_profile.yaml"
        assert cam_yaml_path.exists(), "camera_profile.yaml 必须存在"

        with open(cam_yaml_path, "r", encoding="utf-8") as f:
            cam_cfg = yaml.safe_load(f)

        geom = cam_cfg.get("geometry_calibration", {})
        assert 80 <= geom.get("optical_axis_height_cm", 0) <= 100
        assert 2.5 <= geom.get("distance_to_subject_m", 0) <= 3.5

        dual_specimen = cam_cfg.get("dual_specimen_protocol", {})
        assert "pass_specimen" in dual_specimen
        assert "fail_specimen" in dual_specimen

        field_csv_path = TEMPLATES_DIR / "field_record_template.csv"
        assert field_csv_path.exists(), "field_record_template.csv 必须存在"
        with open(field_csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            assert "camera_profile_id" in headers
            assert "field_result" in headers
            assert "exclusion_reason" in headers

        verifier.verify_g1_camera_executable()
        assert verifier.results.get("G1_CAMERA_EXECUTABLE") is True

    def test_g2_rule_deterministic(self, verifier):
        """测试 G2 规则确定性：三条核心规则定义完备，聚合策略前置覆盖明确"""
        rule_yaml_path = CONTRACTS_DIR / "rule_set.yaml"
        assert rule_yaml_path.exists(), "rule_set.yaml 必须存在"

        with open(rule_yaml_path, "r", encoding="utf-8") as f:
            rule_cfg = yaml.safe_load(f)

        rules = {r["rule_id"]: r for r in rule_cfg.get("rules", [])}
        assert "R-CYCLE-001" in rules
        assert "R-DEPTH-001" in rules
        assert "R-LEAN-001" in rules

        # 检查状态机序列
        cycle_seq = rules["R-CYCLE-001"]["temporal_parameters"]["state_sequence"]
        assert cycle_seq == ["STANDING", "DESCENDING", "BOTTOM", "ASCENDING", "STANDING"]

        # 检查聚合策略
        agg = rule_cfg.get("aggregation_policy", {})
        assert "AGG-STRICT-GATED" in agg.get("policy_id", "")
        assert "NOT_EVALUATED" in agg.get("pre_gate_override", {}).get("rule", "")

        verifier.verify_g2_rule_deterministic()
        assert verifier.results.get("G2_RULE_DETERMINISTIC") is True

    def test_g3_consent_traceable(self, verifier):
        """测试 G3 授权可追溯与数据分级治理：成年人准入、凭证解耦及 S1/S2 防泄漏"""
        consent_yaml_path = CONTRACTS_DIR / "consent_governance.yaml"
        assert consent_yaml_path.exists(), "consent_governance.yaml 必须存在"

        with open(consent_yaml_path, "r", encoding="utf-8") as f:
            consent_cfg = yaml.safe_load(f)

        assert consent_cfg.get("eligibility_rules", {}).get("min_age") >= 18
        assert consent_cfg.get("lifecycle_and_disposal", {}).get("retention_until") is not None

        # 检查 S1-S4 分级
        classif = consent_cfg.get("data_classification_and_handling", {})
        for tier in ["S1_raw_sensitive", "S2_controlled_derived", "S3_presentation_evidence", "S4_public_contracts"]:
            assert tier in classif

        # 检查 .gitignore 防泄漏
        gitignore_path = ROOT_DIR / ".gitignore"
        assert gitignore_path.exists()
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gi_content = f.read()
            assert "S1_raw_sensitive" in gi_content
            assert "S2_derived_features" in gi_content

        verifier.verify_g3_consent_traceable()
        assert verifier.results.get("G3_CONSENT_TRACEABLE") is True

    def test_g4_dataset_isolated(self, verifier):
        """测试 G4 数据集物理隔离与零伪真值：校准/验证集严格按受试者隔离"""
        ds_yaml_path = CONTRACTS_DIR / "dataset_manifest.yaml"
        assert ds_yaml_path.exists(), "dataset_manifest.yaml 必须存在"

        with open(ds_yaml_path, "r", encoding="utf-8") as f:
            ds_cfg = yaml.safe_load(f)

        subsets = ds_cfg.get("subsets", {})
        assert "calibration_set" in subsets
        assert "validation_set" in subsets
        assert "invalid_set" in subsets

        # 检查零伪真值红线
        discipline = ds_cfg.get("ground_truth_discipline", {})
        assert discipline.get("zero_fake_truth_mandate") is not None

        verifier.verify_g4_dataset_isolated()
        assert verifier.results.get("G4_DATASET_ISOLATED") is True

    def test_g5_version_auditable(self, verifier):
        """测试 G5 版本审计：实时重算契约 SHA-256，必须与基线清单 100% 吻合"""
        verifier.verify_g5_version_auditable()
        assert verifier.results.get("G5_VERSION_AUDITABLE") is True

    def test_g6_refusal_matrix_desktop_simulation(self, verifier):
        """测试 G6-P0 无效状态矩阵演练：8 组异常输入必须 100% 熔断阻断，不计数、不评价"""
        verifier.run_g6_desktop_simulation()
        assert verifier.results.get("G6_REFUSAL_CONTRACT_SIMULATION") is True

        sim_records = verifier.details["G6_REFUSAL_CONTRACT_SIMULATION"]["extra"]["simulation_records"]
        assert len(sim_records) == 8
        for rec in sim_records:
            assert rec["passed"] is True, f"场景 {rec['scenario_id']} 演练失败"
            assert rec["rep_count"] == 0, f"场景 {rec['scenario_id']} 不得增加动作次数"
            assert rec["expected"] == rec["actual"], f"场景 {rec['scenario_id']} 拒绝码不匹配"

    def test_admission_record_template_schema(self):
        """测试单条视频准入记录样本的数据格式与凭证解耦字段"""
        adm_path = TEMPLATES_DIR / "admission_record_template.json"
        assert adm_path.exists()
        with open(adm_path, "r", encoding="utf-8") as f:
            adm = json.load(f)

        assert adm.get("baseline_id") == "P0-SQUAT-SIDE-OFFLINE-v1.0"
        permit = adm.get("runtime_permit", {})
        assert permit.get("processing_permit_id") is not None
        assert permit.get("disposal_status") is not None
        assert "baseline_fingerprint" in adm
