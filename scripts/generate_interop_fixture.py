#!/usr/bin/env python3
"""
Generate AgentNexus test-vector fixture for APS interop.

Outputs: interop/fixtures/agentnexus/happy-path.json
         interop/fixtures/agentnexus/scope-expansion.json
"""
import hashlib
import json
import time
from datetime import datetime, timezone

# 固定密钥用于 fixture（确定性测试）
# Ed25519 私钥 = 32 bytes (64 hex chars)
PRINCIPAL_SK = "650e96215016523d5b9e7db13e35c3f77bf59466866b33ff249dfdcc6624e573"
PRINCIPAL_PK = "17a3defcd90537b0ce5e5fc04b7253b84f0ab7b8640d4b9d8ea3cb73ddc86dab"

AGENT_SK = "08188dd538a909b99bcb47d13fbe07cea16d8c08a4b014703c7cf432f1d04ad5"
AGENT_PK = "416d245ce70d8d56ac1233e26718dea4d650e8a7b1edf1ab56485608dc672217"


def compute_constraint_hash(scope: dict, constraints: dict) -> str:
    """JCS canonicalization + SHA256"""
    canonical = json.dumps(
        {"scope": scope, "constraints": constraints},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def jcs_canonicalize(obj: dict, exclude_keys: list = None) -> str:
    """JCS canonicalization (RFC 8785)"""
    exclude_keys = exclude_keys or []
    filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ed25519_sign(canonical: str, private_key_hex: str) -> str:
    """Ed25519 签名，返回 base64url 编码"""
    from nacl.signing import SigningKey
    from nacl.encoding import URLSafeBase64Encoder

    sk = SigningKey(bytes.fromhex(private_key_hex))
    signed = sk.sign(canonical.encode())
    return URLSafeBase64Encoder.encode(signed.signature).decode()


def generate_happy_path() -> dict:
    """生成 happy-path fixture"""
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    now_ts = time.time()

    # Parent token (principal → agent)
    parent_scope = {
        "permissions": ["vault:read", "vault:write", "playbook:execute"],
        "resource_pattern": "enclave:test-enc/*",
        "role": "collaborator"
    }
    parent_constraints = {
        "spend_limit": 100,
        "max_delegation_depth": 2,
        "allowed_stages": ["stage_1", "stage_2"],
        "input_keys": ["input_a"],
        "output_key": "output_x"
    }

    parent_token = {
        "token_id": "ct_a1b2c3d4e5f6",
        "version": 1,
        "issuer_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "subject_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "enclave_id": "enc_test_001",
        "scope": parent_scope,
        "constraints": parent_constraints,
        "validity": {
            "not_before": now_ts,
            "not_after": now_ts + 86400,  # 24h
        },
        "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/ct_a1b2c3d4e5f6/status",
        "evaluated_constraint_hash": compute_constraint_hash(parent_scope, parent_constraints),
        "created_at": now_ts,
    }

    # 签名 parent token
    parent_canonical = jcs_canonicalize(parent_token, ["signature", "signature_alg", "canonicalization", "status", "revoked_at"])
    parent_token["signature"] = ed25519_sign(parent_canonical, PRINCIPAL_SK)
    parent_token["signature_alg"] = "EdDSA"
    parent_token["canonicalization"] = "JCS"
    parent_token["status"] = "active"

    # Child token (delegation) - scope narrowed
    child_scope = {
        "permissions": ["vault:read"],  # ⊂ parent
        "resource_pattern": "enclave:test-enc/docs/*",  # narrower
        "role": "reader"
    }
    child_constraints = {
        "spend_limit": 50,  # < parent
        "max_delegation_depth": 1,  # < parent
        "allowed_stages": ["stage_1"],  # ⊂ parent
        "input_keys": ["input_a"],
        "output_key": "output_x"
    }

    child_token = {
        "token_id": "ct_child_001",
        "version": 1,
        "issuer_did": parent_token["subject_did"],  # delegated by agent
        "subject_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "enclave_id": "enc_test_001",
        "scope": child_scope,
        "constraints": child_constraints,
        "validity": {
            "not_before": now_ts,
            "not_after": now_ts + 3600,  # 1h (within parent window)
        },
        "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/ct_child_001/status",
        "evaluated_constraint_hash": compute_constraint_hash(child_scope, child_constraints),
        "created_at": now_ts,
    }

    child_canonical = jcs_canonicalize(child_token, ["signature", "signature_alg", "canonicalization", "status", "revoked_at"])
    child_token["signature"] = ed25519_sign(child_canonical, AGENT_SK)
    child_token["signature_alg"] = "EdDSA"
    child_token["canonicalization"] = "JCS"
    child_token["status"] = "active"

    return {
        "description": "AgentNexus happy path: parent token issued (scope: vault:read/write/playbook:execute, spend_limit: 100), child token delegated with narrowed scope (vault:read only, spend_limit: 50). Full delegation chain, all signatures valid, monotonic narrowing enforced.",
        "generated_at": now_iso,
        "protocol_version": "1.0.0",
        "source_system": "AgentNexus v1.0",
        "objects": {
            "parent_token": parent_token,
            "child_token": child_token,
        },
        "canonicalized": {
            "parent_token": {
                "input": {k: v for k, v in parent_token.items() if k not in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]},
                "canonical_string": parent_canonical,
                "canonical_hex": parent_canonical.encode().hex(),
                "method": "JCS (RFC 8785) + SHA256",
                "evaluated_constraint_hash": parent_token["evaluated_constraint_hash"],
            },
            "child_token": {
                "input": {k: v for k, v in child_token.items() if k not in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]},
                "canonical_string": child_canonical,
                "canonical_hex": child_canonical.encode().hex(),
                "method": "JCS (RFC 8785) + SHA256",
                "evaluated_constraint_hash": child_token["evaluated_constraint_hash"],
            },
        },
        "signatures": {
            "parent_token": {
                "signature": parent_token["signature"],
                "signed_by": "principal (issuer_did)",
                "algorithm": "Ed25519",
            },
            "child_token": {
                "signature": child_token["signature"],
                "signed_by": "agent (parent subject, child issuer)",
                "algorithm": "Ed25519",
            },
        },
        "keys": {
            "principal": {
                "public_key": PRINCIPAL_PK,
                "role": "Enclave owner, issues parent token",
            },
            "agent": {
                "public_key": AGENT_PK,
                "role": "Parent token holder, issues child token (delegate)",
            },
        },
        "delegation_chain": [
            {
                "token_id": parent_token["token_id"],
                "issuer_did": parent_token["issuer_did"],
                "scope_hash": parent_token["evaluated_constraint_hash"],
            },
            {
                "token_id": child_token["token_id"],
                "issuer_did": child_token["issuer_did"],
                "scope_hash": child_token["evaluated_constraint_hash"],
                "parent_token_id": parent_token["token_id"],
            },
        ],
        "expected": {
            "parent_signature_valid": True,
            "child_signature_valid": True,
            "delegation_chain_complete": True,
            "scope_is_subset": True,  # child ⊂ parent
            "spend_limit_narrowed": True,  # 50 < 100
            "max_delegation_depth_narrowed": True,  # 1 < 2
            "monotonic_narrowing": True,
            "reasoning": "Child scope is strict subset of parent. spend_limit and max_delegation_depth both reduced. All signatures valid. Delegation chain complete.",
        },
        "verification_results": {
            "parent_token": {
                "valid": True,
                "checks": {
                    "signature": "verified",
                    "validity": "in_window",
                    "status": "active",
                },
            },
            "child_token": {
                "valid": True,
                "checks": {
                    "signature": "verified",
                    "validity": "in_window",
                    "chain": "complete",
                    "scope_is_subset": True,
                    "spend_limit": "narrowed",
                    "max_delegation_depth": "narrowed",
                    "status": "active",
                },
            },
        },
    }


def generate_scope_expansion() -> dict:
    """生成 scope-expansion fixture（验证失败）"""
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    now_ts = time.time()

    # Parent token
    parent_scope = {
        "permissions": ["vault:read"],
        "resource_pattern": "enclave:test-enc/*",
        "role": "reader"
    }
    parent_constraints = {
        "spend_limit": 50,
        "max_delegation_depth": 1,
        "allowed_stages": [],
        "input_keys": [],
        "output_key": ""
    }

    parent_token = {
        "token_id": "ct_scope_parent",
        "version": 1,
        "issuer_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "subject_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "enclave_id": "enc_test_002",
        "scope": parent_scope,
        "constraints": parent_constraints,
        "validity": {
            "not_before": now_ts,
            "not_after": now_ts + 86400,
        },
        "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/ct_scope_parent/status",
        "evaluated_constraint_hash": compute_constraint_hash(parent_scope, parent_constraints),
        "created_at": now_ts,
    }

    parent_canonical = jcs_canonicalize(parent_token, ["signature", "signature_alg", "canonicalization", "status", "revoked_at"])
    parent_token["signature"] = ed25519_sign(parent_canonical, PRINCIPAL_SK)
    parent_token["signature_alg"] = "EdDSA"
    parent_token["canonicalization"] = "JCS"
    parent_token["status"] = "active"

    # Child token - SCOPE EXPANSION (invalid)
    child_scope = {
        "permissions": ["vault:read", "vault:write"],  # EXPANDED (not subset)
        "resource_pattern": "enclave:test-enc/*",
        "role": "writer"  # upgraded role
    }
    child_constraints = {
        "spend_limit": 100,  # EXPANDED (> parent)
        "max_delegation_depth": 2,  # EXPANDED (> parent)
        "allowed_stages": [],
        "input_keys": [],
        "output_key": ""
    }

    child_token = {
        "token_id": "ct_scope_child_invalid",
        "version": 1,
        "issuer_did": parent_token["subject_did"],
        "subject_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "enclave_id": "enc_test_002",
        "scope": child_scope,
        "constraints": child_constraints,
        "validity": {
            "not_before": now_ts,
            "not_after": now_ts + 3600,
        },
        "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/ct_scope_child_invalid/status",
        "evaluated_constraint_hash": compute_constraint_hash(child_scope, child_constraints),
        "created_at": now_ts,
    }

    child_canonical = jcs_canonicalize(child_token, ["signature", "signature_alg", "canonicalization", "status", "revoked_at"])
    child_token["signature"] = ed25519_sign(child_canonical, AGENT_SK)
    child_token["signature_alg"] = "EdDSA"
    child_token["canonicalization"] = "JCS"
    child_token["status"] = "active"

    return {
        "description": "AgentNexus scope expansion: child token attempts to expand scope beyond parent (vault:write added, spend_limit: 100 > 50, max_delegation_depth: 2 > 1). Signature valid but monotonic narrowing violation. Should fail verification with SCOPE_EXPANSION.",
        "generated_at": now_iso,
        "protocol_version": "1.0.0",
        "source_system": "AgentNexus v1.0",
        "objects": {
            "parent_token": parent_token,
            "child_token": child_token,
        },
        "canonicalized": {
            "parent_token": {
                "input": {k: v for k, v in parent_token.items() if k not in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]},
                "canonical_string": parent_canonical,
                "method": "JCS (RFC 8785)",
            },
            "child_token": {
                "input": {k: v for k, v in child_token.items() if k not in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]},
                "canonical_string": child_canonical,
                "method": "JCS (RFC 8785)",
            },
        },
        "signatures": {
            "parent_token": {
                "signature": parent_token["signature"],
                "signed_by": "principal",
                "algorithm": "Ed25519",
                "valid": True,
            },
            "child_token": {
                "signature": child_token["signature"],
                "signed_by": "agent",
                "algorithm": "Ed25519",
                "valid": True,  # signature is valid, but scope expansion makes token invalid
            },
        },
        "keys": {
            "principal": {
                "public_key": PRINCIPAL_PK,
            },
            "agent": {
                "public_key": AGENT_PK,
            },
        },
        "expected": {
            "parent_signature_valid": True,
            "child_signature_valid": True,  # signature itself is valid
            "scope_is_subset": False,  # child ⊄ parent
            "spend_limit_narrowed": False,  # 100 > 50
            "max_delegation_depth_narrowed": False,  # 2 > 1
            "monotonic_narrowing": False,
            "verification_result": "SCOPE_EXPANSION",
            "reasoning": "Child permissions expanded (vault:write added), spend_limit increased (100 > 50), max_delegation_depth increased (2 > 1). All three violate monotonic narrowing. First check fails on scope expansion.",
        },
        "verification_results": {
            "parent_token": {
                "valid": True,
            },
            "child_token": {
                "valid": False,
                "reason": "SCOPE_EXPANSION",
                "detail": "child permissions [vault:read, vault:write] ⊄ parent permissions [vault:read]",
            },
        },
    }


if __name__ == "__main__":
    import os

    base_dir = "interop/fixtures/agentnexus"
    os.makedirs(base_dir, exist_ok=True)

    happy_path = generate_happy_path()
    with open(f"{base_dir}/happy-path.json", "w") as f:
        json.dump(happy_path, f, indent=2)
    print(f"Generated {base_dir}/happy-path.json")

    scope_expansion = generate_scope_expansion()
    with open(f"{base_dir}/scope-expansion.json", "w") as f:
        json.dump(scope_expansion, f, indent=2)
    print(f"Generated {base_dir}/scope-expansion.json")