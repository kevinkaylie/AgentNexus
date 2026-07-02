"""
Example: Coding Coordination Demo (SDK facade)

Runs the full Coding Coordination V1 loop:
- Owner / secretary / worker bootstrap
- Enclave + vault content
- Coding intake
- 6 submitted artifacts
- 7 approved/passed receipts
- Receipt-gated stage advancement
- Final closure record

Run with:
    python agentnexus-sdk/examples/coding_coordination_demo.py
"""
import asyncio
import uuid

import agentnexus


async def main():
    suffix = uuid.uuid4().hex[:8]
    nexus = await agentnexus.connect(f"Coordination Demo Client {suffix}", caps=["Admin"])

    owner = await nexus.owner.register(f"Demo Team Owner {suffix}")
    owner_did = owner.did
    print(f"Owner: {owner_did}")

    async def register_agent(role_name, caps):
        result = await nexus._request(
            "POST",
            "/agents/register",
            json={"name": f"Demo {role_name} {suffix}", "capabilities": caps},
        )
        return result["did"]

    secretary_did = await register_agent("Secretary", ["orchestrate", "intake"])
    designer_did = await register_agent("Designer", ["design"])
    developer_did = await register_agent("Developer", ["coding"])
    reviewer_did = await register_agent("Reviewer", ["review"])
    tester_did = await register_agent("Tester", ["testing"])

    print(f"Secretary: {secretary_did}")
    print(f"Designer:  {designer_did}")
    print(f"Developer: {developer_did}")
    print(f"Reviewer:  {reviewer_did}")
    print(f"Tester:    {tester_did}")

    for did in [secretary_did, designer_did, developer_did, reviewer_did, tester_did]:
        await nexus.owner.bind(owner_did, did)

    enclave = await nexus.create_enclave(
        name="Demo Coordination Enclave",
        owner_did=owner_did,
        actor_did=owner_did,
        members={
            "designer": {"did": designer_did, "role": "designer", "permissions": "rw"},
            "developer": {"did": developer_did, "role": "developer", "permissions": "rw"},
            "reviewer": {"did": reviewer_did, "role": "reviewer", "permissions": "rw"},
            "tester": {"did": tester_did, "role": "tester", "permissions": "rw"},
        },
    )
    enclave_id = enclave.enclave_id

    vault_items = {
        "clarify.md": "# Requirements\n\nLogin module with email/password.",
        "design.md": "# Design\n\nLogin API, password hasher, session manager.",
        "implement.py": "def login(email, password):\n    return create_session(email, password)\n",
        "code_review.md": "# Code Review\n\nApproved with no blocking findings.",
        "test_report.md": "# Test Report\n\nUnit and integration tests passed.",
    }
    for key, content in vault_items.items():
        await nexus.vault_put(enclave_id, key, content, author_did=owner_did)

    print("\n--- Coding Intake ---")
    session = await nexus.coordination.coding_intake(
        owner_did=owner_did,
        actor_did=secretary_did,
        objective="Implement demo login module",
        enclave_id=enclave_id,
        complexity="medium",
    )
    session_id = session["coordination_session_id"]
    run_id = session["playbook_run_id"]
    print(f"Session: {session_id}")
    print(f"Run:     {run_id}")

    workflow = [
        ("clarify", "RequirementSpec", designer_did, "ClarifyReceipt", reviewer_did, "clarify.md"),
        ("design", "DesignArtifact", designer_did, "DesignReceipt", reviewer_did, "design.md"),
        ("design_review", "DesignReviewArtifact", reviewer_did, "DesignReviewReceipt", reviewer_did, "design.md"),
        ("implement", "ImplementationArtifact", developer_did, "ImplementationReceipt", reviewer_did, "implement.py"),
        ("code_review", "CodeReviewArtifact", reviewer_did, "CodeReviewReceipt", reviewer_did, "code_review.md"),
        ("test", "TestResultArtifact", tester_did, "TestReceipt", reviewer_did, "test_report.md"),
    ]

    print("\n--- Artifacts, Receipts, Advance ---")
    for stage, artifact_type, producer_did, receipt_type, issuer_did, vault_key in workflow:
        artifact = await nexus.coordination.submit_artifact(
            coordination_session_id=session_id,
            run_id=run_id,
            stage=stage,
            artifact_type=artifact_type,
            producer_did=producer_did,
            content_ref=f"vault://{enclave_id}/{vault_key}",
        )
        print(f"Artifact: {artifact['artifact_id']} ({stage})")

        receipt = await nexus.coordination.submit_receipt(
            coordination_session_id=session_id,
            run_id=run_id,
            stage=stage,
            receipt_type=receipt_type,
            issuer_did=issuer_did,
            decision="approved",
            subject_artifact_id=artifact["artifact_id"],
        )
        print(f"Receipt:  {receipt['receipt_id']} ({stage})")

        state = await nexus.coordination.advance(
            coordination_session_id=session_id,
            run_id=run_id,
            actor_did=secretary_did,
        )
        label = "completed" if state.get("status") == "completed" else state.get("current_stage", "")
        print(f"Advance:  -> {label}")
        if state.get("status") == "completed":
            break

    print("\n--- Results ---")
    session_detail = await nexus.coordination.get_session(
        coordination_session_id=session_id,
        actor_did=secretary_did,
    )
    timeline = await nexus.coordination.timeline(
        coordination_session_id=session_id,
        actor_did=secretary_did,
    )
    closures = await nexus.coordination.closures(
        coordination_session_id=session_id,
        actor_did=secretary_did,
    )

    print(f"Status:   {session_detail.get('status')}")
    print(f"Timeline: {len(timeline.get('timeline', []))} events")
    for closure in closures.get("closures", []):
        print(f"Closure:  {closure.get('closure_id')} [{closure.get('sla_status', '')}]")

    print(f"\nDashboard: http://127.0.0.1:8765/ui/coordination/{session_id}")

    await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
