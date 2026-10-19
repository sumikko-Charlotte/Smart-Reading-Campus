"""权限点目录与角色默认权限（第二阶段：三角色 + 双级管理员）。

设计原则
--------
1. **角色只决定默认权限，不直接决定能不能做**。业务代码一律校验权限点，
   不写 `if role == 'admin'`，这样系统管理员给「个别学生」开口子时不需要改代码。
2. 权限点编码固定为 `资源:动作`，全小写，双端共用同一份。
3. 有效权限 = 角色默认权限 - 收回权限 + 额外授予权限。
4. `system:permission` 只属于系统管理员，且**不允许授予任何其他账号**，
   避免出现「谁都能造一个超级管理员」的越权链。
"""
from enum import Enum


class Permission(str, Enum):
    # ---- 活动 ----
    ACTIVITY_VIEW = "activity:view"          # 浏览活动（含访客）
    ACTIVITY_SIGNUP = "activity:signup"      # 报名参加活动
    ACTIVITY_CREATE = "activity:create"      # 申办活动，并管理自己申办的活动
    ACTIVITY_MANAGE_ALL = "activity:manage_all"  # 管理全部活动（改/删/流转）
    ACTIVITY_REVIEW = "activity:review"      # 审批活动、定级（校级/院级）、驳回
    ACTIVITY_SUMMARY = "activity:summary"    # 发布活动总结（图文）并推送给全站
    # ---- 图书漂流 ----
    DRIFT_VIEW = "drift:view"                # 查看漂流池与图书状态（含访客）
    DRIFT_PARTICIPATE = "drift:participate"  # 上架、申领漂流书
    DRIFT_MANAGE = "drift:manage"            # 漂流运营管理（下架/异常）
    # ---- 馆藏图书 ----
    BOOK_MANAGE = "book:manage"              # 馆藏图书建档与维护
    # ---- 电子证书 ----
    CERTIFICATE_VIEW = "certificate:view"    # 查看并下载自己的证书（仅学生端）
    # ---- AI ----
    AI_RECOMMEND = "ai:recommend"            # 图书推荐（访客走降级 Mock）
    AI_CHAT = "ai:chat"                      # AI 伴读多轮对话
    # ---- 系统 ----
    SYSTEM_USER = "system:user"              # 用户管理
    SYSTEM_PERMISSION = "system:permission"  # 分配/收回权限、调整角色（系统管理员专属）


#: 权限目录：管理端「权限分配」页按 group 分组渲染
PERMISSION_CATALOG: list[dict] = [
    {"code": Permission.ACTIVITY_VIEW.value, "name": "浏览活动", "group": "活动", "description": "查看活动列表与详情", "risk": "low"},
    {"code": Permission.ACTIVITY_SIGNUP.value, "name": "报名活动", "group": "活动", "description": "报名参加活动、查看本人参与记录", "risk": "low"},
    {"code": Permission.ACTIVITY_CREATE.value, "name": "申办活动", "group": "活动", "description": "新建活动并管理自己申办的活动（学生会成员按需授予）", "risk": "medium"},
    {"code": Permission.ACTIVITY_MANAGE_ALL.value, "name": "管理全部活动", "group": "活动", "description": "编辑、删除、流转任意活动", "risk": "high"},
    {"code": Permission.ACTIVITY_REVIEW.value, "name": "审批活动", "group": "活动", "description": "审核活动并定级为校级/院级，审批通过后方可发布", "risk": "high"},
    {"code": Permission.ACTIVITY_SUMMARY.value, "name": "发布活动总结", "group": "活动", "description": "活动结束后发布图文总结并推送给指定角色", "risk": "medium"},
    {"code": Permission.DRIFT_VIEW.value, "name": "查看漂流池", "group": "图书漂流", "description": "查看漂流图书与流转状态", "risk": "low"},
    {"code": Permission.DRIFT_PARTICIPATE.value, "name": "参与漂流", "group": "图书漂流", "description": "扫码上架、申领交接漂流书", "risk": "low"},
    {"code": Permission.DRIFT_MANAGE.value, "name": "漂流运营管理", "group": "图书漂流", "description": "下架、修正漂流状态等运营操作", "risk": "medium"},
    {"code": Permission.BOOK_MANAGE.value, "name": "馆藏图书管理", "group": "图书漂流", "description": "馆藏图书建档、编辑与 AI 解读刷新", "risk": "medium"},
    {"code": Permission.CERTIFICATE_VIEW.value, "name": "查看/下载本人证书", "group": "电子证书", "description": "查看本人电子证书并下载 PDF", "risk": "low"},
    {"code": Permission.AI_RECOMMEND.value, "name": "AI 智能推荐", "group": "AI 能力", "description": "使用智能推荐（访客自动降级为 Mock）", "risk": "low"},
    {"code": Permission.AI_CHAT.value, "name": "AI 伴读对话", "group": "AI 能力", "description": "与 AI 阅读助手多轮对话", "risk": "low"},
    {"code": Permission.SYSTEM_USER.value, "name": "用户管理", "group": "系统", "description": "新增/编辑/禁用用户", "risk": "high"},
    {"code": Permission.SYSTEM_PERMISSION.value, "name": "权限分配", "group": "系统", "description": "调整角色与逐项分配权限（仅系统管理员）", "risk": "critical"},
]

ALL_PERMISSIONS: set[str] = {item["code"] for item in PERMISSION_CATALOG}

#: 不可下放的权限：即使系统管理员误操作也不允许授予他人
NON_DELEGABLE = {Permission.SYSTEM_PERMISSION.value}

ROLE_LABELS: dict[str, str] = {
    "visitor": "访客",
    "student": "学生",
    "admin": "普通管理员",
    "super_admin": "系统管理员",
}

#: 角色默认权限。普通管理员默认具备审批权，但系统管理员可按人收回
ROLE_DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    "visitor": {
        Permission.ACTIVITY_VIEW.value,
        Permission.DRIFT_VIEW.value,
        Permission.AI_RECOMMEND.value,
    },
    "student": {
        Permission.ACTIVITY_VIEW.value,
        Permission.ACTIVITY_SIGNUP.value,
        Permission.DRIFT_VIEW.value,
        Permission.DRIFT_PARTICIPATE.value,
        Permission.CERTIFICATE_VIEW.value,
        Permission.AI_RECOMMEND.value,
        Permission.AI_CHAT.value,
    },
    "admin": {
        Permission.ACTIVITY_VIEW.value,
        Permission.ACTIVITY_SIGNUP.value,
        Permission.ACTIVITY_CREATE.value,
        Permission.ACTIVITY_MANAGE_ALL.value,
        Permission.ACTIVITY_REVIEW.value,
        Permission.ACTIVITY_SUMMARY.value,
        Permission.DRIFT_VIEW.value,
        Permission.DRIFT_PARTICIPATE.value,
        Permission.DRIFT_MANAGE.value,
        Permission.BOOK_MANAGE.value,
        Permission.AI_RECOMMEND.value,
        Permission.AI_CHAT.value,
        Permission.SYSTEM_USER.value,
    },
    "super_admin": ALL_PERMISSIONS,
}

STAFF_ROLES = {"admin", "super_admin"}
VALID_ROLES = set(ROLE_LABELS)


def effective_permissions(role: str, granted: list[str] | None = None, revoked: list[str] | None = None) -> set[str]:
    """有效权限 = 角色默认 - 收回 + 额外授予。非法权限码直接忽略。"""
    defaults = set(ROLE_DEFAULT_PERMISSIONS.get(role, set()))
    extra = {code for code in (granted or []) if code in ALL_PERMISSIONS}
    removed = {code for code in (revoked or []) if code in ALL_PERMISSIONS}
    result = (defaults - removed) | extra
    if role != "super_admin":
        # 系统管理员专属权限永不下放
        result -= NON_DELEGABLE
    return result


def permission_groups() -> list[dict]:
    """按分组聚合的权限目录，供前端渲染复选框。"""
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for item in PERMISSION_CATALOG:
        if item["group"] not in grouped:
            grouped[item["group"]] = []
            order.append(item["group"])
        grouped[item["group"]].append(item)
    return [{"group": name, "items": grouped[name]} for name in order]
