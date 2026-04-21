# Proposal: Decision Consistency Levels for A2A

> **Author:** kevinkaylie (AgentNexus)
> **Date:** 2026-04-21
> **Status:** Draft
> **Related:** #1575, #1717, #1497, #1472, #1501

## Problem

Agent-to-agent decisions today are evaluated at query time. The same interaction proof can yield different outcomes depending on when and where it's evaluated — trust scores decay, endorsements propagate, TTLs expire, graph state changes.

This is not a bug. Most agent operations don't need temporal guarantees. But some do — and the protocol currently has no way for a caller to declare "this decision needs time-sensitive verification" vs. "just check the constraint hash."

The result: every implementation invents its own approach to temporal consistency, making cross-verifier equivalence impossible to reason about.

## Proposal: `consistency_level` as a protocol-level field

Introduce an optional `consistency_level` field in the decision/verification envelope. Callers declare the level of temporal guarantee they need; verifiers enforce accordingly.

### Levels

| Level | Name | Guarantee | Overhead | Use Case |
|-------|------|-----------|----------|----------|
| **L0** | None | Constraint hash only. No temporal context. | Zero | Permission checks, scope validation, daily operations. **Default.** |
| **L1** | Wall-clock timestamp | `evaluated_at` timestamp included. Verifier checks reasonable time window. | Minimal | Audit trails, general compliance, transaction records. |
| **L2** | Causal ordering | Hybrid Logical Clock (HLC) guarantees "A happened before B" across distributed agents. | Low | Multi-agent collaboration, ordering-sensitive workflows. |
| **L3** | Partition-tolerant | Store-and-forward with delayed confirmation. Tolerates network partitions and high latency. | Medium | Cross-region compliance, intermittent connectivity, extreme-latency networks. |

### Wire format

```json
{
  "evaluated_constraint_hash": "sha256:abc...",
  "consistency_level": "L1",
  "evaluation_context": {
    "evaluated_at": 1713600000,
    "policy_version": "v1.2"
  }
}
```

At L0, both `consistency_level` and `evaluation_context` are **omitted entirely** — zero overhead, full backward compatibility with existing implementations.

At L2, `evaluation_context` carries an HLC tuple:

```json
{
  "evaluated_constraint_hash": "sha256:abc...",
  "consistency_level": "L2",
  "evaluation_context": {
    "hlc": {
      "wall_time": 1713600000000,
      "logical": 3,
      "node_id": "did:agentnexus:z6Mk..."
    },
    "policy_version": "v1.2"
  }
}
```

### What each level answers

The key insight is that **different layers of a decision have different temporal properties**:

| Layer | Temporal property | Example |
|-------|-------------------|---------|
| Interaction proof (IPR hash + signature) | **Time-invariant.** Deterministic, identical regardless of when verified. | "Agent A signed action X" |
| Authorization (Capability Token scope) | **Time-invariant.** Token is active or revoked — binary state. | "Agent A has vault:read" |
| Derived decision (trust score → grade → limit) | **Time-dependent.** Varies with graph state, decay, propagation. | "Agent A's trust score is 72 → L3 → $1000 limit" |

L0 covers the first two layers (sufficient for most operations). L1+ covers the third layer for use cases that need it.

### Cross-verifier equivalence

Two verifiers are considered equivalent when:

- **At L0:** They agree on the constraint hash. Derived decisions may differ — this is expected and acceptable.
- **At L1:** They agree on the constraint hash AND their `evaluated_at` timestamps fall within a protocol-defined window (e.g., ±30 seconds).
- **At L2:** They agree on the constraint hash AND their HLC values establish the same causal ordering of events.

This means equivalence is **scoped to the declared consistency level**, not absolute. A verifier operating at L0 and one at L2 are not expected to produce identical derived decisions — they're answering different questions.

## Design principles

1. **Default is zero overhead.** L0 adds nothing to the wire format. Existing implementations are L0-compliant without changes.
2. **Caller declares, verifier enforces.** The business decides what level it needs, not the platform.
3. **Cost scales with sensitivity.** Higher levels cost more (bandwidth, computation, coordination) — only pay for what you need.
4. **Orthogonal to transport.** Consistency level is about decision guarantees, not message delivery. A message can travel over HTTP, Relay, or DTN independently of its consistency level.

## Compatibility

- **Backward compatible:** L0 is the implicit default. No existing A2A implementation needs to change.
- **Forward compatible:** New levels (e.g., L4 for hardware-attested timestamps) can be added without breaking existing levels.
- **Composable:** Works alongside `evaluated_constraint_hash` (already shipping in 3 implementations), Acta decision receipts, and APS delegation chains. Each layer retains its own signing identity and verification path.

## Reference implementation

AgentNexus v1.0 ships `evaluated_constraint_hash` with JCS+SHA-256 canonicalization (L0).

L1 implementation is complete:
- `agent_net/common/consistency_level.py` — `ConsistencyLevel` enum, `EvaluationContext`, `check_l1_window()`
- `agent_net/common/capability_token.py` — `verify_token()` accepts `consistency_level` parameter, returns `evaluation_context` in success response
- `tests/test_consistency_level.py` — 7 test cases covering L0/L1/L2 context building, L1 window boundaries, and serialization round-trip
- 382 tests pass (full suite)

L2+ (HLC) and L3 (store-and-forward) are planned for subsequent iterations.

## Open questions

1. **L1 window size:** What's a reasonable default for the wall-clock verification window? 30 seconds? 5 minutes? Should it be configurable per-deployment?
2. **L2 HLC format:** Should the HLC tuple be standardized (e.g., as a single sortable string `"1713600000000.0003.did:..."`) or kept as a structured object?
3. **Level negotiation:** Should two agents negotiate consistency level during handshake, or is it purely caller-declared?

## Next steps

- [x] Implement L0/L1 in AgentNexus (capability_token.py + consistency_level.py)
- [x] Publish test vectors for L0/L1 (test_consistency_level.py)
- [ ] Community feedback on this proposal
- [ ] Finalize L1 window size default (open question #1)
- [ ] Push L1 into AgentNexus v1.5 unified policy engine
