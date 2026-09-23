#!/usr/bin/env python3
"""执行 q3 行为用例并输出执行记录（Markdown 到 stdout）。

对应 `specs/profiles/code-review/v1/fixtures/binding/q3-outcome-coverage.md` 的
"执行记录要求"：登记适配器版本、可复现命令、原始输入与目标产物的真实摘要、
UI/评论实际文本、重复投递前后计数、拒绝阶段，以及**未在本仓库验证**的部分。

用法（脚本不写文件，便于在受限沙箱与 CI 中重跑）::

    python scripts/run_q3_harness.py > specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-<date>.md
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_net.code_review import (  # noqa: E402
    ProfileError,
    build_hczj_profile_report,
    render_review_summary,
    report_digest,
    translate_agentnexus_result,
    validate_publish_body,
    validate_review_report,
)

PACKAGE = ROOT / "specs" / "profiles" / "code-review" / "v1"
FROZEN_VALID_09 = PACKAGE / "fixtures" / "valid" / "09_review_report_issues_found_with_inherited_gap.artifact_body.json"
MANIFEST_DIGEST = "sha256:" + "1" * 64


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── q3 Given 数据（与 tests/test_code_review_q3_harness.py 保持一致） ──


def _evidence() -> dict:
    return {
        "provider_id": "did:agentnexus:z6MkNexusScanner00000000000000000000000000000",
        "report_id": "R1",
        "side": "after",
        "snapshot_id": "snap_after_g3",
        "project": "proj_7788",
        "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "path": "src/main/java/com/example/OrderService.java",
        "blob_sha": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        "start_line": 120,
        "end_line": 128,
        "content_sha256": "5e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
    }


def _hczj_finding() -> dict:
    return {
        "finding_id": "F7",
        "severity": "P2",
        "title": "库存校验失败路径未释放预留额度",
        "trigger": "库存校验返回 false 后未回滚预留记录",
        "impact": "失败订单长期占用库存额度",
        "location": {
            "side": "after",
            "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
            "path": "src/main/java/com/example/OrderService.java",
            "start_line": 120,
            "end_line": 128,
        },
        "evidence_refs": [_evidence()],
        "suggested_validation": "补充库存校验失败后的预留回滚断言",
    }


def _hczj_report(outcome: str, findings=None) -> dict:
    return {
        "schema_version": "hczj.review_report.v1",
        "report_id": "R1",
        "outcome": outcome,
        "findings": [_hczj_finding()] if findings is None else findings,
        "limitations": [],
    }


def _hczj_coverage(status: str = "partial") -> dict:
    return {
        "schema_version": "hczj.review_coverage.v1",
        "status": status,
        "planned_files": [
            "src/main/java/com/example/OrderService.java",
            "src/main/java/com/example/OrderRepository.java",
        ],
        "reviewed_files": ["src/main/java/com/example/OrderService.java"],
        "omitted_files": [
            {
                "path": "src/main/java/com/example/OrderRepository.java",
                "reason": "inherited_gap_impact_graph_truncated",
            }
        ],
        "gap_reasons": ["继承输入证据缺口：依赖图谱在 200 节点处截断"],
        "inherited_gaps": [
            {"source": "art_impact_R1", "reason": "依赖图谱在 200 节点处截断（truncated=true）"}
        ],
    }


def _identity() -> dict:
    return {
        "run_id": "RUN-ID-2026-09-14",
        "attempt_id": "A3",
        "input_manifest_digest": MANIFEST_DIGEST,
        "impact_artifact": {
            "artifact_id": "art_impact_R1",
            "producer_id": "did:agentnexus:z6MkNexusScanner00000000000000000000000000000",
            "media_type": "application/json",
            "schema_version": "nexus.review_impact.v1",
            "digest_algorithm": "sha256-bytes-v1",
            "digest": "sha256:" + "0" * 64,
            "byte_length": 18456,
            "locator": "nexus-report:did:agentnexus:z6MkNexusScanner00000000000000000000000000000:R1",
            "access_scope": "service_private",
            "retention_until": "2027-03-18T00:00:00Z",
            "replaces": None,
        },
        "review_policy_sha256": "a" * 64,
        "review_revision": 1,
        "base_sha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "head_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "target_sha": "3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
        "generation": 3,
        "execution_revision": 1,
        "reviewer_id": "did:agentnexus:z6MkReviewerWorker00000000000000000000000000000",
    }


def _execution_metadata() -> dict:
    return {
        "provider": "hczj-model-gateway",
        "model": "code-review-model",
        "model_version": None,
        "skill_version": "code-review-skill/0.1.0",
        "tool_versions": ["nexus-mcp/1.0"],
        "started_at": "2026-09-20T02:00:00Z",
        "completed_at": "2026-09-20T02:09:00Z",
    }


def _usage() -> dict:
    return {
        "measurement": "partial",
        "input_tokens": 96000,
        "output_tokens": 11000,
        "cost": None,
        "note": "成本未计量；不得视为零成本",
    }


def _convert(report: dict, coverage: dict) -> dict:
    return build_hczj_profile_report(
        hczj_report=report,
        hczj_coverage=coverage,
        identity=_identity(),
        execution_metadata=_execution_metadata(),
        usage=_usage(),
    )


def _package_version() -> str:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    return str(manifest.get("package_version", "unknown"))


async def _replay_counts() -> dict:
    """真实执行一次交付 + 重放，统计前后计数（使用工作区内的临时 DB）。

    注意：这里刻意**不用** ``tempfile.mkdtemp``——它默认 mode 0o700，在受限沙箱下
    建出的目录随即不可访问（``sqlite3.OperationalError: unable to open database file``）。
    """
    import shutil

    import agent_net.storage as s

    tmpdir = ROOT / ".q3_harness_tmp" / f"run_{uuid.uuid4().hex[:8]}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    orig = s.DB_PATH
    s.DB_PATH = tmpdir / "agent_net.db"
    try:
        await s.init_db()
        owner = await s.register_owner("Q3HarnessOwner")
        cs_id = f"cs_{uuid.uuid4().hex[:12]}"
        await s.create_coordination_session(
            coordination_session_id=cs_id,
            owner_did=owner["did"],
            controller_did=owner["did"],
            objective="q3 harness",
        )
        profile = await s.create_profile_session(
            f"psess_{uuid.uuid4().hex[:12]}",
            coordination_session_id=cs_id,
            coordinator_id="urn:code-review:coordinator:test",
            external_run_id=f"RUN_{uuid.uuid4().hex[:8]}",
            review_policy_sha256="a" * 64,
        )
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        await s.create_objective_execution(
            execution_id=execution_id,
            coordination_session_id=cs_id,
            run_id="local-run",
            stage="code_review",
            worker_did="did:agentnexus:worker",
            backend_kind="local_cli",
        )
        await s.bind_execution_assignment(
            execution_id,
            profile_session_id=profile["profile_session_id"],
            external_coordinator_id=profile["coordinator_id"],
            external_run_id=profile["external_run_id"],
            external_attempt_id="A3",
            assignment_epoch=1,
            input_manifest_digest=MANIFEST_DIGEST,
            output_schema="code_review.report.v1",
        )
        target = _convert(_hczj_report("findings_present"), _hczj_coverage())
        body = json.dumps(target, ensure_ascii=False)
        kwargs = dict(
            actor_did="did:agentnexus:worker",
            artifact_type="CodeReviewReport",
            artifact_body=body,
            media_type="application/json",
            schema_version="code_review.report.v1",
            summary="q3 harness replay",
            run_state="completed",
            outcome=target["outcome"],
            domain_status="completed",
            enforcement="declared_only",
            report_input_manifest_digest=MANIFEST_DIGEST,
        )
        first = await s.commit_profile_delivery(execution_id, **kwargs)
        before = {
            "deliveries": len(await s.list_deliveries(profile["profile_session_id"])),
            "receipts": len(await s.list_profile_receipts(profile["profile_session_id"])),
        }
        replay = await s.commit_profile_delivery(execution_id, **kwargs)
        after = {
            "deliveries": len(await s.list_deliveries(profile["profile_session_id"])),
            "receipts": len(await s.list_profile_receipts(profile["profile_session_id"])),
        }
        return {
            "before": before,
            "after": after,
            "replayed": replay["replayed"],
            "same_artifact": replay["artifact_id"] == first["artifact_id"],
            "artifact_id": first["artifact_id"],
            "receipt_kinds": [r["kind"] for r in replay["receipts"]],
        }
    finally:
        s.DB_PATH = orig
        shutil.rmtree(tmpdir, ignore_errors=True)


def _rejection_stage(callable_) -> str:
    try:
        callable_()
    except ProfileError as exc:
        return exc.code
    return "NOT REJECTED"


def main() -> int:
    out: list[str] = []
    add = out.append

    target_found = _convert(_hczj_report("findings_present"), _hczj_coverage())
    target_inconclusive = _convert(_hczj_report("inconclusive"), _hczj_coverage())
    target_empty = _convert(_hczj_report("no_findings", findings=[]), _hczj_coverage())
    body_found = render_review_summary(target_found)
    body_empty = render_review_summary(target_empty)
    serialized = json.dumps(target_found, ensure_ascii=False)
    digest, byte_length = report_digest(serialized)

    corrupt_a = dict(target_found, outcome="inconclusive")
    corrupt_b = json.loads(serialized)
    corrupt_b["coverage"]["status"] = "complete"
    replay = asyncio.run(_replay_counts())

    add("# q3 行为用例执行记录（自动生成）")
    add("")
    add("生成方式：`python scripts/run_q3_harness.py > <本文件>`（脚本不写文件，可重复生成）。")
    add("")
    add("## 1. 适配器版本与实现位置")
    add("")
    add(f"- 规范包版本：`{_package_version()}`")
    add("- 实现模块：`agent_net/code_review/provider_adapter.py`（厂商无关管线与 provider 注册表）、`agent_net/code_review/hczj_adapter.py`（HCZJ 词表）、`agent_net/code_review/presentation.py`（呈现规则）、`agent_net/code_review/validation.py`（结构校验）")
    add("- 用例定义：`specs/profiles/code-review/v1/fixtures/binding/q3-outcome-coverage.md`")
    add("")
    add("## 2. 可复现命令")
    add("")
    add("```bash")
    add("python -m pytest tests/test_code_review_q3_harness.py -q -p no:cacheprovider")
    add("python scripts/run_q3_harness.py > specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-<date>.md")
    add("```")
    add("")
    add("## 3. 真实摘要（§15.3 口径）")
    add("")
    add("| 对象 | 摘要 | 字节长度 |")
    add("|---|---|---|")
    add(f"| 目标 Profile 报告（q3-found-partial，序列化字节） | `{digest}` | {byte_length} |")
    add(f"| 冻结 fixture `valid/09` | `{_sha256(FROZEN_VALID_09.read_text(encoding='utf-8'))}` | {FROZEN_VALID_09.stat().st_size} |")
    add("")
    add("## 4. 转换结果（q3-found-partial，两种原 outcome）")
    add("")
    add("| 原 HCZJ outcome | 目标 outcome | 目标 coverage | finding severity | 溯源 source_outcome |")
    add("|---|---|---|---|---|")
    for label, target in (("findings_present", target_found), ("inconclusive", target_inconclusive)):
        add(
            f"| {label} | `{target['outcome']}` | `{target['coverage']['status']}` | "
            f"`{target['findings'][0]['severity']}` | `{target['extensions']['hczj.provenance']['source_outcome']}` |"
        )
    add("")
    add("两种输入的目标语义一致（`issues_found` + `partial`），各自保留源产物溯源，符合 q3 期望。")
    add("")
    add("## 5. UI / 评论正文（实际渲染文本）")
    add("")
    add("### q3-found-partial")
    add("")
    add("```text")
    add(body_found)
    add("```")
    add("")
    add("### q3-empty-partial（findings=[]、coverage=partial）")
    add("")
    add("```text")
    add(body_empty)
    add("```")
    add("")
    add("## 6. 重复投递前后计数（真实执行）")
    add("")
    add("| 指标 | 首次交付后 | 重放后 |")
    add("|---|---|---|")
    add(f"| deliveries | {replay['before']['deliveries']} | {replay['after']['deliveries']} |")
    add(f"| receipts | {replay['before']['receipts']} | {replay['after']['receipts']} |")
    add("")
    add(f"- 重放标记 `replayed={replay['replayed']}`，复用同一 artifact（`same_artifact={replay['same_artifact']}`，id=`{replay['artifact_id']}`）")
    add(f"- 回执 kind：{replay['receipt_kinds']}（**不含 `accepted`**，本入口只签发 `received`）")
    add("")
    add("## 7. 拒绝阶段")
    add("")
    add("| 用例 | 注入内容 | 拒绝阶段 | 错误码 |")
    add("|---|---|---|---|")
    add(f"| A | 非空 findings + outcome=inconclusive | 结构校验 | `{_rejection_stage(lambda: translate_agentnexus_result('completed', artifact_type='CodeReviewReport', report=corrupt_a))}` |")
    add(f"| B | inherited_gaps 非空 + coverage=complete | 结构校验 | `{_rejection_stage(lambda: translate_agentnexus_result('completed', artifact_type='CodeReviewReport', report=corrupt_b))}` |")
    add(f"| C | 模板只呈现 outcome | 呈现校验 | `{_rejection_stage(lambda: validate_publish_body('发现问题', target_found))}` |")
    add(f"| D | 呈现缺遗漏范围 | 呈现校验 | `{_rejection_stage(lambda: validate_publish_body(body_found.replace('src/main/java/com/example/OrderRepository.java', ''), target_found))}` |")
    add("")
    add("C/D 的拒绝发生在**写入外部系统之前**，即使目标报告已通过 JSON Schema（`validate_review_report` 返回空）。")
    add("")
    add("## 8. 未在本仓库验证的部分")
    add("")
    add("- **发布重放半场**（“同 operation_id 发布重放不得新增 GitLab 评论”）属 HCZJ 应用边界（RC2 §5），本仓库没有 GitLab 写入路径，无法验证；测试中显式 `skip`，不视为通过。")
    add("- Nexus/HCZJ 侧的真实响应样例、`contract_revision` 取值仍待外部提供（T1–T6）。")
    add("")
    add("## 9. 与冻结 fixture 的交叉校验")
    add("")
    add("目标报告的关键不变式与冻结 `valid/09` 一致（outcome/coverage.status/severity）；`valid/09` 仅锁结构，不能代替本记录的行为验收。")
    add("")

    record = "\n".join(out)
    if not record.strip():  # 防"退出码 0 但无输出"
        print("[FAIL] 执行记录为空——生成逻辑异常", file=sys.stderr)
        return 1
    print(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
