"""主键生成、鉴权、权限校验依赖、手机号/邮箱脱敏。

权限模型（第二阶段）
------------------
- 角色只提供**默认权限**，接口一律校验权限点（`require_permissions`）
- 有效权限 = 角色默认 - 收回 + 额外授予，由 `app.core.permissions` 计算
- 支持可选登录：访客不带 token 也能访问只读接口（`get_optional_user`）
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import UserRole, UserStatus
from app.core.permissions import effective_permissions
from app.core.response import CODE_FORBIDDEN, CODE_UNAUTHORIZED, BizError
from app.db.base import get_db

ID_PREFIXES = {
    "user": "usr",
    "activity": "act",
    "book": "bok",
    "conversation": "cnv",
    "message": "msg",
    "drift": "drf",
    "signup": "sgn",
    "report": "rpt",
    "certificate": "crt",
    "summary": "sum",
    "notification": "ntf",
    "permission_log": "plg",
    "borrow": "brw",
    "favorite": "fav",
    "event": "evt",
    "agent_run": "run",
    "permission_request": "prq",
}


def new_id(kind: str) -> str:
    """统一主键：前缀 + 12 位十六进制，如 usr_9f2a1c77b0d4。"""
    prefix = ID_PREFIXES.get(kind, kind[:3])
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- 密码
#
# 只依赖标准库：PBKDF2-HMAC-SHA256 + 每用户随机盐，格式
#   pbkdf2_sha256$迭代次数$盐(hex)$摘要(hex)
# 演示账号（seed 写入）没有 password_hash，登录时回退到统一演示密码，
# 一旦通过「修改密码」设置过密码，就只认哈希，不再接受演示密码。

PBKDF2_ITERATIONS = 120_000
DEMO_PASSWORD = "123456"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt, expected = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def check_login_password(password: str, stored_hash: str) -> bool:
    """有哈希按哈希校验；没有哈希的演示账号仍可用统一演示密码登录。"""
    if stored_hash:
        return verify_password(password, stored_hash)
    return password == DEMO_PASSWORD


# ---------------------------------------------------------------- token


def create_token(user_id: str, role: str, ttl_minutes: int | None = None) -> str:
    ttl = (ttl_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60
    payload = {"sub": user_id, "role": role, "exp": int(time.time()) + ttl}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def parse_token(token: str) -> dict:
    try:
        raw, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise BizError(CODE_UNAUTHORIZED, "token 格式非法") from exc
    expect = hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expect):
        raise BizError(CODE_UNAUTHORIZED, "token 签名校验失败")
    payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
    if payload.get("exp", 0) < int(time.time()):
        raise BizError(CODE_UNAUTHORIZED, "token 已过期，请重新登录")
    return payload


class CurrentUser:
    """当前请求主体：既可能是登录用户，也可能是匿名访客（visitor）。"""

    def __init__(
        self,
        user_id: str,
        role: str,
        permissions: set[str] | frozenset[str] | None = None,
        name: str = "",
        student_no: str = "",
        is_anonymous: bool = False,
    ):
        self.user_id = user_id
        self.role = role
        self.name = name
        self.student_no = student_no
        self.is_anonymous = is_anonymous
        self.permissions = frozenset(permissions if permissions is not None else effective_permissions(role))

    def can(self, *codes: str) -> bool:
        """全部命中才算有权限（与 require_permissions 默认 all 语义一致）。"""
        return all(code in self.permissions for code in codes)

    def can_any(self, *codes: str) -> bool:
        return any(code in self.permissions for code in codes)

    @property
    def is_staff(self) -> bool:
        return self.role in (UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value)

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN.value

    @property
    def is_visitor(self) -> bool:
        return self.role == UserRole.VISITOR.value


VISITOR = CurrentUser(
    user_id="",
    role=UserRole.VISITOR.value,
    permissions=effective_permissions(UserRole.VISITOR.value),
    name="访客",
    is_anonymous=True,
)


def _load_user(token: str, db: Session) -> CurrentUser:
    """token 里的 role 只作兜底，真实角色与权限一律以数据库为准（改权限即时生效）。"""
    from app.db.models import User  # 延迟导入，避免 models -> security 的循环依赖

    payload = parse_token(token)
    user = db.get(User, payload["sub"])
    if user is None or user.is_deleted:
        raise BizError(CODE_UNAUTHORIZED, "账号不存在或已注销")
    if user.status != UserStatus.ACTIVE.value:
        raise BizError(CODE_UNAUTHORIZED, "账号已被禁用，请联系管理员")
    return CurrentUser(
        user_id=user.user_id,
        role=user.role,
        permissions=effective_permissions(user.role, user.granted_permissions, user.revoked_permissions),
        name=user.name,
        student_no=user.student_no,
    )


def _auth_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """必须登录：未带 token 直接 401。"""
    token = _auth_token(authorization)
    if not token:
        raise BizError(CODE_UNAUTHORIZED, "未登录或登录已失效")
    return _load_user(token, db)


async def get_optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """可选登录：无 token 返回访客上下文，用于活动/漂流/AI 推荐的公开浏览。"""
    token = _auth_token(authorization)
    if not token:
        return VISITOR
    return _load_user(token, db)


def require_permissions(*codes: str, mode: str = "all"):
    """权限依赖工厂。

    用法：`dependencies=[Depends(require_permissions(Permission.ACTIVITY_REVIEW))]`
    """

    wanted = tuple(c.value if hasattr(c, "value") else c for c in codes)

    async def _checker(user: CurrentUser = Depends(get_optional_user)) -> CurrentUser:
        hit = all(code in user.permissions for code in wanted) if mode == "all" else any(
            code in user.permissions for code in wanted
        )
        if not hit:
            if user.is_anonymous:
                raise BizError(CODE_UNAUTHORIZED, "该操作需要登录后使用", http_status=401)
            raise BizError(CODE_FORBIDDEN, "当前账号未被授予该操作权限", http_status=403)
        return user

    return _checker


def require_roles(*roles: str):
    """兼容旧代码的角色校验；新代码请优先使用 require_permissions。"""

    allowed = {r.value if hasattr(r, "value") else r for r in roles}

    async def _checker(user: CurrentUser = Depends(get_optional_user)) -> CurrentUser:
        if user.role not in allowed:
            if user.is_anonymous:
                raise BizError(CODE_UNAUTHORIZED, "该操作需要登录后使用", http_status=401)
            raise BizError(CODE_FORBIDDEN, "当前角色无权访问该资源", http_status=403)
        return user

    return _checker


# ---------------------------------------------------------------- 脱敏


def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return phone or ""
    return f"{phone[:3]}****{phone[-4:]}"


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    name, domain = email.split("@", 1)
    keep = name[:2] if len(name) > 2 else name[:1]
    return f"{keep}****@{domain}"
