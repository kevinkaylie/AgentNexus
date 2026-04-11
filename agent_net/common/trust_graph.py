"""
Web of Trust - 信任网络图

支持信任传递、路径发现、信任衰减。

v0.9.6 新增。
"""
from __future__ import annotations

import asyncio
import aiosqlite
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_net.common.constants import DATA_DIR


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TrustEdge:
    """信任边：A → B 的信任关系"""
    from_did: str
    to_did: str
    score: float              # 0.0 - 1.0，A 对 B 的直接信任分
    timestamp: float          # 建立时间（Unix epoch）
    evidence: Optional[str]   # 信任来源证据（cert ID / 交互记录 ID）

    def to_dict(self) -> dict:
        return {
            "from_did": self.from_did,
            "to_did": self.to_did,
            "score": self.score,
            "timestamp": self.timestamp,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrustEdge":
        return cls(
            from_did=d["from_did"],
            to_did=d["to_did"],
            score=d["score"],
            timestamp=d["timestamp"],
            evidence=d.get("evidence"),
        )


@dataclass
class TrustPath:
    """信任路径：A → B → C 的链式信任"""
    nodes: list[str]          # [A_did, B_did, C_did]
    edges: list[TrustEdge]
    derived_score: float      # 衰减后的信任分

    def to_dict(self) -> dict:
        return {
            "nodes": self.nodes,
            "edges": [e.to_dict() for e in self.edges],
            "derived_score": round(self.derived_score, 4),
        }


# ---------------------------------------------------------------------------
# 信任图（内存版）
# ---------------------------------------------------------------------------

class TrustGraph:
    """
    Web of Trust 图结构（内存版）
    支持：
      - 添加/移除信任边
      - 查找信任路径（BFS）
      - 计算衍生信任分
      - 信任衰减
    """

    def __init__(self, max_depth: int = 4, decay_rate: float = 0.15):
        """
        Args:
            max_depth: 最大信任传递深度（防止无限搜索）
            decay_rate: 每跳衰减率（默认 15%）
        """
        self.max_depth = max_depth
        self.decay_rate = decay_rate
        self.edges: dict[str, list[TrustEdge]] = {}  # from_did -> [edges]

    def add_edge(self, edge: TrustEdge) -> None:
        """添加信任边"""
        if edge.from_did not in self.edges:
            self.edges[edge.from_did] = []
        # 检查是否已存在到同一目标的边
        for i, existing in enumerate(self.edges[edge.from_did]):
            if existing.to_did == edge.to_did:
                # 更新
                self.edges[edge.from_did][i] = edge
                return
        self.edges[edge.from_did].append(edge)

    def remove_edge(self, from_did: str, to_did: str) -> bool:
        """移除信任边"""
        if from_did not in self.edges:
            return False
        for i, e in enumerate(self.edges[from_did]):
            if e.to_did == to_did:
                self.edges[from_did].pop(i)
                return True
        return False

    def get_direct_trust(self, from_did: str, to_did: str) -> Optional[TrustEdge]:
        """获取直接信任边"""
        if from_did not in self.edges:
            return None
        for e in self.edges[from_did]:
            if e.to_did == to_did:
                return e
        return None

    def find_trust_paths(self, source: str, target: str) -> list[TrustPath]:
        """
        查找从 source 到 target 的所有信任路径（BFS）
        限制最大深度 self.max_depth
        """
        if source == target:
            return []

        paths = []
        # BFS 队列: (当前节点, 路径节点列表, 边列表, 已访问集合)
        queue = [(source, [source], [], {source})]

        while queue:
            current, nodes, edges, visited = queue.pop(0)

            if len(nodes) > self.max_depth + 1:
                continue

            if current not in self.edges:
                continue

            for edge in self.edges[current]:
                next_node = edge.to_did

                if next_node == target:
                    # 找到路径
                    final_nodes = nodes + [next_node]
                    final_edges = edges + [edge]
                    derived = self._compute_derived_score(final_edges)
                    paths.append(TrustPath(
                        nodes=final_nodes,
                        edges=final_edges,
                        derived_score=derived,
                    ))
                elif next_node not in visited:
                    queue.append((
                        next_node,
                        nodes + [next_node],
                        edges + [edge],
                        visited | {next_node},
                    ))

        # 按衍生分数降序排列
        paths.sort(key=lambda p: p.derived_score, reverse=True)
        return paths

    def _compute_derived_score(self, edges: list[TrustEdge]) -> float:
        """
        计算多跳信任的衍生分数
        规则：每经过一跳衰减 decay_rate，最终分数 = 各边分数乘积 × 衰减因子
        """
        if not edges:
            return 0.0

        # 各边分数的几何平均
        product = 1.0
        for e in edges:
            product *= e.score

        # 衰减因子：每跳衰减
        decay = ((1.0 - self.decay_rate) ** (len(edges) - 1)) if len(edges) > 1 else 1.0

        return product * decay

    def compute_derived_trust(self, source: str, target: str) -> float:
        """
        计算 source 对 target 的衍生信任分
        返回所有路径中的最高分
        """
        paths = self.find_trust_paths(source, target)
        if not paths:
            return 0.0
        return paths[0].derived_score

    def apply_decay(self, decay_rate: float = 0.01, min_score: float = 0.1) -> None:
        """
        对所有边应用信任衰减（模拟长期无交互）
        每次调用将所有边的 score 乘以 (1 - decay_rate)
        最低不低于 min_score
        """
        for from_did in self.edges:
            for edge in self.edges[from_did]:
                new_score = edge.score * (1 - decay_rate)
                edge.score = max(min_score, new_score)

    def get_all_edges(self) -> list[TrustEdge]:
        """获取所有信任边"""
        result = []
        for edges in self.edges.values():
            result.extend(edges)
        return result


# ---------------------------------------------------------------------------
# 信任图存储（SQLite 持久化）
# ---------------------------------------------------------------------------

class TrustGraphStore:
    """
    信任图持久化存储

    使用 SQLite 存储信任边，支持：
      - CRUD 操作
      - 加载到内存图
      - 与 storage.py 集成
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path else None

    async def _get_db(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        if self.db_path:
            return await aiosqlite.connect(self.db_path)
        else:
            # 使用默认路径
            from agent_net.storage import DB_PATH
            return await aiosqlite.connect(DB_PATH)

    async def init_table(self, conn: Optional[aiosqlite.Connection] = None) -> None:
        """初始化表（由 storage.py 调用）"""
        if conn:
            await self._init_table(conn)
        else:
            async with await self._get_db() as conn:
                await self._init_table(conn)

    async def _init_table(self, conn: aiosqlite.Connection) -> None:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trust_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                score REAL NOT NULL,
                timestamp REAL NOT NULL,
                evidence TEXT,
                UNIQUE(from_did, to_did)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trust_edges_from
            ON trust_edges(from_did)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trust_edges_to
            ON trust_edges(to_did)
        """)
        await conn.commit()

    async def add_edge(self, edge: TrustEdge, conn: Optional[aiosqlite.Connection] = None) -> None:
        """添加信任边"""
        async def _add(c: aiosqlite.Connection):
            await c.execute(
                """
                INSERT OR REPLACE INTO trust_edges
                (from_did, to_did, score, timestamp, evidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    edge.from_did,
                    edge.to_did,
                    edge.score,
                    edge.timestamp,
                    edge.evidence,
                ),
            )
            await c.commit()

        if conn:
            await _add(conn)
        else:
            async with await self._get_db() as conn:
                await _add(conn)

    async def remove_edge(self, from_did: str, to_did: str, conn: Optional[aiosqlite.Connection] = None) -> bool:
        """移除信任边"""
        async def _remove(c: aiosqlite.Connection) -> bool:
            cursor = await c.execute(
                "DELETE FROM trust_edges WHERE from_did = ? AND to_did = ?",
                (from_did, to_did),
            )
            await c.commit()
            return cursor.rowcount > 0

        if conn:
            return await _remove(conn)
        else:
            async with await self._get_db() as conn:
                return await _remove(conn)

    async def get_edge(self, from_did: str, to_did: str, conn: Optional[aiosqlite.Connection] = None) -> Optional[TrustEdge]:
        """获取单条信任边"""
        async def _get(c: aiosqlite.Connection) -> Optional[TrustEdge]:
            cursor = await c.execute(
                "SELECT from_did, to_did, score, timestamp, evidence FROM trust_edges WHERE from_did = ? AND to_did = ?",
                (from_did, to_did),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return TrustEdge(
                from_did=row[0],
                to_did=row[1],
                score=row[2],
                timestamp=row[3],
                evidence=row[4],
            )

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as conn:
                return await _get(conn)

    async def get_outgoing_edges(self, from_did: str, conn: Optional[aiosqlite.Connection] = None) -> list[TrustEdge]:
        """获取从某个 DID 发出的所有信任边"""
        async def _get(c: aiosqlite.Connection) -> list[TrustEdge]:
            cursor = await c.execute(
                "SELECT from_did, to_did, score, timestamp, evidence FROM trust_edges WHERE from_did = ?",
                (from_did,),
            )
            rows = await cursor.fetchall()
            return [
                TrustEdge(
                    from_did=row[0],
                    to_did=row[1],
                    score=row[2],
                    timestamp=row[3],
                    evidence=row[4],
                )
                for row in rows
            ]

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as conn:
                return await _get(conn)

    async def get_incoming_edges(self, to_did: str, conn: Optional[aiosqlite.Connection] = None) -> list[TrustEdge]:
        """获取指向某个 DID 的所有信任边"""
        async def _get(c: aiosqlite.Connection) -> list[TrustEdge]:
            cursor = await c.execute(
                "SELECT from_did, to_did, score, timestamp, evidence FROM trust_edges WHERE to_did = ?",
                (to_did,),
            )
            rows = await cursor.fetchall()
            return [
                TrustEdge(
                    from_did=row[0],
                    to_did=row[1],
                    score=row[2],
                    timestamp=row[3],
                    evidence=row[4],
                )
                for row in rows
            ]

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as conn:
                return await _get(conn)

    async def get_all_edges(self, conn: Optional[aiosqlite.Connection] = None) -> list[TrustEdge]:
        """获取所有信任边"""
        async def _get(c: aiosqlite.Connection) -> list[TrustEdge]:
            cursor = await c.execute(
                "SELECT from_did, to_did, score, timestamp, evidence FROM trust_edges"
            )
            rows = await cursor.fetchall()
            return [
                TrustEdge(
                    from_did=row[0],
                    to_did=row[1],
                    score=row[2],
                    timestamp=row[3],
                    evidence=row[4],
                )
                for row in rows
            ]

        if conn:
            return await _get(conn)
        else:
            async with await self._get_db() as conn:
                return await _get(conn)

    async def load_graph(self, conn: Optional[aiosqlite.Connection] = None) -> TrustGraph:
        """从数据库加载完整信任图"""
        edges = await self.get_all_edges(conn)
        graph = TrustGraph()
        for edge in edges:
            graph.add_edge(edge)
        return graph

    async def apply_decay(
        self,
        decay_rate: float = 0.01,
        min_score: float = 0.1,
        conn: Optional[aiosqlite.Connection] = None,
    ) -> int:
        """
        对所有边应用衰减

        Returns:
            更新的边数
        """
        async def _apply(c: aiosqlite.Connection) -> int:
            # 获取所有边
            edges = await self.get_all_edges(c)

            updated = 0
            for edge in edges:
                new_score = max(min_score, edge.score * (1 - decay_rate))
                if abs(new_score - edge.score) > 0.0001:
                    edge.score = new_score
                    await self.add_edge(edge, c)
                    updated += 1

            return updated

        if conn:
            return await _apply(conn)
        else:
            async with await self._get_db() as conn:
                return await _apply(conn)
