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
    assert me["data"]["name"] == "图书馆老师" and me["data"]["email"] == "", me
    assert me["data"]["created_at"].endswith("+08:00"), me

    # 4. 活动列表 + 状态统计
    acts = client.get("/api/v1/activities", headers=headers, params={"page": 1, "page_size": 5}).json()
    assert acts["code"] == 0 and "list" in acts["data"], acts
    stats = client.get("/api/v1/activities/stats").json()
    assert stats["code"] == 0, stats

    # 5. 新建活动（草稿）→ 非法流转被拦截（1005）→ 合法流转成功
    created_response = client.post(
        "/api/v1/activities",
        headers=headers,
        json={
            "title": "冒烟测试活动",
            "category": "reading_share",
            "start_at": "2026-11-01T14:00:00+08:00",
            "end_at": "2026-11-01T17:00:00+08:00",
            "capacity": 30,
        },
    )
    assert created_response.status_code == 201, created_response.json()
    created = created_response.json()
    assert created["code"] == 0, created
    aid = created["data"]["activity_id"]
    assert created["data"]["status"] == "draft"
    assert created["data"]["created_at"].endswith("+08:00")
    assert created["data"]["start_at"] == "2026-11-01T14:00:00+08:00", created
    invalid_create = client.post(
        "/api/v1/activities",
        headers=headers,
        json={"title": "身份注入", "category": "other", "start_at": "2026-12-02T14:00:00+08:00", "organizer_id": "usr_fake"},
    )
    assert invalid_create.status_code == 422 and invalid_create.json()["code"] == 1001, invalid_create.json()

    bad = client.post(f"/api/v1/activities/{aid}/status", headers=headers, json={"target_status": "finished"}).json()
    assert bad["code"] == 1005, bad

    good = client.post(f"/api/v1/activities/{aid}/status", headers=headers, json={"target_status": "published"}).json()
    assert good["code"] == 0 and good["data"]["status"] == "published", good

    student_headers = {"Authorization": f"Bearer {_login('2025211987')}"}
    draft = client.post(
        "/api/v1/activities",
        headers=headers,
        json={"title": "学生不可见草稿", "category": "other", "start_at": "2026-12-01T14:00:00+08:00"},
    ).json()
    hidden_draft = client.get(f"/api/v1/activities/{draft['data']['activity_id']}", headers=student_headers)
    assert hidden_draft.status_code == 404, hidden_draft.json()
    signup = client.post(f"/api/v1/activities/{aid}/signups", headers=student_headers, json={}).json()
    assert signup["code"] == 0 and signup["data"]["status"] == "approved", signup
    duplicate = client.post(f"/api/v1/activities/{aid}/signups", headers=student_headers, json={})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == 1005, duplicate.json()

    # 6. 图书：列表 / ISBN 扫码 / AI 解读
    books = client.get("/api/v1/books", params={"page_size": 100}).json()
    assert books["code"] == 0 and books["data"]["list"], books
    isbn = next(book["isbn"] for book in books["data"]["list"] if book["isbn"])
    scan = client.get(f"/api/v1/books/isbn/{isbn}").json()
    assert scan["code"] == 0, scan
    summary = client.post(f"/api/v1/books/{scan['data']['book_id']}/ai-summary", headers=headers).json()
    assert summary["code"] == 0 and summary["data"]["ai_summary"], summary
    for title in ("无 ISBN 测试书一", "无 ISBN 测试书二"):
        created_book = client.post(
            "/api/v1/books",
            headers=headers,
            json={"isbn": "", "title": title, "author": "测试作者"},
        )
        assert created_book.status_code == 201 and created_book.json()["data"]["publish_date"] is None, created_book.json()

    # 7. AI 对话（非流式）
    chat = client.post(
        "/api/v1/ai/chat",
        headers=headers,
        json={"content": "这本书适合什么基础的人读？", "scene": "qa"},
    ).json()
    assert chat["code"] == 0 and chat["data"]["message_id"] and chat["data"]["content"], chat

    # 8. 漂流池 + 流转记录
    pool = client.get("/api/v1/drift/books").json()
    assert pool["code"] == 0, pool
    records = client.get("/api/v1/drift/records").json()
    assert records["code"] == 0, records
    manual_drift = client.post(
        "/api/v1/drift/books",
        headers=student_headers,
        json={"isbn": "", "title": "无 ISBN 漂流书", "author": "测试作者", "location": "图书馆一层大厅"},
    )
    assert manual_drift.status_code == 200 and manual_drift.json()["data"]["drift_id"], manual_drift.json()

    print("冒烟测试全部通过 ✅")


if __name__ == "__main__":
    test_smoke()
