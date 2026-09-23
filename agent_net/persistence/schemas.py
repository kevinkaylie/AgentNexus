"""SQLite schema initialization and migrations."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Return whether a table already contains a column."""
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    return any(row[1] == column for row in rows)


async def _safe_migrate(
    db: aiosqlite.Connection,
    alter_sql: str,
    table: str,
    column: str,
) -> None:
    """Add a column while preserving errors unrelated to duplicate columns."""
    if await _column_exists(db, table, column):
        return
    try:
        await db.execute(alter_sql)
        await db.commit()
    except aiosqlite.OperationalError:
        if await _column_exists(db, table, column):
            return
        raise


# ── Enclave Tables (ADR-013) ────────────────────────────────────────

async def init_enclave_tables(db: aiosqlite.Connection):
    """初始化 Enclave 相关表（在 init_db 中调用，连接由调用者管理）"""
    await db.executescript("""
            -- Enclave 项目组
            CREATE TABLE IF NOT EXISTS enclaves (
                enclave_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_did TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                vault_backend TEXT DEFAULT 'local',
                vault_config TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            -- 成员 + 角色
            CREATE TABLE IF NOT EXISTS enclave_members (
                enclave_id TEXT NOT NULL,
                did TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT DEFAULT 'rw',
                handbook TEXT,
                joined_at REAL NOT NULL,
                PRIMARY KEY (enclave_id, did),
                FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id)
            );

            -- Playbook 定义
            CREATE TABLE IF NOT EXISTS playbooks (
                playbook_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT DEFAULT '1',
                fingerprint TEXT DEFAULT '',
                stages TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            -- Playbook 执行实例
            CREATE TABLE IF NOT EXISTS playbook_runs (
                run_id TEXT PRIMARY KEY,
                coordination_session_id TEXT DEFAULT NULL,
                enclave_id TEXT NOT NULL,
                playbook_id TEXT NOT NULL,
                playbook_name TEXT DEFAULT '',
                current_stage TEXT,
                status TEXT DEFAULT 'running',
                context TEXT DEFAULT '{}',
                started_at REAL NOT NULL,
                completed_at REAL,
                FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id),
                FOREIGN KEY (playbook_id) REFERENCES playbooks(playbook_id)
            );

            -- 阶段执行记录
            CREATE TABLE IF NOT EXISTS stage_executions (
                run_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                assigned_did TEXT,
                status TEXT DEFAULT 'pending',
                task_id TEXT,
                output_ref TEXT,
                retry_count INTEGER DEFAULT 0,
                started_at REAL,
                completed_at REAL,
                PRIMARY KEY (run_id, stage_name),
                FOREIGN KEY (run_id) REFERENCES playbook_runs(run_id)
            );

            -- Vault 存储（LocalVaultBackend 使用）
            CREATE TABLE IF NOT EXISTS enclave_vault (
                enclave_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                updated_by TEXT NOT NULL,
                updated_at REAL NOT NULL,
                message TEXT DEFAULT '',
                PRIMARY KEY (enclave_id, key)
            );

            -- Vault 历史版本
            CREATE TABLE IF NOT EXISTS enclave_vault_history (
                enclave_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at REAL NOT NULL,
                message TEXT DEFAULT '',
                action TEXT DEFAULT 'update'  -- create / update / delete
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_enclaves_owner ON enclaves(owner_did);
            CREATE INDEX IF NOT EXISTS idx_enclaves_status ON enclaves(status);
            CREATE INDEX IF NOT EXISTS idx_enclave_members_did ON enclave_members(did);
            CREATE INDEX IF NOT EXISTS idx_playbook_runs_enclave ON playbook_runs(enclave_id);
            CREATE INDEX IF NOT EXISTS idx_playbook_runs_status ON playbook_runs(status);
            CREATE INDEX IF NOT EXISTS idx_stage_executions_task ON stage_executions(task_id);
            CREATE INDEX IF NOT EXISTS idx_vault_history_enclave_key ON enclave_vault_history(enclave_id, key);

            -- Capability Tokens（v1.0-08）
            CREATE TABLE IF NOT EXISTS capability_tokens (
                token_id TEXT PRIMARY KEY,
                version INTEGER DEFAULT 1,
                issuer_did TEXT NOT NULL,
                subject_did TEXT NOT NULL,
                enclave_id TEXT,
                scope_json TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                validity_json TEXT NOT NULL,
                revocation_endpoint TEXT NOT NULL,
                evaluated_constraint_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                revoked_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_ct_subject ON capability_tokens(subject_did);
            CREATE INDEX IF NOT EXISTS idx_ct_enclave ON capability_tokens(enclave_id);
            CREATE INDEX IF NOT EXISTS idx_ct_status ON capability_tokens(status);

            -- 委托链关系（v1.0-08）
            CREATE TABLE IF NOT EXISTS delegation_chain_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_token_id TEXT NOT NULL,
                parent_token_id TEXT NOT NULL,
                parent_scope_hash TEXT NOT NULL,
                depth INTEGER DEFAULT 1,
                FOREIGN KEY (child_token_id) REFERENCES capability_tokens(token_id),
                FOREIGN KEY (parent_token_id) REFERENCES capability_tokens(token_id)
            );
            CREATE INDEX IF NOT EXISTS idx_dcl_child ON delegation_chain_links(child_token_id);
            CREATE INDEX IF NOT EXISTS idx_dcl_parent ON delegation_chain_links(parent_token_id);
        """)
    await db.commit()

    # ── 向后兼容迁移（PRAGMA 检查，不静默吞错）──
    _enclave_migrations = [
        ("ALTER TABLE playbooks ADD COLUMN version TEXT DEFAULT '1'", "playbooks", "version"),
        ("ALTER TABLE playbooks ADD COLUMN fingerprint TEXT DEFAULT ''", "playbooks", "fingerprint"),
        ("ALTER TABLE stage_executions ADD COLUMN evaluated_constraint_hash TEXT", "stage_executions", "evaluated_constraint_hash"),
        ("ALTER TABLE stage_executions ADD COLUMN capability_token_id TEXT", "stage_executions", "capability_token_id"),
        ("ALTER TABLE stage_executions ADD COLUMN retry_count INTEGER DEFAULT 0", "stage_executions", "retry_count"),
    ]
    for alter_sql, table, column in _enclave_migrations:
        await _safe_migrate(db, alter_sql, table, column)


# ── Trust & Governance Tables (ADR-014) ───────────────────────────────────

async def init_trust_tables(db: aiosqlite.Connection):
    """初始化信任网络和治理认证相关表（连接由调用者管理）"""
    # 检查表是否已存在，避免重复创建
    existing = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trust_edges'"
    )
    row = await existing.fetchone()
    if row is not None:
        # 表已存在，跳过
        return
    await db.executescript("""
        -- 信任边（Web of Trust）
        CREATE TABLE IF NOT EXISTS trust_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_did TEXT NOT NULL,
            to_did TEXT NOT NULL,
            score REAL NOT NULL,
            timestamp REAL NOT NULL,
            evidence TEXT,
            UNIQUE(from_did, to_did)
        );
        CREATE INDEX IF NOT EXISTS idx_trust_edges_from ON trust_edges(from_did);
        CREATE INDEX IF NOT EXISTS idx_trust_edges_to ON trust_edges(to_did);

        -- 交互记录
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_did TEXT NOT NULL,
            to_did TEXT NOT NULL,
            interaction_type TEXT NOT NULL,
            success INTEGER NOT NULL,
            response_time_ms REAL,
            timestamp REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_interactions_to_did ON interactions(to_did, timestamp);

        -- 声誉缓存
        CREATE TABLE IF NOT EXISTS reputation_cache (
            agent_did TEXT PRIMARY KEY,
            base_score REAL NOT NULL,
            behavior_delta REAL NOT NULL,
            attestation_bonus REAL NOT NULL,
            trust_level INTEGER NOT NULL,
            updated_at REAL NOT NULL
        );

        -- 治理认证缓存
        CREATE TABLE IF NOT EXISTS governance_attestations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_did TEXT NOT NULL,
            issuer TEXT NOT NULL,
            attestation_json TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(agent_did, issuer)
        );
        CREATE INDEX IF NOT EXISTS idx_governance_attestations_did ON governance_attestations(agent_did);
        CREATE INDEX IF NOT EXISTS idx_governance_attestations_expires ON governance_attestations(expires_at);
    """)
    await db.commit()


async def init_coordination_tables(db: aiosqlite.Connection):
    """初始化 Coding Coordination V1 相关表（连接由调用者管理）"""
    await db.executescript("""
            CREATE TABLE IF NOT EXISTS coordination_sessions (
                coordination_session_id TEXT PRIMARY KEY,
                root_session_id TEXT DEFAULT NULL,
                owner_did TEXT NOT NULL,
                controller_did TEXT NOT NULL,
                objective TEXT NOT NULL,
                enclave_id TEXT NOT NULL,
                playbook_id TEXT NOT NULL,
                playbook_version TEXT DEFAULT '1',
                playbook_fingerprint TEXT DEFAULT '',
                playbook_run_id TEXT NOT NULL,
                current_stage TEXT DEFAULT '',
                status TEXT DEFAULT 'running',
                policy_json TEXT DEFAULT '{}',
                context_snapshot TEXT DEFAULT NULL,
                stage_snapshots TEXT NOT NULL DEFAULT '[]',
                intake_session_id TEXT DEFAULT NULL,
                parent_session_id TEXT DEFAULT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_links (
                link_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                from_session_id TEXT NOT NULL,
                to_session_id TEXT NOT NULL,
                link_type TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_links_coord
                ON session_links(coordination_session_id);
            CREATE INDEX IF NOT EXISTS idx_session_links_child
                ON session_links(to_session_id);

            CREATE TABLE IF NOT EXISTS delegations (
                delegation_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                role TEXT NOT NULL,
                delegator_did TEXT NOT NULL,
                delegatee_did TEXT NOT NULL,
                capability_token_id TEXT DEFAULT '',
                runtime_kind TEXT DEFAULT 'native_worker',
                protocol TEXT DEFAULT 'agentnexus-native',
                session_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_delegations_coord
                ON delegations(coordination_session_id);

            CREATE TABLE IF NOT EXISTS runtime_events (
                event_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                stage TEXT DEFAULT '',
                actor_did TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                run_id TEXT DEFAULT '',
                delegation_id TEXT DEFAULT '',
                artifact_id TEXT DEFAULT '',
                receipt_id TEXT DEFAULT '',
                payload TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runtime_events_coord
                ON runtime_events(coordination_session_id);
            CREATE INDEX IF NOT EXISTS idx_runtime_events_stage
                ON runtime_events(coordination_session_id, stage);
            CREATE INDEX IF NOT EXISTS idx_runtime_events_type
                ON runtime_events(coordination_session_id, event_type);

            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                producer_did TEXT NOT NULL,
                content_ref TEXT NOT NULL,
                content_hash TEXT DEFAULT '',
                schema_version TEXT DEFAULT '1',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_coord
                ON artifacts(coordination_session_id);
            CREATE INDEX IF NOT EXISTS idx_artifacts_stage
                ON artifacts(coordination_session_id, run_id, stage);

            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL,
                receipt_type TEXT NOT NULL,
                issuer_did TEXT NOT NULL,
                decision TEXT NOT NULL,
                subject_artifact_id TEXT DEFAULT '',
                evidence_refs TEXT DEFAULT '[]',
                signature TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_receipts_coord
                ON receipts(coordination_session_id);
            CREATE INDEX IF NOT EXISTS idx_receipts_stage
                ON receipts(coordination_session_id, run_id, stage);

            CREATE TABLE IF NOT EXISTS decision_requests (
                decision_id TEXT PRIMARY KEY,
                owner_did TEXT NOT NULL,
                coordination_session_id TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT '',
                requested_by_did TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT DEFAULT '[]',
                recommended_option TEXT DEFAULT '',
                risk_level TEXT DEFAULT 'normal',
                evidence_refs TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                response_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                resolved_at REAL DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decision_requests_owner
                ON decision_requests(owner_did, status);
            CREATE INDEX IF NOT EXISTS idx_decision_requests_coord
                ON decision_requests(coordination_session_id, run_id, stage, status);

            CREATE TABLE IF NOT EXISTS closure_records (
                closure_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                actor_did TEXT NOT NULL,
                status TEXT NOT NULL,
                sla_status TEXT NOT NULL,
                sla_metrics TEXT DEFAULT '{}',
                receipt_id TEXT DEFAULT '',
                evidence_refs TEXT DEFAULT '[]',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_closure_records_coord
                ON closure_records(coordination_session_id);

            CREATE TABLE IF NOT EXISTS objective_executions (
                execution_id TEXT PRIMARY KEY,
                coordination_session_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                worker_did TEXT NOT NULL,
                backend_kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                lease_expires_at REAL,
                attempt INTEGER DEFAULT 1,
                external_session_id TEXT DEFAULT '',
                artifact_id TEXT DEFAULT '',
                receipt_id TEXT DEFAULT '',
                result_hash TEXT DEFAULT '',
                error TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_objective_executions_session
                ON objective_executions(coordination_session_id, run_id, stage);
            CREATE INDEX IF NOT EXISTS idx_objective_executions_status
                ON objective_executions(status, lease_expires_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_objective_executions_active_stage
                ON objective_executions(coordination_session_id, run_id, stage)
                WHERE status IN ('pending', 'running');
        """)

    coord_migrations = [
        ("ALTER TABLE coordination_sessions ADD COLUMN enclave_id TEXT DEFAULT ''", "coordination_sessions", "enclave_id"),
        ("ALTER TABLE coordination_sessions ADD COLUMN playbook_id TEXT DEFAULT 'coding.v1'", "coordination_sessions", "playbook_id"),
        ("ALTER TABLE coordination_sessions ADD COLUMN playbook_version TEXT DEFAULT '1'", "coordination_sessions", "playbook_version"),
        ("ALTER TABLE coordination_sessions ADD COLUMN playbook_fingerprint TEXT DEFAULT ''", "coordination_sessions", "playbook_fingerprint"),
        ("ALTER TABLE coordination_sessions ADD COLUMN playbook_run_id TEXT DEFAULT ''", "coordination_sessions", "playbook_run_id"),
        ("ALTER TABLE coordination_sessions ADD COLUMN current_stage TEXT DEFAULT ''", "coordination_sessions", "current_stage"),
        ("ALTER TABLE coordination_sessions ADD COLUMN stage_snapshots TEXT DEFAULT '[]'", "coordination_sessions", "stage_snapshots"),
        ("ALTER TABLE artifacts ADD COLUMN run_id TEXT DEFAULT ''", "artifacts", "run_id"),
        ("ALTER TABLE receipts ADD COLUMN run_id TEXT DEFAULT ''", "receipts", "run_id"),
    ]
    for alter_sql, table, column in coord_migrations:
        await _safe_migrate(db, alter_sql, table, column)
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 秘书编排相关 — D-SEC-01 / D-SEC-02
# ══════════════════════════════════════════════════════════════════════════════

async def init_secretary_tables(db: aiosqlite.Connection):
    """初始化 secretary_intakes 表（连接由调用者管理）"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS secretary_intakes (
            session_id TEXT PRIMARY KEY,
            owner_did TEXT NOT NULL,
            actor_did TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'intake',
            objective TEXT NOT NULL,
            required_roles TEXT NOT NULL,
            preferred_playbook TEXT,
            selected_workers TEXT,
            run_id TEXT,
            coordination_session_id TEXT,
            source_channel TEXT,
            source_message_ref TEXT,
            constraints_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_intakes_owner ON secretary_intakes(owner_did);
        CREATE INDEX IF NOT EXISTS idx_intakes_status ON secretary_intakes(status);
        CREATE INDEX IF NOT EXISTS idx_intakes_run ON secretary_intakes(run_id);
    """)
    await _safe_migrate(
        db,
        "ALTER TABLE secretary_intakes ADD COLUMN coordination_session_id TEXT",
        "secretary_intakes",
        "coordination_session_id",
    )
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Code Review Collaboration Profile v1 —— AgentNexus 侧存储
# 依据：Profile §15.4（词表与持久化映射）、§15.6（external ID 与 epoch）、
#       §15.7（角色授权）、binding RC2 §4/§5。
# 说明：profile 数据独立成表，不改动既有非 Profile 路径的语义；
#       artifact 的 profile 元数据按 §15.4 的映射表以**加列**方式扩展。
# ══════════════════════════════════════════════════════════════════════════════

async def init_code_review_tables(db: aiosqlite.Connection):
    """初始化 Code Review Profile 相关表与列（连接由调用者管理）"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS code_review_profile_sessions (
            profile_session_id TEXT PRIMARY KEY,
            coordination_session_id TEXT NOT NULL,
            coordinator_id TEXT NOT NULL,
            external_run_id TEXT NOT NULL,
            review_revision INTEGER NOT NULL DEFAULT 1,
            review_policy_sha256 TEXT NOT NULL DEFAULT '',
            activation_revision INTEGER,
            target_revision INTEGER,
            target_json TEXT DEFAULT '{}',
            adapter_version TEXT DEFAULT '',
            role_enforcement TEXT NOT NULL DEFAULT 'unenforced',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cr_sessions_key
            ON code_review_profile_sessions(coordinator_id, external_run_id);
        CREATE INDEX IF NOT EXISTS idx_cr_sessions_coord
            ON code_review_profile_sessions(coordination_session_id);

        CREATE TABLE IF NOT EXISTS code_review_deliveries (
            delivery_id TEXT PRIMARY KEY,
            profile_session_id TEXT NOT NULL,
            external_run_id TEXT NOT NULL,
            external_attempt_id TEXT NOT NULL,
            assignment_epoch INTEGER NOT NULL,
            input_manifest_digest TEXT NOT NULL DEFAULT '',
            artifact_id TEXT NOT NULL DEFAULT '',
            artifact_digest TEXT NOT NULL DEFAULT '',
            byte_length INTEGER NOT NULL DEFAULT 0,
            schema_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'received',
            reason_code TEXT DEFAULT '',
            replaces_delivery_id TEXT,
            correction_no INTEGER,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cr_deliveries_attempt
            ON code_review_deliveries(profile_session_id, external_run_id, external_attempt_id);

        CREATE TABLE IF NOT EXISTS code_review_receipts (
            receipt_id TEXT PRIMARY KEY,
            profile_session_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            decision TEXT NOT NULL,
            issuer_id TEXT NOT NULL,
            subject_kind TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            external_run_id TEXT NOT NULL DEFAULT '',
            external_attempt_id TEXT,
            report_digest TEXT,
            authority_ref TEXT DEFAULT '',
            reason_code TEXT DEFAULT '',
            evidence_refs TEXT DEFAULT '[]',
            signature TEXT DEFAULT '',
            enforcement TEXT DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cr_receipts_run
            ON code_review_receipts(profile_session_id, external_run_id, kind);

        CREATE TABLE IF NOT EXISTS code_review_messages (
            message_id TEXT PRIMARY KEY,
            profile_session_id TEXT NOT NULL DEFAULT '',
            message_type TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'inbound',
            sender_id TEXT NOT NULL,
            receiver_id TEXT NOT NULL,
            correlation_id TEXT DEFAULT '',
            causation_id TEXT,
            external_run_id TEXT DEFAULT '',
            external_attempt_id TEXT DEFAULT '',
            assignment_epoch INTEGER,
            payload_digest TEXT DEFAULT '',
            envelope_json TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'stored',
            receipts_json TEXT DEFAULT '[]',
            error_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cr_messages_session
            ON code_review_messages(profile_session_id, state);
    """)

    # 评审 R3-4：消息幂等按**业务投影**比较（§7），需要持久化投影摘要
    await _safe_migrate(
        db,
        "ALTER TABLE code_review_messages ADD COLUMN projection_digest TEXT DEFAULT ''",
        "code_review_messages",
        "projection_digest",
    )

    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS code_review_role_grants (
            principal_id TEXT NOT NULL,
            role TEXT NOT NULL,
            instance_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            profile_session_id TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            PRIMARY KEY (principal_id, role, instance_id, project_id, profile_session_id)
        );

        CREATE TABLE IF NOT EXISTS code_review_enforcement (
            constraint_name TEXT PRIMARY KEY,
            level TEXT NOT NULL,
            component TEXT DEFAULT '',
            updated_at REAL NOT NULL
        );

        -- 评审 B1：服务接口的独立凭据登记（token 摘要 → principal）。
        -- 既有 Daemon token 只证明"能访问本 Daemon"，不能证明主体身份与资源范围；
        -- 这里显式登记 principal_id、角色、可代表的 DID 与允许的 instance/project/session。
        CREATE TABLE IF NOT EXISTS code_review_service_principals (
            token_sha256 TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            roles_json TEXT NOT NULL DEFAULT '[]',
            dids_json TEXT NOT NULL DEFAULT '[]',
            instances_json TEXT NOT NULL DEFAULT '[]',
            projects_json TEXT NOT NULL DEFAULT '[]',
            sessions_json TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        -- 评审 B4 / R2-1 / R3-3 / R3-4：上传幂等映射。
        -- state: pending=已预留但产物尚未登记；committed=产物已登记。
        -- namespace（principal + 动作 + 资源范围）与幂等 key 分离（RC2 §7）：
        -- 同一 key 在不同 namespace 下是**不同操作**，不按冲突处理。
        CREATE TABLE IF NOT EXISTS code_review_artifact_idempotency (
            principal_id TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'artifact_upload',
            resource_scope TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (principal_id, action, resource_scope, idempotency_key)
        );
    """)

    # 既有库：早期形状没有 namespace/state/updated_at。重建表以保留已登记的 key
    # （§6 禁止把 key 清理后当成新操作执行），旧行以 action='artifact_upload'、
    # resource_scope='' 迁移；空 scope 不会与新的真实 scope 命中，属一次性迁移。
    try:
        async with db.execute("PRAGMA table_info(code_review_artifact_idempotency)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
    except Exception:  # pragma: no cover - 表刚创建时一定存在
        columns = set()
    if columns and "action" not in columns:
        await db.execute("ALTER TABLE code_review_artifact_idempotency RENAME TO _cr_idem_old")
        await db.execute(
            """
            CREATE TABLE code_review_artifact_idempotency (
                principal_id TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'artifact_upload',
                resource_scope TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (principal_id, action, resource_scope, idempotency_key)
            )
            """
        )
        legacy_state = "'committed'" if "state" in columns else "'pending'"
        legacy_updated = "updated_at" if "updated_at" in columns else "created_at"
        await db.execute(
            f"""
            INSERT INTO code_review_artifact_idempotency
                (principal_id, action, resource_scope, idempotency_key, artifact_id,
                 request_digest, state, created_at, updated_at)
            SELECT principal_id, 'artifact_upload', '', idempotency_key, artifact_id,
                   request_digest, {legacy_state}, created_at, {legacy_updated}
            FROM _cr_idem_old
            """
        )
        await db.execute("DROP TABLE _cr_idem_old")

    # artifact 的 profile 元数据（§15.4：新增字段或关联表；此处按加列实现）
    artifact_migrations = [
        ("ALTER TABLE artifacts ADD COLUMN media_type TEXT DEFAULT ''", "media_type"),
        ("ALTER TABLE artifacts ADD COLUMN byte_length INTEGER DEFAULT 0", "byte_length"),
        ("ALTER TABLE artifacts ADD COLUMN access_scope TEXT DEFAULT ''", "access_scope"),
        ("ALTER TABLE artifacts ADD COLUMN retention_until REAL", "retention_until"),
        ("ALTER TABLE artifacts ADD COLUMN digest_algorithm TEXT DEFAULT ''", "digest_algorithm"),
        ("ALTER TABLE artifacts ADD COLUMN profile_session_id TEXT DEFAULT ''", "profile_session_id"),
        # 评审 R2「协议边界」：retention_until 必须**原样**回显请求值，不能由 float 反格式化
        ("ALTER TABLE artifacts ADD COLUMN retention_until_text TEXT DEFAULT ''", "retention_until_text"),
    ]
    for alter_sql, column in artifact_migrations:
        await _safe_migrate(db, alter_sql, "artifacts", column)

    # execution 的 §15.6/§15.5 字段
    execution_migrations = [
        ("ALTER TABLE objective_executions ADD COLUMN external_coordinator_id TEXT DEFAULT ''", "external_coordinator_id"),
        ("ALTER TABLE objective_executions ADD COLUMN external_run_id TEXT DEFAULT ''", "external_run_id"),
        ("ALTER TABLE objective_executions ADD COLUMN external_attempt_id TEXT DEFAULT ''", "external_attempt_id"),
        ("ALTER TABLE objective_executions ADD COLUMN assignment_epoch INTEGER DEFAULT 0", "assignment_epoch"),
        ("ALTER TABLE objective_executions ADD COLUMN input_manifest_digest TEXT DEFAULT ''", "input_manifest_digest"),
        ("ALTER TABLE objective_executions ADD COLUMN output_schema TEXT DEFAULT ''", "output_schema"),
        ("ALTER TABLE objective_executions ADD COLUMN deadline REAL", "deadline"),
        ("ALTER TABLE objective_executions ADD COLUMN enforcement_json TEXT DEFAULT '{}'", "enforcement_json"),
        ("ALTER TABLE objective_executions ADD COLUMN profile_session_id TEXT DEFAULT ''", "profile_session_id"),
    ]
    for alter_sql, column in execution_migrations:
        await _safe_migrate(db, alter_sql, "objective_executions", column)

    await db.commit()
