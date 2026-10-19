"""第二阶段冒烟测试：权限矩阵 + 审批流 + 电子证书 + 活动总结推送。

运行： backend/.venv/Scripts/python.exe tests/test_api_smoke.py
前提： 先跑过 scripts/seed.py（测试依赖演示账号与演示活动）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    Activity,
    ActivitySignup,
    ActivitySummary,
    Certificate,
    Notification,
    PermissionLog,
)
from app.main import app  # noqa: E402

client = TestClient(app)
PASSWORD = "123456"
PREFIX = "[SMOKE]"


def login(student_no: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"student_no": student_no, "password": PASSWORD})
    body = resp.json()
    assert body["code"] == 0, f"登录失败 {student_no}: {body}"
    return body["data"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def expect(resp, code: int, label: str):
    body = resp.json()
    assert body["code"] == code, f"{label} 期望 code={code}，实际 HTTP {resp.status_code} {body}"
    return body


def cleanup() -> None:
    """清理测试产生的数据，保持演示库干净。"""
    db = SessionLocal()
    try:
        # 按标题前缀兜底清理测试总结（含推送消息），避免历史残留污染演示
        stray = db.scalars(select(ActivitySummary).where(ActivitySummary.title.like(f"{PREFIX}%"))).all()
        for summary in stray:
            db.execute(delete(Notification).where(Notification.ref_id == summary.summary_id))
            db.delete(summary)
        acts = db.scalars(select(Activity).where(Activity.title.like(f"{PREFIX}%"))).all()
        if acts:
            ids = [row.activity_id for row in acts]
            for row in acts:
                row.is_deleted = True
            summaries = db.scalars(select(ActivitySummary).where(ActivitySummary.activity_id.in_(ids))).all()
            for summary in summaries:
                db.execute(delete(Notification).where(Notification.ref_id == summary.summary_id))
            db.execute(delete(ActivitySummary).where(ActivitySummary.activity_id.in_(ids)))
            db.execute(delete(ActivitySignup).where(ActivitySignup.activity_id.in_(ids)))
            db.execute(delete(Certificate).where(Certificate.activity_id.in_(ids)))
        db.execute(delete(PermissionLog).where(PermissionLog.remark.like(f"{PREFIX}%")))
        db.commit()
    finally:
        db.close()


def main() -> None:
    print("=== 1. 健康检查与登录 ===")
    assert client.get("/api/v1/health").json()["code"] == 0
    accounts = {
        "super": login("admin"),
        "admin": login("T2009"),
        "admin_no_review": login("T2010"),
        "alice": login("2025211987"),
        "wanbei": login("2025211995"),
        "bob": login("2025211996"),
        "guest": login("guest"),
    }
    for key, data in accounts.items():
        print(f"  {key:<16} role={data['user']['role']:<12} 权限数={len(data['user']['permissions'])}")

    tokens = {key: data["token"] for key, data in accounts.items()}
    assert "system:permission" in accounts["super"]["user"]["permissions"]
    assert "activity:review" not in accounts["admin_no_review"]["user"]["permissions"], "T2010 的审批权应被收回"
    assert "activity:create" in accounts["wanbei"]["user"]["permissions"], "万贝应有申办权"
    assert "activity:create" not in accounts["bob"]["user"]["permissions"], "Bob 不应有申办权"
    assert "activity:signup" not in accounts["guest"]["user"]["permissions"], "访客不应能报名"
    print("  ✅ 角色默认权限与按人收回/授予均生效")

    print("=== 2. 访客只读边界 ===")
    expect(client.get("/api/v1/activities"), 0, "匿名浏览活动")
    expect(client.post("/api/v1/activities/act_not_exist/signups", json={}, headers=auth(tokens["guest"])), 1003, "访客报名")
    expect(client.get("/api/v1/drift/books", headers=auth(tokens["guest"])), 0, "访客看漂流池")
    expect(client.post("/api/v1/drift/books", json={"isbn": "9787115428028"}, headers=auth(tokens["guest"])), 1003, "访客上架")
    rec = client.post("/api/v1/books/recommend", json={"limit": 3, "extra_prompt": "想读点历史"}, headers=auth(tokens["guest"]))
    rec_body = expect(rec, 0, "访客 AI 推荐")
    assert rec_body["data"]["degraded"] is True and rec_body["data"]["model"] == "mock", rec_body
    print("  ✅ 访客可浏览/看漂流/用 Mock 推荐，不能报名、不能上架")

    print("=== 3. 学生申办 → 提交 → 管理员审批定级 ===")
    expect(
        client.post("/api/v1/activities", json={"title": f"{PREFIX}bob 越权申办", "start_at": "2026-12-01T14:00:00+08:00"},
                    headers=auth(tokens["bob"])),
        1003,
        "无申办权学生创建活动",
    )
    created = client.post(
        "/api/v1/activities",
        json={
            "title": f"{PREFIX}摄影展",
            "category": "exhibition",
            "start_at": "2026-12-05T14:00:00+08:00",
            "end_at": "2026-12-05T17:00:00+08:00",
            "signup_start_at": "2026-11-01T00:00:00+08:00",
            "signup_end_at": "2026-12-01T00:00:00+08:00",
            "need_certificate": True,
        },
        headers=auth(tokens["wanbei"]),
    )
    act = expect(created, 0, "学生会成员申办活动")["data"]
    assert act["status"] == "draft" and act["level"] == "none"

    expect(client.post(f"/api/v1/activities/{act['activity_id']}/submit", json={}, headers=auth(tokens["wanbei"])), 0, "提交审批")

    # 无审批权的管理员不能审批
    expect(
        client.post(f"/api/v1/activities/{act['activity_id']}/review", json={"approved": True, "level": "school"},
                    headers=auth(tokens["admin_no_review"])),
        1003,
        "无审批权管理员审批",
    )
    # 审批通过必须定级
    expect(
        client.post(f"/api/v1/activities/{act['activity_id']}/review", json={"approved": True},
                    headers=auth(tokens["admin"])),
        1001,
        "审批未定级",
    )
    reviewed = expect(
        client.post(f"/api/v1/activities/{act['activity_id']}/review",
                    json={"approved": True, "level": "school", "comment": f"{PREFIX}同意"}, headers=auth(tokens["admin"])),
        0,
        "审批通过",
    )
    assert reviewed["data"]["status"] == "published" and reviewed["data"]["level"] == "school", reviewed
    print("  ✅ 未授权学生被拦、无审批权管理员被拦、审批通过自动定级并发布")

    # 审批人不能审批自己的活动
    own = client.post(
        "/api/v1/activities",
        json={"title": f"{PREFIX}管理员自己的活动", "start_at": "2026-12-08T14:00:00+08:00"},
        headers=auth(tokens["admin"]),
    ).json()["data"]
    client.post(f"/api/v1/activities/{own['activity_id']}/submit", json={}, headers=auth(tokens["admin"]))
    expect(
        client.post(f"/api/v1/activities/{own['activity_id']}/review", json={"approved": True, "level": "college"},
                    headers=auth(tokens["admin"])),
        1003,
        "自审自批",
    )
    expect(client.delete(f"/api/v1/activities/{own['activity_id']}", headers=auth(tokens["admin"])), 1005, "待审批活动不可删除")
    expect(client.post(f"/api/v1/activities/{own['activity_id']}/status", json={"target_status": "cancelled"},
                       headers=auth(tokens["admin"])), 0, "取消待审批活动")
    expect(client.delete(f"/api/v1/activities/{own['activity_id']}", headers=auth(tokens["admin"])), 0, "删除已取消活动")
    print("  ✅ 审批人不能审批自己申办的活动")

    print("=== 4. 系统管理员分配权限 ===")
    bob_id = accounts["bob"]["user"]["user_id"]
    expect(
        client.patch(f"/api/v1/users/{bob_id}/permissions", json={"grant": ["activity:create"], "remark": f"{PREFIX}学生会"},
                     headers=auth(tokens["super"])),
        0,
        "授予申办权",
    )
    bob_login = login("2025211996")
    assert "activity:create" in bob_login["user"]["permissions"]
    bob_act = client.post(
        "/api/v1/activities",
        json={"title": f"{PREFIX}bob 获权后申办", "start_at": "2026-12-10T14:00:00+08:00"},
        headers=auth(tokens["bob"]),
    )
    expect(bob_act, 0, "授权后申办")

    expect(
        client.patch(f"/api/v1/users/{bob_id}/permissions", json={"revoke": ["activity:create"], "remark": f"{PREFIX}收回"},
                     headers=auth(tokens["super"])),
        0,
        "收回申办权",
    )
    expect(
        client.post("/api/v1/activities", json={"title": f"{PREFIX}收回后再申办", "start_at": "2026-12-11T14:00:00+08:00"},
                    headers=auth(tokens["bob"])),
        1003,
        "收回后申办",
    )
    # 自我提权 / 授予超级权限都应被拒
    expect(client.patch(f"/api/v1/users/{accounts['super']['user']['user_id']}/permissions",
                        json={"grant": ["system:permission"]}, headers=auth(tokens["super"])), 1003, "修改自己权限")
    expect(client.patch(f"/api/v1/users/{bob_id}/permissions", json={"grant": ["system:permission"]},
                        headers=auth(tokens["super"])), 1003, "下放 system:permission")
    print("  ✅ 授权即时生效、收回即时失效、自提权与越权下放被拒")

    print("=== 5. 电子证书 ===")
    mine = expect(client.get("/api/v1/certificates/mine", headers=auth(tokens["alice"])), 0, "我的证书")
    assert mine["data"]["total"] >= 1, mine
    cert = mine["data"]["list"][0]
    pdf = client.get(f"/api/v1/certificates/{cert['certificate_id']}/pdf", headers=auth(tokens["alice"]))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code
    print(f"  PDF 大小 {len(pdf.content) / 1024:.1f} KB，开头 {pdf.content[:4]!r}")

    verify_body = expect(client.get(f"/api/v1/certificates/verify/{cert['verify_code']}"), 0, "公开验真")
    assert verify_body["data"]["valid"] is True and "*" in verify_body["data"]["holder_name"], verify_body
    expect(client.get(f"/api/v1/certificates/{cert['certificate_id']}/pdf", headers=auth(tokens["bob"])), 1003, "下载他人证书")
    expect(client.post(f"/api/v1/activities/{cert['activity_id']}/certificates", json={}, headers=auth(tokens["alice"])), 1003, "学生颁发证书")
    issued = expect(
        client.post(f"/api/v1/activities/{cert['activity_id']}/certificates",
                    json={"only_checked_in": True, "certificate_name": "荣誉证书"}, headers=auth(tokens["admin"])),
        0,
        "管理员批量颁发",
    )
    print(f"  批量颁发：新发 {issued['data']['issued']} 张，跳过 {issued['data']['skipped']} 张（已有证书）")
    print("  ✅ 证书 PDF 可下载、公开验真、越权访问被拦、批量颁发幂等")

    print("=== 6. 活动总结与推送 ===")
    # 自建一条活动并走完生命周期，保证测试可重复运行（不污染演示数据）
    wrap = expect(
        client.post("/api/v1/activities",
                    json={"title": f"{PREFIX}总结推送验证活动", "start_at": "2026-12-01T19:00:00+08:00",
                          "category": "reading_share", "need_certificate": True},
                    headers=auth(tokens["admin"])),
        0,
        "创建总结用活动",
    )["data"]
    wrap_id = wrap["activity_id"]
    expect(client.post(f"/api/v1/activities/{wrap_id}/submit", json={}, headers=auth(tokens["admin"])), 0, "提交审批")
    expect(client.post(f"/api/v1/activities/{wrap_id}/review",
                       json={"approved": True, "level": "college", "comment": f"{PREFIX}同意"},
                       headers=auth(tokens["super"])), 0, "审批通过")
    for target_status in ("signup_closed", "ongoing", "finished"):
        expect(client.post(f"/api/v1/activities/{wrap_id}/status", json={"target_status": target_status},
                           headers=auth(tokens["admin"])), 0, f"流转到 {target_status}")

    draft = expect(
        client.post(f"/api/v1/activities/{wrap_id}/summary",
                    json={"title": f"{PREFIX}活动回顾", "content": "这是一次很成功的活动，共 60 人参与。", "images": []},
                    headers=auth(tokens["admin"])),
        0,
        "撰写总结",
    )
    summary_id = draft["data"]["summary_id"]
    published = expect(
        client.post(f"/api/v1/summaries/{summary_id}/publish", json={"target_roles": ["student", "visitor"]},
                    headers=auth(tokens["admin"])),
        0,
        "发布总结",
    )
    assert published["data"]["pushed_to"] == ["student", "visitor"], published
    feed = expect(client.get("/api/v1/summaries", headers=auth(tokens["guest"])), 0, "访客看总结流")
    assert any(item["summary_id"] == summary_id for item in feed["data"]["list"]), "访客应能看到已发布总结"
    notes = expect(client.get("/api/v1/notifications", headers=auth(tokens["guest"])), 0, "访客消息")
    assert any(n["ref_id"] == summary_id for n in notes["data"]["list"]), "访客应收到推送"
    # 已发布的总结不能重复发布
    expect(client.post(f"/api/v1/summaries/{summary_id}/publish", json={"target_roles": ["student"]},
                       headers=auth(tokens["admin"])), 1005, "重复发布总结")
    print("  ✅ 总结发布后进入全站流，访客也能收到推送，且不可重复发布")

    print("=== 7. 运营状态流转 ===")
    expect(client.post(f"/api/v1/activities/{act['activity_id']}/status", json={"target_status": "finished"},
                       headers=auth(tokens["admin"])), 1005, "非法流转")
    expect(client.post(f"/api/v1/activities/{act['activity_id']}/status", json={"target_status": "signup_closed"},
                       headers=auth(tokens["admin"])), 0, "合法流转")
    print("  ✅ 状态机拦截非法流转")

    print("\n冒烟测试全部通过 ✅")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
