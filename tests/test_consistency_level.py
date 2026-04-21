"""
Consistency Levels 测试套件
测试 ID: cl_01 – cl_07

覆盖场景：
  - L0: 零开销，无 temporal context
  - L1: wall-clock timestamp + 验证窗口检查
  - build_evaluation_context 各级别构建
  - check_l1_window 边界值
"""
import sys
import time

import pytest

sys.path.insert(0, ".")

from agent_net.common.consistency_level import (
    ConsistencyLevel,
    EvaluationContext,
    build_evaluation_context,
    check_l1_window,
)


# ---------------------------------------------------------------------------
# L0 — 零开销
# ---------------------------------------------------------------------------

def test_cl_01_l0_context_omitted():
    """L0 不生成 evaluation_context（零开销）"""
    ctx = build_evaluation_context(ConsistencyLevel.L0)
    assert ctx is None


# ---------------------------------------------------------------------------
# L1 — wall-clock timestamp
# ---------------------------------------------------------------------------

def test_cl_02_l1_carries_timestamp():
    """L1 携带 evaluated_at 时间戳"""
    ctx = build_evaluation_context(ConsistencyLevel.L1, policy_version="v1.2")
    assert ctx is not None
    assert ctx.evaluated_at is not None
    assert ctx.wall_time is None  # L1 不含 HLC
    assert ctx.policy_version == "v1.2"


def test_cl_03_l1_window_within():
    """L1: 时间在窗口内 → 通过"""
    now = time.time()
    ok, reason = check_l1_window(now, window_seconds=30, now=now)
    assert ok is True
    assert reason == "within_window"


def test_cl_04_l1_window_exceeded():
    """L1: 时间超出窗口 → 拒绝"""
    now = time.time()
    past = now - 60  # 60 秒前
    ok, reason = check_l1_window(past, window_seconds=30, now=now)
    assert ok is False
    assert "exceeds_window" in reason


def test_cl_05_l1_window_boundary():
    """L1: 边界值精确测试"""
    now = 1000.0
    # 正好 30 秒 → 应通过
    ok, _ = check_l1_window(970.0, window_seconds=30, now=now)
    assert ok is True
    # 30.001 秒 → 应拒绝
    ok, _ = check_l1_window(969.99, window_seconds=30, now=now)
    assert ok is False


# ---------------------------------------------------------------------------
# L2+ — HLC
# ---------------------------------------------------------------------------

def test_cl_06_l2_carries_hlc():
    """L2 携带 HLC tuple"""
    ctx = build_evaluation_context(
        ConsistencyLevel.L2,
        policy_version="v1.2",
        node_id="did:agentnexus:z6Mk...",
    )
    assert ctx is not None
    assert ctx.wall_time is not None
    assert ctx.logical == 0
    assert ctx.node_id == "did:agentnexus:z6Mk..."
    assert ctx.evaluated_at is not None


# ---------------------------------------------------------------------------
# EvaluationContext 序列化
# ---------------------------------------------------------------------------

def test_cl_07_evaluation_context_roundtrip():
    """EvaluationContext dict 序列化/反序列化"""
    original = EvaluationContext(
        evaluated_at=1713600000.0,
        policy_version="v1.2",
        wall_time=1713600000000,
        logical=3,
        node_id="did:agentnexus:z6Mk...",
    )
    d = original.to_dict()
    assert d["evaluated_at"] == 1713600000.0
    assert d["policy_version"] == "v1.2"
    assert d["hlc"]["wall_time"] == 1713600000000
    assert d["hlc"]["logical"] == 3
    assert d["hlc"]["node_id"] == "did:agentnexus:z6Mk..."

    restored = EvaluationContext.from_dict(d)
    assert restored.evaluated_at == original.evaluated_at
    assert restored.wall_time == original.wall_time
    assert restored.logical == original.logical
    assert restored.node_id == original.node_id
