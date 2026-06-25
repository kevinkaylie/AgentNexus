#!/usr/bin/env python
"""
AgentNexus CLI

用法:
  agent-nexus node start                      启动本地节点 Daemon (:8765)
  agent-nexus node mcp                        启动节点 MCP Server (stdio，无身份绑定)
  agent-nexus node mcp --name <name>          启动 MCP 并自动注册/绑定 Agent（推荐）
    --caps <cap1,cap2,...>                       能力标签（逗号分隔）
    --desc <description>                        名片描述
    --tags <tag1,tag2,...>                       名片标签
    --public                                     公开注册到联邦种子站
  agent-nexus node mcp --did <did>            启动 MCP 并绑定到已有 DID
  agent-nexus node demo                       本地功能演示
  agent-nexus node status [--pending]         查看节点状态（--pending 只看待审批请求）
  agent-nexus node mode set <public|ask|private>  设置访问控制模式
  agent-nexus node whitelist add    <did>     加入白名单
  agent-nexus node whitelist remove <did>     移出白名单
  agent-nexus node whitelist list             查看白名单
  agent-nexus node blacklist add    <did>     加入黑名单
  agent-nexus node blacklist remove <did>     移出黑名单
  agent-nexus node blacklist list             查看黑名单
  agent-nexus node resolve <did> <allow|deny> 审批 PENDING 握手请求

  agent-nexus node relay list                 查看已配置的 relay
  agent-nexus node relay add <url>            加入种子 relay（写配置并触发 federation/join）
  agent-nexus node relay remove <url>         移除种子 relay
  agent-nexus node relay set-local <url>      设置本地 relay 地址
  agent-nexus node local-runner start [--config <path>]
                                             启动 Objective Loop 本地 Runner
  agent-nexus node local-runner run <session_id> <run_id> [--config <path>]
                                             执行指定 coordination session/run
  agent-nexus node objective start --owner <did> --actor <did> --objective "<text>"
                                             创建 Objective Loop session
  agent-nexus node objective status <session_id> --actor <did>
                                             查看 Objective Loop 状态

  agent-nexus relay start [--host <domain>]    启动公网信令/中转服务器 (:9000)
                                                 --host: 设置 Relay 域名（用于 did:web）

  agent-nexus agent list                列出所有本地 Agent
  agent-nexus agent get   <did>         查看指定 Agent 详情
  agent-nexus agent add   <name> [opts] 新建 Agent
    --type <type>                         类型，默认 GeneralAgent
    --caps <cap1,cap2,...>                能力标签（逗号分隔）
    --location <loc>                      地理位置
    --public                              公开注册到联邦种子站
    --desc <description>                  名片描述
    --tags <tag1,tag2,...>               名片标签
  agent-nexus agent update <did> [opts] 更新 Agent 字段
    --name <name>
    --type <type>
    --caps <cap1,cap2,...>               覆盖能力标签
    --location <loc>
  agent-nexus agent delete <did>        删除指定 Agent
  agent-nexus agent search <keyword>    按能力关键词搜索
  agent-nexus agent profile <did>       查看 Agent 的 NexusProfile 名片
  agent-nexus agent export <did> --output <file> --password <pw>
                                       导出加密 Agent 身份包
  agent-nexus agent import <file> --password <pw>
                                       导入加密 Agent 身份包

  agent-nexus node worker init <name> [--type <type>] [--owner <owner_did>] [--caps c1,c2]
                                        注册 Worker Agent（默认 interactive_cli）
  agent-nexus node worker status <did>  查看 Worker 状态（owner、worker_type、presence）

  agent-nexus test                      运行全部测试用例
"""
import sys
import asyncio
import os


def _read_token() -> str:
    """从 data/daemon_token.txt 读取 daemon Token（写接口鉴权用）"""
    from agent_net.common.constants import DAEMON_TOKEN_FILE
    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE) as f:
            return f.read().strip()
    return ""


def _usage():
    print(__doc__)
    sys.exit(1)



__all__ = [name for name in globals() if not name.startswith("__")]
