"""智能体链路冒烟测试。

真实模型 key 可能失效、可能没余额，但「模型一旦可用，工具调用链路是通的」这件事
必须能被验证。所以这里用一个脚本化的假模型驱动运行时：它按预设返回 tool_calls，
走的是和真实模型完全相同的代码路径（runtime 循环 → 工具执行 → 结果回灌 → 校验）。

覆盖：
1. 工具层能查真实数据
2. ReAct 循环真的会调工具、并把结果用于最终回答
3. 模型编造 book_id 时会被剔除
4. 四个场景的降级路径都能出结果
5. 访客边界与权限校验
6. 运行记录落库

用法： python tests/test_agent_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.agents import fallback, runtime, scenes, tools  # noqa: E402
from app.agents.tools import SCENE_COMPANION, SCENE_MATCH, ToolContext  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.models import AgentRun, Book, User  # noqa: E402
from app.services import llm_client  # noqa: E402
from app.services.llm_client import ChatResult, ToolCall  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"❌ {label}")
    PASSED += 1
    print(f"  ✅ {label}")


class FakeLLM:
    """按脚本返回预设响应，用于驱动 runtime 而不真正联网。"""

    def __init__(self, script: list[ChatResult]):
        self.script = script
        self.index = 0
        self.seen_messages: list[list[dict]] = []

    def __call__(self, messages, tools=None, **kwargs):
        self.seen_messages.append(list(messages))
        item = self.script[min(self.index, len(self.script) - 1)]
        self.index += 1
        return item


def with_fake_model(script: list[ChatResult]):
    """上下文管理器：把模型替换成脚本，并让 is_available 返回 True。"""
    class _Ctx:
        def __enter__(self):
            self._orig_chat = llm_client.chat
            self._orig_available = llm_client.is_available
            self.fake = FakeLLM(script)
            llm_client.chat = self.fake  # type: ignore[assignment]
            llm_client.is_available = lambda: (True, "")  # type: ignore[assignment]
            return self.fake

        def __exit__(self, *exc):
            llm_client.chat = self._orig_chat  # type: ignore[assignment]
            llm_client.is_available = self._orig_available  # type: ignore[assignment]
            return False

    return _Ctx()


def main() -> None:
    db = SessionLocal()
    try:
        student = db.scalars(select(User).where(User.role == UserRole.STUDENT.value, User.is_deleted.is_(False))).first()
        admin = db.scalars(select(User).where(User.role == UserRole.SUPER_ADMIN.value)).first()
        check(student is not None and admin is not None, "存在学生与管理员账号")

        print("\n=== 1. 工具层 ===")
        ctx = ToolContext(db=db, user_id=student.user_id, scene=SCENE_MATCH)
        found = tools.dispatch("search_books", {"keyword": "数学", "limit": 3}, ctx)
        check(found["ok"] and found["count"] > 0, f"search_books 命中 {found.get('count')} 本")

        first = found["books"][0]
        detail = tools.dispatch("get_book", {"title_or_isbn": first["title"]}, ctx)
        check(detail["ok"] and detail["book"]["book_id"] == first["book_id"], "get_book 能按书名取到同一本书")

        profile = tools.dispatch("user_profile", {}, ctx)
        check(profile["ok"], "user_profile 能取到当前读者画像")

        blocked = tools.dispatch("activity_audience", {"activity_id": "x"}, ctx)
        check(not blocked["ok"], "未声明该场景的工具会被拒绝调用")

        bad = tools.dispatch("search_books", {}, ctx)
        check(not bad["ok"], "参数缺失时返回错误而不是抛异常")
        check(len(ctx.trace) == 5, f"工具调用轨迹全部记录（{len(ctx.trace)} 条）")

        print("\n=== 2. ReAct 循环（假模型驱动）===")
        # 第一轮：模型决定查书；第二轮：拿到结果后给最终答复
        script = [
            ChatResult(
                tool_calls=[ToolCall(id="c1", name="search_books", arguments={"keyword": "数学", "limit": 2})],
                tokens=120,
                model="fake-model",
            ),
            ChatResult(
                content='{"strategy":"keyword","items":[{"book_id":"__FROM_TOOL__","title":"x","reason":"同分类","evidence":["命中数学"]}],"explanation":"按关键词"}',
                tokens=80,
                model="fake-model",
            ),
        ]
        ctx2 = ToolContext(db=db, user_id=student.user_id, scene=SCENE_MATCH)
        with with_fake_model(script) as fake:
            result = runtime.run(SCENE_MATCH, "测试提示词", "找数学书", ctx2, expect_json=True)
            check(fake.index == 2, "模型被调用了两轮（工具一次 + 收尾一次）")
        check(result.steps == 2, f"运行时记录 {result.steps} 步")
        check(len(result.tool_trace) == 1, "运行轨迹里有一次工具调用")
        check(result.tool_trace[0]["tool"] == "search_books", "轨迹记录了正确的工具名")
        check(result.tokens == 200, f"token 累计 {result.tokens}")
        # 第二轮的上下文里应当已经包含工具结果
        second_round = fake.seen_messages[1]
        check(any(msg.get("role") == "tool" for msg in second_round), "工具结果被回灌进第二轮上下文")

        print("\n=== 3. 防编造：模型给出不存在的书 ===")
        bogus = [
            ChatResult(
                content='{"strategy":"profile","items":[{"book_id":"bok_不存在","title":"编造的书","reason":"理由","evidence":[]}],"explanation":"x"}',
                tokens=50,
                model="fake-model",
            )
        ]
        with with_fake_model(bogus):
            res = scenes.run_match(db, student.user_id, "student", {"query": "随便", "limit": 3})
        check(res["degraded"], "全部书目未通过核对时转为降级")
        check(all(item["book_id"] != "bok_不存在" for item in res["result"]["items"]), "编造的 book_id 没有出现在结果里")

        print("\n=== 4. 正常场景（模型可用）===")
        real_book = db.scalars(select(Book).where(Book.is_deleted.is_(False))).first()
        good = [
            ChatResult(
                tool_calls=[ToolCall(id="c1", name="user_profile", arguments={})],
                tokens=100,
                model="fake-model",
            ),
            ChatResult(
                content=f'{{"strategy":"profile","items":[{{"book_id":"{real_book.book_id}","title":"{real_book.title}","reason":"与你常读方向一致","evidence":["你借过 3 本同类"]}}],"explanation":"按画像"}}',
                tokens=90,
                model="fake-model",
            ),
        ]
        with with_fake_model(good):
            res = scenes.run_match(db, student.user_id, "student", {"query": "", "limit": 3})
        check(not res["degraded"], "模型可用时状态为 success")
        check(len(res["result"]["items"]) == 1, "返回了通过核对的书")
        check(res["result"]["items"][0]["title"] == real_book.title, "书名以数据库为准，不用模型给的")
        check(res["steps"] == 2 and res["tokens"] == 190, "步数与 token 统计正确")

        print("\n=== 5. 降级路径（无模型）===")
        no_model = [
            ChatResult(content="", tokens=0, model="fake-model", finish_reason="error"),
        ]
        with with_fake_model(no_model):
            pass  # 仅确认上下文管理器可退出

        saved = llm_client.is_available
        llm_client.is_available = lambda: (False, "测试：模型不可用")  # type: ignore[assignment]
        try:
            m = scenes.run_match(db, student.user_id, "student", {"query": "", "limit": 3})
            check(m["degraded"] and len(m["result"]["items"]) > 0, "匹配降级仍返回结果")

            v = scenes.run_match(db, "", "visitor", {"query": "数学", "limit": 2})
            check(v["degraded"] and "访客" in v["degraded_reason"], "访客被打上专属降级原因")

            i = scenes.run_intake(db, admin.user_id, {"isbn": "9787115428028"})
            check("book" in i["result"], "录书降级返回结构化的书")

            o = scenes.run_outreach(db, admin.user_id, {"topic": "读书"})
            check(o["result"].get("push_text") is not None, "触达降级返回文案")

            c = scenes.run_companion(db, student.user_id, "student", {"question": "数学书在哪"})
            check(bool(c["result"].get("answer")), "伴读降级返回回答")
        finally:
            llm_client.is_available = saved  # type: ignore[assignment]

        print("\n=== 6. 落库与统计 ===")
        before = db.scalar(select(func.count()).select_from(AgentRun)) or 0
        db.add(
            AgentRun(
                scene="match",
                user_id=student.user_id,
                user_name=student.name,
                input_summary="测试",
                status="success",
                steps=2,
                tool_calls=[{"tool": "search_books"}],
                tokens=100,
                model="fake-model",
                elapsed_ms=123,
                output_summary="推荐 1 本",
            )
        )
        db.commit()
        after = db.scalar(select(func.count()).select_from(AgentRun)) or 0
        check(after == before + 1, "运行记录可以写入 agent_runs")

        print(f"\n冒烟测试全部通过 ✅（{PASSED} 项）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
