"""统一枚举：双端必须共用同一份取值，禁止在业务代码里写裸字符串。"""
from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # 便于日志与序列化
        return self.value


class UserRole(StrEnum):
    STUDENT = "student"
    LIBRARIAN = "librarian"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ActivityCategory(StrEnum):
    READING_SHARE = "reading_share"
    LECTURE = "lecture"
    EXHIBITION = "exhibition"
    READING_CHALLENGE = "reading_challenge"
    BOOK_DRIFT = "book_drift"
    OTHER = "other"


class ActivityStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SIGNUP_CLOSED = "signup_closed"
    ONGOING = "ongoing"
    FINISHED = "finished"
    CANCELLED = "cancelled"


# 活动状态合法流转表：非法流转统一返回 code=1005
ACTIVITY_STATUS_TRANSITIONS: dict[str, set[str]] = {
    ActivityStatus.DRAFT: {ActivityStatus.PUBLISHED, ActivityStatus.CANCELLED},
    ActivityStatus.PUBLISHED: {ActivityStatus.SIGNUP_CLOSED, ActivityStatus.ONGOING, ActivityStatus.CANCELLED},
    ActivityStatus.SIGNUP_CLOSED: {ActivityStatus.ONGOING, ActivityStatus.FINISHED, ActivityStatus.CANCELLED},
    ActivityStatus.ONGOING: {ActivityStatus.FINISHED},
    ActivityStatus.FINISHED: set(),
    ActivityStatus.CANCELLED: set(),
}

ACTIVITY_STATUS_LABELS: dict[str, str] = {
    ActivityStatus.DRAFT: "草稿",
    ActivityStatus.PUBLISHED: "报名中",
    ActivityStatus.SIGNUP_CLOSED: "报名截止",
    ActivityStatus.ONGOING: "进行中",
    ActivityStatus.FINISHED: "已结束",
    ActivityStatus.CANCELLED: "已取消",
}


class BookSource(StrEnum):
    LIBRARY = "library"
    DRIFT = "drift"


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


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class SignupStatus(StrEnum):
    """活动报名状态（第 2 轮启用，先占位）"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
