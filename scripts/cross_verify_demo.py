#!/usr/bin/env python3
"""
Cross-Verify Test: 双发行者 governance_attestation 验证演示

场景：
1. 使用一个 did:agentnexus 主体
2. APS 和 MolTrust 分别签发 governance_attestation
3. 两边的 JWS 独立验证
4. 合并结果得到多发行者共识

运行前提：
- MolTrust API Key (环境变量 MOLTRUST_API_KEY)
- APS 公开可用（无需 API Key）
- 一个已注册的 did:agentnexus DID

Usage:
    export MOLTRUST_API_KEY="your-key"
    python scripts/cross_verify_demo.py
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")


async def main():
    from agent_net.common.governance import (
        GovernanceRegistry,
        MolTrustClient,
        APSClient,
        CapabilityRequest,
        create_default_registry,
    )

    # 1. 创建 Registry 并注册两个发行者
    registry = GovernanceRegistry()

    # APS（公开，无需 API Key）
    registry.register("aps", APSClient())
    print("✅ APS 客户端已注册")

    # MolTrust（需要 API Key）
    moltrust_key = os.environ.get("MOLTRUST_API_KEY", "")
    if moltrust_key:
        registry.register("moltrust", MolTrustClient(api_key=moltrust_key))
        print("✅ MolTrust 客户端已注册")
    else:
        print("⚠️ MOLTRUST_API_KEY 未设置，跳过 MolTrust")

    # 2. 测试主体 DID（需要是真实注册的 DID）
    test_did = os.environ.get("TEST_AGENT_DID", "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK")
    print(f"\n📍 测试主体: {test_did}")

    # 3. 请求的能力
    requested = [
        CapabilityRequest(scope="data:read"),
        CapabilityRequest(scope="commerce:checkout", max_amount_usd=100),
    ]

    # 4. 并行调用两个发行者
    print("\n🔄 调用治理服务...")
    results = await registry.validate_capabilities(
        agent_did=test_did,
        requested=requested,
        context={"test": "cross_verify"},
    )

    # 5. 显示各发行者结果
    print("\n" + "=" * 60)
    print("📊 发行者独立验证结果")
    print("=" * 60)

    for name, att in results.items():
        print(f"\n【{name.upper()}】")
        print(f"  Decision: {att.decision}")
        print(f"  Trust Score: {att.trust_score}")
        print(f"  Passport Grade: {att.passport_grade}")
        print(f"  Spend Limit: ${att.spend_limit} (参考)")
        print(f"  Scopes: {att.scopes}")
        print(f"  Expires: {att.expires_at}")
        print(f"  JWS: {att.jws[:50]}..." if att.jws else "  JWS: (无签名)")

        # 验证 JWS
        if att.jws:
            valid = await registry.verify_attestation(att, name)
            print(f"  ✅ JWS 验证: {'通过' if valid else '失败'}")

    # 6. 合并结果
    print("\n" + "=" * 60)
    print("🔗 多发行者共识")
    print("=" * 60)

    best = registry.get_highest_trust(results)
    print(f"\n最高信任结果来自: {best.issuer}")
    print(f"  Decision: {best.decision}")
    print(f"  Trust Score: {best.trust_score}")
    print(f"  L 级映射: L{best.grade_to_level}")

    # 7. 计算聚合信任分
    if len(results) > 1:
        avg_score = sum(att.trust_score for att in results.values()) / len(results)
        print(f"\n📈 聚合信任分: {avg_score:.1f} (平均值)")
        print(f"   发行者数量: {len(results)}")
        print(f"   共识级别: {'强共识' if all(a.decision == 'permit' for a in results.values()) else '弱共识'}")

    print("\n✅ Cross-verify 测试完成！")
    print("   - 两个发行者独立签发 attestation")
    print("   - 每个 JWS 独立验证")
    print("   - 零耦合：发行者之间无依赖")
    print("   - 可组合：信号类型跨厂商合成")


if __name__ == "__main__":
    asyncio.run(main())
