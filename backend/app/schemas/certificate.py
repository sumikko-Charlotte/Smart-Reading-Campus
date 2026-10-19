"""电子证书 Schema。"""
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel, RequestModel


class CertificateIssueRequest(RequestModel):
    user_ids: list[str] = Field(default_factory=list, description="为空时按活动报名名单批量颁发")
    only_checked_in: bool = Field(default=False, description="仅给已签到的学生颁发")
    certificate_name: str = Field(default="荣誉证书", max_length=64)
    remark: str = Field(default="", max_length=255)


class CertificateOut(ORMModel):
    certificate_id: str
    serial_no: str
    verify_code: str
    user_id: str
    student_name: str
    student_no: str
    college: str
    activity_id: str
    activity_title: str
    activity_level: str
    certificate_name: str
    seal_name: str
    issued_by_name: str
    issued_at: datetime
    status: str


class CertificateVerifyOut(RequestModel):
    valid: bool
    serial_no: str
    holder_name: str
    activity_title: str
    activity_level: str
    certificate_name: str
    seal_name: str
    issued_at: datetime | None = None
    message: str = ""


class CertificateIssueResult(RequestModel):
    issued: int
    skipped: int
    skipped_reason: str = ""
    certificates: list[CertificateOut] = Field(default_factory=list)
