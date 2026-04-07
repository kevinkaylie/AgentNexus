"""
Webhook Platform Adapter

Generic webhook adapter for platforms like Dify, Coze, etc.
"""
import hashlib
import hmac
import json
from typing import Dict, Any, Optional

import aiohttp

from .base import PlatformAdapter, SkillManifest


class WebhookAdapter(PlatformAdapter):
    """
    Webhook platform adapter.

    Provides bidirectional communication through webhooks:
    - inbound: Receive webhooks from external platforms
    - outbound: Send webhooks to external platforms

    Usage:
        adapter = WebhookAdapter(agent_did, router, storage, webhook_secret)
        await adapter.inbound(webhook_request)
    """

    platform = "webhook"

    def __init__(
        self,
        agent_did: str,
        router,  # agent_net.router.Router
        storage,  # agent_net.storage module
        webhook_secret: str,
        callback_url: Optional[str] = None,
    ):
        """
        Initialize Webhook adapter.

        Args:
            agent_did: The Agent DID this adapter is bound to
            router: Daemon's router module for message sending
            storage: Daemon's storage module
            webhook_secret: Secret for HMAC signature verification
            callback_url: Default callback URL for outbound webhooks
        """
        self.agent_did = agent_did
        self.router = router
        self.storage = storage
        self.webhook_secret = webhook_secret
        self.callback_url = callback_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def inbound(self, request: dict) -> dict:
        """
        Handle incoming webhook → AgentNexus message.

        Args:
            request: {
                "signature": HMAC-SHA256 signature,
                "timestamp": Unix timestamp,
                "body": {
                    "to_did": target DID,
                    "content": message content,
                    ...
                }
            }

        Returns:
            Response dict
        """
        # Verify signature
        signature = request.get("signature", "")
        timestamp = request.get("timestamp", "")
        body = request.get("body", {})

        if not self._verify_signature(signature, timestamp, body):
            return {"error": "Invalid signature", "status": 401}

        # Extract message parameters
        to_did = body.get("to_did")
        content = body.get("content")

        if not to_did or content is None:
            return {"error": "Missing to_did or content", "status": 400}

        # Route message
        try:
            result = await self.router.route_message(
                from_did=self.agent_did,
                to_did=to_did,
                content=json.dumps(content) if isinstance(content, dict) else content,
                message_type=body.get("message_type"),
                protocol=body.get("protocol"),
            )
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"error": str(e), "status": 500}

    async def outbound(self, message: dict) -> dict:
        """
        Send AgentNexus message → external webhook.

        Args:
            message: {
                "callback_url": target URL (or use default),
                "from_did": sender DID,
                "content": message content,
                ...
            }

        Returns:
            Webhook response
        """
        callback_url = message.get("callback_url") or self.callback_url
        if not callback_url:
            return {"error": "No callback URL configured", "status": 400}

        session = await self._get_session()

        payload = {
            "from_did": message.get("from_did", self.agent_did),
            "content": message.get("content"),
        }

        headers = self._sign_headers(payload)

        try:
            async with session.post(
                callback_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"status": "ok", "response": await resp.json()}
                else:
                    return {
                        "error": f"Webhook returned {resp.status}",
                        "status": resp.status,
                    }
        except Exception as e:
            return {"error": str(e), "status": 500}

    def skill_manifest(self) -> dict:
        """Return skill manifest for this adapter."""
        manifest = SkillManifest(
            name="agentnexus-webhook",
            version="0.1.0",
            platform="webhook",
            description="AgentNexus webhook adapter for generic platform integration",
            capabilities=["Communication", "Webhook"],
            actions=["send_webhook", "receive_webhook"],
            install={
                "type": "webhook",
                "config": {
                    "callback_url": "Your platform's webhook URL",
                    "secret": "Your webhook secret",
                },
            },
            auth={
                "type": "hmac_sha256",
                "header": "X-AgentNexus-Signature",
            },
        )
        return manifest.to_dict()

    # ── Signature Methods ───────────────────────────────────────────

    def _verify_signature(self, signature: str, timestamp: str, body: dict) -> bool:
        """
        Verify HMAC-SHA256 signature.

        Args:
            signature: Provided signature (hex)
            timestamp: Unix timestamp string
            body: Request body

        Returns:
            True if signature is valid
        """
        if not signature or not timestamp:
            return False

        # Compute expected signature
        payload = f"{timestamp}.{json.dumps(body, separators=(',', ':'))}"
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def _sign_headers(self, payload: dict) -> dict:
        """
        Generate signed headers for outbound webhook.

        Args:
            payload: JSON payload

        Returns:
            Headers dict with signature
        """
        import time
        timestamp = str(int(time.time()))
        payload_str = json.dumps(payload, separators=(',', ':'))
        sign_payload = f"{timestamp}.{payload_str}"
        signature = hmac.new(
            self.webhook_secret.encode(),
            sign_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Content-Type": "application/json",
            "X-AgentNexus-Timestamp": timestamp,
            "X-AgentNexus-Signature": signature,
        }
