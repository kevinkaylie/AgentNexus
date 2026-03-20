"""
agent_net.node.gatekeeper
访问控制网关 —— 在握手入口处执行白/黑名单 + 模式检查

模式:
  public  — 全部放行（黑名单除外）
  private — 仅白名单放行
  ask     — 未知 DID 进入 PENDING 队列，等待人工审批

决策结果:
  GateDecision.ALLOW   — 放行，继续握手
  GateDecision.DENY    — 拒绝，返回 403
  GateDecision.PENDING — 存入 pending_requests，返回 202
"""
import json
import asyncio
from enum import Enum
from pathlib import Path

from agent_net import storage

CONFIG_DIR = Path(__file__).parent.parent.parent / "data"
WHITELIST_PATH = CONFIG_DIR / "whitelist.json"
BLACKLIST_PATH = CONFIG_DIR / "blacklist.json"
MODE_PATH = CONFIG_DIR / "mode.json"


class GateDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    PENDING = "pending"


# ── 文件 I/O ─────────────────────────────────────────────

def _load_list(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_list(path: Path, dids: set[str]):
    CONFIG_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(sorted(dids), indent=2, ensure_ascii=False), encoding="utf-8")


def load_mode() -> str:
    if MODE_PATH.exists():
        try:
            return json.loads(MODE_PATH.read_text(encoding="utf-8")).get("mode", "public")
        except Exception:
            pass
    return "public"


def save_mode(mode: str):
    CONFIG_DIR.mkdir(exist_ok=True)
    MODE_PATH.write_text(json.dumps({"mode": mode}, ensure_ascii=False), encoding="utf-8")


# ── Gatekeeper ────────────────────────────────────────────

class Gatekeeper:
    """
    权限管理器，每次调用 check() 都从磁盘重新读取列表（热加载）。
    生产环境可加内存缓存 + 文件 watcher。
    """

    # resolve 回调：did -> asyncio.Future，握手恢复用
    _pending_futures: dict[str, asyncio.Future] = {}

    async def check(self, did: str, init_packet: dict) -> GateDecision:
        blacklist = _load_list(BLACKLIST_PATH)
        if did in blacklist:
            return GateDecision.DENY

        whitelist = _load_list(WHITELIST_PATH)
        if did in whitelist:
            return GateDecision.ALLOW

        mode = load_mode()
        if mode == "public":
            return GateDecision.ALLOW
        elif mode == "private":
            return GateDecision.DENY
        else:  # ask
            await storage.add_pending(did, init_packet)
            return GateDecision.PENDING

    # ── 白/黑名单管理 ─────────────────────────────────────

    def whitelist_add(self, did: str):
        lst = _load_list(WHITELIST_PATH)
        lst.add(did)
        _save_list(WHITELIST_PATH, lst)

    def whitelist_remove(self, did: str):
        lst = _load_list(WHITELIST_PATH)
        lst.discard(did)
        _save_list(WHITELIST_PATH, lst)

    def whitelist_all(self) -> list[str]:
        return sorted(_load_list(WHITELIST_PATH))

    def blacklist_add(self, did: str):
        lst = _load_list(BLACKLIST_PATH)
        lst.add(did)
        _save_list(BLACKLIST_PATH, lst)

    def blacklist_remove(self, did: str):
        lst = _load_list(BLACKLIST_PATH)
        lst.discard(did)
        _save_list(BLACKLIST_PATH, lst)

    def blacklist_all(self) -> list[str]:
        return sorted(_load_list(BLACKLIST_PATH))

    # ── PENDING 恢复机制 ──────────────────────────────────

    def register_pending_future(self, did: str, fut: asyncio.Future):
        """握手协程注册一个 Future，resolve 后由此唤醒"""
        self._pending_futures[did] = fut

    async def resolve(self, did: str, action: str) -> bool:
        """
        人工审批：action='allow'|'deny'
        1. 更新 SQLite 状态
        2. 若握手协程正在等待，通过 Future 唤醒
        """
        ok = await storage.resolve_pending(did, action)
        if not ok:
            return False
        fut = self._pending_futures.pop(did, None)
        if fut and not fut.done():
            fut.set_result(action)
        return True


# 全局单例
gatekeeper = Gatekeeper()
