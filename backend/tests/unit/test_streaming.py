"""测试 ReAct Agent 的流式输出

验证 token 流是否能正确传播到外层。
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.graph.workflow import astream_workflow
from langchain_core.messages import HumanMessage


async def test_react_streaming():
    """测试 ReAct 循环的流式输出"""

    print("=" * 60)
    print("测试 ReAct Agent 流式输出")
    print("=" * 60)

    # 简单的查询测试
    message = "帮我搜索一下字节跳动的面试题"

    print(f"\n输入: {message}")
    print("-" * 60)

    token_count = 0
    update_count = 0
    final_content = ""

    async for event in astream_workflow(
        messages=[HumanMessage(content=message)],
        thread_id="test-streaming",
    ):
        event_type = event.get("type")

        if event_type == "token":
            token_count += 1
            content = event.get("content", "")
            final_content += content
            # 只打印前几个 token 和后几个 token
            if token_count <= 5:
                print(f"[Token {token_count}] {content}")
            elif token_count == 6:
                print("...")

        elif event_type == "update":
            update_count += 1
            node = event.get("node", "")
            content = event.get("content", "")
            print(f"\n[Update] Node: {node}")
            print(f"  Content: {content[:100]}..." if len(content) > 100 else f"  Content: {content}")

        elif event_type == "final":
            print(f"\n[Final] 流程完成")

        elif event_type == "error":
            print(f"\n[Error] {event.get('content')}")

    print("-" * 60)
    print(f"统计:")
    print(f"  Token 数量: {token_count}")
    print(f"  Update 数量: {update_count}")
    print(f"  最终内容长度: {len(final_content)}")

    if token_count > 0:
        print(f"\n✅ Token 流正常工作!")
        print(f"   前 50 字符: {final_content[:50]}")
    else:
        print(f"\n❌ Token 流未工作，请检查配置")


async def test_simple_chat():
    """测试简单聊天的流式输出（不触发工具）"""

    print("\n" + "=" * 60)
    print("测试简单聊天流式输出（无工具调用）")
    print("=" * 60)

    # 简单聊天，不应该触发工具
    message = "你好，请简单介绍一下你自己"

    print(f"\n输入: {message}")
    print("-" * 60)

    token_count = 0
    final_content = ""

    async for event in astream_workflow(
        messages=[HumanMessage(content=message)],
        thread_id="test-simple-chat",
    ):
        event_type = event.get("type")

        if event_type == "token":
            token_count += 1
            content = event.get("content", "")
            final_content += content
            print(content, end="", flush=True)

        elif event_type == "update":
            print(f"\n[Update] {event.get('node')}: {event.get('content', '')[:50]}")

    print("\n" + "-" * 60)
    print(f"Token 数量: {token_count}")

    if token_count > 0:
        print("✅ 简单聊天流式输出正常!")
    else:
        print("❌ 简单聊天流式输出失败!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Offer-Catcher 流式输出测试")
    print("=" * 60)

    # 运行测试
    asyncio.run(test_simple_chat())
    asyncio.run(test_react_streaming())