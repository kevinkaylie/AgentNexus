# RFC-001: Agent Discovery and Identity Establishment

| Field | Value |
|---|---|
| Status | Draft |
| Category | Standards Track |
| Version | 0.1 |
| Created | 2026-07-17 |
| Authors | AgentNexus Contributors |
| Requires | RFC-000 |
| Updates | None |
| Obsoletes | None |

## Abstract

This document defines transport-independent semantics for discovering agents
and establishing control over agent identities within the Agent Collaboration
Framework (ACF).

Discovery and identity are related but independent concerns. Discovery locates
potential collaboration endpoints and retrieves descriptions about them.
Identity establishment resolves an identifier and verifies that a participant
controls an authorized verification method. A discovered description is not
automatically verified, and a verified identity is not automatically trusted,
capable, authorized, online, or suitable for a collaboration.

This RFC is divided into two independently conformable parts:

- **Part A — Agent Discovery**
- **Part B — Agent Identity Establishment**

Implementations may support either part or both, but they MUST identify their
conformance separately.

## 1. Status and Normative Language

This document is a Draft and is not yet a ratified wire specification. JSON
examples are illustrative unless a later version explicitly marks a schema as
normative.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and
**OPTIONAL** in this document are to be interpreted as described in
[BCP 14](https://www.rfc-editor.org/info/bcp14) when, and only when, they appear
in all capitals.

## 2. Relationship Between Discovery and Identity

Discovery answers:

- Where can an Agent be found?
- Which collaboration protocols and transports does it claim to support?
- Which capabilities, actions, or domains does it claim to offer?
- Which description, directory, referral, or registration source supplied the
  result?

Identity establishment answers:

- Which identifier names the Agent?
- Which verification methods are authorized for that identifier?
- Does the current participant control an authorized verification method?
- Which Principal does the Agent claim to represent?
- How are keys, controllers, status, rotation, deactivation, and recovery
  handled?

The relationship is:

```text
Discovery Record
  → contains an Agent Identifier and Identity Reference
  → Identity Resolution retrieves authorized verification methods
  → Proof of Control establishes current control
  → RFC-002 may request additional representation or organization evidence
```

The following implications are invalid:

```text
Discovered       ⇏ identity verified
Identity verified ⇏ Principal relationship verified
Identity verified ⇏ capability verified
Identity verified ⇏ authority granted
Identity verified ⇏ trusted
Identity verified ⇏ online
```

## 3. Common Terminology

### 3.1 Agent Identifier

A stable identifier used to refer to an Agent. The identifier MAY be a DID,
URI, URN, or another resolvable identifier format defined by an identity
method.

ACF does not require a single identity technology.

### 3.2 Principal Identifier

An identifier for a Principal represented by or granting authority to an
Agent. A Principal Identifier MUST NOT be inferred solely from an Agent
Identifier.

### 3.3 Agent Descriptor

A structured, versioned description of an Agent's declared collaboration
properties. It may contain endpoints, supported protocol versions, declared
capabilities, actions, identity references, and metadata references.

An Agent Descriptor is a set of claims. It is not proof of those claims merely
because it is discoverable.

### 3.4 Discovery Record

A record returned by a discovery mechanism. It contains or references an Agent
Descriptor and identifies the source and provenance of the result.

### 3.5 Directory

A service or data structure that stores, indexes, recommends, or returns
Discovery Records. A Directory may be public, private, federated,
organization-scoped, local, or ephemeral.

### 3.6 Identity Method

A method that defines identifier syntax, resolution, verification methods,
controller semantics, lifecycle, status, and error behavior.

### 3.7 Identity Document

A resolved, versioned document describing authorized verification methods,
controllers, status, and service or metadata references for an Agent
Identifier.

### 3.8 Verification Method

A cryptographic or equivalent method authorized by an Identity Document for a
specific purpose, such as authentication, assertion, delegation, or key
agreement.

### 3.9 Proof of Control

A fresh proof that a participant currently controls an authorized
Verification Method for an Agent Identifier.

### 3.10 Representation Claim

A claim that an Agent represents, is operated by, or acts for a Principal.
Representation is separate from control of the Agent Identifier and is
verified through evidence exchange under RFC-002.

## Part A — Agent Discovery

## 4. Discovery Scope

Part A defines:

- discovery queries;
- discovery records and descriptors;
- endpoint descriptions;
- provenance of directory and referral results;
- registration, announcement, update, and withdrawal semantics;
- discovery freshness and status;
- separate conformance requirements for discovery providers and clients.

Part A does not:

- define how messages are transported;
- guarantee endpoint reachability;
- verify every descriptor claim;
- define a universal capability taxonomy;
- define search ranking or recommendation truth;
- require a centralized registry;
- establish identity control, trust, permission, or authority.

## 5. Discovery Models

An implementation MAY support one or more discovery models:

| Model | Description |
|---|---|
| Direct Reference | The requester already has an Agent Identifier or descriptor reference |
| Directory Query | A directory is queried using structured filters |
| Registration Registry | Agents register descriptors with a service |
| Broadcast or Gossip | Descriptors or announcements are propagated among peers |
| Referral | One participant recommends or points to another Agent |
| Federated Lookup | Multiple directories resolve or forward a query |
| Local Enumeration | A runtime lists locally available Agents |

All models MUST preserve the source of a result. An implementation MUST NOT
rewrite a third-party or self-asserted claim as if the Directory were its
original issuer.

## 6. Discovery Query

A Discovery Query SHOULD support:

- `query_id`: globally or collision-resistant query identifier;
- `requester`: optional requester identifier;
- `capability_terms`: declared capability terms or namespaced identifiers;
- `action_terms`: declared actions or interfaces;
- `protocol_versions`: acceptable ACF RFC versions or profiles;
- `transport_bindings`: acceptable transport bindings;
- `identity_methods`: acceptable identity methods, if constrained;
- `principal_requirements_ref`: optional RFC-002 requirements reference;
- `location_or_scope`: optional network, organization, jurisdiction, or
  deployment scope;
- `freshness`: maximum acceptable descriptor age;
- `limit` and `cursor`: bounded pagination;
- `created_at` and `expires_at`;
- privacy preferences;
- proof when required by the Directory.

Capability and action terms are discovery filters. A match means that a
descriptor contains a corresponding claim. It does not prove capability.

A Directory MAY reject or reduce a query that is too broad, expensive,
privacy-invasive, or unauthenticated.

## 7. Agent Descriptor

An Agent Descriptor SHOULD be capable of expressing:

- `descriptor_id`;
- `descriptor_version`;
- `agent_id`;
- `identity_ref`;
- declared names and human-readable descriptions;
- declared capabilities and actions;
- supported ACF RFC versions and extension profiles;
- Endpoint Descriptors;
- Principal or organization claim references;
- evidence-service or metadata-negotiation endpoints;
- availability or presence claims;
- creation, update, and expiration time;
- predecessor or successor descriptor references;
- status;
- issuer;
- proof;
- extension fields.

The descriptor MUST distinguish:

- self-asserted fields;
- third-party assertions;
- locally observed fields;
- Directory-generated fields.

The descriptor MUST NOT use a single `verified` flag to collapse these
different claim types.

### 7.1 Declared Capability

A declared capability SHOULD identify:

- a namespaced capability type;
- optional action identifiers;
- schema or interface references;
- version;
- input and output media or schema types;
- optional supporting Evidence references;
- constraints known at discovery time.

A declared capability is not Permission and is not proof of competence.

### 7.2 Presence and Reachability

Presence and reachability are time-sensitive claims.

A presence claim SHOULD identify:

- observer or issuer;
- observation time;
- expiration or TTL;
- observed endpoint or binding;
- observation method;
- proof or provenance when available.

An expired presence claim MUST NOT be represented as current. Failure to reach
an endpoint does not deactivate the Agent Identifier.

## 8. Endpoint Descriptor

An Endpoint Descriptor SHOULD identify:

- endpoint identifier;
- transport or application binding;
- URI or transport-specific address;
- supported ACF RFC and profile versions;
- supported serialization and proof formats;
- authentication or precondition requirements;
- priority and weight;
- network or organization scope;
- creation and expiration time;
- issuer and proof;
- confidentiality or data-residency constraints.

Endpoint addresses are untrusted input until validated by the consumer.
Implementations MUST apply transport-specific protections against SSRF,
redirect abuse, local-network access, credential forwarding, and endpoint
confusion.

## 9. Discovery Record

A Discovery Record SHOULD identify:

- `record_id`;
- `query_id` or direct lookup reference;
- Agent Descriptor or immutable descriptor reference;
- record source;
- original descriptor issuer;
- Directory, referrer, or federation path;
- retrieval and expiration time;
- ranking or recommendation metadata, if any;
- proof or integrity mechanism;
- warnings and validation status.

If a Directory adds ranking, recommendation, risk, or score fields, those
fields MUST identify:

- the evaluator;
- method and version;
- evaluated context;
- evaluation time;
- relevant input references where disclosure is permitted.

Such fields are Evidence under RFC-002 and MUST NOT be interpreted as universal
trust.

## 10. Registration, Announcement, Update, and Withdrawal

### 10.1 Registration or Announcement

A registration or announcement SHOULD bind:

- Agent Identifier;
- descriptor or descriptor hash;
- endpoint set;
- issuer;
- nonce or unique announcement identifier;
- issuance and expiration time;
- proof of origin.

A Directory MAY require Proof of Control before accepting a registration. If
it does not, the resulting record MUST be marked as unverified or
self-asserted.

### 10.2 Update

An update MUST:

- identify the record or descriptor being replaced;
- use a monotonically increasing version, immutable version identifier, or
  equivalent conflict-resolution mechanism;
- be authorized according to the Directory policy;
- preserve provenance;
- carry a fresh proof when required.

### 10.3 Withdrawal

A withdrawal removes a Discovery Record from a particular Directory or
discovery scope. It does not necessarily deactivate the Agent Identifier.

Withdrawal and identity deactivation MUST remain distinct operations.

### 10.4 Expiration

Directories MUST NOT return an expired record as current without explicitly
marking it stale. Cached records SHOULD retain retrieval source and original
expiry.

## 11. Discovery Result Validation

A discovery client SHOULD separately record:

- descriptor syntax status;
- descriptor proof status;
- directory or referral proof status;
- descriptor freshness;
- endpoint validation status;
- Identity Resolution status;
- Proof of Control status, if performed;
- warnings and unsupported fields.

A single boolean `verified` is insufficient.

## 12. Discovery Failure Semantics

Part A defines the following failure classes:

- `query_malformed`;
- `query_too_broad`;
- `query_unauthorized`;
- `query_rate_limited`;
- `directory_unavailable`;
- `record_not_found`;
- `record_expired`;
- `descriptor_malformed`;
- `descriptor_proof_invalid`;
- `endpoint_unsupported`;
- `federation_loop`;
- `cursor_invalid`;
- `privacy_rejected`.

Transport bindings MAY map these classes to transport-specific errors.

## 13. Discovery Security and Privacy

### 13.1 Directory Poisoning

Directories may contain false, injected, or stale records. Clients MUST
preserve provenance and SHOULD verify descriptor proofs and identity control
before sensitive collaboration.

### 13.2 Capability Spam and Search Manipulation

Agents or directories may stuff descriptors with capability terms or
manipulate ranking. Capability matches MUST remain claims until supported by
Evidence and receiver-local evaluation.

### 13.3 Endpoint Hijacking

An attacker may replace a legitimate endpoint while preserving other
descriptor fields. Security-sensitive descriptors SHOULD bind endpoint sets
into the issuer proof. Consumers MUST verify endpoint freshness and binding.

### 13.4 Replay and Staleness

Announcements and records SHOULD use unique identifiers, timestamps, expiry,
and versioning. Directories MUST prevent an older valid descriptor from
silently replacing a newer one.

### 13.5 Privacy of Queries

Discovery queries may expose an Agent's objective, capability needs,
organization, location, or intended action. Implementations SHOULD support:

- minimal queries;
- private or organization-scoped directories;
- pseudonymous or unauthenticated lookup where policy allows;
- query retention limits;
- proof of authorization before returning sensitive descriptors;
- result minimization.

### 13.6 Enumeration and Correlation

Public enumeration can enable surveillance and correlation. Directories SHOULD
support rate limits, bounded pagination, visibility policy, and selective
fields.

### 13.7 Sybil Identities

Discovery systems MUST NOT equate identifier count with independent
participants. Sybil resistance is receiver and domain specific and may use
Evidence under RFC-002.

### 13.8 Federation Loops and Amplification

Federated discovery MUST bound forwarding depth, identify visited directories,
and prevent recursive amplification.

## Part B — Agent Identity Establishment

## 14. Identity Scope

Part B defines:

- identity method requirements;
- Identity Resolution;
- Verification Methods and their purposes;
- Proof of Control;
- separation of Agent identity from Principal representation;
- key rotation, deactivation, operator change, and recovery semantics;
- identity validation results and failure classes.

Part B does not:

- mandate DID or any other single identity technology;
- establish uniqueness of a human, organization, or legal entity;
- prove capability or permission;
- establish trust;
- prove that an Agent still satisfies a collaboration policy;
- define the full representation or organization credential format.

## 15. Identity Method Requirements

An ACF Identity Method MUST define:

- identifier syntax and normalization;
- resolution procedure;
- supported Verification Method types;
- verification-purpose semantics;
- controller semantics;
- document or key versioning;
- status and deactivation semantics;
- key rotation;
- compromise and recovery behavior;
- cache and freshness requirements;
- deterministic error classes;
- security and privacy considerations;
- test vectors.

Identity methods MAY be self-certifying, registry-backed, domain-backed,
ledger-backed, federated, or local. Consumers MUST NOT assume identical
security properties across methods.

## 16. Identity Document

An Identity Document SHOULD support:

- `id`: Agent Identifier;
- `method` and method version;
- authorized controllers;
- Verification Methods;
- purpose bindings for authentication, assertion, delegation, and key
  agreement;
- status;
- creation and update time;
- immutable version identifier;
- predecessor or successor references;
- service and descriptor references;
- representation-evidence references;
- recovery or deactivation references where supported;
- proof or method-specific integrity mechanism.

Service endpoints in an Identity Document do not replace Endpoint Descriptors.
An Identity Document may reference discovery information without making every
discovery claim an identity claim.

## 17. Identity Resolution

The abstract resolution interface is:

```text
resolve_identity(agent_id, options)
  → IdentityResolutionResult
```

An Identity Resolution Result SHOULD identify:

- requested identifier;
- normalized identifier;
- identity method;
- Identity Document;
- authorized Verification Methods;
- resolution source;
- retrieval time;
- document version and freshness;
- cache status;
- method-specific metadata;
- validation warnings;
- status.

Resolution success means that the method produced a valid Identity Document
according to its rules. It does not prove that the current participant controls
an authorized key. Proof of Control is a separate step.

### 17.1 Cache Behavior

Cached identity data MUST retain:

- original source;
- retrieval time;
- expiry or method-defined TTL;
- document version;
- status and validation result.

An implementation MUST NOT silently replace failed live resolution with an
unverified key. Stale cached identity MAY be returned only with explicit stale
status and according to local policy.

## 18. Verification Methods and Purpose

Each Verification Method MUST identify:

- method identifier;
- controller;
- cryptographic or equivalent method type;
- public verification material or resolvable reference;
- authorized purposes;
- validity or version information where applicable;
- revocation or status information where applicable.

Using a valid key for an unauthorized purpose MUST fail. For example, a key
authorized only for key agreement MUST NOT be accepted for assertions.

## 19. Proof of Control

Proof of Control SHOULD use a fresh verifier challenge.

### 19.1 Challenge

A control challenge SHOULD identify:

- challenge identifier;
- verifier;
- Agent Identifier;
- intended audience;
- purpose;
- cryptographically random nonce;
- issued and expiration time;
- requested Verification Method or method class;
- related intent or session, when applicable.

### 19.2 Response

A control response SHOULD identify:

- challenge identifier and nonce binding;
- Agent Identifier;
- selected Verification Method;
- verifier and audience;
- purpose;
- issued time;
- proof.

The proof input MUST bind all security-relevant challenge fields.

### 19.3 Verification

The verifier MUST:

1. resolve the current Identity Document;
2. locate the selected Verification Method;
3. confirm that the method is authorized for the requested purpose;
4. validate challenge freshness and single use;
5. validate audience and context binding;
6. verify the proof;
7. record document version, method identifier, and verification time.

The result SHOULD be structured:

```text
control_proven
control_not_proven
identity_unresolved
method_unauthorized
proof_invalid
challenge_expired
identity_deactivated
```

## 20. Agent and Principal Separation

Control of an Agent Identifier proves control of that Agent identity. It does
not prove:

- legal identity;
- organization membership;
- employment;
- ownership;
- authority to represent another Principal;
- professional license;
- regulatory status.

Such relationships MUST be represented as Claims and Evidence under RFC-002.

An Agent MAY represent multiple Principals in different contexts. A
Collaboration Intent or Session MUST identify the relevant Principal and
representation Evidence when that distinction affects authority or risk.

## 21. Rotation, Deactivation, Operator Change, and Recovery

### 21.1 Key Rotation

An Identity Method MUST define whether key rotation:

- updates the same identifier;
- creates a successor identifier;
- requires proofs from old and new keys;
- uses an independent recovery authority.

A rotation record SHOULD identify:

- predecessor identity or document version;
- successor identity or document version;
- affected Verification Methods;
- effective time;
- reason class;
- continuity proofs;
- recovery proof when the old key is unavailable or compromised.

### 21.2 Deactivation

Deactivation means the Agent Identifier or a Verification Method is no longer
valid for new protocol actions. Historical proofs and receipts may remain
verifiable according to their issuance-time context.

Deactivation MUST be distinguishable from:

- temporary unreachability;
- discovery-record withdrawal;
- session suspension;
- expired presence;
- operator change.

### 21.3 Operator or Principal Change

Changing the operator or represented Principal is not merely key rotation.
The change SHOULD update or revoke relevant Representation Claims and
delegations through RFC-002 and RFC-003 semantics.

### 21.4 Recovery

Recovery mechanisms MUST define:

- authorized recovery controller or process;
- compromise assumptions;
- continuity proof;
- delay or challenge period, if any;
- notification and audit record;
- effect on existing sessions and authority.

Consumers SHOULD re-evaluate active collaboration after identity recovery.

## 22. Identity States

An implementation SHOULD distinguish at least:

- `unresolved`;
- `resolved`;
- `control_proven`;
- `control_not_proven`;
- `stale`;
- `deactivated`;
- `compromised`;
- `recovery_pending`;
- `unavailable`.

Identity status is time- and method-specific. A prior `control_proven` result
MUST NOT be treated as permanent.

## 23. Identity Failure Semantics

Part B defines the following failure classes:

- `identifier_malformed`;
- `method_unsupported`;
- `identity_not_found`;
- `identity_unavailable`;
- `document_malformed`;
- `document_proof_invalid`;
- `key_type_unsupported`;
- `verification_method_not_found`;
- `verification_purpose_unauthorized`;
- `challenge_malformed`;
- `challenge_expired`;
- `challenge_replayed`;
- `proof_missing`;
- `proof_invalid`;
- `controller_mismatch`;
- `identity_deactivated`;
- `identity_compromised`;
- `rotation_invalid`;
- `recovery_unverified`.

## 24. Identity Security and Privacy

### 24.1 Identity Impersonation

Consumers MUST perform Proof of Control before relying on a participant's
claimed Agent Identifier for sensitive collaboration.

### 24.2 Key Substitution

Resolution sources, caches, and directories may attempt to substitute keys.
Identity Method integrity, document version, controller, and Proof of Control
MUST be validated together.

### 24.3 Key Compromise

Identity Methods MUST define deactivation or recovery behavior. Receivers
SHOULD re-evaluate active sessions and authority after compromise signals.

### 24.4 Rotation Downgrade

An attacker may replay an old identity document or suppress a rotation.
Consumers SHOULD use monotonic versions, immutable version identifiers, status
checks, and freshness policy.

### 24.5 Operator Change

Continuing to trust old representation evidence after operator change can
create a confused-deputy condition. Principal relationships and delegations
SHOULD be re-evaluated.

### 24.6 Sybil Identities

Self-certifying identity proves key control, not uniqueness. Identity
implementations MUST NOT claim Sybil resistance without a separately defined
mechanism and evidence.

### 24.7 Correlation

Stable identifiers enable correlation across directories, transports,
sessions, and domains. Implementations SHOULD support pairwise or scoped
identifiers where compatible with audit and authority requirements.

### 24.8 Recovery Takeover

Recovery mechanisms may be attacked to seize an identity. Recovery authority,
delay, notification, and audit semantics require explicit method-specific
security analysis.

## 25. Conformance

Conformance is declared separately.

### 25.1 Discovery Client Conformance

A conformant Discovery Client:

1. MUST preserve record and descriptor provenance;
2. MUST distinguish discovered claims from verified identity and Evidence;
3. MUST enforce record freshness semantics;
4. MUST treat endpoint addresses as untrusted input;
5. MUST expose structured validation status rather than a single `verified`
   flag;
6. MUST implement the Part A security and privacy requirements applicable to
   its discovery models.

### 25.2 Discovery Provider Conformance

A conformant Discovery Provider:

1. MUST return versioned, attributable Discovery Records;
2. MUST preserve original issuers and source types;
3. MUST distinguish stale, withdrawn, and current records;
4. MUST bound queries, pagination, federation, and amplification;
5. MUST document ranking, recommendation, and retention behavior;
6. MUST not present capability claims or scores as universal trust.

### 25.3 Identity Resolver Conformance

A conformant Identity Resolver:

1. MUST implement a documented Identity Method;
2. MUST return structured source, version, freshness, status, and error data;
3. MUST NOT fall back to an unverified key;
4. MUST enforce verification-purpose semantics;
5. MUST implement method-specific rotation, deactivation, and recovery
   behavior;
6. MUST pass method-specific positive and negative test vectors.

### 25.4 Proof-of-Control Verifier Conformance

A conformant Proof-of-Control Verifier:

1. MUST use fresh, single-use challenges for sensitive establishment;
2. MUST bind proof to verifier, purpose, audience, subject, and expiry;
3. MUST resolve the current authorized Verification Method;
4. MUST reject replay, unauthorized purpose, deactivated identity, and invalid
   proof;
5. MUST record the identity document version and verification time.

An implementation claiming RFC-001 conformance MUST state which of these four
roles it implements.

## 26. Relationship to Other ACF RFCs

- [RFC-000](./000-agent-collaboration-framework.md) defines the framework
  boundary and core object distinctions. Its
  [canonical object relationship map](./000-agent-collaboration-framework.md#724-canonical-object-relationship-map)
  governs how this RFC refines Agent, Principal, Claim, and Evidence.
- RFC-002 requests and exchanges Representation, organization, capability,
  behavior, and other Evidence.
- RFC-003 defines Permission, authority, and delegation.
- RFC-004 binds established identities into Collaboration Sessions.
- RFC-007 maps discovery and identity objects to transports.
- RFC-008 consolidates cross-domain security and composition risks.

## 27. Relationship to Existing AgentNexus Work

| Existing work | Relationship to RFC-001 |
|---|---|
| [ADR-001: DID Format Selection](../../docs/adr/001-did-format-selection.md) | Candidate Identity Method implementation |
| [ADR-009: DID Method Handler Registry](../../docs/adr/009-did-method-handler-registry.md) | Reference pluggable resolver architecture |
| [ADR-010: Platform Adapter and Skill Registry](../../docs/adr/010-platform-adapter-skill-registry.md) | Discovery and declared-capability implementation input |
| [did:agentnexus Method Specification](../../docs/did-method-spec.md) | Candidate method profile; not the only allowed identity technology |
| [DID Resolution Working Group Specification](../working-group/did-resolution.md) | Existing cross-project identity-resolution input |

AgentNexus Relay directories, signed profiles, capability search, presence, and
DID resolution are reference implementations. Their current field names and
transport endpoints are not normative for RFC-001.

## 28. Open Questions

1. Which Identity Methods, if any, are REQUIRED in the baseline profile?
2. Should Discovery Records have a required canonical signed form?
3. Which capability vocabulary registry should be used for interoperable
   search?
4. How should private and authenticated discovery be negotiated?
5. Should pairwise Agent Identifiers be part of the baseline privacy profile?
6. What minimum continuity proof is required for successor identifiers?
7. How are Directory recommendation methods registered and audited?
8. Which liveness and presence semantics belong in RFC-001 versus RFC-004?

## 29. References

### 29.1 Normative References

- [RFC-000: Agent Collaboration Framework Architecture](./000-agent-collaboration-framework.md)
- [RFC 2119: Key words for use in RFCs to Indicate Requirement Levels](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words](https://www.rfc-editor.org/rfc/rfc8174)

### 29.2 Informative References

- [DID Resolution Working Group Specification](../working-group/did-resolution.md)
- [AgentNexus did:agentnexus Method Specification](../../docs/did-method-spec.md)
- [ADR-001: DID Format Selection](../../docs/adr/001-did-format-selection.md)
- [ADR-009: DID Method Handler Registry](../../docs/adr/009-did-method-handler-registry.md)
- [ADR-010: Platform Adapter and Skill Registry](../../docs/adr/010-platform-adapter-skill-registry.md)

## Appendix A. Illustrative Discovery Record

The following example is non-normative:

```json
{
  "record_id": "disc_01J...",
  "query_id": "query_01J...",
  "source": {
    "type": "federated_directory",
    "directory_id": "did:web:directory.example"
  },
  "descriptor": {
    "descriptor_id": "desc_01J...",
    "descriptor_version": "3",
    "agent_id": "did:example:agent-123",
    "identity_ref": "did:example:agent-123",
    "declared_capabilities": [
      {
        "type": "example:medical-record-review",
        "version": "1"
      }
    ],
    "endpoints": [
      {
        "binding": "a2a",
        "uri": "https://agent.example/a2a",
        "acf_versions": ["000-0.2", "001-0.1", "002-0.1"]
      }
    ],
    "updated_at": "2026-07-17T10:00:00Z",
    "expires_at": "2026-07-17T11:00:00Z",
    "issuer": "did:example:agent-123",
    "proof": {"type": "ExampleProof", "value": "..."}
  },
  "retrieved_at": "2026-07-17T10:05:00Z",
  "warnings": ["capability_self_asserted"]
}
```

## Appendix B. Illustrative Proof of Control

The following example is non-normative:

```json
{
  "challenge": {
    "challenge_id": "chal_01J...",
    "verifier": "did:example:receiver",
    "agent_id": "did:example:agent-123",
    "audience": "did:example:receiver",
    "purpose": "authentication",
    "nonce": "base64url-random-value",
    "issued_at": "2026-07-17T10:06:00Z",
    "expires_at": "2026-07-17T10:07:00Z"
  },
  "response": {
    "challenge_id": "chal_01J...",
    "agent_id": "did:example:agent-123",
    "verification_method": "did:example:agent-123#auth-1",
    "proof": {"type": "ExampleSignature", "value": "..."}
  }
}
```
