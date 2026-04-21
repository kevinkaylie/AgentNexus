"""
Consistency Levels for A2A Decision Verification

Proposal: Decision Consistency Levels (2026-04-21)
Related: https://github.com/a2aproject/A2A/issues/1717

L0 — None: constraint hash only, no temporal context (default, zero overhead)
L1 — Wall-clock timestamp: evaluated_at + verification window check
L2 — Causal ordering: HLC (Hybrid Logical Clock)
L3 — Partition-tolerant: store-and-forward with delayed confirmation
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ConsistencyLevel(str, Enum):
    """决策一致性级别"""
    L0 = "L0"  # None — constraint hash only
    L1 = "L1"  # Wall-clock timestamp
    L2 = "L2"  # Causal ordering (HLC)
    L3 = "L3"  # Partition-tolerant


#: 默认 L1 验证窗口（秒）
DEFAULT_L1_WINDOW_SECONDS = 30


@dataclass
class EvaluationContext:
    """评估上下文，随一致性级别递增携带更多信息"""
    evaluated_at: Optional[float] = None       # Unix timestamp (L1+)
    policy_version: Optional[str] = None       # 策略版本 (L1+)
    wall_time: Optional[int] = None            # HLC wall time ms (L2+)
    logical: Optional[int] = None              # HLC logical counter (L2+)
    node_id: Optional[str] = None              # HLC node identifier (L2+)

    def to_dict(self) -> dict:
        result = {}
        if self.evaluated_at is not None:
            result["evaluated_at"] = self.evaluated_at
        if self.policy_version is not None:
            result["policy_version"] = self.policy_version
        if self.wall_time is not None:
            result["hlc"] = {
                "wall_time": self.wall_time,
                "logical": self.logical,
                "node_id": self.node_id,
            }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationContext":
        hlc = data.get("hlc", {})
        return cls(
            evaluated_at=data.get("evaluated_at"),
            policy_version=data.get("policy_version"),
            wall_time=hlc.get("wall_time"),
            logical=hlc.get("logical"),
            node_id=hlc.get("node_id"),
        )


def check_l1_window(
    evaluated_at: float,
    window_seconds: float = DEFAULT_L1_WINDOW_SECONDS,
    now: Optional[float] = None,
) -> tuple[bool, str]:
    """
    检查 L1 时间窗口：验证 evaluated_at 与当前时间的差值在合理范围内。

    Args:
        evaluated_at: 决策评估时间戳（Unix seconds）
        window_seconds: 允许的偏差窗口（默认 30 秒）
        now: 当前时间（可注入用于测试）

    Returns:
        (within_window, reason)
    """
    if now is None:
        now = time.time()

    drift = abs(now - evaluated_at)
    if drift <= window_seconds:
        return True, "within_window"
    return False, f"time_drift_{int(drift)}s_exceeds_window_{int(window_seconds)}s"


def build_evaluation_context(
    level: ConsistencyLevel,
    policy_version: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Optional[EvaluationContext]:
    """
    根据一致性级别构建 evaluation_context。

    L0 返回 None（零开销）。
    L1 携带 wall-clock timestamp。
    L2+ 携带 HLC tuple。
    """
    if level == ConsistencyLevel.L0:
        return None

    now = time.time()
    ctx = EvaluationContext(
        evaluated_at=now,
        policy_version=policy_version,
    )

    if level in (ConsistencyLevel.L2, ConsistencyLevel.L3):
        ctx.wall_time = int(now * 1000)
        ctx.logical = 0
        ctx.node_id = node_id

    return ctx
