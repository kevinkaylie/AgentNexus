"""Governance & Trust Endpoints (ADR-014)"""
import os

from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import _require_token
from agent_net.node._models import GovernanceValidateRequest, TrustEdgeRequest, InteractionRequest
from agent_net.storage import (
    get_agent,
    add_trust_edge, list_trust_edges_from, remove_trust_edge,
    record_interaction, get_interactions,
    save_governance_attestation, get_all_governance_attestations,
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
async def api_remove_trust_edge(from_did: str, to_did: str):
    removed = await remove_trust_edge(from_did, to_did)
    if not removed:
        raise HTTPException(404, "Trust edge not found")
    return {"status": "ok"}


@router.post("/interactions")
async def api_record_interaction(req: InteractionRequest):
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
async def api_get_reputation(did: str, trust_level: int = 1):
    from agent_net.common.reputation import ReputationStore
    store = ReputationStore()
    attestations = await get_all_governance_attestations(did)
    attestation_bonus = min(15.0, sum(
        att.get("attestation", {}).get("trust_score", 0) * 0.1
        for att in attestations
    ))
    rep = await store.compute_reputation(
        agent_did=did, trust_level=trust_level, attestation_bonus=attestation_bonus,
    )
    return {"status": "ok", "reputation": rep.to_dict(), "oatr_format": rep.to_oatr_format()}
