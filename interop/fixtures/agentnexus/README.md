# AgentNexus Track A Fixtures

Interoperability test vectors for AgentNexus Capability Token envelope verification.

## Overview

Two fixtures for cross-verifier comparison between [AgentNexus](https://github.com/kevinkaylie/AgentNexus) and [APS](https://github.com/aeoess/agent-passport-system).

| Fixture | Description | Expected Verdict |
|---------|-------------|------------------|
| `happy-path.json` | Parent + child tokens with monotonic narrowing | accept |
| `scope-expansion.json` | Child token violates narrowing on 3 dimensions | deny (SCOPE_EXPANSION) |

## Canonicalization

All signatures use **JCS (JSON Canonicalization Scheme, RFC 8785)** for canonical string representation before Ed25519 signing.

- AgentNexus: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` (Python)
- APS: `canonicalizeJCS()` in `src/core/canonical-jcs.ts` (TypeScript)

Both produce byte-identical output for the same input object — verified by APS round-trip report with zero canonicalization drift.

## Signature Scheme

- Algorithm: Ed25519 (EdDSA)
- Signature encoding: Base64URL (RFC 4648 §5)
- Signed payload: JCS-canonical JSON with `signature`, `signature_alg`, `canonicalization`, `status`, `revoked_at` fields excluded

## Keys

| Key ID | Role | Public Key (hex) |
|--------|------|-----------------|
| `principal` | Enclave owner, issues parent token | `17a3defcd90537b0ce5e5fc04b7253b84f0ab7b8640d4b9d8ea3cb73ddc86dab` |
| `agent` | Parent token holder, issues child token | `416d245ce70d8d56ac1233e26718dea4d650e8a7b1edf1ab56485608dc672217` |

> Fixtures use deterministic key pairs. **Do not use these keys in production.**

## Verification Steps

Both implementations verify tokens through the same 5-step process:

| Step | Check | Failure Reason |
|------|-------|----------------|
| 1 | Token status (active / revoked) | `REVOKED` |
| 2 | Ed25519 signature over JCS canonical | `SIGNATURE_INVALID` |
| 3 | Validity window (not_before / not_after) | `NOT_YET_VALID` / `EXPIRED` |
| 4 | Delegation chain + monotonic narrowing | `CHAIN_BREAK` / `SCOPE_EXPANSION` / `SPEND_LIMIT_EXPANSION` / `DELEGATION_DEPTH_EXPANSION` |
| 5 | Action in scope permissions | `PERMISSION_DENIED` |

## Scope Expansion Details

The `scope-expansion.json` fixture violates monotonic narrowing on three dimensions:

| Dimension | Parent | Child | Violation |
|-----------|--------|-------|-----------|
| permissions | `[vault:read]` | `[vault:read, vault:write]` | `vault:write` added |
| spend_limit | 50 | 100 | doubled |
| max_delegation_depth | 1 | 2 | increased |

The first check (permissions subset) triggers `SCOPE_EXPANSION` — consistent with fail-fast verification.

## Crosswalk

Field-level mapping to the governance vocabulary: [`crosswalk/agentnexus.yaml`](https://github.com/aeoess/agent-governance-vocabulary/blob/main/crosswalk/agentnexus.yaml)

## Round-trip Verification

APS round-trip report: [`interop/agentnexus-roundtrip-report.md`](https://github.com/aeoess/agent-passport-system/blob/main/interop/agentnexus-roundtrip-report.md)

```
| Check                | happy-path | scope-expansion |
|----------------------|------------|-----------------|
| JCS canonicalization | pass       | pass            |
| Ed25519 signature    | pass       | pass            |
| Validity window      | pass       | pass            |
| Chain linkage        | pass       | pass            |
| scope_is_subset      | pass       | fail (expected) |
| Token status         | pass       | pass            |
| APS decision         | accept     | deny            |
```

Run repro: `npx tsx interop/run-agentnexus-roundtrip.ts` (exit 0 on full match).
