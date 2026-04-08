"""测试 SSE 流式输出端点

直接调用 /chat/stream API 验证流式输出。
"""

import asyncio
import httpx


async def test_sse_stream():
    """测试 SSE 流式输出"""

    print("=" * 60)
    print("测试 SSE 流式输出端点")
    print("=" * 60)

    url = "http://localhost:8000/api/v1/chat/stream"
    payload = {
        "message": "帮我搜索一下字节跳动的面试题",
        "conversation_id": "test-sse-stream"
    }

    print(f"\n请求: {payload['message']}")
    print("-" * 60)

    token_count = 0
    chunk_count = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            print(f"状态码: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print("-" * 60)

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # 去掉 "data: " 前缀

                    if data == "[DONE]":
                        print("\n[DONE] 流式输出结束")
                        break
                    elif data.startswith("[ERROR]"):
                        print(f"\n[ERROR] {data}")
                        break
                    else:
                        chunk_count += 1
                        # 统计 token 数量（粗略）
                        token_count += len(data.split())

                        # 打印前几个 chunk
                        if chunk_count <= 5:
                            print(f"[Chunk {chunk_count}] {data}")
                        elif chunk_count == 6:
                            print("...")
                        elif chunk_count > 5:
                            print(data, end="", flush=True)

    print("\n" + "-" * 60)
    print(f"统计:")
    print(f"  Chunk 数量: {chunk_count}")
    print(f"  粗略 Token 数: {token_count}")

    if chunk_count > 10:
        print("\n✅ SSE 流式输出正常!")
    else:
        print("\n❌ SSE 流式输出可能有问题")


if __name__ == "__main__":
    asyncio.run(test_sse_stream())