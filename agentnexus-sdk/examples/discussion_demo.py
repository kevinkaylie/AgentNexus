"""
Example: Multi-Agent Discussion Demo

Demonstrates how to start a discussion, vote, and conclude.
"""
import asyncio
import agentnexus
from agentnexus import (
    Consensus,
    ConsensusMode,
    TimeoutAction,
    ActionItem,
    ConclusionType,
    DiscussionManager,
)


async def main():
    # Connect to AgentNexus network
    nexus = await agentnexus.connect(
        name="DiscussionLeader",
        caps=["Chat", "Discussion"],
    )

    print(f"Connected as: {nexus.agent_info.did}")

    # Create discussion manager
    discussion_mgr = DiscussionManager(nexus)

    # Start a discussion with majority voting
    topic_id = await discussion_mgr.start_discussion(
        title="Should we use async or sync API?",
        participants=[
            "did:agentnexus:z6Mk...dev1",  # Replace with actual DIDs
            "did:agentnexus:z6Mk...dev2",
        ],
        context="We need to decide on the API style for the SDK.",
        consensus=Consensus(
            mode=ConsensusMode.MAJORITY,
            timeout_seconds=300,  # 5 minutes
            timeout_action=TimeoutAction.AUTO_REJECT,
        ),
        related_task_id="task_sdk_design",
    )

    print(f"Started discussion: {topic_id}")

    # Simulate discussion flow
    await asyncio.sleep(2)

    # Reply to discussion
    await discussion_mgr.reply(
        topic_id=topic_id,
        content="I prefer async API because it's more flexible.",
    )

    # Cast vote
    await discussion_mgr.vote(
        topic_id=topic_id,
        vote="approve",
        reason="Async is the way to go",
    )

    # After voting completes (simulated), conclude
    await asyncio.sleep(2)

    await discussion_mgr.conclude(
        topic_id=topic_id,
        conclusion="We will use async API with sync wrapper as optional",
        conclusion_type=ConclusionType.CONSENSUS,
        action_items=[
            ActionItem(
                type="update_document",
                ref="adr-006",
                description="Update SDK architecture doc with async-first approach",
            ),
        ],
    )

    print("Discussion concluded!")

    await nexus.close()


if __name__ == "__main__":
    asyncio.run(main())
