"""接口冒烟测试：python -m pytest tests -q  （或直接 python tests/test_api_smoke.py）

覆盖：健康检查 → 登录 → 活动列表/新建/状态机 → 图书列表/扫码 → AI 对话 → 漂流池
不依赖真实大模型（走 Mock），可离线跑通。
"""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

client = TestClient(app)


def _login(student_no: str = "T2009") -> str:
    resp = client.post("/api/v1/auth/login", json={"student_no": student_no, "password": "123456"})
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]["token"]


def test_smoke() -> None:
    # 1. 健康检查
    r = client.get("/api/v1/health").json()
    assert r["code"] == 0 and r["data"]["app"], r

    # 2. 未登录访问受限接口 → 1002
    r = client.get("/api/v1/users/me").json()
    assert r["code"] == 1002, r

    # 3. 登录
    token = _login("T2009")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/users/me", headers=headers).json()
    assert me["data"]["role"] == "librarian", me

    # 4. 活动列表 + 状态统计
    acts = client.get("/api/v1/activities", params={"page": 1, "page_size": 5}).json()
    assert acts["code"] == 0 and "list" in acts["data"], acts
    stats = client.get("/api/v1/activities/stats").json()
    assert stats["code"] == 0, stats

    # 5. 新建活动（草稿）→ 非法流转被拦截（1005）→ 合法流转成功
    created = client.post(
        "/api/v1/activities",
        headers=headers,
        json={
            "title": "冒烟测试活动",
            "category": "reading_share",
            "start_at": "2026-11-01T14:00:00+08:00",
            "end_at": "2026-11-01T17:00:00+08:00",
            "capacity": 30,
        },
    ).json()
    assert created["code"] == 0, created
    aid = created["data"]["activity_id"]
    assert created["data"]["status"] == "draft"

    bad = client.post(f"/api/v1/activities/{aid}/status", headers=headers, json={"target_status": "finished"}).json()
    assert bad["code"] == 1005, bad

    good = client.post(f"/api/v1/activities/{aid}/status", headers=headers, json={"target_status": "published"}).json()
    assert good["code"] == 0 and good["data"]["status"] == "published", good

    # 6. 图书：列表 / ISBN 扫码 / AI 解读
    books = client.get("/api/v1/books", params={"page_size": 3}).json()
    assert books["code"] == 0 and books["data"]["list"], books
    isbn = books["data"]["list"][0]["isbn"]
    scan = client.get(f"/api/v1/books/isbn/{isbn}").json()
    assert scan["code"] == 0, scan
    summary = client.post(f"/api/v1/books/{scan['data']['book_id']}/ai-summary", headers=headers).json()
    assert summary["code"] == 0 and summary["data"]["ai_summary"], summary

    # 7. AI 对话（非流式）
    chat = client.post(
        "/api/v1/ai/chat",
        headers=headers,
        json={"message": "这本书适合什么基础的人读？", "scene": "qa"},
    ).json()
    assert chat["code"] == 0 and chat["data"]["message"]["role"] == "assistant", chat

    # 8. 漂流池 + 流转记录
    pool = client.get("/api/v1/drift/books").json()
    assert pool["code"] == 0, pool
    records = client.get("/api/v1/drift/records").json()
    assert records["code"] == 0, records

    print("冒烟测试全部通过 ✅")


if __name__ == "__main__":
    test_smoke()
