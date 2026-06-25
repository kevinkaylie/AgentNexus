from .common import _read_token

# ── node coordination 子命令 ──────────────────────────────

# ── node coordination 子命令 ──────────────────────────────

def _check_sdk_available():
    """Return True if agentnexus SDK coordination facade is importable."""
    try:
        import agentnexus
        from agentnexus.coordination import CoordinationClient
        return True
    except ImportError:
        return False


async def _get_coordination_client():
    """Create a lightweight SDK client connected to local daemon."""
    import aiohttp
    from agentnexus.client import AgentNexusClient, AgentInfo

    token = _read_token()
    client = AgentNexusClient(
        daemon_url="http://localhost:8765",
        token=token,
        agent_info=AgentInfo(did="", name="CLI-Coordination", capabilities=["Admin"], owner_did=""),
    )
    client._session = aiohttp.ClientSession()
    return client


async def _close_coordination_client(client):
    """Close the SDK client session cleanly."""
    if client and client._session:
        await client._session.close()
        client._session = None


async def _run_coordination_demo():
    """Run the full coding coordination demo via SDK facades. Returns result dict."""
    import asyncio, time, json as _json
    from agentnexus.client import AgentNexusClient, AgentInfo
    from agentnexus.owner import OwnerClient
    from agentnexus.enclave import EnclaveManager
    import aiohttp

    token = _read_token()
    base = "http://localhost:8765"
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Create a proper connected client for the demo
    client = AgentNexusClient(
        daemon_url=base,
        token=token,
        agent_info=AgentInfo(did="", name="CLI-Coordination-Demo", capabilities=["Admin"], owner_did=""),
    )
    client._session = aiohttp.ClientSession()
    owner = OwnerClient(client)
    result = {"steps": [], "session_id": None, "closure_id": None}

    try:
        # Step 0: check daemon health
        try:
            async with client._session.get(f"{base}/health") as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Daemon not healthy: {resp.status}")
        except aiohttp.ClientConnectorError:
            print("[Error] Cannot connect to Node Daemon. Run: python main.py node start")
            return result

        # Step 1: create/find Demo Owner via proper owner API
        print("Setting up demo identities...")
        demo_dids = {}

        # Create owner via /owner/register (writes owner table, required for coding_intake)
        owner_did = None

        # Try to find existing Demo Owner by checking all local agents
        async with client._session.get(f"{base}/agents/local") as r:
            if r.status == 200:
                data = await r.json()
                for a in data.get("agents", []):
                    if a.get("profile", {}).get("name") == "Demo Owner":
                        owner_did = a["did"]
                        break

        if not owner_did:
            try:
                owner_info = await owner.register("Demo Owner")
                owner_did = owner_info.did
            except Exception:
                # Fallback: register-agent path for backwards compat
                async with client._session.post(
                    f"{base}/agents/register",
                    json={"name": "Demo Owner", "capabilities": ["Admin"], "worker_type": "resident"},
                    headers=auth_headers,
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        owner_did = data["did"]
                    else:
                        raise RuntimeError(f"Failed to create Demo Owner: {await r.text()}")

        demo_dids["owner"] = owner_did
        print(f"  Owner: {owner_did}")

        # Create non-owner agents (Secretary, Designer, etc.)
        async def _find_or_create_agent(name, caps, worker_type="resident"):
            async with client._session.get(f"{base}/agents/local") as r:
                if r.status == 200:
                    data = await r.json()
                    for a in data.get("agents", []):
                        if a.get("profile", {}).get("name") == name:
                            return a["did"]
            async with client._session.post(
                f"{base}/agents/register",
                json={"name": name, "capabilities": caps, "worker_type": worker_type},
                headers=auth_headers,
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["did"]
                raise RuntimeError(f"Failed to create agent {name}: {await r.text()}")

        secretary_did = await _find_or_create_agent("Demo Secretary", ["orchestrate", "intake", "dispatch"], "resident")
        demo_dids["secretary"] = secretary_did
        print(f"  Secretary: {secretary_did}")

        designer_did = await _find_or_create_agent("Demo Designer", ["design"], "resident")
        demo_dids["designer"] = designer_did

        developer_did = await _find_or_create_agent("Demo Developer", ["coding"], "resident")
        demo_dids["developer"] = developer_did

        reviewer_did = await _find_or_create_agent("Demo Reviewer", ["review"], "resident")
        demo_dids["reviewer"] = reviewer_did

        tester_did = await _find_or_create_agent("Demo Tester", ["testing"], "resident")
        demo_dids["tester"] = tester_did

        # Bind agents to owner via SDK facade
        for role, did in demo_dids.items():
            if role != "owner":
                try:
                    await owner.bind(owner_did, did)
                except Exception:
                    pass

        # Step 2: create demo enclave + vault content via SDK facades
        print("Creating demo enclave and vault content...")
        enclave_id = "demo_coordination_enclave"

        enclaves = EnclaveManager(client)
        try:
            enclave = await enclaves.create(
                name="Demo Coordination Enclave",
                owner_did=owner_did,
                members={
                    "designer": {"did": designer_did, "role": "designer", "permissions": "rw"},
                    "developer": {"did": developer_did, "role": "developer", "permissions": "rw"},
                    "reviewer": {"did": reviewer_did, "role": "reviewer", "permissions": "rw"},
                    "tester": {"did": tester_did, "role": "tester", "permissions": "rw"},
                },
            )
            enclave_id = enclave.enclave_id
        except Exception:
            # Fallback: raw HTTP for enclave creation
            try:
                async with client._session.post(
                    f"{base}/enclaves",
                    json={
                        "name": "Demo Coordination Enclave",
                        "owner_did": owner_did,
                        "actor_did": owner_did,
                        "members": {
                            "designer": {"did": designer_did, "role": "designer", "permissions": "rw"},
                            "developer": {"did": developer_did, "role": "developer", "permissions": "rw"},
                            "reviewer": {"did": reviewer_did, "role": "reviewer", "permissions": "rw"},
                            "tester": {"did": tester_did, "role": "tester", "permissions": "rw"},
                        },
                    },
                    headers=auth_headers,
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        enclave_id = data.get("enclave_id", enclave_id)
            except Exception:
                pass

        # Write vault content for each stage
        vault_contents = {
            "clarify.md": "# Requirement Spec\n\nLogin module with email/password.\n\n## Acceptance Criteria\n- Email validation\n- Password hashing\n- Session management",
            "design.md": "# Design Spec\n\n## Architecture\n- Login API endpoint\n- Password hasher service\n- Session token manager",
            "implement.py": "# Implementation\n\ndef login(email, password):\n    user = find_user(email)\n    if user and verify_password(password, user.hash):\n        return create_session(user.id)\n    raise AuthError()",
            "code_review.md": "# Code Review\n\nAll acceptance criteria met. Code follows style guide. Tests pass.",
            "test_report.md": "# Test Report\n\n## Results\n- Unit tests: 12/12 passed\n- Integration tests: 4/4 passed\n- Coverage: 87%",
        }
        vault = None
        try:
            enclave_proxy = await enclaves.get(enclave_id, actor_did=owner_did)
            vault = enclave_proxy.vault
        except Exception:
            pass

        for key, value in vault_contents.items():
            try:
                if vault:
                    await vault.put(key, value, author_did=owner_did)
                else:
                    async with client._session.post(
                        f"{base}/enclaves/{enclave_id}/vault/{key}",
                        json={"value": value, "author_did": owner_did},
                        headers=auth_headers,
                    ) as r:
                        pass
            except Exception:
                pass

        # Step 3: coding intake
        print("Running coding coordination workflow...")
        session = await client.coordination.coding_intake(
            owner_did=owner_did,
            actor_did=secretary_did,
            objective="Implement demo login module",
            enclave_id=enclave_id,
            complexity="medium",
        )
        session_id = session["coordination_session_id"]
        run_id = session["playbook_run_id"]
        result["session_id"] = session_id
        result["run_id"] = run_id
        print(f"  Session: {session_id}")
        print(f"  Run: {run_id}")

        # Full 7-stage workflow: clarify -> design -> design_review -> implement -> code_review -> test -> final
        workflow_definition = [
            # (stage, artifact_type, producer_did, receipt_type, issuer_did, vault_key)
            ("clarify", "RequirementSpec", designer_did, "ClarifyReceipt", reviewer_did, "clarify.md"),
            ("design", "DesignArtifact", designer_did, "DesignReceipt", reviewer_did, "design.md"),
            ("design_review", "DesignReviewArtifact", reviewer_did, "DesignReviewReceipt", reviewer_did, None),
            ("implement", "ImplementationArtifact", developer_did, "ImplementationReceipt", reviewer_did, "implement.py"),
            ("code_review", "CodeReviewArtifact", reviewer_did, "CodeReviewReceipt", reviewer_did, "code_review.md"),
            ("test", "TestResultArtifact", tester_did, "TestReceipt", reviewer_did, "test_report.md"),
            ("final", None, None, None, None, None),  # final auto-closes on advance
        ]

        for stage, atype, producer, rtype, issuer, vkey in workflow_definition:
            # Submit artifact (skip for final — it auto-generates)
            if atype and producer:
                try:
                    content_ref = f"vault://{enclave_id}/{vkey}" if vkey else f"vault://{enclave_id}/design.md"
                    art = await client.coordination.submit_artifact(
                        coordination_session_id=session_id,
                        run_id=run_id,
                        stage=stage,
                        artifact_type=atype,
                        producer_did=producer,
                        content_ref=content_ref,
                    )
                    print(f"  Artifact: {art['artifact_id']} ({stage})")
                except Exception as e:
                    print(f"  [Warn] Artifact {stage}: {e}")

            # Submit receipt (skip for final — advance auto-generates FinalResultReceipt)
            if rtype and issuer:
                try:
                    rcpt = await client.coordination.submit_receipt(
                        coordination_session_id=session_id,
                        run_id=run_id,
                        stage=stage,
                        receipt_type=rtype,
                        issuer_did=issuer,
                        decision="approved",
                    )
                    print(f"  Receipt: {rcpt['receipt_id']} ({stage})")
                except Exception as e:
                    print(f"  [Warn] Receipt {stage}: {e}")

            # Advance to next stage
            try:
                state = await client.coordination.advance(
                    coordination_session_id=session_id,
                    run_id=run_id,
                    actor_did=secretary_did,
                )
                status = state.get("status", "")
                cs = state.get("current_stage", "?")
                closure = state.get("closure")
                if closure and closure.get("closure"):
                    result["closure_id"] = closure["closure"].get("closure_id")
                stage_label = "completed" if status == "completed" else cs
                print(f"  Advance: -> {stage_label}")
                if status == "completed":
                    break
            except Exception as e:
                print(f"  [Warn] advance {stage}: {e}")

        # Step 4: timeline and closure
        timeline_data = await client.coordination.timeline(
            coordination_session_id=session_id,
            actor_did=secretary_did,
        )
        closures_data = await client.coordination.closures(
            coordination_session_id=session_id,
            actor_did=secretary_did,
        )
        try:
            session_detail = await client.coordination.get_session(
                coordination_session_id=session_id,
                actor_did=secretary_did,
            )
        except Exception:
            session_detail = {}

        result["timeline"] = timeline_data.get("timeline", [])
        closures = closures_data.get("closures", [])
        if closures and not result["closure_id"]:
            result["closure_id"] = closures[0].get("closure_id")

        # Print summary
        print(f"\nCoding Coordination demo completed\n")
        print(f"Session: {session_id}")
        final_status = session_detail.get("status") or ("completed" if result["closure_id"] else "unknown")
        print(f"Status : {final_status}")
        print(f"Events : {len(result['timeline'])} timeline entries")
        if result["closure_id"]:
            print(f"Closure: {result['closure_id']}")
        print(f"\nOpen:  http://127.0.0.1:8765/ui/coordination/{session_id}")

    finally:
        await _close_coordination_client(client)

    return result


async def node_coordination_cmd(args: list[str]):
    """node coordination — Coding Coordination V1 CLI (via SDK facade)."""
    import json as _json

    if not args:
        print("Usage: node coordination <subcommand> [...]")
        print("Primary:  demo | show <session_id> | timeline <session_id>")
        print("Low-level: coding-intake | get | list | fork | artifact | receipt | advance | decision | delegate | runtime-mock | accept | reject | closures")
        return

    if not _check_sdk_available():
        print("Error: AgentNexus SDK is not installed.")
        print("Please install: pip install -e agentnexus-sdk")
        return

    sub = args[0]

    # ── demo ────────────────────────────────────────────────
    if sub == "demo":
        await _run_coordination_demo()
        return

    # ── show ────────────────────────────────────────────────
    if sub == "show":
        if len(args) < 2:
            print("Usage: node coordination show <session_id> [--actor <did>]"); return
        session_id = args[1]
        actor_did = ""
        it = iter(args[2:])
        for tok in it:
            if tok == "--actor": actor_did = next(it, "")
        if not actor_did:
            print("Error: --actor <did> is required"); return

        nexus = await _get_coordination_client()
        try:
            sess = await nexus.coordination.get_session(session_id, actor_did=actor_did)
            timeline = await nexus.coordination.timeline(session_id, actor_did=actor_did)
            artifacts = await nexus.coordination.list_artifacts(session_id, actor_did=actor_did)
            receipts = await nexus.coordination.list_receipts(session_id, actor_did=actor_did)
            closures = await nexus.coordination.closures(session_id, actor_did=actor_did)

            print(f"Session: {sess.get('coordination_session_id')}")
            print(f"Objective: {sess.get('objective')}")
            print(f"Status: {sess.get('status')}")
            print(f"Playbook: {sess.get('playbook_id')}")
            print(f"Current stage: {sess.get('current_stage')}")
            print(f"Owner: {sess.get('owner_did')}")
            print(f"Controller: {sess.get('controller_did')}")
            print()
            print(f"Timeline ({len(timeline.get('timeline', []))} entries):")
            for evt in timeline.get("timeline", []):
                print(f"  [{evt.get('event_type')}] {evt.get('stage', '')}")
            print(f"Artifacts ({len(artifacts)}):")
            for art in artifacts:
                print(f"  {art.get('artifact_id')} [{art.get('stage')}] {art.get('artifact_type')}")
            print(f"Receipts ({len(receipts)}):")
            for rcpt in receipts:
                print(f"  {rcpt.get('receipt_id')} [{rcpt.get('stage')}] {rcpt.get('decision')}")
            closures_list = closures.get("closures", [])
            print(f"Closures ({len(closures_list)}):")
            for clo in closures_list:
                print(f"  {clo.get('closure_id')} [{clo.get('sla_status', '')}]")
        finally:
            await _close_coordination_client(nexus)
        return

    # ── Low-level commands via SDK facade ────────────────────
    # All remaining subcommands need an SDK client
    nexus = await _get_coordination_client()
    try:
        def _pp(data):
            print(_json.dumps(data, ensure_ascii=False, indent=2))

        # ── coding-intake ──────────────────────────────────
        if sub == "coding-intake":
            if len(args) < 4:
                print("Usage: node coordination coding-intake <owner_did> <actor_did> <objective> [--enclave <id>] [--complexity medium] [--risk normal] [--cost balanced] [--sensitivity internal] [--approval]")
                return
            opts = {"enclave_id": None, "complexity": "medium", "risk_level": "normal", "cost_policy": "balanced", "data_sensitivity": "internal", "requires_human_approval": False}
            it = iter(args[4:])
            for tok in it:
                if tok == "--enclave": opts["enclave_id"] = next(it, "")
                elif tok == "--complexity": opts["complexity"] = next(it, "medium")
                elif tok == "--risk": opts["risk_level"] = next(it, "normal")
                elif tok == "--cost": opts["cost_policy"] = next(it, "balanced")
                elif tok == "--sensitivity": opts["data_sensitivity"] = next(it, "internal")
                elif tok == "--approval": opts["requires_human_approval"] = True
            session = await nexus.coordination.coding_intake(
                owner_did=args[1], actor_did=args[2], objective=args[3],
                **opts,
            )
            print(f"Session: {session['coordination_session_id']}")
            _pp(session)

        # ── get ────────────────────────────────────────────
        elif sub == "get":
            if len(args) < 2:
                print("Usage: node coordination get <session_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            sess = await nexus.coordination.get_session(args[1], actor_did=actor_did)
            print(f"Session: {sess.get('coordination_session_id')}")
            print(f"Objective: {sess.get('objective')}")
            print(f"Status: {sess.get('status')}")
            _pp(sess)

        # ── list ───────────────────────────────────────────
        elif sub == "list":
            params = {}
            it = iter(args[1:])
            for tok in it:
                if tok == "--owner": params["owner_did"] = next(it, "")
                elif tok == "--actor": params["actor_did"] = next(it, "")
                elif tok == "--status": params["status"] = next(it, "")
                elif tok == "--playbook": params["playbook_id"] = next(it, "")
            sessions = await nexus.coordination.list_sessions(**params)
            print(f"Sessions: {len(sessions)}")
            for s in sessions:
                print(f"  {s.get('coordination_session_id')} — {s.get('objective', '')} [{s.get('status', '')}]")

        # ── fork ───────────────────────────────────────────
        elif sub == "fork":
            if len(args) < 2:
                print("Usage: node coordination fork <session_id> --actor <did> [--link-type <t>] [--reason <r>]"); return
            body = {"coordination_session_id": args[1], "actor_did": "", "link_type": "review_fork", "reason": ""}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": body["actor_did"] = next(it, "")
                elif tok == "--link-type": body["link_type"] = next(it, "review_fork")
                elif tok == "--reason": body["reason"] = next(it, "")
            child = await nexus.coordination.fork_session(**body)
            print(f"Forked: {child.get('coordination_session_id')}")
            _pp(child)

        # ── artifact ───────────────────────────────────────
        elif sub == "artifact":
            action = args[1] if len(args) > 1 else ""
            if action == "submit":
                if len(args) < 7:
                    print("Usage: node coordination artifact submit <session_id> <stage> <type> <producer_did> <content_ref> [--run <run_id>]"); return
                opts = {}
                it = iter(args[7:])
                for tok in it:
                    if tok == "--run": opts["run_id"] = next(it, "")
                art = await nexus.coordination.submit_artifact(
                    coordination_session_id=args[2], stage=args[3],
                    artifact_type=args[4], producer_did=args[5], content_ref=args[6],
                    **opts,
                )
                print(f"Artifact: {art.get('artifact_id')}")
                _pp(art)
            elif action == "list":
                params = {"actor_did": ""}
                it = iter(args[2:])
                for tok in it:
                    if tok == "--actor": params["actor_did"] = next(it, "")
                    elif tok == "--stage": params["stage"] = next(it, "")
                    elif tok == "--run": params["run_id"] = next(it, "")
                session_id = args[2] if len(args) > 2 and not args[2].startswith("--") else ""
                if session_id:
                    arts = await nexus.coordination.list_artifacts(session_id, **params)
                    _pp(arts)
                else:
                    print("Usage: node coordination artifact list <session_id> --actor <did>")
            else:
                print("Usage: node coordination artifact <submit|list> [...]")

        # ── receipt ────────────────────────────────────────
        elif sub == "receipt":
            action = args[1] if len(args) > 1 else ""
            if action == "submit":
                if len(args) < 7:
                    print("Usage: node coordination receipt submit <session_id> <stage> <type> <issuer_did> <decision> [--run <run_id>] [--subject-artifact <id>]"); return
                opts = {}
                it = iter(args[7:])
                for tok in it:
                    if tok == "--run": opts["run_id"] = next(it, "")
                    elif tok == "--subject-artifact": opts["subject_artifact_id"] = next(it, "")
                rcpt = await nexus.coordination.submit_receipt(
                    coordination_session_id=args[2], stage=args[3],
                    receipt_type=args[4], issuer_did=args[5], decision=args[6],
                    **opts,
                )
                print(f"Receipt: {rcpt.get('receipt_id')}")
                _pp(rcpt)
            elif action == "list":
                params = {"actor_did": ""}
                it = iter(args[2:])
                for tok in it:
                    if tok == "--actor": params["actor_did"] = next(it, "")
                    elif tok == "--stage": params["stage"] = next(it, "")
                    elif tok == "--run": params["run_id"] = next(it, "")
                session_id = args[2] if len(args) > 2 and not args[2].startswith("--") else ""
                if session_id:
                    receipts = await nexus.coordination.list_receipts(session_id, **params)
                    _pp(receipts)
                else:
                    print("Usage: node coordination receipt list <session_id> --actor <did>")
            else:
                print("Usage: node coordination receipt <submit|list> [...]")

        # ── advance ────────────────────────────────────────
        elif sub == "advance":
            if len(args) < 3:
                print("Usage: node coordination advance <session_id> <run_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[3:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            state = await nexus.coordination.advance(args[1], args[2], actor_did=actor_did)
            print(f"Status: {state.get('status')}")
            print(f"Stage:  {state.get('current_stage', state.get('previous_stage', ''))}")
            _pp(state)

        # ── timeline ───────────────────────────────────────
        elif sub == "timeline":
            if len(args) < 2:
                print("Usage: node coordination timeline <session_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            data = await nexus.coordination.timeline(args[1], actor_did=actor_did)
            tl = data.get("timeline", [])
            print(f"Events: {len(tl)}")
            for evt in tl:
                print(f"  [{evt.get('event_type')}] {evt.get('stage', '')}")
            _pp(data)

        # ── runtime-mock ───────────────────────────────────
        elif sub == "runtime-mock":
            if len(args) < 4:
                print("Usage: node coordination runtime-mock <session_id> <run_id> <stage> --actor <did> [--session <external_session>] [--delegatee <did>] [--delegator <did>]"); return
            actor_did = ""
            external_session = f"mock-{args[2]}-{args[3]}"
            delegatee_did = ""
            delegator_did = ""
            it = iter(args[4:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
                elif tok == "--session": external_session = next(it, external_session)
                elif tok == "--delegatee": delegatee_did = next(it, "")
                elif tok == "--delegator": delegator_did = next(it, "")
            delegation = None
            if delegatee_did:
                delegation = await nexus.coordination.delegate_stage(
                    coordination_session_id=args[1],
                    run_id=args[2],
                    stage=args[3],
                    delegator_did=delegator_did or actor_did,
                    delegatee_did=delegatee_did,
                    runtime_kind="external_mock",
                    protocol="agentnexus-runtime-mock",
                    session_id=external_session,
                )
            accepted = await nexus.coordination.emit_event(
                args[1],
                "runtime.adapter.accepted",
                actor_did=actor_did,
                run_id=args[2],
                stage=args[3],
                session_id=external_session,
                payload={
                    "runtime_kind": "external_mock",
                    "protocol": "agentnexus-runtime-mock",
                    "delegation_id": (delegation or {}).get("delegation", {}).get("delegation_id", ""),
                },
            )
            completed = await nexus.coordination.emit_event(
                args[1],
                "runtime.adapter.completed",
                actor_did=actor_did,
                run_id=args[2],
                stage=args[3],
                session_id=external_session,
                payload={"runtime_kind": "external_mock", "status": "completed"},
            )
            print(f"Runtime adapter mock: {external_session}")
            if delegation:
                print(f"Delegation: {delegation.get('delegation', {}).get('delegation_id')}")
            print(f"Events: {accepted.get('event_id')}, {completed.get('event_id')}")
            _pp({"delegation": delegation, "events": [accepted, completed]})

        # ── decision ───────────────────────────────────────
        elif sub == "decision":
            action = args[1] if len(args) > 1 else ""
            if action == "request":
                if len(args) < 6:
                    print("Usage: node coordination decision request <session_id> <run_id> <stage> <question> --actor <did> [--owner <did>] [--option <id:label>] [--recommend <id>] [--risk normal]"); return
                actor_did = ""
                owner_did = None
                options = []
                recommended = ""
                risk = "normal"
                it = iter(args[6:])
                for tok in it:
                    if tok == "--actor": actor_did = next(it, "")
                    elif tok == "--owner": owner_did = next(it, "")
                    elif tok == "--recommend": recommended = next(it, "")
                    elif tok == "--risk": risk = next(it, "normal")
                    elif tok == "--option":
                        raw = next(it, "")
                        opt_id, _, label = raw.partition(":")
                        options.append({"id": opt_id, "label": label or opt_id})
                decision = await nexus.coordination.create_decision(
                    coordination_session_id=args[2],
                    run_id=args[3],
                    stage=args[4],
                    requested_by_did=actor_did,
                    owner_did=owner_did,
                    question=args[5],
                    options=options,
                    recommended_option=recommended,
                    risk_level=risk,
                )
                print(f"Decision: {decision.get('decision_id')}")
                print(f"Status:   {decision.get('status')}")
                _pp(decision)
            elif action == "list":
                owner_did = ""
                actor_did = ""
                status = "pending"
                it = iter(args[2:])
                for tok in it:
                    if tok == "--owner": owner_did = next(it, "")
                    elif tok == "--actor": actor_did = next(it, "")
                    elif tok == "--status": status = next(it, "pending")
                if not owner_did or not actor_did:
                    print("Usage: node coordination decision list --owner <owner_did> --actor <did> [--status pending]"); return
                decisions = await nexus.coordination.list_decisions(owner_did=owner_did, actor_did=actor_did, status=status)
                print(f"Decisions: {len(decisions)}")
                for d in decisions:
                    print(f"  {d.get('decision_id')} [{d.get('status')}] {d.get('stage')}: {d.get('question')}")
                _pp({"decisions": decisions})
            elif action == "respond":
                if len(args) < 4:
                    print("Usage: node coordination decision respond <decision_id> <approved|changes_requested|rejected|aborted> --actor <did> [--comment <text>] [--channel <ref>]"); return
                actor_did = ""
                comment = ""
                channel_ref = ""
                it = iter(args[4:])
                for tok in it:
                    if tok == "--actor": actor_did = next(it, "")
                    elif tok == "--comment": comment = next(it, "")
                    elif tok == "--channel": channel_ref = next(it, "")
                result = await nexus.coordination.respond_decision(
                    args[2],
                    actor_did=actor_did,
                    decision=args[3],
                    comment=comment,
                    channel_ref=channel_ref,
                )
                print(f"Decision: {args[2]}")
                print(f"Status:   {result.get('status')}")
                print(f"Receipt:  {result.get('receipt', {}).get('receipt_id', '')}")
                _pp(result)
            else:
                print("Usage: node coordination decision <request|list|respond> [...]")

        # ── closures ───────────────────────────────────────
        elif sub == "closures":
            if len(args) < 2:
                print("Usage: node coordination closures <session_id> --actor <did> [--status <s>]"); return
            params = {}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": params["actor_did"] = next(it, "")
                elif tok == "--status": params["status"] = next(it, "")
            data = await nexus.coordination.closures(args[1], **params)
            cls = data.get("closures", [])
            print(f"Closures: {len(cls)}")
            for clo in cls:
                print(f"  {clo.get('closure_id')} [{clo.get('status')}]")
            _pp(data)

        # ── delegate ───────────────────────────────────────
        elif sub == "delegate":
            if len(args) < 4:
                print("Usage: node coordination delegate <session_id> <stage> <delegatee_did> --delegator <did> [--run <run_id>] [--role <r>]"); return
            body = {"coordination_session_id": args[1], "stage": args[2], "delegatee_did": args[3], "delegator_did": "", "role": args[2]}
            it = iter(args[4:])
            for tok in it:
                if tok == "--delegator": body["delegator_did"] = next(it, "")
                elif tok == "--role": body["role"] = next(it, args[2])
                elif tok == "--run": body["run_id"] = next(it, "")
            result = await nexus.coordination.delegate_stage(**body)
            delegation = result.get("delegation", {})
            print(f"Delegation: {delegation.get('delegation_id')}")
            print(f"Status: {delegation.get('status')}")
            _pp(result)

        # ── accept ─────────────────────────────────────────
        elif sub == "accept":
            if len(args) < 2:
                print("Usage: node coordination accept <delegation_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            result = await nexus.coordination.accept_delegation(args[1], actor_did=actor_did)
            print(f"Status: {result.get('status')}")
            _pp(result)

        # ── reject ─────────────────────────────────────────
        elif sub == "reject":
            if len(args) < 2:
                print("Usage: node coordination reject <delegation_id> --actor <did> [--reason <r>]"); return
            body = {"actor_did": "", "reason": ""}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": body["actor_did"] = next(it, "")
                elif tok == "--reason": body["reason"] = next(it, "")
            result = await nexus.coordination.reject_delegation(args[1], **body)
            print(f"Status: {result.get('status')}")
            _pp(result)

        else:
            print(f"Unknown coordination subcommand: '{sub}'")
            print("Primary:  demo | show <session_id> | timeline <session_id>")
            print("Low-level: coding-intake | get | list | fork | artifact submit/list | receipt submit/list | advance | delegate | accept | reject | closures")

    finally:
        await _close_coordination_client(nexus)



__all__ = [name for name in globals() if not name.startswith("__")]
