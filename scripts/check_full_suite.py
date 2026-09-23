#!/usr/bin/env python3
"""全量回归门禁：改动后必须跑全量测试，且失败集合不得超出已登记基线。

为什么需要它
------------
只跑"改动相关的测试"会漏掉**跨模块覆盖型**回归：例如新增模块中的
``store_message`` 与既有 ``messaging.store_message`` 在星号导入链上同名互相覆盖，
只跑新测试全绿，全量却出现 22 个 ``TypeError``。因此把"改动后跑全量"做成可执行门禁，
而不是口头约定。

用法
----
::

    # 1) 跑全量并落盘（任何环境；受限环境建议加 -p no:cacheprovider）
    python -m pytest tests/ -q -p no:cacheprovider --tb=no > .pytest_full_report.txt 2>&1

    # 2) 门禁判定
    python scripts/check_full_suite.py --input .pytest_full_report.txt

    # 3) 由脚本自行调用 pytest（需要允许创建子进程的环境）
    python scripts/check_full_suite.py --run

    # 4) 环境变化后刷新基线（刷新前必须人工审阅 diff，并确认每条失败都能归因）
    python scripts/check_full_suite.py --input .pytest_full_report.txt --update-baseline

退出码
------
- ``0`` 通过：无未登记失败，基线以内。
- ``1`` **回归**：出现未登记失败，或通过数低于基线（测试被删/改名）。
- ``2`` **基线需要维护**：基线项已不再失败、或存在未分类（UNCLASSIFIED）条目。
- ``3`` **报告不可用**：报告文件编码受损（含 U+FFFD），跳过原因无法逐字校验。

编码注意
--------
跳过的**原因**要逐字匹配，所以报告必须以 UTF-8 落盘。中文 Windows 上
`python ... > report.txt` 走的是解释器的 locale 编码（GBK），控制台/管道若按 UTF-8
解读会把中文变成 U+FFFD，导致匹配全部失败。跑全量前先设置：

    $env:PYTHONIOENCODING='utf-8'
    python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs > .pytest_full_report.txt 2>&1
    python scripts/check_full_suite.py --input .pytest_full_report.txt

本脚本对 GBK 报告也能解码（见 ``decode_report``），但**已经丢失**的中文无法还原，
此时按退出码 ``3`` 提示重跑，而不是猜测跳过原因。

基线纪律
--------
``tests/full_suite_baseline.json`` 只登记**可归因于运行环境**的失败，并必须写明原因。
禁止为了让门禁变绿而登记真实失败；未分类的失败不允许写入基线（除非显式
``--allow-unclassified``，且会被标记为待人工确认）。

> 受限环境提示：若沙箱拒绝由子进程写文件，``--update-baseline`` 会以
> ``PermissionError`` 失败；此时可先用本脚本的 ``parse_report``/``reason_for``
> 打印条目，再由人工按同样结构创建该 JSON（内容必须逐条给出归因）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tests" / "full_suite_baseline.json"

FULL_SUITE_COMMAND = "python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs"

#: **环境依赖**测试文件 → 该文件在能力缺失时整体跳过的原因。
#: 这些文件里的用例本身是好的：它们需要真实子进程或工作区外临时目录。
#: 受限环境由 ``tests/conftest.py`` 的能力探针显式 skip（带同一句原因），
#: 因此门禁只对"未登记失败"严格；被跳过的通过数**必须**由本表逐条解释。
ENVIRONMENT_DEPENDENT_FILES: Dict[str, str] = {
    "tests/test_local_cli_backend.py": "受限环境：禁止创建子进程（asyncio.create_subprocess_exec → PermissionError）",
    "tests/test_local_runner.py": "受限环境：禁止创建子进程（asyncio.create_subprocess_exec → PermissionError）",
    "tests/test_runner_loop.py": "受限环境：禁止创建子进程（asyncio.create_subprocess_exec → PermissionError）",
    "tests/test_vault_git.py": "受限环境：禁止创建子进程（asyncio.create_subprocess_exec → PermissionError）",
    "tests/test_relay_did_web.py": "受限环境：工作区外临时目录/家目录不可读写（PermissionError）",
}

#: 兼容旧名（写基线时用于给出归因提示）
KNOWN_ENVIRONMENTAL: Dict[str, str] = dict(ENVIRONMENT_DEPENDENT_FILES)

UNCLASSIFIED = "UNCLASSIFIED：必须人工确认并补写归因后方可登记"


def decode_report(raw: bytes) -> str:
    """把 pytest 输出**字节**解码成文本。

    为什么不能只按 UTF-8 解码：pytest 的 stdout 在被重定向到文件时使用解释器的
    locale 编码（中文 Windows 上是 GBK/cp936）。若只按 UTF-8 读，跳过的**原因**
    会变成 U+FFFD，导致环境跳过逐字匹配全部失败、门禁误报"无理由跳过"。
    因此这里显式按候选编码逐个**严格**解码，取第一个能成功的。
    """
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


def parse_report(text: str) -> Tuple[List[str], Dict[str, int]]:
    """从 pytest 输出解析失败/错误 node id 与汇总计数。"""
    bad: List[str] = []
    for kind in ("FAILED", "ERROR"):
        bad.extend(re.findall(rf"^{kind} (\S+)", text, re.M))

    counts: Dict[str, int] = {}
    for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed"):
        match = re.search(rf"(\d+) {key}\b", text)
        counts[key] = int(match.group(1)) if match else 0
    return bad, counts


def parse_skips(text: str) -> Tuple[List[dict], Dict[str, int]]:
    """解析 ``-rs`` 的 ``SKIPPED [n] <path>:<line>: <reason>``。

    返回 ``(全部跳过记录, {路径: 数量})``；路径统一为正斜杠（Windows 报告用反斜杠）。
    """
    records: List[dict] = []
    counts: Dict[str, int] = {}
    for count, raw_path, reason in re.findall(
        r"^SKIPPED \[(\d+)\] (\S+?):(?:\d+:)? (.*)$", text, re.M
    ):
        path = raw_path.replace("\\", "/")
        number = int(count)
        records.append({"path": path, "count": number, "reason": reason.strip()})
        counts[path] = counts.get(path, 0) + number
    return records, counts


def classify_skips(records: List[dict]) -> Tuple[int, List[str]]:
    """返回 ``(可解释的环境跳过数, 不可解释的跳过描述)``。

    只有原因**逐字匹配**本脚本登记的环境跳过原因的跳过才算可解释；
    其余跳过（例如仓库里既有的 ``@pytest.mark.skip``）必须落在基线 ``counts.skipped``
    以内，超出即视为"可能掩盖回归"。
    """
    env_reasons = set(ENVIRONMENT_DEPENDENT_FILES.values())
    excused = 0
    unexplained: List[str] = []
    for record in records:
        if record["reason"] in env_reasons:
            excused += record["count"]
        else:
            unexplained.append(f"{record['path']} ×{record['count']}：{record['reason'][:80]}")
    return excused, unexplained


def module_of(node_id: str) -> str:
    return node_id.split("::", 1)[0]


def reason_for(node_id: str) -> str:
    return KNOWN_ENVIRONMENTAL.get(module_of(node_id), UNCLASSIFIED)


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(bad: List[str], counts: Dict[str, int], allow_unclassified: bool) -> int:
    entries = []
    unclassified = []
    for node in sorted(set(bad)):
        reason = reason_for(node)
        if reason == UNCLASSIFIED:
            unclassified.append(node)
        entries.append({"node_id": node, "module": module_of(node), "reason": reason})

    if unclassified and not allow_unclassified:
        print("[FAIL] 以下失败无法归因到已知环境因素，**拒绝写入基线**（先判断是否为真实回归）：")
        for node in unclassified:
            print("   -", node)
        print("\n如确认确属环境因素，请把它加入 KNOWN_ENVIRONMENTAL 说明原因；")
        print("确需临时登记时使用 --allow-unclassified（会被标记为待人工确认）。")
        return 1

    baseline = {
        "generated_at_command": FULL_SUITE_COMMAND,
        "counts": counts,
        "environmental_failures": entries,
        "discipline": (
            "本文件只登记可归因于运行环境的失败。新增失败必须先修复；"
            "任何登记都需要说明原因并经代码评审确认（见 CLAUDE.md / tests/CLAUDE.md 的硬规则）。"
        ),
        "unclassified_pending_human": unclassified,
    }
    BASELINE_PATH.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] 已写入基线 {BASELINE_PATH.relative_to(ROOT)}：{len(entries)} 条环境性失败")
    if unclassified:
        print(f"[WARN] 其中 {len(unclassified)} 条标记为待人工确认（unclassified_pending_human）")
    return 0


def check(bad: List[str], counts: Dict[str, int], skip_records: List[dict] | None = None) -> int:
    baseline = load_baseline()
    if not baseline:
        print("[FAIL] 缺少基线文件 tests/full_suite_baseline.json")
        print("       先跑全量并执行：python scripts/check_full_suite.py --input <report> --update-baseline")
        return 2

    known: Set[str] = {entry["node_id"] for entry in baseline.get("environmental_failures", [])}
    actual: Set[str] = set(bad)

    new_failures = sorted(actual - known)
    stale_entries = sorted(known - actual)
    unclassified = baseline.get("unclassified_pending_human") or []
    baseline_passed = int(baseline.get("counts", {}).get("passed", 0))
    baseline_skipped = int(baseline.get("counts", {}).get("skipped", 0))
    excused, unexplained = classify_skips(skip_records or [])
    unexplained_skips = max(0, counts["skipped"] - baseline_skipped - excused)

    print(f"全量结果：{counts['passed']} passed, {counts['skipped']} skipped, "
          f"{counts['failed']} failed, {counts['errors']} errors")
    print(f"基线：{baseline_passed} passed, {baseline_skipped} skipped, "
          f"{len(known)} 条登记的环境性失败")
    if excused:
        print(f"环境跳过：{excused} 项（原因与 ENVIRONMENT_DEPENDENT_FILES 逐字匹配）")

    failed = 0
    if new_failures:
        print("\n[FAIL] 出现**未登记**的失败（按硬规则视为回归，必须先修复）：")
        for node in new_failures:
            hint = KNOWN_ENVIRONMENTAL.get(module_of(node))
            print(f"   - {node}")
            print(f"     归因提示：{hint or '不在已知环境性表中 —— 很可能是本次改动引入'}")
        failed = 1

    if unexplained_skips:
        print(f"\n[FAIL] 跳过数超出基线（{counts['skipped']} > 基线 {baseline_skipped} + 环境跳过 {excused}）：")
        for detail in sorted(unexplained):
            print(f"   - {detail}")
        print("       环境依赖跳过必须由 tests/conftest.py 的能力探针触发并在")
        print("       ENVIRONMENT_DEPENDENT_FILES 登记原因；无理由的跳过按回归处理。")
        failed = 1

    # 通过数下限 = 基线通过数 - 环境跳过的通过数（跳过必须逐条可解释）。
    floor = baseline_passed - excused
    if counts["passed"] < floor:
        print(
            f"\n[FAIL] 通过数下降（{counts['passed']} < 允许下限 {floor}"
            f" = 基线 {baseline_passed} - 环境跳过 {excused}）："
            "测试可能被删除/改名/无理由跳过，需说明并刷新基线"
        )
        failed = 1

    if stale_entries:
        print("\n[FAIL] 基线过时：以下登记项本次**不再失败**，请收窄基线：")
        for node in stale_entries:
            print("   -", node)
        print("       刷新：python scripts/check_full_suite.py --input <report> --update-baseline")
        return 2 if not failed else 1

    if unclassified:
        print("\n[FAIL] 基线中存在未分类条目，必须人工确认归因：")
        for node in unclassified:
            print("   -", node)
        return 2 if not failed else 1

    if failed:
        return 1

    print("\n[PASS] 全量结果与基线一致：无未登记失败，通过数未下降。")
    return 0


def main() -> int:
    # 中文 Windows 控制台是 GBK：打印受损报告内容时不应因编码而崩溃成 traceback。
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - 取决于运行环境
        pass

    parser = argparse.ArgumentParser(description="全量回归门禁（基线比对）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="pytest 输出文件路径")
    source.add_argument("--run", action="store_true", help="由本脚本调用 pytest（需允许创建子进程）")
    parser.add_argument("--update-baseline", action="store_true", help="用本次结果刷新基线")
    parser.add_argument("--allow-unclassified", action="store_true", help="允许登记未归因失败（待人工确认）")
    args = parser.parse_args()

    if args.run:
        import subprocess  # 局部导入：受限环境下不使用该分支

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "--tb=no", "-rs"],
            cwd=ROOT,
            capture_output=True,
        )
        text = decode_report(proc.stdout + proc.stderr)
    else:
        report = Path(args.input)
        if not report.is_absolute():
            report = ROOT / report
        if not report.exists():
            print(f"[FAIL] 找不到报告文件：{report}")
            return 2
        text = decode_report(report.read_bytes())

    bad, counts = parse_report(text)
    if counts["passed"] == 0 and not bad:
        print("[FAIL] 报告中没有解析到测试结果（命令或输出格式不符？）")
        print(f"       期望命令：{FULL_SUITE_COMMAND}")
        return 2

    # 报告若已把中文写成替换字符，跳过原因就不可能逐字匹配——必须 fail-closed，
    # 但要说清是"报告编码坏了"，而不是误报成"出现无理由跳过"。
    if "\ufffd" in text:
        print("[FAIL] 报告不可用：文件含 U+FFFD 替换字符，跳过原因已不可还原。")
        print("       多半是写报告时用了控制台 locale 编码（中文 Windows 为 GBK）。")
        print("       请以 UTF-8 重跑全量后再次执行本门禁：")
        print("         $env:PYTHONIOENCODING='utf-8'")
        print(f"         {FULL_SUITE_COMMAND} > .pytest_full_report.txt 2>&1")
        return 3

    skips, _ = parse_skips(text)
    if args.update_baseline:
        return write_baseline(bad, counts, args.allow_unclassified)
    return check(bad, counts, skips)


if __name__ == "__main__":
    sys.exit(main())
