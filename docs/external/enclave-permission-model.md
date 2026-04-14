# Enclave Permission Model — Reference for SINT Integration

This document describes the AgentNexus Enclave permission model for integration with SINT capability tokens.

---

## Overview

Enclave is a project-group collaboration model with:
- **Role-based membership** — Agents assigned to roles with permissions
- **Vault** — Shared document storage with version history
- **Playbook** — Stage-gated workflow automation

---

## Permission Levels

Enclave uses three permission levels for Vault access:

| Level | Description | Vault Operations |
|-------|-------------|------------------|
| `r` | Read-only | `get`, `list`, `history` |
| `rw` | Read-write | `get`, `list`, `history`, `put`, `delete` |
| `admin` | Full control | All operations + member management + Playbook start |

### Mapping to SINT

| AgentNexus | SINT ConstraintEnvelope | Notes |
|------------|-------------------------|-------|
| `admin` | `behavioral.allowedRoles: ["admin"]` | Full project control |
| `rw` | `behavioral.allowedRoles: ["member"]` | Standard contributor |
| `r` | `behavioral.allowedRoles: ["viewer"]` | Observer only |

---

## Delegation Model

### Current: Single-Layer Delegation

```
Enclave Owner (admin)
    │
    │  Add member with role + permissions
    ▼
Member Agent (rw / r)
```

**Properties:**
- `maxDelegationDepth: 1` — Only owner can add members
- Monotonic narrowing — Owner grants permissions, members cannot expand
- No sub-delegation — Members cannot add other members

### Planned: Multi-Hop Delegation (v1.0)

```
Owner (admin)
    │
    │  Delegate to Agent A (rw, scope: ["feature_x"])
    ▼
Agent A
    │
    │  Sub-delegate to Agent B (r, scope: ["feature_x/docs"])
    ▼
Agent B (viewer)
```

**Properties:**
- `maxDelegationDepth: 3` — Allow 2-hop sub-delegation
- `resolved_scope` precomputation — Each delegation narrows scope
- Cascade revocation — Owner revokes → all sub-delegations revoked

---

## Role Assignment

Members are assigned roles with associated permissions:

```json
{
  "enclave_id": "enc_abc123",
  "members": {
    "architect": {
      "did": "did:agentnexus:z6Mk...A",
      "permissions": "rw",
      "handbook": "Design system architecture"
    },
    "developer": {
      "did": "did:agentnexus:z6Mk...B",
      "permissions": "rw",
      "handbook": "Implement features"
    },
    "reviewer": {
      "did": "did:agentnexus:z6Mk...C",
      "permissions": "r",
      "handbook": "Review and approve"
    }
  }
}
```

### Trust Score Integration (Optional)

Role assignment can be gated by external trust score:

```
Owner → Add member
    │
    │  Check MolTrust trust_score ≥ threshold
    │  └── trust_score ≥ 50 required for "rw"
    │  └── trust_score ≥ 30 required for "r"
    │  └── MolTrust unreachable → proceed with local eval (fail-open)
    ▼
Assign role + permissions
```

---

## Playbook Stage-Gated Enforcement

Playbook defines stages with role requirements:

```json
{
  "name": "standard_dev_flow",
  "stages": [
    {
      "name": "design",
      "role": "architect",
      "permissions_required": "rw",
      "input_keys": ["requirements"],
      "output_key": "design_doc",
      "next": "review"
    },
    {
      "name": "review",
      "role": "reviewer",
      "permissions_required": "r",
      "input_keys": ["design_doc"],
      "next": "implement",
      "on_reject": "design"
    },
    {
      "name": "implement",
      "role": "developer",
      "permissions_required": "rw",
      "input_keys": ["design_doc"],
      "output_key": "code",
      "next": "done"
    }
  ]
}
```

### Enforcement Points

| Stage | Check | Enforcement |
|-------|-------|-------------|
| Assignment | Role match | `member.role == stage.role` |
| Assignment | Permission match | `member.permissions >= stage.permissions_required` |
| Assignment | Trust score (optional) | `trust_score ≥ threshold` |
| Execution | Input access | `member.permissions >= 'r'` for input_keys |
| Completion | Output write | `member.permissions >= 'rw'` for output_key |

---

## Active Constraints

Each stage execution carries active constraints:

```json
{
  "agent_did": "did:agentnexus:z6Mk...A",
  "enclave_id": "enc_abc123",
  "stage_name": "design",
  "role": "architect",
  "permissions": "rw",
  "input_keys": ["requirements"],
  "output_key": "design_doc",
  "delegation_depth": 1
}
```

### SINT ConstraintEnvelope Mapping

| AgentNexus Field | SINT Section | Format |
|------------------|--------------|--------|
| `permissions` | `behavioral.allowedRoles` | `["admin"]`, `["member"]`, `["viewer"]` |
| `role` | `behavioral.requiredRole` | String |
| `input_keys` | `attestation.inputEvidenceRefs` | Array of Vault keys |
| `output_key` | `attestation.outputEvidenceRef` | Single Vault key |
| `delegation_depth` | `execution.delegationDepth` | Integer (1 = single-layer) |
| `enclave_id` | `execution.contextId` | Enclave reference |

---

## Constraint Evaluation Flow

```
PlaybookEngine.start_stage()
    │
    ├── 1. Resolve role → find member DID
    ├── 2. Check permissions >= stage.permissions_required
    │       └── Fail: reject stage, log "INSUFFICIENT_PERMISSIONS"
    ├── 3. (Optional) Query MolTrust trust_score
    │       └── Fail-open: proceed if service unreachable
    ├── 4. Create stage_execution record (status=active)
    ├── 5. Send task_propose to member DID
    │       └── Include active_constraints in metadata
    │
    ▼
Member executes task
    │
    ├── Vault.get(input_keys) — requires 'r' permission
    ├── Member produces output
    ├── Vault.put(output_key) — requires 'rw' permission
    │       └── Fail: log "PERMISSION_DENIED", abort
    │
    ▼
Member calls notify_state(completed)
    │
    └── PlaybookEngine.on_stage_completed()
        ├── Verify output_ref exists in Vault
        ├── Advance to next stage
        └── Update stage_execution status
```

---

## Cross-Enclave Verification

### DID Resolution

`relay.agentnexus.top/resolve/{did}` returns W3C DID Document:

```json
{
  "@context": ["https://www.w3.org/ns/did/v1"],
  "id": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "verificationMethod": [{
    "id": "did:agentnexus:z6Mk...#keys-1",
    "type": "Ed25519VerificationKey2020",
    "controller": "did:agentnexus:z6Mk...",
    "publicKeyMultibase": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
  }]
}
```

**Key extraction path:** `verificationMethod[0].publicKeyMultibase` — z-prefixed, multicodec ed25519-pub.

### Signature Compatibility

AgentNexus uses Ed25519 (PyNaCl/libsodium), byte-compatible with:
- APS EdDSA signatures
- SINT capability tokens
- MolTrust JWS attestations

---

## Test Vectors

### Permission Check Cases

| Case | Permissions | Required | Result |
|------|-------------|----------|--------|
| `allow-r-get` | `r` | `r` | ✅ allow |
| `allow-rw-put` | `rw` | `rw` | ✅ allow |
| `allow-admin-all` | `admin` | `rw` | ✅ allow |
| `deny-r-put` | `r` | `rw` | ❌ deny (INSUFFICIENT_PERMISSIONS) |
| `deny-rw-admin` | `rw` | `admin` | ❌ deny (ADMIN_REQUIRED) |

### Delegation Depth Cases

| Depth | SINT Tier Floor | Notes |
|-------|-----------------|-------|
| 1 | T1 | Single-layer (current) |
| 3 | T2 | Multi-hop (planned) |
| ≥5 | T3 | Deep delegation |

---

## Integration Endpoints

| Function | Endpoint | Notes |
|----------|----------|-------|
| Trust score query | `GET api.moltrust.ch/skill/trust-score/{did}` | Optional role assignment gate |
| DID resolution | `GET relay.agentnexus.top/resolve/{did}` | Ed25519 key extraction |
| Governance attestation | `POST api.moltrust.ch/guard/governance/validate-capabilities` | Cross-verify |

---

## References

- ADR-013: Enclave Collaboration Architecture
- ADR-014: Governance Attestation + Trust Network
- SINT PR #111: skill-bound capability conformance fixture
- Crosswalk PR #9: agent-governance-vocabulary