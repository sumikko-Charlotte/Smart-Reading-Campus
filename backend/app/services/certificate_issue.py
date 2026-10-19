"""证书自动发放：学生完成签到与签退后即时生成。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ActivityLevel, CertificateStatus, NotificationType
from app.core.security import new_id
from app.db.models import Activity, ActivitySignup, Certificate, User
from app.services import notification_service as svc


def _verify_code() -> str:
    return new_id("certificate").split("_")[1].upper()[:8]


def issue_for_signup(
    db: Session,
    activity: Activity,
    signup: ActivitySignup,
    issued_by: str = "",
    issued_by_name: str = "系统自动发放",
) -> Optional[Certificate]:
    """签到 + 签退齐全且活动已定级时，为学生生成一张证书（幂等）。"""
    if not activity.need_certificate:
        return None
    if activity.level not in (ActivityLevel.SCHOOL.value, ActivityLevel.COLLEGE.value):
        return None
    if not signup.checked_in_at or not signup.checked_out_at:
        return None

    existing = db.scalar(
        select(Certificate).where(
            Certificate.activity_id == activity.activity_id,
            Certificate.user_id == signup.user_id,
            Certificate.is_deleted.is_(False),
        )
    )
    if existing is not None:
        if not signup.certificate_no:
            signup.certificate_no = existing.serial_no
        return existing

    student = db.get(User, signup.user_id)
    if student is None or student.is_deleted:
        return None

    verify_code = _verify_code()
    year = datetime.now(timezone.utc).year
    level_code = "S" if activity.level == ActivityLevel.SCHOOL.value else "C"
    cert = Certificate(
        certificate_id=new_id("certificate"),
        serial_no=f"ZYYC-{year}-{level_code}-{verify_code}",
        verify_code=verify_code,
        user_id=student.user_id,
        student_name=student.name,
        student_no=student.student_no,
        college=student.college,
        activity_id=activity.activity_id,
        activity_title=activity.title,
        activity_level=activity.level,
        certificate_name="荣誉证书",
        seal_name="北京邮电大学图书馆",
        issued_by=issued_by,
        issued_by_name=issued_by_name,
        issued_at=datetime.now(timezone.utc),
        status=CertificateStatus.ISSUED.value,
    )
    db.add(cert)
    signup.certificate_no = cert.serial_no
    svc.notify_user(
        db,
        student.user_id,
        type=NotificationType.CERTIFICATE_ISSUED.value,
        title=f"你获得了活动证书：{activity.title}",
        content=f"证书编号 {cert.serial_no}，可在「我的证书」查看并下载。",
        ref_type="certificate",
        ref_id=cert.certificate_id,
        actor_id=issued_by,
        actor_name=issued_by_name,
    )
    return cert
