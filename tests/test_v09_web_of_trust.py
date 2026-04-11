"""
v0.9.6 Web of Trust 信任传递测试套件
测试 ID: tr_wot_01 – tr_wot_08

覆盖场景：
  - A 信任 B，B 背书 C → A 对 C 有衍生信任分
  - 信任路径发现：给定两个 DID，找到信任链
  - 信任衰减：长期无交互 → trust_score 缓慢下降
  - 多跳信任传递
  - 信任环检测
  - 最大路径深度限制
"""
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 数据模型
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
# 信任图
# ---------------------------------------------------------------------------

class TrustGraph:
    """
    Web of Trust 图结构
    支持：
      - 添加/移除信任边
      - 查找信任路径（BFS）
      - 计算衍生信任分
      - 信任衰减
    """

    def __init__(self, max_depth: int = 4):
        """
        Args:
            max_depth: 最大信任传递深度（防止无限搜索）
        """
        self.max_depth = max_depth
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
        规则：每经过一跳衰减 15%，最终分数 = 各边分数乘积 × 衰减因子
        """
        if not edges:
            return 0.0

        # 各边分数的几何平均
        product = 1.0
        for e in edges:
            product *= e.score

        # 衰减因子：每跳衰减 15%
        decay = (0.85 ** (len(edges) - 1)) if len(edges) > 1 else 1.0

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


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_tr_wot_01_direct_trust():
    """直接信任：A 对 B 的信任边正确存储和查询"""
    graph = TrustGraph()
    edge = TrustEdge(
        from_did="did:agentnexus:zAgentA",
        to_did="did:agentnexus:zAgentB",
        score=0.9,
        timestamp=time.time(),
        evidence="cert_001",
    )
    graph.add_edge(edge)

    found = graph.get_direct_trust("did:agentnexus:zAgentA", "did:agentnexus:zAgentB")
    assert found is not None
    assert found.score == 0.9
    assert found.evidence == "cert_001"


def test_tr_wot_02_one_hop_derived_trust():
    """一跳传递：A 信任 B(0.9)，B 背书 C(0.8) → A 对 C 的衍生信任"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zC", 0.8, time.time(), None))

    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zC")
    assert len(paths) == 1
    assert paths[0].nodes == ["did:agentnexus:zA", "did:agentnexus:zB", "did:agentnexus:zC"]
    # 0.9 * 0.8 * 0.85 = 0.612
    assert abs(paths[0].derived_score - 0.612) < 0.01


def test_tr_wot_03_multi_hop_derived_trust():
    """多跳传递：A → B → C → D，分数逐级衰减"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zC", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zC", "did:agentnexus:zD", 1.0, time.time(), None))

    score = graph.compute_derived_trust("did:agentnexus:zA", "did:agentnexus:zD")
    # 1.0 * 1.0 * 1.0 * 0.85^2 = 0.7225
    assert abs(score - 0.7225) < 0.01


def test_tr_wot_04_multiple_paths():
    """多条路径：选择最高分路径"""
    graph = TrustGraph()
    # 路径 1: A → B → D (高分路径)
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zD", 0.9, time.time(), None))
    # 路径 2: A → C → D (低分路径)
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zC", 0.5, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zC", "did:agentnexus:zD", 0.5, time.time(), None))

    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zD")
    assert len(paths) >= 2

    # 最高分路径应排第一
    best = paths[0]
    # 0.9 * 0.9 * 0.85 = 0.6885
    assert abs(best.derived_score - 0.6885) < 0.01


def test_tr_wot_05_no_path():
    """无信任路径时返回空列表"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))

    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zX")
    assert paths == []

    # 反向也无路径
    paths = graph.find_trust_paths("did:agentnexus:zB", "did:agentnexus:zA")
    assert paths == []


def test_tr_wot_06_trust_decay():
    """信任衰减：长期无交互，分数缓慢下降"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 1.0, time.time(), None))

    # 模拟 10 次衰减（每次 1%）
    for _ in range(10):
        graph.apply_decay(decay_rate=0.01, min_score=0.1)

    edge = graph.get_direct_trust("did:agentnexus:zA", "did:agentnexus:zB")
    # 1.0 * 0.99^10 ≈ 0.904
    assert abs(edge.score - 0.904) < 0.01


def test_tr_wot_07_max_depth_limit():
    """最大深度限制：超过 max_depth 的路径被忽略"""
    graph = TrustGraph(max_depth=3)
    # 构建 5 跳路径
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zC", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zC", "did:agentnexus:zD", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zD", "did:agentnexus:zE", 1.0, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zE", "did:agentnexus:zF", 1.0, time.time(), None))

    # 只能找到 A → B → C → D（3 跳，深度=3）
    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zD")
    assert len(paths) == 1
    assert paths[0].nodes == ["did:agentnexus:zA", "did:agentnexus:zB", "did:agentnexus:zC", "did:agentnexus:zD"]

    # 超过深度的路径不应返回
    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zF")
    assert paths == []


def test_tr_wot_08_cycle_detection():
    """信任环检测：A → B → C → A，不会无限循环"""
    graph = TrustGraph()
    # 创建环：A → B → C → A
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zC", 0.8, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zC", "did:agentnexus:zA", 0.7, time.time(), None))

    # 查找 A → A 的路径（应返回空，因为起点等于终点）
    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zA")
    assert paths == []

    # A → C 仍能找到路径
    paths = graph.find_trust_paths("did:agentnexus:zA", "did:agentnexus:zC")
    assert len(paths) == 1
    assert paths[0].nodes == ["did:agentnexus:zA", "did:agentnexus:zB", "did:agentnexus:zC"]


# ---------------------------------------------------------------------------
# 集成测试：与 RuntimeVerifier 结合
# ---------------------------------------------------------------------------

def test_tr_wot_09_derived_trust_in_verification():
    """衍生信任分纳入 trust_score 计算"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))
    graph.add_edge(TrustEdge("did:agentnexus:zB", "did:agentnexus:zC", 0.8, time.time(), None))

    derived = graph.compute_derived_trust("did:agentnexus:zA", "did:agentnexus:zC")
    # 0.9 * 0.8 * 0.85 = 0.612
    assert abs(derived - 0.612) < 0.01

    # 可用于 trust_score 加成（behavior_delta）
    # 示例：trust_score = base_score + derived * behavior_weight
    base_score = 0.15  # L1
    behavior_weight = 0.3
    trust_score = base_score + derived * behavior_weight
    # 0.15 + 0.612 * 0.3 = 0.3336
    assert abs(trust_score - 0.3336) < 0.01


def test_tr_wot_10_edge_update():
    """更新已存在的信任边"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.5, time.time(), None))

    # 更新
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), "new_cert"))

    # 应只有一条边
    assert len(graph.edges["did:agentnexus:zA"]) == 1

    edge = graph.get_direct_trust("did:agentnexus:zA", "did:agentnexus:zB")
    assert edge.score == 0.9
    assert edge.evidence == "new_cert"


def test_tr_wot_11_edge_removal():
    """移除信任边"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.9, time.time(), None))

    removed = graph.remove_edge("did:agentnexus:zA", "did:agentnexus:zB")
    assert removed is True

    edge = graph.get_direct_trust("did:agentnexus:zA", "did:agentnexus:zB")
    assert edge is None

    # 移除不存在的边
    removed = graph.remove_edge("did:agentnexus:zA", "did:agentnexus:zX")
    assert removed is False


def test_tr_wot_12_decay_with_min_score():
    """衰减有下限保护"""
    graph = TrustGraph()
    graph.add_edge(TrustEdge("did:agentnexus:zA", "did:agentnexus:zB", 0.2, time.time(), None))

    # 大量衰减
    for _ in range(100):
        graph.apply_decay(decay_rate=0.1, min_score=0.1)

    edge = graph.get_direct_trust("did:agentnexus:zA", "did:agentnexus:zB")
    # 不低于 min_score
    assert edge.score == 0.1
