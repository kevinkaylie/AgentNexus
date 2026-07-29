# RFC-003: Capability Negotiation, Authority Grants, and Delegation

| Field | Value |
|---|---|
| Status | Draft |
| Category | Standards Track |
| Version | 0.3 |
| Created | 2026-07-27 |
| Updated | 2026-07-29 |
| Authors | AgentNexus Contributors |
| Requires | RFC-000, RFC-001 Part B, RFC-002 |
| Updates | None |
| Obsoletes | None |

## Abstract

This document defines transport-independent semantics for negotiating
capability, granting bounded Permission, representing Authority, and
delegating that Authority within the Agent Collaboration Framework (ACF).

In this RFC, **Capability** means a claimed or demonstrated ability. It does
not mean an object-capability authorization token. An authorization artifact
that conveys Permission is called an **Authority Grant**, regardless of
whether an implementation encodes it as an access token, capability token,
credential, signed envelope, or server-side reference.

An Agent may claim or demonstrate that it can perform an action. That
Capability does not authorize the Agent to perform the action. Permission
arises only from an Authority Grant made by a Grantor that is entitled to
control the relevant action or resource. A Delegate may further delegate only
when explicitly permitted, and every derived grant must monotonically narrow
the authority of its parent. For consumable Authority, per-child narrowing is
necessary but not sufficient: allocation and consumption across the entire
grant family must also remain within the parent budget.

This RFC standardizes Capability Requirements, Capability Statements,
Authority Requests, Authority Grants, Delegation Records, constraints,
obligations, Grant Acceptance, consumable-authority accounting, proof
bindings, verification results, and lifecycle signals. It does not define a
universal competence score, decide whether an Agent is capable or trustworthy,
create legal authority, or prescribe the receiver's authorization Policy.

The governing distinctions are:

```text
Capability ≠ Permission
Permission ≠ Authority
Authority Grant ≠ Session
Delegation ≠ transfer of trust
Protocol-valid grant ≠ legal authority
```

## 1. Status and Normative Language

This document is a Draft. JSON examples are illustrative unless a later
version explicitly marks a schema or profile as normative.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and
**OPTIONAL** in this document are to be interpreted as described in
[BCP 14](https://www.rfc-editor.org/info/bcp14) when, and only when, they appear
in all capitals.

## 2. Scope

RFC-003 defines:

- receiver-declared Capability Requirements;
- Capability Statements and references to supporting Evidence;
- Authority Requests and counter-proposals;
- Permission, action, resource, purpose, and scope semantics;
- Authority Grants and their proof bindings;
- delegation authorization and Delegation Records;
- monotonic narrowing of derived grants;
- allocation and accounting semantics for consumable Authority;
- constraints, conditions, and obligations;
- Grant Acceptance, possession, presentation, verification, and enforcement
  signals;
- immutable grant bodies, digest coverage, and replacement;
- critical-extension handling;
- explicit composition of multiple grants;
- Purpose Assurance expression;
- expiration, suspension, revocation, replacement, and surrender;
- structured verification results and failure classes;
- security and privacy requirements specific to authority negotiation.

RFC-003 does not:

- define whether a Capability Claim is true;
- define a universal skill, competence, quality, reliability, reputation, or
  Trust Score;
- infer Permission from identity, Capability, reputation, payment, or evidence
  acceptance;
- determine whether a Grantor has authority under law, contract, employment,
  or industry rules;
- mandate a particular token, credential, signature, identity, or policy
  technology;
- establish the Collaboration Session defined by RFC-004;
- define task execution or artifact handoff semantics from RFC-005;
- adjudicate whether an obligation was fulfilled or who is legally liable;
- replace OAuth, GNAP, object-capability systems, access-control engines, or
  domain authorization systems;
- require disclosure of a receiver's private Policy or an Agent's internal
  reasoning.

An implementation MAY map an Authority Grant to an existing authorization
technology. Such a mapping MUST preserve the semantics and bindings required
by this RFC and MUST identify any loss of expressiveness.

## 3. Governing Model

The abstract sequence is:

```text
Collaboration Intent + accepted Evidence context
  → Capability Requirements
  → Capability Statement + Capability Evidence
  → receiver-local capability evaluation
  → Authority Request
  → Authority Grant | counter-proposal | decline
  → Grant Acceptance when required
  → grant verification and enforcement preparation
  → RFC-004 Session Agreement
```

The sequence MAY be compressed. For example, a receiver MAY include Capability
Requirements in RFC-002 Metadata Requirements, and a Grantor MAY attach a
proposed Authority Grant to a conditional acceptance. Compression MUST NOT
erase the distinctions between Evidence, evaluation, Permission, and
Authority.

The following statements are invalid:

```text
Identity verified       ⇏ Capability established
Capability advertised   ⇏ Capability established
Capability established  ⇏ Permission granted
Permission granted      ⇏ Authority may be re-delegated
Evidence accepted       ⇏ Permission granted
Grant signed            ⇏ Grantor controls the resource
Grant verified          ⇏ requested action is safe
Grant accepted          ⇏ Collaboration Session active
```

## 4. Roles

One entity MAY perform more than one role. Roles are relative to a particular
exchange or grant.

### 4.1 Capability Requester

The participant that declares a Capability Requirement for a proposed
collaboration.

### 4.2 Capability Subject

The Agent or other entity whose ability is described by a Capability
Statement.

### 4.3 Capability Claimant

The entity that asserts a Capability Statement. The Claimant may be the
Capability Subject, its Principal, a certifier, or another Evidence Issuer.

### 4.4 Authority Requester

The participant that requests Permission for a proposed Grantee. The Requester
MAY be the Grantee or an authorized intermediary.

### 4.5 Grantor

The Principal, Agent, authorization service, resource controller, or other
entity that issues an Authority Grant.

A valid Grantor proof establishes who issued the grant. It does not, by
itself, prove that the Grantor has domain or legal authority over the resource.
Evidence supporting the Grantor's authority MAY be requested under RFC-002.

### 4.6 Grantee

The Agent, Principal, service, or other subject to which an Authority Grant is
issued. The Grantee is not necessarily the software instance that exercises
the granted Permission.

### 4.7 Represented Principal

The Principal on whose behalf an Authorized Executor acts when exercising a
Permission. A self-representing Grantee MUST identify itself explicitly rather
than relying on an omitted value.

### 4.8 Authorized Executor

The Agent, service, software instance, human-operated endpoint, or other actor
authorized to exercise a Permission. The Authorized Executor MAY be the
Grantee, but the relationship MUST be explicit.

### 4.9 Delegator

A current Authority Holder that issues a derived grant to a Delegate. A
Delegator is a Grantor for the derived grant.

### 4.10 Delegate

The Grantee of a derived Authority Grant.

### 4.11 Authority Verifier

The component that verifies protocol facts about a grant, including proof,
issuer control, subject, audience, scope, chain integrity, time validity,
revocation, and requested-action binding.

### 4.12 Policy Decision Point

The receiver-local component that decides whether a verified grant and other
context are sufficient to permit an attempted action.

### 4.13 Policy Enforcement Point

The component that permits, denies, constrains, suspends, or terminates an
attempted action according to the local decision.

### 4.14 Resource Controller

The entity or enforcement domain that controls access to a resource. A
Resource Controller MAY delegate grant issuance to another Grantor.

### 4.15 Grant Acceptor

The Grantee, Authorized Executor, Represented Principal, or authorized
representative that accepts a grant and its obligations when acceptance is
required. A profile MUST identify which party or parties must accept.

## 5. Terminology and Required Distinctions

### 5.1 Capability

An ability to perform a class of action. Capability may be claimed,
demonstrated, certified, observed, or inferred. It is evaluated in a stated
context and does not imply Permission.

In this RFC, Capability does not mean an object-capability authorization
token. Security systems that use the word "capability" for an unforgeable
authority-bearing reference MAY map that artifact to an Authority Grant
profile, but MUST NOT interpret possession of it as Evidence that the holder
is able to perform the authorized action well.

### 5.2 Capability Requirement

A receiver-declared description of an ability needed for a proposed
collaboration. It may specify the action class, target context, evidence
requirements, minimum recency, test conditions, or acceptable alternatives.

### 5.3 Capability Statement

An attributable Claim that a Capability Subject can perform a described class
of action under stated conditions.

### 5.4 Permission

A structured description of an allowed action, resource, audience, purpose,
validity, and applicable limits for an identified Grantee, Represented
Principal, and Authorized Executor.

A Permission has two orthogonal components:

- **Subject Binding**: Grantee, Represented Principal, and Authorized
  Executor;
- **Authority Scope**: action, resource, audience, Purpose, required Purpose
  Assurance, validity, constraints, conditions, obligations, allocation, and
  Delegate Policy and delegation limits.

A Permission describes the normative authorization scope carried by an
Authority Grant. It is not itself a grant, credential, proof, or decision, and
has no effect unless conveyed by an active Authority Grant and permitted by
the applicable Policy Enforcement Point.

The complete Permission relation changes when a delegation names a new
Grantee or Executor. Therefore, the complete Permission relation MUST NOT be
used as the operand of the monotonic set-subset test. Authority Scope is
checked for narrowing; Subject Binding is checked by the separate controlled
transition rules in Section 12.3.

### 5.5 Authority

The source, scope, and grant relationship from which one or more Permissions
are derived. Authority is relational and contextual; it is not an intrinsic
property of an Agent.

### 5.6 Authority Grant

An attributable, verifiable object by which a Grantor conveys one or more
Permissions to a Grantee under defined constraints and lifecycle rules.

An Authority Grant is sometimes encoded by implementations as an access token,
capability token, credential, signed envelope, certificate, policy binding, or
server-side grant reference. This RFC uses **Authority Grant** as the
technology-neutral semantic term.

### 5.7 Authority Holder

The current Grantee of an active Authority Grant.

### 5.8 Delegation

The act of an Authority Holder issuing a derived, narrower Authority Grant to
a Delegate when the parent grant explicitly permits it.

### 5.9 Delegation Record

An attributable record that links a derived Authority Grant to its parent
grant, Delegator, Delegate, acceptance, and lifecycle events.

A Delegation Record is an audit and correlation record. It is not an
independent source of Permission and MUST NOT redefine the normative scope,
constraints, obligations, or delegation depth contained in the immutable
parent and child Authority Grants.

### 5.10 Scope

The structured boundary of a Permission. Scope commonly includes action,
resource, purpose, context, audience, time, quantity, value, stage, data class,
or other domain-defined dimensions.

### 5.11 Constraint

A machine-evaluable limit on when or how Permission may be exercised or
delegated. Examples include time bounds, amount limits, resource patterns,
allowed stages, rate limits, geographic limits, and maximum delegation depth.

### 5.12 Condition

A predicate that MUST be satisfied before or while Permission is exercised.
For example, a condition may require fresh human approval, a particular
Session state, a second signature, or a current liveness proof.

### 5.13 Obligation

A required action associated with accepting or exercising a grant, such as
producing a Receipt, deleting data after a retention period, notifying a
Principal, or submitting an output for review.

An Obligation is not necessarily enforceable by the protocol. A grant profile
MUST state whether an Obligation is pre-enforced, post-verified, merely
declared, or enforced outside ACF.

### 5.14 Proof of Possession

A proof that the presenter controls a key or mechanism bound to a grant. Proof
of possession is distinct from proof that the Grantor issued the grant.

### 5.15 Bearer Grant

An Authority Grant exercisable by any presenter that possesses it, without a
separate proof of possession. Bearer Grants have higher theft and replay risk.

### 5.16 Delegate Policy

An integrity-protected rule in a parent Grant Body that identifies eligible
Delegates, permitted Executor transitions, required evidence and acceptance,
and the context in which delegation may occur.

A Delegate Policy has two distinct semantic parts:

- **current-transition eligibility**: whether the proposed child Grantee,
  Executor, and context are eligible for the current delegation;
- **redelegation ceiling**: the maximum downstream delegation policy that the
  child Grant is allowed to carry.

Delegation depth alone is neither current-transition eligibility nor a
redelegation ceiling.

### 5.17 Required Distinctions

Implementations MUST preserve:

```text
Capability Claim       ≠ Capability Evidence
Capability Evidence    ≠ receiver capability decision
Capability             ≠ Permission
Permission             ≠ Authority
Authority              ≠ Trust
Constraint             ≠ Obligation
Grant possession       ≠ grant validity
Grant validity         ≠ action authorization
Delegation             ≠ impersonation
Delegation             ≠ transfer of the Delegator's identity or Trust
Delegation Record      ≠ Authority Grant
Grant Acceptance       ≠ legal acceptance or Session activation
Task delegation        ≠ Authority delegation
Service invocation     ≠ Authority delegation
Scope narrowing        ≠ Subject Binding transition
```

The term `capability_token` MAY be retained by an implementation for
compatibility. Documentation claiming RFC-003 alignment MUST state whether the
token represents evidence of ability, an Authority Grant, or both. A token
that conveys Permission SHOULD be described semantically as an Authority
Grant Token to avoid confusing ability with authorization.

## 6. Capability Negotiation

### 6.1 Capability Requirements

A Capability Requirement SHOULD identify:

- requirement identifier and version;
- related Collaboration Intent;
- requester;
- Capability Subject or acceptable subject class;
- action or ability vocabulary;
- operating context and target resource class;
- required and optional Evidence types;
- acceptable issuers or issuer classes when disclosure is safe;
- demonstration, test, benchmark, or observation requirements;
- freshness and expiration limits;
- required confidence provenance, if any;
- alternatives and criticality;
- challenge, audience, and response deadline;
- proof and integrity mechanism.

A Capability Requester MUST NOT imply that satisfying the Requirement grants
Permission. A requirement may establish suitability for consideration, not
authorization.

### 6.2 Capability Statements

A Capability Statement SHOULD identify:

- statement identifier and schema version;
- Capability Claimant;
- Capability Subject;
- action or ability;
- input and output types or schemas;
- operating constraints and dependencies;
- supported protocol or tool interfaces when relevant;
- validity period;
- related Evidence or immutable Evidence references;
- context, audience, challenge, and Intent bindings;
- proof when the statement is intended to be verifiable.

Self-asserted Capability Statements MUST be distinguishable from independent
certification, observed performance, and derived assessment.

### 6.3 Capability Evidence

Capability Evidence is an RFC-002 Evidence Item whose subject or claim concerns
ability. It MAY include:

- a signed Capability Statement;
- a certification or license;
- a reproducible test result;
- a benchmark with method and environment;
- an observed outcome or historical Receipt;
- an artifact demonstrating prior work;
- a third-party assessment;
- a locally observed result;
- a derived assessment with disclosed method and provenance.

The Authority Verifier MAY verify the Evidence's protocol properties. The
receiver's Policy Decision Point determines what the Evidence means for the
proposed action.

### 6.4 Capability Negotiation Result

A receiver MAY signal:

- `capability_accepted`;
- `capability_conditionally_accepted`;
- `additional_capability_evidence_required`;
- `capability_not_established`;
- `capability_unsupported`;
- `capability_evaluation_deferred`;
- `capability_evaluation_cancelled`.

These signals are scoped to the exact Intent, Requirement version, Capability
Subject, context, and receiver. They MUST NOT be represented as global
competence or Trust verdicts.

## 7. Authority Request

An Authority Request asks a prospective Grantor to convey bounded Permission.
It SHOULD identify:

- request identifier and version;
- related Collaboration Intent;
- Requester;
- proposed Grantee;
- proposed Represented Principal;
- proposed Authorized Executor;
- intended Grantor or Resource Controller;
- requested action set;
- requested resource set;
- purpose;
- audience and enforcement domain;
- requested validity interval;
- requested delegation rights and maximum depth;
- requested authority class and allocation mode for quantitative or
  consumable Permission;
- proposed constraints, conditions, and obligations;
- proposed Purpose Assurance requirements;
- Session Proposal identifier, when the request is intended for a new
  Collaboration Session;
- relevant Capability Statement or Evidence references;
- related Requirement and Decision Package references;
- nonce, issuance time, and expiration time;
- proof of Requester control.

An Authority Request MUST be interpreted as a proposal. It creates no
Permission.

A Requester MUST NOT request a wildcard action, resource, audience, or
unbounded validity when a narrower request can satisfy the Intent. Profiles
MUST define whether wildcards are permitted and how their subset relationship
is evaluated.

## 8. Authority Negotiation

The prospective Grantor MAY respond with:

- `grant_offered`;
- `counter_proposed`;
- `additional_evidence_required`;
- `human_approval_required`;
- `grant_declined`;
- `grant_unsupported`;
- `grant_deferred`;
- `request_expired`;
- `request_cancelled`.

A counter-proposal MUST identify the exact Authority Request it revises and
the dimensions changed. A participant MUST NOT treat silence, message
delivery, identity verification, Evidence acceptance, or continued
conversation as an Authority Grant.

Negotiation SHOULD be bounded by:

- maximum round count;
- absolute expiration;
- per-round response deadline;
- maximum object size;
- maximum number of alternatives;
- rate and concurrency limits.

The Grantor MAY return a minimal reason such as `policy_declined` to avoid
revealing private Policy. Error minimization MUST NOT make `invalid_grant`,
`expired_grant`, and `revoked_grant` indistinguishable at the enforcement
boundary when safe handling depends on the distinction.

## 9. Permission and Scope Model

### 9.1 Permission Structure

At minimum, a Permission MUST bind a Subject Binding:

```text
(Grantee, Represented Principal, Authorized Executor)
```

and an Authority Scope:

```text
(Action, Resource, Audience, Purpose, Purpose Assurance, Validity,
 Constraints, Conditions, Obligations, Allocation, Delegate Policy)
```

A self-representing Grantee MUST still use an explicit Principal binding. If
the Grantee and Authorized Executor are the same entity, both fields MUST
identify that entity or use an explicit, profile-defined equivalence marker.

The Subject Binding and Authority Scope are integrity-protected together in
the Grant Body, but they follow different derivation rules:

- Authority Scope MUST monotonically narrow;
- Subject Binding MAY change only through an authorized delegation
  transition;
- neither rule can substitute for the other.

A profile MAY define additional dimensions. If a dimension is omitted, the
profile MUST define whether omission means no value, a default, inheritance,
or wildcard. Security-critical dimensions MUST NOT have ambiguous defaults.

### 9.2 Actions

Actions MUST use a versioned vocabulary or an unambiguous URI-like identifier.
Examples include:

```text
artifact:read
artifact:write
task:execute
payment:authorize
message:send
member:invite
```

Natural-language descriptions MAY supplement action identifiers but MUST NOT
be the sole representation of security-critical action scope.

### 9.3 Resources

A Resource MAY be identified by:

- an immutable identifier;
- a content hash;
- a URI or URI pattern;
- a typed collection;
- a Session, task, stage, artifact, account, dataset, or tool reference;
- a profile-defined structured selector.

Resource pattern semantics MUST be defined by the applicable profile. A
Verifier MUST NOT infer containment from string prefix alone unless the
profile explicitly defines that algorithm.

### 9.4 Purpose

Purpose limits why the Permission may be exercised. A purpose MUST use a
defined identifier or profile vocabulary when it affects authorization.

Purpose declarations are Claims. Writing `purpose=book-travel` proves only
that the presenter made and bound that declaration. It does not prove the
presenter's internal intent or prevent other use.

An Authority Grant or presentation using Purpose as an authorization
dimension MUST identify a Purpose Assurance mode:

- `declared`: the presenter declares the Purpose;
- `context_bound`: the Purpose is cryptographically bound to the Intent,
  Session Proposal or Session, action, resource, and relevant payload;
- `attested`: an identified external party attests to the Purpose or approval;
- `enforced`: an identified technical control restricts the action or data
  path to the stated Purpose.

These modes describe different evidence and control properties and are not a
universal ordinal score. Multiple modes MAY apply. A profile MUST define the
proof and verification procedure for any mode stronger than `declared`.
Receiver-local Policy decides which modes are sufficient.

Required Purpose Assurance is part of Authority Scope and MUST NOT be
downgraded by delegation. Because the modes are not a universal ordinal
scale, each profile that permits delegation MUST define an implication or
strength relation for the combinations it supports. A child requirement is
valid only when satisfying it necessarily satisfies every applicable parent
requirement. In particular, `declared` alone MUST NOT replace
`context_bound`, `attested`, or `enforced`.

Post-action audit is not a Purpose Assurance mode available at presentation
time. A requirement to produce an audit record MUST be represented as an
Obligation with its own `obligation_id`, trigger, due time, and expected
Receipt. Once produced, an audit record MAY become Evidence about past Purpose
conformance; it does not retroactively prove the actor's internal intent.

### 9.5 Audience and Enforcement Domain

Every portable Authority Grant MUST identify the intended audience or
enforcement domain. A grant issued for one Resource Controller MUST NOT be
accepted by another unless cross-audience use is explicit and locally
permitted.

### 9.6 Validity

A grant MUST include an issuance time and an expiration time or a
profile-defined bounded lifetime. Where clock uncertainty matters, the
profile MUST define allowed skew and time source assumptions.

Long-lived grants SHOULD require renewal, re-evaluation, or continuous
conditions rather than relying only on distant expiration.

### 9.7 Replicable and Consumable Authority

Per-child subset validation is sufficient only for Authority that may be
safely replicated, such as read access that has no family-wide usage limit.
For amount, count, inventory, rate, quota, one-time, or other consumable
Authority, every grant MUST identify an allocation mode and accounting domain.

This family-wide invariant is called **Authority Conservation**: delegation
may subdivide, reserve, or route consumable Authority, but MUST NOT create
additional aggregate capacity.

The baseline allocation modes are:

- `replicable`: multiple derived grants may carry the same non-consumable
  scope, subject to all other constraints;
- `partitioned`: issuance reserves a non-overlapping portion of a parent
  budget for a child;
- `shared_counter`: parent and child grants consume from one authoritative
  counter at the point of exercise;
- `exclusive_transfer`: the delegated portion becomes unavailable to the
  Delegator while the child grant is active;
- `single_use`: exactly one successful exercise is permitted across the
  identified grant family or reservation.

A consumable-authority definition MUST identify:

- authority class and allocation mode;
- accounting-domain identifier;
- unit and total limit;
- consumed, reserved, and available-value semantics;
- authoritative counter, ledger, allocator, or reservation service;
- atomicity and consistency requirements;
- behavior during partition, timeout, retry, and duplicate submission;
- reservation release rules after rejection, expiration, surrender, or
  revocation;
- reconciliation and audit records.

For `partitioned` Authority, child issuance MUST atomically reserve value and:

```text
sum(active child reservations)
  + parent-branch consumed value
  + parent-branch outstanding reservations
  ≤ parent authorized total
```

The Delegator MUST NOT exercise or re-delegate a reserved portion until it is
released according to the profile. For `shared_counter` and `single_use`
Authority, every exercise MUST perform an atomic check-and-consume operation
against the authoritative accounting domain.

An accounting-domain identifier is not merely descriptive scope. Every
derived consumable grant MUST preserve **Accounting Domain Continuity** by
either:

- naming the same authoritative accounting domain as its parent; or
- naming a child accounting domain backed by a verifiable, atomic reservation
  or transfer from the parent accounting domain.

A child accounting domain MUST NOT be treated as continuous merely because
its numeric limit is smaller. When a distinct child domain is used, the child
Grant Body or an integrity-protected allocation record MUST bind the parent
domain, child domain, parent and child Grant Body digests, reserved unit and
amount, allocation mode, reservation identifier, and authoritative proof of
the debit or lock in the parent domain. Independent counters without that
binding violate Authority Conservation.

A static signed grant, per-child subset check, or local counter alone MUST NOT
be presented as enforcing a family-wide consumable limit across independent
enforcement domains. If the required accounting mechanism is unavailable or
its consistency cannot be established, a critical consumable Permission MUST
fail closed or use a pre-authorized, cryptographically or operationally
partitioned reservation.

## 10. Authority Grant

An Authority Grant MUST identify:

- grant identifier and schema version;
- Grantor;
- Grantee;
- Represented Principal;
- Authorized Executor;
- related Authority Request or an explicit `unsolicited` marker;
- parent grant identifier and digest, if derived;
- Permission set, including action and resource scope;
- purpose and required Purpose Assurance;
- intended audience and enforcement domain;
- authority class, allocation mode, and accounting domain when applicable;
- constraints, conditions, and obligations;
- delegation permission, maximum remaining depth, and Delegate Policy when
  delegation is permitted;
- Grant Acceptance requirements;
- issuance, not-before, and expiration time;
- nonce or request binding;
- Collaboration Intent and Session Proposal binding, or an existing Session
  binding when the Session already exists;
- proof-of-possession key or mechanism, when required;
- immutable Grant Body canonicalization and digest profile;
- status mechanism descriptor;
- critical-extension declarations;
- Grantor proof profile.

An Authority Grant MAY reference Capability Evidence or receiver
decision-context Evidence when disclosure is allowed. Such a reference
explains grant context; it does not make the referenced Capability Evidence
an authorization source.

The grant MUST NOT contain an implicit universal `admin`, `all`, or equivalent
scope unless the applicable profile gives that value precise, bounded
semantics.

A Grantor MUST NOT issue Permission broader than the Authority it controls.
This rule is a protocol-verifiable fact only when the Grantor's own Authority
is represented by a verifiable parent grant or another profile-defined root
authority record. Otherwise, the Grantor's domain authority remains an
external Claim.

### 10.1 Root Grants

A Root Grant has no parent grant. Its verifier MUST determine the source of
the Grantor's authority using a profile-defined trust anchor, resource-control
record, ownership proof, organizational policy, local configuration, or
another explicitly identified mechanism.

Root status MUST NOT be interpreted as self-validating or universally
authoritative.

### 10.2 Referenced and Self-Contained Grants

An Authority Grant MAY be:

- self-contained and presented to a Policy Enforcement Point;
- referenced by an opaque identifier and resolved from an authorization
  service;
- split between a signed semantic object and local enforcement state.

The representation choice MUST NOT alter the required semantic bindings.
Reference resolution MUST authenticate the resolver response and define cache,
freshness, unavailability, and revocation behavior.

### 10.3 Bearer and Proof-Bound Grants

Proof-bound grants SHOULD be used for high-risk, portable, or long-lived
authority. A proof-bound grant MUST identify the possession key or mechanism
and the action presentation MUST prove possession.

If a profile permits Bearer Grants, it MUST document:

- transport and storage protections;
- replay prevention;
- maximum lifetime;
- audience restriction;
- revocation behavior;
- leakage and logging mitigations.

### 10.4 Grant Body Immutability and Digest Coverage

An issued Authority Grant has three logically separate parts:

1. **Grant Body**: the immutable normative authorization content;
2. **Grant Proof**: one or more proofs binding a Grantor to the Grant Body;
3. **Grant Status Statement**: mutable, attributable lifecycle information
   referenced by the Grant Body but not edited into it.

The Grant Body MUST be immutable after issuance. Any semantic change,
including scope, Principal, Executor, Purpose, Purpose Assurance, constraint,
obligation, allocation, Delegate Policy, validity, proof-of-possession
binding, critical extension, or status-mechanism change, MUST create a
replacement grant with a new `grant_id`. A replacement MUST identify the
prior grant. A `grant_id` MUST NOT be reused for different Grant Body bytes or
semantics.

The baseline digest model is:

```text
grant_digest =
  HASH(profile_identifier || canonicalize(complete Grant Body))
```

The complete Grant Body includes the `grant_id`, version, all core normative
fields, extension values, critical-extension declarations, status mechanism
descriptor, and canonicalization profile. The descriptor need not contain a
remote URI. The Grant Body excludes Grant Proof values and external Grant
Status Statements so that proofs and status can change without a
self-referential or mutable digest.

Each Grant Proof MUST bind the `grant_digest`, Grantor, proof purpose,
algorithm, verification method, and proof creation time. Multiple proofs MAY
cover the same Grant Body without changing `grant_digest`.

If a `constraint_set_digest` is present, it MUST be recomputed from the exact
canonical constraint, condition, obligation, authority-allocation, and
criticality structures defined by the profile. A mismatch is
`digest_mismatch`; the digest MUST NOT override the Grant Body.

An `authority_chain_digest` MUST cover the ordered sequence of Grant Body
digests from the Root Grant through the presented grant. It does not replace
per-grant proof, status, or chain validation. A Verification Result using a
chain digest MUST separately identify the status snapshot and verification
time.

Canonicalization failure, unsupported critical canonicalization rules,
duplicate semantic keys, or digest mismatch MUST make the grant invalid or
unsupported. An implementation MUST NOT fall back to a different
canonicalization algorithm silently.

### 10.5 Critical Extensions

The baseline extension mechanism uses:

- an `extensions` map whose keys are collision-resistant, versioned extension
  identifiers;
- a `critical_extensions` array listing extension identifiers that MUST be
  understood and enforced.

Every identifier in `critical_extensions` MUST name an entry in `extensions`
or a profile-defined core extension point. An implementation that does not
understand a critical extension MUST return `unsupported_critical_extension`
and MUST NOT activate or exercise the grant.

An unknown non-critical extension MAY be ignored for authorization, but it
MUST remain integrity-protected by the Grant Body digest and MUST NOT be
reinterpreted with locally invented semantics. Extensions MUST NOT redefine
core fields or weaken core validation.

Unknown top-level fields outside a profile-defined extension point MUST be
treated according to the serialization profile's strict-field rules. The
baseline profile SHOULD reject them rather than guessing whether they are
critical.

Constraint-level `critical` indicators remain valid for individual
constraints. The top-level mechanism applies to any future semantic addition,
including payment confirmation, jurisdiction, data residency, biometric
approval, or human-review requirements.

Every critical extension has a delegation behavior. Its definition SHOULD
declare that behavior and any required comparison rule. The baseline
behaviors are:

- `inherited`: the extension applies to descendant grants and MUST appear in
  each child unchanged or with a profile-defined stronger value;
- `non_inheritable`: authority carrying the extension MUST NOT be delegated;
- `transformable`: a child MAY use a different extension value only when a
  profile-defined comparison proves that the transformed value preserves or
  strengthens the parent protection.

An authorization-affecting critical extension defaults to `inherited`
unchanged when its definition does not specify a behavior. The
`non_inheritable` and `transformable` behaviors MUST be explicitly defined;
an implementation MUST NOT infer them. A Delegator or Verifier that cannot
determine the behavior or comparison result MUST fail closed. A child MUST
NOT omit an applicable parent critical extension merely because the parent
Grant remains present in the chain. Such omission is
`critical_extension_stripped`.

### 10.6 Grant Acceptance

Grant Acceptance applies to Root Grants and derived grants. Delegation
Acceptance is one specialization of this common mechanism.

A Grant MUST require explicit acceptance when:

- the Authority Requester is not the Grantee;
- the Authorized Executor did not participate in the request;
- the grant adds an Obligation to the Grantee, Executor, or Represented
  Principal;
- a proof-of-possession key has not already been confirmed by its controller;
- the grant is unsolicited;
- the applicable profile or Grantor requires acceptance.

A Grant Acceptance SHOULD identify:

- acceptance identifier and version;
- grant identifier and `grant_digest`;
- acceptor and acceptor role;
- status: `accepted`, `conditionally_accepted`, `rejected`, or
  `clarification_requested`;
- Obligation identifiers explicitly acknowledged;
- proof-of-possession key confirmation when applicable;
- proposed conditions when status is `conditionally_accepted`;
- nonce, issuance time, and expiration time;
- proof.

`accepted` applies only to the exact immutable Grant Body identified by
`grant_digest`.

`conditionally_accepted` does not accept or modify that Grant Body. It is an
integrity-protected counter-proposal. The Grant MUST enter or remain in
`countered` state and MUST NOT activate. If the Grantor agrees to the proposed
condition, it MUST issue a replacement Grant Body containing that condition
and a new `grant_id` and `grant_digest`. The replacement requires its own
Acceptance unless a valid request-time pre-acceptance covers the exact
replacement terms.

A third party MUST NOT apply a condition found only in an Acceptance to the
original Grant Body. Conditions that affect authorization, delegation, or
enforcement MUST be present in the immutable Grant Body.

When acceptance is required, the grant MUST enter `acceptance_pending` and
MUST NOT be exercisable until every required `accepted` result has been
verified. Silence, delivery, storage, discovery, or possession of a grant is
not acceptance.

#### 10.6.1 Request-Time Pre-Acceptance

An Authority Request MAY contain a signed pre-acceptance to reduce a redundant
round trip. A pre-acceptance MUST identify:

- prospective Acceptor and role;
- canonical `acceptance_terms`;
- `acceptance_terms_digest`;
- explicitly acknowledged Obligation identifiers;
- proposed proof-of-possession key;
- nonce, validity, and proof.

The canonical `acceptance_terms` MUST include every term whose later addition
or change would require Acceptance, including Grantee, Represented Principal,
Authorized Executor, Permission, constraints, conditions, obligations,
allocation, delegation rights, Purpose Assurance, and proof-of-possession
binding.

A Grant MAY rely on pre-acceptance only when:

- the Requester is the relevant Acceptor or proves authority to accept;
- the Grant copies every acceptance-relevant term without semantic change;
- the Grant contains the same `acceptance_terms_digest`;
- no new Acceptor, Obligation, condition, Permission, delegation right, or
  stronger burden has been added;
- the pre-acceptance is current and its proof is valid.

Any counter-proposal or acceptance-relevant change invalidates
pre-acceptance. The resulting grant MUST obtain a new Acceptance.

Rejecting or ignoring an unsolicited grant MUST NOT create an Obligation,
responsibility record, negative reputation event, or inference of misconduct.
A Grant Acceptance is a technical protocol assertion. It does not by itself
establish contractual consent, legal liability, business acceptance, or
Session activation.

### 10.7 Status Mechanism Descriptor

An Authority Grant MUST describe how current exercise status is determined,
but it does not need to contain a remote status URL. The descriptor MUST name
a mode and define the verification and failure behavior applicable to that
mode.

Baseline modes are:

- `remote_reference`: resolve authenticated status from an identified
  endpoint or service;
- `local_state`: consult authoritative state maintained in the local
  enforcement domain;
- `short_lived_no_revocation`: rely on a narrowly bounded lifetime and declare
  that no mid-lifetime remote revocation mechanism exists;
- `single_use_ledger`: perform an atomic unused-to-consumed transition in an
  identified ledger or nonce store;
- `profile_defined`: use a named profile with explicit status semantics.

A status mechanism descriptor SHOULD identify:

- mode and profile version;
- status authority or enforcement domain;
- grant or ledger key;
- resolution or lookup method when applicable;
- authentication and integrity mechanism;
- freshness and cache limits;
- suspension, revocation, consumption, and terminal-state semantics;
- descendant propagation, compatibility, and maximum-observation-delay
  requirements;
- behavior when time, network, storage, or status authority is unavailable.

An implementation MUST NOT invent a remote URL merely to satisfy this RFC.
For `short_lived_no_revocation`, the risk and maximum lifetime MUST be
explicit and receiver-local Policy decides whether that mode is acceptable.
For `single_use_ledger`, the atomic transition is part of authorization
exercise, not an optional audit update.

When a derived grant or Grant Composition cannot satisfy an applicable
ancestor or contributing grant's status, freshness, propagation, or failure
requirements, verification MUST return `status_mechanism_incompatible`.

## 11. Constraints, Conditions, and Obligations

### 11.1 Constraint Vocabulary

Constraint types MUST have:

- a stable identifier and version;
- a value schema;
- deterministic evaluation rules;
- a defined comparison or subset relation when delegable;
- critical-field behavior;
- failure and indeterminate behavior.

An implementation MUST reject or decline a grant containing an unknown
critical constraint. It MUST NOT silently ignore it.

### 11.2 Common Constraint Dimensions

Profiles MAY define constraints such as:

- allowed and prohibited resources;
- amount, cost, quantity, or rate limits;
- allowed task, stage, or workflow state;
- input and output artifact restrictions;
- geographic or jurisdictional boundary;
- allowed tools or execution environments;
- required reviewers or co-signers;
- data classification and retention;
- maximum delegation depth;
- maximum parallel or cumulative use;
- liveness, attestation, or re-verification interval.

### 11.3 Conditions

The baseline semantics of a Condition array are conjunctive: every member of
the array MUST be satisfied. An array MUST NOT be interpreted as `OR`,
`threshold`, priority, fallback, or another boolean form.

Disjunction, threshold logic, and other compound boolean semantics MUST use
an explicit, versioned composite Condition type or a profile-defined
expression format with deterministic evaluation, canonicalization, and
implication rules.

A condition evaluation MUST produce a structured result:

- `satisfied`;
- `not_satisfied`;
- `expired`;
- `revoked`;
- `indeterminate`;
- `unsupported`.

For a critical condition, any result other than `satisfied` MUST prevent
authority exercise.

Delegation MUST preserve or strengthen the complete parent Condition
predicate. For parent condition set `C_parent` and child condition set
`C_child`, a valid derivation requires:

```text
AND(C_child) ⇒ AND(C_parent)
```

The implication MUST be established by a deterministic, profile-defined
algorithm for every Condition type and combination involved. Exact
preservation is sufficient. Adding an independently evaluated conjunct is a
strengthening. Replacing, deleting, broadening, changing the evaluation
authority of, or changing the failure behavior of a parent Condition is valid
only when the declared implication algorithm proves that the child predicate
still implies the parent predicate.

If no applicable implication algorithm exists, a child MAY preserve the
parent Condition exactly and add new Conditions, but it MUST NOT replace or
remove the parent Condition. An unknown, ambiguous, or indeterminate
implication result MUST fail closed as `condition_weakened` or
`delegation_indeterminate`, according to the profile's single-result failure
mapping.

### 11.4 Obligations

Each Obligation MUST identify:

- `obligation_id`, unique within the Grant Body;
- obligation type and schema version;
- obligated party;
- trigger;
- required action;
- due time or event;
- evidence or Receipt expected;
- enforcement mode;
- failure signal;
- descendant-trigger applicability and delegation behavior.

Grant Acceptance MUST acknowledge specific `obligation_id` values, not only
obligation types. Two Obligations of the same type remain distinct when their
recipient, trigger, due time, evidence target, or enforcement mode differs.
Because Acceptance also binds `grant_digest`, an Obligation identifier is
resolved only within that exact Grant Body.

Obligation **retention** and Obligation **propagation** are distinct:

- retention means the original Obligation remains attributable to the
  obligated party named by the Grant Body that created it;
- propagation means descendant exercise creates an additional Obligation in
  the child Grant Body, normally for the Delegate or child Executor.

The baseline delegation behavior is `retained`: the original Obligation is
not copied, its `obligation_id` remains scoped to its origin Grant Body, and
its definition MUST state whether descendant exercise can trigger it. A child
Grant MUST carry an integrity-protected reference to every retained,
descendant-applicable Obligation using the origin `grant_digest` and
`obligation_id`.

When propagation is required, the child Grant MUST contain a new Obligation
with a new `obligation_id`, a `source_obligation` reference, and the child
obligated party. The new party MUST accept that Obligation under Section
10.6. Propagation does not release the original obligated party unless an
explicit profile defines transfer semantics and an attributable release or
replacement record. The baseline profile does not infer transfer from
delegation.

A parent Obligation marked `non_inheritable` does not mean it may be silently
discarded. It means either that it remains confined to parent-branch exercise
or that authority subject to it cannot be delegated, as specified by the
Obligation definition.

An obligation that cannot be enforced by the receiver MUST be marked
`declared` or `externally_enforced`. The protocol MUST NOT claim that including
an Obligation guarantees compliance.

## 12. Delegation

### 12.1 Delegation Preconditions

A Grantee MAY delegate only when the active parent grant explicitly authorizes
delegation. Delegation MUST be denied when:

- delegation is absent or prohibited;
- remaining delegation depth is zero;
- the parent grant is inactive, expired, revoked, suspended, or
  indeterminate under fail-closed Policy;
- the derived Authority Scope cannot be proven to be a subset of the parent
  Authority Scope;
- required Purpose Assurance is weakened;
- an applicable critical extension is omitted, weakened, or cannot be
  compared;
- the proposed Grantee or Executor transition is not authorized by the
  parent's delegation rules;
- the child Delegate Policy cannot be proven to remain within the parent's
  redelegation ceiling;
- an unknown critical constraint prevents comparison;
- the Delegator cannot prove control of the parent grant;
- the proposed Delegate, audience, purpose, or context is outside the parent
  scope;
- a required consumable-authority reservation or shared-counter operation
  cannot be completed atomically;
- Accounting Domain Continuity cannot be established;
- the child status mechanism cannot satisfy the parent's descendant
  invalidation and maximum-staleness requirements.

### 12.2 Delegation Record

A Delegation Record SHOULD identify:

- delegation identifier and version;
- parent grant identifier and digest;
- derived grant identifier and digest;
- Delegator;
- Delegate;
- creation time;
- related Intent, Session Proposal, or Session, when known;
- Grant Acceptance identifier and digest, when acceptance is required;
- status-event, revocation, surrender, or replacement references;
- proof.

A Delegation Record MAY contain a derived human-readable summary of scope
reduction, constraints, obligations, remaining depth, or status. Such a
summary MUST be marked non-normative and MUST NOT be used for authorization.

The immutable parent and child Grant Bodies are the sole portable sources of
delegated Permission. Authoritative lifecycle state comes from the status
mechanism referenced by those Grant Bodies. If a Delegation Record conflicts
with either Grant Body or an authoritative status statement:

- the Delegation Record is invalid;
- the Grant Body and authoritative status remain controlling;
- the conflict MUST be surfaced as `delegation_record_mismatch`;
- an implementation MUST NOT merge fields or select the broader value.

### 12.3 Scope Narrowing and Subject Transition

Delegation applies two independent validations:

1. **Authority Scope Narrowing** determines whether the child conveys no more
   authority than the parent.
2. **Subject Transition Validation** determines whether Authority may move
   from the parent Grantee and Executor to the named Delegate and child
   Executor.

These validations MUST NOT be collapsed into one set-subset formula.

For every derived grant `G_child` and parent grant `G_parent`, Authority Scope
MUST satisfy:

```text
actions(G_child)          ⊆ actions(G_parent)
resources(G_child)        ⊆ resources(G_parent)
audiences(G_child)        ⊆ audiences(G_parent)
purposes(G_child)         ⊆ purposes(G_parent)
purpose_assurance_required(G_child)
                           ⪰ purpose_assurance_required(G_parent)
validity(G_child)         ⊆ validity(G_parent)
allocation(G_child)       ⊆ allocation(G_parent)
delegate_policy(G_child)  ⪯ redelegation_ceiling(G_parent)
delegation_depth(G_child) < delegation_depth(G_parent)
```

Here `⪰` means that the child Purpose Assurance requirement preserves or
strengthens every applicable parent requirement under the profile-defined
implication relation in Section 9.4. It does not define a universal ordering
of assurance modes.

Here `⪯` means that every downstream delegation transition authorized by the
child Delegate Policy is also authorized by the parent's redelegation
ceiling. It does not compare the parent rule for selecting the current child
with the child's rule for selecting a future descendant. A child that
prohibits delegation has an empty downstream policy, which satisfies this
relation.

Every inherited constraint and condition MUST be preserved or strengthened.
Every applicable authorization-affecting critical extension MUST be inherited
or transformed without weakening it under Section 10.5. Applicable Obligation
semantics MUST be preserved using the retention and propagation rules in
Section 11.4; copying every parent Obligation into the child is neither
required nor sufficient.

For consumable Authority, these per-child subset relations are necessary but
not sufficient. The Delegator MUST also satisfy the family-wide allocation and
accounting invariants, including Accounting Domain Continuity, in Section
9.7. Two child grants that each authorize `amount ≤ 100` violate a parent
budget of `100` if they can independently consume `100` without a shared
counter or partitioned reservation. A child that changes from `ledger-A` to
`ledger-B` also violates the invariant unless an atomic, verifiable
reservation or transfer binds `ledger-B` to consumption or unavailability in
`ledger-A`.

The subset relation MUST be defined per scope and constraint vocabulary.
String comparison, set comparison, numeric comparison, and URI-prefix
comparison are not interchangeable.

If a Verifier cannot establish the subset relation for a critical dimension,
the result MUST be `delegation_indeterminate` or `unsupported_constraint`, and
the derived grant MUST NOT be accepted under fail-closed Policy.

Subject Binding follows transition rules rather than subset rules. For
ordinary delegation:

```text
grantor(G_child)               = authorized Delegator
grantee(G_child)               = named Delegate
represented_principal(G_child) = represented_principal(G_parent)
authorized_executor(G_child)   = Delegate
                                  or an executor explicitly permitted
                                  by the parent delegation rule
```

Changing the Grantee and Executor from Agent A to Agent B is expected and does
not violate monotonic narrowing when the transition is authorized. The parent
Grant Body MUST define whether delegation is allowed. If delegation is
allowed, it MUST contain an explicit Delegate Policy that defines:

- current-transition eligibility for permitted Delegate identifiers, classes,
  organizations, or Evidence;
- whether the Delegate itself must be the child Authorized Executor;
- whether the Delegate may nominate a different Executor;
- required proof of control and Grant Acceptance;
- delegation Purpose, audience, depth, time, and Session context;
- the redelegation ceiling, if the child may receive further delegation
  authority.

The proposed child Subject Binding and context MUST satisfy the parent's
current-transition eligibility. Separately, any Delegate Policy carried by
the child Grant MUST monotonically narrow the parent's redelegation ceiling.
The comparison MUST cover, as applicable:

- eligible descendant identifiers and selector domains;
- permitted Executor transitions;
- required Evidence, proof of control, and acceptance;
- Purpose, audience, Session, time, organization, and context restrictions;
- maximum remaining depth and any profile-defined delegation constraints.

A child MUST NOT replace an exact-identifier selector with a class or
organization selector, relax required Evidence or acceptance, permit a
different Executor model, or broaden context unless the parent redelegation
ceiling explicitly authorizes that transition. Every profile supporting
redelegation MUST define a deterministic Delegate Policy comparison relation.
If the relation cannot be established, the result is
`delegate_policy_expansion` or `delegation_indeterminate`, according to the
profile's single-result failure mapping.

The baseline safe defaults are:

- `delegation.permitted` absent or false means delegation is prohibited;
- `delegation.permitted=true` without a valid Delegate Policy authorizes no
  Delegate and MUST NOT activate a derived grant;
- permitted Delegates are exact identifiers unless a declared profile defines
  class, organization, or Evidence matching;
- the Delegate MUST be the child Authorized Executor unless the Delegate
  Policy explicitly permits and constrains another Executor;
- a missing redelegation ceiling means the child MUST set delegation to
  prohibited with zero remaining depth;
- only the parent Grantee acting through its Authorized Executor may delegate;
  a different Delegator MUST be explicitly authorized.

`remaining_depth` limits chain length but never identifies who may receive
Authority. Depth greater than zero MUST NOT be interpreted as permission to
delegate to any Agent.

The Represented Principal MUST remain unchanged in ordinary delegation. A
change of Represented Principal is not validated as a child-subset operation.
It requires an independent authority source for the new Principal and MUST be
represented as a new Root Grant, explicitly re-rooted Grant, or permitted
multi-grant composition with its own proof and Policy evaluation.

If the child Grantee, Executor, Delegator, or Principal transition is not
authorized, verification MUST return `invalid_subject_transition` or
`principal_transition_not_permitted`, even when every Authority Scope
dimension is narrower.

The child status mechanism MUST be compatible with every ancestor's
descendant-status requirements. A child MAY use
`short_lived_no_revocation` only when the parent Delegate Policy and
applicable profile explicitly permit bounded offline descendants and define a
maximum lifetime, maximum revocation-observation delay, and receiver failure
behavior. It MUST NOT be used to bypass a parent requirement for online,
single-use, immediate, or fresher status. An incompatible child status
mechanism MUST return `status_mechanism_incompatible`.

### 12.4 Chain Integrity

A delegation chain MUST:

- terminate at a recognized Root Grant or local authority anchor;
- contain no cycles;
- preserve parent-child identifiers and digests;
- verify every Grantor proof;
- establish control by each Delegator over the parent Grantee identity or
  bound possession mechanism;
- remain within maximum depth and size limits;
- preserve required audience, purpose, and context bindings;
- contain no inactive ancestor grant.

A verifier MUST NOT accept a valid suffix of a chain when a required parent or
constraint has been omitted.

### 12.5 Delegation Acceptance

Delegation Acceptance uses the common Grant Acceptance mechanism in
Section 10.6. A Delegate MAY also request a narrower derived grant or declare
the delegation profile unsupported.

Acceptance confirms willingness to receive the derived grant and acknowledge
the identified obligations. It does not prove Capability, activate a
Collaboration Session, guarantee future performance, or alter the child Grant
Body. The Delegation Record SHOULD reference the verified Grant Acceptance
rather than copying its status or obligation acknowledgements.

### 12.6 Delegation and Impersonation

Delegation and impersonation MUST remain distinguishable.

In delegation:

- the Delegate acts as itself;
- the Delegator and original Principal remain attributable;
- the chain of authority is visible to the verifier as required;
- actions are recorded under the Delegate's identity.

If a profile permits impersonation, it MUST mark that mode explicitly and
define separate audit, consent, and security requirements. Implementations
MUST NOT silently represent impersonation as ordinary delegation.

### 12.7 Task Delegation and Service Invocation

Task delegation is an RFC-005 coordination action that asks another Agent to
perform work. Service invocation is a request to an Agent or endpoint. Neither
operation by itself transfers Authority.

An Agent MAY accept a task or service request while using only its own
Authority. If the task requires access to the caller's identity data, account,
payment instrument, private artifact, tool, or other protected resource, each
required Permission MUST be conveyed through a separate Authority Grant.

Implementations MUST NOT infer Authority delegation from:

- assignment of a task;
- selection of a worker or service;
- inclusion in a Session or workflow;
- Capability matching;
- payment for a service;
- transmission of input data that does not itself authorize further access.

A task reference MAY be bound into an Authority Grant for context, but the
task object is not the authorization source.

## 13. Grant Presentation and Exercise

An attempted authority exercise SHOULD bind:

- grant identifier or grant object;
- Grantee;
- Represented Principal;
- Authorized Executor and actual presenter;
- proof of possession;
- action;
- resource;
- purpose;
- presented Purpose Assurance;
- audience;
- timestamp and nonce;
- related Session Proposal or Session, task, stage, artifact, or event;
- request payload or immutable payload digest where material;
- proof profile and proof.

The Policy Enforcement Point MUST compare the attempted action with the
verified grant. It MUST NOT authorize an action merely because:

- the grant signature is valid;
- the presenter is the named Grantee;
- the grant contains some Permission;
- the grant was previously accepted in another Session;
- a related Agent has a high Trust or Capability score.

High-impact actions SHOULD use single-use or narrowly replay-bounded
presentations and SHOULD bind the exact payload or artifact digest.

## 14. Verification

Authority verification establishes protocol facts. It does not make the final
receiver decision.

### 14.1 Verification Inputs

A Verifier SHOULD receive:

- Authority Grant and complete required parent chain;
- required Grant Acceptances;
- presentation proof;
- Grantee, Represented Principal, Authorized Executor, and presenter;
- attempted action, resource, purpose, Purpose Assurance, and audience;
- Intent and Session Proposal or Session context;
- consumable-authority reservation and counter state when applicable;
- current time and freshness context;
- revocation and suspension information;
- applicable scope and constraint vocabularies;
- profile and proof-suite identifiers;
- local authority anchors.

### 14.2 Verification Checks

A Verifier MUST produce structured checks for applicable properties:

- structural validity;
- supported version and critical fields;
- Grant Body canonicalization and digest;
- critical-extension support;
- Grantor identity and proof;
- Grantee, Represented Principal, Authorized Executor, and presenter binding;
- required Grant Acceptance;
- proof of possession;
- Authority Request and nonce binding;
- Intent, Session Proposal or Session, action, resource, purpose, Purpose
  Assurance, and audience binding;
- issuance, not-before, expiration, and clock skew;
- status, revocation, and suspension;
- parent-chain completeness and integrity;
- monotonic narrowing;
- Delegate Policy and redelegation-ceiling narrowing;
- Purpose Assurance preservation;
- inherited critical-extension preservation;
- Subject Binding transition authorization;
- delegation depth;
- constraint comparison, Condition implication, and current Condition results;
- applicable Obligation retention and propagation;
- consumable-authority reservation, Accounting Domain Continuity, counter,
  and replay-safe consumption;
- descendant-status-mechanism compatibility;
- payload or artifact digest binding;
- duplicate or replay detection.

### 14.3 Verification Result

A Verification Result SHOULD identify:

- result identifier;
- verifier;
- grant and presentation identifiers;
- attempted action context;
- overall protocol status;
- per-check status and machine-readable reason;
- evaluated constraint-set digest;
- authority-chain digest;
- verification time;
- evidence and status sources;
- warnings and indeterminate checks;
- proof when the result is shared.

The overall protocol status SHOULD be one of:

- `valid`;
- `invalid`;
- `expired`;
- `revoked`;
- `suspended`;
- `not_yet_valid`;
- `insufficient_scope`;
- `invalid_chain`;
- `replay_detected`;
- `unsupported`;
- `indeterminate`.

`valid` means the defined protocol checks succeeded. It does not mean the
receiver MUST authorize the action.

### 14.4 Evaluation and Enforcement

After verification, the Policy Decision Point MAY produce:

- `permit`;
- `deny`;
- `conditional_permit`;
- `additional_evidence_required`;
- `human_approval_required`;
- `defer`.

The Policy Enforcement Point MUST enforce the decision and all pre-enforced
conditions. The receiver MAY keep its internal Policy and risk thresholds
private.

## 15. Lifecycle

### 15.1 Grant States

A grant lifecycle SHOULD support:

```text
offered
  → acceptance_pending
      → accepted_pending_activation
      → countered → replaced | cancelled | expired
      → rejected | cancelled | expired
  → accepted_pending_activation
      → active
      → cancelled | expired | replaced

active
  → suspended → active
  → expired | revoked | surrendered | replaced
```

The direct transition from `offered` to `accepted_pending_activation` applies
only when Acceptance is not required or valid request-time pre-acceptance
satisfies every required Acceptor.

`acceptance_pending` MAY contain multiple verified partial Acceptances, but it
MUST remain non-exercisable until all required Acceptors return `accepted`.
`conditionally_accepted` produces `countered`, not
`accepted_pending_activation`.

`accepted_pending_activation` means every required Acceptance is complete,
but one or more activation prerequisites remain, such as Session activation,
proof-of-possession registration, co-signature, status-mechanism readiness, or
human approval. Implementations SHOULD expose structured
`activation_pending_reasons`.

`expired`, `revoked`, and `surrendered` SHOULD be terminal for the specific
grant identifier. Renewal SHOULD create a new version or replacement grant so
that audit history remains unambiguous.

### 15.2 Activation

A grant becomes active only when all activation conditions defined by its
profile are satisfied. These MAY include:

- Grantor issuance;
- every required Grant Acceptance;
- required co-signatures;
- Session activation;
- human approval;
- proof-of-possession registration;
- status-mechanism readiness when required by the selected mode.

An Acceptance MUST NOT supply an activation condition that is absent from the
Grant Body. A conditional Acceptance requires replacement as specified in
Section 10.6.

### 15.3 Suspension

Suspension temporarily prevents authority exercise without erasing the grant
or its audit history. A suspension signal MUST identify:

- affected grant or subtree;
- issuer of the signal;
- effective time;
- reason class;
- expected re-evaluation or recovery mechanism;
- proof.

Resumption MUST re-check expiration, revocation, chain validity, and required
conditions.

### 15.4 Revocation

Revocation prevents future exercise of a grant. A profile MUST define:

- who may revoke;
- how revocation status is authenticated;
- effective time semantics;
- propagation to derived grants;
- cache and maximum-staleness rules;
- behavior when status is unavailable;
- whether emergency local denial overrides remote status.

Revoking a parent grant MUST invalidate all descendant grants unless a profile
defines an independently re-rooted replacement with explicit authorization.
This is a normative authorization-state rule, not a claim that every offline
enforcer learns the revocation instantaneously. A profile MUST define how
descendant status is observed, its maximum propagation or staleness bound,
and behavior before fresh status can be obtained. A parent requiring
immediate or online revocation observation MUST prohibit descendants whose
status mechanism cannot meet that requirement. Any permitted
`short_lived_no_revocation` descendant remains exposed until its bounded
expiry, and that residual window MUST be explicitly authorized and evaluated
by receiver-local Policy.

### 15.5 Surrender

A Grantee MAY surrender a grant. Surrender indicates that the Grantee no
longer intends to exercise it. The Grantor or enforcement domain SHOULD make
the surrender effective and publish status according to the applicable
profile.

### 15.6 Renewal and Replacement

Renewal and replacement MUST NOT silently expand authority. A replacement
grant MUST identify the prior grant and whether it narrows, preserves, or
changes scope. Any expansion requires fresh Grantor authorization and
receiver-local evaluation.

## 16. Session Binding

RFC-003 produces authority inputs for RFC-004. It does not establish the
Collaboration Session.

A participant proposing a future Session MAY mint a `session_proposal_id`
before authority negotiation. RFC-004 will define any formal Session Initiator
role. This identifier correlates Intent, Requirements, Authority Requests,
offered Grants, and acceptances. It is not a `session_id`, does not indicate
agreement, and conveys no Permission.

An Authority Grant issued for a not-yet-established Session MUST bind the
`session_proposal_id`, not an assumed final `session_id`. It MUST also state
whether it:

- becomes eligible for activation only after RFC-004 Session activation;
- may be reused outside that proposal;
- must be replaced by a final Session-bound grant after activation.

A proposed Session Agreement SHOULD reference:

- Session Proposal identifier;
- accepted Authority Grant identifiers and digests;
- required Grant Acceptance identifiers and digests;
- participant-specific Permission;
- constraints, conditions, and obligations;
- evidence and verification snapshots;
- grant validity and renewal conditions;
- suspension and revocation behavior.

RFC-004 assigns or confirms the final `session_id` and records its relation to
the `session_proposal_id`. After activation, enforcement MAY use that verified
mapping, or the Grantor MAY issue a replacement Grant bound directly to the
final `session_id`. RFC-003 does not assume that the two identifiers are equal.

An Authority Grant MAY predate a Session, be issued for a Session Proposal, or
be issued for an already active Session. Reuse across Sessions MUST be
explicit.

Session termination does not automatically revoke a reusable parent grant.
Session-bound derived grants MUST become unusable when the Session reaches a
terminal state unless a profile explicitly defines a narrower post-session
purpose such as audit retrieval.

## 17. Grant Composition

### 17.1 Composition Evaluation

Multiple grants MUST NOT be combined implicitly. By default, one attempted
action must be fully authorized by one active grant and its chain.

A receiver MAY combine grants only when a profile, an explicit
Grant-Composition object, or local Policy defines the composition. A portable
Grant-Composition object SHOULD identify:

- composition identifier and version;
- ordered grant identifiers and Grant Body digests;
- attempted action, resource, audience, Purpose, required Purpose Assurance,
  Principal, and Executor;
- composition mode;
- threshold, grouping, or role semantics when applicable;
- constraint, condition, obligation, and consumable-budget merge rules;
- critical-extension merge and enforcement rules;
- status-mechanism compatibility, freshness, and failure rules;
- explicit delegation and Grant-issuance result, including a composed Delegate
  Policy, when either is requested;
- Session Proposal or Session binding;
- validity and status-evaluation time;
- issuer or evaluator and proof.

Composition modes MAY include:

- `all_of`: every identified grant and condition is required;
- `any_of`: one complete grant is sufficient;
- `threshold`: at least a defined number or role set must authorize;
- `intersection`: only authority common to all identified grants is usable;
- `explicit_union`: distinct Permission fragments may be combined only under
  a profile that defines every merge rule.

`explicit_union` MUST NOT be the default. An implementation MUST NOT take the
Grantee from one grant, Principal from another, action from a third, and
resource from a fourth merely because every field appears somewhere.

For the following rules, an **applicable contributing grant** is a grant whose
authority, approval, role, or condition is actually counted toward the
selected composition result. In `any_of`, this may be one selected branch. In
`threshold`, it is the set counted toward the threshold. A profile MAY require
validation of additional listed alternatives, but it MUST distinguish them
from the grants that authorize the result.

For every composition:

- Grantee, Represented Principal, Authorized Executor, audience, and Purpose
  MUST be identical or compatible under an explicit profile rule;
- the composed Purpose Assurance requirement MUST imply every applicable
  contributing requirement under the profile-defined assurance relation;
- constraints and conditions MUST be intersected or otherwise combined
  without weakening any contributing grant;
- applicable obligations MUST be preserved;
- every applicable authorization-affecting critical extension MUST remain
  present and enforceable under an explicit non-weakening merge rule;
- every applicable contributing grant and chain MUST be valid and checked for
  current status;
- the composed status requirements MUST satisfy every applicable contributing
  grant's status mechanism, freshness, descendant propagation, and failure
  requirements; an incompatible combination MUST fail with
  `status_mechanism_incompatible`;
- a consumable budget MUST NOT be counted more than once or converted into
  replicable Authority;
- the composed Authority MUST NOT exceed the Authority produced by applying
  the declared composition mode to the contributing grants and Grantors.

For `threshold`, `all_of`, and other joint modes, no individual contributing
Grantor needs to be independently able to authorize the final action. The
profile MUST instead establish that the required set, threshold, roles, or
joint control relation is itself an authorized source for that action.

### 17.2 Delegation and Grant Issuance

Composition does not imply delegation authority or Grant Issuance Authority.
Unless an explicit composition profile and Grant-Composition object authorize
them, the composed result has:

```text
delegation.permitted       = false
grant_issuance.permitted   = false
composed_delegate_policy   = empty
```

The ability to exercise a composed action MUST NOT be interpreted as
permission to delegate that action, issue a derived Grant, issue a Root Grant,
or act as a Grantor.

If a composition explicitly produces delegation authority:

- delegation or Grant issuance MUST be an explicit Permission authorized by
  the declared composition mode;
- the Grant-Composition object MUST identify the composed Delegate Policy and
  the applicable contributing grants used to derive it;
- every transition permitted by the composed Delegate Policy MUST be
  permitted by every applicable contributing grant's redelegation ceiling;
- a contributing grant with no redelegation ceiling contributes an empty
  ceiling, so the composition cannot produce delegation authority;
- Purpose Assurance, Conditions, critical extensions, status requirements,
  obligations, allocation limits, and remaining depth applicable to
  delegation MUST still satisfy all contributing grants.

Thus, a composed Delegate Policy is bounded by the intersection of all
applicable redelegation ceilings, not their union. An incompatible or broader
result MUST fail with `composition_not_permitted` or
`delegate_policy_expansion` according to the profile's single-result mapping.

A successful composition evaluation is a local decision input. It does not
create a new portable Authority Grant unless an authorized Grantor issues a
new immutable grant. Even when composition authorizes Grant issuance, the
portable result exists only after that separately authorized Grantor creates
and proves a new immutable Grant Body.

## 18. Multi-Party and Multi-Principal Collaboration

Multi-party collaboration MUST NOT assume that one participant's grant,
Capability evaluation, or Policy decision applies to all participants.

A multi-party authority model MUST make explicit:

- which Grantor controls each resource;
- which Principal each Agent represents for each action;
- which participant is the Grantee of each Permission;
- which Agent or service is the Authorized Executor;
- whether joint approval or threshold authorization is required;
- whether grants are independent, conjunctive, or alternative;
- how withdrawal, suspension, and revocation affect shared actions;
- which participant must satisfy each Obligation.

An Agent representing multiple Principals MUST identify the applicable
Principal and authority chain for each security-relevant action. Authority
from one Principal MUST NOT be combined with a resource or Permission from
another unless an explicit composition rule permits it.

## 19. Privacy and Data Minimization

Authority negotiation can expose organizational structure, resource names,
operating limits, financial limits, internal roles, approval paths, and future
intent.

Implementations SHOULD:

- request the minimum Permission necessary;
- disclose only Capability Evidence relevant to the Intent;
- prefer references or derived proofs over unnecessary raw credentials;
- avoid publishing sensitive Authority Grants in public directories;
- minimize stable cross-domain identifiers;
- separate public Capability advertisement from private Authority;
- support audience-restricted and pairwise presentations;
- define retention and deletion behavior for rejected requests;
- prevent logs from capturing reusable Bearer Grants or secret proof material;
- allow a Grantor to decline without exposing full Policy.

Selective disclosure MUST NOT hide fields necessary to establish grant scope,
chain integrity, critical constraints, or the attempted-action binding.

## 20. Failure Semantics

Implementations MUST distinguish at least:

| Failure | Meaning |
|---|---|
| `malformed_object` | Required structure cannot be parsed |
| `unsupported_version` | Object version is unsupported |
| `unsupported_action` | Action vocabulary or action is unsupported |
| `unsupported_constraint` | A required constraint cannot be evaluated |
| `unsupported_critical_extension` | A critical extension cannot be understood or enforced |
| `canonicalization_failed` | Grant Body cannot be canonicalized under its declared profile |
| `digest_mismatch` | A declared digest does not match canonical content |
| `capability_not_established` | Receiver did not establish required Capability |
| `grant_not_found` | Referenced grant cannot be resolved |
| `invalid_grant_proof` | Grantor proof is invalid |
| `invalid_possession_proof` | Presenter did not prove control of the bound mechanism |
| `wrong_grantee` | The grant or attempted-action context names a Grantee different from the Grantee bound by the Authority Grant |
| `wrong_principal` | Attempted Represented Principal is not authorized |
| `wrong_executor` | Presenter is not the Authorized Executor |
| `invalid_subject_transition` | Child Grantee or Executor transition is not authorized |
| `principal_transition_not_permitted` | Derived grant changes Represented Principal without an independent authority source |
| `wrong_audience` | Grant is not valid for this enforcement domain |
| `wrong_purpose` | Attempted purpose is outside the grant |
| `insufficient_scope` | Action or resource is outside Permission |
| `condition_not_satisfied` | Required condition is not satisfied |
| `grant_not_yet_valid` | Grant validity has not begun |
| `grant_expired` | Grant validity has ended |
| `grant_suspended` | Grant is temporarily inactive |
| `grant_revoked` | Grant has been revoked |
| `invalid_delegation_chain` | Parent chain or a chain proof is invalid |
| `delegation_not_permitted` | Parent does not allow delegation |
| `delegation_depth_exceeded` | Derived grant exceeds remaining depth |
| `delegate_policy_expansion` | Child Delegate Policy exceeds the parent's redelegation ceiling |
| `scope_expansion` | Derived scope is not a subset of parent scope |
| `purpose_assurance_weakened` | Derived grant does not preserve every applicable parent Purpose Assurance requirement |
| `constraint_weakened` | Derived grant weakens an inherited constraint |
| `condition_weakened` | Child Conditions do not deterministically imply all applicable parent Conditions |
| `critical_extension_stripped` | Derived grant omits or weakens an applicable parent critical extension |
| `obligation_removed` | Derived grant removes applicable retained or propagated Obligation semantics |
| `acceptance_required` | A required Grant Acceptance is absent or invalid |
| `acceptance_countered` | Conditional Acceptance proposed new terms; original grant cannot activate |
| `delegation_record_mismatch` | Delegation Record conflicts with a Grant Body or status source |
| `composition_not_permitted` | Multiple grants or composed delegation/Grant issuance were used without an applicable explicit rule |
| `budget_reservation_failed` | Consumable Authority could not be reserved atomically |
| `budget_exhausted` | No consumable Authority remains |
| `accounting_unavailable` | Required counter, ledger, or allocator is unavailable |
| `accounting_domain_discontinuity` | Child accounting domain is neither the parent domain nor verifiably backed by it |
| `replay_detected` | Presentation or request was replayed |
| `status_unavailable` | Required status information cannot be obtained |
| `status_too_stale` | Status snapshot exceeds the profile freshness limit |
| `status_mechanism_incompatible` | A child or composed status mechanism cannot satisfy an applicable parent or contributing grant requirement |
| `policy_denied` | Local Policy denied the action without disclosing details |

A protocol error MUST NOT be described as a Trust conclusion. Error responses
SHOULD disclose no more sensitive Policy or resource information than is
necessary for safe recovery.

## 21. Security Considerations

### 21.1 Capability Inflation

A subject may exaggerate ability by presenting self-assertion as independent
Evidence or by omitting test context. Capability Statements MUST identify
Claimant, Subject, context, source, and Evidence class.

### 21.2 Permission Inference

Implementations MUST NOT infer Permission from discovery metadata, identity,
Capability, Trust Score, payment, relationship, or successful transport
authentication.

### 21.3 Grantor Impersonation and Key Substitution

Grant proofs MUST use verification methods authorized for grant issuance.
Verifiers MUST process key rotation, deactivation, recovery, and proof purpose
according to RFC-001 and the applicable proof profile.

### 21.4 Grant Theft

Portable grants are high-value credentials. High-risk profiles SHOULD bind
grants to proof-of-possession keys, minimize lifetime and scope, protect them
at rest and in transit, and prevent disclosure through logs or error messages.

### 21.5 Replay

Authority Requests and grant presentations SHOULD use audience-bound nonces,
timestamps, single-use identifiers, or replay caches. High-impact actions MUST
bind the exact action and payload or artifact digest where substitution would
change the result.

### 21.6 Grant Transplant

A valid grant from one audience, Session, action, resource, purpose, or
payload MUST NOT be accepted in another unless reuse is explicit.

### 21.7 Scope Ambiguity

Wildcard, URI-pattern, hierarchical resource, and action-containment rules can
produce accidental expansion. Profiles MUST define deterministic scope
comparison, and Verifiers MUST fail closed on unknown critical semantics.

### 21.8 Delegation Expansion

Every child Authority Scope MUST be proven to be a subset of its parent
Authority Scope. Implementations MUST separately validate the Subject Binding
transition and MUST check all scope dimensions, constraints, obligations,
validity, audience, Purpose, required Purpose Assurance, critical extensions,
allocation, Accounting Domain Continuity, Delegate Policy narrowing, and
remaining delegation depth rather than only action names. A child MUST NOT
receive a broader redelegation envelope than its parent conveyed.

### 21.9 Chain Truncation and Splicing

Parent identifiers and digests MUST bind the complete ordered chain. A
Verifier MUST reject omitted ancestors, reordered links, duplicated links,
cycles, or links borrowed from a different chain.

### 21.10 Confused Deputy

A more privileged Agent may be induced to use its Authority for another
party's purpose. Grants and action presentations SHOULD bind requester,
Grantee, purpose, resource, Session, and payload. Policy Enforcement Points
SHOULD verify that the requested action remains within the initiating
Principal's context.

### 21.11 Principal Confusion

An Agent representing multiple Principals may apply authority from the wrong
Principal. Security-relevant actions MUST identify the represented Principal
and applicable authority chain.

### 21.12 Obligation, Constraint, and Critical-Extension Stripping

Critical constraints, applicable critical extensions, and inherited
Obligation semantics MUST be integrity-protected. Unknown critical fields,
missing inherited fields, lost retained-Obligation references, missing
propagated Obligations, and changed canonical forms MUST cause verification
failure or an indeterminate result.

### 21.13 Revocation Race and Stale Status

Profiles MUST define status freshness, cache limits, fail-open or fail-closed
behavior, and emergency local denial. High-impact actions SHOULD obtain fresh
status close to the point of exercise.

### 21.14 Time-of-Check to Time-of-Use

Authority may change between verification and exercise. The Policy
Enforcement Point SHOULD minimize this interval and re-check volatile
conditions, revocation, Session state, resource state, and cumulative limits
at the point of action.

### 21.15 Counter and Budget Races

Distributed use of amount, rate, quantity, or one-time constraints can exceed
limits under concurrent execution. Profiles using consumable authority MUST
define atomic reservation, serialization, reconciliation, or conservative
failure behavior and satisfy Section 9.7. A signed static grant alone cannot
enforce a global consumable budget.

### 21.16 Delegation Bombs

Attackers may submit excessively deep, wide, or complex chains. Verifiers MUST
bound chain depth, object count, reference depth, resolution time, proof
operations, and constraint-evaluation cost.

### 21.17 Downgrade

Participants MUST NOT silently remove proof-of-possession, audience binding,
required Purpose Assurance, critical constraints, authorization-affecting
critical extensions, revocation checks, or stronger proof suites during
negotiation. Any downgrade MUST be explicit and subject to receiver-local
Policy.

### 21.18 Liveness Confusion

Identity validity and Authority validity do not prove that an Agent is
currently reachable or operating safely. A profile MAY require current
liveness or runtime attestation as a condition. Liveness failure SHOULD
suspend exercise rather than silently erase audit history.

### 21.19 Legal and Organizational Overclaiming

A cryptographically valid grant proves an attributable protocol assertion. It
does not prove legal ownership, employment authority, contractual capacity, or
regulatory compliance. Such assertions require domain Evidence and local
Policy.

### 21.20 Grant Spam and Unaccepted Obligations

Attackers may issue unsolicited grants to create misleading responsibility
records, expose resource names, or attach unwanted obligations. Required Grant
Acceptance MUST gate activation, and rejection or non-response MUST NOT create
an adverse protocol inference.

### 21.21 Digest and Canonicalization Confusion

Different serializations, omitted extensions, proof-inclusive hashes, or
reused grant identifiers can split verifier interpretation. Profiles MUST
define one canonical Grant Body, exact digest coverage, and strict duplicate
field behavior. Replacements MUST use new identifiers.

### 21.22 Grant Composition Escalation

An attacker may splice compatible-looking fields from several individually
insufficient grants. Multiple grants MUST NOT be combined without an explicit
composition rule, and all Principal, Executor, constraint, obligation,
Purpose Assurance, critical-extension, status, and consumable-budget
invariants MUST survive composition. Composition MUST NOT create delegation or
Grant Issuance Authority by default; any composed Delegate Policy must remain
within the intersection of all applicable redelegation ceilings.

### 21.23 Purpose Washing

An actor may declare a benign Purpose while acting for another reason.
Verifiers MUST distinguish declaration from context binding, attestation, and
enforcement. Audit requirements MUST be expressed as Obligations. A high-risk
receiver MUST NOT treat a self-declared Purpose as proof of actual intent.

## 22. Conformance

An implementation MUST state which roles, object profiles, scope vocabularies,
proof suites, status mechanisms, allocation modes, critical extensions,
acceptance rules, Purpose Assurance modes, Delegate selector and comparison
algorithms, Condition implication algorithms, and composition modes it
implements.

### 22.1 Capability Negotiator Conformance

A conformant Capability Negotiator:

1. MUST distinguish Capability from Permission;
2. MUST bind requirements and responses to the exact Intent and context;
3. MUST preserve the issuer and provenance of Capability Evidence;
4. MUST identify self-assertion as such;
5. MUST NOT produce a universal competence or Trust verdict;
6. MUST support explicit unsupported, unavailable, declined, and indeterminate
   outcomes.

### 22.2 Grantor Conformance

A conformant Grantor:

1. MUST issue attributable, bounded, time-limited grants;
2. MUST identify Grantee, Represented Principal, Authorized Executor, action,
   resource, audience, Purpose, and Purpose Assurance;
3. MUST define all security-critical defaults;
4. MUST NOT infer Permission from Capability alone;
5. MUST NOT grant broader Authority than its verifiable or configured source;
6. MUST define delegation, status, revocation, and replacement behavior;
7. MUST integrity-protect critical constraints and obligations;
8. MUST bind the grant to the related request or explicitly identify an
   unsolicited grant;
9. MUST issue an immutable Grant Body with defined digest coverage and use a
   new identifier for replacement;
10. MUST declare required Grant Acceptances and critical extensions;
11. MUST define and enforce allocation semantics for consumable Authority.

### 22.3 Delegator Conformance

A conformant Delegator:

1. MUST prove control of an active delegable parent grant;
2. MUST produce a derived grant whose Authority Scope monotonically narrows
   the parent;
3. MUST preserve or strengthen inherited constraints and conditions and
   preserve applicable Obligation retention and propagation semantics;
4. MUST reduce remaining delegation depth;
5. MUST bind parent and child identifiers and digests;
6. MUST NOT impersonate the original Grantor or Principal;
7. MUST expose revocation and chain status according to the profile;
8. MUST preserve Principal continuity and make every Executor transition
   explicit;
9. MUST validate the Grantee and Executor transition independently from scope
   narrowing;
10. MUST preserve Purpose Assurance requirements and
    authorization-affecting critical extensions;
11. MUST enforce family-wide allocation invariants and Accounting Domain
    Continuity for consumable Authority;
12. MUST apply the safe Delegate defaults or an explicit Delegate Policy;
13. MUST ensure the child status mechanism can satisfy ancestor revocation and
    status-freshness requirements;
14. MUST prove that any child Delegate Policy monotonically narrows the
    parent's redelegation ceiling;
15. MUST use deterministic implication rules for any Condition replacement.

### 22.4 Grant Acceptor Conformance

A conformant Grant Acceptor:

1. MUST bind acceptance to the exact `grant_id` and `grant_digest`;
2. MUST identify its role and authority to accept;
3. MUST explicitly acknowledge applicable obligations;
4. MUST confirm the bound proof-of-possession key when required;
5. MUST support rejection without creating an Obligation or adverse protocol
   inference;
6. MUST NOT represent technical acceptance as legal liability or Session
   activation.

### 22.5 Authority Verifier Conformance

A conformant Authority Verifier:

1. MUST validate proof, Grantee, Principal, Executor, audience, Purpose,
   Purpose Assurance, scope, time, status, and replay properties as
   applicable;
2. MUST validate the complete required delegation chain;
3. MUST use profile-defined subset algorithms for every critical dimension;
4. MUST validate Grant Body canonicalization, digests, required acceptances,
   and critical extensions;
5. MUST validate applicable consumable-authority accounting and explicit
   composition rules;
6. MUST independently validate every Grantee, Represented Principal, and
   Authorized Executor transition in the delegation chain;
7. MUST verify Purpose Assurance preservation, critical-extension
   inheritance, applicable Obligation semantics, Accounting Domain Continuity,
   and descendant-status compatibility;
8. MUST verify Delegate Policy narrowing and deterministic Condition
   implication for every derived grant;
9. MUST ensure Grant Composition explicitly preserves Purpose Assurance,
   critical extensions, and status requirements and defaults delegation and
   Grant issuance to prohibited;
10. MUST produce structured per-check results;
11. MUST distinguish invalid, expired, revoked, suspended, unsupported, and
   indeterminate outcomes;
12. MUST NOT turn verification success into an automatic Trust decision;
13. MUST pass positive and negative test vectors for supported profiles.

### 22.6 Policy Enforcement Point Conformance

A conformant Policy Enforcement Point:

1. MUST bind an attempted action to a verified grant and current local
   decision;
2. MUST enforce critical conditions before or during execution;
3. MUST reject insufficient scope and inactive grants;
4. MUST re-check volatile status and perform required atomic reservation or
   consumption operations;
5. MUST record an attributable event or Receipt for audit-relevant exercise;
6. MUST reject implicit multi-grant field splicing;
7. MUST NOT rely solely on identity, transport authentication, or Trust Score.

## 23. Relationship to Other ACF RFCs

- [RFC-000](./000-agent-collaboration-framework.md) defines the constitutional
  distinction between Capability, Permission, Authority, Trust, and local
  Policy.
- [RFC-001](./001-agent-discovery-and-identity.md) establishes identifiers,
  proof of control, verification methods, and key lifecycle.
- [RFC-002](./002-metadata-requirements-and-evidence-exchange.md) carries
  Capability Evidence, Grantor-authority Evidence, Metadata Requirements, and
  Decision Packages.
- RFC-004 binds accepted Authority Grants, constraints, conditions, and
  obligations into a Collaboration Session.
- RFC-005 binds authority exercise to tasks, events, artifacts, and handoffs.
- RFC-006 defines Receipts, correction, revocation records, and dispute
  signals related to grants and authority exercise.
- RFC-007 maps RFC-003 objects to concrete transports and authorization
  protocols.
- RFC-008 consolidates cross-domain security and composition risks.

## 24. Mappings to Existing Authorization Standards

RFC-003 defines ACF-level collaboration semantics. It does not replace mature
authorization protocols. RFC-007 profiles SHOULD reuse those protocols and
state exactly which RFC-003 objects and invariants they preserve.

| Existing standard | Candidate RFC-003 mapping | What the existing standard does not by itself establish for ACF |
|---|---|---|
| [RFC 9396: OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396) | `authorization_details` can carry an Authority Request's fine-grained action, resource, data type, location, amount, and profile-specific constraints. An OAuth authorization-details type can serve as an RFC-003 Permission vocabulary. | Agent Capability Evidence, the Capability-versus-Permission distinction, generic Principal/Executor delegation chains, Grant Acceptance, ACF Session binding, and family-wide consumable-authority accounting remain profile requirements. |
| [RFC 9635: GNAP Core](https://www.rfc-editor.org/rfc/rfc9635) | A GNAP grant request and its `access` structures can bind an Authority Request; interaction and continuation can carry negotiation and required approval; issued access tokens can represent Authority Grant Tokens. | An ACF binding still needs Agent/Principal/Executor semantics, Capability Evidence linkage, monotonic delegation rules, obligations, Session Proposal binding, immutable Grant Body digests, and ACF Receipt semantics. |
| [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693) | `subject_token` can represent the party on whose behalf authority is requested; `actor_token` and the JWT `act` chain can represent the Authorized Executor and delegation actors; the issued token can encode a derived Authority Grant under a profile. | RFC 8693 deliberately leaves token syntax, token semantics, trust model, and many deployment rules to profiles. An ACF profile must add Grant Body, Authority Scope narrowing, Subject Transition, constraint, Acceptance, status-propagation, and consumable-authority rules. Impersonation MUST remain distinct from delegation. |
| [RFC 9767: GNAP Resource Server Connections](https://www.rfc-editor.org/rfc/rfc9767) | The GNAP access-token model can encode audience, key binding, access rights, validity, Resource Owner, and client instance; token introspection can implement status-aware Authority Verification; downstream token derivation can implement a derived Authority Grant. | An ACF binding still needs explicit Grant Body and digest rules, Delegation Record source-of-truth rules, generic non-GNAP transport continuity, Grant Acceptance, Purpose Assurance, ACF Session binding, and family-wide budget invariants. |
| [RFC 9449: OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) | DPoP can be a proof-of-possession profile for OAuth-based Authority Grant Tokens and action presentations. | DPoP does not define Capability Evidence, Permission semantics, delegation narrowing, Principal representation, Grant Acceptance, or Session lifecycle. |
| [W3C Verifiable Credentials Data Model v2.0](https://www.w3.org/TR/vc-data-model-2.0/) | Capability Statements, Capability Evidence, representation claims, or an Authority Grant profile may be encoded as credentials or presentations. | Credential validity proves an attributable claim and integrity properties, not receiver authorization, resource enforcement, consumable accounting, or domain truth. |

A mapping claiming RFC-003 conformance MUST document:

1. the source field for Grantee, Represented Principal, Authorized Executor,
   action, resource, audience, Purpose, validity, and constraints;
2. how Grant Acceptance and proof of possession are represented;
3. how immutable Grant Body digests, critical extensions, status, revocation,
   replacement, and chain integrity are preserved;
4. whether the mapped format supports replicable, partitioned,
   shared-counter, exclusive-transfer, or single-use Authority;
5. how Session Proposal and final Session bindings are carried;
6. which semantics are unavailable or require local side state.

Two formats are not interoperable merely because both can carry a signed
token. Interoperability requires equivalent authorization meaning and
enforcement behavior.

## 25. Relationship to Existing AgentNexus Work

| Existing work | Relationship to RFC-003 |
|---|---|
| [ADR-005: Gatekeeper Three Modes](../../docs/adr/005-gatekeeper-three-modes.md) | Example receiver-local Policy Decision Point and Policy Enforcement Point |
| [ADR-007: Action Layer](../../docs/adr/007-action-layer-protocol.md) | Historical structured-action input; task actions require explicit Authority under this RFC |
| [ADR-013: Enclave Collaboration](../../docs/adr/013-enclave-collaboration-architecture.md) | Reference resource, role, and local permission model |
| [ADR-014: Governance and Trust Network](../../docs/adr/014-governance-trust-network.md) | Evidence sources and constraint-hash input; Trust calculations remain local Policy |
| [Coding Coordination V1](../../docs/design/design-coding-coordination-v1.md) | Reference Delegation Record and stage-scoped authority exercise |
| [Enclave Permission Model](../../docs/external/enclave-permission-model.md) | Existing integration profile for role and resource constraints |

The current AgentNexus `CapabilityToken` implementation is an experimental
Authority Grant Token profile. Its `permissions`, resource scope, constraints,
validity, delegation links, constraint hash, and signature are useful
implementation inputs.

Current behavior does not define RFC-003 semantics. In particular:

- a `role` string is not itself Permission;
- `r`, `rw`, and `admin` require a profile-defined action and resource mapping;
- string-prefix resource comparison is not universally safe;
- failure to obtain revocation status must follow an explicit profile Policy;
- a derived grant must validate all critical dimensions and every required
  ancestor;
- Principal and Authorized Executor bindings must be explicit;
- required Grant Acceptance cannot be inferred from token possession;
- a mutable token row is not an immutable Grant Body and status must be
  separated from digest-covered authorization content;
- per-token amount checks do not enforce a family-wide consumable budget;
- delegation depth does not authorize arbitrary recipients, and a child
  Delegate Policy must remain within the parent's redelegation ceiling;
- unknown critical extensions and constraints must fail closed;
- a signed grant does not establish Capability, Trust, or legal authority.

## 26. Open Questions and Profile Work

### 26.1 Open Questions

1. Which baseline serialization, canonicalization, and proof suite should be
   mandatory for the first Authority Grant profile?
2. Should the baseline profile require proof of possession and prohibit
   portable Bearer Grants?
3. Which action, resource, purpose, constraint, and obligation registries are
   required for interoperable implementations?
4. How should profiles express deterministic subset relations for structured
   resource selectors?
5. Which revocation and suspension status mechanisms should be mandatory?
6. How should offline or partitioned Policy Enforcement Points handle status
   freshness?
7. Which party set must accept when Grantee, Represented Principal, and
   Authorized Executor are different entities?
8. Which consistency, reservation, and reconciliation profiles should be
   mandatory for consumable Authority across federated enforcement domains?
9. Which privacy-preserving proof formats can demonstrate authority without
   disclosing the complete organizational chain?
10. How should threshold, joint, or multi-Principal grants be represented?
11. Should capability demonstration challenges be standardized here or in a
    separate capability-evidence profile?
12. Which existing authorization systems should receive the first RFC-007
    mappings?

### 26.2 Baseline Profile Deliverables

The following are intentionally profile-stage work rather than unresolved
Core semantics. A baseline profile MUST NOT claim interoperable RFC-003
support until it publishes:

1. a normative Delegate Policy JSON structure, including
   current-transition eligibility and the redelegation ceiling;
2. deterministic Delegate selector matching and Delegate Policy comparison
   algorithms;
3. complete machine-readable parent/child Grant positive and negative test
   vectors, with one expected result per vector;
4. deterministic Condition implication algorithms for every supported
   Condition type and composition;
5. a canonicalization profile, mandatory proof suite or suites, and JSON
   Schemas for all profile objects.

These deliverables may evolve independently of the Core RFC provided they
preserve its non-expansion, non-downgrade, evidence, status, and
receiver-decision boundaries.

## 27. References

### 27.1 Normative References

- [RFC-000: Agent Collaboration Framework Architecture](./000-agent-collaboration-framework.md)
- [RFC-001: Agent Discovery and Identity Establishment](./001-agent-discovery-and-identity.md)
- [RFC-002: Metadata Requirements and Evidence Exchange](./002-metadata-requirements-and-evidence-exchange.md)
- [RFC 2119: Key words for use in RFCs to Indicate Requirement Levels](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words](https://www.rfc-editor.org/rfc/rfc8174)

### 27.2 Informative References

- [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9396: OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396)
- [RFC 9449: OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9635: Grant Negotiation and Authorization Protocol](https://www.rfc-editor.org/rfc/rfc9635)
- [RFC 9767: GNAP Resource Server Connections](https://www.rfc-editor.org/rfc/rfc9767)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [W3C Verifiable Credentials Data Model v2.0](https://www.w3.org/TR/vc-data-model-2.0/)
- [ADR-005: Gatekeeper Three Modes](../../docs/adr/005-gatekeeper-three-modes.md)
- [ADR-013: Enclave Collaboration](../../docs/adr/013-enclave-collaboration-architecture.md)
- [ADR-014: Governance and Trust Network](../../docs/adr/014-governance-trust-network.md)

## Appendix A. Illustrative Authority Request

The following example is non-normative:

```json
{
  "type": "acf:AuthorityRequest",
  "version": "0.3",
  "request_id": "authreq_01J...",
  "intent_id": "intent_01J...",
  "session_proposal_id": "session_proposal_01J...",
  "session_binding": {
    "activation": "requires_session_activation",
    "reuse": "prohibited",
    "finalization": "verified_proposal_to_session_mapping"
  },
  "requester": "did:example:coordinator",
  "grantee": "did:example:worker",
  "represented_principal": "did:example:project-owner",
  "authorized_executor": "did:example:worker",
  "grantor": "did:example:project-owner",
  "permissions": [
    {
      "action": "artifact:read",
      "resource": "urn:acf:artifact:requirements-v3",
      "purpose": "task:implement",
      "audience": "did:example:vault"
    },
    {
      "action": "artifact:write",
      "resource": "urn:acf:collection:implementation-output",
      "purpose": "task:implement",
      "audience": "did:example:vault"
    }
  ],
  "purpose_assurance_required": ["context_bound"],
  "authority": {
    "class": "non_consumable",
    "allocation_mode": "replicable"
  },
  "constraints": [
    {
      "type": "acf:session-proposal",
      "value": "session_proposal_01J...",
      "critical": true
    },
    {
      "type": "acf:stage",
      "value": "implement",
      "critical": true
    }
  ],
  "proposed_obligations": [
    {
      "obligation_id": "obl_delivery_receipt_owner",
      "type": "acf:delivery-receipt",
      "schema_version": "1",
      "obligated_party": "did:example:worker",
      "trigger": "artifact:write",
      "required_action": "send-receipt",
      "due": "on-completion",
      "evidence_expected": "acf:DeliveryReceipt",
      "enforcement": "post-verified",
      "failure_signal": "obligation_unfulfilled",
      "descendant_trigger": "applies",
      "delegation_behavior": "retained"
    }
  ],
  "delegation_request": {
    "request_delegation_right": false,
    "requested_max_depth": 0
  },
  "acceptance_requested": {
    "required": true,
    "acceptors": [
      {
        "role": "authorized_executor",
        "id": "did:example:worker"
      }
    ]
  },
  "validity": {
    "not_before": "2026-07-27T09:00:00Z",
    "not_after": "2026-07-27T11:00:00Z"
  },
  "capability_evidence": [
    "evidence_01J..."
  ],
  "nonce": "base64url-random-value",
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:coordinator#key-1",
    "proof_value": "..."
  }
}
```

## Appendix B. Illustrative Authority Grant

The following example is non-normative:

```json
{
  "type": "acf:AuthorityGrant",
  "version": "0.3",
  "grant_id": "grant_01J...",
  "grantor": "did:example:project-owner",
  "grantee": "did:example:worker",
  "represented_principal": "did:example:project-owner",
  "authorized_executor": "did:example:worker",
  "request_id": "authreq_01J...",
  "intent_id": "intent_01J...",
  "session_proposal_id": "session_proposal_01J...",
  "session_binding": {
    "activation": "requires_session_activation",
    "reuse": "prohibited",
    "finalization": "verified_proposal_to_session_mapping"
  },
  "permissions": [
    {
      "action": "artifact:read",
      "resource": "urn:acf:artifact:requirements-v3",
      "purpose": "task:implement",
      "audience": "did:example:vault"
    },
    {
      "action": "artifact:write",
      "resource": "urn:acf:collection:implementation-output",
      "purpose": "task:implement",
      "audience": "did:example:vault"
    }
  ],
  "purpose_assurance_required": ["context_bound"],
  "authority": {
    "class": "non_consumable",
    "allocation_mode": "replicable"
  },
  "constraints": [
    {
      "type": "acf:session-proposal",
      "value": "session_proposal_01J...",
      "critical": true
    },
    {
      "type": "acf:stage",
      "value": "implement",
      "critical": true
    },
    {
      "type": "acf:output-content-type",
      "value": "text/x-diff",
      "critical": true
    }
  ],
  "obligations": [
    {
      "obligation_id": "obl_delivery_receipt_owner",
      "type": "acf:delivery-receipt",
      "schema_version": "1",
      "obligated_party": "did:example:worker",
      "trigger": "artifact:write",
      "required_action": "send-receipt",
      "due": "on-completion",
      "evidence_expected": "acf:DeliveryReceipt",
      "enforcement": "post-verified",
      "failure_signal": "obligation_unfulfilled",
      "descendant_trigger": "applies",
      "delegation_behavior": "retained"
    }
  ],
  "delegation": {
    "permitted": false,
    "remaining_depth": 0
  },
  "acceptance": {
    "required": true,
    "acceptors": [
      {
        "role": "authorized_executor",
        "id": "did:example:worker"
      }
    ],
    "accept_by": "2026-07-27T09:10:00Z"
  },
  "validity": {
    "issued_at": "2026-07-27T09:00:05Z",
    "not_before": "2026-07-27T09:00:05Z",
    "not_after": "2026-07-27T11:00:00Z"
  },
  "confirmation": {
    "method": "proof-of-possession",
    "key": "did:example:worker#session-key-7"
  },
  "status_mechanism": {
    "mode": "remote_reference",
    "uri": "https://authority.example/grants/grant_01J.../status"
  },
  "critical_extensions": [],
  "extensions": {},
  "canonicalization": "example-jcs-profile-v1",
  "digest_algorithm": "sha-256",
  "constraint_set_digest": "sha256:...",
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:project-owner#authority-key",
    "grant_digest": "sha256:...",
    "created": "2026-07-27T09:00:05Z",
    "proof_value": "..."
  }
}
```

## Appendix C. Illustrative Derived Grant

The following examples are non-normative. The first object is an abbreviated
parent Grant excerpt showing the Delegate Policy semantics used by this
derivation. Its JSON member names are illustrative; Section 26.2 requires the
baseline profile to publish the normative JSON structure and selector
algorithm.

The parent permits `did:example:lead-worker` to delegate the current Grant only
to `did:example:review-worker`, requires the Delegate to be its own Executor,
and requires Acceptance. Its redelegation ceiling would allow a child to pass
a still-narrower review Grant only to `did:example:quality-worker`:

```json
{
  "type": "acf:AuthorityGrantExcerpt",
  "version": "0.3",
  "grant_id": "grant_parent_01J...",
  "grantee": "did:example:lead-worker",
  "represented_principal": "did:example:project-owner",
  "authorized_executor": "did:example:lead-worker",
  "permissions": [
    {
      "action": "artifact:read",
      "resource": "urn:acf:collection:implementation-output",
      "purpose": "task:review",
      "audience": "did:example:vault"
    }
  ],
  "delegation": {
    "permitted": true,
    "remaining_depth": 2,
    "delegate_policy": {
      "current_transition_eligibility": {
        "delegate_selectors": [
          {
            "type": "exact_identifier",
            "value": "did:example:review-worker"
          }
        ],
        "executor_rule": "delegate_must_be_executor",
        "acceptance_required": true
      },
      "redelegation_ceiling": {
        "delegate_selectors": [
          {
            "type": "exact_identifier",
            "value": "did:example:quality-worker"
          }
        ],
        "executor_rule": "delegate_must_be_executor",
        "acceptance_required": true,
        "purposes": ["task:review"],
        "audiences": ["did:example:vault"],
        "session_proposal_ids": ["session_proposal_01J..."],
        "maximum_remaining_depth": 1
      }
    }
  }
}
```

The child changes the Grantee and Executor through that authorized current
transition while narrowing the resource to one artifact and shortening
validity. It prohibits further delegation, so its empty downstream Delegate
Policy is narrower than the parent's non-empty redelegation ceiling:

```json
{
  "type": "acf:AuthorityGrant",
  "version": "0.3",
  "grant_id": "grant_child_01J...",
  "parent_grant": {
    "grant_id": "grant_parent_01J...",
    "digest": "sha256:..."
  },
  "grantor": "did:example:lead-worker",
  "grantee": "did:example:review-worker",
  "represented_principal": "did:example:project-owner",
  "authorized_executor": "did:example:review-worker",
  "request_id": "authreq_review_01J...",
  "intent_id": "intent_01J...",
  "session_proposal_id": "session_proposal_01J...",
  "session_binding": {
    "activation": "requires_session_activation",
    "reuse": "prohibited",
    "finalization": "verified_proposal_to_session_mapping"
  },
  "permissions": [
    {
      "action": "artifact:read",
      "resource": "urn:acf:artifact:implementation-output-42",
      "purpose": "task:review",
      "audience": "did:example:vault"
    }
  ],
  "purpose_assurance_required": ["context_bound"],
  "authority": {
    "class": "non_consumable",
    "allocation_mode": "replicable"
  },
  "constraints": [
    {
      "type": "acf:session-proposal",
      "value": "session_proposal_01J...",
      "critical": true
    },
    {
      "type": "acf:stage",
      "value": "review",
      "critical": true
    }
  ],
  "delegation": {
    "permitted": false,
    "remaining_depth": 0
  },
  "acceptance": {
    "required": true,
    "acceptors": [
      {
        "role": "authorized_executor",
        "id": "did:example:review-worker"
      }
    ]
  },
  "validity": {
    "issued_at": "2026-07-27T09:30:00Z",
    "not_before": "2026-07-27T09:30:00Z",
    "not_after": "2026-07-27T10:00:00Z"
  },
  "status_mechanism": {
    "mode": "remote_reference",
    "uri": "https://authority.example/grants/grant_child_01J.../status"
  },
  "critical_extensions": [],
  "extensions": {},
  "canonicalization": "example-jcs-profile-v1",
  "digest_algorithm": "sha-256",
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:lead-worker#delegation-key",
    "grant_digest": "sha256:...",
    "created": "2026-07-27T09:30:00Z",
    "proof_value": "..."
  }
}
```

## Appendix D. Illustrative Verification Result

The following example is non-normative:

```json
{
  "type": "acf:AuthorityVerificationResult",
  "version": "0.3",
  "result_id": "authverify_01J...",
  "verifier": "did:example:vault",
  "grant_id": "grant_child_01J...",
  "presentation_id": "presentation_01J...",
  "status": "valid",
  "action_context": {
    "grantee": "did:example:review-worker",
    "represented_principal": "did:example:project-owner",
    "authorized_executor": "did:example:review-worker",
    "action": "artifact:read",
    "resource": "urn:acf:artifact:implementation-output-42",
    "purpose": "task:review",
    "purpose_assurance": ["context_bound"],
    "audience": "did:example:vault",
    "session_proposal_id": "session_proposal_01J..."
  },
  "checks": [
    {"name": "grant_body_digest", "status": "valid"},
    {"name": "grant_proof", "status": "valid"},
    {"name": "critical_extensions", "status": "valid"},
    {"name": "grant_acceptance", "status": "valid"},
    {"name": "principal_binding", "status": "valid"},
    {"name": "executor_binding", "status": "valid"},
    {"name": "possession_proof", "status": "valid"},
    {"name": "audience_binding", "status": "valid"},
    {"name": "scope", "status": "valid"},
    {"name": "validity", "status": "valid"},
    {"name": "revocation", "status": "valid"},
    {"name": "delegation_chain", "status": "valid"},
    {"name": "authority_scope_narrowing", "status": "valid"},
    {"name": "subject_transition", "status": "valid"},
    {"name": "delegate_policy_narrowing", "status": "valid"},
    {"name": "purpose_assurance_preservation", "status": "valid"},
    {"name": "condition_implication", "status": "valid"},
    {"name": "critical_extension_inheritance", "status": "valid"},
    {"name": "status_mechanism_compatibility", "status": "valid"}
  ],
  "constraint_set_digest": "sha256:...",
  "authority_chain_digest": "sha256:...",
  "status_snapshot": {
    "digest": "sha256:...",
    "observed_at": "2026-07-27T09:42:00Z"
  },
  "verified_at": "2026-07-27T09:42:00Z"
}
```

This result states that protocol verification succeeded. The Resource
Controller still applies local Policy before permitting the action.

## Appendix E. Illustrative Grant Acceptance

The following example is non-normative:

```json
{
  "type": "acf:GrantAcceptance",
  "version": "0.3",
  "acceptance_id": "acceptance_01J...",
  "grant_id": "grant_01J...",
  "grant_digest": "sha256:...",
  "acceptor": "did:example:worker",
  "acceptor_role": "authorized_executor",
  "status": "accepted",
  "obligations_acknowledged": [
    "obl_delivery_receipt_owner"
  ],
  "possession_key_confirmed": "did:example:worker#session-key-7",
  "nonce": "base64url-random-value",
  "issued_at": "2026-07-27T09:03:00Z",
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:worker#session-key-7",
    "proof_value": "..."
  }
}
```

This acceptance makes an identified technical assertion about one immutable
Grant Body. It does not activate the Session or create legal liability.

## Appendix F. Illustrative Capability Negotiation

The following examples are non-normative.

### F.1 Capability Requirement

```json
{
  "type": "acf:CapabilityRequirement",
  "version": "0.3",
  "requirement_id": "capreq_01J...",
  "intent_id": "intent_01J...",
  "requester": "did:example:travel-coordinator",
  "capability_subject": "did:example:hotel-analyst",
  "ability": "travel:hotel-price-analysis",
  "context": {
    "market": "CN",
    "currency": "CNY",
    "maximum_result_age": "PT15M"
  },
  "evidence_requirements": [
    {
      "type": "acf:reproducible-capability-test",
      "required": true,
      "freshness": "P30D"
    }
  ],
  "challenge": "base64url-random-value",
  "response_deadline": "2026-07-28T10:00:00Z",
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:travel-coordinator#key-1",
    "proof_value": "..."
  }
}
```

### F.2 Capability Statement

```json
{
  "type": "acf:CapabilityStatement",
  "version": "0.3",
  "statement_id": "capstmt_01J...",
  "claimant": "did:example:hotel-analyst",
  "capability_subject": "did:example:hotel-analyst",
  "ability": "travel:hotel-price-analysis",
  "inputs": ["travel:hotel-search-criteria-v1"],
  "outputs": ["travel:hotel-price-comparison-v1"],
  "operating_constraints": {
    "markets": ["CN"],
    "currencies": ["CNY"],
    "requires_network_access": true
  },
  "evidence": [
    "evidence_capability_test_01J..."
  ],
  "intent_id": "intent_01J...",
  "audience": "did:example:travel-coordinator",
  "challenge": "base64url-random-value",
  "validity": {
    "issued_at": "2026-07-28T09:00:00Z",
    "not_after": "2026-08-27T09:00:00Z"
  },
  "proof": {
    "type": "ExampleProof2026",
    "verification_method": "did:example:hotel-analyst#key-1",
    "proof_value": "..."
  }
}
```

### F.3 Capability Negotiation Result

```json
{
  "type": "acf:CapabilityNegotiationResult",
  "version": "0.3",
  "result_id": "capresult_01J...",
  "receiver": "did:example:travel-coordinator",
  "requirement_id": "capreq_01J...",
  "statement_id": "capstmt_01J...",
  "capability_subject": "did:example:hotel-analyst",
  "status": "capability_accepted",
  "context": {
    "intent_id": "intent_01J...",
    "market": "CN",
    "currency": "CNY"
  },
  "evidence_considered": [
    "evidence_capability_test_01J..."
  ],
  "evaluated_at": "2026-07-28T09:05:00Z"
}
```

This result is scoped to the receiver, Requirement, Intent, subject, and
context. It is not a global competence score and conveys no Permission.

## Appendix G. Minimum Negative Test Vectors

Every baseline Authority Grant profile SHOULD publish machine-readable
positive and negative vectors. A Core RFC scenario may map to different
failure taxonomies across profiles, but each concrete profile's
machine-readable vector MUST specify exactly one expected result. At minimum,
its negative set SHOULD cover:

| Vector | Invalid scenario | Expected result |
|---|---|---|
| `unauthorized_executor_transition` | Child scope narrows, but the parent delegation rule does not authorize the child Grantee or Executor | `invalid_subject_transition` |
| `principal_changed_in_child` | Child changes Represented Principal without an independent authority source | `principal_transition_not_permitted` |
| `scope_expansion` | Child adds an action or resource outside the parent Authority Scope | `scope_expansion` |
| `purpose_assurance_downgrade` | Parent requires `enforced`; child requires only `declared` | `purpose_assurance_weakened` |
| `parent_revoked` | Child is otherwise valid, but an ancestor Grant is revoked | `invalid_delegation_chain` |
| `obligation_semantics_stripped` | Child loses a retained descendant-trigger reference or required propagated Obligation | `obligation_removed` |
| `unknown_critical_extension` | Grant declares a critical extension unsupported by the Verifier | `unsupported_critical_extension` |
| `critical_extension_stripped` | Child omits an applicable authorization-affecting critical extension from the parent | `critical_extension_stripped` |
| `partition_oversubscription` | Two partitioned children reserve more than the parent budget | `budget_reservation_failed` |
| `accounting_domain_discontinuity` | Child changes from `ledger-A` to independent `ledger-B` without a parent reservation or transfer proof | `accounting_domain_discontinuity` |
| `delegate_policy_missing` | Parent sets `delegation.permitted=true` and positive depth but supplies no Delegate Policy | `delegation_not_permitted` |
| `delegate_policy_expansion` | Child Delegate Policy broadens an exact parent redelegation selector to an organization-wide selector | `delegate_policy_expansion` |
| `condition_replacement_unproven` | Child replaces a parent human-approval Condition without a deterministic implication proof | `condition_weakened` |
| `offline_status_downgrade` | Child selects `short_lived_no_revocation` although the parent requires online descendant revocation status | `status_mechanism_incompatible` |
| `composition_assurance_stripped` | Composition omits a contributing Grant's required Purpose Assurance or critical extension | `composition_not_permitted` |
| `composition_status_incompatible` | Composition cannot satisfy all contributing status freshness or failure requirements | `status_mechanism_incompatible` |
| `composition_implied_delegation` | Composition of action Grants is treated as carrying delegation or Grant Issuance Authority without an explicit rule | `composition_not_permitted` |
| `composed_delegate_policy_union` | Composed Delegate Policy uses the union rather than the intersection of applicable redelegation ceilings | `delegate_policy_expansion` |
| `conditional_acceptance_activation` | Implementation attempts to activate the original Grant after `conditionally_accepted` | `acceptance_countered` |
| `wrong_represented_principal` | Presentation names a different Principal than the Grant | `wrong_principal` |
| `implicit_grant_splicing` | Executor from one Grant and action or resource from another are combined without a composition rule | `composition_not_permitted` |
| `stale_status_snapshot` | Status evidence exceeds the profile freshness limit | `status_too_stale` |
| `canonicalization_mismatch` | Proof uses bytes from a different canonicalization profile while the declared profile is supported | `digest_mismatch` |

For the first vector, changing Agent A to Agent B is not inherently invalid.
It is invalid only when the Subject Transition is unauthorized. A companion
positive vector SHOULD demonstrate the same scope with an explicitly
authorized A-to-B delegation transition.
