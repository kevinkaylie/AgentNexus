"""幂等**业务投影**（RC2 §7 第 147 行）。

为什么需要单独一个模块
----------------------
幂等判定不能用"HTTP 原始字节"或"完整信封"：

- 对原始 JSON 字节算摘要 → 相同 DTO 只要换排版（键序/空白）就被判成
  ``delivery_conflict``（复审 R3-4 复现）；
- 比较完整信封 → 只改了 ``created_at`` 这类**追踪字段**的重放被判成
  ``idempotency_conflict``（同一批复现）。

契约 §7 的规定：

> 其他 binding DTO 比较所有业务字段，排除凭据、头部 correlation ID；消息排除信封
> message_id/created_at/correlation_id/causation_id，但保留 type/sender/receiver/session/
> run/attempt/epoch 及 payload。固定缺省后用递归排序键、数组原顺序、无空白 UTF-8 JSON
> 比较，禁止浮点；这是局部比较规则，不是产物摘要算法。
> 幂等键按认证 principal+动作+资源范围隔离。

本模块把这条规则实现成**一个**显式函数对，消息与产物共用同一条规范化路径，
避免每个端点各写一套"差不多"的比较。

规范化规则
----------
1. 按需剔除追踪字段（见 :data:`MESSAGE_TRACKING_FIELDS`）；
2. **固定缺省**：信封的可选属性缺失时补 ``None``（可选集取自冻结
   ``envelope.schema.json`` 的非 required 属性）；嵌套 payload 的 optionals 由各自的
   payload schema 定义，不做统一缺省，保持"payload 原样参与比较"；
3. **递归排序键**、**数组保持原顺序**、**无空白 UTF-8**；
4. **禁止浮点**（§7 明确禁止）——出现 float 直接 ``invalid_output``，不做四舍五入。

产物的 ``artifact_body`` 是**字符串**，按 §15.3 原样参与比较：绝不对其内部内容
重新序列化或解析。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping, Sequence

from .errors import ProfileError

#: §7：消息比较时排除的信封追踪字段
MESSAGE_TRACKING_FIELDS = ("message_id", "created_at", "correlation_id", "causation_id")

#: 冻结 envelope.schema.json 的非 required 属性——缺失时补固定缺省 ``None``
MESSAGE_OPTIONAL_FIELDS = (
    "request_id",
    "run_id",
    "attempt_id",
    "assignment_epoch",
    "extensions",
    "critical_extensions",
)

#: 产物上传 DTO 的业务字段（§4；按契约字段集合，不含任何追踪字段）
ARTIFACT_BUSINESS_FIELDS = (
    "run_id",
    "attempt_id",
    "assignment_epoch",
    "artifact_body",
    "media_type",
    "schema_version",
    "retention_until",
)


def _reject_floats(value: Any, where: str = "<root>") -> None:
    if isinstance(value, float):
        raise ProfileError(
            "invalid_output",
            f"幂等投影禁止浮点（§7）：{where}",
            scope="idempotency",
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_floats(item, f"{where}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{where}[{index}]")


def _canonical(value: Any) -> Any:
    """递归排序键、保持数组顺序、递归拒绝浮点。"""
    _reject_floats(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """无空白 UTF-8 JSON（键递归排序、数组原顺序、禁浮点）。"""
    return json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def message_projection(envelope: Mapping[str, Any]) -> Dict[str, Any]:
    """消息的业务投影（§7）：剔除追踪字段 + 固定缺省。"""
    if not isinstance(envelope, Mapping):
        raise ProfileError("invalid_output", "信封必须是对象", scope="idempotency")
    projection: Dict[str, Any] = {
        key: value for key, value in envelope.items() if key not in MESSAGE_TRACKING_FIELDS
    }
    for key in MESSAGE_OPTIONAL_FIELDS:
        projection.setdefault(key, None)
    return projection


def artifact_projection(dto: Mapping[str, Any]) -> Dict[str, Any]:
    """产物上传 DTO 的业务投影（§7 + §4）。

    ``artifact_body`` 原样取字符串；其余取业务字段。未声明的字段**不参与**比较
    （它们在路由层已被拒绝，能到这里说明是契约字段）。
    """
    if not isinstance(dto, Mapping):
        raise ProfileError("invalid_output", "上传 DTO 必须是对象", scope="idempotency")
    projection = {}
    for field in ARTIFACT_BUSINESS_FIELDS:
        if field not in dto:
            continue
        value = dto[field]
        if field == "artifact_body":
            if not isinstance(value, str):
                raise ProfileError(
                    "invalid_output", "artifact_body 必须是字符串", scope="idempotency"
                )
            projection[field] = value  # 原样，不重序列化
        else:
            projection[field] = value
    return projection


def projection_digest(projection: Mapping[str, Any], *, namespace: Iterable[str] = ()) -> str:
    """投影摘要。

    ``namespace`` 用于实现 §7 的"幂等键按认证 principal + 动作 + 资源范围隔离"：
    同一 ``Idempotency-Key`` 在不同 namespace 下是**不同的操作**，因此摘要里带上
    namespace，避免跨命名空间误判冲突。
    """
    parts = [str(item) for item in namespace]
    parts.append(canonical_json(projection))
    return "sha256:" + hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
