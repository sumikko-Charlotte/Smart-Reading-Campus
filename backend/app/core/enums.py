"""统一枚举：双端必须共用同一份取值，禁止在业务代码里写裸字符串。"""
from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # 便于日志与序列化
        return self.value


class UserRole(StrEnum):
    """三类角色，其中管理员分两级：普通管理员 / 系统管理员。"""

    VISITOR = "visitor"          # 访客：只读浏览 / AI 推荐走降级 Mock
    STUDENT = "student"          # 学生：报名、漂流、证书；按需授予申办活动
    ADMIN = "admin"              # 普通管理员：申办/审批/漂流运营/发证书
    SUPER_ADMIN = "super_admin"  # 系统管理员：全部权限 + 权限分配


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PermissionRequestStatus(StrEnum):
    """权限申请单状态：学生/管理员提交 → 系统管理员审批。"""

    PENDING = "pending"      # 待审批
    APPROVED = "approved"    # 已通过（权限已写入）
    REJECTED = "rejected"    # 已驳回
    CANCELLED = "cancelled"  # 申请人主动撤回


class ActivityCategory(StrEnum):
    READING_SHARE = "reading_share"
    LECTURE = "lecture"
    EXHIBITION = "exhibition"
    READING_CHALLENGE = "reading_challenge"
    BOOK_DRIFT = "book_drift"
    OTHER = "other"


class ActivityStatus(StrEnum):
    DRAFT = "draft"                    # 草稿（申办人可编辑）
    PENDING_REVIEW = "pending_review"  # 待审批（已提交，等待管理员审核）
    REJECTED = "rejected"              # 审批驳回（可修改后重新提交）
    PUBLISHED = "published"            # 已发布（审批通过，开放报名）
    SIGNUP_CLOSED = "signup_closed"
    ONGOING = "ongoing"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ActivityLevel(StrEnum):
    """活动等级：审批时确定，决定证书盖章口径。"""

    NONE = "none"        # 未定级（草稿/待审批）
    COLLEGE = "college"  # 院级
    SCHOOL = "school"    # 校级


ACTIVITY_LEVEL_LABELS: dict[str, str] = {
    ActivityLevel.NONE: "未定级",
    ActivityLevel.COLLEGE: "院级",
    ActivityLevel.SCHOOL: "校级",
}

# 活动状态合法流转表：非法流转统一返回 code=1005
ACTIVITY_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ActivityStatus.DRAFT: {ActivityStatus.PENDING_REVIEW, ActivityStatus.CANCELLED},
    ActivityStatus.PENDING_REVIEW: {ActivityStatus.PUBLISHED, ActivityStatus.REJECTED, ActivityStatus.CANCELLED},
    ActivityStatus.REJECTED: {ActivityStatus.PENDING_REVIEW, ActivityStatus.CANCELLED},
    ActivityStatus.PUBLISHED: {ActivityStatus.SIGNUP_CLOSED, ActivityStatus.CANCELLED},
    ActivityStatus.SIGNUP_CLOSED: {ActivityStatus.ONGOING, ActivityStatus.CANCELLED},
    ActivityStatus.ONGOING: {ActivityStatus.FINISHED},
    ActivityStatus.FINISHED: set(),
    ActivityStatus.CANCELLED: set(),
}

#: 只有这些状态属于「对外可见」，访客/学生不应看到草稿、待审批、驳回
ACTIVITY_PUBLIC_STATUSES = {
    ActivityStatus.PUBLISHED,
    ActivityStatus.SIGNUP_CLOSED,
    ActivityStatus.ONGOING,
    ActivityStatus.FINISHED,
}

ACTIVITY_STATUS_LABELS: dict[str, str] = {
    ActivityStatus.DRAFT: "草稿",
    ActivityStatus.PENDING_REVIEW: "待审批",
    ActivityStatus.REJECTED: "审批驳回",
    ActivityStatus.PUBLISHED: "已发布",
    ActivityStatus.SIGNUP_CLOSED: "报名截止",
    ActivityStatus.ONGOING: "进行中",
    ActivityStatus.FINISHED: "已结束",
    ActivityStatus.CANCELLED: "已取消",
}


class BookSource(StrEnum):
    LIBRARY = "library"
    DRIFT = "drift"
    BOTH = "both"


class DriftStatus(StrEnum):
    IDLE = "idle"
    RESERVED = "reserved"
    IN_TRANSIT = "in_transit"
    CLAIMED = "claimed"
    CLOSED = "closed"


class ConversationScene(StrEnum):
    BOOK_ANALYSIS = "book_analysis"
    RECOMMEND = "recommend"
    QA = "qa"
    COPYWRITING = "copywriting"
    ACTIVITY_SUMMARY = "activity_summary"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class SignupStatus(StrEnum):
    """活动报名状态"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CertificateStatus(StrEnum):
    ISSUED = "issued"
    REVOKED = "revoked"


class SummaryStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class NotificationType(StrEnum):
    ACTIVITY_SUMMARY = "activity_summary"  # 参加过的活动发布了回顾
    ACTIVITY_PUBLISHED = "activity_published"  # 活动审批通过并发布
    ACTIVITY_REJECTED = "activity_rejected"  # 活动被驳回
    ACTIVITY_CANCELLED = "activity_cancelled"  # 活动取消
    ACTIVITY_REVIEW = "activity_review"  # 有待你审批的活动
    ACTIVITY_STATUS = "activity_status"  # 活动状态变化（报名截止 / 开始 / 结束）
    CERTIFICATE_ISSUED = "certificate_issued"
    PERMISSION_REQUEST = "permission_request"  # 有待你审批的权限申请
    PERMISSION_APPROVED = "permission_approved"  # 你的权限申请通过
    PERMISSION_REJECTED = "permission_rejected"  # 你的权限申请被驳回
    PERMISSION_CHANGED = "permission_changed"  # 管理员直接调整了你的权限
    SYSTEM = "system"


# ------------------------------------------------------------ 第二阶段②：AI 数据层


class BorrowStatus(StrEnum):
    """借阅记录状态（AI 匹配 / AI 触达的核心数据来源）。"""

    BORROWING = "borrowing"  # 在借
    RETURNED = "returned"  # 已归还
    OVERDUE = "overdue"  # 逾期未还


class BorrowSource(StrEnum):
    LIBRARY = "library"  # 馆藏借阅
    DRIFT = "drift"  # 漂流获得
    PURCHASE = "purchase"  # 荐购 / 自购登记


class ReadingEventType(StrEnum):
    """阅读行为埋点类型，用于画像与推荐解释。"""

    SEARCH = "search"  # 检索（带 keyword）
    VIEW_BOOK = "view_book"  # 查看书目详情
    VIEW_ACTIVITY = "view_activity"  # 查看活动详情
    AI_RECOMMEND = "ai_recommend"  # 触发 AI 推荐
    AI_CHAT = "ai_chat"  # 与伴读助手对话
    FAVORITE = "favorite"  # 收藏
    UNFAVORITE = "unfavorite"  # 取消收藏
    RATE = "rate"  # 评分（score 1-5）
    SIGNUP = "signup"  # 报名活动
    CHECKIN = "checkin"  # 签到
    SUMMARY_VIEW = "summary_view"  # 浏览活动总结
    NOTIFICATION_READ = "notification_read"  # 打开推送


READING_EVENT_LABELS: dict[str, str] = {
    "search": "检索",
    "view_book": "查看书目",
    "view_activity": "查看活动",
    "ai_recommend": "AI 推荐",
    "ai_chat": "AI 伴读",
    "favorite": "收藏",
    "unfavorite": "取消收藏",
    "rate": "评分",
    "signup": "报名",
    "checkin": "签到",
    "summary_view": "看总结",
    "notification_read": "读推送",
}

BORROW_STATUS_LABELS: dict[str, str] = {
    "borrowing": "在借",
    "returned": "已归还",
    "overdue": "逾期",
}

