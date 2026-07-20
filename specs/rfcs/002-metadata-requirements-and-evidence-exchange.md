# RFC-002: Metadata Requirements and Evidence Exchange

| Field | Value |
|---|---|
| Status | Draft |
| Category | Standards Track |
| Version | 0.1 |
| Created | 2026-07-17 |
| Authors | AgentNexus Contributors |
| Requires | RFC-000, RFC-001 Part B |
| Updates | None |
| Obsoletes | None |

## Abstract

This document defines receiver-driven metadata requirements and structured
evidence exchange for the Agent Collaboration Framework (ACF).

An initiator proposes a Collaboration Intent. The receiver declares which
metadata and evidence it requires for that specific intent, action, resource,
and risk context. The sender responds with per-requirement statuses and a
Decision Package containing Evidence Items or immutable references. The
receiver verifies the package and applies its own local Policy.

This RFC standardizes evidence expression, request, exchange, binding,
verification results, and negotiation state. It does not define domain truth,
a universal trust score, or the receiver's decision policy.

> The framework standardizes evidence exchange, not trust decisions.

## 1. Status and Normative Language

This document is a Draft. JSON examples are illustrative unless a later
version explicitly marks a schema as normative.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and
**OPTIONAL** in this document are to be interpreted as described in
[BCP 14](https://www.rfc-editor.org/info/bcp14) when, and only when, they appear
in all capitals.

## 2. Scope

RFC-002 defines:

- Collaboration Intent semantics required to begin evidence negotiation;
- receiver-authored Metadata Requirements;
- Requirement Items and alternative satisfaction rules;
- Evidence Items;
- per-requirement response status;
- Decision Package composition;
- evidence provenance, source, confidence, score, and binding semantics;
- structured verification results;
- negotiation revision and termination;
- privacy-preserving decline and selective-disclosure behavior;
- evidence-exchange security properties and failure classes.

RFC-002 does not:

- define which Evidence is sufficient for a receiver;
- define which issuers are trusted;
- define a universal Trust Score or reputation algorithm;
- automatically convert an attestation or score into Permission;
- define the full capability and delegation model of RFC-003;
- establish the Collaboration Session defined by RFC-004;
- define industry requirements for healthcare, finance, law, insurance, or
  other domains;
- require disclosure of private Policy or model chain-of-thought;
- guarantee that a validly issued Claim is factually true.

## 3. Governing Model

The governing sequence is:

```text
Initiator
  → Collaboration Intent

Receiver
  → Metadata Requirements

Sender
  → Requirement Responses + Decision Package

Receiver
  → Parse → Verify → Local Policy Evaluation
  → requirements accepted
     | additional requirements
     | conditionally accepted
     | rejected
```

The receiver determines what it needs. The sender determines what it is
willing and able to disclose. The protocol standardizes the negotiation and
its evidence; it does not force agreement.

## 4. Roles

### 4.1 Initiator

The participant that proposes the Collaboration Intent.

### 4.2 Requirements Issuer

The receiver that issues Metadata Requirements. It is normally the intended
responder or a receiver-authorized policy service.

### 4.3 Evidence Presenter

The participant that assembles and presents Evidence. It may be the Initiator,
another Agent, a Principal, or an authorized intermediary.

### 4.4 Evidence Issuer

The entity that originally makes an Evidence Claim or assessment.

### 4.5 Evidence Subject

The Agent, Principal, organization, artifact, event, capability, or other
entity about which the Evidence makes a Claim.

### 4.6 Verifier

The component that evaluates protocol-verifiable properties such as proof,
issuer control, binding, freshness, and revocation.

### 4.7 Receiver Policy Decision Point

The receiver-local component that decides whether verified and unverified
Evidence is sufficient. This role is outside the normative evidence-exchange
decision logic.

## 5. Required Distinctions

Implementations MUST preserve:

```text
Requirement       ≠ Policy
Claim             ≠ Evidence
Evidence validity ≠ domain truth
Evidence score    ≠ universal trust
Package accepted  ≠ globally trusted
Package accepted  ≠ Permission granted
```

A Requirement is the receiver's disclosed condition for an exchange. A Policy
is the receiver's local rule set used to generate Requirements and make
decisions.

## 6. Negotiation Lifecycle

The abstract state machine is:

```text
intent_proposed
  → requirements_issued
  → evidence_pending
  → package_presented
  → verification_complete
  → requirements_accepted
      | additional_requirements
      | conditionally_accepted
      | rejected
      | expired
      | cancelled
```

`verification_complete` is not a trust decision. It means that the verifier
has produced structured results.

A receiver MAY issue no additional Requirements and evaluate an initial
package directly. A sender MAY attach unsolicited Evidence to a Collaboration
Intent, but the receiver remains free to request different or additional
Evidence.

## 7. Collaboration Intent

A Collaboration Intent starts an evidence-negotiation context.

It SHOULD identify:

- `intent_id`;
- schema and protocol version;
- initiator Agent Identifier;
- represented Principal, if relevant;
- intended receiver or receiver-selection criteria;
- requested objective or action;
- resource, artifact, or payload reference;
- purpose;
- initiator-declared constraints;
- requested capability or authority references;
- creation and expiration time;
- unique nonce or replay-protection value;
- trace and correlation references;
- proof of origin when required.

The Intent MUST distinguish:

- natural-language explanation;
- structured action or objective;
- immutable payload or artifact references;
- sender-declared constraints.

Natural language MUST NOT be the only representation of security-critical
action, subject, resource, purpose, or validity.

## 8. Metadata Requirements

A Metadata Requirements object SHOULD identify:

- `requirements_id`;
- schema and protocol version;
- related `intent_id`;
- Requirements Issuer;
- intended Evidence Presenter;
- subjects to which requirements apply;
- ordered or unordered Requirement Items;
- challenge nonce;
- creation and expiration time;
- response deadline;
- maximum negotiation rounds, if bounded;
- purpose and optional retention statement;
- package proof requirements;
- proof of origin.

Requirements MUST be versioned. A material change MUST produce a new version
or identifier and MUST NOT silently reuse an old requirements hash.

### 8.1 Requirements Hash

A requirements profile SHOULD define a deterministic hash over all
security-relevant Requirement fields.

The Decision Package MUST bind to the exact Requirements version or hash it
answers. This prevents the presenter or receiver from later substituting a
different requirement set.

### 8.2 Policy Privacy

Metadata Requirements are a public projection of receiver Policy. The receiver
MUST NOT be required to reveal:

- internal weights or thresholds;
- fraud indicators;
- private issuer blocklists;
- model internals;
- human-review rules;
- other sensitive decision logic.

A receiver SHOULD reveal enough information for an honest presenter to
construct an interoperable response.

## 9. Requirement Item

A Requirement Item SHOULD support:

- `requirement_id`;
- requirement type;
- target subject;
- requested Claim or Evidence schema;
- required, optional, or advisory criticality;
- accepted Evidence formats;
- acceptable issuer identifiers or issuer classes, when disclosed;
- accepted proof methods or proof properties;
- freshness and maximum-age rules;
- expiration requirements;
- revocation-check requirements;
- subject, audience, action, resource, artifact, intent, and session bindings;
- cardinality;
- `all_of`, `any_of`, or alternative satisfaction groups;
- selective-disclosure or derived-proof allowance;
- purpose or human-readable rationale;
- data-retention or onward-disclosure constraints;
- extension fields.

### 9.1 Criticality

The following criticality values are defined:

- `required`: absence prevents satisfaction;
- `optional`: absence does not prevent satisfaction;
- `advisory`: supplied for information and MUST NOT be silently treated as
  required.

### 9.2 Alternatives

A receiver SHOULD use explicit alternatives when multiple Evidence forms can
satisfy the same need.

For example:

```text
any_of:
  - organization credential issued by an accepted registry
  - signed Principal representation attestation
  - receiver-authorized manual review
```

The presence of alternatives does not require disclosure of internal Policy
weights.

### 9.3 Requirement Purpose

Requirements involving sensitive data SHOULD include a purpose and retention
statement. A sender MAY decline a Requirement whose purpose is absent,
incompatible, excessive, or unverifiable.

## 10. Evidence Item

An Evidence Item SHOULD support:

- `evidence_id`;
- Evidence type and schema version;
- issuer;
- subject;
- Claims;
- source and provenance;
- proof and proof method;
- issuance, observation, and expiration time;
- revocation mechanism or status reference;
- action, audience, resource, artifact, intent, and session bindings;
- Evidence payload or immutable reference;
- trace references;
- structured confidence or score assessment, if present;
- disclosure limitations;
- extension fields.

An Evidence Item MUST identify which Claim or Claims are covered by its proof.

### 10.1 Evidence Classes

RFC-002 permits, but does not mandate, Evidence classes including:

- Agent identity-control results from RFC-001;
- Principal representation or organization affiliation;
- professional, regulatory, or compliance credentials;
- capability claims and capability assessments;
- authority or delegation references from RFC-003;
- source and artifact provenance;
- behavior observations;
- outcome attestations or receipts;
- liveness or presence observations;
- risk assessments;
- evaluator-generated scores or grades.

The receiver determines which classes and issuers are acceptable.

### 10.2 First-Party Evidence

Evidence issued by the subject or presenter MUST be marked as first-party or
self-asserted. A valid first-party proof establishes authorship and integrity,
not independent corroboration.

### 10.3 Third-Party Evidence

Third-party Evidence MUST preserve the original issuer and proof. An
intermediary MUST NOT replace the original issuer identity with its own unless
it is issuing a distinct derived assessment.

### 10.4 Locally Observed Evidence

A receiver may use local observations that are never transmitted. If a local
observation is exported, it becomes an Evidence Item issued by the observer
and SHOULD include observation method, time, context, and limitations.

### 10.5 Derived Evidence

An evaluator may derive an assessment from other Evidence. Derived Evidence
SHOULD identify:

- evaluator;
- method and version;
- evaluated scope and context;
- input Evidence identifiers or hashes where disclosure is allowed;
- evaluation time and validity;
- result and limitations;
- proof.

Derived Evidence does not replace its inputs unless the receiver's Policy
explicitly allows that substitution.

## 11. Source and Provenance

A `source` field MUST distinguish at least:

- origin of the underlying information;
- issuer of the Evidence;
- presenter of the Evidence;
- retrieval or mediation service;
- transformation or evaluation steps.

A URL alone is not sufficient provenance.

Evidence carried by reference MUST include an immutable content hash, immutable
version, or equivalent integrity binding. A mutable reference without an
integrity binding MUST NOT satisfy a Requirement that demands reproducible
verification.

## 12. Confidence, Scores, and Grades

Confidence, score, grade, risk, reputation, and trust-related values are
Claims.

Such an assessment MUST identify:

- evaluator or issuer;
- subject and target Claim;
- scale, range, and unit;
- method and version;
- evaluated context and scope;
- input Evidence references where disclosure is permitted;
- issuance and expiration time;
- proof or provenance;
- known limitations or calibration reference where applicable.

Scores from different evaluators or methods MUST NOT be assumed comparable.
RFC-002 defines no automatic `trust_delta`, permission upgrade, spending limit,
or trust-level mapping.

## 13. Requirement Response

The presenter MUST provide a response for each required Requirement Item.

The following statuses are defined:

- `satisfied`;
- `partially_satisfied`;
- `unavailable`;
- `declined`;
- `unsupported`;
- `not_applicable`.

Each response SHOULD identify:

- `requirement_id`;
- status;
- Evidence identifiers or references;
- disclosed fields;
- presenter constraint or counterproposal, if any;
- machine-readable reason class;
- optional human-readable explanation.

`unavailable`, `declined`, `unsupported`, and `invalid` are distinct.
`invalid` is a verifier-assigned outcome rather than a presenter response
status:

- `unavailable`: the presenter cannot currently obtain the Evidence;
- `declined`: the presenter chooses not to disclose it;
- `unsupported`: the presenter cannot process the Requirement type;
- `invalid`: the presented Evidence failed verification.

The presenter SHOULD NOT fabricate an empty Evidence Item to represent
missing Evidence.

## 14. Decision Package

A Decision Package is the complete presenter response for a Requirements
version.

It SHOULD identify:

- `package_id`;
- schema and protocol version;
- presenter;
- related `intent_id`;
- related `requirements_id` and requirements hash;
- intended receiver and audience;
- Requirement Responses;
- included Evidence Items;
- immutable external Evidence references;
- payload or artifact hash when evidence is bound to content;
- capability or authority references, when applicable;
- sender-declared constraints and public Policy references;
- challenge nonce;
- creation and expiration time;
- trace and correlation data;
- package-level proof.

A Decision Package MUST NOT contain a field that claims to be the receiver's
private Policy.

### 14.1 Package Binding

For a security-sensitive exchange, the package proof SHOULD bind:

- presenter;
- receiver and audience;
- `intent_id`;
- Requirements identifier and hash;
- challenge nonce;
- payload or artifact hash;
- Evidence identifiers or hashes;
- creation and expiration time.

This binding prevents a valid package from being transplanted into another
intent, receiver, artifact, or requirements set.

### 14.2 Package Completeness

Package completeness is evaluated against the referenced Requirements version.
A package may be complete while containing Evidence that later fails
verification. Completeness and validity MUST remain separate statuses.

## 15. Verification Result

A Verifier SHOULD produce structured results for:

- package syntax;
- package proof;
- requirements-hash binding;
- intent binding;
- presenter and audience binding;
- challenge freshness and replay status;
- Evidence schema;
- Evidence proof;
- issuer resolution and control;
- subject binding;
- artifact or payload binding;
- freshness and expiration;
- revocation status;
- unsupported critical fields;
- warnings and indeterminate checks.

A Verification Result SHOULD identify:

- verifier;
- verification method and version;
- verification time;
- input package and Evidence hashes;
- status for each check;
- reason classes;
- uncertainty or unavailable checks;
- proof if the result is later shared as Evidence.

A single boolean `valid` is insufficient for local Policy evaluation and
audit.

## 16. Receiver-Local Evaluation and Signaling

After verification, the receiver applies local Policy.

The protocol MAY signal:

- `requirements_accepted`;
- `additional_requirements`;
- `conditionally_accepted`;
- `rejected`;
- `expired`;
- `cancelled`.

These signals apply only to the related intent and requirements exchange.

`requirements_accepted` means the receiver considers the package sufficient to
continue to the next protocol step. It does not mean:

- global trust;
- verified competence for every task;
- Permission has been granted;
- a Collaboration Session exists;
- a business result has been accepted.

The receiver MAY return `policy_rejected` without revealing the private rule
that caused rejection.

## 17. Revisions and Bounded Negotiation

Either party may revise its proposal:

- the receiver may issue additional or alternative Requirements;
- the presenter may submit a new package;
- the presenter may counter a disclosure or constraint;
- either party may cancel.

Every revision MUST have a new version or identifier and MUST reference its
predecessor.

Implementations SHOULD bound:

- negotiation rounds;
- package size;
- number of Evidence Items;
- reference-fetch depth;
- verification work;
- expiration time.

Exceeding a bound SHOULD produce an explicit failure or escalation rather than
an unbounded negotiation loop.

## 18. Selective Disclosure and Data Minimization

Receivers SHOULD request the minimum Evidence necessary for the action and
risk context.

Requirement profiles SHOULD allow:

- field-level disclosure;
- derived predicates;
- redacted credentials;
- proof by reference;
- alternative Evidence;
- receiver-authorized manual review.

The presenter MAY refuse a requirement that would expose:

- unrelated personal or organizational data;
- private model reasoning;
- secrets or credentials;
- unrelated collaboration history;
- excessive behavioral history;
- data incompatible with declared purpose or retention.

A selective-disclosure proof proves only its defined predicate. Receivers MUST
NOT infer undisclosed fields.

## 19. Freshness, Expiration, Revocation, and Correction

Each Requirement MAY define maximum age and revocation-check behavior.

Evidence status SHOULD distinguish:

- `current`;
- `expired`;
- `revoked`;
- `corrected`;
- `superseded`;
- `status_unknown`;
- `status_unavailable`.

If status cannot be checked, the Verifier MUST report uncertainty. Whether to
fail open, fail closed, request additional Evidence, or escalate is receiver
Policy.

A corrected Evidence Item SHOULD reference the superseded item. Correction
MUST NOT erase the audit existence of the earlier item where retention is
legally and operationally permitted.

## 20. Canonicalization and Proof Profiles

RFC-002 does not mandate one cryptographic suite in this Draft. A conformant
wire profile MUST define:

- deterministic canonicalization;
- hash algorithm;
- proof suite;
- key and issuer resolution;
- proof input fields;
- detached or embedded proof behavior;
- critical-field handling;
- algorithm-agility and downgrade rules.

Transport serialization MUST NOT change the bytes or semantic object over
which a proof is verified.

## 21. Failure Semantics

The following failure classes are defined:

- `intent_malformed`;
- `intent_expired`;
- `requirements_malformed`;
- `requirements_expired`;
- `requirements_hash_mismatch`;
- `requirement_unsupported`;
- `requirement_conflict`;
- `requirement_unsatisfied`;
- `evidence_missing`;
- `evidence_malformed`;
- `evidence_proof_invalid`;
- `evidence_expired`;
- `evidence_revoked`;
- `evidence_status_unknown`;
- `issuer_unresolved`;
- `subject_mismatch`;
- `audience_mismatch`;
- `intent_binding_mismatch`;
- `artifact_binding_mismatch`;
- `challenge_expired`;
- `challenge_replayed`;
- `package_incomplete`;
- `package_proof_invalid`;
- `privacy_declined`;
- `policy_rejected`;
- `negotiation_limit_exceeded`.

Failure responses SHOULD expose enough information for correction without
revealing private Policy or sensitive Evidence.

## 22. Security and Privacy Considerations

### 22.1 Replay

Requirements and Decision Packages SHOULD use unique identifiers, short-lived
nonces, issuance time, expiration, audience binding, and replay caches.

### 22.2 Evidence Transplant

An attacker may reuse Evidence issued for another subject, audience, action,
resource, artifact, intent, or session. Security-sensitive proof profiles MUST
bind all context required by the relevant Requirement.

### 22.3 Evidence Substitution

An attacker may replace referenced Evidence while preserving a mutable URI.
Security-sensitive references MUST include an immutable version or content
hash.

### 22.4 Expired or Revoked Evidence

Valid historical signatures do not imply current validity. Verifiers MUST
check the freshness and revocation behavior required by the Requirement.

### 22.5 Issuer Impersonation

Issuer identifiers and Verification Methods MUST be resolved and validated
under RFC-001 Part B or an explicitly defined issuer-resolution profile.

### 22.6 Metadata Fishing

A malicious receiver may request excessive data to profile or de-anonymize an
Agent or Principal. Presenters MUST be able to decline, minimize, or
selectively disclose.

### 22.7 Policy Probing

Repeated adaptive requests may reveal receiver Policy. Receivers SHOULD limit
negotiation rounds and MAY use coarse rejection reasons.

### 22.8 Correlation

Evidence identifiers, stable subjects, organization credentials, and trace
references may enable cross-session correlation. Profiles SHOULD minimize
stable identifiers and support scoped disclosure where compatible with audit.

### 22.9 Score Laundering

A presenter may omit an evaluator's method, context, or limitations and expose
only a favorable score. Scores lacking the fields required by Section 12 MUST
NOT satisfy a score or assessment Requirement.

### 22.10 Collusion

Multiple issuers may collude to produce misleading Evidence. RFC-002 preserves
issuer and provenance but does not define universal issuer independence or
trust. The receiver evaluates those risks locally.

### 22.11 Downgrade and Omission

An attacker may strip required fields, choose a weaker proof profile, or omit
negative Evidence. Critical Requirements and proof-profile negotiation MUST be
downgrade-resistant.

### 22.12 Denial of Service

Large packages, recursive references, expensive proofs, and repeated
negotiation can consume resources. Implementations SHOULD enforce size, time,
depth, and round limits before expensive verification.

### 22.13 Internal Reasoning Privacy

RFC-002 MUST NOT be used to require chain-of-thought or hidden model reasoning.
A receiver MAY request structured explanation, source, method, confidence,
provenance, or reproducible output Evidence.

## 23. Conformance

### 23.1 Requirements Issuer Conformance

A conformant Requirements Issuer:

1. MUST issue versioned, attributable, time-bounded Requirements;
2. MUST distinguish Requirement from private Policy;
3. MUST identify required versus optional items;
4. MUST provide context and binding requirements;
5. MUST accept explicit decline, unavailable, and unsupported statuses;
6. MUST implement data-minimization and metadata-fishing mitigations;
7. MUST NOT require a universal Trust Score.

### 23.2 Evidence Presenter Conformance

A conformant Evidence Presenter:

1. MUST answer every required Requirement Item with a defined status;
2. MUST preserve original issuers and provenance;
3. MUST bind a Decision Package to the exact Intent and Requirements version;
4. MUST distinguish missing, declined, unsupported, and unavailable Evidence;
5. MUST NOT present self-assertion as independent verification;
6. MUST NOT claim that package acceptance grants global trust or Permission.

### 23.3 Verifier Conformance

A conformant Verifier:

1. MUST produce structured check results;
2. MUST validate proof, issuer, subject, audience, context, freshness, and
   revocation as required;
3. MUST distinguish invalid, expired, revoked, and indeterminate status;
4. MUST NOT convert verification success directly into a trust conclusion;
5. MUST enforce replay and evidence-transplant protections;
6. MUST pass positive and negative test vectors for its proof profiles.

### 23.4 Decision Package Profile Conformance

A conformant package profile:

1. MUST define deterministic canonicalization and proof inputs;
2. MUST bind presenter, receiver, Intent, Requirements hash, nonce, payload or
   artifact, Evidence set, and validity;
3. MUST define critical-field handling;
4. MUST define size and reference-fetch limits;
5. MUST preserve identical semantics across transport bindings.

An implementation claiming RFC-002 conformance MUST state which of these four
roles and which proof profiles it implements.

## 24. Relationship to Other ACF RFCs

- [RFC-000](./000-agent-collaboration-framework.md) defines the boundary
  between Evidence and receiver-local trust decisions.
- [RFC-001](./001-agent-discovery-and-identity.md) establishes Agent identity
  control and issuer resolution.
- RFC-003 defines capability, Permission, authority, delegation, and
  constraints referenced by Decision Packages.
- RFC-004 creates Collaboration Sessions after receiver-local evaluation and
  negotiation.
- RFC-006 defines outcome attestations that may later be presented as
  Evidence.
- RFC-007 maps RFC-002 objects to concrete transports.
- RFC-008 consolidates cross-domain security and composition risks.

## 25. Relationship to Existing AgentNexus Work

| Existing work | Relationship to RFC-002 |
|---|---|
| [ADR-004: Multi-CA Certification](../../docs/adr/004-multi-ca-certification.md) | Certification format and issuer-verification input; L1-L4 are local Policy |
| [ADR-014: Governance Attestation and Trust Network](../../docs/adr/014-governance-trust-network.md) | Governance attestations, endorsements, and behavior observations are Evidence sources |
| [Giskard CA Contract](../../docs/contracts/giskard-ca-certification.md) | Domain-specific certification input; automatic trust-level mapping is non-normative |
| [OATR JWT Attestation Contract](../../docs/contracts/oatr-jwt-attestation.md) | Attestation input; `trust_delta` is receiver-local evaluation, not RFC-002 semantics |

Existing AgentNexus Governance Attestations, Certifications, Trust Edges,
Reputation Scores, and interaction records MAY be adapted into Evidence Items.
Current `trust_level`, `trust_score`, `attestation_bonus`, and
`best_decision` behavior is a reference local Policy implementation, not an
RFC-002 protocol result.

## 26. Open Questions

1. Which canonical serialization and proof suite should define the baseline
   Decision Package profile?
2. How should Evidence schemas and Requirement types be registered?
3. Which selective-disclosure formats belong in the baseline profile?
4. How should confidential Evidence references be authorized and fetched?
5. Should Requirements include machine-readable retention enforcement or only
   declared obligations?
6. Which Verification Result fields may be safely shared without enabling
   Policy probing?
7. How should multi-party sessions combine participant-specific Requirements?
8. Which package size, reference depth, and negotiation-round defaults should
   be RECOMMENDED?

## 27. References

### 27.1 Normative References

- [RFC-000: Agent Collaboration Framework Architecture](./000-agent-collaboration-framework.md)
- [RFC-001: Agent Discovery and Identity Establishment](./001-agent-discovery-and-identity.md)
- [RFC 2119: Key words for use in RFCs to Indicate Requirement Levels](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words](https://www.rfc-editor.org/rfc/rfc8174)

### 27.2 Informative References

- [ADR-004: Multi-CA Certification](../../docs/adr/004-multi-ca-certification.md)
- [ADR-014: Governance Attestation and Trust Network](../../docs/adr/014-governance-trust-network.md)
- [Giskard CA Contract](../../docs/contracts/giskard-ca-certification.md)
- [OATR JWT Attestation Contract](../../docs/contracts/oatr-jwt-attestation.md)

## Appendix A. Illustrative Metadata Requirements

The following example is non-normative:

```json
{
  "requirements_id": "reqs_01J...",
  "version": "1",
  "intent_id": "intent_01J...",
  "issuer": "did:example:receiver",
  "presenter": "did:example:initiator",
  "challenge": "base64url-random-value",
  "items": [
    {
      "requirement_id": "r_identity",
      "type": "acf:identity-control-result",
      "subject": "did:example:initiator",
      "criticality": "required",
      "max_age_seconds": 300,
      "bindings": {
        "audience": "did:example:receiver",
        "intent_id": "intent_01J..."
      }
    },
    {
      "requirement_id": "r_org",
      "type": "example:organization-representation",
      "criticality": "required",
      "any_of": [
        {"issuer_class": "example:accepted-registry"},
        {"review": "receiver_manual_review"}
      ]
    }
  ],
  "issued_at": "2026-07-17T10:10:00Z",
  "expires_at": "2026-07-17T10:15:00Z",
  "proof": {"type": "ExampleProof", "value": "..."}
}
```

## Appendix B. Illustrative Decision Package

The following example is non-normative:

```json
{
  "package_id": "pkg_01J...",
  "version": "1",
  "presenter": "did:example:initiator",
  "receiver": "did:example:receiver",
  "intent_id": "intent_01J...",
  "requirements_id": "reqs_01J...",
  "requirements_hash": "sha256:...",
  "challenge": "base64url-random-value",
  "responses": [
    {
      "requirement_id": "r_identity",
      "status": "satisfied",
      "evidence_ids": ["ev_identity"]
    },
    {
      "requirement_id": "r_org",
      "status": "satisfied",
      "evidence_ids": ["ev_org"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "ev_identity",
      "type": "acf:identity-control-result",
      "issuer": "did:example:receiver",
      "subject": "did:example:initiator",
      "claims": {"control_proven": true},
      "issued_at": "2026-07-17T10:11:00Z",
      "expires_at": "2026-07-17T10:16:00Z",
      "proof": {"type": "ExampleProof", "value": "..."}
    },
    {
      "evidence_id": "ev_org",
      "type": "example:organization-representation",
      "issuer": "did:example:registry",
      "subject": "did:example:initiator",
      "claims": {
        "principal": "did:example:organization",
        "role": "reviewer"
      },
      "issued_at": "2026-07-01T00:00:00Z",
      "expires_at": "2026-08-01T00:00:00Z",
      "proof": {"type": "ExampleProof", "value": "..."}
    }
  ],
  "created_at": "2026-07-17T10:12:00Z",
  "expires_at": "2026-07-17T10:15:00Z",
  "proof": {"type": "ExamplePackageProof", "value": "..."}
}
```
