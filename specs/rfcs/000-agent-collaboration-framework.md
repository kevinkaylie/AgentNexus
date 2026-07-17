# RFC-000: Agent Collaboration Framework Architecture

| Field | Value |
|---|---|
| Status | Draft |
| Category | Foundational |
| Version | 0.1 |
| Created | 2026-07-17 |
| Authors | AgentNexus Contributors |
| Intended audience | Protocol designers, agent runtime implementers, identity and governance providers |
| Updates | None |
| Obsoletes | None |

## Abstract

This document defines the architecture and governing principles of the
Agent Collaboration Framework (ACF).

ACF addresses how independently operated and potentially unfamiliar agents
discover one another, establish identity, request metadata, exchange trust
evidence, negotiate capabilities and authority, establish collaboration
sessions, coordinate work, exchange artifacts, and create auditable records of
responsibility.

ACF is not an agent runtime framework and does not prescribe how an agent
reasons, plans, stores memory, or invokes tools. It is not a transport protocol
and does not replace HTTP, WebSocket, gRPC, message queues, MCP, A2A, or other
delivery mechanisms. It does not define a universal trust score and does not
decide which agents a receiver should trust.

The framework standardizes the information and state transitions required for
trusted and accountable collaboration. Trust remains contextual and belongs to
the receiver. The framework carries verifiable claims and evidence from which
each receiver can make and enforce its own decisions.

## 1. Status of This Memo

This document is a Draft. It establishes the scope and architecture for a
family of more specific RFCs. It does not by itself define a complete wire
protocol.

Existing AgentNexus code and Architecture Decision Records are inputs and
reference implementations. They are not normative sources for this RFC. While
this document remains a Draft, it does not supersede existing ADRs.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and
**OPTIONAL** in this document are to be interpreted as described in
[BCP 14](https://www.rfc-editor.org/info/bcp14) when, and only when, they appear
in all capitals.

## 2. Motivation

Agent interoperability is often framed as a communication problem: assign
addresses, deliver messages, and allow one agent to invoke another. Those
mechanisms are necessary, but they are not sufficient for collaboration among
independently operated agents.

Message delivery answers:

> How can Agent A send data to Agent B?

Collaboration requires additional answers:

- How does Agent A discover an appropriate Agent B?
- How does each party establish control over its claimed identity?
- What metadata does the receiver require for this specific interaction?
- Which claims are supported by verifiable evidence?
- What is the agent able to do, and what is it authorized to do?
- Which constraints apply to the proposed work?
- When does a collaboration relationship begin and end?
- How are tasks, dependencies, artifacts, and outcomes correlated?
- Which actor is accountable for a decision or result?
- How can another party later audit, revoke, challenge, or verify the record?

These are relationship and coordination problems rather than transport
problems.

ACF therefore treats the fundamental unit of interoperability as a
**collaboration relationship**, not a message. A collaboration relationship is
established through explicit intent, receiver-driven requirements, evidence
presentation, local evaluation, negotiated authority, session agreement, and
accountable outcomes.

## 3. Scope

ACF defines a common framework for:

1. discovering agents and their collaboration endpoints;
2. binding agent identifiers to cryptographic control;
3. expressing collaboration intent;
4. allowing receivers to request metadata and evidence;
5. presenting claims, provenance, proofs, and third-party attestations;
6. negotiating capabilities, authority, constraints, and obligations;
7. establishing and managing collaboration sessions;
8. coordinating tasks and artifact handoffs;
9. producing outcome receipts and audit records;
10. binding all of the above to the relevant actors, context, time, and
    collaboration instance.

ACF defines semantic interoperability. Individual RFCs will define the
required object models, state machines, validation rules, error semantics,
security properties, and transport bindings.

## 4. Non-Goals

ACF does not:

1. define an agent's internal reasoning, planning, memory, model, or tool-use
   architecture;
2. define a universal agent runtime or orchestration engine;
3. replace existing network and application transports;
4. mandate a specific DID method, public-key infrastructure, credential
   format, or ledger;
5. define a universal trust score, reputation score, or trust hierarchy;
6. require receivers to disclose their complete decision policies;
7. decide whether a receiver should permit, reject, or constrain an action;
8. guarantee the truth of a claim merely because the claim is well-formed or
   signed;
9. define a single global ontology for every industry or collaboration domain;
10. require natural language as the collaboration format;
11. define a product interface, dashboard, marketplace, or commercial
    operating model.

An implementation MAY provide any of these functions locally. Such functions
are implementation policy and MUST NOT be presented as universal ACF
semantics.

## 5. Architectural Principles

### 5.1 Collaboration, Not Agent Runtime

ACF standardizes relationships between independent agents. It does not
standardize the internal construction of an agent.

An ACF participant MAY be implemented by an LLM agent, deterministic service,
workflow engine, human-operated gateway, software organization, or hybrid
system. Conformance depends on observable protocol behavior, not internal
architecture.

### 5.2 Transport Agnostic

Core ACF objects and state transitions MUST be expressible independently of
HTTP, WebSocket, gRPC, message queues, MCP, A2A, or any other transport.

A transport binding defines how ACF objects are carried over a particular
transport. The binding MUST preserve:

- protocol version;
- object and correlation identifiers;
- actor and subject identifiers;
- semantic field values;
- proof material and proof inputs;
- causality and replay-protection data;
- errors and terminal states.

Transport security MAY protect delivery, but successful transport
authentication MUST NOT be treated as sufficient collaboration trust or
authorization.

### 5.3 Trust Belongs to the Receiver

Trust is a receiver's contextual willingness to accept risk in a proposed
interaction.

ACF MUST NOT define statements such as "`trust = 95`" as universal protocol
truth. A score, grade, recommendation, or decision produced by an evaluator MAY
be carried as evidence, but it MUST identify at least:

- the evaluator or issuer;
- the subject;
- the evaluated context or scope;
- the method or policy version;
- the evaluation time and validity period;
- the evidence inputs or input references when disclosure is permitted;
- the proof or provenance of the assessment.

Different receivers MAY reach different decisions from the same evidence.
This is expected behavior, not a protocol inconsistency.

### 5.4 The Framework Expresses Evidence, Not Trust

ACF defines how claims and evidence are requested, presented, bound, and
verified. Verification establishes properties such as signature validity,
issuer control, freshness, scope, and revocation status. It does not establish
that a receiver must accept the claim or act on it.

A signed assertion proves that the signing issuer made the assertion. It does
not, by itself, prove that the assertion is factually correct.

### 5.5 Decisions Belong to the Receiver

The receiver owns the policy decision.

ACF MAY standardize:

- how a receiver declares evidence requirements;
- how a sender responds to those requirements;
- how validation results are represented;
- how a receiver communicates acceptance, rejection, or conditional
  acceptance;
- how obligations and constraints are attached to an accepted session.

ACF MUST NOT mandate which issuers a receiver trusts, which thresholds it uses,
or which risks it accepts.

A receiver SHOULD be able to keep internal thresholds, weighting, fraud rules,
and other sensitive policy details private. Declaring evidence requirements
does not require disclosing the complete decision function.

### 5.6 Metadata Requirements Are Receiver-Driven

The sender does not unilaterally determine which metadata is sufficient.

The receiver MUST be able to state which metadata and evidence are required
for a particular intent, action, resource, or risk context. Requirements MAY
include:

- required and optional claim types;
- acceptable issuers or issuer classes;
- acceptable proof formats;
- subject and audience bindings;
- freshness and expiration limits;
- revocation requirements;
- required capability or authority scope;
- artifact or payload bindings;
- a receiver-generated nonce or challenge;
- disclosure and privacy constraints.

The sender MAY satisfy, partially satisfy, counter, or decline the request. A
missing or declined item MUST be distinguishable from an invalid item.

### 5.7 Language Is Payload, Not Protocol

Natural language MAY appear in an intent, payload, explanation, artifact, or
human-readable reason. Natural language MUST NOT be the sole representation of
identity, authority, evidence requirements, proof bindings, session state, or
audit-critical outcomes.

Protocol-critical semantics MUST be represented in structured fields with
defined validation rules.

### 5.8 Evidence Must Be Context-Bound

Evidence valid in one context is not automatically valid in another.

Where applicable, evidence and proofs SHOULD be bound to:

- issuer;
- subject;
- intended audience;
- requested action;
- resource or artifact;
- collaboration intent;
- session;
- nonce or challenge;
- issuance time;
- expiration time;
- delegation and constraint scope.

Later RFCs MUST define the exact binding and canonicalization requirements for
each object type.

### 5.9 Capability and Authority Are Distinct

An agent's claimed or demonstrated ability to perform an action is not the
same as authorization to perform that action.

ACF MUST distinguish:

- **capability claim**: the agent claims it can perform an action;
- **capability evidence**: evidence supporting that claim;
- **authority**: permission granted by a principal or policy to perform the
  action;
- **delegation**: transfer of limited authority from one subject to another;
- **constraint**: a bound limit on authority, such as resource, amount, time,
  stage, or purpose.

Delegation MUST NOT expand authority beyond its parent grant.

### 5.10 Accountability Is a First-Class Output

Collaboration produces more than payloads. It produces assertions about what
was requested, authorized, performed, reviewed, accepted, rejected, or
aborted.

ACF sessions SHOULD produce verifiable receipts or equivalent signed records
for audit-relevant events. A receipt is itself an issuer's assertion and MUST
be evaluated as evidence; it is not automatically objective truth.

### 5.11 Minimize Disclosure

Metadata negotiation can expose identity, organization, capability, financial,
health, location, and behavioral information.

Receivers SHOULD request only evidence relevant to the proposed collaboration.
Senders MUST be able to decline excessive requests. Later RFCs SHOULD support
selective disclosure, references, or derived proofs where practical.

### 5.12 Specifications Precede Implementations

Reference implementations are used to test and improve RFCs. They do not
silently define protocol behavior.

Normative protocol behavior MUST be documented in an RFC. An implementation
extension not covered by a ratified RFC MUST be identified as experimental,
implementation-specific, or vendor-specific.

## 6. Terminology

### 6.1 Agent

An independently addressable actor capable of participating in a
collaboration. An agent may represent itself, a human, an organization, or
another principal.

### 6.2 Principal

The person, organization, service, or other authority on whose behalf an agent
acts.

### 6.3 Initiator and Responder

The **Initiator** proposes a collaboration intent. The **Responder** receives
the proposal. Either party may later act as sender or receiver for individual
protocol objects.

### 6.4 Sender and Receiver

The **Sender** transmits a protocol object. The **Receiver** evaluates that
object. These terms are relative to a specific exchange.

### 6.5 Subject

The entity about which a claim or evidence item makes an assertion.

### 6.6 Issuer

The entity that makes and, where applicable, cryptographically signs a claim,
credential, attestation, assessment, or receipt.

### 6.7 Verifier

The component that validates proof, binding, freshness, scope, revocation, and
other objective properties of presented evidence.

### 6.8 Policy Decision Point

The receiver-local component that evaluates verified evidence and local
context to produce a decision such as permit, deny, or conditional permit.

### 6.9 Policy Enforcement Point

The component that enforces a local decision and its obligations.

### 6.10 Collaboration Intent

A structured proposal describing the action, objective, payload or payload
reference, participants, constraints, and time bounds of a desired
collaboration.

### 6.11 Metadata Requirement

A receiver-declared requirement for a claim, evidence type, proof property,
freshness property, capability, authority, or context needed to evaluate a
collaboration intent.

### 6.12 Claim

An assertion made by a subject or issuer. A claim may be unverified, verified,
disputed, expired, or revoked.

### 6.13 Evidence

A claim together with sufficient provenance, proof, observation context, or
supporting material for a verifier and receiver to evaluate it.

Evidence may be first-party, third-party, locally observed, derived, or
historical. Its weight is receiver-specific.

### 6.14 Decision Package

A structured package assembled for a receiver's decision process. It may
contain the collaboration intent, payload or payload reference, identity and
organization claims, capability and authority evidence, provenance, proof,
trace, confidence assessments, and context bindings.

Despite its name, a Decision Package is an input to the receiver's decision.
It does not make the decision and does not require the receiver to disclose its
policy.

### 6.15 Capability

An ability to perform a class of action. Capability may be claimed,
demonstrated, certified, or inferred, but capability does not imply authority.

### 6.16 Authority

Permission to perform an action on a resource or within a scope. Authority is
granted by a principal or derived through a valid delegation chain.

### 6.17 Collaboration Session

A negotiated, bounded relationship among two or more participants for a
specific collaboration intent.

A Collaboration Session is not merely:

- a transport connection;
- an encryption session;
- a chat thread;
- a message correlation identifier;
- an internal workflow run.

It may reference these objects, but it has its own participants, negotiated
conditions, authority, evidence snapshot, lifecycle, and audit context.

### 6.18 Artifact

A content-addressed or otherwise identifiable work product, input, output, or
state object exchanged or referenced during collaboration.

### 6.19 Receipt

A verifiable assertion that an event, review, decision, delivery, acceptance,
rejection, or other outcome occurred according to the issuer.

### 6.20 Trust

A receiver-local, context-specific decision to accept risk. Trust is not a
wire-level scalar and is not globally transferable.

## 7. Framework Model

ACF is organized into seven collaboration domains. These are semantic domains,
not mandatory network layers.

| Domain | Responsibility | Primary question |
|---|---|---|
| D0 Discovery | Locate agents and collaboration endpoints | Who may be relevant and reachable? |
| D1 Identity | Bind identifiers to cryptographic control and principal claims | Who is participating? |
| D2 Requirements and Evidence | Request metadata and present verifiable claims | What does the receiver need to evaluate? |
| D3 Capability and Authority | Negotiate ability, permission, delegation, and constraints | What can and may each party do? |
| D4 Session | Establish and manage the collaboration relationship | Under what agreed context are we collaborating? |
| D5 Coordination and Artifacts | Coordinate actions, state, dependencies, and outputs | How is the work performed and handed off? |
| D6 Accountability | Produce receipts, audit records, revocations, and dispute references | Who is accountable for what happened? |

Transport bindings operate below and across these domains. Evidence and proof
bindings apply across all domains. Receiver-local policy consumes framework
objects but is not standardized as a universal decision function.

```text
┌─────────────────────────────────────────────────────────────┐
│        Independent Agents, Runtimes, and Organizations      │
├─────────────────────────────────────────────────────────────┤
│ D6  Accountability: receipts, audit, revocation, disputes   │
├─────────────────────────────────────────────────────────────┤
│ D5  Coordination: tasks, events, artifacts, outcomes        │
├─────────────────────────────────────────────────────────────┤
│ D4  Collaboration Session: agreement and lifecycle          │
├─────────────────────────────────────────────────────────────┤
│ D3  Capability, authority, delegation, constraints          │
├─────────────────────────────────────────────────────────────┤
│ D2  Metadata requirements and evidence presentation         │
├─────────────────────────────────────────────────────────────┤
│ D1  Identity establishment and principal claims             │
├─────────────────────────────────────────────────────────────┤
│ D0  Discovery and endpoint description                      │
├─────────────────────────────────────────────────────────────┤
│ Transport Bindings: HTTP / WebSocket / MCP / A2A / MQ / ... │
└─────────────────────────────────────────────────────────────┘

       Verified objects ──► Receiver-local policy ──► Enforcement
```

The diagram does not require every interaction to use every domain. A receiver
MAY reuse valid cached evidence, an existing relationship, or a previously
negotiated session. Skipped exchanges MUST NOT weaken required freshness,
binding, authorization, or audit properties.

## 8. Conceptual Protocol Objects

This section defines conceptual objects. It does not define their final wire
encoding.

### 8.1 Collaboration Intent

A Collaboration Intent SHOULD identify:

- intent identifier;
- initiator and intended responder or responder selection criteria;
- requested action or objective;
- payload, payload type, or payload reference;
- requested resources;
- initiator constraints;
- creation and expiration time;
- correlation and replay-protection data;
- proof of origin when required.

An intent is a proposal, not authority to act.

### 8.2 Metadata Requirements

Metadata Requirements SHOULD identify:

- the intent to which the requirements apply;
- the requesting receiver;
- the subject or subjects for which evidence is requested;
- required and optional evidence types;
- accepted issuers, proof formats, or trust registries where applicable;
- freshness, expiration, and revocation requirements;
- action, audience, artifact, or session binding requirements;
- challenge nonce;
- response deadline;
- privacy or disclosure constraints.

Requirements MUST distinguish protocol requirements from private receiver
policy. A receiver is not required to publish the latter.

### 8.3 Evidence Item

An Evidence Item SHOULD be capable of expressing:

- evidence type and schema version;
- issuer;
- subject;
- claims;
- source or provenance;
- proof and proof method;
- issuance, observation, and expiration time;
- scope and context;
- intended audience;
- revocation mechanism or status reference;
- trace references;
- confidence assessment, including who produced the assessment, what it refers
  to, and which method was used.

An Evidence Item MUST NOT be considered valid only because required fields are
present. Each evidence type requires its own validation procedure.

### 8.4 Decision Package

A Decision Package SHOULD be able to combine:

- the related Collaboration Intent;
- the payload or immutable payload reference;
- subject identity evidence;
- organization or principal relationship evidence;
- capability claims and supporting evidence;
- authority and delegation evidence;
- requested source and provenance records;
- evidence satisfying each declared Metadata Requirement;
- sender-declared constraints and policy references;
- context, audience, time, nonce, and artifact bindings;
- trace and correlation information;
- package-level proof.

A field named `policy` in a Decision Package MUST identify sender-declared
constraints, an applicable public policy, or a policy reference. It MUST NOT be
interpreted as the receiver's private decision function.

### 8.5 Session Agreement

A Session Agreement SHOULD identify:

- session identifier;
- participants and represented principals;
- related intent;
- accepted protocol and schema versions;
- negotiated capabilities and authority;
- constraints and obligations;
- evidence snapshot or evidence references used to establish the session;
- permitted actions and resources as granted by the relevant principals;
- validity and renewal conditions;
- termination and revocation mechanisms;
- transport binding references, if any;
- proofs of agreement required by the session policy.

A Session Agreement does not imply unlimited trust outside its scope.

### 8.6 Collaboration Event

A Collaboration Event SHOULD identify:

- session and event identifiers;
- actor;
- event type;
- related task, action, artifact, or prior event;
- causal and temporal ordering information;
- payload or payload reference;
- applicable authority reference;
- proof when required.

### 8.7 Artifact Manifest

An Artifact Manifest SHOULD identify:

- artifact identifier and media or schema type;
- content hash or content-addressed reference;
- producer;
- related session, task, and event;
- provenance and source inputs;
- creation time;
- confidentiality and access constraints;
- optional validation or review evidence.

Large artifacts SHOULD be referenced rather than embedded when transport or
privacy constraints make embedding inappropriate.

### 8.8 Receipt

A Receipt SHOULD identify:

- receipt type and identifier;
- issuer;
- subject, actor, or responsible party;
- related session, intent, event, decision, or artifact;
- asserted outcome;
- evidence and artifact references;
- issuance and expiration time when applicable;
- proof and proof method;
- revocation or correction reference when applicable.

Receipt verification establishes who issued the receipt and whether it was
altered. Acceptance of the receipt's assertion remains receiver-specific.

## 9. Collaboration Lifecycle

The canonical high-level lifecycle is:

```text
Discover
  → Establish Identity
  → Propose Collaboration Intent
  → Request Metadata and Evidence
  → Present Decision Package
  → Perform Receiver-Local Evaluation
  → Negotiate Capability, Authority, and Constraints
  → Establish Collaboration Session
  → Coordinate Work and Exchange Artifacts
  → Produce Outcome Receipts
  → Complete, Abort, Expire, or Revoke Session
  → Retain or Disclose Audit Record According to Policy
```

Identity establishment MUST NOT be interpreted as trust, capability,
authority, or session acceptance.

Evidence validation and receiver-local evaluation MAY occur repeatedly during
a session. Long-running sessions SHOULD support re-evaluation when:

- evidence expires or is revoked;
- keys rotate;
- authority changes;
- the requested action or resource changes;
- risk context changes;
- session constraints are exceeded;
- a participant resumes after suspension or loss of liveness.

### 9.1 Session States

Later RFCs SHOULD define a state machine compatible with at least:

- `proposed`;
- `requirements_pending`;
- `evidence_pending`;
- `negotiating`;
- `active`;
- `suspended`;
- `closing`;
- `completed`;
- `aborted`;
- `expired`;
- `revoked`.

Not every local policy decision must be disclosed. A receiver MAY return a
minimal protocol reason such as `policy_rejected` without exposing sensitive
decision rules.

### 9.2 Multi-Party Collaboration

Multi-party sessions MUST NOT assume that evidence accepted by one participant
is accepted by all others.

Each participant MAY:

- declare different Metadata Requirements;
- accept different issuers;
- grant different authority;
- apply different local policy;
- require different receipts.

A multi-party Session Agreement MUST make participant-specific grants,
constraints, and obligations unambiguous.

## 10. Validation and Local Decision Separation

Implementations SHOULD separate four stages:

```text
Parse
  → Verify
  → Evaluate
  → Enforce
```

### 10.1 Parse

Parsing determines whether an object is structurally well-formed and supported
by the implementation.

### 10.2 Verify

Verification evaluates objective protocol properties, including:

- proof correctness;
- issuer and subject binding;
- key resolution;
- freshness;
- expiration;
- revocation;
- audience and context binding;
- delegation-chain integrity;
- artifact or payload hash binding.

Verification SHOULD produce structured results rather than a single trust
score.

### 10.3 Evaluate

Evaluation applies receiver-local policy to verified and unverified evidence,
local observations, risk context, and requested action.

Evaluation MAY produce:

- permit;
- deny;
- conditional permit;
- request for additional evidence;
- human or external review;
- reduced scope;
- rate, cost, time, or resource constraints.

### 10.4 Enforce

Enforcement applies the local decision at the relevant action boundary.

An implementation MUST NOT treat successful parsing or signature verification
as equivalent to authorization.

## 11. Failure Semantics

Later RFCs SHOULD define machine-readable failure classes including:

- `unsupported_version`;
- `unsupported_object_type`;
- `malformed_object`;
- `identity_unresolved`;
- `proof_missing`;
- `proof_invalid`;
- `evidence_missing`;
- `evidence_invalid`;
- `evidence_expired`;
- `evidence_revoked`;
- `requirements_unsatisfied`;
- `privacy_declined`;
- `capability_mismatch`;
- `authority_insufficient`;
- `delegation_invalid`;
- `constraint_conflict`;
- `policy_rejected`;
- `session_conflict`;
- `session_expired`;
- `session_revoked`;
- `transport_binding_failure`.

Failure responses SHOULD reveal enough information for interoperability while
avoiding disclosure of private policy, sensitive metadata, or exploitable
security details.

## 12. Transport Bindings

An ACF transport binding specifies:

- how protocol objects are encoded and carried;
- endpoint discovery rules;
- request-response, asynchronous, and streaming mappings;
- delivery acknowledgement semantics;
- correlation and idempotency behavior;
- size and fragmentation limits;
- proof preservation;
- transport-specific authentication and confidentiality assumptions;
- retry and duplicate-delivery behavior;
- mapping of framework errors to transport errors.

ACF allows different transports within the same collaboration. For example,
metadata negotiation may use HTTP, task delivery may use a message queue, and
artifacts may use content-addressed storage.

Transport changes MUST NOT silently change session identity, evidence binding,
authority scope, or audit continuity.

## 13. Security and Privacy Considerations

Every ACF RFC MUST include security and privacy considerations appropriate to
its domain.

### 13.1 Impersonation and Key Substitution

Identifier resolution MUST be bound to proof of control. Implementations MUST
handle key rotation and MUST NOT silently accept an unrelated replacement key.

### 13.2 Replay

Time-sensitive objects SHOULD include nonces, timestamps, expiration, unique
identifiers, and audience or session binding as appropriate. Duplicate
processing MUST be detectable at action boundaries.

### 13.3 Evidence Transplant

An attacker may copy valid evidence from one subject, action, audience,
artifact, or session into another context. Proof inputs MUST bind all
security-relevant context required to prevent such reuse.

### 13.4 Sybil Identities

Cryptographic control of an identifier does not establish uniqueness,
reputation, legal identity, or organizational affiliation. Receivers MUST NOT
infer these properties from a valid self-generated identifier alone.

### 13.5 Confused Deputy and Delegation Expansion

Authority tokens and delegations MUST identify the intended subject, audience,
action, resource, and constraints. Derived delegation MUST be monotonically
narrower than its parent authority.

### 13.6 Stale and Revoked Evidence

Receivers SHOULD define freshness and revocation requirements according to
risk. If revocation status cannot be determined, fail-open or fail-closed
behavior is a local policy choice, but the uncertainty MUST be explicit and
SHOULD be auditable.

### 13.7 Metadata Fishing

A malicious responder may request excessive metadata in order to profile or
de-anonymize an agent or principal. Senders MUST be able to decline, minimize,
or selectively disclose requested information.

### 13.8 Policy Probing

Detailed rejection reasons may allow attackers to infer and game receiver
policy. Protocol errors SHOULD distinguish interoperability failures from
local policy rejection without requiring disclosure of the complete policy.

### 13.9 Collusion and Reputation Laundering

Multiple issuers or agents may collude to generate misleading attestations,
endorsements, or receipts. ACF does not solve this through a universal score.
Receivers SHOULD evaluate issuer independence, provenance, context, and
conflicts of interest.

### 13.10 Receipt Forgery and Overclaiming

Receipts MUST use defined canonicalization and proof rules before they can be
treated as verifiable. A valid signature proves issuance, not factual
correctness or fairness.

### 13.11 Audit Privacy

Audit records can expose sensitive objectives, relationships, resources, and
behavior. Implementations SHOULD support retention limits, access control,
redaction, encrypted storage, and reference-based disclosure.

### 13.12 Transport Downgrade

Negotiation over a weaker transport MUST NOT silently remove required proof,
confidentiality, freshness, or identity properties. Binding negotiation SHOULD
be downgrade-resistant.

## 14. Extensibility and Versioning

ACF requires a small interoperable semantic core and extensible domain
vocabularies.

Future RFCs SHOULD define:

- version negotiation;
- namespaced extensions;
- critical versus non-critical fields;
- behavior for unknown fields and object types;
- registries for evidence, capability, receipt, and error types;
- deterministic canonicalization for signed objects.

An implementation MUST reject an unknown critical extension. It MAY preserve
and forward unknown non-critical extensions when doing so does not create a
security or privacy violation.

Domain-specific profiles, such as healthcare, finance, software delivery, or
scientific research, MAY define additional evidence requirements and receipt
types. Such profiles MUST NOT redefine the core distinction between evidence
and receiver-local decision.

## 15. Relationship to Existing AgentNexus Work

Existing AgentNexus work remains useful as implementation experience. This RFC
reclassifies its role in the future specification process.

| Existing work | Relationship to ACF |
|---|---|
| [ADR-001: DID Format Selection](../../docs/adr/001-did-format-selection.md) | Candidate identity implementation and input to RFC-001 |
| [ADR-002: Four-Step Handshake](../../docs/adr/002-four-step-handshake.md) | Secure-channel mechanism and possible transport/security binding; not metadata or trust negotiation |
| [ADR-004: Multi-CA Certification](../../docs/adr/004-multi-ca-certification.md) | Certification evidence source; L1-L4 and spending limits are local policy |
| [ADR-005: Gatekeeper](../../docs/adr/005-gatekeeper-three-modes.md) | Example receiver-local policy decision and enforcement mechanism |
| [ADR-007: Action Layer](../../docs/adr/007-action-layer-protocol.md) | Structured collaboration-message experiment and input to RFC-005 |
| [ADR-012: ACP Communication Stack](../../docs/adr/012-push-gateway-and-mcp-collaboration.md) | Historical implementation layering; transport, delivery, and collaboration semantics require separation under ACF |
| [ADR-013: Enclave Collaboration](../../docs/adr/013-enclave-collaboration-architecture.md) | Reference orchestration and artifact-management model; not a universal framework requirement |
| [ADR-014: Governance and Trust Network](../../docs/adr/014-governance-trust-network.md) | Attestations, endorsements, and behavior records are evidence sources; trust scores remain evaluator-specific |
| [DID Resolution Working Group Specification](../working-group/did-resolution.md) | Existing cross-project identity-resolution input to RFC-001 |

Existing AgentNexus modules for routing, handshakes, trust graphs, reputation,
capability tokens, coordination sessions, artifacts, and receipts MAY be
adapted as reference implementations. Conformance will be measured against
ratified RFCs rather than current module behavior.

## 16. RFC Family

The initial ACF RFC family is:

| RFC | Working title | Scope |
|---|---|---|
| RFC-000 | Agent Collaboration Framework Architecture | Principles, roles, domains, lifecycle, and governance |
| RFC-001 | Agent Discovery and Identity | Discovery documents, identifiers, endpoint description, proof of control |
| RFC-002 | Metadata Requirements and Trust Evidence Negotiation | Collaboration Intent, Metadata Requirements, Evidence Items, Decision Package |
| RFC-003 | Capability Negotiation and Delegation | Capability claims, authority, delegation, constraints, obligations |
| RFC-004 | Collaboration Session Lifecycle | Session proposal, agreement, activation, renewal, suspension, termination |
| RFC-005 | Task Coordination and Artifact Handoff | Tasks, events, dependencies, artifact manifests, handoff semantics |
| RFC-006 | Outcome Receipts and Accountability | Signed receipts, audit records, correction, revocation, dispute references |
| RFC-007 | Transport Bindings and Interoperability | HTTP, WebSocket, MCP, A2A, queues, and cross-transport continuity |
| RFC-008 | Security, Privacy, and Threat Model | Cross-cutting threats, privacy properties, and required mitigations |

RFC numbers and titles after RFC-000 remain provisional until their first
Draft is accepted.

## 17. Conformance

RFC-000 defines architectural conformance, not full wire conformance.

An implementation or specification claiming alignment with RFC-000:

1. MUST separate transport from core collaboration semantics;
2. MUST distinguish identity proof, capability, authority, evidence, trust,
   decision, and enforcement;
3. MUST NOT present a universal trust score as protocol truth;
4. MUST allow the receiver to declare context-specific metadata requirements;
5. MUST treat the Decision Package as input to a receiver-local decision;
6. MUST bind security-relevant evidence to the required subject, audience,
   action, context, time, and session;
7. MUST represent collaboration session scope and lifecycle explicitly;
8. MUST support accountable outcome records for audit-relevant collaboration;
9. MUST document security, privacy, revocation, and failure behavior;
10. MUST identify which specific ACF RFC versions it implements.

No implementation may claim complete ACF conformance until the relevant
wire-level RFCs and conformance tests exist.

## 18. Specification Governance

ACF documents use the following lifecycle:

```text
Proposal → Draft → Review → Candidate → Ratified
                                      ↘ Deprecated → Obsoleted
```

- **Proposal**: problem statement and initial direction.
- **Draft**: sufficiently complete for technical review and experiments.
- **Review**: active cross-implementation review with unresolved issues
  tracked.
- **Candidate**: semantics are stable; conformance work is in progress.
- **Ratified**: approved and supported by required interoperability evidence.
- **Deprecated**: retained for compatibility but not recommended.
- **Obsoleted**: replaced by another RFC.

Wire-level RFCs SHOULD have:

- at least two independently developed interoperable implementations;
- machine-readable schemas where applicable;
- conformance tests and negative test vectors;
- documented security review;
- no unresolved blocking issue;

before Ratification.

Reference implementation behavior that differs from a Ratified RFC MUST be
treated as an implementation defect or documented extension, not as an
implicit amendment to the RFC.

## 19. Future Agent Society Work

ACF defines primitives for establishing bounded collaboration relationships.
An eventual Agent Society Framework may build on these primitives to study:

- persistent relationships and institutions;
- governance and collective decision procedures;
- markets and economic coordination;
- norms, sanctions, and dispute resolution;
- portable reputation evidence;
- organizational membership and representation;
- public-interest and regulatory constraints.

Such a framework remains outside the scope of RFC-000.

Agent society MUST NOT require a single global trust authority or a universal
reputation score. Society-level systems should preserve receiver sovereignty,
evidence provenance, contextual decisions, and accountable outcomes.

## 20. Open Questions

The following questions are intentionally deferred:

1. What is the final name and namespace of the wire protocol suite?
2. Which identity methods are REQUIRED for baseline interoperability?
3. Which canonical serialization and proof suites are REQUIRED?
4. How are evidence-type and receipt-type registries governed?
5. How should selective disclosure and zero-knowledge proofs be integrated?
6. How should multi-party Metadata Requirements be combined or kept
   participant-specific?
7. Which session-resumption and liveness properties are mandatory?
8. How are cross-issuer revocation and key rotation discovered?
9. Which minimal rejection reasons provide interoperability without enabling
   policy probing?
10. What evidence is required before an outcome receipt may be treated as
    independently auditable?

These questions are expected to be resolved by subsequent RFCs and do not
change the architectural separation established here.

## 21. References

### 21.1 Normative References

- [RFC 2119: Key words for use in RFCs to Indicate Requirement Levels](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words](https://www.rfc-editor.org/rfc/rfc8174)

### 21.2 Informative References

- [AgentNexus Architecture](../../docs/architecture.md)
- [AgentNexus Security Policy](../../SECURITY.md)
- [ADR-001: DID Format Selection](../../docs/adr/001-did-format-selection.md)
- [ADR-002: Four-Step Handshake](../../docs/adr/002-four-step-handshake.md)
- [ADR-004: Multi-CA Certification](../../docs/adr/004-multi-ca-certification.md)
- [ADR-005: Gatekeeper Three Modes](../../docs/adr/005-gatekeeper-three-modes.md)
- [ADR-007: Action Layer Protocol](../../docs/adr/007-action-layer-protocol.md)
- [ADR-012: AgentNexus Communication Protocol](../../docs/adr/012-push-gateway-and-mcp-collaboration.md)
- [ADR-013: Enclave Collaboration Architecture](../../docs/adr/013-enclave-collaboration-architecture.md)
- [ADR-014: Governance Attestation and Trust Network](../../docs/adr/014-governance-trust-network.md)
- [DID Resolution Working Group Specification](../working-group/did-resolution.md)

## Appendix A. Foundational Thesis

The framework can be summarized as:

> Agent collaboration begins when independently operated agents can negotiate
> the evidence, authority, constraints, and accountability required to pursue
> a shared intent.

And its trust boundary as:

> ACF does not create trust and does not decide whom to trust. It enables each
> receiver to request, verify, and retain the evidence needed to make its own
> contextual decision.

## Appendix B. Example Abstract Exchange

The following is illustrative and non-normative:

```text
Initiator
  → Collaboration Intent:
      "Review medical record R under purpose P"

Responder
  → Metadata Requirements:
      - proof of requesting organization
      - delegated authority for record R
      - accepted medical-review capability evidence
      - purpose and retention constraints
      - receiver challenge nonce

Initiator
  → Decision Package:
      - identity proof
      - organization credential
      - scoped delegation
      - capability attestation
      - provenance and validity data
      - proof bound to R, P, responder, nonce, and expiration

Responder
  → local verification and policy evaluation
  → conditional acceptance:
      - read-only access
      - no onward delegation
      - session expires in 30 minutes
      - signed review receipt required

Both parties
  → Session Agreement
  → Artifact exchange and collaboration events
  → Signed outcome receipt
  → Session completion
```

The same framework can support banking, software delivery, procurement,
research, customer support, or other domains by changing evidence requirements
and local policy rather than changing the foundational collaboration model.
