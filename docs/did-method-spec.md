# did:agentnexus Method Specification

**Version:** 1.0  
**Status:** Draft  
**DID Method Name:** `agentnexus`  
**Namespace:** W3C DID Core

---

## 1. Overview

`did:agentnexus` is a DID method for autonomous software agents in the AgentNexus network. It provides a self-certifying identifier derived from an Ed25519 public key, enabling agents to prove control over their identity without requiring a central registry.

The method is designed to:
- Provide strong identity guarantees through cryptographic key ownership
- Enable interoperability with the Agent Identity Working Group (WG DID Resolution v1.0)
- Support key agreement for encrypted communication (X25519)
- Maintain backward compatibility with the legacy `did:agent` format

## 2. DID Format

### 2.1 ABNF Definition

```
did-agentnexus = "did:agentnexus:" multikey
multikey = "z" base58btc(multicodec-prefix || ed25519-pubkey)
multicodec-prefix = 2-byte big-endian unsigned integer
ed25519-pubkey = 32 bytes
base58btc = base58 encoding using Bitcoin alphabet
```

### 2.2 Format Details

| Component | Value | Length |
|-----------|-------|--------|
| multicodec prefix (Ed25519) | `0xED01` | 2 bytes |
| Ed25519 public key | raw 32 bytes | 32 bytes |
| Total payload | multicodec + key | 34 bytes |
| Multikey (z-prefix + base58btc) | varies | ~46 characters |

### 2.3 Examples

```
did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK
did:agentnexus:z7jt6mN3mR4pY1vT2kX8sH3gQ9hL5dF4aB2cE6rM8jV3pN7xY1zW9qU
```

## 3. DID Document Format

### 3.1 Standard DID Document

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/suites/ed25519-2020/v1"
  ],
  "id": "did:agentnexus:z6Mk...",
  "verificationMethod": [{
    "id": "did:agentnexus:z6Mk...#agent-1",
    "type": "Ed25519VerificationKey2018",
    "controller": "did:agentnexus:z6Mk...",
    "publicKeyMultibase": "z6Mk..."
  }],
  "authentication": ["did:agentnexus:z6Mk...#agent-1"],
  "assertionMethod": ["did:agentnexus:z6Mk...#agent-1"],
  "keyAgreement": [{
    "id": "did:agentnexus:z6Mk...#key-agreement-1",
    "type": "X25519KeyAgreementKey2019",
    "controller": "did:agentnexus:z6Mk...",
    "publicKeyMultibase": "zEC..."
  }]
}
```

### 3.2 Required Fields

| Field | Requirement | Description |
|-------|-------------|-------------|
| `@context` | REQUIRED | Must include `https://www.w3.org/ns/did/v1` |
| `id` | REQUIRED | The DID itself |
| `verificationMethod` | REQUIRED | At least one Ed25519 verification key |
| `authentication` | REQUIRED | Verification method IDs for authentication |
| `assertionMethod` | REQUIRED | Verification method IDs for assertion |
| `keyAgreement` | RECOMMENDED | X25519 key for ECDH key agreement |

## 4. Operations

### 4.1 Create (DID Generation)

**Algorithm:**
1. Generate a new Ed25519 signing key pair
2. Encode the public key as a multikey: `z` + base58btc(0xED01 || pubkey)
3. Construct the DID: `did:agentnexus:<multikey>`

**Implementation:**
```python
from agent_net.common.did import DIDGenerator, create_agentnexus_did

# Using DIDGenerator
agent_did, multikey = DIDGenerator.create_agentnexus("my-agent")

# Or using the convenience function
did, private_key_hex, public_key_hex = create_agentnexus_did("my-agent")
```

### 4.2 Read (Resolution)

**Algorithm:**
1. Parse the DID to extract the multikey
2. Decode the multikey to obtain the Ed25519 public key
3. Construct the DID Document
4. Derive the X25519 key for keyAgreement (if included)

**Resolution Methods:**

| Method | Resolution Type | Notes |
|--------|----------------|-------|
| `did:agentnexus` | Local | Keys derived from DID, no network required |
| `did:agent` | Local DB | Legacy format, resolves from local agents table |
| `did:key` | Local | Keys encoded in DID, no network required |
| `did:web` | Remote | Fetch from `https://<domain>/.well-known/did.json` |

### 4.3 Update

The `did:agentnexus` method supports key rotation through DID Document updates:

1. Generate a new Ed25519 key pair
2. Update the DID Document with the new verification method
3. The new DID becomes: `did:agentnexus:z<new-multikey>`

Note: Key rotation creates a new DID with a different identifier.

### 4.4 Deactivate

To deactivate a DID:
1. Remove all verification methods from the DID Document
2. Update the DID Document with `status: "deactivated"`
3. Any party attempting to resolve will receive an error

## 5. Cryptographic Operations

### 5.1 Ed25519 → X25519 Derivation

For ECDH key agreement, the X25519 public key is derived from the Ed25519 public key:

```
x25519_pubkey = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(ed25519_pubkey)
```

**Reference:** [RFC 7748](https://www.rfc-editor.org/rfc/rfc7748) Section 4.1

### 5.2 Multicodec Encoding

| Key Type | Multicodec Prefix | Encoded Length |
|----------|-------------------|----------------|
| Ed25519 | `0xED01` | 34 bytes (2 prefix + 32 key) |
| X25519 | `0xEC02` | 34 bytes (2 prefix + 32 key) |

### 5.3 Sender ID Derivation

The sender ID is derived for QSP-1 envelope verification:

```
sender_id = SHA-256(ed25519_pubkey)[0:16]
```

Encoded as lowercase hexadecimal (32 characters).

## 6. Privacy and Security Considerations

### 6.1 Public Key Exposure

The DID and DID Document reveal the public key. This is by design for self-certifying identifiers, but implies:
- Any party can verify signatures made by the agent
- The agent's activity can be linked via the public key
- Revocation/revocation requires key rotation

### 6.2 Key Storage

Private keys must be stored securely:
- Use encrypted storage
- Never transmit private keys in plaintext
- Implement secure deletion when keys are no longer needed

### 6.3 Network Security

For `did:web` resolution:
- Always use HTTPS (never HTTP)
- Validate TLS certificates
- Set descriptive User-Agent headers (some CDNs block default agents)
- Implement timeout (recommended: 10 seconds)
- Follow redirects up to 3 hops

### 6.4 Key Rotation

When rotating keys:
1. The old DID remains valid for a grace period
2. Update all relying parties with the new DID
3. After verification, invalidate the old key
4. Consider maintaining a key history for verification of past signatures

## 7. Interoperability

### 7.1 WG DID Resolution v1.0

The `did:agentnexus` method is designed to integrate with the Agent Identity Working Group's DID Resolution specification:

| WG Requirement | Implementation |
|----------------|----------------|
| `resolve_did()` interface | `DIDResolver.resolve_did()` |
| `did:key` support | Via `DIDResolver._resolve_key()` |
| `did:web` support | Via `DIDResolver._resolve_web()` |
| `sender_id` derivation | `derive_sender_id()` |
| Ed25519 key extraction | `decode_multikey_ed25519()` |

### 7.2 Cross-System Resolution

| Source | Target | Status |
|--------|--------|--------|
| AgentNexus | `did:key:z...` | ✅ Supported |
| AgentNexus | `did:web:example.com` | ✅ Supported |
| AgentNexus | `did:agent:...` | ✅ Supported (legacy) |

### 7.3 Third-Party Verification Services

#### AgentID (getagentid.dev)

[AgentID](https://getagentid.dev) provides external DID verification for `did:agentnexus` identifiers. Their `/api/v1/agents/verify` endpoint can resolve and verify any `did:agentnexus` DID without requiring registration:

```bash
curl -X POST https://www.getagentid.dev/api/v1/agents/verify \
  -H "Content-Type: application/json" \
  -d '{"did": "did:agentnexus:z6Mk..."}'
```

**Response:**
```json
{
  "verified": true,
  "identity_gate": "passed",
  "did": "did:agentnexus:z6Mk...",
  "resolution_source": "external",
  "resolution_method": "did:agentnexus",
  "public_key": {
    "type": "Ed25519VerificationKey2020",
    "publicKeyHex": "..."
  }
}
```

This interoperability enables:
- Third-party verification without AgentNexus infrastructure
- Cross-platform agent identity validation
- Integration with AgentID's trust ecosystem (optional registration)

**Note:** Trust levels, behavioral signals, and receipts require AgentID registration, but basic DID resolution works for all `did:agentnexus` identifiers.

## 8. Test Vectors

### 8.1 Ed25519 Key Generation

```python
# Private key (32 bytes hex):
"9b53a0f27a3a0c1d1f9c8f8c1d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0"

# Public key (32 bytes hex):
"2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6"

# Multikey:
"z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
```

### 8.2 Sender ID Derivation

```
public_key_hex: "2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6"
sender_id_hex: "c446d9bcf84d5e3ee966bac5c1f634c1"
```

### 8.3 X25519 Derivation

```
ed25519_pubkey_hex: "2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6"
x25519_pubkey_hex: "13d6992e65f6e6abd16fa77d438bce3d5b3ecf00f9e6f0f0e0f0f0f0f0f0f0f0f0"
```

## 9. Reference Implementation

```python
from agent_net.common.did import DIDResolver, DIDGenerator, create_agentnexus_did

# Generate a new DID
did, priv_hex, pub_hex = create_agentnexus_did("my-agent")
print(f"New DID: {did}")

# Resolve a DID
resolver = DIDResolver()
result = await resolver.resolve(did)
print(f"Public key: {result.public_key.hex()}")
print(f"DID Document: {result.did_document}")

# WG-compatible resolution
wg_result = await resolver.resolve_did(did)
print(f"WG format: {wg_result}")

# Derive sender ID
sender_id = resolver.derive_sender_id(result.public_key)
print(f"Sender ID: {sender_id}")
```

## 10. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-26 | Initial specification |

---

**Authors:** AgentNexus Development Team  
**License:** MIT  
**Repository:** https://github.com/agentnexus/AgentNexus
