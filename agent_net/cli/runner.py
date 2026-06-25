import asyncio

from .common import _read_token

# ── node local-runner 子命令 ──────────────────────────────

async def node_local_runner_cmd(args: list[str]):
    """node local-runner — Objective Loop V1.1 local runner CLI.

    Usage:
      python main.py node local-runner run <session_id> <run_id> [--config <path>]
      python main.py node local-runner start [--config <path>]
    """
    if not args:
        print("Usage: node local-runner <run|start> [...]")
        return

    sub = args[0]
    config_path = ".agentnexus/local-runner.yaml"
    it = iter(args[1:])
    for tok in it:
        if tok == "--config":
            config_path = next(it, config_path)

    from agent_net.node.local_runner import load_runner_config

    try:
        cfg = load_runner_config(config_path)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Create one based on .agentnexus/local-runner.yaml.example")
        return
    except ValueError as e:
        print(f"Config error: {e}")
        return

    if sub == "run":
        if len(args) < 3:
            print("Usage: node local-runner run <session_id> <run_id> [--config <path>] [--owner <did>] [--actor <did>]")
            return

        # Reconcile local worker profiles with Worker Registry
        from agent_net.node.local_runner import reconcile_workers
        try:
            token = _read_token()
            auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
            reconcile_warnings = await reconcile_workers(
                cfg, cfg["daemon_url"], auth_headers
            )
            for w in reconcile_warnings:
                print(f"  [WARNING] {w}")
        except ValueError as e:
            print(f"Error: {e}")
            return

        session_id = args[1]
        run_id = args[2]

        # Parse extra args
        owner_override = ""
        actor_override = ""
        it2 = iter(args[3:])
        for tok in it2:
            if tok == "--owner": owner_override = next(it2, "")
            elif tok == "--actor": actor_override = next(it2, "")
            elif tok == "--config": pass  # already parsed

        owner_did = owner_override or cfg.get("owner_did", "")
        actor_did = actor_override or cfg.get("secretary_agent", "")

        if not owner_did:
            print("Error: owner_did required (set in config or pass --owner)")
            return

        print(f"Local Runner run: session={session_id} run={run_id}")
        print(f"  Owner: {owner_did}  Actor: {actor_did}")

        from agent_net.node.runner_loop import runner_tick
        import httpx
        token = _read_token()
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
        daemon_url = cfg["daemon_url"]

        async with httpx.AsyncClient(timeout=30) as client:

            async def _list(**kw):
                r = await client.get(f"{daemon_url}/coordination/sessions", params={k: v for k, v in kw.items() if v}, headers=auth_headers)
                if r.status_code == 200: return r.json().get("sessions", [])
                return []

            async def _na(sid, actor):
                r = await client.get(f"{daemon_url}/coordination/sessions/{sid}/next-action", params={"actor_did": actor or ""}, headers=auth_headers)
                if r.status_code == 200: return r.json().get("action", {})
                return {"action_type": "blocked", "reason": f"API: {r.status_code}"}

            async def _detail(sid, actor):
                r = await client.get(f"{daemon_url}/coordination/sessions/{sid}", params={"actor_did": actor or ""}, headers=auth_headers)
                if r.status_code != 200: return {}
                detail = r.json().get("session", r.json())
                try:
                    ar = await client.get(f"{daemon_url}/coordination/sessions/{sid}/artifacts", params={"actor_did": actor or ""}, headers=auth_headers)
                    if ar.status_code == 200: detail["artifacts"] = ar.json().get("artifacts", [])
                except Exception: detail["artifacts"] = []
                try:
                    rr = await client.get(f"{daemon_url}/coordination/sessions/{sid}/receipts", params={"actor_did": actor or ""}, headers=auth_headers)
                    if rr.status_code == 200: detail["receipts"] = rr.json().get("receipts", [])
                except Exception: detail["receipts"] = []
                return detail

            async def _ce(**body):
                r = await client.post(f"{daemon_url}/coordination/executions", json=body, headers=auth_headers)
                if r.status_code == 200: return r.json()
                raise Exception(f"create_execution: {r.status_code}")

            async def _sr(eid, body):
                r = await client.post(f"{daemon_url}/coordination/executions/{eid}/result", json=body, headers=auth_headers)
                if r.status_code == 200: return r.json()
                raise Exception(f"submit_result: {r.status_code}")

            async def _adv(sid, rid, actor):
                r = await client.post(f"{daemon_url}/coordination/coding/{sid}/runs/{rid}/advance", json={"actor_did": actor}, headers=auth_headers)
                if r.status_code == 200: return r.json()
                raise Exception(f"advance: {r.status_code}")

            async def _dec(**kw):
                from agent_net.node.secretary_gateway import handle_decision_gate
                return await handle_decision_gate(**kw)

            async def _ue(eid, body):
                r = await client.patch(
                    f"{daemon_url}/coordination/executions/{eid}",
                    json=body,
                    headers=auth_headers,
                )
                if r.status_code == 200:
                    return r.json()
                raise Exception(f"update_execution: {r.status_code}")

            actions = await runner_tick(
                config=cfg,
                list_sessions=_list,
                get_next_action=_na,
                get_session_detail=_detail,
                create_execution=_ce,
                submit_result=_sr,
                call_advance=_adv,
                create_decision=_dec,
                update_execution=_ue,
                actor_did=actor_did,
                owner_did=owner_did,
            )

            for a in actions:
                print(f"  [{a.get('action', '?')}] {a.get('session_id', '')[:16]} "
                      f"stage={a.get('stage', '')} → {a.get('result_status', a.get('reason', ''))}")

    elif sub == "start":
        daemon_url = cfg["daemon_url"]
        poll_interval = cfg.get("poll_interval_sec", 5)

        # Read daemon token for auth
        token = _read_token()
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
        actor_did = cfg.get("secretary_agent", "")
        owner_did = cfg.get("owner_did", "")

        print(f"Local Runner started")
        print(f"  Daemon: {daemon_url}")
        print(f"  Workers: {list(cfg.get('workers', {}).keys())}")
        print(f"  Actor: {actor_did or '(not set)'}")
        print(f"  Owner: {owner_did or '(not set)'}")
        print(f"  Poll interval: {poll_interval}s")
        print(f"  Press Ctrl+C to stop")
        print()

        # Reconcile local worker profiles with Worker Registry
        from agent_net.node.local_runner import reconcile_workers
        try:
            reconcile_warnings = await reconcile_workers(
                cfg, daemon_url, auth_headers
            )
            for w in reconcile_warnings:
                print(f"  [WARNING] {w}")
        except ValueError as e:
            print(f"Error: {e}")
            return

        import httpx
        tick_count = 0

        while True:
            tick_count += 1
            try:
                async with httpx.AsyncClient(timeout=30) as client:

                    async def _list_sessions(**kw):
                        r = await client.get(
                            f"{daemon_url}/coordination/sessions",
                            params={k: v for k, v in kw.items() if v},
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json().get("sessions", [])
                        return []

                    async def _next_action(sid, actor):
                        r = await client.get(
                            f"{daemon_url}/coordination/sessions/{sid}/next-action",
                            params={"actor_did": actor or ""},
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json().get("action", {})
                        return {"action_type": "blocked", "reason": f"API: {r.status_code}"}

                    async def _get_session_detail(sid, actor):
                        r = await client.get(
                            f"{daemon_url}/coordination/sessions/{sid}",
                            params={"actor_did": actor or ""},
                            headers=auth_headers,
                        )
                        if r.status_code != 200:
                            return {}
                        detail = r.json().get("session", r.json())

                        # Also fetch artifacts and receipts for context
                        try:
                            ar = await client.get(
                                f"{daemon_url}/coordination/sessions/{sid}/artifacts",
                                params={"actor_did": actor or ""},
                                headers=auth_headers,
                            )
                            if ar.status_code == 200:
                                detail["artifacts"] = ar.json().get("artifacts", [])
                        except Exception:
                            detail["artifacts"] = []

                        try:
                            rr = await client.get(
                                f"{daemon_url}/coordination/sessions/{sid}/receipts",
                                params={"actor_did": actor or ""},
                                headers=auth_headers,
                            )
                            if rr.status_code == 200:
                                detail["receipts"] = rr.json().get("receipts", [])
                        except Exception:
                            detail["receipts"] = []
                        return detail

                    async def _create_exec(**body):
                        r = await client.post(
                            f"{daemon_url}/coordination/executions",
                            json=body,
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json()
                        raise Exception(f"create_execution: {r.status_code}")

                    async def _submit_result(eid, result_body):
                        r = await client.post(
                            f"{daemon_url}/coordination/executions/{eid}/result",
                            json=result_body,
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json()
                        raise Exception(f"submit_result: {r.status_code}")

                    async def _call_advance(sid, rid, actor):
                        r = await client.post(
                            f"{daemon_url}/coordination/coding/{sid}/runs/{rid}/advance",
                            json={"actor_did": actor},
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json()
                        raise Exception(f"advance: {r.status_code}")

                    async def _create_decision(**kw):
                        from agent_net.node.secretary_gateway import handle_decision_gate
                        return await handle_decision_gate(**kw)

                    async def _ue(eid, body):
                        r = await client.patch(
                            f"{daemon_url}/coordination/executions/{eid}",
                            json=body,
                            headers=auth_headers,
                        )
                        if r.status_code == 200:
                            return r.json()
                        raise Exception(f"update_execution: {r.status_code}")

                    actions = await runner_tick(
                        config=cfg,
                        list_sessions=_list_sessions,
                        get_next_action=_next_action,
                        get_session_detail=_get_session_detail,
                        create_execution=_create_exec,
                        submit_result=_submit_result,
                        call_advance=_call_advance,
                        create_decision=_create_decision,
                        update_execution=_ue,
                        actor_did=actor_did,
                        owner_did=owner_did,
                    )

                    for a in actions:
                        at = a.get("action", "?")
                        if at == "start_execution":
                            print(f"  [{tick_count}] {a['session_id'][:16]} {a['stage']} → {a['result_status']}")
                        elif at in ("advance", "closed", "create_decision_gate"):
                            print(f"  [{tick_count}] {a['session_id'][:16]} {at}: {a.get('reason', a.get('gate', ''))}")
                        elif at == "error":
                            print(f"  [{tick_count}] ERROR: {a.get('reason', '')}")
                        elif at == "skip":
                            print(f"  [{tick_count}] SKIP {a.get('session_id', '')[:16]}: {a.get('reason', '')}")

                    if not actions:
                        # Print a dot for idle ticks
                        pass

            except httpx.ConnectError:
                print(f"  [{tick_count}] Cannot connect to {daemon_url} — retrying...")
            except Exception as e:
                print(f"  [{tick_count}] Error: {e}")

            await asyncio.sleep(poll_interval)

    else:
        print(f"Unknown local-runner subcommand: '{sub}'")
        print("Usage: node local-runner <run|start> [...]")


async def _objective_demo(owner_did: str, actor_did: str, objective: str, roles: str):
    """Create a new Objective Loop session via the coordination API."""
    import httpx
    token = _read_token()
    auth = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Create session via coordination intake
        r = await client.post(
            "http://127.0.0.1:8765/coordination/coding/intake",
            json={
                "owner_did": owner_did,
                "actor_did": actor_did,
                "objective": objective,
                "complexity": "medium",
            },
            headers=auth,
        )
        if r.status_code == 200:
            data = r.json()
            print(f"Session created: {data.get('coordination_session_id', '?')}")
            print(f"Dashboard: http://127.0.0.1:8765/ui/coordination/{data.get('coordination_session_id', '')}")
        else:
            print(f"Error: {r.status_code} {r.text}")


async def _run_demo_loop():
    """Run a complete Objective Loop demo using the coordination API and fake workers.

    Creates a coding.v1 session and executes all 7 stages locally.
    """
    import httpx, uuid, json as _json
    from agent_net.node.local_runner import execute_stage

    token = _read_token()
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    base = "http://127.0.0.1:8765"

    # Fake worker scripts for each stage
    FAKE_WORKERS = {
        "clarify": {
            "summary": "Requirements clarified: login module needs email+password flow",
            "status": "completed",
            "artifact_type": "RequirementSpec",
            "artifact_body": "# Requirements\n- Email/password login\n- Session management\n- Error handling",
            "evidence_refs": [],
        },
        "design": {
            "summary": "Design complete: 3-tier architecture with JWT auth",
            "status": "completed",
            "artifact_type": "DesignArtifact",
            "artifact_body": "# Design\n- Frontend: React form\n- Backend: FastAPI /auth endpoint\n- Storage: SQLite users table",
            "evidence_refs": [],
        },
        "design_review": {
            "summary": "Design review passed: architecture approved",
            "status": "completed",
            "artifact_type": "DesignReviewArtifact",
            "artifact_body": "# Review\n- Architecture: ✅\n- Security: JWT ✅\n- No blocking issues",
            "evidence_refs": [],
        },
        "implement": {
            "summary": "Implementation complete: login endpoint + frontend form",
            "status": "completed",
            "artifact_type": "ImplementationArtifact",
            "artifact_body": "```python\n@app.post('/auth/login')\nasync def login(...):\n    ...\n```",
            "evidence_refs": [],
        },
        "code_review": {
            "summary": "Code review passed: no P0/P1 issues",
            "status": "completed",
            "artifact_type": "CodeReviewArtifact",
            "artifact_body": "# Code Review\n- Login flow: ✅\n- Error handling: ✅\n- Tests: ✅\nNo blocking issues",
            "evidence_refs": [],
        },
        "test": {
            "summary": "All tests passed: 12 passed, 0 failed",
            "status": "completed",
            "artifact_type": "TestResultArtifact",
            "artifact_body": "12 passed, 0 failed in 2.34s",
            "evidence_refs": [],
        },
        "final": {
            "summary": "Delivery manifest generated",
            "status": "completed",
            "artifact_type": "DeliveryManifest",
            "artifact_body": "# Delivery Manifest\nAll stages complete, 7/7 artifacts, 7/7 receipts approved",
            "evidence_refs": [],
        },
    }

    STAGES = ["clarify", "design", "design_review", "implement", "code_review", "test", "final"]

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Register owner
        owner_name = f"DemoOwner_{uuid.uuid4().hex[:6]}"
        r = await client.post(f"{base}/owner/register", json={"name": owner_name}, headers=auth)
        if r.status_code == 200:
            owner = r.json()
        else:
            print(f"Failed to create owner: {r.status_code} {r.text}")
            return

        print(f"Owner:      {owner['did']}")

        # 2. Create session via intake
        r = await client.post(
            f"{base}/coordination/coding/intake",
            json={
                "owner_did": owner["did"],
                "actor_did": owner["did"],
                "objective": "Implement login module with email+password",
                "complexity": "medium",
            },
            headers=auth,
        )
        if r.status_code != 200:
            print(f"Failed intake: {r.status_code} {r.text}")
            return
        sess = r.json()
        sid = sess.get("session", {}).get("coordination_session_id", "")
        rid = sess.get("session", {}).get("playbook_run_id", "")
        enclave_id = sess.get("session", {}).get("enclave_id", "default")
        print(f"Session:    {sid}")
        print(f"Objective:  Implement login module with email+password")
        print(f"Dashboard:  http://127.0.0.1:8765/ui/coordination/{sid}")
        print(f"Stages:     {' → '.join(STAGES)}")
        print()

        # 3. Run each stage
        for i, stage in enumerate(STAGES):
            fw = FAKE_WORKERS[stage]
            print(f"  [{i+1}/{len(STAGES)}] {stage}...", end=" ", flush=True)

            # Advance to this stage (except first stage which starts at clarify)
            if i > 0:
                await client.post(
                    f"{base}/coordination/coding/{sid}/runs/{rid}/advance",
                    json={"actor_did": owner["did"]},
                    headers=auth,
                )

            # Write artifact to Vault first (required by artifact API)
            from agent_net.storage import vault_put as _vp
            vk = f"demo/{stage}/output.md"
            await _vp(enclave_id, vk, fw["artifact_body"], owner["did"])
            content_ref = f"vault://{enclave_id}/{vk}"

            # Create artifact
            art_r = await client.post(
                f"{base}/coordination/artifacts",
                json={
                    "coordination_session_id": sid,
                    "run_id": rid,
                    "stage": stage,
                    "artifact_type": fw["artifact_type"],
                    "producer_did": owner["did"],
                    "content_ref": content_ref,
                },
                headers=auth,
            )
            art_id = art_r.json().get("artifact", {}).get("artifact_id", "")

            # Create receipt
            rcpt_r = await client.post(
                f"{base}/coordination/receipts",
                json={
                    "coordination_session_id": sid,
                    "run_id": rid,
                    "stage": stage,
                    "receipt_type": "FinalResultReceipt" if stage == "final" else "DesignReceipt",
                    "issuer_did": owner["did"],
                    "decision": "approved",
                    "subject_artifact_id": art_id,
                    "actor_did": owner["did"],
                },
                headers=auth,
            )

            status = "OK" if rcpt_r.status_code == 200 else "FAIL"
            print(status)

        print()
        print(f"=== Demo complete ===")
        print(f"Session:    {sid}")
        print(f"Dashboard:  http://127.0.0.1:8765/ui/coordination/{sid}")
        print()
        print("Run with local-runner: python main.py node local-runner start")

async def node_objective_cmd(args: list[str]):
    """node objective — Objective Loop V1.1 objective management.

    Usage:
      python main.py node objective start --owner <did> --actor <did> --objective "<text>"
      python main.py node objective status <session_id> --actor <did>
    """
    if not args:
        print("Usage: node objective <start|status> [...]")
        return

    sub = args[0]

    if sub == "start":
        owner_did = ""
        actor_did = ""
        objective = ""
        roles = ""
        it = iter(args[1:])
        for tok in it:
            if tok == "--owner": owner_did = next(it, "")
            elif tok == "--actor": actor_did = next(it, "")
            elif tok == "--objective": objective = next(it, "")
            elif tok == "--roles": roles = next(it, "")

        if not owner_did or not objective:
            print("Usage: node objective start --owner <did> --actor <did> --objective \"<text>\" [--roles a,b,c]")
            return

        print(f"Creating objective: {objective}")
        await _objective_demo(owner_did, actor_did, objective, roles)

    elif sub == "demo":
        print("=== Objective Loop V1.1 Demo ===\n")
        await _run_demo_loop()

    elif sub == "status":
        if len(args) < 2:
            print("Usage: node objective status <session_id> --actor <did>")
            return
        session_id = args[1]
        actor_did = ""
        it = iter(args[2:])
        for tok in it:
            if tok == "--actor": actor_did = next(it, "")

        from agent_net.node.loop_engine import next_action
        action = await next_action(session_id, actor_did or "")
        print(f"Session: {session_id}")
        print(f"Next action: {action['action_type']}")
        print(f"Stage: {action.get('stage', '')}")
        print(f"Reason: {action.get('reason', '')}")

    else:
        print(f"Unknown objective subcommand: '{sub}'")



__all__ = [name for name in globals() if not name.startswith("__")]
