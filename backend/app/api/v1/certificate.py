"""电子证书：颁发、列表、PDF 下载、公开验真、撤销。

权限口径
--------
- 学生：`certificate:view` —— 只能看/下载**自己**的证书
- 管理员：`certificate:issue` —— 批量颁发、加盖公章、查看全部、撤销
- 访客：无 —— 只有公开验真接口（按验真码查询，不列名单）
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import (
    ACTIVITY_LEVEL_LABELS,
    ActivityLevel,
    ActivityStatus,
    CertificateStatus,
    NotificationType,
    SignupStatus,
)
from app.core.permissions import Permission
from app.core.response import CODE_ILLEGAL_STATE, CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, get_optional_user, new_id, require_permissions
from app.db.base import get_db
from app.db.models import Activity, ActivitySignup, Certificate, User
from app.schemas.certificate import (
    CertificateIssueRequest,
    CertificateIssueResult,
    CertificateOut,
    CertificateVerifyOut,
)
from app.schemas.common import PageQuery
from app.services import certificate_service
from app.services import notification_service as svc

router = APIRouter(tags=["电子证书"])

CST = timezone(timedelta(hours=8))


def _mask_name(name: str) -> str:
    if not name:
        return ""
    if len(name) <= 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def _out(row: Certificate) -> dict:
    return CertificateOut.model_validate(row).model_dump()


@router.get(
    "/certificates/mine",
    summary="我的电子证书",
    dependencies=[Depends(require_permissions(Permission.CERTIFICATE_VIEW))],
)
def list_my_certificates(
    pq: PageQuery = Depends(page_query),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Certificate).where(
        Certificate.user_id == current.user_id,
        Certificate.status == CertificateStatus.ISSUED.value,
        Certificate.is_deleted.is_(False),
    )
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Certificate.activity_title.like(like), Certificate.serial_no.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Certificate.issued_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    return ok(page_result([_out(r) for r in rows], pq.page, pq.page_size, total))


@router.get(
    "/certificates",
    summary="证书列表（管理端，按活动/关键词筛选）",
    dependencies=[Depends(require_permissions(Permission.CERTIFICATE_ISSUE))],
)
def list_certificates(
    pq: PageQuery = Depends(page_query),
    activity_id: str = Query(default=""),
    status: str = Query(default=""),
    db: Session = Depends(get_db),
):
    stmt = select(Certificate).where(Certificate.is_deleted.is_(False))
    if activity_id:
        stmt = stmt.where(Certificate.activity_id == activity_id)
    if status:
        stmt = stmt.where(Certificate.status == status)
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(
            or_(
                Certificate.student_name.like(like),
                Certificate.student_no.like(like),
                Certificate.activity_title.like(like),
                Certificate.serial_no.like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Certificate.issued_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    return ok(page_result([_out(r) for r in rows], pq.page, pq.page_size, total))


@router.get("/certificates/verify/{verify_code}", summary="证书验真（公开，无需登录）")
def verify_certificate(verify_code: str, db: Session = Depends(get_db)):
    row = db.scalar(
        select(Certificate).where(Certificate.verify_code == verify_code.strip().upper(), Certificate.is_deleted.is_(False))
    )
    if row is None:
        return ok(CertificateVerifyOut(valid=False, serial_no="", holder_name="", activity_title="",
                                       activity_level="", certificate_name="", seal_name="",
                                       message="未查询到该证书，请核对验真码").model_dump())
    valid = row.status == CertificateStatus.ISSUED.value
    return ok(
        CertificateVerifyOut(
            valid=valid,
            serial_no=row.serial_no,
            holder_name=_mask_name(row.student_name),
            activity_title=row.activity_title,
            activity_level=ACTIVITY_LEVEL_LABELS.get(row.activity_level, row.activity_level),
            certificate_name=row.certificate_name,
            seal_name=row.seal_name,
            issued_at=row.issued_at.astimezone(CST),
            message="证书有效" if valid else "该证书已被撤销",
        ).model_dump()
    )


@router.get("/certificates/{certificate_id}/pdf", summary="下载证书 PDF（本人或管理员）")
def download_certificate(
    certificate_id: str,
    current: CurrentUser = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    row = db.get(Certificate, certificate_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "证书不存在")
    is_owner = current.user_id == row.user_id and current.can(Permission.CERTIFICATE_VIEW.value)
    if not (is_owner or current.can(Permission.CERTIFICATE_ISSUE.value)):
        raise BizError(1003, "无权下载他人的证书", http_status=403)
    if row.status != CertificateStatus.ISSUED.value:
        raise BizError(CODE_ILLEGAL_STATE, "证书已被撤销，不能下载")

    pdf = certificate_service.render_certificate(
        holder_name=row.student_name,
        student_no=row.student_no,
        college=row.college,
        activity_title=row.activity_title,
        activity_level=row.activity_level,
        certificate_name=row.certificate_name,
        seal_name=row.seal_name,
        serial_no=row.serial_no,
        verify_code=row.verify_code,
        issued_date=row.issued_at.astimezone(CST).strftime("%Y 年 %m 月 %d 日"),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="certificate_{row.serial_no}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/activities/{activity_id}/certificates",
    status_code=201,
    summary="按活动颁发电子证书（批量）",
    dependencies=[Depends(require_permissions(Permission.CERTIFICATE_ISSUE))],
)
def issue_certificates(
    activity_id: str,
    payload: CertificateIssueRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None or activity.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    if activity.status != ActivityStatus.FINISHED.value:
        raise BizError(CODE_ILLEGAL_STATE, "活动结束后才能颁发证书")
    if activity.level not in (ActivityLevel.SCHOOL.value, ActivityLevel.COLLEGE.value):
        raise BizError(CODE_ILLEGAL_STATE, "活动尚未定级（校级/院级），请先完成审批")

    stmt = select(ActivitySignup).where(
        ActivitySignup.activity_id == activity_id,
        ActivitySignup.is_deleted.is_(False),
        ActivitySignup.status == SignupStatus.APPROVED.value,
    )
    if payload.user_ids:
        stmt = stmt.where(ActivitySignup.user_id.in_(payload.user_ids))
    if payload.only_checked_in:
        stmt = stmt.where(ActivitySignup.checked_in_at.is_not(None))
    signups = db.scalars(stmt).all()
    if not signups:
        raise BizError(CODE_ILLEGAL_STATE, "没有符合条件的颁发对象（报名/签到名单为空）")

    existing = {
        row.user_id
        for row in db.scalars(
            select(Certificate).where(
                Certificate.activity_id == activity_id,
                Certificate.is_deleted.is_(False),
            )
        ).all()
    }

    issued: list[Certificate] = []
    skipped = 0
    year = datetime.now(CST).year
    level_code = "S" if activity.level == ActivityLevel.SCHOOL.value else "C"
    for signup in signups:
        if signup.user_id in existing:
            skipped += 1
            continue
        student = db.get(User, signup.user_id)
        if student is None or student.is_deleted:
            skipped += 1
            continue
        verify_code = new_id("certificate").split("_")[1].upper()[:8]
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
            certificate_name=payload.certificate_name,
            seal_name="北京邮电大学图书馆" if activity.level == ActivityLevel.SCHOOL.value else "北京邮电大学图书馆",
            issued_by=current.user_id,
            issued_by_name=current.name,
            issued_at=datetime.now(timezone.utc),
            status=CertificateStatus.ISSUED.value,
        )
        db.add(cert)
        signup.certificate_no = cert.serial_no
        issued.append(cert)
        existing.add(student.user_id)
        svc.notify_user(
            db,
            student.user_id,
            type=NotificationType.CERTIFICATE_ISSUED.value,
            title=f"你获得了活动证书：{activity.title}",
            content=f"证书编号 {cert.serial_no}，可在「我的证书」查看并下载 PDF。",
            ref_type="certificate",
            ref_id=cert.certificate_id,
            actor_id=current.user_id,
            actor_name=current.name,
        )

    db.commit()
    for cert in issued:
        db.refresh(cert)

    reason = ""
    if skipped:
        reason = f"{skipped} 人已有证书或账号已注销，已跳过"
    return ok(
        CertificateIssueResult(
            issued=len(issued),
            skipped=skipped,
            skipped_reason=reason,
            certificates=[CertificateOut.model_validate(cert) for cert in issued],
        ).model_dump()
    )


@router.post(
    "/certificates/{certificate_id}/revoke",
    summary="撤销证书",
    dependencies=[Depends(require_permissions(Permission.CERTIFICATE_ISSUE))],
)
def revoke_certificate(certificate_id: str, db: Session = Depends(get_db)):
    row = db.get(Certificate, certificate_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "证书不存在")
    if row.status == CertificateStatus.REVOKED.value:
        raise BizError(CODE_ILLEGAL_STATE, "证书已是撤销状态")
    row.status = CertificateStatus.REVOKED.value
    db.commit()
    db.refresh(row)
    return ok(_out(row))
