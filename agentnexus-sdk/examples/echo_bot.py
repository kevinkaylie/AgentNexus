"""
Example: Echo Bot with Discussion Protocol

A simple bot that echoes messages and demonstrates discussion capabilities.
"""
import asyncio
import agentnexus
from agentnexus import (
    Consensus,
    ConsensusMode,
    TimeoutAction,
    ActionItem,
    ConclusionType,
)


async def main():
    # Connect to AgentNexus network
    nexus = await agentnexus.connect(
        name="EchoBot",
        caps=["Chat", "Discussion"],
    )

    print(f"Connected as: {nexus.agent_info.did}")

    # Message handler
    @nexus.on_message
    async def handle_message(msg):
        print(f"[MSG] From {msg.from_did}: {msg.content}")

        # Echo back
        await nexus.send(
            to_did=msg.from_did,
            content=f"Echo: {msg.content}",
        )

    # Task proposal handler
    @nexus.on_task_propose
    async def handle_task_propose(action):
        print(f"[TASK] New task: {action.content['title']}")

        # Claim the task
        await nexus.claim_task(
            to_did=action.from_did,
            task_id=action.content["task_id"],
            message="I'll handle this!",
        )

        # Simulate work
        await asyncio.sleep(1)

        # Notify completion
        await nexus.notify_state(
            to_did=action.from_did,
            status="completed",
            task_id=action.content["task_id"],
        )

    # Keep running
    print("EchoBot is running. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
