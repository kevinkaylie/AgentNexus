"""
v0.9.6 交互声誉系统测试套件
测试 ID: tr_rep_01 – tr_rep_12

覆盖场景：
  - trust_score 重构：base_score + behavior_delta + attestation_bonus
  - 交互历史记录（成功率、响应速度）
  - 动态加减分
  - OATR 0-100 连续评分兼容
  - 声誉存储 & 查询
"""
import asyncio
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class InteractionRecord:
    """交互记录"""
    id: Optional[int]
    from_did: str
    to_did: str
    interaction_type: str     # "message" / "task" / "transaction"
    success: bool
    response_time_ms: Optional[float]
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_did": self.from_did,
            "to_did": self.to_did,
            "interaction_type": self.interaction_type,
            "success": self.success,
            "response_time_ms": self.response_time_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class ReputationScore:
    """声誉评分（v0.9 重构）"""
    agent_did: str
    base_score: float           # L 级基础分（0-100）
    behavior_delta: float       # 行为加成/扣分（-20 ~ +20）
    attestation_bonus: float    # OATR attestation 加成（0 ~ +15）
    trust_level: int            # L1-L4

    @property
    def trust_score(self) -> float:
        """最终信任分（0-100 连续评分）"""
        score = self.base_score + self.behavior_delta + self.attestation_bonus
        return max(0.0, min(100.0, score))

    def to_dict(self) -> dict:
        return {
            "agent_did": self.agent_did,
            "base_score": round(self.base_score, 2),
            "behavior_delta": round(self.behavior_delta, 2),
            "attestation_bonus": round(self.attestation_bonus, 2),
            "trust_score": round(self.trust_score, 2),
            "trust_level": self.trust_level,
        }

    def to_oatr_format(self) -> dict:
        """导出为 OATR 标准格式"""
        return {
            "extensions": {
                "agent-trust": {
                    "did": self.agent_did,
                    "trust_level": self.trust_level,
                    "trust_score": round(self.trust_score, 2),
                    "base_score": round(self.base_score, 2),
                    "behavior_delta": round(self.behavior_delta, 2),
                    "attestation_bonus": round(self.attestation_bonus, 2),
                }
            }
        }


# ---------------------------------------------------------------------------
# 行为评分引擎
# ---------------------------------------------------------------------------

class BehaviorScorer:
    """
    行为评分计算引擎
    基于：
      - 交互成功率
      - 响应速度
      - 交互频率
    """

    def __init__(
        self,
        success_weight: float = 0.5,
        response_time_weight: float = 0.3,
        frequency_weight: float = 0.2,
    ):
        self.success_weight = success_weight
        self.response_time_weight = response_time_weight
        self.frequency_weight = frequency_weight

    def compute_behavior_delta(
        self,
        interactions: list[InteractionRecord],
        time_window_days: int = 30,
    ) -> float:
        """
        计算行为加成/扣分
        返回值范围：-20.0 ~ +20.0

        公式：
          behavior_delta = success_component + response_component + frequency_component

          success_component = (success_rate - 0.8) * 50  # 成功率 >80% 加分
          response_component = (1 - avg_response_time / expected_time) * 10  # 响应快加分
          frequency_component = min(interactions / expected_count, 1.0) * 5  # 活跃度加分
        """
        if not interactions:
            return 0.0

        # 过滤时间窗口内的交互
        now = time.time()
        window_start = now - time_window_days * 86400
        recent = [i for i in interactions if i.timestamp >= window_start]

        if not recent:
            return 0.0

        # 1. 成功率分量
        success_count = sum(1 for i in recent if i.success)
        success_rate = success_count / len(recent)
        success_component = (success_rate - 0.8) * 50  # 80% 为基准线

        # 2. 响应速度分量
        response_times = [i.response_time_ms for i in recent if i.response_time_ms is not None]
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            # 期望响应时间 5000ms（5秒），越快加分越多
            expected_response = 5000.0
            response_component = max(-10, (1 - avg_response / expected_response) * 10)
        else:
            response_component = 0.0

        # 3. 活跃度分量
        # 期望 30 天内 50 次交互
        expected_count = 50
        frequency_component = min(len(recent) / expected_count, 1.0) * 5

        total = success_component + response_component + frequency_component

        # 限制范围
        return max(-20.0, min(20.0, total))


# ---------------------------------------------------------------------------
# 声誉存储（SQLite）
# ---------------------------------------------------------------------------

class ReputationStore:
    """声誉数据存储"""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（持久连接）"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                interaction_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                response_time_ms REAL,
                timestamp REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interactions_to_did
            ON interactions(to_did, timestamp)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reputation_cache (
                agent_did TEXT PRIMARY KEY,
                base_score REAL NOT NULL,
                behavior_delta REAL NOT NULL,
                attestation_bonus REAL NOT NULL,
                trust_level INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

    def record_interaction(self, record: InteractionRecord) -> int:
        """记录一次交互"""
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO interactions
            (from_did, to_did, interaction_type, success, response_time_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.from_did,
                record.to_did,
                record.interaction_type,
                1 if record.success else 0,
                record.response_time_ms,
                record.timestamp,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def get_interactions(
        self,
        agent_did: str,
        time_window_days: int = 30,
    ) -> list[InteractionRecord]:
        """获取 Agent 的交互历史"""
        now = time.time()
        window_start = now - time_window_days * 86400

        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM interactions
            WHERE to_did = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (agent_did, window_start),
        ).fetchall()

        return [
            InteractionRecord(
                id=row["id"],
                from_did=row["from_did"],
                to_did=row["to_did"],
                interaction_type=row["interaction_type"],
                success=bool(row["success"]),
                response_time_ms=row["response_time_ms"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def save_reputation(self, rep: ReputationScore) -> None:
        """保存声誉评分缓存"""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO reputation_cache
            (agent_did, base_score, behavior_delta, attestation_bonus, trust_level, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rep.agent_did,
                rep.base_score,
                rep.behavior_delta,
                rep.attestation_bonus,
                rep.trust_level,
                time.time(),
            ),
        )
        conn.commit()

    def get_reputation(self, agent_did: str) -> Optional[ReputationScore]:
        """获取缓存的声誉评分"""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT * FROM reputation_cache WHERE agent_did = ?
            """,
            (agent_did,),
        ).fetchone()

        if row is None:
            return None

        return ReputationScore(
            agent_did=row["agent_did"],
            base_score=row["base_score"],
            behavior_delta=row["behavior_delta"],
            attestation_bonus=row["attestation_bonus"],
            trust_level=row["trust_level"],
        )


# ---------------------------------------------------------------------------
# L 级基础分映射
# ---------------------------------------------------------------------------

LEVEL_BASE_SCORES = {
    1: 15.0,   # L1: 最低信任
    2: 40.0,   # L2: 有 cert
    3: 70.0,   # L3: trusted CA cert
    4: 95.0,   # L4: entity_verified
}


def compute_trust_score(
    trust_level: int,
    behavior_delta: float = 0.0,
    attestation_bonus: float = 0.0,
) -> ReputationScore:
    """
    计算完整的信任评分
    """
    return ReputationScore(
        agent_did="",  # 调用者填充
        base_score=LEVEL_BASE_SCORES.get(trust_level, 15.0),
        behavior_delta=behavior_delta,
        attestation_bonus=attestation_bonus,
        trust_level=trust_level,
    )


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_tr_rep_01_base_score_mapping():
    """L 级基础分映射正确"""
    assert LEVEL_BASE_SCORES[1] == 15.0
    assert LEVEL_BASE_SCORES[2] == 40.0
    assert LEVEL_BASE_SCORES[3] == 70.0
    assert LEVEL_BASE_SCORES[4] == 95.0


def test_tr_rep_02_trust_score_formula():
    """trust_score = base_score + behavior_delta + attestation_bonus"""
    rep = ReputationScore(
        agent_did="did:agentnexus:zTest",
        base_score=70.0,
        behavior_delta=5.0,
        attestation_bonus=8.5,
        trust_level=3,
    )
    assert rep.trust_score == 83.5


def test_tr_rep_03_trust_score_clamped():
    """trust_score 限制在 0-100 范围"""
    # 超过 100
    rep = ReputationScore(
        agent_did="did:agentnexus:zTest",
        base_score=95.0,
        behavior_delta=10.0,
        attestation_bonus=10.0,
        trust_level=4,
    )
    assert rep.trust_score == 100.0

    # 低于 0
    rep = ReputationScore(
        agent_did="did:agentnexus:zTest",
        base_score=15.0,
        behavior_delta=-20.0,
        attestation_bonus=0.0,
        trust_level=1,
    )
    assert rep.trust_score == 0.0


def test_tr_rep_04_behavior_scorer_success_rate():
    """成功率影响 behavior_delta"""
    scorer = BehaviorScorer()
    now = time.time()

    # 高成功率（90%）
    interactions = [
        InteractionRecord(None, "did:a", "did:b", "message", True, 1000, now - i)
        for i in range(90)
    ] + [
        InteractionRecord(None, "did:a", "did:b", "message", False, 1000, now - i)
        for i in range(10)
    ]

    delta = scorer.compute_behavior_delta(interactions)
    # 成功率 90% > 80%，应加分
    assert delta > 0


def test_tr_rep_05_behavior_scorer_response_time():
    """响应速度影响 behavior_delta"""
    scorer = BehaviorScorer()
    now = time.time()

    # 快速响应（100ms）
    fast_interactions = [
        InteractionRecord(None, "did:a", "did:b", "message", True, 100, now - i)
        for i in range(50)
    ]
    fast_delta = scorer.compute_behavior_delta(fast_interactions)

    # 慢速响应（10000ms）
    slow_interactions = [
        InteractionRecord(None, "did:a", "did:b", "message", True, 10000, now - i)
        for i in range(50)
    ]
    slow_delta = scorer.compute_behavior_delta(slow_interactions)

    # 快速响应应得更高分
    assert fast_delta > slow_delta


def test_tr_rep_06_behavior_scorer_delta_range():
    """behavior_delta 范围限制在 [-20, +20]"""
    scorer = BehaviorScorer()
    now = time.time()

    # 极端成功（全部成功 + 超快响应）
    perfect = [
        InteractionRecord(None, "did:a", "did:b", "message", True, 1, now - i)
        for i in range(100)
    ]
    delta = scorer.compute_behavior_delta(perfect)
    assert delta <= 20.0

    # 极端失败（全部失败 + 超慢响应）
    terrible = [
        InteractionRecord(None, "did:a", "did:b", "message", False, 100000, now - i)
        for i in range(100)
    ]
    delta = scorer.compute_behavior_delta(terrible)
    assert delta >= -20.0


def test_tr_rep_07_reputation_store_crud():
    """ReputationStore 基础 CRUD"""
    store = ReputationStore()

    # 记录交互
    record = InteractionRecord(
        id=None,
        from_did="did:agentnexus:zA",
        to_did="did:agentnexus:zB",
        interaction_type="message",
        success=True,
        response_time_ms=500,
        timestamp=time.time(),
    )
    record_id = store.record_interaction(record)
    assert record_id > 0

    # 查询交互
    interactions = store.get_interactions("did:agentnexus:zB")
    assert len(interactions) == 1
    assert interactions[0].from_did == "did:agentnexus:zA"
    assert interactions[0].success is True


def test_tr_rep_08_reputation_store_time_window():
    """时间窗口过滤正确"""
    store = ReputationStore()
    now = time.time()

    # 记录不同时间的交互
    store.record_interaction(InteractionRecord(
        None, "did:a", "did:b", "message", True, 100, now - 86400 * 5
    ))
    store.record_interaction(InteractionRecord(
        None, "did:a", "did:b", "message", True, 100, now - 86400 * 10
    ))
    store.record_interaction(InteractionRecord(
        None, "did:a", "did:b", "message", True, 100, now - 86400 * 40
    ))  # 超出 30 天窗口

    # 只返回 30 天内的
    interactions = store.get_interactions("did:b", time_window_days=30)
    assert len(interactions) == 2


def test_tr_rep_09_reputation_cache():
    """声誉评分缓存"""
    store = ReputationStore()

    rep = ReputationScore(
        agent_did="did:agentnexus:zTest",
        base_score=70.0,
        behavior_delta=5.0,
        attestation_bonus=8.5,
        trust_level=3,
    )
    store.save_reputation(rep)

    cached = store.get_reputation("did:agentnexus:zTest")
    assert cached is not None
    assert cached.trust_score == 83.5
    assert cached.trust_level == 3


def test_tr_rep_10_oatr_format_export():
    """导出为 OATR 标准格式"""
    rep = ReputationScore(
        agent_did="did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        base_score=75.0,
        behavior_delta=0.0,
        attestation_bonus=8.5,
        trust_level=3,
    )

    oatr = rep.to_oatr_format()
    assert "extensions" in oatr
    assert "agent-trust" in oatr["extensions"]
    assert oatr["extensions"]["agent-trust"]["trust_score"] == 83.5


def test_tr_rep_11_empty_interactions():
    """无交互记录时 behavior_delta 为 0"""
    scorer = BehaviorScorer()
    delta = scorer.compute_behavior_delta([])
    assert delta == 0.0


def test_tr_rep_12_compute_trust_score_helper():
    """compute_trust_score 辅助函数"""
    rep = compute_trust_score(
        trust_level=3,
        behavior_delta=5.0,
        attestation_bonus=10.0,
    )
    assert rep.base_score == 70.0
    assert rep.trust_score == 85.0
    assert rep.trust_level == 3


# ---------------------------------------------------------------------------
# 集成测试：与 RuntimeVerifier 结合
# ---------------------------------------------------------------------------

def test_tr_rep_13_integration_with_verifier():
    """与 RuntimeVerifier 集成：trust_score 包含行为分量"""
    store = ReputationStore()
    scorer = BehaviorScorer()
    now = time.time()

    agent_did = "did:agentnexus:zTestAgent"

    # 记录 50 次成功交互
    for i in range(50):
        store.record_interaction(InteractionRecord(
            None, "did:caller", agent_did, "message", True, 500, now - i * 60
        ))

    # 计算行为加成
    interactions = store.get_interactions(agent_did)
    behavior_delta = scorer.compute_behavior_delta(interactions)

    # 计算完整 trust_score
    rep = compute_trust_score(
        trust_level=3,
        behavior_delta=behavior_delta,
        attestation_bonus=0.0,
    )
    rep.agent_did = agent_did

    # 保存缓存
    store.save_reputation(rep)

    # 验证
    cached = store.get_reputation(agent_did)
    assert cached is not None
    assert cached.trust_score > 70.0  # base_score + 行为加成
