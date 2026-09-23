"""T1–T6 收口清单与证据校验器的机械保证。

覆盖两类事实：
1. 随包发布的清单/模板本身自洽（每条证据要求都有模板 record、检查名均已登记）；
2. 校验器真的会拒绝「声称关闭却拿不出证据」「提前放行」「声明与实际不一致」，
   并且在证据完整时接受关闭——否则单一地放行等于没有收口。
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "specs" / "profiles" / "code-review" / "v1"
CHECKER = PACKAGE / "tools" / "check_evidence.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_evidence_under_test", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker():
    return _load_checker()


def sha256_of(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def point_at(module, root: Path) -> None:
    module.REPO_ROOT = root
    module.BASE = root
    module.EVIDENCE = root / "bindings" / "evidence"
    module.CHECKLIST = module.EVIDENCE / "closure-checklist.json"
    module.TEMPLATES = module.EVIDENCE / "templates"
    module.RECEIVED = module.EVIDENCE / "received"
    module.COMPATIBILITY = root / "compatibility.json"
    module.ERROR_SCHEMA = None


def point_at_package(module, package_root: Path, repo_root: Path) -> None:
    """包与宿主分离：包来自 ``package_root``，宿主标记在 ``repo_root`` 找。"""
    point_at(module, package_root)
    module.REPO_ROOT = repo_root


def locked_compatibility() -> dict:
    return {
        "default_decision": "reject",
        "nexus": {"observed_contract": {"operative_allowlist": False}},
        "externally_owned_vocabularies": {"artifact_allowlist": [], "artifact_access_scope": [], "operative_allowlist": False},
    }


def synthetic_item(status: str = "open") -> dict:
    return {
        "id": "T1",
        "title": "synthetic",
        "owner": "Nexus_Agent",
        "status": status,
        "status_reason": "synthetic",
        "template": "templates/T1.json",
        "evidence": [
            {
                "id": "T1.x",
                "kind": "production_sample",
                "record_key": "x",
                "blocking": True,
                "required_fields": ["samples", "attested_by"],
                "checks": ["sample_bytes"],
                "required_case_coverage": ["a"],
            },
            {
                "id": "T1.y",
                "kind": "behavior_evidence",
                "record_key": "y",
                "blocking": True,
                "required_fields": ["note_count_before", "note_count_after"],
                "checks": ["note_count_unchanged"],
            },
        ],
    }


def write_local_evidence_package(
    root: Path,
    *,
    production: bool = False,
    samples_production: bool = False,
    manifest_sha: str | None = None,
    capture_version: str | None = None,
    rechecks=None,
    host_markers: bool = True,
) -> dict:
    """写一个最小的本地证据包（docs/evidence/l0-test/），返回 source-snapshot 文档。

    `host_markers=True` 时补齐宿主标记，使宿主证据审计真正执行；Portability 用例
    则传 False，模拟"包被复制到别处"。
    """
    base = root / "docs" / "evidence" / "l0-test"
    base.mkdir(parents=True, exist_ok=True)
    samples = base / "nexus-http-samples.json"
    samples.write_text(json.dumps({"evidence_kind": "synthetic_local_http_capture", "production": samples_production, "records": []}), encoding="utf-8")
    results = base / "nexus-test-results.xml"
    results.write_text("<testsuite tests='1'/>", encoding="utf-8")
    if host_markers:
        (root / "AGENTS.md").write_text("# synthetic host\n", encoding="utf-8")
        (root / "docs" / "wip.md").write_text("# synthetic wip\n", encoding="utf-8")
        (root / "tests").mkdir(parents=True, exist_ok=True)
        (root / "tests" / "conftest.py").write_text("# synthetic conftest\n", encoding="utf-8")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    snapshot = {
        "captured_at": "2026-08-01T00:00:00Z",
        "evidence_kind": "isolated_local_implementation",
        "production": production,
        "profile_manifest_sha256": manifest_sha
        if manifest_sha is not None
        else hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "capture_package_version": capture_version
        if capture_version is not None
        else manifest.get("package_version"),
        "artifacts": [
            {"path": "nexus-http-samples.json", "sha256": hashlib.sha256(samples.read_bytes()).hexdigest()},
            {"path": "nexus-test-results.xml", "sha256": hashlib.sha256(results.read_bytes()).hexdigest()},
        ],
    }
    if rechecks is not None:
        snapshot["profile_manifest_rechecks"] = rechecks
    (base / "source-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return snapshot


def drifted_snapshot(root: Path, **overrides) -> dict:
    """模拟"包已升级、pin 仍是采集时的旧值"：版本戳旧、pin 用旧摘要、无复核记录。"""
    kwargs = {"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"}
    kwargs.update(overrides)
    return write_local_evidence_package(root, **kwargs)


def good_recheck(root: Path) -> dict:
    """指向当前包摘要的合规复核记录（S3）。"""
    current = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    return {
        "checked_at": "2026-08-02T00:00:00Z",
        "checked_against_sha256": current,
        "command": "python specs/profiles/code-review/v1/tools/validate.py",
        "scope": "包自检与收口裁判；未重跑旧 HTTP/JUnit 样例",
        "result": "exit 0",
        "reexecuted": False,
    }


def build_package(root: Path, *, t1_status="open", t1_records=None, compat=None, template_records=None, gate="closed", extra_items=None, local_package: dict | None = None, snapshots: dict | None = None) -> Path:
    evidence = root / "bindings" / "evidence"
    (evidence / "templates").mkdir(parents=True, exist_ok=True)
    (evidence / "received").mkdir(parents=True, exist_ok=True)

    # 拒绝事实校验要读冻结错误契约及其引用（common.schema.json）；从真实包整体复制，
    # 保证测试与生产同源。
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    for schema_path in (PACKAGE / "schemas").glob("*.schema.json"):
        (root / "schemas" / schema_path.name).write_bytes(schema_path.read_bytes())
    (root / "manifest.json").write_text('{"package_version":"synthetic"}', encoding="utf-8")

    t1 = synthetic_item(t1_status)
    t1["local_evidence"] = {"status": "non_closing", "artifacts": ["nexus-http-samples.json", "nexus-test-results.xml"]}
    items = [t1]
    for tid in ("T2", "T3", "T4", "T5", "T6"):
        items.append(
            {"id": tid, "title": tid, "owner": "three-party", "status": "open", "status_reason": "x", "template": f"templates/{tid}.json", "evidence": []}
        )
    items.extend(extra_items or [])

    (evidence / "closure-checklist.json").write_text(
        json.dumps(
            {
                "tracker": "T1-T6-closure-checklist",
                "gate": {"name": "BINDING-GATE-1", "status": gate},
                "local_evidence_package": local_package
                if local_package is not None
                else {
                    "path": "docs/evidence/l0-test",
                    "snapshot": "source-snapshot.json",
                    "closing": False,
                    "host_markers": ["AGENTS.md", "docs/wip.md", "tests/conftest.py"],
                },
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    t1_template = {"_template": "T1", "t_item": "T1", "records": template_records if template_records is not None else {"x": {"status": "open"}, "y": {"status": "open"}}}
    (evidence / "templates" / "T1.json").write_text(json.dumps(t1_template, ensure_ascii=False), encoding="utf-8")
    for tid in ("T2", "T3", "T4", "T5", "T6"):
        (evidence / "templates" / f"{tid}.json").write_text(json.dumps({"t_item": tid, "records": {}}), encoding="utf-8")

    if t1_records is not None:
        (evidence / "received" / "T1.json").write_text(
            json.dumps({"t_item": "T1", "item_status": t1_status, "item_status_reason": "synthetic", "records": t1_records}, ensure_ascii=False),
            encoding="utf-8",
        )

    (root / "compatibility.json").write_text(json.dumps(compat if compat is not None else locked_compatibility()), encoding="utf-8")
    write_local_evidence_package(root, **(snapshots or {}))
    return root


def good_x_record() -> dict:
    payload = b'{"ok":true}'
    return {
        "status": "closed",
        "attested_by": "Nexus release engineering",
        "samples": [
            {
                "case": "a",
                "endpoint": "POST A/messages",
                "response_status": 202,
                "raw_bytes_b64": b64(payload),
                "sha256": sha256_of(payload),
                "byte_length": len(payload),
            }
        ],
    }


def good_y_record() -> dict:
    return {"status": "closed", "note_count_before": 1, "note_count_after": 1}


# --------------------------------------------------------------------- 真实包自检


def test_real_package_checklist_is_consistent(checker, capsys):
    assert checker.main() == 0
    out = capsys.readouterr().out
    assert "清单与模板对应：25 条证据要求" in out
    assert "0/6 已关闭" in out
    for item in ("T1", "T2", "T3", "T4", "T5", "T6"):
        assert f"{item} [open" in out
    assert "BINDING-GATE-1：closed" in out


def test_real_checklist_registers_every_check_name(checker):
    checklist = json.loads((PACKAGE / "bindings" / "evidence" / "closure-checklist.json").read_text(encoding="utf-8"))
    names = {name for item in checklist["items"] for spec in item["evidence"] for name in spec.get("checks", [])}
    assert names, "清单里没有任何检查名"
    assert names <= checker.KNOWN_CHECKS, f"未登记的检查名：{sorted(names - checker.KNOWN_CHECKS)}"


def test_real_checklist_has_no_received_records_yet(checker):
    received = PACKAGE / "bindings" / "evidence" / "received"
    assert sorted(p.name for p in received.glob("*.json")) == [], "收到证据记录后应同步更新清单声明与本文"


# --------------------------------------------------------------------- 校验器行为


def test_open_state_passes(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path))
    assert checker.main() == 0
    assert "0/6 已关闭" in capsys.readouterr().out


def test_valid_closure_is_accepted(checker, tmp_path, capsys):
    records = {"x": good_x_record(), "y": good_y_record()}
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records=records))
    assert checker.main() == 0
    out = capsys.readouterr().out
    assert "T1 [closed]" in out
    assert "1/6 已关闭" in out


def test_bad_digest_is_rejected(checker, tmp_path, capsys):
    record = good_x_record()
    record["samples"][0]["sha256"] = sha256_of(b"other bytes")
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": record, "y": good_y_record()}))
    assert checker.main() == 1
    assert "摘要不符" in capsys.readouterr().out


def test_wrong_byte_length_is_rejected(checker, tmp_path, capsys):
    record = good_x_record()
    record["samples"][0]["byte_length"] = 999
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": record, "y": good_y_record()}))
    assert checker.main() == 1
    assert "长度不符" in capsys.readouterr().out


def test_residual_placeholder_in_closed_record_is_rejected(checker, tmp_path, capsys):
    record = good_x_record()
    record["samples"][0]["redaction_note"] = "__TODO__"
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": record, "y": good_y_record()}))
    assert checker.main() == 1
    assert "残留占位符" in capsys.readouterr().out


def test_declared_closed_without_evidence_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, t1_status="closed"))
    assert checker.main() == 1
    assert "声明 closed 与实际 open 不一致" in capsys.readouterr().out


def test_declared_open_with_closed_evidence_is_rejected(checker, tmp_path, capsys):
    records = {"x": good_x_record(), "y": good_y_record()}
    point_at(checker, build_package(tmp_path, t1_status="open", t1_records=records))
    assert checker.main() == 1
    assert "声明 open 与实际 closed 不一致" in capsys.readouterr().out


def test_semantic_check_failure_is_rejected(checker, tmp_path, capsys):
    record = good_y_record()
    record["note_count_after"] = 2
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": good_x_record(), "y": record}))
    assert checker.main() == 1
    assert "重放前后评论数必须相同" in capsys.readouterr().out


def test_missing_case_coverage_is_rejected(checker, tmp_path, capsys):
    record = good_x_record()
    record["samples"][0]["case"] = "b"
    record["samples"].append(dict(record["samples"][0]))
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": record, "y": good_y_record()}))
    assert checker.main() == 1
    assert "缺用例 a" in capsys.readouterr().out


def test_missing_required_field_is_rejected(checker, tmp_path, capsys):
    record = good_x_record()
    record["attested_by"] = ""
    point_at(checker, build_package(tmp_path, t1_status="closed", t1_records={"x": record, "y": good_y_record()}))
    assert checker.main() == 1
    assert "closed 记录缺必需字段" in capsys.readouterr().out


def test_premature_enablement_is_rejected(checker, tmp_path, capsys):
    compat = locked_compatibility()
    compat["externally_owned_vocabularies"]["operative_allowlist"] = True
    compat["externally_owned_vocabularies"]["artifact_access_scope"] = ["service_private"]
    point_at(checker, build_package(tmp_path, compat=compat))
    assert checker.main() == 1
    out = capsys.readouterr().out
    assert "必须为 false" in out
    assert "artifact_access_scope 必须为空列表" in out


def test_gate_cannot_open_while_items_open(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, gate="open"))
    assert checker.main() == 1
    assert "按证据计算应为 closed" in capsys.readouterr().out


def test_template_missing_record_key_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, template_records={"x": {"status": "open"}}))
    assert checker.main() == 1
    assert "模板缺 record_key y" in capsys.readouterr().out


def test_unknown_check_name_is_rejected(checker, tmp_path, capsys):
    item = synthetic_item()
    item["evidence"][0]["checks"] = ["sample_bytes", "not_a_real_check"]
    point_at(checker, build_package(tmp_path, extra_items=None, template_records={"x": {"status": "open"}, "y": {"status": "open"}}))
    # 直接改写清单中的检查名
    checklist_path = tmp_path / "bindings" / "evidence" / "closure-checklist.json"
    doc = json.loads(checklist_path.read_text(encoding="utf-8"))
    doc["items"][0] = item
    checklist_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert checker.main() == 1
    assert "未登记检查名" in capsys.readouterr().out


def test_wrong_item_ids_are_fatal(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    checklist_path = root / "bindings" / "evidence" / "closure-checklist.json"
    doc = json.loads(checklist_path.read_text(encoding="utf-8"))
    doc["items"] = doc["items"][:5]
    checklist_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 2
    assert "必须恰好为" in capsys.readouterr().out


def test_missing_checklist_is_fatal(checker, tmp_path, capsys):
    point_at(checker, tmp_path)
    assert checker.main() == 2
    assert "[FATAL]" in capsys.readouterr().out


# ------------------------------------------------------------- 本地证据包（非关闭）


def test_local_evidence_package_must_exist(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, local_package={"path": "docs/evidence/l0-missing", "closing": False}))
    assert checker.main() == 1
    assert "本地证据包不存在" in capsys.readouterr().out


def test_local_evidence_package_cannot_claim_production(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, snapshots={"production": True}))
    assert checker.main() == 1
    assert "必须声明 production=false" in capsys.readouterr().out


def test_local_evidence_sample_relabeling_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, snapshots={"samples_production": True}))
    assert checker.main() == 1
    assert "不得改写标签" in capsys.readouterr().out


def test_local_evidence_artifact_drift_is_rejected(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    samples = root / "docs" / "evidence" / "l0-test" / "nexus-http-samples.json"
    samples.write_text(json.dumps({"production": False, "records": [1]}), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "与快照摘要不符" in capsys.readouterr().out


def test_local_evidence_artifact_missing_is_rejected(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    (root / "docs" / "evidence" / "l0-test" / "nexus-test-results.xml").unlink()
    point_at(checker, root)
    assert checker.main() == 1
    assert "快照登记但文件缺失" in capsys.readouterr().out


def test_local_evidence_must_be_marked_non_closing(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    checklist_path = root / "bindings" / "evidence" / "closure-checklist.json"
    doc = json.loads(checklist_path.read_text(encoding="utf-8"))
    doc["items"][0]["local_evidence"]["status"] = "closed"
    checklist_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "必须是 non_closing" in capsys.readouterr().out


def test_local_evidence_citation_must_exist_in_snapshot(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    checklist_path = root / "bindings" / "evidence" / "closure-checklist.json"
    doc = json.loads(checklist_path.read_text(encoding="utf-8"))
    doc["items"][0]["local_evidence"]["artifacts"] = ["not-registered.json"]
    checklist_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "引用了快照中不存在的 artifact" in capsys.readouterr().out


def test_real_package_local_evidence_is_wired(checker, capsys):
    checklist = json.loads((PACKAGE / "bindings" / "evidence" / "closure-checklist.json").read_text(encoding="utf-8"))
    package = checklist["local_evidence_package"]
    assert package["closing"] is False
    base = REPO_ROOT / package["path"]
    snapshot = json.loads((base / package["snapshot"]).read_text(encoding="utf-8"))
    registered = {a["path"] for a in snapshot["artifacts"]}
    cited = set()
    for item in checklist["items"]:
        local = item.get("local_evidence")
        assert local is not None, f"{item['id']} 未登记本地证据"
        assert local["status"] == "non_closing"
        cited |= set(local["artifacts"])
    assert cited <= registered, f"清单引用了快照外的 artifact：{sorted(cited - registered)}"
    assert snapshot["production"] is False


# ------------------------------------------------------- B9：拒绝事实必须来自样例


def refusal_item() -> dict:
    """一个只用拒绝样例判定的合成 T 项。"""
    item = synthetic_item()
    item["evidence"] = [
        {
            "id": "T1.refuse",
            "kind": "auth_evidence",
            "record_key": "r",
            "blocking": True,
            "required_fields": ["refusal_samples"],
            "checks": ["worker_refusal_evidenced"],
        }
    ]
    item["template"] = "templates/T1.json"
    return item


def refusal_record(status: int, code: str, *, case: str = "worker_publish_refused") -> dict:
    envelope = {
        "schema": "code_review.error.v1",
        "code": code,
        "retryable": False,
        "action_required": True,
        "scope": "policy",
        "correlation_id": "c-1",
        "safe_message": "denied",
        "retry_after_seconds": None,
    }
    payload = json.dumps(envelope).encode("utf-8")
    return {
        "status": "closed",
        "refusal_samples": [
            {
                "case": case,
                "subject": "worker:did:agentnexus:zWorker",
                "endpoint": "POST H/publications",
                "response_status": status,
                "content_type": "application/json; charset=utf-8",
                "raw_bytes_b64": b64(payload),
                "sha256": sha256_of(payload),
                "byte_length": len(payload),
                "expected_error_code": code,
            }
        ],
    }


def build_refusal_package(root: Path, record: dict | None):
    """构造只含一个拒绝检查项的合成包。"""
    root_path = build_package(root, t1_status="closed" if record else "open", t1_records=None)
    evidence = root_path / "bindings" / "evidence"
    doc = json.loads((evidence / "closure-checklist.json").read_text(encoding="utf-8"))
    doc["items"][0] = refusal_item()
    doc["items"][0]["status"] = "closed" if record else "open"
    (evidence / "closure-checklist.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (evidence / "templates" / "T1.json").write_text(json.dumps({"t_item": "T1", "records": {"r": {"status": "open"}}}), encoding="utf-8")
    if record is not None:
        (evidence / "received" / "T1.json").write_text(
            json.dumps({"t_item": "T1", "item_status": "closed", "item_status_reason": "synthetic", "records": {"r": record}}),
            encoding="utf-8",
        )
    return root_path


def test_refusal_sample_accepts_real_403(checker, tmp_path, capsys):
    point_at(checker, build_refusal_package(tmp_path, refusal_record(403, "authority_denied")))
    assert checker.main() == 0, capsys.readouterr().out
    assert "T1 [closed]" in capsys.readouterr().out


def test_boolean_without_refusal_sample_is_rejected(checker, tmp_path, capsys):
    """评审 B9 反例：只写布尔 true、没有拒绝样例，必须失败。"""
    record = {"status": "closed", "worker_refusal_evidenced": True}
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    assert "缺 refusal_samples" in capsys.readouterr().out


def test_refusal_sample_with_200_is_rejected(checker, tmp_path, capsys):
    """评审 B9 反例：名字叫 rejected 但实际 200，必须失败。"""
    point_at(checker, build_refusal_package(tmp_path, refusal_record(200, "authority_denied")))
    assert checker.main() == 1
    assert "必须是 401/403" in capsys.readouterr().out


def test_refusal_sample_with_wrong_code_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_refusal_package(tmp_path, refusal_record(403, "invalid_output")))
    assert checker.main() == 1
    assert "错误码应为" in capsys.readouterr().out


def test_refusal_sample_unknown_code_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_refusal_package(tmp_path, refusal_record(403, "made_up_code")))
    assert checker.main() == 1
    assert "不在冻结 error.schema.json 枚举内" in capsys.readouterr().out


def test_refusal_sample_missing_subject_is_rejected(checker, tmp_path, capsys):
    record = refusal_record(403, "authority_denied")
    record["refusal_samples"][0].pop("subject")
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    assert "必须记录被拒主体" in capsys.readouterr().out


def test_refusal_sample_not_error_envelope_is_rejected(checker, tmp_path, capsys):
    record = refusal_record(403, "authority_denied")
    payload = json.dumps({"error": "nope"}).encode("utf-8")
    sample = record["refusal_samples"][0]
    sample["raw_bytes_b64"] = b64(payload)
    sample["sha256"] = sha256_of(payload)
    sample["byte_length"] = len(payload)
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    assert "不是冻结错误信封" in capsys.readouterr().out


# ── R2-6：拒绝证据必须按冻结 schema 与具体场景验证 ────────────────────


def test_r26_legal_403_from_unrelated_scenario_is_rejected(checker, tmp_path, capsys):
    """复审 R2-6 复现：无关的 403（subject=unrelated-admin、endpoint=/unrelated/health）曾通过。"""
    record = refusal_record(403, "authority_denied")
    sample = record["refusal_samples"][0]
    sample["subject"] = "unrelated-admin"
    sample["endpoint"] = "GET /unrelated/health"
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    out = capsys.readouterr().out
    assert "主体与拒绝场景不符" in out
    assert "端点与拒绝场景不符" in out


def test_r26_schema_invalid_error_body_is_rejected(checker, tmp_path, capsys):
    """复审 R2-6 复现：所有键都在但类型/const 不合法（retryable='yes'、scope=123、
    retry_after_seconds=-99、schema=not-an-error-schema）曾被判通过。"""
    record = refusal_record(403, "authority_denied")
    payload = json.dumps(
        {
            "schema": "not-an-error-schema",
            "code": "authority_denied",
            "retryable": "yes",
            "action_required": None,
            "scope": 123,
            "correlation_id": "c-1",
            "safe_message": "denied",
            "retry_after_seconds": -99,
        }
    ).encode("utf-8")
    sample = record["refusal_samples"][0]
    sample["raw_bytes_b64"] = b64(payload)
    sample["sha256"] = sha256_of(payload)
    sample["byte_length"] = len(payload)
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    assert "未通过冻结 error.schema.json" in capsys.readouterr().out


def test_r26_error_code_must_match_the_scenario(checker, tmp_path, capsys):
    """场景允许码之外的合法错误码同样不通过（如发布被拒不应报 input_mismatch）。"""
    record = refusal_record(403, "input_mismatch")
    point_at(checker, build_refusal_package(tmp_path, record))
    assert checker.main() == 1
    assert "该场景的错误码应为" in capsys.readouterr().out


def test_r26_unregistered_refusal_case_is_rejected(checker, tmp_path, capsys):
    """未登记场景期望的拒绝用例无法验证，必须失败而不是放行。"""
    failures: list = []
    sample = refusal_record(403, "authority_denied")["refusal_samples"][0]
    ok = checker.verify_refusal_sample(sample, "made_up_refusal_case", "T1.x", failures)
    assert ok is False
    assert any("未登记场景期望" in f for f in failures)


def test_unconfigured_text_cannot_satisfy_refusal_check(checker, tmp_path, capsys):
    """评审 B9 反例：文本写 "does not reject; allows requests" 不能再通过。"""
    item = {
        "id": "T1",
        "title": "synthetic",
        "owner": "Nexus_Agent",
        "status": "open",
        "status_reason": "synthetic",
        "template": "templates/T1.json",
        "evidence": [
            {
                "id": "T1.unconfigured",
                "kind": "auth_evidence",
                "record_key": "r",
                "blocking": True,
                "required_fields": ["unconfigured_behavior"],
                "checks": ["must_refuse_when_unconfigured"],
            }
        ],
    }
    root = build_package(tmp_path)
    evidence = root / "bindings" / "evidence"
    doc = json.loads((evidence / "closure-checklist.json").read_text(encoding="utf-8"))
    doc["items"][0] = item
    (evidence / "closure-checklist.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    record = {"status": "closed", "unconfigured_behavior": "does not reject; allows requests"}
    (evidence / "received" / "T1.json").write_text(
        json.dumps({"t_item": "T1", "item_status": "open", "item_status_reason": "synthetic", "records": {"r": record}}),
        encoding="utf-8",
    )
    point_at(checker, root)
    assert checker.main() == 1
    assert "缺 refusal_samples" in capsys.readouterr().out


# ------------------------------------------- B10 / S3：可移植性与采集 pin 不可改写


def test_package_without_host_markers_skips_host_audit(checker, tmp_path, capsys):
    """评审 B10：包被复制到别处后必须能独立通过自检。"""
    point_at(checker, build_package(tmp_path, snapshots={"host_markers": False}))
    assert checker.main() == 0
    out = capsys.readouterr().out
    assert "[SKIP] 宿主证据审计" in out
    assert "0/6 已关闭" in out


def test_require_host_audit_flag_turns_skip_into_failure(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, snapshots={"host_markers": False}))
    assert checker.main(["--require-host-audit"]) == 1
    assert "要求宿主审计但缺少宿主标记" in capsys.readouterr().out


def test_unknown_cli_flag_is_fatal(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path))
    assert checker.main(["--nope"]) == 2
    assert "未知参数" in capsys.readouterr().out


def test_real_package_copied_anywhere_still_passes(checker, tmp_path, capsys):
    """评审 B10 的验收：把**真实**规范包复制到任意目录，自检必须通过。

    复制体没有宿主的 docs/evidence 目录，也没有宿主标记，因此宿主审计应被跳过；
    包内收到的关闭证据仍然逐条严格校验。
    """
    import shutil

    copied = tmp_path / "vendored" / "code-review-v1"
    shutil.copytree(PACKAGE, copied)
    # 复制体不含宿主证据，也不含宿主标记
    assert not (copied / "docs").exists()
    assert not (tmp_path / "AGENTS.md").exists()

    point_at_package(checker, copied, tmp_path)
    assert checker.main() == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "[SKIP] 宿主证据审计" in out
    assert "0/6 已关闭" in out

    # 收紧后必须失败：要求宿主审计却没有宿主标记
    assert checker.main(["--require-host-audit"]) == 1


def test_missing_host_evidence_with_markers_present_is_rejected(checker, tmp_path, capsys):
    """宿主标记齐备却缺证据目录 = 中央仓库里证据被删，必须失败而非跳过。"""
    point_at(checker, build_package(tmp_path, local_package={"path": "docs/evidence/l0-missing", "closing": False, "host_markers": ["AGENTS.md"]}))
    assert checker.main() == 1
    assert "本地证据包不存在" in capsys.readouterr().out


def test_rewritten_capture_pin_is_rejected(checker, tmp_path, capsys):
    """评审 S3：包已升级却把 pin 改成当前摘要（我此前犯的错）必须失败。"""
    root = build_package(tmp_path)
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["capture_package_version"] = "1.0-draft.2+semantic.9"  # 与当前 synthetic 版本不同
    snapshot["profile_manifest_sha256"] = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "采集 pin 被改写为当前包摘要" in capsys.readouterr().out


def test_same_version_pin_must_match_current(checker, tmp_path, capsys):
    """同版本下 pin 必须等于当前摘要，否则快照与包已不一致。"""
    point_at(checker, build_package(tmp_path, snapshots={"manifest_sha": "c" * 64}))
    assert checker.main() == 1
    assert "同版本下 pin 必须等于当前摘要" in capsys.readouterr().out


def test_snapshot_must_record_capture_package_version(checker, tmp_path, capsys):
    root = build_package(tmp_path)
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot.pop("capture_package_version")
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "必须记录 capture_package_version" in capsys.readouterr().out


def test_drifted_pin_with_valid_recheck_is_accepted(checker, tmp_path, capsys):
    """评审 S3：保留原 pin + 另记复核记录 → 通过。"""
    root = build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"})
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["profile_manifest_rechecks"] = [good_recheck(root)]
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 0, capsys.readouterr().out


def test_drifted_pin_without_recheck_is_rejected(checker, tmp_path, capsys):
    point_at(checker, build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"}))
    assert checker.main() == 1
    assert "缺 profile_manifest_rechecks 复核记录" in capsys.readouterr().out


def test_recheck_before_capture_time_is_rejected(checker, tmp_path, capsys):
    root = build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"})
    recheck = good_recheck(root)
    recheck["checked_at"] = "2026-07-01T00:00:00Z"  # captured_at 是 2026-08-01
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["profile_manifest_rechecks"] = [recheck]
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "复核时间必须晚于采集时间" in capsys.readouterr().out


def test_recheck_claiming_reexecution_needs_artifacts(checker, tmp_path, capsys):
    root = build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"})
    recheck = good_recheck(root)
    recheck["reexecuted"] = True
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["profile_manifest_rechecks"] = [recheck]
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "reexecuted_artifacts" in capsys.readouterr().out


def test_recheck_must_point_at_current_package(checker, tmp_path, capsys):
    root = build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"})
    recheck = good_recheck(root)
    recheck["checked_against_sha256"] = "b" * 64
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["profile_manifest_rechecks"] = [recheck]
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 1
    assert "没有一条复核记录指向当前包摘要" in capsys.readouterr().out


def test_historical_recheck_may_point_at_older_digest(checker, tmp_path, capsys):
    """复核记录是时点证据：历史条目可指向当时的摘要，但仍须有一次针对当前包。"""
    root = build_package(tmp_path, snapshots={"manifest_sha": "a" * 64, "capture_version": "1.0-draft.2+semantic.9"})
    older = good_recheck(root)
    older["checked_against_sha256"] = "c" * 64
    older["checked_at"] = "2026-08-02T00:00:00Z"
    newer = good_recheck(root)
    newer["checked_at"] = "2026-08-03T00:00:00Z"
    snapshot_path = root / "docs" / "evidence" / "l0-test" / "source-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["profile_manifest_rechecks"] = [older, newer]
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    point_at(checker, root)
    assert checker.main() == 0, capsys.readouterr().out
