"""Agents, owners, messaging, skills, and push persistence."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path
from .schemas import (
    _column_exists,
    _safe_migrate,
    init_coordination_tables,
    init_enclave_tables,
    init_secretary_tables,
    init_trust_tables,
)


async def init_db():
    get_db_path().parent.mkdir(exist_ok=True)
    async with connect() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                did TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                is_local INTEGER DEFAULT 0,
                last_seen REAL,
                private_key_hex TEXT
            );
            -- 向后兼容：为旧数据库追加列（若已存在则忽略错误）

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                delivered INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS contacts (
                did TEXT PRIMARY KEY,
                endpoint TEXT,
                relay TEXT,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS pending_requests (
                did TEXT PRIMARY KEY,
                init_packet TEXT NOT NULL,
                requested_at REAL NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS skills (
                skill_id TEXT PRIMARY KEY,
                agent_did TEXT NOT NULL,
                name TEXT NOT NULL,
                capabilities TEXT,
                actions TEXT NOT NULL,
                platform TEXT DEFAULT 'native',
                created_at REAL NOT NULL,
                FOREIGN KEY (agent_did) REFERENCES agents(did)
            );

            CREATE TABLE IF NOT EXISTS push_registrations (
                registration_id TEXT PRIMARY KEY,
                did TEXT NOT NULL,
                callback_url TEXT NOT NULL,
                callback_type TEXT DEFAULT 'webhook',
                callback_secret TEXT NOT NULL,
                push_key TEXT,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(did, callback_url, callback_type)
            );
            CREATE INDEX IF NOT EXISTS idx_push_registrations_did ON push_registrations(did);
            CREATE INDEX IF NOT EXISTS idx_push_registrations_expires ON push_registrations(expires_at);
        """)
        await db.commit()

        # ── 向后兼容迁移（使用 PRAGMA table_info 检查，不静默吞错）──
        _migrations = [
            ("ALTER TABLE agents ADD COLUMN private_key_hex TEXT", "agents", "private_key_hex"),
            ("ALTER TABLE agents ADD COLUMN owner_did TEXT DEFAULT NULL", "agents", "owner_did"),
            ("ALTER TABLE messages ADD COLUMN session_id TEXT DEFAULT ''", "messages", "session_id"),
            ("ALTER TABLE messages ADD COLUMN reply_to INTEGER DEFAULT NULL", "messages", "reply_to"),
            ("ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT NULL", "messages", "message_type"),
            ("ALTER TABLE messages ADD COLUMN protocol TEXT DEFAULT NULL", "messages", "protocol"),
            ("ALTER TABLE messages ADD COLUMN content_encoding TEXT DEFAULT NULL", "messages", "content_encoding"),
            ("ALTER TABLE agents ADD COLUMN worker_type TEXT DEFAULT 'resident'", "agents", "worker_type"),
            ("ALTER TABLE messages ADD COLUMN message_id TEXT", "messages", "message_id"),
        ]
        for alter_sql, table, column in _migrations:
            await _safe_migrate(db, alter_sql, table, column)

        # 索引：CREATE INDEX IF NOT EXISTS 天然幂等，无需额外检查
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_did)",
        ]:
            await db.execute(idx_sql)
            await db.commit()

        # ── 子模块表（复用当前连接，避免重复 aiosqlite.connect）──
        await init_enclave_tables(db)
        await init_secretary_tables(db)
        await init_trust_tables(db)
        await init_coordination_tables(db)

        # 向后兼容：为后续模块创建的表追加 coordination 列
        for alter in [
            "ALTER TABLE playbook_runs ADD COLUMN coordination_session_id TEXT DEFAULT NULL",
            "ALTER TABLE secretary_intakes ADD COLUMN coordination_session_id TEXT DEFAULT NULL",
            "ALTER TABLE stage_executions ADD COLUMN delegation_id TEXT DEFAULT NULL",
            "ALTER TABLE artifacts ADD COLUMN run_id TEXT DEFAULT ''",
            "ALTER TABLE receipts ADD COLUMN run_id TEXT DEFAULT ''",
        ]:
            try:
                await db.execute(alter)
                await db.commit()
            except Exception:
                pass  # 列已存在，忽略


