"""§15.3 字节口径与摘要。

Profile §15.3 的规范性要求：

- ``artifact_body`` 必须是**字符串**；摘要输入 ``B`` 是该字符串**严格编码为 UTF-8** 的字节
  （无 BOM、不加尾换行、禁止孤立 surrogate）；
- ``report_digest = SHA256(B)``、``byte_length = len(B)``；
- 外层 JSON 的转义方式与空白**不参与**摘要；内层报告原有空白、顺序、换行**均参与**；
- **禁止**解析内层 JSON 后再序列化来计算原报告摘要（旧 ``result_hash`` 即属此类，不得复用）；
- 证据行区间以 LF 定界、保留 CRLF 中的 CR、保留末行是否有 LF，**不做换行归一**。

本模块是上述规则的唯一实现点，路由与适配器都必须调用它，不得自行计算摘要。
"""

from __future__ import annotations

import hashlib
from typing import Tuple

DIGEST_ALGORITHM = "sha256-bytes-v1"
_BOM = "\ufeff"


class DigestError(ValueError):
    """摘要输入不满足 §15.3 的字节口径。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def artifact_body_bytes(artifact_body: str) -> bytes:
    """把 ``artifact_body`` 字符串编码为 §15.3 定义的字节 ``B``。

    严格拒绝：非字符串、内含孤立 surrogate、以 BOM 开头。**不**追加尾换行，
    也不做任何空白或转义归一。
    """
    if not isinstance(artifact_body, str):
        raise DigestError("artifact_body 必须是字符串（§15.3）")
    if artifact_body.startswith(_BOM):
        raise DigestError("artifact_body 不得以 BOM 开头（§15.3）")
    try:
        encoded = artifact_body.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:  # 孤立 surrogate 等
        raise DigestError(f"artifact_body 含不可编码的孤立 surrogate：{exc.reason}") from exc
    return encoded


def report_digest(artifact_body: str) -> Tuple[str, int]:
    """返回 ``("sha256:<hex>", byte_length)``。

    这是 Profile 产物的权威摘要；调用方不得改用重序列化摘要或 ``result_hash``。
    """
    data = artifact_body_bytes(artifact_body)
    return f"sha256:{hashlib.sha256(data).hexdigest()}", len(data)


def _split_lf_lines(text: str) -> list[str]:
    """按 LF 定界切分并保留行尾 LF（保留 CRLF 中的 CR、保留末行是否有 LF）。"""
    parts = text.split("\n")
    if len(parts) == 1:
        return [parts[0]] if parts[0] != "" else []
    lines = [p + "\n" for p in parts[:-1]]
    tail = parts[-1]
    if tail != "":
        lines.append(tail)
    return lines


def line_range_bytes(text: str, start_line: int, end_line: int) -> bytes:
    """取绑定版本的**行区间原始字节**（§15.3、§6.1）。

    行号从 1 开始、闭区间；空文本没有第 1 行。越界或 ``start_line > end_line``
    抛 :class:`DigestError`（调用方映射为 ``input_mismatch``）。
    """
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        raise DigestError("行号必须是整数（§6.1）")
    if start_line < 1 or end_line < 1:
        raise DigestError("行号从 1 开始（§6.1）")
    if start_line > end_line:
        raise DigestError("start_line 不得大于 end_line（§6.1）")
    lines = _split_lf_lines(text)
    if not lines:
        raise DigestError("空文件没有第 1 行（§15.3）")
    if end_line > len(lines):
        raise DigestError(f"行区间超出文件范围：文件 {len(lines)} 行（§15.3）")
    return "".join(lines[start_line - 1 : end_line]).encode("utf-8", errors="strict")


def line_range_sha256(text: str, start_line: int, end_line: int) -> str:
    """行区间原始字节的 SHA256（不带算法前缀，对应 EvidenceRef.content_sha256）。"""
    return hashlib.sha256(line_range_bytes(text, start_line, end_line)).hexdigest()
