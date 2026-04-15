"""Governance & Trust Endpoints (ADR-014)"""
import os
import time

from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import _require_token
from agent_net.node._models import GovernanceValidateRequest, TrustEdgeRequest, InteractionRequest
from agent_net.storage import (
    get_agent,
    add_trust_edge, list_trust_edges_from, remove_trust_edge,
    record_interaction, get_interactions,
    save_governance_attestation, get_all_governance_attestations,
    save_capability_token, get_capability_token, list_capability_tokens_by_did,
    revoke_capability_token, get_delegation_chain, is_token_revoked,
    get_private_key,
)

router = APIRouter()

_governance_registry = None


def _get_governance_registry():
    global _governance_registry
    if _governance_registry is None:
        from agent_net.common.governance import create_default_registry
        moltrust_key = os.environ.get("MOLTRUST_API_KEY", "")
        _governance_registry = create_default_registry(moltrust_key)
    return _governance_registry


def set_governance_registry(registry) -> None:
    """设置治理服务注册表（供测试注入）"""
    global _governance_registry
    _governance_registry = registry


def reset_governance_registry() -> None:
    """重置治理服务注册表（供测试隔离）"""
    global _governance_registry
    _governance_registry = None


@router.post("/governance/validate")
async def api_governance_validate(req: GovernanceValidateRequest):
    from agent_net.common.governance import CapabilityRequest
    registry = _get_governance_registry()
    requested = [CapabilityRequest(**c) for c in req.requested_capabilities]
    results = await registry.validate_capabilities(
        agent_did=req.agent_did, requested=requested,
        context=req.context, clients=req.clients,
    )
    best = registry.get_highest_trust(results)
    for name, att in results.items():
        if att.expires_at:
            try:
                from datetime import datetime
                expires_ts = datetime.fromisoformat(att.expires_at.replace("Z", "+00:00")).timestamp()
                await save_governance_attestation(
                    agent_did=req.agent_did, issuer=name,
                    attestation=att.to_dict(), expires_at=expires_ts,
                )
            except Exception:
                pass
    return {
        "status": "ok",
        "agent_did": req.agent_did,
        "best_decision": best.decision,
        "best_trust_score": best.trust_score,
        "best_passport_grade": best.passport_grade,
        "results": {name: att.to_dict() for name, att in results.items()},
    }


@router.get("/governance/attestations/{did}")
async def api_get_governance_attestations(did: str):
    attestations = await get_all_governance_attestations(did)
    return {"status": "ok", "agent_did": did, "attestations": attestations}


@router.get("/trust/paths")
async def api_find_trust_paths(source: str, target: str, max_depth: int = 4):
    from agent_net.common.trust_graph import TrustGraphStore
    store = TrustGraphStore()
    graph = await store.load_graph()
    original_max_depth = graph.max_depth
    graph.max_depth = max_depth
    paths = graph.find_trust_paths(source, target)
    graph.max_depth = original_max_depth
    return {
        "status": "ok",
        "source": source, "target": target,
        "paths_found": len(paths),
        "paths": [p.to_dict() for p in paths[:10]],
    }


@router.post("/trust/edge")
async def api_add_trust_edge(req: TrustEdgeRequest, _=Depends(_require_token)):
    if req.score < 0 or req.score > 1:
        raise HTTPException(400, "score must be between 0 and 1")

    local_agent = await get_agent(req.from_did)
    if not local_agent:
        if not req.signature:
            raise HTTPException(403, "from_did is not a local agent. Signature required.")
        try:
            from agent_net.common.crypto import VerifyKey
            from agent_net.common.did import decode_multibase_pubkey
            import json
            if req.from_did.startswith("did:agentnexus:"):
                pubkey_multibase = req.from_did.split(":")[-1]
                pubkey_bytes = decode_multibase_pubkey(pubkey_multibase)
                verify_key = VerifyKey(pubkey_bytes)
                message = json.dumps(
                    {"from_did": req.from_did, "to_did": req.to_did, "score": req.score},
                    sort_keys=True,
                )
                verify_key.verify(message.encode(), bytes.fromhex(req.signature))
            else:
                raise HTTPException(400, "Unsupported DID method for signature verification")
        except Exception as e:
            raise HTTPException(403, f"Signature verification failed: {e}")

    await add_trust_edge(
        from_did=req.from_did, to_did=req.to_did,
        score=req.score, evidence=req.evidence,
    )
    return {"status": "ok", "from_did": req.from_did, "to_did": req.to_did, "score": req.score}


@router.get("/trust/edges/{did}")
async def api_list_trust_edges(did: str):
    edges = await list_trust_edges_from(did)
    return {"status": "ok", "from_did": did, "edges": edges}


@router.delete("/trust/edge")
async def api_remove_trust_edge(from_did: str, to_did: str, _=Depends(_require_token)):
    """删除信任边（需要鉴权，验证 from_did 归属）"""
    # 验证 from_did 是本地注册的 Agent
    local_agent = await get_agent(from_did)
    if not local_agent:
        raise HTTPException(403, "from_did is not a local agent. Cannot delete trust edges for remote agents.")
    removed = await remove_trust_edge(from_did, to_did)
    if not removed:
        raise HTTPException(404, "Trust edge not found")
    return {"status": "ok"}


@router.post("/interactions")
async def api_record_interaction(req: InteractionRequest, _=Depends(_require_token)):
    """记录交互（需要鉴权，验证 from_did 是本地 Agent）"""
    # 验证 from_did 是本地注册的 Agent
    local_agent = await get_agent(req.from_did)
    if not local_agent:
        raise HTTPException(403, "from_did is not a local agent. Cannot record interactions for remote agents.")
    interaction_id = await record_interaction(
        from_did=req.from_did, to_did=req.to_did,
        interaction_type=req.interaction_type, success=req.success,
        response_time_ms=req.response_time_ms,
    )
    return {"status": "ok", "interaction_id": interaction_id}


@router.get("/interactions/{did}")
async def api_get_interactions(did: str, time_window_days: int = 30):
    interactions = await get_interactions(did, time_window_days)
    return {"status": "ok", "agent_did": did, "time_window_days": time_window_days, "interactions": interactions}


@router.get("/reputation/{did}")
async def api_get_reputation(did: str):
    """
    获取声誉评分

    trust_level 从 Agent 的实际 L 级推导（S7 修复）
    """
    from agent_net.common.reputation import ReputationStore
    from agent_net.common.runtime_verifier import AgentNexusRuntimeVerifier
    from agent_net.common.did import DIDResolver

    store = ReputationStore()

    # 获取 Agent 的实际 L 级
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {did}")

    # 使用 RuntimeVerifier 计算实际 L 级（无 trusted_cas 时基于 DID）
    verifier = AgentNexusRuntimeVerifier(resolver=DIDResolver())
    result = await verifier.verify(did, agent.get("public_key", ""))
    trust_level = result.trust_level

    attestations = await get_all_governance_attestations(did)
    attestation_bonus = min(15.0, sum(
        att.get("attestation", {}).get("trust_score", 0) * 0.1
        for att in attestations
    ))
    rep = await store.compute_reputation(
        agent_did=did, trust_level=trust_level, attestation_bonus=attestation_bonus,
    )
    return {
        "status": "ok",
        "trust_level": trust_level,
        "reputation": rep.to_dict(),
        "oatr_format": rep.to_oatr_format()
    }


@router.get("/trust-snapshot/{did}")
async def api_trust_snapshot(did: str):
    """导出 OATR 格式的信任快照"""
    from agent_net.common.reputation import ReputationStore
    from agent_net.common.runtime_verifier import AgentNexusRuntimeVerifier
    from agent_net.common.did import DIDResolver

    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {did}")

    verifier = AgentNexusRuntimeVerifier(resolver=DIDResolver())
    result = await verifier.verify(did, agent.get("public_key", ""))
    trust_level = result.trust_level

    attestations = await get_all_governance_attestations(did)
    attestation_bonus = min(15.0, sum(
        att.get("attestation", {}).get("trust_score", 0) * 0.1
        for att in attestations
    ))
    store = ReputationStore()
    rep = await store.compute_reputation(
        agent_did=did, trust_level=trust_level, attestation_bonus=attestation_bonus,
    )
    return rep.to_oatr_format()


@router.post("/attestations/verify")
async def api_verify_attestation(request: dict):
    """验证外部 governance attestation 的 JWS 签名"""
    from agent_net.common.governance import GovernanceAttestation

    jws = request.get("jwt", "") or request.get("jws", "")
    if not jws:
        return {"valid": False, "error": "missing jwt/jws field"}

    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer=request.get("issuer", ""),
        subject=request.get("agent_did", ""),
        decision="permit",
        jws=jws,
        expires_at=request.get("expires_at"),
    )
    registry = _get_governance_registry()
    try:
        valid = await registry.verify_attestation(att)
        return {"valid": valid, "agent_did": request.get("agent_did", "")}
    except Exception as e:
        return {"valid": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Capability Token 端点 — v1.0-08
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/capability-tokens/issue")
async def api_issue_token(req: dict, _=Depends(_require_token)):
    """
    签发 Capability Token。

    请求体：
    {
        "issuer_did": "did:agentnexus:...",
        "subject_did": "did:agentnexus:...",
        "enclave_id": "enc_..." (可选),
        "scope": {"permissions": [...], "role": "..."},
        "constraints": {"spend_limit": 100, "max_delegation_depth": 1, ...},
        "validity_days": 30,
        "parent_token_id": "ct_..." (可选，委托链)
    }
    """
    issuer_did = req.get("issuer_did")
    subject_did = req.get("subject_did")
    if not issuer_did or not subject_did:
        raise HTTPException(400, "Missing issuer_did or subject_did")

    # 验证 issuer 存在且有私钥
    issuer_pk = await get_private_key(issuer_did)
    if not issuer_pk:
        raise HTTPException(404, "Issuer not found or no private key")

    from agent_net.common.capability_token import (
        issue_token, sign_token, compute_constraint_hash,
    )

    # 获取父 Token 信息（如果有）
    parent_token_id = req.get("parent_token_id")
    parent_scope_hash = None
    if parent_token_id:
        parent = await get_capability_token(parent_token_id)
        if not parent:
            raise HTTPException(404, "Parent token not found")
        parent_scope_hash = compute_constraint_hash(parent["scope"], parent["constraints"])

    # 签发 Token
    token = await issue_token(
        issuer_did=issuer_did,
        subject_did=subject_did,
        enclave_id=req.get("enclave_id"),
        scope=req.get("scope"),
        constraints=req.get("constraints"),
        validity_days=req.get("validity_days", 30),
        max_delegation_depth=req.get("constraints", {}).get("max_delegation_depth", 1),
        parent_token_id=parent_token_id,
        parent_scope_hash=parent_scope_hash,
    )

    # 签名
    signed_token = sign_token(token, issuer_pk)

    # 保存
    token_dict = signed_token.to_dict()
    await save_capability_token(token_dict)

    return {"status": "ok", "token": token_dict}


@router.get("/capability-tokens/{token_id}")
async def api_get_token(token_id: str):
    """
    查询 Capability Token。
    """
    token = await get_capability_token(token_id)
    if not token:
        raise HTTPException(404, "Token not found")
    return token


@router.post("/capability-tokens/{token_id}/verify")
async def api_verify_token(token_id: str, req: dict):
    """
    验证 Capability Token。

    请求体：{"action": "vault:read"}
    返回：{valid: bool, reason: str}
    """
    token = await get_capability_token(token_id)
    if not token:
        raise HTTPException(404, "Token not found")

    action = req.get("action", "")
    if not action:
        raise HTTPException(400, "Missing action")

    from agent_net.common.capability_token import CapabilityToken, verify_token

    # 转换为 CapabilityToken 对象
    ct = CapabilityToken(
        token_id=token["token_id"],
        version=token["version"],
        issuer_did=token["issuer_did"],
        subject_did=token["subject_did"],
        enclave_id=token["enclave_id"],
        scope=token["scope"],
        constraints=token["constraints"],
        validity=token["validity"],
        revocation_endpoint=token["revocation_endpoint"],
        evaluated_constraint_hash=token["evaluated_constraint_hash"],
        signature=token["signature"],
        status=token["status"],
        created_at=token["created_at"],
        revoked_at=token.get("revoked_at"),
    )
    ct._parent_token_id = token.get("_parent_token_id")
    ct._parent_scope_hash = token.get("_parent_scope_hash")

    result = await verify_token(
        ct, action,
        get_token_func=get_capability_token,
        get_delegation_chain_func=get_delegation_chain,
        is_revoked_func=is_token_revoked,
    )
    return result


@router.post("/capability-tokens/{token_id}/revoke")
async def api_revoke_token(token_id: str, _=Depends(_require_token)):
    """
    撤销 Capability Token。
    """
    success = await revoke_capability_token(token_id)
    if not success:
        raise HTTPException(404, "Token not found or already revoked")
    return {"status": "ok", "token_id": token_id, "revoked_at": time.time()}


@router.get("/capability-tokens/by-did/{did}")
async def api_list_tokens_by_did(did: str, status: str = "active"):
    """
    查询某 DID 持有的所有 Token。
    """
    tokens = await list_capability_tokens_by_did(did, status)
    return {"did": did, "tokens": tokens, "count": len(tokens)}
