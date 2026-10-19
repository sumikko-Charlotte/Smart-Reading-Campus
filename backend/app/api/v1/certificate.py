"""电子证书：我的证书、PDF 下载、公开验真。

学生完成签到与签退后由系统自动发放（见 services/certificate_issue.py）。
管理端不再提供批量颁发、全量列表与撤销入口。
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import ACTIVITY_LEVEL_LABELS, CertificateStatus, UserRole
from app.core.permissions import Permission
from app.core.response import CODE_FORBIDDEN, CODE_ILLEGAL_STATE, CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, require_permissions
from app.db.base import get_db
from app.db.models import Certificate
from app.schemas.certificate import CertificateOut, CertificateVerifyOut
from app.schemas.common import PageQuery
from app.services import certificate_service

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


def _require_student(current: CurrentUser) -> None:
    if current.role != UserRole.STUDENT.value:
        raise BizError(CODE_FORBIDDEN, "仅学生端提供证书查看与下载", http_status=403)


@router.get(
    "/certificates/mine",
    summary="我的电子证书（学生端）",
    dependencies=[Depends(require_permissions(Permission.CERTIFICATE_VIEW))],
)
def list_my_certificates(
    pq: PageQuery = Depends(page_query),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_student(current)
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


@router.get("/certificates/verify/{verify_code}", summary="证书验真（公开，无需登录）")
def verify_certificate(verify_code: str, db: Session = Depends(get_db)):
    row = db.scalar(
        select(Certificate).where(Certificate.verify_code == verify_code.strip().upper(), Certificate.is_deleted.is_(False))
    )
    if row is None:
        return ok(
            CertificateVerifyOut(
                valid=False,
                serial_no="",
                holder_name="",
                activity_title="",
                activity_level="",
                certificate_name="",
                seal_name="",
                message="未查询到该证书，请核对验真码",
            ).model_dump()
        )
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


@router.get("/certificates/{certificate_id}/pdf", summary="下载本人证书 PDF")
def download_certificate(
    certificate_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_student(current)
    row = db.get(Certificate, certificate_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "证书不存在")
    if current.user_id != row.user_id:
        raise BizError(CODE_FORBIDDEN, "无权下载他人的证书", http_status=403)
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
