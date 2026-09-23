#!/usr/bin/env python3
"""执行 CP-01～26 一致性用例并生成运行记录（路线图第 4 步）。

为什么需要它
------------
``fixtures/cp-matrix.json`` 只声明「有哪些一致性用例」，``tools/validate.py`` 只检查
「引用是否存在」。两者都不执行行为语义，于是"CP-01～26 已执行"很容易变成一句无人复算的
结论。本脚本把 26 个用例逐个落到**可执行证据**上：

* ``kind=structural`` 的用例 → 用冻结 schema 复核 fixture（valid 必须过、invalid 必须不过）；
* ``kind=digest`` 的用例 → 直接复算 ``fixtures/digest_vectors.json``；
* ``kind=behavioral`` 的用例 → 运行 ``bindings/l0-agentnexus-cp-coverage.json`` 里映射的
  AgentNexus 行为测试，按 node id 逐个记录通过/失败。

覆盖映射只描述 **AgentNexus 侧**能提供什么证据。裁定权在 HCZJ / Nexus 的用例标为
``blocked``（附 owner 与限制说明），只覆盖一半的标为 ``partial``；脚本**不会**把二者渲染成通过。

用法
----
::

    # 1) 生成行为测试清单并跑它（受限环境用两步；-rA 用于逐条结果）
    python scripts/run_cp_matrix.py --list-tests
    $env:PYTHONIOENCODING='utf-8'
    python -m pytest <上面输出的 node id...> -q -p no:cacheprovider --tb=no -rA > .pytest_cp_report.txt 2>&1

    # 2) 生成运行记录
    python scripts/run_cp_matrix.py --input .pytest_cp_report.txt --out <记录路径>

    # 3) 允许创建子进程的环境可一步到位
    python scripts/run_cp_matrix.py --run

退出码
------
- ``0`` 声明的证据全部执行通过（blocked/partial 如实标注，不算失败）；
- ``1`` 有声明为 verified 的证据执行失败（真实回归）；
- ``2`` 输入不可用：CP 集合不一致、映射腐烂、报告解析不到结果；
- ``3`` 报告编码受损（含 U+FFFD），无法逐条判定。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "specs" / "profiles" / "code-review" / "v1"
MATRIX = BASE / "fixtures" / "cp-matrix.json"
COVERAGE = BASE / "bindings" / "l0-agentnexus-cp-coverage.json"
INDEX = BASE / "fixtures" / "index.json"
MANIFEST = BASE / "manifest.json"
DEFAULT_OUT = BASE / "fixtures" / "binding" / "cp-execution-record-{date}.md"

VALID_STATUS = ("verified", "partial", "blocked")


def _load(path: Path):
    return json.loads(path.read_bytes().decode("utf-8"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode_report(raw: bytes) -> str:
    """与 scripts/check_full_suite.py 同口径：报告可能落在 locale 编码（中文 Windows=GBK）。"""
    for encoding in ("utf-8", "utf-16"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    for encoding in ("cp936", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StructuralResult:
    def __init__(self) -> None:
        self.ok: List[str] = []
        self.failed: List[str] = []
        self.spec_doc: List[str] = []

    def as_dict(self) -> dict:
        return {"ok": self.ok, "failed": self.failed, "spec_doc": self.spec_doc}


def check_structural(validate_mod, case: dict) -> StructuralResult:
    """按 cp-matrix 的 fixtures 引用做机器判定（schema / valid / invalid / 文档锚点）。"""
    registry, ids = validate_mod.build_registry()
    index = _load(INDEX)
    valid_map = {item["file"]: item["schema"] for item in index["valid"]}
    invalid_map = {item["file"]: item for item in index["invalid"]}
    result = StructuralResult()

    for ref in case.get("fixtures", []):
        path = validate_mod.resolve_ref(ref)
        if not path.exists():
            result.failed.append(f"{ref}: 引用文件不存在")
            continue
        if ref.split("#", 1)[0].endswith(".md"):
            result.spec_doc.append(ref)
            continue
        if path.name.endswith(".schema.json"):
            try:
                schema = _load(path)
            except Exception as exc:  # noqa: BLE001 - 报告原始原因即可
                result.failed.append(f"{ref}: schema 无法解析（{exc}）")
                continue
            sid = schema.get("$id")
            if not sid or sid not in ids:
                result.failed.append(f"{ref}: schema 未在 registry 中登记（$id={sid}）")
            else:
                result.ok.append(f"{ref}: schema 已登记（$id={sid}）")
            continue

        rel = path.relative_to(BASE / "fixtures").as_posix()
        try:
            doc = _load(path)
        except Exception as exc:  # noqa: BLE001
            result.failed.append(f"{ref}: 无法解析（{exc}）")
            continue
        if rel in valid_map:
            validator = validate_mod.validator_for(valid_map[rel], registry)
            errors = list(validator.iter_errors(doc))
            if errors:
                result.failed.append(f"{ref}: valid fixture 被 schema 拒绝（{errors[0].message[:120]}）")
            else:
                result.ok.append(f"{ref}: valid fixture 通过 {valid_map[rel]}")
        elif rel in invalid_map:
            validator = validate_mod.validator_for(invalid_map[rel]["schema"], registry)
            if list(validator.iter_errors(doc)):
                result.ok.append(f"{ref}: invalid fixture 按预期被拒绝")
            else:
                result.failed.append(f"{ref}: invalid fixture 竟然通过校验（schema 漏了 MUST）")
        else:
            # 例如 fixtures/digest_vectors.json：由 digest 步骤负责语义，这里只确认存在。
            result.ok.append(f"{ref}: 文件存在（语义由本脚本相应步骤判定）")
    return result


def check_digest(validate_mod) -> StructuralResult:
    failures: List[str] = []
    checked = validate_mod.check_digest_vectors(failures)
    result = StructuralResult()
    if failures:
        result.failed.extend(failures)
    else:
        result.ok.append(f"digest_vectors: {checked} 个向量复算一致（含禁止重序列化反例）")
    return result


def parse_test_report(text: str) -> Dict[str, str]:
    """解析 ``-rA`` 的逐条结果行，返回 {node_id: PASSED/FAILED/ERROR/SKIPPED}。

    参数化用例在报告里是 ``node[param]``，因此这里的 key 可能是带参数的完整 id；
    归并到映射里的裸 node id 由 :func:`verdict_for` 负责。
    """
    outcomes: Dict[str, str] = {}
    for verdict, node in re.findall(r"^(PASSED|FAILED|ERROR|SKIPPED) (\S+)", text, re.M):
        outcomes.setdefault(node, verdict)
    return outcomes


#: 没有证据（没跑到）与坏结果都必须算作"该用例未通过"。
BAD_VERDICTS = ("FAILED", "ERROR")
MISSING_VERDICTS = ("NOT_RUN", "SKIPPED")


def verdict_for(node: str, outcomes: Dict[str, str]) -> str:
    """把映射里的 node id 归并成一个判定：参数化展开的全部实例取最坏结果。"""
    if node in outcomes:
        return outcomes[node]
    matched = [verdict for key, verdict in outcomes.items() if key.startswith(node + "[")]
    if not matched:
        return "NOT_RUN"
    for worst in BAD_VERDICTS + MISSING_VERDICTS:
        if worst in matched:
            return worst
    return "PASSED"


def collect_tests(coverage: dict) -> List[str]:
    tests: List[str] = []
    for case in coverage["cases"]:
        for node in case.get("tests", []):
            if node not in tests:
                tests.append(node)
    return tests


def validate_mapping(matrix: dict, coverage: dict) -> List[str]:
    """CP 集合一致性 + 映射不被腐烂 + 状态字段完整。"""
    problems: List[str] = []
    matrix_ids = [case["id"] for case in matrix["cases"]]
    cov_ids = [case["id"] for case in coverage["cases"]]
    if matrix_ids != cov_ids:
        missing = sorted(set(matrix_ids) - set(cov_ids))
        extra = sorted(set(cov_ids) - set(matrix_ids))
        problems.append(f"CP 集合与 cp-matrix 不一致：缺失 {missing}，多出 {extra}")
    if len(set(cov_ids)) != len(cov_ids):
        problems.append("覆盖映射中 CP id 重复")
    for case in coverage["cases"]:
        status = case.get("status")
        if status not in VALID_STATUS:
            problems.append(f"{case['id']}: 非法 status {status!r}")
            continue
        if status == "blocked":
            if not case.get("owner"):
                problems.append(f"{case['id']}: blocked 必须给出 owner")
            if not case.get("limitation"):
                problems.append(f"{case['id']}: blocked 必须给出 limitation")
        if status == "partial" and not case.get("limitation"):
            problems.append(f"{case['id']}: partial 必须给出 limitation")
        if status == "verified" and not case.get("tests"):
            problems.append(f"{case['id']}: verified 但没有任何映射测试")
        for node in case.get("tests", []):
            path, _, name = node.partition("::")
            target = ROOT / path
            if not target.exists():
                problems.append(f"{case['id']}: 测试文件不存在 {path}")
                continue
            if f"def {name}(" not in target.read_text(encoding="utf-8"):
                problems.append(f"{case['id']}: 测试函数不存在 {node}")
    return problems


def build_record(matrix: dict, coverage: dict, results: dict, mode: str, command: str, date: str) -> str:
    cov = {case["id"]: case for case in coverage["cases"]}
    structural: Dict[str, StructuralResult] = results["structural"]
    outcomes: Dict[str, str] = results["outcomes"]

    counts = {"verified": 0, "partial": 0, "blocked": 0, "failed": 0}
    lines: List[str] = []
    lines.append(f"# CP-01～26 执行记录（AgentNexus 侧，{date}）\n")
    lines.append(
        "本记录由 `scripts/run_cp_matrix.py` 生成，可重跑。**不声明符合性、不声明 wire conformance**："
        "`verified` 只表示本仓声明的证据在同一次运行中执行通过；裁定权在 HCZJ / Nexus 的用例标为"
        "`blocked`，只覆盖一半的标为 `partial`，二者都不构成该 CP 已通过。\n"
    )
    manifest = _load(MANIFEST) if MANIFEST.exists() else {}
    lines.append("## 运行输入\n")
    lines.append(f"- 规范包版本：`{manifest.get('package_version', 'unknown')}`")
    lines.append(
        "- manifest 摘要：**故意不内嵌**——本记录本身由 manifest 登记，内嵌会对「记录被登记」形成循环；"
        "方向是 manifest 固定本记录的摘要（见 `manifest.json` 中本文件条目），版本变化后须重新生成本记录。"
    )
    lines.append(f"- CP 定义：`fixtures/cp-matrix.json`（sha256 `{_sha256(MATRIX)}`）")
    lines.append(f"- 覆盖映射：`bindings/l0-agentnexus-cp-coverage.json`（sha256 `{_sha256(COVERAGE)}`）")
    lines.append(f"- 行为测试获取方式：{'--run（脚本内调用 pytest）' if mode == 'run' else '--input（外部报告）'}")
    lines.append(f"- 命令：`{command}`")
    lines.append(
        "- 环境：受限沙箱（禁止创建子进程的环境跳过相关文件）；行为测试使用合成存储、"
        "进程内 ASGI/Flask 客户端与临时数据库，不访问生产服务、不执行真实 GitLab 写入。\n"
    )

    lines.append("## 逐用例结果\n")
    lines.append("| CP | 阶段 | 类型 | 声明状态 | 结构/摘要判定 | 行为证据 | 结果 |")
    lines.append("|---|---|---|---|---|---|---|")
    for case in matrix["cases"]:
        cp = case["id"]
        declared = cov[cp]["status"]
        struct = structural.get(cp, StructuralResult())
        struct_txt = "—"
        if struct.ok or struct.failed or struct.spec_doc:
            parts = []
            if struct.ok:
                parts.append(f"ok {len(struct.ok)}")
            if struct.failed:
                parts.append(f"**failed {len(struct.failed)}**")
            if struct.spec_doc:
                parts.append(f"spec-doc {len(struct.spec_doc)}（非机器判定）")
            struct_txt = "；".join(parts)
        nodes = cov[cp].get("tests", [])
        if nodes:
            verdicts = [verdict_for(node, outcomes) for node in nodes]
            beh_txt = f"{sum(1 for v in verdicts if v == 'PASSED')}/{len(nodes)} passed"
            if any(v in BAD_VERDICTS for v in verdicts):
                beh_txt = f"**{beh_txt}**"
            elif any(v in MISSING_VERDICTS for v in verdicts):
                beh_txt = f"{beh_txt}（未全部执行）"
        else:
            beh_txt = "—"
        failed_here = bool(struct.failed) or any(
            verdict_for(node, outcomes) in BAD_VERDICTS + MISSING_VERDICTS for node in nodes
        )
        if failed_here:
            counts["failed"] += 1
            outcome = "**证据失败/缺失**"
        else:
            counts[declared] += 1
            outcome = {"verified": "AgentNexus 侧通过", "partial": "部分通过", "blocked": "无本仓证据"}[declared]
        lines.append(
            f"| {cp} | {case['phase']} | {case['kind']} | {declared} | {struct_txt} | {beh_txt} | {outcome} |"
        )

    lines.append("")
    lines.append("## 汇总\n")
    lines.append(
        f"- AgentNexus 侧通过：**{counts['verified']}**；部分通过：**{counts['partial']}**；"
        f"无本仓证据（blocked）：**{counts['blocked']}**；证据失败/缺失：**{counts['failed']}**"
    )
    lines.append(f"- 行为测试实际执行：{sum(1 for v in outcomes.values() if v == 'PASSED')} passed / "
                 f"{sum(1 for v in outcomes.values() if v in ('FAILED', 'ERROR'))} failed / "
                 f"{sum(1 for v in outcomes.values() if v == 'SKIPPED')} skipped")

    partial_or_blocked = [case for case in coverage["cases"] if case["status"] != "verified"]
    lines.append("\n## 限制与未覆盖（不得据此声称通过）\n")
    for case in partial_or_blocked:
        owner = case.get("owner", "AgentNexus")
        reason = case.get("limitation") or case.get("note") or "未说明"
        lines.append(f"- **{case['id']}**（{case['status']}，owner={owner}）：{reason}")
    lines.append("")
    lines.append("## 结论\n")
    lines.append(
        "- 本记录只覆盖**门禁允许范围**（BINDING-GATE-1 关闭、仅独立语义验证，无集成运行）。"
        "T1–T6 仍未关闭，`compatibility.json` 未三方冻结，因此 **CP-01～26 不构成符合性结论**。"
    )
    lines.append("- 上表 `blocked` / `partial` 的用例在相应 owner 提供证据并复核前一律视为未通过。")
    lines.append("- 重跑：见文件头用法；记录内所有摘要可按输入自行复算核对。")
    return "\n".join(lines) + "\n"


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="执行 CP-01～26 并生成运行记录")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", help="pytest -rA 报告文件（受限环境推荐）")
    source.add_argument("--run", action="store_true", help="由本脚本调用 pytest")
    source.add_argument("--list-tests", action="store_true", help="只打印需要执行的行为测试 node id")
    parser.add_argument("--out", help="运行记录输出路径（默认 fixtures/binding/cp-execution-record-<date>.md）")
    parser.add_argument("--date", help="记录日期（默认今天，UTC）")
    args = parser.parse_args(argv)

    matrix = _load(MATRIX)
    coverage = _load(COVERAGE)
    problems = validate_mapping(matrix, coverage)
    if problems:
        print("[FAIL] 覆盖映射不可用：")
        for problem in problems:
            print("   -", problem)
        return 2

    tests = collect_tests(coverage)
    if args.list_tests:
        for node in tests:
            print(node)
        print(f"# 共 {len(tests)} 个 node id", file=sys.stderr)
        return 0

    command = "python -m pytest " + " ".join(tests) + " -q -p no:cacheprovider --tb=no -rA"
    if args.run:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", "--tb=no", "-rA"],
            cwd=ROOT,
            capture_output=True,
        )
        text = _decode_report(proc.stdout + proc.stderr)
        mode = "run"
    elif args.input:
        report = Path(args.input)
        if not report.is_absolute():
            report = ROOT / report
        if not report.exists():
            print(f"[FAIL] 找不到报告文件：{report}")
            return 2
        text = _decode_report(report.read_bytes())
        mode = "input"
        command = f"python -m pytest <{len(tests)} node ids> -q -p no:cacheprovider --tb=no -rA > {args.input}"
    else:
        print("[FAIL] 需要 --input / --run / --list-tests 之一")
        return 2

    if "\ufffd" in text:
        print("[FAIL] 报告不可用：含 U+FFFD，测试结论无法逐条还原。")
        print("       请设置 $env:PYTHONIOENCODING='utf-8' 后重跑并再次执行本脚本。")
        return 3

    outcomes = parse_test_report(text)
    if not outcomes:
        print("[FAIL] 报告中没有解析到逐条结果（PASSED/FAILED 行）。")
        print(f"       期望命令：{command}")
        return 2

    validate_mod = _load_module("code_review_validate", BASE / "tools" / "validate.py")
    structural: Dict[str, StructuralResult] = {}
    for case in matrix["cases"]:
        cp = case["id"]
        result = check_structural(validate_mod, case)
        if case["id"] in ("CP-23", "CP-26"):
            digest = check_digest(validate_mod)
            result.ok.extend(digest.ok)
            result.failed.extend(digest.failed)
        structural[cp] = result

    date = args.date or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    record = build_record(matrix, coverage, {"structural": structural, "outcomes": outcomes}, mode, command, date)

    out = Path(args.out) if args.out else Path(str(DEFAULT_OUT).format(date=date))
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(record, encoding="utf-8")
    print(f"[OK] 运行记录已写入 {out.relative_to(ROOT)}")

    failed = 0
    for case in coverage["cases"]:
        if structural[case["id"]].failed:
            failed += 1
        elif any(
            verdict_for(node, outcomes) in BAD_VERDICTS + MISSING_VERDICTS
            for node in case.get("tests", [])
        ):
            failed += 1
    print(f"[{'PASS' if failed == 0 else 'FAIL'}] CP 用例：{len(matrix['cases'])} 个，"
          f"证据失败/缺失 {failed} 个；未覆盖用例见记录中的限制小节。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
