"""
v0.9.0 Output Provenance 测试套件
测试 ID: tr_prov_01 – tr_prov_08

覆盖场景：
  - trust_context 头部格式
  - 来源分级 T1~T5 定义
  - evidence_chain 结构
  - overall_confidence 计算
  - Relay 统计 Agent 产生的 T1~T5 比例
  - Profile 中的可靠性权重沉淀
  - 消息携带 trust_context 的端到端流程
"""
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Optional

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 数据模型（v0.9 新增）
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """证据链条目"""
    type: str                    # "database" / "url" / "model_inference" / "agent_report"
    source: str                  # 数据源 DID 或 URL
    confidence: float            # 0.0 - 1.0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class TrustContext:
    """
    v0.9 消息信任上下文（trust_context 头部）

    来源分级：
      T1: 原始事实（数据库查询、官方文件、链上数据）
      T2: 经验证的二手信息（已验签的 Agent 转述）
      T3: 聚合推理（多源综合，有部分推理）
      T4: 单源推理（基于单一模型输出）
      T5: 纯模型推理（无外部验证，幻觉风险最高）
    """
    source_tier: str              # "T1" / "T2" / "T3" / "T4" / "T5"
    evidence_chain: list[EvidenceItem]
    overall_confidence: float     # 0.0 - 1.0

    def to_dict(self) -> dict:
        return {
            "source_tier": self.source_tier,
            "evidence_chain": [e.to_dict() for e in self.evidence_chain],
            "overall_confidence": round(self.overall_confidence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrustContext":
        return cls(
            source_tier=d["source_tier"],
            evidence_chain=[
                EvidenceItem(**e) for e in d.get("evidence_chain", [])
            ],
            overall_confidence=d.get("overall_confidence", 0.0),
        )


# ---------------------------------------------------------------------------
# 置信度计算函数
# ---------------------------------------------------------------------------

def calculate_overall_confidence(evidence_chain: list[EvidenceItem]) -> float:
    """
    根据证据链计算综合置信度。
    规则：加权平均，权重由证据类型决定。
    """
    if not evidence_chain:
        return 0.0

    type_weights = {
        "database": 1.0,
        "url": 0.8,
        "agent_report": 0.7,
        "model_inference": 0.5,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for item in evidence_chain:
        w = type_weights.get(item.type, 0.5)
        total_weight += w
        weighted_sum += w * item.confidence

    if total_weight == 0:
        return 0.0
    return min(1.0, weighted_sum / total_weight)


def determine_source_tier(evidence_chain: list[EvidenceItem]) -> str:
    """
    根据证据链判定来源分级。
    规则：
      - 全为 database/url 且高置信度 → T1
      - 有 agent_report 转述 → T2
      - 多源混合 + 部分推理 → T3
      - 单一 model_inference → T4
      - 无证据或纯 model_inference 低置信度 → T5
    """
    if not evidence_chain:
        return "T5"

    has_db = any(e.type == "database" for e in evidence_chain)
    has_url = any(e.type == "url" for e in evidence_chain)
    has_agent = any(e.type == "agent_report" for e in evidence_chain)
    has_model = any(e.type == "model_inference" for e in evidence_chain)

    model_ratio = sum(1 for e in evidence_chain if e.type == "model_inference") / len(evidence_chain)

    # T1: 原始事实
    if (has_db or has_url) and not has_model and not has_agent:
        avg_conf = sum(e.confidence for e in evidence_chain) / len(evidence_chain)
        if avg_conf >= 0.9:
            return "T1"

    # T2: 验证过的二手信息
    if has_agent and not has_model:
        return "T2"

    # T3: 多源混合
    if len(evidence_chain) >= 2 and has_model and (has_db or has_url or has_agent):
        return "T3"

    # T4: 单源推理
    if model_ratio >= 0.5 and len(evidence_chain) == 1:
        return "T4"

    # T5: 纯模型推理高风险
    if model_ratio >= 0.8:
        return "T5"

    # 默认 T3
    return "T3"


# ---------------------------------------------------------------------------
# 可靠性权重统计
# ---------------------------------------------------------------------------

@dataclass
class ProvenanceStats:
    """Agent 的 Provenance 统计"""
    t1_count: int = 0
    t2_count: int = 0
    t3_count: int = 0
    t4_count: int = 0
    t5_count: int = 0

    def record(self, tier: str) -> None:
        """记录一条消息的来源分级"""
        if tier == "T1":
            self.t1_count += 1
        elif tier == "T2":
            self.t2_count += 1
        elif tier == "T3":
            self.t3_count += 1
        elif tier == "T4":
            self.t4_count += 1
        elif tier == "T5":
            self.t5_count += 1

    def total(self) -> int:
        return self.t1_count + self.t2_count + self.t3_count + self.t4_count + self.t5_count

    def reliability_weight(self) -> float:
        """
        可靠性权重（0.0 - 1.0）
        公式：加权平均，T1=1.0, T2=0.8, T3=0.6, T4=0.4, T5=0.2
        """
        total = self.total()
        if total == 0:
            return 0.5  # 无历史数据，中性权重

        weights = {
            "T1": 1.0,
            "T2": 0.8,
            "T3": 0.6,
            "T4": 0.4,
            "T5": 0.2,
        }
        weighted_sum = (
            self.t1_count * weights["T1"] +
            self.t2_count * weights["T2"] +
            self.t3_count * weights["T3"] +
            self.t4_count * weights["T4"] +
            self.t5_count * weights["T5"]
        )
        return round(weighted_sum / total, 4)

    def to_dict(self) -> dict:
        return {
            "t1_count": self.t1_count,
            "t2_count": self.t2_count,
            "t3_count": self.t3_count,
            "t4_count": self.t4_count,
            "t5_count": self.t5_count,
            "total": self.total(),
            "reliability_weight": self.reliability_weight(),
        }


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_tr_prov_01_trust_context_format():
    """trust_context 头部格式正确，可序列化/反序列化"""
    ctx = TrustContext(
        source_tier="T2",
        evidence_chain=[
            EvidenceItem(type="database", source="did:agentnexus:zDictService", confidence=0.95),
            EvidenceItem(type="model_inference", source="gpt-4", confidence=0.7),
        ],
        overall_confidence=0.82,
    )

    d = ctx.to_dict()
    assert d["source_tier"] == "T2"
    assert len(d["evidence_chain"]) == 2
    assert d["evidence_chain"][0]["type"] == "database"
    assert d["overall_confidence"] == 0.82

    # 可 JSON 序列化
    json_str = json.dumps(d)
    recovered = TrustContext.from_dict(json.loads(json_str))
    assert recovered.source_tier == ctx.source_tier
    assert len(recovered.evidence_chain) == len(ctx.evidence_chain)


def test_tr_prov_02_source_tier_t1():
    """T1: 数据库查询 + 高置信度 → 原始事实"""
    chain = [
        EvidenceItem(type="database", source="did:agentnexus:zChainData", confidence=0.98),
        EvidenceItem(type="url", source="https://official.api/data", confidence=0.95),
    ]
    tier = determine_source_tier(chain)
    assert tier == "T1"


def test_tr_prov_03_source_tier_t2():
    """T2: Agent 转述 → 验证过的二手信息"""
    chain = [
        EvidenceItem(type="agent_report", source="did:agentnexus:zTrustedAgent", confidence=0.9),
    ]
    tier = determine_source_tier(chain)
    assert tier == "T2"


def test_tr_prov_04_source_tier_t3():
    """T3: 多源混合 + 部分推理"""
    chain = [
        EvidenceItem(type="database", source="did:agentnexus:zData", confidence=0.9),
        EvidenceItem(type="model_inference", source="gpt-4", confidence=0.7),
    ]
    tier = determine_source_tier(chain)
    assert tier == "T3"


def test_tr_prov_05_source_tier_t4():
    """T4: 单一模型推理"""
    chain = [
        EvidenceItem(type="model_inference", source="gpt-4", confidence=0.6),
    ]
    tier = determine_source_tier(chain)
    assert tier == "T4"


def test_tr_prov_06_source_tier_t5():
    """T5: 纯模型推理高风险"""
    chain = [
        EvidenceItem(type="model_inference", source="gpt-4", confidence=0.5),
        EvidenceItem(type="model_inference", source="claude", confidence=0.4),
    ]
    tier = determine_source_tier(chain)
    assert tier == "T5"


def test_tr_prov_07_overall_confidence():
    """overall_confidence 加权计算正确"""
    chain = [
        EvidenceItem(type="database", source="db1", confidence=1.0),      # weight=1.0
        EvidenceItem(type="model_inference", source="gpt-4", confidence=0.8),  # weight=0.5
    ]
    conf = calculate_overall_confidence(chain)
    # (1.0 * 1.0 + 0.5 * 0.8) / 1.5 = 1.4 / 1.5 ≈ 0.933
    assert abs(conf - 0.9333) < 0.01


def test_tr_prov_08_reliability_weight():
    """ProvenanceStats 可靠性权重计算正确"""
    stats = ProvenanceStats()
    stats.record("T1")
    stats.record("T1")
    stats.record("T2")
    stats.record("T5")

    # (2*1.0 + 1*0.8 + 1*0.2) / 4 = 3.0 / 4 = 0.75
    assert stats.reliability_weight() == 0.75
    assert stats.total() == 4

    # 可序列化
    d = stats.to_dict()
    assert d["t1_count"] == 2
    assert d["reliability_weight"] == 0.75


# ---------------------------------------------------------------------------
# 集成测试：消息携带 trust_context
# ---------------------------------------------------------------------------

def test_tr_prov_09_message_with_trust_context():
    """消息携带 trust_context 头部的端到端格式"""
    ctx = TrustContext(
        source_tier="T2",
        evidence_chain=[
            EvidenceItem(type="database", source="did:agentnexus:zDictService", confidence=0.95),
        ],
        overall_confidence=0.95,
    )

    message = {
        "from_did": "did:agentnexus:zAgentA",
        "to_did": "did:agentnexus:zAgentB",
        "content": "翻译结果：Hello World",
        "trust_context": ctx.to_dict(),
    }

    # 验证格式
    assert "trust_context" in message
    tc = message["trust_context"]
    assert tc["source_tier"] == "T2"
    assert len(tc["evidence_chain"]) == 1

    # 可 JSON 序列化（传输）
    json_str = json.dumps(message)
    recovered = json.loads(json_str)
    assert recovered["trust_context"]["source_tier"] == "T2"


def test_tr_prov_10_empty_evidence_chain():
    """空证据链 → T5，confidence=0"""
    ctx = TrustContext(
        source_tier=determine_source_tier([]),
        evidence_chain=[],
        overall_confidence=calculate_overall_confidence([]),
    )

    assert ctx.source_tier == "T5"
    assert ctx.overall_confidence == 0.0


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------

def test_tr_prov_11_mixed_evidence_tier():
    """混合证据（DB + Agent + Model）→ T3"""
    chain = [
        EvidenceItem(type="database", source="db1", confidence=0.95),
        EvidenceItem(type="agent_report", source="did:agentnexus:zAgent", confidence=0.85),
        EvidenceItem(type="model_inference", source="gpt-4", confidence=0.7),
    ]
    tier = determine_source_tier(chain)
    # 多源混合 + model → T3
    assert tier == "T3"


def test_tr_prov_12_confidence_edge_cases():
    """置信度边界值处理"""
    # 单条证据
    chain = [EvidenceItem(type="database", source="db", confidence=1.0)]
    assert calculate_overall_confidence(chain) == 1.0

    # 零置信度
    chain = [EvidenceItem(type="database", source="db", confidence=0.0)]
    assert calculate_overall_confidence(chain) == 0.0

    # 超高置信度被截断到 1.0
    chain = [
        EvidenceItem(type="database", source="db", confidence=1.0),
        EvidenceItem(type="database", source="db2", confidence=1.0),
    ]
    assert calculate_overall_confidence(chain) == 1.0
