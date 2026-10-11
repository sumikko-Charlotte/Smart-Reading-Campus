"""接口冒烟测试：python -m pytest tests -q  （或直接 python tests/test_api_smoke.py）

覆盖：健康检查 → 登录 → 活动列表/新建/状态机 → 图书列表/扫码 → AI 对话 → 漂流池
模型请求使用隔离的 HTTP 响应桩，可离线跑通。
"""
import json
import os
import sys
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402
from app.db.models import Book  # noqa: E402
from app.services import llm_service  # noqa: E402

client = TestClient(app)


def _login(student_no: str = "T2009") -> str:
    resp = client.post("/api/v1/auth/login", json={"student_no": student_no, "password": "123456"})
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]["token"]


@patch.object(llm_service.settings, "LLM_ENABLED", True)
def test_smoke() -> None:
    mock_recommendation_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "choices": [{"message": {"content": '{"reasons":["适合入门阅读"]}'}}],
            "usage": {"total_tokens": 27},
        },
    )
    mock_text_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"choices": [{"message": {"content": "基于图书信息生成的测试模型回答。"}}], "usage": {"total_tokens": 19}},
    )

    def mock_recommendation_post(*args, **kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        candidates_json = prompt.split("候选书目：", 1)[1]
        candidates = json.loads(candidates_json)
        result = {
            "reasons": [
                f"结合{item['title']}主题生成的测试理由"
                for item in candidates
            ]
        }
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}],
                "usage": {"total_tokens": 27},
            },
        )
    test_book = cast(Book, SimpleNamespace(
        book_id="bok_test",
        title="测试书目",
        author="测试作者",
        category="文学",
        tags=["入门"],
        summary="测试简介",
        borrow_count=12,
    ))
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post", return_value=mock_recommendation_response
    ) as post:
        reasons, tokens = llm_service.recommend_reasons([test_book], "适合入门", 1)
        assert reasons == {"bok_test": "适合入门阅读"}, reasons
        assert tokens == 27, tokens
        assert post.call_args.args[0] == "https://api.deepseek.com/v1/chat/completions"
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-only-key"
        assert post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}

    with patch.object(llm_service.settings, "LLM_API_KEY", ""):
        try:
            llm_service.chat_reply("qa", "no preset please", None)
        except llm_service.LLMServiceError as exc:
            assert "未配置 LLM_API_KEY" in str(exc)
        else:
            raise AssertionError("missing API key must not return a Mock answer")

    upstream_response = httpx.Response(402, request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"))
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post",
        side_effect=httpx.HTTPStatusError("402", request=upstream_response.request, response=upstream_response),
    ):
        try:
            llm_service.chat_reply("qa", "check billing error", None)
        except llm_service.LLMServiceError as exc:
            assert "余额不足" in str(exc)
        else:
            raise AssertionError("HTTP 402 must map to the insufficient-balance message")

    with patch.object(llm_service.settings, "LLM_ENABLED", False), patch(
        "app.services.llm_service.httpx.post", side_effect=AssertionError("disabled LLM must not make a request")
    ):
        try:
            llm_service.chat_reply("qa", "billing is disabled", None)
        except llm_service.LLMServiceError as exc:
            assert "LLM_ENABLED=true" in str(exc)
        else:
            raise AssertionError("disabled LLM must not return a preset answer")

    with patch.object(llm_service.settings, "LLM_ENABLED", True), patch.object(
        llm_service.settings, "LLM_API_KEY", "test-only-key"
    ), patch("app.services.llm_service.httpx.post", side_effect=AssertionError("empty candidates must not call model")):
        empty_reasons, empty_tokens = llm_service.recommend_reasons([], "any", 1)
        assert empty_reasons == {} and empty_tokens == 0

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

    # 5.1 POST /publish：不带请求体与带空对象都应可用（规范 7.5）
    draft_plain = client.post(
        "/api/v1/activities",
        headers=headers,
        json={"title": "冒烟测试-发布用草稿", "category": "other", "start_at": "2026-11-05T14:00:00+08:00"},
    ).json()
    plain_id = draft_plain["data"]["activity_id"]
    pub = client.post(f"/api/v1/activities/{plain_id}/publish", headers=headers)
    assert pub.status_code == 200 and pub.json()["data"]["status"] == "published", pub.json()
    assert pub.json()["data"]["published_at"], pub.json()
    pub_repeat = client.post(f"/api/v1/activities/{plain_id}/publish", headers=headers, json={})
    assert pub_repeat.status_code == 409 and pub_repeat.json()["code"] == 1005, pub_repeat.json()

    # 5.2 需要证书但未指定模板 → 发布被拒（规范 7.2 第 2 条）
    cert_draft = client.post(
        "/api/v1/activities",
        headers=headers,
        json={
            "title": "冒烟测试-缺证书模板",
            "category": "lecture",
            "start_at": "2026-11-06T14:00:00+08:00",
            "need_certificate": True,
        },
    ).json()
    cert_pub = client.post(f"/api/v1/activities/{cert_draft['data']['activity_id']}/publish", headers=headers)
    assert cert_pub.status_code == 422 and cert_pub.json()["code"] == 1001, cert_pub.json()

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
    my_activities = client.get("/api/v1/activities/mine", headers=student_headers).json()
    assert my_activities["code"] == 0 and my_activities["data"]["total"] >= 1, my_activities
    my_activity = next(item for item in my_activities["data"]["list"] if item["activity_id"] == aid)
    assert my_activity["signup_status"] == "approved" and my_activity["checked_in_at"] is None, my_activity
    duplicate = client.post(f"/api/v1/activities/{aid}/signups", headers=student_headers, json={})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == 1005, duplicate.json()

    # 6. 图书：列表 / ISBN 扫码 / AI 解读
    books = client.get("/api/v1/books", params={"page_size": 100}).json()
    assert books["code"] == 0 and books["data"]["list"], books
    isbn = next(book["isbn"] for book in books["data"]["list"] if book["isbn"])
    scan = client.get(f"/api/v1/books/isbn/{isbn}").json()
    assert scan["code"] == 0, scan
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post", return_value=mock_text_response
    ):
        summary = client.post(f"/api/v1/books/{scan['data']['book_id']}/ai-summary", headers=headers).json()
    assert summary["code"] == 0 and summary["data"]["ai_summary"], summary
    for title in ("无 ISBN 测试书一", "无 ISBN 测试书二"):
        created_book = client.post(
            "/api/v1/books",
            headers=headers,
            json={"isbn": "", "title": title, "author": "测试作者"},
        )
        assert created_book.status_code == 201 and created_book.json()["data"]["publish_date"] is None, created_book.json()

    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post", side_effect=mock_recommendation_post
    ):
        recommendation = client.post(
            "/api/v1/books/recommend",
            headers=headers,
            json={"scene": "recommend", "limit": 2, "extra_prompt": "适合入门"},
        )
    recommendation_body = recommendation.json()
    assert recommendation.status_code == 200 and recommendation_body["code"] == 0, recommendation_body
    assert recommendation_body["data"]["items"], recommendation_body
    conversation = client.get(
        f"/api/v1/ai/conversations/{recommendation_body['data']['conversation_id']}",
        headers=headers,
    ).json()
    assert conversation["data"]["messages"][0]["tokens"] == 27, conversation
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post", side_effect=llm_service.httpx.ConnectError("test connection failure")
    ):
        unavailable = client.post(
            "/api/v1/books/recommend",
            headers=headers,
            json={"scene": "recommend", "limit": 1},
        )
    assert unavailable.status_code == 503 and unavailable.json()["code"] == 5000, unavailable.json()
    assert "test connection failure" not in unavailable.json()["message"], unavailable.json()

    # 7. AI 对话（非流式）
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch(
        "app.services.llm_service.httpx.post", return_value=mock_text_response
    ):
        chat = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"content": "这本书适合什么基础的人读？", "scene": "qa"},
        ).json()
    assert chat["code"] == 0 and chat["data"]["message_id"] and chat["data"]["content"], chat
    with patch.object(llm_service.settings, "LLM_API_KEY", "" ):
        chat_unconfigured = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"content": "不要返回预设回答", "scene": "qa"},
        )
    assert chat_unconfigured.status_code == 503, chat_unconfigured.json()
    assert "未配置 LLM_API_KEY" in chat_unconfigured.json()["message"], chat_unconfigured.json()
    with patch.object(llm_service.settings, "LLM_API_KEY", "test-only-key"), patch.object(
        llm_service.settings, "LLM_ENABLED", False
    ):
        chat_disabled = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"content": "开关关闭时不应调用模型", "scene": "qa"},
        )
    assert chat_disabled.status_code == 503, chat_disabled.json()
    assert "AI 调用已关闭" in chat_disabled.json()["message"], chat_disabled.json()

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
