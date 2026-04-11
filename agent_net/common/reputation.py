"""
Reputation System - 交互声誉系统

支持动态信任评分：base_score + behavior_delta + attestation_bonus

v0.9.6 新增。
"""
from __future__ import annotations

import aiosqlite
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_net.common.constants import DATA_DIR


# ---------------------------------------------------------------------------
# L 级基础分映射
# ---------------------------------------------------------------------------

LEVEL_BASE_SCORES = {
    1: 15.0,   # L1: 最低信任
    2: 40.0,   # L2: 有 cert
    3: 70.0,   # L3: trusted CA cert
    4: 95.0,   # L4: entity_verified
}


# ---------------------------------------------------------------------------
# 数据结构
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

    @classmethod
    def from_row(cls, row: tuple) -> "InteractionRecord":
        return cls(
            id=row[0],
            from_did=row[1],
            to_did=row[2],
            interaction_type=row[3],
            success=bool(row[4]),
            response_time_ms=row[5],
            timestamp=row[6],
        )


@dataclass
class ReputationScore:
    """声誉评分（v0.9 重构）"""
    agent_did: str
    base_score: float           # L 级基础分（0-100）
    behavior_delta: float       # 行为加成/扣分（-20 ~ +20）
    attestation_bonus: float    # 治理认证加成（0 ~ +15）
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

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path else None

    async def _get_db(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        if self.db_path:
            return await aiosqlite.connect(self.db_path)
        else:
            from agent_net.storage import DB_PATH
            return await aiosqlite.connect(DB_PATH)

    async def init_tables(self, conn: Optional[aiosqlite.Connection] = None) -> None:
        """初始化表（由 storage.py 调用）"""
        if conn:
            await self._init_tables(conn)
        else:
            async with await self._get_db() as db_conn:
                await self._init_tables(db_conn)

    async def _init_tables(self, conn: aiosqlite.Connection) -> None:
        # 交互记录表
        await conn.execute("""
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
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interactions_to_did
            ON interactions(to_did, timestamp)
        """)

        # 声誉缓存表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reputation_cache (
                agent_did TEXT PRIMARY KEY,
                base_score REAL NOT NULL,
                behavior_delta REAL NOT NULL,
                attestation_bonus REAL NOT NULL,
                trust_level INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await conn.commit()

    async def record_interaction(
        self,
        record: InteractionRecord,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> int:
        """记录一次交互"""
        async def _record(c: aiosqlite.Connection) -> int:
            cursor = await c.execute(
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
            await c.commit()
            return cursor.lastrowid or 0

        if conn:
            return await _record(conn)
        else:
            async with await self._get_db() as db_conn:
                return await _record(db_conn)

    async def get_interactions(
        self,
        agent_did: str,
        time_window_days: int = 30,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> list[InteractionRecord]:
        """获取 Agent 的交互历史"""
        now = time.time()
        window_start = now - time_window_days * 86400

        async def _get(c: aiosqlite.Connection) -> list[InteractionRecord]:
            cursor = await c.execute(
                """
                SELECT id, from_did, to_did, interaction_type, success, response_time_ms, timestamp
                FROM interactions
                WHERE to_did = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (agent_did, window_start),
            )
            rows = await cursor.fetchall()
            return [InteractionRecord.from_row(row) for row in rows]

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as db_conn:
                return await _get(db_conn)

    async def save_reputation(
        self,
        rep: ReputationScore,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> None:
        """保存声誉评分缓存"""
        async def _save(c: aiosqlite.Connection):
            await c.execute(
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
            await c.commit()

        if conn:
            await _save(conn)
        else:
            async with await self._get_db() as db_conn:
                await _save(db_conn)

    async def get_reputation(
        self,
        agent_did: str,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> Optional[ReputationScore]:
        """获取缓存的声誉评分"""
        async def _get(c: aiosqlite.Connection) -> Optional[ReputationScore]:
            cursor = await c.execute(
                """
                SELECT agent_did, base_score, behavior_delta, attestation_bonus, trust_level
                FROM reputation_cache WHERE agent_did = ?
                """,
                (agent_did,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return ReputationScore(
                agent_did=row[0],
                base_score=row[1],
                behavior_delta=row[2],
                attestation_bonus=row[3],
                trust_level=row[4],
            )

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as db_conn:
                return await _get(db_conn)

    async def compute_reputation(
        self,
        agent_did: str,
        trust_level: int,
        attestation_bonus: float = 0.0,
        time_window_days: int = 30,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> ReputationScore:
        """
        计算并保存声誉评分

        Args:
            agent_did: Agent DID
            trust_level: L1-L4
            attestation_bonus: 治理认证加成
            time_window_days: 行为评估时间窗口

        Returns:
            ReputationScore
        """
        async def _compute(c: aiosqlite.Connection) -> ReputationScore:
            # 获取交互历史
            interactions = await self.get_interactions(agent_did, time_window_days, c)

            # 计算行为加成
            scorer = BehaviorScorer()
            behavior_delta = scorer.compute_behavior_delta(interactions, time_window_days)

            # 基础分
            base_score = LEVEL_BASE_SCORES.get(trust_level, 15.0)

            rep = ReputationScore(
                agent_did=agent_did,
                base_score=base_score,
                behavior_delta=behavior_delta,
                attestation_bonus=attestation_bonus,
                trust_level=trust_level,
            )

            # 缓存
            await self.save_reputation(rep, c)

            return rep

        if conn:
            return await _compute(conn)
        else:
            async with await self._get_db() as c:
                return await _compute(c)

    async def get_all_reputations(
        self,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> list[ReputationScore]:
        """获取所有缓存的声誉评分"""
        async def _get(c: aiosqlite.Connection) -> list[ReputationScore]:
            cursor = await c.execute(
                """
                SELECT agent_did, base_score, behavior_delta, attestation_bonus, trust_level
                FROM reputation_cache
                """
            )
            rows = await cursor.fetchall()
            return [
                ReputationScore(
                    agent_did=row[0],
                    base_score=row[1],
                    behavior_delta=row[2],
                    attestation_bonus=row[3],
                    trust_level=row[4],
                )
                for row in rows
            ]

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as db_conn:
                return await _get(db_conn)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def compute_trust_score(
    trust_level: int,
    behavior_delta: float = 0.0,
    attestation_bonus: float = 0.0,
) -> ReputationScore:
    """
    计算信任评分（不依赖存储）
    """
    return ReputationScore(
        agent_did="",  # 调用者填充
        base_score=LEVEL_BASE_SCORES.get(trust_level, 15.0),
        behavior_delta=behavior_delta,
        attestation_bonus=attestation_bonus,
        trust_level=trust_level,
    )