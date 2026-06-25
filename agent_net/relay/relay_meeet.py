import json
import os
import time
from typing import Optional

import aiohttp
from fastapi import HTTPException
from pydantic import BaseModel

from agent_net.common import crypto
from agent_net.common.did_methods.utils import compute_x402_score

from . import server_common as _common
from .server_common import _DIR_PREFIX, app

# ═══════════════════════════════════════════════════════════════
# MEEET Bridge API (ADR-008)
# ═══════════════════════════════════════════════════════════════

# Key schema:
#   meeet:admins              → Redis SET of admin pubkey hex
#   meeet:mapping:{did:meeet} → JSON, TTL=86400 (24h)

_MEEET_ADMINS_KEY = "meeet:admins"
_MEEET_MAPPING_PREFIX = "meeet:mapping:"
_MEEET_TTL = 86400  # 24 hours

# Mock Solana RPC URL (Q7 答疑：先用 Mock 实现)
MEEET_SOLANA_RPC_URL = os.environ.get("MEEET_SOLANA_RPC_URL", "http://localhost:9999/mock-solana")


class MeeetAdminRegisterRequest(BaseModel):
    """平台管理员注册请求"""
    admin_pubkey: str  # Ed25519 verify key, hex
    signature: str     # 用 Relay identity key 签名
    timestamp: float
    name: Optional[str] = None


class MeeetRegisterRequest(BaseModel):
    """单个 MEEET Agent 注册请求"""
    meeet_did: str      # did:meeet:agent_xxx
    pubkey: str         # Ed25519 verify key, hex
    reputation: int     # MEEET reputation score
    nonce: str          # 随机 nonce
    signature: str      # Agent 用自己私钥签名 nonce


class MeeetBatchRegisterRequest(BaseModel):
    """批量 MEEET Agent 注册请求"""
    admin_pubkey: str   # 平台管理员公钥
    admin_signature: str  # 管理员签名整个请求
    admin_timestamp: float
    agents: list[dict]  # [{meeet_did, pubkey, reputation, nonce, signature}, ...]


class MeeetStatusResponse(BaseModel):
    mapping_count: int
    admin_count: int
    last_updated: Optional[float]


# ── 平台管理员注册 ────────────────────────────────────────────

@app.post("/meeet/admin/register")
async def meeet_admin_register(req: MeeetAdminRegisterRequest):
    """
    注册 MEEET 平台管理员密钥。

    安全机制（ADR-012 评审修复）：
    1. 首次注册：必须用 Relay 自身签名密钥签名（Bootstrap）
    2. 后续注册：必须用已注册的 admin 密钥签名
    """
    # 验证时间戳（防重放）
    if abs(time.time() - req.timestamp) > 300:  # 5分钟窗口
        raise HTTPException(status_code=400, detail="Timestamp expired")

    # 构建签名消息
    message = f"meeet-admin-register:{req.admin_pubkey}:{req.timestamp}"

    # 获取已注册的管理员列表
    existing_admins = await _common._redis.smembers(_MEEET_ADMINS_KEY)

    try:
        from nacl.signing import VerifyKey
        sig_bytes = bytes.fromhex(req.signature)

        if not existing_admins:
            # Bootstrap 模式：首次注册，必须用 Relay 私钥签名
            relay_vk = _common._relay_signing_key.verify_key
            relay_vk.verify(message.encode(), sig_bytes)
        else:
            # 正常模式：必须用已注册的 admin 密钥签名
            # 验证签名来自已注册的 admin
            verified = False
            for admin_pk in existing_admins:
                try:
                    admin_vk = VerifyKey(bytes.fromhex(admin_pk))
                    admin_vk.verify(message.encode(), sig_bytes)
                    verified = True
                    break
                except Exception:
                    continue

            if not verified:
                raise HTTPException(
                    status_code=401,
                    detail="Signature must be from a registered admin"
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid admin signature: {e}")

    # 写入管理员列表
    await _common._redis.sadd(_MEEET_ADMINS_KEY, req.admin_pubkey)

    return {"status": "ok", "admin_pubkey": req.admin_pubkey[:16] + "..."}


@app.get("/meeet/admin/status")
async def meeet_admin_status():
    """查询已注册的管理员列表（仅返回公钥指纹）"""
    admins = await _common._redis.smembers(_MEEET_ADMINS_KEY)
    fingerprints = [f"{pk[:8]}...{pk[-8:]}" for pk in admins]
    return {
        "admin_count": len(admins),
        "admin_fingerprints": fingerprints,
    }


# ── MEEET Agent 注册 ────────────────────────────────────────────


def _pubkey_to_agentnexus_did(pubkey_hex: str) -> str:
    """从 Ed25519 公钥推导 did:agentnexus"""
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    multikey = crypto.encode_multikey_ed25519(pubkey_bytes)
    return f"did:agentnexus:{multikey}"


async def _verify_agent_signature(pubkey_hex: str, nonce: str, signature: str) -> bool:
    """验证 Agent 签名"""
    try:
        from nacl.signing import VerifyKey
        vk = VerifyKey(bytes.fromhex(pubkey_hex))
        sig_bytes = bytes.fromhex(signature)
        vk.verify(nonce.encode(), sig_bytes)
        return True
    except Exception:
        return False


@app.post("/meeet/register")
async def meeet_register(req: MeeetRegisterRequest):
    """
    单个 MEEET Agent 注册（Agent 自签名即可）。
    """
    # 验证签名
    if not await _verify_agent_signature(req.pubkey, req.nonce, req.signature):
        raise HTTPException(status_code=401, detail="Invalid agent signature")

    # 推导 did:agentnexus
    agentnexus_did = _pubkey_to_agentnexus_did(req.pubkey)
    x402_score = compute_x402_score(req.reputation)

    # 写入映射表
    mapping_key = f"{_MEEET_MAPPING_PREFIX}{req.meeet_did}"
    mapping_data = {
        "agentnexus_did": agentnexus_did,
        "pubkey_hex": req.pubkey,
        "meeet_reputation": req.reputation,
        "x402_score": x402_score,
        "registered_at": time.time(),
        "last_verified": time.time(),
    }
    await _common._redis.set(mapping_key, json.dumps(mapping_data), ex=_MEEET_TTL)

    # 同时写入 ANPN directory（可被 lookup 发现）
    dir_key = f"{_DIR_PREFIX}{agentnexus_did}"
    await _common._redis.set(dir_key, json.dumps({
        "did": agentnexus_did,
        "relay_url": f"https://{_common._relay_host}",
        "meeet_did": req.meeet_did,
        "x402_score": x402_score,
    }))

    return {
        "status": "ok",
        "meeet_did": req.meeet_did,
        "agentnexus_did": agentnexus_did,
        "x402_score": x402_score,
    }


@app.post("/meeet/batch-register")
async def meeet_batch_register(req: MeeetBatchRegisterRequest):
    """
    批量 MEEET Agent 注册（需平台管理员签名 + 每条 Agent 签名）。

    单次最大 100 条（Q9 答疑）。
    """
    # 检查数量限制
    if len(req.agents) > 100:
        raise HTTPException(status_code=400, detail="Max 100 agents per batch")

    # 验证时间戳
    if abs(time.time() - req.admin_timestamp) > 300:
        raise HTTPException(status_code=400, detail="Timestamp expired")

    # 验证管理员签名
    admin_exists = await _common._redis.sismember(_MEEET_ADMINS_KEY, req.admin_pubkey)
    if not admin_exists:
        raise HTTPException(status_code=401, detail="Not a registered admin")

    # 验证请求签名
    message = f"batch-register:{req.admin_timestamp}:{len(req.agents)}"
    try:
        from nacl.signing import VerifyKey
        vk = VerifyKey(bytes.fromhex(req.admin_pubkey))
        vk.verify(message.encode(), bytes.fromhex(req.admin_signature))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid admin signature")

    # 逐条处理
    results = []
    success_count = 0

    for agent in req.agents:
        try:
            # 验证 Agent 签名
            if not await _verify_agent_signature(
                agent["pubkey"],
                agent["nonce"],
                agent["signature"]
            ):
                results.append({
                    "meeet_did": agent.get("meeet_did", "unknown"),
                    "status": "failed",
                    "error": "Invalid agent signature",
                })
                continue

            # 推导 did:agentnexus
            agentnexus_did = _pubkey_to_agentnexus_did(agent["pubkey"])
            x402_score = compute_x402_score(agent["reputation"])

            # 写入映射表
            mapping_key = f"{_MEEET_MAPPING_PREFIX}{agent['meeet_did']}"
            mapping_data = {
                "agentnexus_did": agentnexus_did,
                "pubkey_hex": agent["pubkey"],
                "meeet_reputation": agent["reputation"],
                "x402_score": x402_score,
                "registered_at": time.time(),
                "last_verified": time.time(),
            }
            await _common._redis.set(mapping_key, json.dumps(mapping_data), ex=_MEEET_TTL)

            # 写入 ANPN directory
            dir_key = f"{_DIR_PREFIX}{agentnexus_did}"
            await _common._redis.set(dir_key, json.dumps({
                "did": agentnexus_did,
                "relay_url": f"https://{_common._relay_host}",
                "meeet_did": agent["meeet_did"],
                "x402_score": x402_score,
            }))

            results.append({
                "meeet_did": agent["meeet_did"],
                "agentnexus_did": agentnexus_did,
                "x402_score": x402_score,
                "status": "ok",
            })
            success_count += 1

        except Exception as e:
            results.append({
                "meeet_did": agent.get("meeet_did", "unknown"),
                "status": "failed",
                "error": str(e),
            })

    return {
        "status": "partial" if success_count < len(req.agents) else "ok",
        "total": len(req.agents),
        "success": success_count,
        "results": results,
    }


@app.get("/meeet/status")
async def meeet_status():
    """查询 MEEET 映射状态统计"""
    # 获取映射数量（扫描 meeet:mapping:* 键）
    keys = await _common._redis.keys(f"{_MEEET_MAPPING_PREFIX}*")
    admin_count = await _common._redis.scard(_MEEET_ADMINS_KEY)

    return MeeetStatusResponse(
        mapping_count=len(keys),
        admin_count=admin_count,
        last_updated=time.time(),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
