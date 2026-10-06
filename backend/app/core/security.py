"""主键生成、鉴权与 RBAC 骨架、手机号/邮箱脱敏。

本轮为骨架实现：登录校验用「学号 + 固定演示密码」，token 用 HMAC 签名串，
第 2 轮替换为真实 JWT（PyJWT）即可，接口签名保持不变。
"""
import base64
import hashlib
import hmac
import json
import time
import uuid

from fastapi import Depends, Header

from app.core.config import settings
from app.core.enums import UserRole
from app.core.response import CODE_FORBIDDEN, CODE_UNAUTHORIZED, BizError

ID_PREFIXES = {
    "user": "usr",
    "activity": "act",
    "book": "bok",
    "conversation": "cnv",
    "message": "msg",
    "drift": "drf",
    "signup": "sup",
}


def new_id(kind: str) -> str:
    """统一主键：前缀 + 12 位十六进制，如 usr_9f2a1c77b0d4。"""
    prefix = ID_PREFIXES.get(kind, kind[:3])
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
    """最小可用上下文，后续可从数据库补全完整 User 对象。"""

    def __init__(self, user_id: str, role: str):
        self.user_id = user_id
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """从 Authorization: Bearer <token> 解析当前用户（允许匿名透传场景自行放开）。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise BizError(CODE_UNAUTHORIZED, "未登录或登录已失效")
    payload = parse_token(authorization.split(" ", 1)[1].strip())
    return CurrentUser(user_id=payload["sub"], role=payload["role"])


def require_roles(*roles: str):
    """RBAC 依赖工厂：@router.get(..., dependencies=[Depends(require_roles('admin'))])"""

    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in {r.value if hasattr(r, "value") else r for r in roles}:
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
