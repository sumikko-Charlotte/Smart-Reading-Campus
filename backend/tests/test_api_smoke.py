"""第二阶段冒烟测试：权限矩阵 + 审批流 + 电子证书 + 活动总结推送。

运行： backend/.venv/Scripts/python.exe tests/test_api_smoke.py
隔离： 每次在 tests/.test_smoke.db 建一个全新库并灌 seed 数据，
      不碰演示库（演示库随时会被人从界面改动，断言依赖它就会时好时坏）。
"""
import os
import sys
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / ".test_smoke.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

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
    NotificationRead,
    PermissionLog,
    PermissionRequest,
    User,
)
from app.main import app  # noqa: E402
from scripts import seed as seed_script  # noqa: E402

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
        summary_ids = [
            row.summary_id
            for row in db.scalars(select(ActivitySummary).where(ActivitySummary.title.like(f"{PREFIX}%"))).all()
        ]
        acts = db.scalars(select(Activity).where(Activity.title.like(f"{PREFIX}%"))).all()
        act_ids = [row.activity_id for row in acts]
        test_users = db.scalars(select(User).where(User.student_no.like("SMOKE%"))).all()
        user_ids = [row.user_id for row in test_users]
        # 申请单对应的待审批消息发给了系统管理员（user_id 不是测试账号），
        # 必须按 ref_id 清，否则每跑一次就给管理员留一条孤儿待办
        request_ids = (
            [
                row.request_id
                for row in db.scalars(
                    select(PermissionRequest).where(PermissionRequest.user_id.in_(user_ids))
                ).all()
            ]
            if user_ids
            else []
        )

        # 消息与已读回执：按 ref_id（总结 / 活动 / 申请单）和收件人两种口径一起清
        notif_ids: set[str] = set()
        if summary_ids:
            notif_ids |= set(
                db.scalars(select(Notification.notification_id).where(Notification.ref_id.in_(summary_ids))).all()
            )
        if act_ids:
            notif_ids |= set(
                db.scalars(select(Notification.notification_id).where(Notification.ref_id.in_(act_ids))).all()
            )
        if request_ids:
            notif_ids |= set(
                db.scalars(select(Notification.notification_id).where(Notification.ref_id.in_(request_ids))).all()
            )
        if user_ids:
            notif_ids |= set(
                db.scalars(select(Notification.notification_id).where(Notification.user_id.in_(user_ids))).all()
            )
        if notif_ids:
            db.execute(delete(NotificationRead).where(NotificationRead.notification_id.in_(notif_ids)))
            db.execute(delete(Notification).where(Notification.notification_id.in_(notif_ids)))

        if summary_ids:
            db.execute(delete(ActivitySummary).where(ActivitySummary.summary_id.in_(summary_ids)))
        if act_ids:
            db.execute(delete(ActivitySummary).where(ActivitySummary.activity_id.in_(act_ids)))
            db.execute(delete(ActivitySignup).where(ActivitySignup.activity_id.in_(act_ids)))
            db.execute(delete(Certificate).where(Certificate.activity_id.in_(act_ids)))
            # 物理删除：以前只标 is_deleted，跑一轮攒一批，演示库会越来越脏
            db.execute(delete(Activity).where(Activity.activity_id.in_(act_ids)))

        db.execute(delete(PermissionLog).where(PermissionLog.remark.like(f"{PREFIX}%")))

        # 注册测试账号（SMOKE 前缀）连同申请单、日志、消息一起清理，保证下次可重复注册
        if user_ids:
            db.execute(delete(PermissionRequest).where(PermissionRequest.user_id.in_(user_ids)))
            db.execute(delete(PermissionLog).where(PermissionLog.target_user_id.in_(user_ids)))
            db.execute(delete(PermissionLog).where(PermissionLog.operator_id.in_(user_ids)))
            db.execute(delete(NotificationRead).where(NotificationRead.user_id.in_(user_ids)))
            db.execute(delete(ActivitySignup).where(ActivitySignup.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.user_id.in_(user_ids)))
        db.commit()
    finally:
        db.close()


def reset_demo_baseline() -> None:
    """把演示账号恢复到 seed 基线。

    现场演示时可能在界面上点过「通过」，Bob / 访客就会多出权限，
    导致「Bob 不应有申办权」这类断言失败。测试前统一退回待审批状态，
    保证脚本可以反复运行。
    """
    db = SessionLocal()
    try:
        for student_no in ("2025211996", "guest"):
            row = db.scalar(select(User).where(User.student_no == student_no))
            if row is None:
                continue
            row.granted_permissions = []
            row.revoked_permissions = []
            approved = db.scalars(
                select(PermissionRequest).where(
                    PermissionRequest.user_id == row.user_id,
                    PermissionRequest.status == "approved",
                )
            ).all()
            for item in approved:
                item.status = "pending"
                item.reviewer_id = ""
                item.reviewer_name = ""
                item.review_comment = ""
                item.reviewed_at = None
        db.commit()
    finally:
        db.close()


def main() -> None:
    seed_script.main()
    reset_demo_baseline()
    print("=== 1. 健康检查与登录 ===")
    assert client.get("/api/v1/health").json()["code"] == 0
    accounts = {
        "super": login("admin"),
        "admin": login("T2009"),
        "admin_no_review": login("T2010"),
        "alice": login("2025211987"),
        "student_creator": login("2025211994"),
        "bob": login("2025211996"),
        "guest": login("guest"),
    }
    for key, data in accounts.items():
        print(f"  {key:<16} role={data['user']['role']:<12} 权限数={len(data['user']['permissions'])}")

    tokens = {key: data["token"] for key, data in accounts.items()}
    assert "system:permission" in accounts["super"]["user"]["permissions"]
    assert "activity:review" not in accounts["admin_no_review"]["user"]["permissions"], "T2010 的审批权应被收回"
    assert "activity:create" in accounts["student_creator"]["user"]["permissions"], "林晓应有申办权"
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
        headers=auth(tokens["student_creator"]),
    )
    act = expect(created, 0, "学生会成员申办活动")["data"]
    assert act["status"] == "draft" and act["level"] == "none"

    expect(client.post(f"/api/v1/activities/{act['activity_id']}/submit", json={}, headers=auth(tokens["student_creator"])), 0, "提交审批")

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
    expect(client.get("/api/v1/certificates/mine", headers=auth(tokens["admin"])), 1003, "管理员无我的证书")
    print("  ✅ 学生证书 PDF 可下载、公开验真、越权访问被拦")

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

    print("=== 8. 注册与访客入口 ===")
    student = expect(
        client.post("/api/v1/auth/register", json={
            "student_no": "SMOKE9001", "name": "注册学生", "password": "stu12345",
            "role": "student", "college": "计算机学院",
        }),
        0,
        "注册学生",
    )
    stu_token = student["data"]["token"]
    assert student["data"]["user"]["role"] == "student"
    me = expect(client.get("/api/v1/users/me", headers=auth(stu_token)), 0, "注册后即登录")
    assert me["data"]["student_no"] == "SMOKE9001"
    # 注册用户只认自己的密码，不接受统一演示密码
    expect(client.post("/api/v1/auth/login", json={"student_no": "SMOKE9001", "password": PASSWORD}), 1002, "演示密码不可登录注册账号")
    expect(client.post("/api/v1/auth/login", json={"student_no": "SMOKE9001", "password": "stu12345"}), 0, "新密码登录")
    expect(client.post("/api/v1/auth/register", json={
        "student_no": "SMOKE9001", "name": "重复", "password": "stu12345",
    }), 1001, "重复学号注册")
    admin_reg = expect(
        client.post("/api/v1/auth/register", json={
            "student_no": "SMOKE9002", "name": "注册管理员", "password": "adm12345", "role": "admin",
        }),
        0,
        "注册管理员",
    )
    assert admin_reg["data"]["user"]["role"] == "admin"
    assert "activity:review" in admin_reg["data"]["user"]["permissions"]
    expect(client.post("/api/v1/auth/register", json={
        "student_no": "SMOKE9003", "name": "越级", "password": "xxx12345", "role": "super_admin",
    }), 1001, "不允许注册系统管理员")
    guest = expect(client.post("/api/v1/auth/guest"), 0, "访客入口")
    assert guest["data"]["user"]["role"] == "visitor"
    assert "activity:signup" not in guest["data"]["user"]["permissions"]
    print("  ✅ 学生/管理员注册即登录、密码独立、访客一键进入")

    print("=== 9. 权限申请与审批 ===")
    req = expect(
        client.post("/api/v1/permission-requests", headers=auth(stu_token),
                    json={"permissions": ["activity:create"], "reason": f"{PREFIX}我要申办读书会"}),
        0,
        "提交申请",
    )
    request_id = req["data"]["request_id"]
    assert req["data"]["status"] == "pending"
    mine = expect(client.get("/api/v1/permission-requests/mine", headers=auth(stu_token)), 0, "我的申请")
    assert mine["data"]["total"] >= 1
    expect(client.post("/api/v1/permission-requests", headers=auth(stu_token),
                       json={"permissions": ["activity:create"], "reason": f"{PREFIX}重复申请"}), 1005, "重复申请")
    expect(client.post("/api/v1/permission-requests", headers=auth(stu_token),
                       json={"permissions": ["system:permission"], "reason": f"{PREFIX}越权申请"}), 1003, "申请系统权限")
    # 普通学生看不到全量申请
    expect(client.get("/api/v1/permission-requests", headers=auth(stu_token)), 1003, "学生看全量申请")
    # 普通管理员同样看不到
    expect(client.get("/api/v1/permission-requests", headers=auth(tokens["admin"])), 1003, "管理员看全量申请")
    all_req = expect(client.get("/api/v1/permission-requests", params={"status": "pending"},
                                headers=auth(tokens["super"])), 0, "系统管理员看申请")
    assert any(item["request_id"] == request_id for item in all_req["data"]["list"])
    summary = expect(client.get("/api/v1/permission-requests/summary", headers=auth(tokens["super"])), 0, "申请统计")
    assert summary["data"]["pending"] >= 1
    reviewed = expect(
        client.post(f"/api/v1/permission-requests/{request_id}/review", headers=auth(tokens["super"]),
                    json={"approve": True, "comment": f"{PREFIX}同意"}),
        0,
        "审批通过",
    )
    assert "activity:create" in reviewed["data"]["granted"]
    me_after = expect(client.get("/api/v1/users/me", headers=auth(stu_token)), 0, "审批后权限")
    assert "activity:create" in me_after["data"]["permissions"], "审批通过应即时生效"
    expect(client.post(f"/api/v1/permission-requests/{request_id}/review", headers=auth(tokens["super"]),
                       json={"approve": True}), 1005, "重复审批")
    # 驳回路径
    req2 = expect(client.post("/api/v1/permission-requests", headers=auth(stu_token),
                              json={"permissions": ["book:manage"], "reason": f"{PREFIX}想管馆藏"}), 0, "再提交")
    rejected = expect(client.post(f"/api/v1/permission-requests/{req2['data']['request_id']}/review",
                                  headers=auth(tokens["super"]), json={"approve": False, "comment": f"{PREFIX}暂不开放"}),
                      0, "驳回")
    assert rejected["data"]["request"]["status"] == "rejected"
    assert "book:manage" not in expect(client.get("/api/v1/users/me", headers=auth(stu_token)), 0, "驳回后权限")["data"]["permissions"]
    # 撤回
    req3 = expect(client.post("/api/v1/permission-requests", headers=auth(stu_token),
                              json={"permissions": ["drift:manage"], "reason": f"{PREFIX}想管漂流"}), 0, "三提")
    cancelled = expect(client.post(f"/api/v1/permission-requests/{req3['data']['request_id']}/cancel",
                                   headers=auth(stu_token)), 0, "撤回")
    assert cancelled["data"]["status"] == "cancelled"
    print("  ✅ 申请→仅系统管理员可见→审批即时授予→驳回不授权→可撤回")

    print("=== 10. 站内消息与未读数 ===")

    def unread(headers: dict) -> int:
        return expect(client.get("/api/v1/notifications/unread-count", headers=headers), 0, "未读数")["data"]["count"]

    def message_list(headers: dict) -> dict:
        return expect(
            client.get("/api/v1/notifications", headers=headers, params={"page": 1, "page_size": 50}),
            0,
            "消息列表",
        )["data"]

    base_super, base_stu = unread(auth(tokens["super"])), unread(auth(stu_token))
    req4 = expect(
        client.post("/api/v1/permission-requests", headers=auth(stu_token),
                    json={"permissions": ["book:manage"], "reason": f"{PREFIX}消息链路测试"}),
        0,
        "消息测试申请",
    )
    rid4 = req4["data"]["request_id"]
    assert unread(auth(tokens["super"])) == base_super + 1, "管理员应收到待审批消息"
    assert unread(auth(stu_token)) == base_stu, "发给管理员的消息不应增加申请人未读"

    expect(client.post(f"/api/v1/permission-requests/{rid4}/review", headers=auth(tokens["super"]),
                       json={"approve": True, "comment": f"{PREFIX}同意"}), 0, "消息测试审批")
    assert unread(auth(tokens["super"])) == base_super, "审批后待办消息应自动已读"
    assert unread(auth(stu_token)) == base_stu + 1, "申请人应收到审批结果"

    msgs = message_list(auth(stu_token))
    hit = [row for row in msgs["list"] if row["ref_id"] == rid4]
    assert hit and hit[0]["type"] == "permission_approved" and hit[0]["is_read"] is False
    assert msgs["unread"] == base_stu + 1

    read1 = expect(
        client.post(f"/api/v1/notifications/{hit[0]['notification_id']}/read", headers=auth(stu_token)),
        0,
        "单条已读",
    )
    assert read1["data"]["changed"] == 1
    assert unread(auth(stu_token)) == base_stu

    all_read = expect(client.post("/api/v1/notifications/read-all", headers=auth(stu_token)), 0, "全部已读")
    assert all_read["data"]["unread"] == 0
    again = expect(client.post("/api/v1/notifications/read-all", headers=auth(stu_token)), 0, "重复全部已读")
    assert again["data"]["changed"] == 0

    # 越权：学生标记管理员的消息不生效
    super_unread = [row for row in message_list(auth(tokens["super"]))["list"] if not row["is_read"]]
    if super_unread:
        foreign = expect(
            client.post(f"/api/v1/notifications/{super_unread[0]['notification_id']}/read", headers=auth(stu_token)),
            0,
            "越权标记他人消息",
        )
        assert foreign["data"]["changed"] == 0
    print("  ✅ 待办通知/审批结果/未读数增减/单条与全部已读/越权保护均正确")

    print("\n冒烟测试全部通过 ✅")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
