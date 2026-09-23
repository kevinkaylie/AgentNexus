"""CP-01～26 执行与覆盖映射的机械校验（路线图第 4 步）。

这一层不重复验证行为语义，而是保证**记录不会比证据说得更多**：

- 覆盖映射必须与 ``fixtures/cp-matrix.json`` 的 CP 集合完全一致（新增 CP 会强制补映射）；
- 映射里的 node id 必须真实存在（防止测试改名后记录继续"复述"一个不存在的证据）；
- blocked/partial 必须写明 owner 与限制；verified 必须有映射测试；
- 渲染出的运行记录不得把 blocked/partial 写成通过，也不得漏掉任何一条限制；
- 门禁关闭期间 ``compatibility.json`` 的允许列表必须保持为空（冻结不能悄悄发生）。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "specs" / "profiles" / "code-review" / "v1"
MATRIX = BASE / "fixtures" / "cp-matrix.json"
COVERAGE = BASE / "bindings" / "l0-agentnexus-cp-coverage.json"
COMPATIBILITY = BASE / "compatibility.json"
RECORD = BASE / "fixtures" / "binding" / "cp-execution-record-2026-09-23.md"
RUNNER = ROOT / "scripts" / "run_cp_matrix.py"


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _runner():
    spec = importlib.util.spec_from_file_location("cp_matrix_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def matrix() -> dict:
    return _load(MATRIX)


@pytest.fixture(scope="module")
def coverage() -> dict:
    return _load(COVERAGE)


def test_coverage_covers_every_cp_exactly_once(matrix, coverage):
    matrix_ids = [case["id"] for case in matrix["cases"]]
    cov_ids = [case["id"] for case in coverage["cases"]]
    assert cov_ids == matrix_ids
    assert len(set(cov_ids)) == len(cov_ids) == 26


def test_coverage_node_ids_exist_in_test_files(coverage):
    for case in coverage["cases"]:
        for node in case.get("tests", []):
            path, _, name = node.partition("::")
            target = ROOT / path
            assert target.exists(), f"{case['id']}: 测试文件不存在 {path}"
            assert f"def {name}(" in target.read_text(encoding="utf-8"), (
                f"{case['id']}: 测试函数不存在 {node}（映射已腐烂）"
            )


def test_blocked_and_partial_cases_declare_limits(coverage):
    for case in coverage["cases"]:
        if case["status"] == "blocked":
            assert case.get("owner"), f"{case['id']}: blocked 缺 owner"
            assert case.get("limitation"), f"{case['id']}: blocked 缺 limitation"
            assert not case.get("tests"), f"{case['id']}: blocked 不应映射测试"
        elif case["status"] == "partial":
            assert case.get("limitation"), f"{case['id']}: partial 缺 limitation"
            assert case.get("tests"), f"{case['id']}: partial 应有已执行的证据"
        else:
            assert case["status"] == "verified"
            assert case.get("tests"), f"{case['id']}: verified 但没有任何映射测试"


def test_real_mapping_passes_the_validator(matrix, coverage):
    assert _runner().validate_mapping(matrix, coverage) == []


def test_validator_flags_a_renamed_test(matrix, coverage):
    """映射腐烂必须报错，而不是继续把不存在的用例算作证据。"""
    broken = json.loads(json.dumps(coverage))
    broken["cases"][0]["tests"] = ["tests/test_code_review_api.py::test_this_does_not_exist"]
    problems = _runner().validate_mapping(matrix, broken)
    assert any("test_this_does_not_exist" in p for p in problems)


def test_validator_flags_a_missing_cp(matrix, coverage):
    broken = json.loads(json.dumps(coverage))
    broken["cases"] = [c for c in broken["cases"] if c["id"] != "CP-15"]
    problems = _runner().validate_mapping(matrix, broken)
    assert any("CP-15" in p for p in problems)


def test_validator_flags_verified_without_evidence(matrix, coverage):
    broken = json.loads(json.dumps(coverage))
    target = next(c for c in broken["cases"] if c["status"] == "verified")
    target["tests"] = []
    problems = _runner().validate_mapping(matrix, broken)
    assert any(target["id"] in p and "verified" in p for p in problems)


def test_validator_flags_blocked_without_owner(matrix, coverage):
    broken = json.loads(json.dumps(coverage))
    target = next(c for c in broken["cases"] if c["status"] == "blocked")
    target.pop("owner", None)
    problems = _runner().validate_mapping(matrix, broken)
    assert any(target["id"] in p and "owner" in p for p in problems)


def test_verdict_for_merges_parametrized_ids():
    """``-rA`` 里参数化用例是 ``node[param]``，归并必须命中，且取最坏结果。"""
    runner = _runner()
    outcomes = {
        "tests/x.py::test_row[alpha]": "PASSED",
        "tests/x.py::test_row[beta]": "FAILED",
        "tests/x.py::test_other": "PASSED",
    }
    assert runner.verdict_for("tests/x.py::test_row", outcomes) == "FAILED"
    assert runner.verdict_for("tests/x.py::test_other", outcomes) == "PASSED"
    assert runner.verdict_for("tests/x.py::test_absent", outcomes) == "NOT_RUN"


def test_verdict_for_treats_skip_as_missing():
    runner = _runner()
    outcomes = {"tests/x.py::test_row[a]": "PASSED", "tests/x.py::test_row[b]": "SKIPPED"}
    assert runner.verdict_for("tests/x.py::test_row", outcomes) == "SKIPPED"
    assert "SKIPPED" in runner.MISSING_VERDICTS


def test_record_never_renders_blocked_or_partial_as_pass(matrix, coverage):
    """用一组"全部通过"的假结果渲染，blocked/partial 仍不得显示为通过。"""
    runner = _runner()
    outcomes = {node: "PASSED" for node in runner.collect_tests(coverage)}
    structural = {case["id"]: runner.StructuralResult() for case in matrix["cases"]}
    record = runner.build_record(
        matrix, coverage, {"structural": structural, "outcomes": outcomes}, "input", "cmd", "2026-09-23"
    )
    rows = {
        row.split("|")[1].strip(): row
        for row in record.splitlines()
        if row.startswith("| CP-")
    }
    assert len(rows) == 26
    for case in coverage["cases"]:
        row = rows[case["id"]]
        if case["status"] == "verified":
            assert "AgentNexus 侧通过" in row
        else:
            assert "AgentNexus 侧通过" not in row
            assert case["id"] in record.split("## 限制与未覆盖")[1]


def test_committed_record_is_consistent_with_declarations(matrix, coverage):
    """已提交的运行记录必须覆盖全部 26 个 CP，且限制小节与声明一致。"""
    assert RECORD.exists(), "缺少 CP 运行记录（跑 scripts/run_cp_matrix.py 生成）"
    text = RECORD.read_text(encoding="utf-8")
    for case in matrix["cases"]:
        assert f"| {case['id']} |" in text, f"记录缺少 {case['id']}"
    limits = text.split("## 限制与未覆盖")[1]
    non_verified = [c["id"] for c in coverage["cases"] if c["status"] != "verified"]
    for cp in non_verified:
        assert f"**{cp}**" in limits, f"记录的限制小节缺少 {cp}"
    assert "不声明符合性" in text and "wire conformance" in text
    assert "BINDING-GATE-1 关闭" in text


def test_committed_record_has_no_failed_evidence(matrix):
    """记录声明 0 个证据失败/缺失——若上游用例变红，这里会先失败提示重新生成。"""
    text = RECORD.read_text(encoding="utf-8")
    match = re.search(r"证据失败/缺失：\*\*(\d+)\*\*", text)
    assert match, "记录缺少汇总行"
    assert int(match.group(1)) == 0


def test_compatibility_allowlists_stay_empty_while_gate_closed():
    """第 3 步的机械底线：三方冻结完成前，允许列表不得被填入，也不得放行 operative。"""
    data = _load(COMPATIBILITY)
    assert data["default_decision"] == "reject"
    assert data["wildcards_allowed"] is False
    assert data["nexus"]["schema_versions"] == []
    assert data["nexus"]["contract_revisions"] == []
    assert data["nexus"]["observed_contract"]["operative_allowlist"] is False
    assert data["externally_owned_vocabularies"]["artifact_access_scope"] == []
    assert data["externally_owned_vocabularies"]["operative_allowlist"] is False
    gate = _load(BASE / "bindings" / "evidence" / "closure-checklist.json")["gate"]
    assert gate["status"] == "closed"
